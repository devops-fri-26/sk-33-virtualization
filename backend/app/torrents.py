"""Prowlarr search, qBittorrent download jobs, and the poller that imports finished downloads."""

import asyncio
import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse

import httpx
import mutagen
import qbittorrentapi
from fastapi import APIRouter, HTTPException
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


@router.get("/search")
async def search(q: str, _: CurrentUser):
    if not settings.prowlarr_api_key:
        raise HTTPException(503, "Prowlarr is not configured (PROWLARR_API_KEY)")
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                f"{settings.prowlarr_url}/api/v1/search",
                params={"query": q, "categories": AUDIO_CATEGORY, "type": "search", "limit": 100},
                headers={"X-Api-Key": settings.prowlarr_api_key},
            )
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Prowlarr error: {e}")
    results = [
        {
            "title": x["title"],
            "size": x.get("size", 0),
            "seeders": x.get("seeders") or 0,
            "leechers": x.get("leechers") or 0,
            "indexer": x.get("indexer"),
            "url": x.get("magnetUrl") or x.get("downloadUrl"),
        }
        for x in r.json()
        if x.get("protocol") == "torrent" and (x.get("magnetUrl") or x.get("downloadUrl"))
    ]
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


@router.post("", status_code=201)
async def add(data: AddTorrent, db: SessionDep, user: CurrentUser):
    magnet, torrent = await _resolve(data.url)
    job = TorrentJob(user_id=user.id, title=data.title)
    db.add(job)
    await db.flush()
    try:
        result = await asyncio.to_thread(
            _qbit().torrents_add,
            urls=magnet,
            torrent_files=torrent,
            save_path=f"{settings.downloads_dir}/{job.id}",
            tags=_tag(job.id),
            category="varsis",
        )
    except qbittorrentapi.APIError as e:
        raise HTTPException(502, f"qBittorrent error: {e}")
    if result == "Fails.":  # older API returns "Ok."/"Fails.", v2.14+ returns JSON metadata
        raise HTTPException(502, "qBittorrent refused the torrent")
    await db.commit()
    return job_out(job)


@router.get("")
async def jobs(db: SessionDep, user: CurrentUser):
    rows = await db.scalars(
        select(TorrentJob).where(TorrentJob.user_id == user.id).order_by(TorrentJob.id.desc()).limit(100)
    )
    return [job_out(j) for j in rows]


# ---------- poller ----------


async def _import_job(db, job: TorrentJob, qbit: qbittorrentapi.Client, torrent_hash: str):
    """Import every supported audio file of a finished job, then remove the torrent and its leftovers."""
    job_id, user_id = job.id, job.user_id  # rollback() expires ORM objects; keep plain values
    folder = Path(settings.downloads_dir) / str(job_id)
    imported, skipped = 0, []
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        if f.suffix.lower().lstrip(".") not in MIME:
            continue
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
    if not imported and not skipped:
        job.message = "No supported audio files (flac, wav, m4a, mp3, ogg, opus) in this torrent"


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
            elif t.progress >= 1:
                job.status, job.progress = "importing", 1
                await db.commit()
                await _import_job(db, job, qbit, t.hash)
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
