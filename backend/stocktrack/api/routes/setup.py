"""One-shot first user setup. Unauthenticated (auth exempt), CSRF protected.

Refuses with 409 once any user exists. Does not log in: the SPA calls
/api/auth/login afterwards. Rate limited per client IP to slow scanning of an
instance that has not been set up yet.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.auth_middleware import user_exists_cache
from stocktrack.api.deps import get_session
from stocktrack.api.rate_limit import limiter
from stocktrack.models import User
from stocktrack.services.auth_service import (
    SetupAlreadyComplete,
    WeakPasswordError,
    bootstrap_user,
)

router = APIRouter()


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)


class SetupResponse(BaseModel):
    user_id: int
    username: str


class SetupStatusResponse(BaseModel):
    setup_needed: bool


@router.get("/setup", response_model=SetupStatusResponse)
async def setup_status(session: AsyncSession = Depends(get_session)):
    """True iff the ``user`` table is empty; the SPA routes to Setup or Login."""
    count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    return SetupStatusResponse(setup_needed=(count or 0) == 0)


@router.post("/setup", response_model=SetupResponse,
             status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def setup(
    request: Request,  # noqa: ARG001 (required by slowapi)
    response: Response,  # noqa: ARG001 (slowapi injects rate limit headers)
    body: SetupRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        user = await bootstrap_user(session, body.username, body.password)
    except SetupAlreadyComplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (WeakPasswordError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # A new user means any cached session from a deleted one is stale now.
    user_exists_cache.clear()
    return SetupResponse(user_id=user.id, username=user.username)
