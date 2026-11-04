"""Playlist CRUD and reordering. Playlists are private to their owner."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from .auth import CurrentUser
from .db import SessionDep
from .library import get_track, track_out
from .models import Playlist, PlaylistTrack, User

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TrackRef(BaseModel):
    track_id: int


class Order(BaseModel):
    entry_ids: list[int]


async def _own(db, playlist_id: int, user: User) -> Playlist:
    pl = await db.get(Playlist, playlist_id)
    if not pl or pl.owner_id != user.id:
        raise HTTPException(404, "Playlist not found")
    return pl


async def _entries(db, playlist_id: int) -> list[PlaylistTrack]:
    rows = await db.scalars(
        select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id).order_by(PlaylistTrack.position)
    )
    return list(rows)


async def _out(db, pl: Playlist):
    entries = await _entries(db, pl.id)
    return {"id": pl.id, "name": pl.name, "tracks": [{**track_out(e.track), "entry_id": e.id} for e in entries]}


@router.get("")
async def list_playlists(db: SessionDep, user: CurrentUser):
    count = func.count(PlaylistTrack.id)
    rows = await db.execute(
        select(Playlist, count)
        .outerjoin(PlaylistTrack)
        .where(Playlist.owner_id == user.id)
        .group_by(Playlist.id)
        .order_by(Playlist.name)
    )
    return [{"id": pl.id, "name": pl.name, "count": n} for pl, n in rows]


@router.post("", status_code=201)
async def create(data: Name, db: SessionDep, user: CurrentUser):
    pl = Playlist(name=data.name.strip(), owner_id=user.id)
    db.add(pl)
    await db.commit()
    return {"id": pl.id, "name": pl.name, "tracks": []}


@router.get("/{playlist_id}")
async def get(playlist_id: int, db: SessionDep, user: CurrentUser):
    return await _out(db, await _own(db, playlist_id, user))


@router.patch("/{playlist_id}")
async def rename(playlist_id: int, data: Name, db: SessionDep, user: CurrentUser):
    pl = await _own(db, playlist_id, user)
    pl.name = data.name.strip()
    await db.commit()
    return {"id": pl.id, "name": pl.name}


@router.delete("/{playlist_id}", status_code=204)
async def remove(playlist_id: int, db: SessionDep, user: CurrentUser):
    await db.delete(await _own(db, playlist_id, user))
    await db.commit()


@router.post("/{playlist_id}/tracks", status_code=201)
async def add_track(playlist_id: int, data: TrackRef, db: SessionDep, user: CurrentUser):
    pl = await _own(db, playlist_id, user)
    await get_track(db, data.track_id)
    last = await db.scalar(select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == pl.id))
    db.add(PlaylistTrack(playlist_id=pl.id, track_id=data.track_id, position=(last or 0) + 1))
    await db.commit()
    return {"detail": "Added"}


@router.delete("/{playlist_id}/tracks/{entry_id}")
async def remove_track(playlist_id: int, entry_id: int, db: SessionDep, user: CurrentUser):
    pl = await _own(db, playlist_id, user)
    await db.execute(delete(PlaylistTrack).where(PlaylistTrack.id == entry_id, PlaylistTrack.playlist_id == pl.id))
    await db.commit()
    return await _out(db, pl)


@router.put("/{playlist_id}/order")
async def reorder(playlist_id: int, data: Order, db: SessionDep, user: CurrentUser):
    pl = await _own(db, playlist_id, user)
    entries = {e.id: e for e in await _entries(db, pl.id)}
    if sorted(data.entry_ids) != sorted(entries):
        raise HTTPException(400, "entry_ids must list every entry of the playlist exactly once")
    for pos, entry_id in enumerate(data.entry_ids, 1):
        entries[entry_id].position = pos
    await db.commit()
    return await _out(db, pl)
