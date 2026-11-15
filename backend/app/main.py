"""FastAPI entry point: app, lifespan (DB setup, admins, plugins) and routers."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from sqlalchemy import text, update

from . import account, admin, auth, library, playlists, plugins
from .auth import current_user
from .config import settings
from .db import Base, engine
from .models import STARTUP_SQL, User

plugins.load()  # before the lifespan runs: plugins add their tables, routes and hooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set the app up before it takes requests, and clean up when it stops.

    Before: create the storage folders and the database tables, run STARTUP_SQL (the app's, then each plugin's),
    give ADMIN_EMAILS their rights and start the plugins. After: stop the plugins and close the database
    connections.

    Args:
        app: The app being started (FastAPI passes it; not used).

    Yields:
        Nothing. The app serves requests between the two halves.
    """
    for d in (settings.music_dir, settings.covers_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in [*STARTUP_SQL, *(sql for sqls in plugins.each("STARTUP_SQL") for sql in sqls)]:
            await conn.execute(text(sql))
        if settings.admins:  # they still need a verified email to log in
            await conn.execute(
                update(User)
                .where(User.email.in_(settings.admins))
                .values(is_admin=True, is_approved=True, is_disabled=False)
            )
    for startup in plugins.each("startup"):
        await startup()
    yield
    for shutdown in plugins.each("shutdown"):
        await shutdown()
    await engine.dispose()


app = FastAPI(title="Varsis", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(admin.router)
app.include_router(library.router)
app.include_router(playlists.router)
for router in plugins.each("router"):  # login required, whether or not the plugin's routes ask for it themselves
    app.include_router(router, dependencies=[Depends(current_user)])
for router in plugins.each("public_router"):
    app.include_router(router)


@app.get("/api/health")
async def health():
    """Tell a monitor that the backend process is up. Needs no login and doesn't touch the database.

    Returns:
        Always `{"ok": true}`.
    """
    return {"ok": True}
