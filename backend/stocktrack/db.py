from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from stocktrack.models.base import Base

def make_engine(database_url: str):
    return create_async_engine(database_url, echo=False)

def make_sessionmaker(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

async def init_models(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
