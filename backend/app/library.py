"""Import, search, albums/artists, upload (with per-user storage limit), delete, download, streaming."""

import asyncio
import base64
import hashlib
import itertools
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

import httpx
import mutagen
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from mutagen.flac import Picture
from pydantic import BaseModel, Field
from sqlalchemy import func, literal, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from . import audiotags, sidecars
from .auth import CurrentUser, storage_used
from .config import settings
from .db import SessionDep
from .models import GB, Album, Artist, Track, User, track_artists

router = APIRouter(prefix="/api", tags=["library"])
log = logging.getLogger("varsis.library")

# Formats browsers can play natively. Files are always served as-is (no transcoding).
MIME = {
    "flac": "audio/flac",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
}
UA = {"User-Agent": "Varsis/0.1 (self-hosted music server)"}


# ---------- import ----------


MAX_NAME = 150  # bytes; file systems allow 255 per name, the rest is room for " (2)" and the like


def _safe(name: str) -> str:
    """Make a name safe to use as one file or folder name.

    Path separators, control characters and the characters Windows forbids become "_", and the name is cut to
    MAX_NAME bytes. The extension survives the cut (a long "….flac" must stay a .flac).

    Args:
        name: A name from a tag or from an uploaded file.

    Returns:
        The safe name, "Unknown" when nothing is left of it.
    """
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    suffix = Path(name).suffix
    if len(suffix.encode()) > 16:  # not an extension, just a dot somewhere in a long name
        suffix = ""
    stem = name[: len(name) - len(suffix)].encode()[: MAX_NAME - len(suffix.encode())]
    return (stem.decode(errors="ignore").strip(" .") + suffix) or "Unknown"


def _reserve(folder: Path, name: str) -> Path:
    """Create an empty file with a free name in `folder` ("x.flac", "x (1).flac", …).

    Creating it is what claims the name, so two imports running at once can't both pick the same one.

    Args:
        folder: The folder, which must exist.
        name: The name to use if it's free.

    Returns:
        The path of the new, empty file.
    """
    stem, suffix = Path(name).stem, Path(name).suffix
    for n in itertools.count():
        dest = folder / (name if n == 0 else f"{stem} ({n}){suffix}")
        try:
            dest.touch(exist_ok=False)
            return dest
        except FileExistsError:
            continue


# Held while artists/albums are created or removed, so two imports at once can't create the same artist or album
# twice (and a delete can't remove an artist that an import is just about to use).
_library_lock = asyncio.Lock()
_user_locks: dict[int, asyncio.Lock] = {}


def user_lock(user_id: int) -> asyncio.Lock:
    """Get the lock that allows one import at a time per user.

    The storage limit is checked and then used, which must not interleave.

    Args:
        user_id: The user.

    Returns:
        Their lock, created the first time it is asked for.
    """
    return _user_locks.setdefault(user_id, asyncio.Lock())


def _first(tags: dict[str, list[str]], key: str) -> str | None:
    """Get the first value of a tag.

    Args:
        tags: The file's tags (see audiotags.text_tags()).
        key: The tag's name, e.g. "title".

    Returns:
        The value. None when the file doesn't have the tag.
    """
    return (tags.get(key) or [None])[0]


def _int(value: str | None) -> int | None:
    """Get the number a tag value starts with ("3/12" -> 3, "2019-05-01" -> 2019), or None when it has none."""
    m = re.match(r"\d+", value or "")
    return int(m.group()) if m else None


def _names(values) -> list[str]:
    """Get the artist names from tag values; one value may hold several separated by ";"."""
    return [n.strip() for v in values or [] for n in str(v).split(";") if n.strip()]


FRONT_COVER = 3  # picture type in FLAC / ID3


def _embedded_cover(path: Path) -> bytes | None:
    """Get the picture stored inside an audio file.

    Args:
        path: The audio file.

    Returns:
        The bytes of its embedded front cover, else of its first picture. None when it has no picture or isn't
        a kind of file mutagen knows.
    """
    f = mutagen.File(path)
    if f is None:
        return None
    tags = f.tags or {}
    if "covr" in tags:  # MP4 (no picture types)
        return bytes(tags["covr"][0])
    pictures = list(getattr(f, "pictures", None) or [])  # FLAC
    if hasattr(tags, "getall"):  # ID3: MP3, WAV
        pictures += tags.getall("APIC")
    elif hasattr(tags, "get"):  # Ogg Vorbis / Opus: base64 FLAC picture blocks
        for b64 in tags.get("metadata_block_picture") or []:
            try:
                pictures.append(Picture(base64.b64decode(b64)))
            except (ValueError, mutagen.MutagenError):
                pass
    pictures.sort(key=lambda p: p.type != FRONT_COVER)  # front covers first; the others keep their order
    return pictures[0].data if pictures else None


