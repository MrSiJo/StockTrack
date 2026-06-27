from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession from the app-level sessionmaker."""
    sm = request.app.state.sessionmaker
    async with sm() as session:
        yield session
