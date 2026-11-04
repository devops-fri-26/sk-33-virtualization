"""FastAPI entry point: app, lifespan (DB setup, torrent poller) and routers."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from . import auth, library, playlists, torrents
from .config import settings
from .db import Base, engine
from .models import SEARCH_SQL


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in (settings.music_dir, settings.covers_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in SEARCH_SQL:
            await conn.execute(text(sql))
    poller = asyncio.create_task(torrents.poll_forever())
    yield
    poller.cancel()
    await engine.dispose()


app = FastAPI(title="Varsis", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(playlists.router)
app.include_router(torrents.router)


@app.get("/api/health")
async def health():
    return {"ok": True}