COVER_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}


def _image_type(data: bytes) -> str | None:
    """Recognise a picture's format from its first bytes, not from a file name anyone could have chosen.

    Args:
        data: The content of the file.

    Returns:
        "jpg", "png", "webp" or "gif". None for anything else.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def _save_cover(data: bytes | None) -> str | None:
    """Store a picture in covers_dir under a name made from its content (so tracks/albums can share it).

    Args:
        data: The picture's bytes, or None.

    Returns:
        The file name inside covers_dir. None when there is no data or it isn't a JPEG, PNG, WebP or GIF.
    """
    ext = _image_type(data) if data else None
    if not ext:
        return None
    name = f"{hashlib.sha256(data).hexdigest()[:32]}.{ext}"
    path = Path(settings.covers_dir) / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return name


def _read_bytes(path: Path | None) -> bytes | None:
    """Read a file's content, or None when there is no path or the file can't be read."""
    try:
        return path.read_bytes() if path else None
    except OSError:
        return None


async def _remove_unused_covers(db: AsyncSession, names: set[str | None]):
    """Delete the cover files that no album or track uses any more.

    Args:
        db: Database session.
        names: File names in covers_dir to check. None entries are skipped.
    """
    for name in filter(None, names):
        in_use = await db.scalar(select(Album.id).where(Album.cover == name).limit(1))
        in_use = in_use or await db.scalar(select(Track.id).where(Track.cover == name).limit(1))
        if not in_use:
            (Path(settings.covers_dir) / name).unlink(missing_ok=True)


def _quoted(text: str) -> str:
    """Put text in quotes for a MusicBrainz search, so it is searched as one phrase."""
    return '"' + re.sub(r'(["\\])', r"\\\1", text) + '"'  # a Lucene phrase: escape quotes and backslashes


async def _musicbrainz_cover(artist: str, album: str) -> bytes | None:
    """Look an album's front cover up on MusicBrainz and the Cover Art Archive.

    Args:
        artist: The album artist's name.
        album: The album's title.

    Returns:
        The picture of the best matching release (500 px version). None when no release matches, it has no
        cover, or the lookup failed.
    """
    query = f"release:{_quoted(album)} AND artist:{_quoted(artist)}"
    try:
        async with httpx.AsyncClient(headers=UA, timeout=15, follow_redirects=True) as c:
            r = await c.get("https://musicbrainz.org/ws/2/release/", params={"query": query, "fmt": "json", "limit": 1})
            releases = r.json().get("releases") or []
            if not releases:
                return None
            img = await c.get(f"https://coverartarchive.org/release/{releases[0]['id']}/front-500")
            return img.content if img.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):  # network error or unexpected JSON
        return None


async def _fetch_cover(db: AsyncSession, album: Album, artist: str):
    """Fetch the Cover Art Archive picture for a new album that came without one.

    Runs after the import, outside the lock, and once per album (not once per track: MusicBrainz allows about one
    request a second). Commits when a cover was found.

    Args:
        db: Database session.
        album: The new album.
        artist: The album artist's name.
    """
    cover = _save_cover(await _musicbrainz_cover(artist, album.title))
    if not cover:
        return
    # Only if it still has none: another track of the album may have brought its own picture meanwhile.
    await db.execute(update(Album).where(Album.id == album.id, Album.cover.is_(None)).values(cover=cover))
    await db.commit()
    await db.refresh(album)
    await _remove_unused_covers(db, {cover})


def import_error(e: Exception) -> str:
    """Say why a file wasn't imported, in words for the user.

    mutagen's and the OS's own messages contain the server's folder paths, so they aren't passed on.

    Args:
        e: The error that import_file() raised.

    Returns:
        A message that is safe to show.
    """
    if isinstance(e, mutagen.MutagenError):
        return "Not a readable audio file (it may be damaged)"
    if isinstance(e, OSError):
        return f"Could not be saved: {e.strerror or 'file error'}"
    return str(e)  # ValueError: our own messages


async def _artist(db: AsyncSession, name: str) -> Artist:
    """Get the artist with this exact name, creating it when it doesn't exist yet.

    Callers hold _library_lock, so two imports can't both create it.

    Args:
        db: Database session.
        name: The artist's name.

    Returns:
        The artist. A new one is flushed (it has an id) but not committed.
    """
    artist = await db.scalar(select(Artist).where(Artist.name == name))
    if not artist:
        artist = Artist(name=name)
        db.add(artist)
        await db.flush()
    return artist


async def _album(db: AsyncSession, title: str, artist_name: str | None, **new) -> tuple[Album, bool]:
    """Get the album with this title and album artist, creating it when it doesn't exist yet.

    Callers hold _library_lock, so two imports can't both create it.

    Args:
        db: Database session.
        title: The album's title.
        artist_name: The album artist's name, None for an album without one.
        **new: Fields for a new album (year, cover).

    Returns:
        The album and whether it is new. A new one is flushed (it has an id) but not committed.
    """
    artist = await _artist(db, artist_name) if artist_name else None
    album = await db.scalar(
        select(Album).where(Album.title == title, Album.artist_id == (artist.id if artist else None))
    )
    if album:
        return album, False
    album = Album(title=title, artist=artist, **new)
    db.add(album)
    await db.flush()
    return album, True


def _sha256(path: Path) -> str:
    """Hash a file's content, reading it in pieces so a big file doesn't have to fit in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024**2):
            digest.update(chunk)
    return digest.hexdigest()


