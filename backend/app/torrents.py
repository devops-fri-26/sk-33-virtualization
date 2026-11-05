"""Prowlarr search, qBittorrent download jobs, and the poller that imports finished downloads."""

import asyncio
import hashlib
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import httpx
import mutagen
import qbittorrentapi
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from .auth import CurrentUser
from .config import settings
from .db import SessionDep, SessionLocal
from .library import MIME, import_file
from .models import TorrentJob

router = APIRouter(prefix="/api/torrents", tags=["torrents"])
log = logging.getLogger("varsis.torrents")
POLL_SECONDS = 15
STALL_SECONDS = 600  # no progress for this long -> import what finished
_last_progress: dict[int, tuple[float, float]] = {}  # job id -> (progress, when it last changed)
AUDIO_CATEGORY = 3000  # Newznab/Torznab "Audio"


def _qbit() -> qbittorrentapi.Client:
    return qbittorrentapi.Client(
        host=settings.qbit_url,
        username=settings.qbit_user,
        password=settings.qbit_pass,
        REQUESTS_ARGS={"timeout": 15},
    )


def _tag(job_id: int) -> str:
    return f"varsis-{job_id}"


def job_out(j: TorrentJob):
    return {
        "id": j.id,
        "title": j.title,
        "status": j.status,
        "progress": j.progress,
        "message": j.message,
        "created_at": j.created_at,
    }


# ---------- search & add ----------


# Format words in release titles -> file extension Varsis can play. AAC lives in .m4a files.
FORMAT_PATTERNS = {
    "flac": r"\bflac\b",
    "wav": r"\bwav\b",
    "m4a": r"\b(alac|m4a|aac)\b",
    "mp3": r"\bmp3\b|\b320\s?kbps\b|\bv0\b",
    "ogg": r"\b(ogg|vorbis)\b",
    "opus": r"\bopus\b(?!\s*(no\.?\s*)?\d)",  # not classical "Opus 27"
}
UNSUPPORTED_PATTERN = r"\b(ape|wv|wavpack|dsd\d*|dsf|dff|sacd|aiff?|wma)\b"
MP3_CATEGORY = 3010


def detect_formats(title: str, categories: list[int]) -> tuple[list[str], bool]:
    """Supported formats named in a release title (or its category), and whether it names unsupported ones."""
    t = title.lower()
    found = [fmt for fmt, pattern in FORMAT_PATTERNS.items() if re.search(pattern, t)]
    if not found and MP3_CATEGORY in categories:
        found = ["mp3"]
    return found, bool(re.search(UNSUPPORTED_PATTERN, t))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


async def _prowlarr(c: httpx.AsyncClient, query: str) -> list[dict]:
    r = await c.get(
        f"{settings.prowlarr_url}/api/v1/search",
        params={"query": query, "categories": AUDIO_CATEGORY, "type": "search", "limit": 100},
        headers={"X-Api-Key": settings.prowlarr_api_key},
    )
    r.raise_for_status()
    return r.json()


@router.get("/search")
async def search(
    _: CurrentUser,
    q: str = "",
    artists: Annotated[list[str], Query()] = [],  # noqa: B006 (FastAPI copies defaults)
    formats: Annotated[list[str], Query()] = [],  # noqa: B006
):
    """Search Prowlarr. With artists: one search per artist, keeping releases that name one of them.
    With formats: drop releases whose title names only other formats (unknown format is kept)."""
    if not settings.prowlarr_api_key:
        raise HTTPException(503, "Prowlarr is not configured (PROWLARR_API_KEY)")
    artists = [a.strip() for a in artists if a.strip()]
    if not q.strip() and not artists:
        raise HTTPException(422, "Enter an artist or a title")
    queries = [f"{a} {q}".strip() for a in artists] or [q.strip()]
    try:
        # Some indexers are slow (archive.org throttles Prowlarr: 30-90 s per search).
        async with httpx.AsyncClient(timeout=180) as c:
            batches = await asyncio.gather(*(_prowlarr(c, query) for query in queries))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Prowlarr error: {e}")

    wanted = {f for f in formats if f in MIME}
    seen, results = set(), []
    for x in (x for batch in batches for x in batch):
        # Prefer the .torrent link: its file list can be checked before downloading (magnets can't).
        url = x.get("downloadUrl") or x.get("magnetUrl")
        if x.get("protocol") != "torrent" or not url or url in seen:
            continue
        seen.add(url)
        title = x.get("title", "")
        if artists and not any(_norm(a) in _norm(title) for a in artists):
            continue
        found, unsupported = detect_formats(title, [cat.get("id") for cat in x.get("categories") or []])
        if wanted and found and not wanted & set(found):
            continue
        if unsupported and not found:
            continue
        results.append(
            {
                "title": title,
                "size": x.get("size", 0),
                "seeders": x.get("seeders") or 0,
                "leechers": x.get("leechers") or 0,
                "indexer": x.get("indexer"),
                "formats": found,  # empty = not stated in the title
                "magnet_only": url.startswith("magnet:"),
                "url": url,
            }
        )
    return sorted(results, key=lambda x: x["seeders"], reverse=True)


