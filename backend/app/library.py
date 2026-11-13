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
from typing import Annotated

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

from . import sidecars
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
    """A file or folder name without path separators or control characters, cut to MAX_NAME bytes.
    The extension survives the cut (a long "….flac" must stay a .flac)."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    suffix = Path(name).suffix
    if len(suffix.encode()) > 16:  # not an extension, just a dot somewhere in a long name
        suffix = ""
    stem = name[: len(name) - len(suffix)].encode()[: MAX_NAME - len(suffix.encode())]
    return (stem.decode(errors="ignore").strip(" .") + suffix) or "Unknown"


def _reserve(folder: Path, name: str) -> Path:
    """Create an empty file with a free name in `folder` ("x.flac", "x (1).flac", …) and return its path.
    Creating it is what claims the name, so two imports running at once can't both pick the same one."""
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
    """One import at a time per user: the storage limit is checked and then used, which must not interleave."""
    return _user_locks.setdefault(user_id, asyncio.Lock())


def _first(tags, key) -> str | None:
    vals = tags.get(key) if tags else None
    return str(vals[0]).strip() or None if vals else None


def _int(value: str | None) -> int | None:
    m = re.match(r"\d+", value or "")
    return int(m.group()) if m else None


def _names(values) -> list[str]:
    """Artist names from tag values; one value may hold several separated by ";"."""
    return [n.strip() for v in values or [] for n in str(v).split(";") if n.strip()]


FRONT_COVER = 3  # picture type in FLAC / ID3


def _embedded_cover(path: Path) -> bytes | None:
    """The file's embedded front cover, else its first picture."""
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
    pictures.sort(key=lambda p: p.type != FRONT_COVER)
    return pictures[0].data if pictures else None


COVER_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}


def _image_type(data: bytes) -> str | None:
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
    """Store a picture in covers_dir under a name made from its content (so tracks/albums can share it)."""
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
    try:
        return path.read_bytes() if path else None
    except OSError:
        return None


async def _remove_unused_covers(db: AsyncSession, names: set[str | None]):
    for name in filter(None, names):
        in_use = await db.scalar(select(Album.id).where(Album.cover == name).limit(1))
        in_use = in_use or await db.scalar(select(Track.id).where(Track.cover == name).limit(1))
        if not in_use:
            (Path(settings.covers_dir) / name).unlink(missing_ok=True)


def _quoted(text: str) -> str:
    return '"' + re.sub(r'(["\\])', r"\\\1", text) + '"'  # a Lucene phrase: escape quotes and backslashes


async def _musicbrainz_cover(artist: str, album: str) -> bytes | None:
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
    """Cover Art Archive picture for a new album that came without one. Runs after the import, outside the lock,
    and once per album (not once per track: MusicBrainz allows about one request a second)."""
    cover = _save_cover(await _musicbrainz_cover(artist, album.title))
    if not cover:
        return
    # Only if it still has none: another track of the album may have brought its own picture meanwhile.
    await db.execute(update(Album).where(Album.id == album.id, Album.cover.is_(None)).values(cover=cover))
    await db.commit()
    await db.refresh(album)
    await _remove_unused_covers(db, {cover})


def import_error(e: Exception) -> str:
    """Why a file wasn't imported, in words for the user. mutagen's and the OS's own messages contain the server's
    folder paths, so they aren't passed on."""
    if isinstance(e, mutagen.MutagenError):
        return "Not a readable audio file (it may be damaged)"
    if isinstance(e, OSError):
        return f"Could not be saved: {e.strerror or 'file error'}"
    return str(e)  # ValueError: our own messages


async def _artist(db: AsyncSession, name: str) -> Artist:
    artist = await db.scalar(select(Artist).where(Artist.name == name))
    if not artist:
        artist = Artist(name=name)
        db.add(artist)
        await db.flush()
    return artist