async def _duplicate(db: AsyncSession, size: int, content_hash: str) -> Track | None:
    """Find the track that has exactly this file.

    Only tracks of the same size can be it. Those from before hashes were stored are hashed now, once.

    Args:
        db: Database session.
        size: The new file's size in bytes.
        content_hash: Its SHA-256.

    Returns:
        The track with the same content, or None. Hashes worked out on the way are not committed yet.
    """
    for other in await db.scalars(select(Track).where(Track.size == size).order_by(Track.id)):
        if other.content_hash is None:
            try:
                other.content_hash = await asyncio.to_thread(_sha256, Path(other.path))
            except OSError:  # its file is missing: nothing to compare with
                continue
        if other.content_hash == content_hash:
            return other
    return None


async def import_file(
    db: AsyncSession, src: Path, original_name: str, user_id: int | None, extras: sidecars.Extras | None = None
) -> Track:
    """Import one audio file: read its tags, move it into the library, create the track.

    The file ends up in music_dir/Artist/Album/, and the track's artists, album and covers are created as needed.
    Commits. If anything fails, the file is not left behind in the library.

    Args:
        db: Database session.
        src: Where the file is now. It is moved, not copied.
        original_name: The file's name as the user knows it. It decides the format and the name in the library.
        user_id: The uploader, whose storage the file counts against. None for nobody.
        extras: What the files next to it say (folder cover, XML/NFO tags), used where the file's own tags are
            empty.

    Returns:
        The new track.

    Raises:
        ValueError: If the format isn't supported, the file isn't audio that can be read, or the same file is
            already in the library.
        mutagen.MutagenError: If the file is damaged.
        OSError: If the file can't be moved into the library.
    """
    ext = Path(original_name).suffix.lower().lstrip(".")
    if ext not in MIME:
        raise ValueError(f"Unsupported format: .{ext}")
    audio = mutagen.File(src, easy=True)
    if audio is None:
        raise ValueError("Not a readable audio file")
    tags = audiotags.text_tags(audio, src)
    extras = extras or sidecars.Extras()

    size, content_hash = src.stat().st_size, await asyncio.to_thread(_sha256, src)
    if same := await _duplicate(db, size, content_hash):
        await db.commit()  # keeps the hashes that were worked out while looking
        raise ValueError(f'Already in the library as "{same.title}"')

    def tag(key: str) -> str | None:
        """Get a tag from the file itself, else from the files next to it."""
        return _first(tags, key) or extras.tags.get(key)

    # Track artists: the file's own, else the sidecars', else the album artist (unless that is "Various Artists").
    names = _names(tags.get("artist")) or _names([extras.tags.get("artist") or ""])
    various = audiotags.VARIOUS.casefold()
    if not names and tag("albumartist") and tag("albumartist").casefold() != various:
        names = [tag("albumartist")]
    title = tag("title") or Path(original_name).stem
    album_title = tag("album")
    # Album artist: the tag (sidecars.find() fills it in for a folder's compilation), else the first track artist.
    album_artist_name = tag("albumartist") or (
        audiotags.VARIOUS if audiotags.is_compilation(tags) else names[0] if names else None
    )

    # Move into /music/Artist/Album/<file>, avoiding name clashes.
    folder = Path(settings.music_dir) / _safe(album_artist_name or "Unknown Artist") / _safe(album_title or "Singles")
    folder.mkdir(parents=True, exist_ok=True)
    dest = _reserve(folder, _safe(Path(original_name).name))
    album, new_album = None, False
    try:
        await asyncio.to_thread(shutil.move, src, dest)
        async with _library_lock:
            artists = [await _artist(db, name) for name in dict.fromkeys(names)]  # fromkeys: no name twice
            if album_title:
                album, new_album = await _album(db, album_title, album_artist_name, year=_int(tag("date")))
                if not album.cover:  # the folder's cover picture, else the embedded one (else Cover Art Archive)
                    album.cover = _save_cover(_read_bytes(extras.cover)) or _save_cover(_embedded_cover(dest))

            track = Track(
                title=title,
                album=album,
                # A track without an album shows its own picture (an album's tracks show the album cover).
                cover=None if album else _save_cover(_embedded_cover(dest)) or _save_cover(_read_bytes(extras.cover)),
                track_no=_int(tag("tracknumber")),
                duration=audio.info.length or 0,
                format=ext,
                mime=MIME[ext],
                path=str(dest),
                size=size,
                content_hash=content_hash,
                uploaded_by=user_id,
                needs_artists=not artists,
                artists=artists,
            )
            db.add(track)
            await db.commit()
    except BaseException:
        # Not in the database, so it must not stay in the library folder (it would use disk space nobody can see).
        dest.unlink(missing_ok=True)
        raise
    if new_album and not album.cover and album_artist_name:
        await _fetch_cover(db, album, album_artist_name)
    return track