class AddTorrent(BaseModel):
    title: str
    url: str  # magnet link or a Prowlarr download link from /search


async def _resolve(url: str) -> tuple[str | None, bytes | None]:
    """Turn a search result URL into (magnet, None) or (None, .torrent bytes)."""
    if url.startswith("magnet:"):
        return url, None
    # Only follow links that point at our Prowlarr, so users can't make the server fetch arbitrary URLs.
    if urlparse(url).netloc != urlparse(settings.prowlarr_url).netloc:
        raise HTTPException(400, "URL must be a magnet link or a Prowlarr download link")
    async with httpx.AsyncClient(timeout=60) as c:
        for _ in range(5):  # Prowlarr may redirect to a magnet link or to the indexer's .torrent
            r = await c.get(url)
            if not r.is_redirect:
                break
            url = r.headers["location"]
            if url.startswith("magnet:"):
                return url, None
        if r.status_code != 200:
            raise HTTPException(502, f"Could not fetch torrent (HTTP {r.status_code})")
        return None, r.content


def _bdecode(data: bytes, i: int = 0):
    """Minimal bencode decoder (enough to read a .torrent's file list). Returns (value, next index)."""
    c = data[i : i + 1]
    if c == b"i":
        end = data.index(b"e", i)
        return int(data[i + 1 : end]), end + 1
    if c in (b"l", b"d"):
        items, i = [], i + 1
        while data[i : i + 1] != b"e":
            value, i = _bdecode(data, i)
            items.append(value)
        return (dict(zip(items[::2], items[1::2])) if c == b"d" else items), i + 1
    colon = data.index(b":", i)
    n = int(data[i:colon])
    return data[colon + 1 : colon + 1 + n], colon + 1 + n


def torrent_files(torrent: bytes) -> list[str]:
    """File paths inside a .torrent, in qBittorrent's file order."""
    try:
        info = _bdecode(torrent)[0][b"info"]
        if b"files" not in info:  # single-file torrent
            return [info[b"name"].decode(errors="replace")]
        return ["/".join(part.decode(errors="replace") for part in f[b"path"]) for f in info[b"files"]]
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, "Could not read the .torrent file")


def info_hash(torrent: bytes) -> str:
    """qBittorrent's id for a .torrent: SHA-1 of the raw bencoded `info` dict."""
    i = 1
    while torrent[i : i + 1] != b"e":
        key, i = _bdecode(torrent, i)
        start = i
        _, i = _bdecode(torrent, i)
        if key == b"info":
            return hashlib.sha1(torrent[start:i]).hexdigest()
    raise HTTPException(502, "Could not read the .torrent file")


def _qbit_add(magnet: str | None, torrent: bytes | None, job_id: int, skip: list[int]):
    """Add to qBittorrent. Files listed in `skip` (indexes) get priority 0 = not downloaded.
    qBittorrent rejects file priorities on upload, so add stopped, set them, then start."""
    q = _qbit()
    result = q.torrents_add(
        urls=magnet,
        torrent_files=torrent,
        save_path=f"{settings.downloads_dir}/{job_id}",
        tags=_tag(job_id),
        category="varsis",
        is_stopped=bool(skip),
    )
    if result == "Fails.":  # older API returns "Ok."/"Fails.", v2.14+ returns JSON metadata
        raise HTTPException(502, "qBittorrent refused the torrent")
    if not skip:
        return
    h = info_hash(torrent)
    for _ in range(20):  # the torrent can take a moment to appear
        try:
            q.torrents_file_priority(torrent_hash=h, file_ids=skip, priority=0)
            break
        except (qbittorrentapi.NotFound404Error, qbittorrentapi.Conflict409Error):
            time.sleep(0.5)
    q.torrents_start(torrent_hashes=h)


def _supported(path: str) -> bool:
    return Path(path).suffix.lower().lstrip(".") in MIME


QUALITY = ["flac", "wav", "m4a", "mp3", "ogg", "opus"]  # best first
LOW_QUALITY_COPY = re.compile(r"_(64kb|vbr|128kb|256kb|320kb)$", re.IGNORECASE)  # archive.org derivatives


def song_key(path: str) -> tuple[str, str]:
    """Files with the same key are versions of the same song (e.g. Song.flac, Song.mp3, Song_64kb.mp3)."""
    p = Path(path)
    return str(p.parent).lower(), LOW_QUALITY_COPY.sub("", p.stem).lower()


def best_versions(paths: list[str]) -> list[int]:
    """Indexes of the files to keep: per song (same folder + name) the best supported format,
    ignoring archive.org's re-encoded copies when an original exists."""
    best = {}  # (folder, name) -> (rank, index)
    for i, path in enumerate(paths):
        p = Path(path)
        ext = p.suffix.lower().lstrip(".")
        if ext not in MIME:
            continue
        rank = QUALITY.index(ext) + (len(QUALITY) if LOW_QUALITY_COPY.search(p.stem) else 0)
        key = song_key(path)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, i)
    return sorted(i for _, i in best.values())


