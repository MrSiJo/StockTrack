"""Login (signs the session cookie), logout (ends every session) and who am I."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.api.auth_middleware import SESSION_COOKIE_NAME, make_serializer
from stocktrack.api.deps import get_session
from stocktrack.api.login_throttle import login_throttle
from stocktrack.api.rate_limit import limiter
from stocktrack.bootstrap import get_settings
from stocktrack.models import User
from stocktrack.models.user import new_session_nonce
from stocktrack.services.auth_service import authenticate

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)


class UserOut(BaseModel):
    user_id: int
    username: str


@router.post("/login", response_model=UserOut)
@limiter.limit("5/minute")
async def login(
    request: Request,  # noqa: ARG001 (required by slowapi)
    response: Response,
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()

    # Per username lockout: defends against distributed / rotating IP brute
    # force that the per IP slowapi limit above can't see.
    locked_for = login_throttle.seconds_until_unlocked(body.username)
    if locked_for:
        raise HTTPException(
            status_code=429,
            detail="too many failed login attempts; try again later",
            headers={"Retry-After": str(locked_for)},
        )

    # Count the attempt as a failure BEFORE the (threaded, slow) argon2
    # check and clear it on success. Recording only after authenticate let
    # parallel attempts all pass the lock check above before any of them
    # was counted. No await between the check and this line.
    login_throttle.record_failure(body.username)
    user = await authenticate(session, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials")

    login_throttle.reset(body.username)
    token = make_serializer(settings.app_secret_key).dumps(
        {"user_id": user.id, "nonce": user.session_nonce})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.session_max_age_seconds,
        path="/",
    )
    return UserOut(user_id=user.id, username=user.username)


@router.post("/logout")
async def logout(request: Request, response: Response,
                 session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    """Rotate the user's session nonce, so every cookie issued so far (this
    browser's and any other's) stops working, then clear this browser's."""
    settings = get_settings()
    user_id = getattr(request.state, "user_id", None)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is not None:
        user.session_nonce = new_session_nonce()
        await session.commit()
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", httponly=True,
                           samesite="strict", secure=settings.cookie_secure)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(request: Request, session: AsyncSession = Depends(get_session)):
    user_id = getattr(request.state, "user_id", None)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return UserOut(user_id=user.id, username=user.username)