# ---------- serialization ----------


def album_out(a: Album | None):
    """Describe an album the way the frontend gets it. None stays None (a track without an album)."""
    if not a:
        return None
    return {
        "id": a.id,
        "title": a.title,
        "year": a.year,
        "cover": a.cover,
        "artist": {"id": a.artist.id, "name": a.artist.name} if a.artist else None,
    }


def track_out(t: Track):
    """Describe a track the way the frontend gets it, with its album and artists. The file path is left out."""
    return {
        "id": t.id,
        "title": t.title,
        "track_no": t.track_no,
        "duration": t.duration,
        "format": t.format,
        "size": t.size,
        "cover": t.cover,
        "needs_artists": t.needs_artists,
        "uploaded_by": t.uploaded_by,
        "album": album_out(t.album),
        "artists": [{"id": a.id, "name": a.name} for a in t.artists],
    }


async def get_track(db: AsyncSession, track_id: int) -> Track:
    """Load a track.

    Args:
        db: Database session.
        track_id: The track.

    Returns:
        The track, with its album and artists loaded.

    Raises:
        HTTPException: 404 when it doesn't exist.
    """
    track = await db.get(Track, track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    return track


async def own_track(db: AsyncSession, track_id: int, user: User) -> Track:
    """Load a track the user may change: one they uploaded (admins may change any).

    Args:
        db: Database session.
        track_id: The track.
        user: The logged-in user.

    Returns:
        The track.

    Raises:
        HTTPException: 404 when it doesn't exist, 403 when someone else uploaded it.
    """
    track = await get_track(db, track_id)
    if not user.is_admin and track.uploaded_by != user.id:
        raise HTTPException(403, "You can only change tracks you uploaded")
    return track


# ---------- routes ----------


@router.get("/search")
async def search(db: SessionDep, _: CurrentUser, q: Annotated[str, Query(max_length=200)] = ""):
    """Search the library by track title, album title and artist name. Typos and partial words still match.

    Args:
        db: Database session.
        q: What to look for. Empty gives the 50 newest tracks instead.

    Returns:
        `tracks` (up to 50), `albums` and `artists` (up to 20 each), best match first.
    """
    q = q.strip()
    if not q:  # empty query: latest tracks
        tracks = await db.scalars(select(Track).order_by(Track.id.desc()).limit(50))
        return {"tracks": [track_out(t) for t in tracks], "albums": [], "artists": []}

    # Word similarity (pg_trgm `<%`) matches typos/partial words inside longer titles; ILIKE catches exact substrings.
    def match(col):
        """Build the condition that a column matches the query."""
        return or_(literal(q).op("<%")(col), col.icontains(q, autoescape=True))

    def rank(col):
        """Build the ordering that puts the best match of a column first."""
        return func.word_similarity(q, col).desc()

    tracks = await db.scalars(select(Track).where(match(Track.title)).order_by(rank(Track.title)).limit(50))
    albums = await db.scalars(select(Album).where(match(Album.title)).order_by(rank(Album.title)).limit(20))
    artists = await db.scalars(select(Artist).where(match(Artist.name)).order_by(rank(Artist.name)).limit(20))
    return {
        "tracks": [track_out(t) for t in tracks],
        "albums": [album_out(a) for a in albums],
        "artists": [{"id": a.id, "name": a.name} for a in artists],
    }


@router.get("/tracks")
async def tracks_needing_artists(db: SessionDep, user: CurrentUser, needs_artists: bool = True):
    """List the user's own uploads (all tracks for admins) that need / don't need artists.

    Args:
        db: Database session.
        user: The logged-in user.
        needs_artists: True for the tracks whose tags named no artist, False for all the others.

    Returns:
        Up to 500 tracks, newest first.
    """
    query = select(Track).where(Track.needs_artists == needs_artists)
    if not user.is_admin:
        query = query.where(Track.uploaded_by == user.id)
    rows = await db.scalars(query.order_by(Track.id.desc()).limit(500))
    return [track_out(t) for t in rows]


Offset = Annotated[int, Query(ge=0)]
PageSize = Annotated[int, Query(ge=1, le=200)]


@router.get("/albums")
async def list_albums(
    db: SessionDep, _: CurrentUser, offset: Offset = 0, limit: PageSize = 60, sort: Literal["title", "recent"] = "title"
):
    """List every album in the library, a page at a time.

    Args:
        db: Database session.
        offset: How many albums to skip.
        limit: How many to return at most.
        sort: "title" for A to Z, "recent" for the newest first.

    Returns:
        `total`, the number of albums in the library, and `items`, this page (see album_out()).
    """
    order = (Album.id.desc(),) if sort == "recent" else (func.lower(Album.title), Album.id)
    albums = await db.scalars(select(Album).order_by(*order).offset(offset).limit(limit))
    total = await db.scalar(select(func.count()).select_from(Album))
    return {"total": total, "items": [album_out(a) for a in albums]}


@router.get("/artists")
async def list_artists(db: SessionDep, _: CurrentUser, offset: Offset = 0, limit: PageSize = 60):
    """List every artist in the library from A to Z, a page at a time.

    Args:
        db: Database session.
        offset: How many artists to skip.
        limit: How many to return at most.

    Returns:
        `total`, the number of artists in the library, and `items`, the id and name of this page's artists.
    """
    artists = await db.scalars(select(Artist).order_by(func.lower(Artist.name), Artist.id).offset(offset).limit(limit))
    total = await db.scalar(select(func.count()).select_from(Artist))
    return {"total": total, "items": [{"id": a.id, "name": a.name} for a in artists]}


@router.get("/albums/{album_id}")
async def get_album(album_id: int, db: SessionDep, _: CurrentUser):
    """Get an album with its tracks.

    Args:
        album_id: The album.
        db: Database session.

    Returns:
        The album (see album_out()) plus `tracks`, by track number and then title.

    Raises:
        HTTPException: 404 when it doesn't exist.
    """
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404, "Album not found")
    tracks = await db.scalars(select(Track).where(Track.album_id == album_id).order_by(Track.track_no, Track.title))
    return {**album_out(album), "tracks": [track_out(t) for t in tracks]}