@router.post("", status_code=201)
async def add(data: AddTorrent, db: SessionDep, user: CurrentUser):
    magnet, torrent = await _resolve(data.url)
    skip = []
    if torrent:  # check the contents; download only supported audio files
        files = torrent_files(torrent)
        keep = best_versions(files)
        skip = [i for i in range(len(files)) if i not in keep]
        if not keep:
            exts = sorted({Path(f).suffix.lower() or "(none)" for f in files})[:8]
            raise HTTPException(400, f"No supported audio files in this torrent (contains: {', '.join(exts)})")
    job = TorrentJob(user_id=user.id, title=data.title)
    db.add(job)
    await db.flush()
    try:
        await asyncio.to_thread(_qbit_add, magnet, torrent, job.id, skip)
    except qbittorrentapi.APIError as e:
        raise HTTPException(502, f"qBittorrent error: {e}")
    if skip:
        job.message = f"Downloading {len(files) - len(skip)} of {len(files)} files (best version of each song)"
    await db.commit()
    return job_out(job)


@router.get("")
async def jobs(db: SessionDep, user: CurrentUser):
    rows = await db.scalars(
        select(TorrentJob).where(TorrentJob.user_id == user.id).order_by(TorrentJob.id.desc()).limit(100)
    )
    return [job_out(j) for j in rows]


# ---------- poller ----------


async def _import_job(db, job: TorrentJob, qbit: qbittorrentapi.Client, torrent_hash: str, stalled=False):
    """Import the finished audio files of a job (best version of each song), then remove the torrent.
    `stalled`: the torrent stopped progressing, so import what finished and report the rest."""
    job_id, user_id = job.id, job.user_id  # rollback() expires ORM objects; keep plain values
    folder = Path(settings.downloads_dir) / str(job_id)
    files = await asyncio.to_thread(qbit.torrents_files, torrent_hash=torrent_hash)
    done = [f.name for f in files if f.priority and f.progress >= 1]
    got = {song_key(name) for name in done if _supported(name)}
    missing = len({song_key(f.name) for f in files if f.priority and _supported(f.name)} - got)  # songs, not files
    imported, skipped = 0, []
    for f in (folder / done[i] for i in best_versions(done)):
        try:
            await import_file(db, f, f.name, user_id)
            imported += 1
        except (ValueError, OSError, mutagen.MutagenError) as e:
            await db.rollback()
            skipped.append(f"{f.name}: {e}")
    await asyncio.to_thread(qbit.torrents_delete, delete_files=True, torrent_hashes=torrent_hash)
    shutil.rmtree(folder, ignore_errors=True)
    job = await db.get(TorrentJob, job_id)
    job.status = "done" if imported else "failed"
    job.message = f"Imported {imported} track(s)" + (f"; skipped: {'; '.join(skipped)}" if skipped else "")
    if stalled and missing:
        job.message += f"; {missing} song(s) couldn't be downloaded (no source had them)"
    if not imported and not skipped:
        job.message = "No supported audio files (flac, wav, m4a, mp3, ogg, opus) in this torrent"


async def _stalled_with_files(qbit: qbittorrentapi.Client, job_id: int, t) -> bool:
    """True when the torrent hasn't progressed for STALL_SECONDS and some wanted audio file is complete."""
    last = _last_progress.get(job_id)
    if last is None or t.progress > last[0]:
        _last_progress[job_id] = (t.progress, time.monotonic())
        return False
    if time.monotonic() - last[1] < STALL_SECONDS:
        return False
    files = await asyncio.to_thread(qbit.torrents_files, torrent_hash=t.hash)
    return any(f.priority and f.progress >= 1 and _supported(f.name) for f in files)


async def poll_once():
    async with SessionLocal() as db:
        ids = list(await db.scalars(select(TorrentJob.id).where(TorrentJob.status == "downloading")))
        if not ids:
            return
        qbit = _qbit()
        torrents = await asyncio.to_thread(qbit.torrents_info, category="varsis")
        by_tag = {t.tags: t for t in torrents}
        for job_id in ids:
            job = await db.get(TorrentJob, job_id)
            t = by_tag.get(_tag(job_id))
            if t is None:
                job.status, job.message = "failed", "Torrent disappeared from qBittorrent"
            elif t.state in ("error", "missingFiles"):
                job.status, job.message = "failed", f"qBittorrent state: {t.state}"
            elif t.progress >= 1 or await _stalled_with_files(qbit, job_id, t):
                stalled = t.progress < 1
                job.status, job.progress = "importing", t.progress
                await db.commit()
                await _import_job(db, job, qbit, t.hash, stalled)
                _last_progress.pop(job_id, None)
            else:
                job.progress = t.progress
            await db.commit()


async def poll_forever():
    while True:
        try:
            await poll_once()
        except Exception:  # keep polling even if qBittorrent/DB hiccups
            log.exception("torrent poll failed")
        await asyncio.sleep(POLL_SECONDS)
