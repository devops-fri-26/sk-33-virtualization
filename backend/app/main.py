"""FastAPI entry point: app, lifespan (DB setup, admins, torrent poller) and routers."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text, update

from . import account, admin, auth, library, playlists, torrents
from .config import settings
from .db import Base, engine
from .models import STARTUP_SQL, User


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set the app up before it takes requests, and clean up when it stops.

    Before: create the storage folders and the database tables, run STARTUP_SQL, put imports that a restart
    interrupted back in the queue, give ADMIN_EMAILS their rights and start the torrent poller. After: stop the
    poller and close the database connections.

    Args:
        app: The app being started (FastAPI passes it; not used).

    Yields:
        Nothing. The app serves requests between the two halves.
    """
    for d in (settings.music_dir, settings.covers_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in STARTUP_SQL:
            await conn.execute(text(sql))
        # A restart in the middle of an import left these behind; the poller finishes them (see _import_job).
        await conn.execute(text("UPDATE torrent_jobs SET status = 'downloading' WHERE status = 'importing'"))
        if settings.admins:  # they still need a verified email to log in
            await conn.execute(
                update(User)
                .where(User.email.in_(settings.admins))
                .values(is_admin=True, is_approved=True, is_disabled=False)
            )
    poller = asyncio.create_task(torrents.poll_forever())
    yield
    poller.cancel()
    await engine.dispose()


app = FastAPI(title="Varsis", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(admin.router)
app.include_router(library.router)
app.include_router(playlists.router)
app.include_router(torrents.router)


@app.get("/api/health")
async def health():
    """Tell a monitor that the backend process is up. Needs no login and doesn't touch the database.

    Returns:
        Always `{"ok": true}`.
    """
    return {"ok": True}