@router.get("/artists/{artist_id}")
async def get_artist(artist_id: int, db: SessionDep, _: CurrentUser):
    """Get an artist with their albums and tracks.

    Args:
        artist_id: The artist.
        db: Database session.

    Returns:
        The artist's id and name, `albums` where they are the album artist (oldest first) and `tracks`, every
        track they are an artist of (by title).

    Raises:
        HTTPException: 404 when they don't exist.
    """
    artist = await db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(404, "Artist not found")
    albums = await db.scalars(select(Album).where(Album.artist_id == artist_id).order_by(Album.year, Album.title))
    tracks = await db.scalars(select(Track).where(Track.artists.any(Artist.id == artist_id)).order_by(Track.title))
    return {
        "id": artist.id,
        "name": artist.name,
        "albums": [album_out(a) for a in albums],
        "tracks": [track_out(t) for t in tracks],
    }


async def _remove_unused_artists(db: AsyncSession, artist_ids: set[int]):
    """Delete the artists among `artist_ids` that no track or album refers to any more.

    Callers hold _library_lock and commit afterwards.

    Args:
        db: Database session.
        artist_ids: The artists that may have lost their last track or album.
    """
    for artist_id in artist_ids:
        used = await db.scalar(select(track_artists.c.track_id).where(track_artists.c.artist_id == artist_id).limit(1))
        used = used or await db.scalar(select(Album.id).where(Album.artist_id == artist_id).limit(1))
        if not used:
            await db.delete(await db.get(Artist, artist_id))


