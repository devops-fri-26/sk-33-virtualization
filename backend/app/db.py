"""Async SQLAlchemy engine, declarative Base and the per-request session dependency."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(settings.database_url)
# expire_on_commit=False: objects stay readable after a commit. Otherwise the next attribute access would reload
# them from the database, which an async session can't do behind the scenes.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class of every ORM model. Its `metadata` knows all tables, which is what creates them at startup."""


async def get_session():
    """FastAPI dependency: a database session for one request.

    Yields:
        The session. It is closed when the request is done, and nothing is committed unless the route does it.
    """
    async with SessionLocal() as session:
        yield session


# Route parameter type: `db: SessionDep` gets the request's session from get_session().
SessionDep = Annotated[AsyncSession, Depends(get_session)]
