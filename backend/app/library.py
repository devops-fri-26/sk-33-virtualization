"""Import, search, albums/artists, upload, download, streaming."""

import asyncio
import re
import shutil
import tempfile
from pathlib import Path

import httpx
import mutagen
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import CurrentUser
from .config import settings
from .db import SessionDep
from .models import Album, Artist, Track

router = APIRouter(prefix="/api", tags=["library"])

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


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")[:120] or "Unknown"


def _first(tags, key) -> str | None:
    vals = tags.get(key) if tags else None
    return str(vals[0]).strip() or None if vals else None


def _int(value: str | None) -> int | None:
    m = re.match(r"\d+", value or "")
    return int(m.group()) if m else None


def _embedded_cover(path: Path) -> bytes | None:
    f = mutagen.File(path)
    if f is None:
        return None
    if getattr(f, "pictures", None):  # FLAC
        return f.pictures[0].data
    tags = f.tags or {}
    if "covr" in tags:  # MP4
        return bytes(tags["covr"][0])
    for key in getattr(tags, "keys", list)():  # ID3 APIC:*
        if key.startswith("APIC"):
            return tags[key].data
    return None


async def _musicbrainz_cover(artist: str, album: str) -> bytes | None:
    query = f'release:"{album}" AND artist:"{artist}"'
    try:
        async with httpx.AsyncClient(headers=UA, timeout=15, follow_redirects=True) as c:
            r = await c.get("https://musicbrainz.org/ws/2/release/", params={"query": query, "fmt": "json", "limit": 1})
            releases = r.json().get("releases") or []
            if not releases:
                return None
            img = await c.get(f"https://coverartarchive.org/release/{releases[0]['id']}/front-500")
            return img.content if img.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


async def _artist(db: AsyncSession, name: str) -> Artist:
    artist = await db.scalar(select(Artist).where(Artist.name == name))
    if not artist:
        artist = Artist(name=name)
        db.add(artist)
        await db.flush()
    return artist


async def import_file(db: AsyncSession, src: Path, original_name: str, user_id: int | None) -> Track:
    """Read tags, move file into the library, create artist/album/track. Commits."""
    ext = Path(original_name).suffix.lower().lstrip(".")
    if ext not in MIME:
        raise ValueError(f"Unsupported format: .{ext}")
    audio = mutagen.File(src, easy=True)
    if audio is None:
        raise ValueError("Not a readable audio file")
    tags = audio.tags

    names = [n.strip() for n in (tags.get("artist") if tags else None) or [] for n in str(n).split(";") if n.strip()]
    if not names and _first(tags, "albumartist"):
        names = [_first(tags, "albumartist")]
    title = _first(tags, "title") or Path(original_name).stem
    album_title = _first(tags, "album")
    album_artist_name = _first(tags, "albumartist") or (names[0] if names else None)

    # Move into /music/Artist/Album/<file>, avoiding name clashes.
    folder = Path(settings.music_dir) / _safe(album_artist_name or "Unknown Artist") / _safe(album_title or "Singles")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / _safe(Path(original_name).name)
    n = 1
    while dest.exists():
        dest = folder / f"{_safe(Path(original_name).stem)} ({n}).{ext}"
        n += 1
    await asyncio.to_thread(shutil.move, src, dest)

    artists = [await _artist(db, name) for name in dict.fromkeys(names)]
    album = None
    if album_title:
        album_artist = await _artist(db, album_artist_name) if album_artist_name else None
        album = await db.scalar(
            select(Album).where(
                Album.title == album_title, Album.artist_id == (album_artist.id if album_artist else None)
            )
        )
        if not album:
            album = Album(title=album_title, artist=album_artist, year=_int(_first(tags, "date")))
            db.add(album)
            await db.flush()
        if not album.cover:
            data = _embedded_cover(dest) or (
                await _musicbrainz_cover(album_artist_name, album_title) if album_artist_name else None
            )
            if data:
                Path(settings.covers_dir).mkdir(parents=True, exist_ok=True)
                (Path(settings.covers_dir) / f"{album.id}.jpg").write_bytes(data)
                album.cover = f"{album.id}.jpg"

    track = Track(
        title=title,
        album=album,
        track_no=_int(_first(tags, "tracknumber")),
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
        "needs_artists": t.needs_artists,
        "album": album_out(t.album),
        "artists": [{"id": a.id, "name": a.name} for a in t.artists],
    }


async def get_track(db: AsyncSession, track_id: int) -> Track:
    track = await db.get(Track, track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    return track


# ---------- routes ----------


@router.get("/search")
async def search(db: SessionDep, _: CurrentUser, q: str = ""):
    q = q.strip()
    if not q:  # empty query: latest tracks
        tracks = await db.scalars(select(Track).order_by(Track.id.desc()).limit(50))
        return {"tracks": [track_out(t) for t in tracks], "albums": [], "artists": []}

    # Word similarity (pg_trgm `<%`) matches typos/partial words inside longer titles; ILIKE catches exact substrings.
    def match(col):
        return or_(literal(q).op("<%")(col), col.ilike(f"%{q}%"))

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
async def tracks_needing_artists(db: SessionDep, _: CurrentUser, needs_artists: bool = True):
    rows = await db.scalars(
        select(Track).where(Track.needs_artists == needs_artists).order_by(Track.id.desc()).limit(500)
    )
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
    names: list[str] = Field(min_length=1)


@router.put("/tracks/{track_id}/artists")
async def set_artists(track_id: int, data: ArtistNames, db: SessionDep, _: CurrentUser):
    track = await get_track(db, track_id)
    names = [n.strip() for n in data.names if n.strip()]
    if not names:
        raise HTTPException(422, "At least one artist name required")
    track.artists = [await _artist(db, n) for n in dict.fromkeys(names)]
    track.needs_artists = False
    await db.commit()
    return track_out(track)


@router.post("/upload")
async def upload(files: list[UploadFile], db: SessionDep, user: CurrentUser):
    incoming = Path(settings.music_dir) / ".incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    user_id = user.id  # rollback() expires ORM objects; keep a plain value
    imported, errors = [], []
    for f in files:
        with tempfile.NamedTemporaryFile(dir=incoming, delete=False) as tmp:
            await asyncio.to_thread(shutil.copyfileobj, f.file, tmp)
        try:
            imported.append(track_out(await import_file(db, Path(tmp.name), f.filename or "upload", user_id)))
        except (ValueError, OSError, mutagen.MutagenError) as e:  # per-file error, keep going
            await db.rollback()
            Path(tmp.name).unlink(missing_ok=True)
            errors.append({"file": f.filename, "error": str(e)})
    return {"imported": imported, "errors": errors}


@router.get("/tracks/{track_id}/stream")
async def stream(track_id: int, db: SessionDep, _: CurrentUser):
    track = await get_track(db, track_id)
    return FileResponse(track.path, media_type=track.mime)  # supports HTTP Range (seeking)


@router.get("/tracks/{track_id}/download")
async def download(track_id: int, db: SessionDep, _: CurrentUser):
    track = await get_track(db, track_id)
    return FileResponse(track.path, media_type=track.mime, filename=Path(track.path).name)


@router.get("/covers/{name}")
async def cover(name: str, _: CurrentUser):
    path = Path(settings.covers_dir) / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")