async def _move_to_album(db: AsyncSession, track: Track, title: str, artist_name: str | None):
    """Put a track into the album with this title and album artist, or take it out of its album.

    The album is created when it doesn't exist yet; it then starts with the year and cover of the album the track
    comes from (which is what renaming an album track by track needs). The audio file stays where it is on disk.
    Callers hold _library_lock; the album the track leaves is not removed here.

    Args:
        db: Database session.
        track: The track to move.
        title: The album's title. Empty for no album.
        artist_name: The album artist's name. None for the artist of the track's current album, else the track's
            first artist.
    """
    old = track.album
    if not title:
        track.cover = track.cover or (old.cover if old else None)  # it keeps the picture it was shown with
        track.album = None
        return
    if artist_name is None and old:
        artist_name = old.artist.name if old.artist else None
    elif artist_name is None:
        artist_name = track.artists[0].name if track.artists else None
    album, _ = await _album(db, title, artist_name, year=old.year if old else None, cover=old.cover if old else None)
    album.cover = album.cover or track.cover
    track.album, track.cover = album, None  # an album's tracks show the album cover


class TrackEdit(BaseModel):
    """Changes to a track. Fields that are left out stay as they are."""

    title: Annotated[str, Field(max_length=500)] | None = None
    artists: list[Annotated[str, Field(max_length=200)]] | None = Field(None, max_length=50)
    album: Annotated[str, Field(max_length=500)] | None = None  # the album's title; "" takes the track out of it
    # With `album`. Left out: the album artist stays (a track without an album: its first artist). "" for none.
    album_artist: Annotated[str, Field(max_length=200)] | None = None


@router.patch("/tracks/{track_id}")
async def edit_track(track_id: int, data: TrackEdit, db: SessionDep, user: CurrentUser):
    """Change a track's title, artists or album.

    Artists and albums that don't exist yet are created, and ones that nothing uses any more are deleted. A track
    whose artists are set no longer counts as needing them. Only the library changes: the audio file and its
    tags stay as they were uploaded.

    Args:
        track_id: The track.
        data: The changes.
        db: Database session.
        user: The logged-in user, who must have uploaded the track or be an admin.

    Returns:
        The updated track (see track_out()).

    Raises:
        HTTPException: 404 when the track doesn't exist, 403 when someone else uploaded it, 422 when the new
            title or every artist name is blank.
    """
    track = await own_track(db, track_id, user)
    title = data.title.strip() if data.title is not None else None
    names = [n.strip() for n in data.artists if n.strip()] if data.artists is not None else None
    if title == "":
        raise HTTPException(422, "The title can't be empty")
    if names == []:
        raise HTTPException(422, "At least one artist name required")
    old_album, covers = track.album, {track.cover}
    async with _library_lock:
        maybe_unused = {a.id for a in track.artists} | ({old_album.artist_id} if old_album else set())
        if title:
            track.title = title
        if names:
            track.artists = [await _artist(db, n) for n in dict.fromkeys(names)]
            track.needs_artists = False
        if data.album is not None:
            album_artist = data.album_artist.strip() if data.album_artist is not None else None
            await _move_to_album(db, track, data.album.strip(), album_artist)
        await db.flush()
        left = old_album and track.album is not old_album
        if left and not await db.scalar(select(Track.id).where(Track.album_id == old_album.id).limit(1)):
            covers.add(old_album.cover)  # it was the album's last track: the album goes too
            await db.delete(old_album)
            await db.flush()
        await _remove_unused_artists(db, maybe_unused - {None})  # e.g. a misspelt name
        await db.commit()
    await _remove_unused_covers(db, covers)
    return track_out(track)