async def import_file(
    db: AsyncSession, src: Path, original_name: str, user_id: int | None, extras: sidecars.Extras | None = None
) -> Track:
    """Read tags, move file into the library, create artist/album/track and their covers. Commits.
    `extras`: what the files next to it say (folder cover, XML/NFO tags), used where the file's own tags are empty."""
    ext = Path(original_name).suffix.lower().lstrip(".")
    if ext not in MIME:
        raise ValueError(f"Unsupported format: .{ext}")
    audio = mutagen.File(src, easy=True)
    if audio is None:
        raise ValueError("Not a readable audio file")
    tags = audio.tags
    extras = extras or sidecars.Extras()

    def tag(key: str) -> str | None:
        return _first(tags, key) or extras.tags.get(key)

    names = _names(tags.get("artist") if tags else None) or _names([extras.tags.get("artist") or ""])
    if not names and tag("albumartist"):
        names = [tag("albumartist")]
    title = tag("title") or Path(original_name).stem
    album_title = tag("album")
    album_artist_name = tag("albumartist") or (names[0] if names else None)

    # Move into /music/Artist/Album/<file>, avoiding name clashes.
    folder = Path(settings.music_dir) / _safe(album_artist_name or "Unknown Artist") / _safe(album_title or "Singles")
    folder.mkdir(parents=True, exist_ok=True)
    dest = _reserve(folder, _safe(Path(original_name).name))
    album, new_album = None, False
    try:
        await asyncio.to_thread(shutil.move, src, dest)
        async with _library_lock:
            artists = [await _artist(db, name) for name in dict.fromkeys(names)]
            if album_title:
                album_artist = await _artist(db, album_artist_name) if album_artist_name else None
                album = await db.scalar(
                    select(Album).where(
                        Album.title == album_title, Album.artist_id == (album_artist.id if album_artist else None)
                    )
                )
                if not album:
                    album = Album(title=album_title, artist=album_artist, year=_int(tag("date")))
                    db.add(album)
                    await db.flush()
                    new_album = True
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
                size=dest.stat().st_size,
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
    track = await db.get(Track, track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    return track


async def own_track(db: AsyncSession, track_id: int, user: User) -> Track:
    """A track the user may change: one they uploaded (admins may change any)."""
    track = await get_track(db, track_id)
    if not user.is_admin and track.uploaded_by != user.id:
        raise HTTPException(403, "You can only change tracks you uploaded")
    return track


# ---------- routes ----------


@router.get("/search")
async def search(db: SessionDep, _: CurrentUser, q: Annotated[str, Query(max_length=200)] = ""):
    q = q.strip()
    if not q:  # empty query: latest tracks
        tracks = await db.scalars(select(Track).order_by(Track.id.desc()).limit(50))
        return {"tracks": [track_out(t) for t in tracks], "albums": [], "artists": []}

    # Word similarity (pg_trgm `<%`) matches typos/partial words inside longer titles; ILIKE catches exact substrings.
    def match(col):
        return or_(literal(q).op("<%")(col), col.icontains(q, autoescape=True))

    def rank(col):
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
    """The user's own uploads (all tracks for admins) that need / don't need artists."""
    query = select(Track).where(Track.needs_artists == needs_artists)
    if not user.is_admin:
        query = query.where(Track.uploaded_by == user.id)
    rows = await db.scalars(query.order_by(Track.id.desc()).limit(500))
    return [track_out(t) for t in rows]


@router.get("/albums/{album_id}")
async def get_album(album_id: int, db: SessionDep, _: CurrentUser):
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404, "Album not found")
    tracks = await db.scalars(select(Track).where(Track.album_id == album_id).order_by(Track.track_no, Track.title))
    return {**album_out(album), "tracks": [track_out(t) for t in tracks]}


@router.get("/artists/{artist_id}")
async def get_artist(artist_id: int, db: SessionDep, _: CurrentUser):
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


class ArtistNames(BaseModel):
    names: list[Annotated[str, Field(max_length=200)]] = Field(min_length=1, max_length=50)


async def _remove_unused_artists(db: AsyncSession, artist_ids: set[int]):
    """Delete the artists among `artist_ids` that no track or album refers to any more."""
    for artist_id in artist_ids:
        used = await db.scalar(select(track_artists.c.track_id).where(track_artists.c.artist_id == artist_id).limit(1))
        used = used or await db.scalar(select(Album.id).where(Album.artist_id == artist_id).limit(1))
        if not used:
            await db.delete(await db.get(Artist, artist_id))


@router.put("/tracks/{track_id}/artists")
async def set_artists(track_id: int, data: ArtistNames, db: SessionDep, user: CurrentUser):
    track = await own_track(db, track_id, user)
    names = [n.strip() for n in data.names if n.strip()]
    if not names:
        raise HTTPException(422, "At least one artist name required")
    async with _library_lock:
        before = {a.id for a in track.artists}
        track.artists = [await _artist(db, n) for n in dict.fromkeys(names)]
        track.needs_artists = False
        await db.flush()
        await _remove_unused_artists(db, before - {a.id for a in track.artists})  # e.g. a misspelt name
        await db.commit()
    return track_out(track)


def _gb(n: int) -> str:
    return f"{n / GB:.1f} GB"


def _rel_path(name: str) -> Path:
    """A path from the browser ("Album/CD1/01.flac") made safe to use inside a folder: no "..", no absolute path."""
    parts = [_safe(p) for p in re.split(r"[\\/]+", name) if p not in ("", ".", "..")]
    return Path(*parts[-8:]) if parts else Path("upload")


MAX_UPLOAD_FILES = 2000  # per request (the upload page sends at most 500)


@router.post("/upload")
async def upload(request: Request, db: SessionDep, user: CurrentUser):
    """Upload audio files or a folder, as a multipart form. `files`: the files. `paths`: each file's path in the
    uploaded folder ("Album/CD1/01.flac"), in the same order. Pictures and XML/NFO files sent along are used for
    album covers and missing tags, then discarded (they don't count against the storage limit)."""
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
                            "error": f"Not enough storage left: you've used {_gb(used)} of {_gb(quota)}. "
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
    """Delete a track and its file (frees the uploader's storage). Removes its album/artists if now unused."""
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
    track = await get_track(db, track_id)
    if not Path(track.path).is_file():
        raise HTTPException(404, "This track's file is missing on the server")
    return track


@router.get("/tracks/{track_id}/stream")
async def stream(track_id: int, db: SessionDep, _: CurrentUser):
    track = await _track_file(db, track_id)
    return FileResponse(track.path, media_type=track.mime)  # supports HTTP Range (seeking)


@router.get("/tracks/{track_id}/download")
async def download(track_id: int, db: SessionDep, _: CurrentUser):
    track = await _track_file(db, track_id)
    return FileResponse(track.path, media_type=track.mime, filename=Path(track.path).name)


@router.get("/covers/{name}")
async def cover(name: str, _: CurrentUser):
    path = Path(settings.covers_dir) / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type=COVER_TYPES.get(sidecars.suffix(path), "image/jpeg"))
