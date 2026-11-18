"""ORM models: User, Artist, Album, Track (+ track_artists), Playlist, PlaylistTrack."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import settings
from .db import Base

GB = 1024**3
DEFAULT_QUOTA = int(settings.default_quota_gb * GB)  # bytes

# Which artists a track has (many-to-many). A row disappears with its track or its artist.
track_artists = Table(
    "track_artists",
    Base.metadata,
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("artist_id", ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    """An account. It can log in once it is verified and approved, and as long as it isn't disabled."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str]
    name: Mapped[str | None] = mapped_column(String(100))  # display name, optional
    is_verified: Mapped[bool] = mapped_column(default=False)  # opened the email link
    is_approved: Mapped[bool] = mapped_column(default=False)  # an admin let them in
    is_disabled: Mapped[bool] = mapped_column(default=False)  # an admin blocked them
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Upload limit in bytes, None = no limit.
    quota: Mapped[int | None] = mapped_column(BigInteger, default=DEFAULT_QUOTA)
    storage_requested: Mapped[bool] = mapped_column(default=False)  # asked an admin for more space
    session_version: Mapped[int] = mapped_column(default=0)  # part of every session cookie; +1 logs out everywhere
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artist(Base):
    """A performer, shared by every track and album that names it. Removed when nothing names it any more."""

    __tablename__ = "artists"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class Album(Base):
    """An album. Imports treat title + album artist as its identity; it is removed with its last track."""

    __tablename__ = "albums"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id"))
    year: Mapped[int | None]
    cover: Mapped[str | None]  # filename inside covers_dir
    artist: Mapped[Artist | None] = relationship(lazy="selectin")


class Track(Base):
    """One audio file in the library, with what its tags said when it was imported."""

    __tablename__ = "tracks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    album_id: Mapped[int | None] = mapped_column(ForeignKey("albums.id"))
    cover: Mapped[str | None]  # own picture in covers_dir, for tracks without an album
    track_no: Mapped[int | None]
    duration: Mapped[float] = mapped_column(default=0)  # seconds
    format: Mapped[str]  # file extension, e.g. "flac"
    mime: Mapped[str]  # Content-Type the file is served with
    path: Mapped[str] = mapped_column(unique=True)  # where the file is, inside music_dir
    size: Mapped[int]  # bytes; counts against the uploader's quota
    # SHA-256 of the file, which is how an import notices a file that is already here. None for tracks from before
    # this existed; it is filled in the first time a file of the same size is imported.
    content_hash: Mapped[str | None] = mapped_column(String(64))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # None once that account is deleted
    needs_artists: Mapped[bool] = mapped_column(default=False)  # no artist in its tags: the uploader is asked
    album: Mapped[Album | None] = relationship(lazy="selectin")
    artists: Mapped[list[Artist]] = relationship(secondary=track_artists, lazy="selectin")


class Playlist(Base):
    """A list of tracks that only its owner can see. Its entries are PlaylistTrack rows."""

    __tablename__ = "playlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlaylistTrack(Base):
    """One entry in a playlist (own id, so the same track can appear twice)."""

    __tablename__ = "playlist_tracks"
    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    position: Mapped[int]  # order inside the playlist, starting at 1
    track: Mapped[Track] = relationship(lazy="selectin")


# Run at startup after create_all: columns added after release (create_all doesn't add columns to existing
# tables) and trigram indexes for fuzzy search.
STARTUP_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100)",
    # Accounts from before admin approval existed start unapproved; ADMIN_EMAILS are approved at startup.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_disabled BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false",
    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS quota BIGINT DEFAULT {DEFAULT_QUOTA}",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS storage_requested BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tracks ADD COLUMN IF NOT EXISTS cover VARCHAR",
    "ALTER TABLE tracks ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS tracks_title_trgm ON tracks USING gin (title gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS artists_name_trgm ON artists USING gin (name gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS albums_title_trgm ON albums USING gin (title gin_trgm_ops)",
]