def gb(n: int) -> str:
    """Write a number of bytes as text in GB, e.g. "1.5 GB"."""
    return f"{n / GB:.1f} GB"


def _rel_path(name: str) -> Path:
    """Make a path from the browser ("Album/CD1/01.flac") safe to use inside a folder: no "..", no absolute path.

    Args:
        name: The path as the browser sent it, with slashes or backslashes between the parts.

    Returns:
        A relative path of at most its last 8 parts, each made safe. "upload" when nothing is left.
    """
    parts = [_safe(p) for p in re.split(r"[\\/]+", name) if p not in ("", ".", "..")]
    return Path(*parts[-8:]) if parts else Path("upload")


MAX_UPLOAD_FILES = 2000  # per request (the upload page sends at most 500)


@router.post("/upload")
async def upload(request: Request, db: SessionDep, user: CurrentUser):
    """Upload audio files or a folder, as a multipart form.

    The form has `files`, the files, and `paths`, each file's path in the uploaded folder ("Album/CD1/01.flac") in
    the same order. Pictures and XML/NFO files sent along are used for album covers and missing tags, then
    discarded (they don't count against the storage limit).

    Args:
        request: The incoming request, which the form is read from.
        db: Database session.
        user: The logged-in user, who becomes the uploader.

    Returns:
        `imported`, the new tracks, and `errors`, one entry with the reason for every file that wasn't imported.

    Raises:
        HTTPException: 403 when the user's storage is already full, 422 when no files were sent.
    """
    user_id, quota = user.id, user.quota  # rollback() expires ORM objects; keep plain values
    if quota is not None and await storage_used(db, user_id) >= quota:
        raise HTTPException(403, "Your storage is full. Ask an admin for more space.")
    incoming = Path(settings.music_dir) / ".incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    # The form is read here instead of being a parameter: FastAPI would receive the whole upload (up to 2 GB,
    # written to disk) before checking the login and the storage limit above.
    async with request.form(max_files=MAX_UPLOAD_FILES, max_fields=MAX_UPLOAD_FILES) as form:
        files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
        paths = [p for p in form.getlist("paths") if isinstance(p, str)]
        if not files:
            raise HTTPException(422, "No files were sent")
        async with user_lock(user_id):  # two uploads at once would each see the same free space
            return await _upload(db, files, paths, user_id, quota, incoming)


async def _upload(db: AsyncSession, files: list[UploadFile], paths: list[str], user_id: int, quota, incoming: Path):
    """Do the work of upload(): save the files to a temporary folder, then import the audio ones.

    The caller holds the user's lock. The temporary folder is removed again whatever happens.

    Args:
        db: Database session.
        files: The uploaded files.
        paths: Their paths in the uploaded folder, in the same order. May be shorter than `files`.
        user_id: The uploader.
        quota: The uploader's storage limit in bytes, None for no limit.
        incoming: The folder to create the temporary folder in.

    Returns:
        The same as upload().
    """
    used = await storage_used(db, user_id)
    root = Path(tempfile.mkdtemp(dir=incoming))
    audio, others, imported, errors = [], [], [], []  # audio: (path on disk, path the user sees)
    try:
        for i, f in enumerate(files):
            shown = paths[i] if i < len(paths) else f.filename or "upload"
            rel = _rel_path(shown)
            ext, size = sidecars.suffix(rel), f.size or 0  # size is set by the multipart parser
            if ext in MIME:
                if quota is not None and used + size > quota:
                    errors.append(
                        {
                            "file": shown,
                            "error": f"Not enough storage left: you've used {gb(used)} of {gb(quota)}. "
                            "Ask an admin for more space.",
                        }
                    )
                    continue
                used += size
            elif ext in sidecars.SIDECARS and size > sidecars.MAX_SIDECAR:
                errors.append(
                    {"file": shown, "error": "Not used: cover pictures and XML/NFO files must be under 20 MB"}
                )
                continue
            elif ext not in sidecars.SIDECARS:
                errors.append({"file": shown, "error": f"Unsupported format: .{ext}"})
                continue
            dest = root / rel
            if dest.exists():  # two names that became the same once made safe
                dest = dest.with_name(f"{i} {dest.name}")
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as out:
                    await asyncio.to_thread(shutil.copyfileobj, f.file, out)
            except OSError as e:  # e.g. a file and a folder with the same name
                errors.append({"file": shown, "error": import_error(e)})
                continue
            (audio if ext in MIME else others).append((dest, shown))

        audio.sort(key=lambda x: x[1].lower())  # folder order: the first track of an album sets its cover
        extras = sidecars.find(root, [p for p, _ in audio], [p for p, _ in others])
        for path, shown in audio:
            try:
                track = await import_file(db, path, path.name, user_id, extras[path])
                imported.append(track_out(track))
            except (ValueError, OSError, mutagen.MutagenError) as e:  # per-file error, keep going
                await db.rollback()
                errors.append({"file": shown, "error": import_error(e)})
            except SQLAlchemyError:
                await db.rollback()
                log.exception("import of %s failed", shown)
                errors.append({"file": shown, "error": "Could not be saved to the library (database error)"})
    finally:
        await asyncio.to_thread(shutil.rmtree, root, True)
    return {"imported": imported, "errors": errors}


