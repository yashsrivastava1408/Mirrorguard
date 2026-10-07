"""One place that owns the database connection."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mirrorguard.db.models import Base


class Database:
    """Works with SQLite for local use and PostgreSQL in production, from the URL alone."""

    def __init__(self, url: str):
        if url.startswith("sqlite"):
            # Wait for the write lock instead of failing when several jobs save at once.
            options = {"connect_args": {"timeout": 30}}
        else:
            options = {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}
        self.engine = create_async_engine(url, **options)
        self.session: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    async def create_tables(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()
