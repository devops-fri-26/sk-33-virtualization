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
    """The name for a new or renamed playlist."""

    name: str = Field(min_length=1, max_length=200, pattern=r"\S")  # not only spaces


class TrackRef(BaseModel):
    """The track to add to a playlist."""

    track_id: int


class Order(BaseModel):
    """A playlist's entries in their new order. These are entry ids, not track ids."""

    entry_ids: list[int]


async def _own(db, playlist_id: int, user: User) -> Playlist:
    """Load a playlist that must belong to the user.

    Args:
        db: Database session.
        playlist_id: The playlist.
        user: The logged-in user.

    Returns:
        The playlist.

    Raises:
        HTTPException: 404 when it doesn't exist or is someone else's. The answer is the same for both, so
            nobody learns which ids exist.
    """
    pl = await db.get(Playlist, playlist_id)
    if not pl or pl.owner_id != user.id:
        raise HTTPException(404, "Playlist not found")
    return pl


async def _entries(db, playlist_id: int) -> list[PlaylistTrack]:
    """Load a playlist's entries in playing order.

    Args:
        db: Database session.
        playlist_id: The playlist.

    Returns:
        Its entries, each with its track loaded.
    """
    rows = await db.scalars(
        select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id).order_by(PlaylistTrack.position)
    )
    return list(rows)


async def _out(db, pl: Playlist):
    """Describe a playlist with its tracks, the way the frontend gets it.

    Args:
        db: Database session.
        pl: The playlist.

    Returns:
        Its id, name and tracks in order. Each track also has `entry_id`, which is what removing and reordering
        work with (a track can be in the playlist twice).
    """
    entries = await _entries(db, pl.id)
    return {"id": pl.id, "name": pl.name, "tracks": [{**track_out(e.track), "entry_id": e.id} for e in entries]}


@router.get("")
async def list_playlists(db: SessionDep, user: CurrentUser):
    """List the user's playlists by name.

    Args:
        db: Database session.
        user: The logged-in user.

    Returns:
        Each playlist's id, name and `count`, its number of entries.
    """
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
    """Create an empty playlist.

    Args:
        data: Its name.
        db: Database session.
        user: The logged-in user, who becomes the owner.

    Returns:
        The new playlist: its id, name and an empty track list.
    """
    pl = Playlist(name=data.name.strip(), owner_id=user.id)
    db.add(pl)
    await db.commit()
    return {"id": pl.id, "name": pl.name, "tracks": []}


@router.get("/{playlist_id}")
async def get(playlist_id: int, db: SessionDep, user: CurrentUser):
    """Get one playlist with its tracks.

    Args:
        playlist_id: The playlist.
        db: Database session.
        user: The logged-in user.

    Returns:
        The playlist (see _out()).

    Raises:
        HTTPException: 404 when it doesn't exist or isn't the user's.
    """
    return await _out(db, await _own(db, playlist_id, user))


@router.patch("/{playlist_id}")
async def rename(playlist_id: int, data: Name, db: SessionDep, user: CurrentUser):
    """Rename a playlist.

    Args:
        playlist_id: The playlist.
        data: The new name.
        db: Database session.
        user: The logged-in user.

    Returns:
        The playlist's id and new name.

    Raises:
        HTTPException: 404 when it doesn't exist or isn't the user's.
    """
    pl = await _own(db, playlist_id, user)
    pl.name = data.name.strip()
    await db.commit()
    return {"id": pl.id, "name": pl.name}


@router.delete("/{playlist_id}", status_code=204)
async def remove(playlist_id: int, db: SessionDep, user: CurrentUser):
    """Delete a playlist. The tracks in it stay in the library.

    Args:
        playlist_id: The playlist.
        db: Database session.
        user: The logged-in user.

    Raises:
        HTTPException: 404 when it doesn't exist or isn't the user's.
    """
    await db.delete(await _own(db, playlist_id, user))
    await db.commit()


@router.post("/{playlist_id}/tracks", status_code=201)
async def add_track(playlist_id: int, data: TrackRef, db: SessionDep, user: CurrentUser):
    """Add a track to the end of a playlist. Adding the same track again makes a second entry.

    Args:
        playlist_id: The playlist.
        data: The track to add.
        db: Database session.
        user: The logged-in user.

    Returns:
        A confirmation message.

    Raises:
        HTTPException: 404 when the playlist doesn't exist or isn't the user's, or the track doesn't exist.
    """
    pl = await _own(db, playlist_id, user)
    await get_track(db, data.track_id)
    last = await db.scalar(select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == pl.id))
    db.add(PlaylistTrack(playlist_id=pl.id, track_id=data.track_id, position=(last or 0) + 1))
    await db.commit()
    return {"detail": "Added"}


@router.delete("/{playlist_id}/tracks/{entry_id}")
async def remove_track(playlist_id: int, entry_id: int, db: SessionDep, user: CurrentUser):
    """Take one entry out of a playlist.

    Args:
        playlist_id: The playlist.
        entry_id: The entry to remove (`entry_id` of a track in the playlist, not the track's id).
        db: Database session.
        user: The logged-in user.

    Returns:
        The playlist as it is now (see _out()).

    Raises:
        HTTPException: 404 when the playlist doesn't exist or isn't the user's.
    """
    pl = await _own(db, playlist_id, user)
    # The playlist_id condition keeps an entry id from someone else's playlist from being deleted.
    await db.execute(delete(PlaylistTrack).where(PlaylistTrack.id == entry_id, PlaylistTrack.playlist_id == pl.id))
    await db.commit()
    return await _out(db, pl)


@router.put("/{playlist_id}/order")
async def reorder(playlist_id: int, data: Order, db: SessionDep, user: CurrentUser):
    """Put a playlist's entries in a new order.

    Args:
        playlist_id: The playlist.
        data: All of its entry ids, in the order they should play.
        db: Database session.
        user: The logged-in user.

    Returns:
        The playlist in its new order (see _out()).

    Raises:
        HTTPException: 404 when the playlist doesn't exist or isn't the user's. 400 when the list leaves out
            an entry, repeats one or names one that isn't in the playlist.
    """
    pl = await _own(db, playlist_id, user)
    entries = {e.id: e for e in await _entries(db, pl.id)}
    if sorted(data.entry_ids) != sorted(entries):
        raise HTTPException(400, "entry_ids must list every entry of the playlist exactly once")
    for pos, entry_id in enumerate(data.entry_ids, 1):
        entries[entry_id].position = pos
    await db.commit()
    return await _out(db, pl)