@router.delete("/tracks/{track_id}", status_code=204)
async def delete_track(track_id: int, db: SessionDep, user: CurrentUser):
    """Delete a track and its file (frees the uploader's storage). Removes its album/artists if now unused.

    Args:
        track_id: The track.
        db: Database session.
        user: The logged-in user, who must have uploaded the track or be an admin.

    Raises:
        HTTPException: 404 when the track doesn't exist, 403 when someone else uploaded it.
    """
    track = await own_track(db, track_id, user)
    path, album, covers = Path(track.path), track.album, {track.cover}
    artist_ids = {a.id for a in track.artists} | ({album.artist_id} if album and album.artist_id else set())
    async with _library_lock:
        await db.delete(track)
        await db.flush()
        if album and not await db.scalar(select(Track.id).where(Track.album_id == album.id).limit(1)):
            covers.add(album.cover)
            await db.delete(album)
            await db.flush()
        await _remove_unused_artists(db, artist_ids)
        await db.commit()
    path.unlink(missing_ok=True)
    await _remove_unused_covers(db, covers)
    for folder in (path.parent, path.parent.parent):  # Album/ and Artist/ folders, if now empty
        try:
            folder.rmdir()
        except OSError:
            break


async def _track_file(db: AsyncSession, track_id: int) -> Track:
    """Load a track whose audio file has to be there.

    Args:
        db: Database session.
        track_id: The track.

    Returns:
        The track.

    Raises:
        HTTPException: 404 when the track doesn't exist or its file is missing on disk.
    """
    track = await get_track(db, track_id)
    if not Path(track.path).is_file():
        raise HTTPException(404, "This track's file is missing on the server")
    return track


@router.get("/tracks/{track_id}/stream")
async def stream(track_id: int, db: SessionDep, _: CurrentUser):
    """Send a track's audio for playing in the browser, as it is on disk.

    Args:
        track_id: The track.
        db: Database session.

    Returns:
        The audio file.

    Raises:
        HTTPException: 404 when the track doesn't exist or its file is missing.
    """
    track = await _track_file(db, track_id)
    return FileResponse(track.path, media_type=track.mime)  # supports HTTP Range (seeking)


@router.get("/tracks/{track_id}/download")
async def download(track_id: int, db: SessionDep, _: CurrentUser):
    """Send a track's audio as a download, under the file's name in the library.

    Args:
        track_id: The track.
        db: Database session.

    Returns:
        The audio file, marked as an attachment.

    Raises:
        HTTPException: 404 when the track doesn't exist or its file is missing.
    """
    track = await _track_file(db, track_id)
    return FileResponse(track.path, media_type=track.mime, filename=Path(track.path).name)


@router.get("/covers/{name}")
async def cover(name: str, _: CurrentUser):
    """Send a cover picture.

    Args:
        name: Its file name, as in the `cover` field of a track or album.

    Returns:
        The picture.

    Raises:
        HTTPException: 404 when there is no such picture.
    """
    # Only the last part of the name is used, so "../…" can't reach files outside covers_dir.
    path = Path(settings.covers_dir) / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type=COVER_TYPES.get(sidecars.suffix(path), "image/jpeg"))
