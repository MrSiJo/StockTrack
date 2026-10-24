"""Single user bootstrap and credential verification.

``bootstrap_user`` is one shot: it refuses when a ``user`` row exists, and the
``singleton`` unique column means two concurrent calls cannot both insert
(the loser hits the constraint and gets SetupAlreadyComplete too).
"""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.models import User
from stocktrack.passwords import hash_password, verify_password

MIN_PASSWORD_LENGTH = 12

_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    """Lazily built argon2 hash, so unknown user logins cost the same as real ones."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("stocktrack-timing-equaliser-not-a-credential")
    return _DUMMY_HASH


def warm_dummy_hash() -> None:
    """Build the dummy hash now (called at startup) so no login pays for it."""
    _dummy_hash()


class SetupAlreadyComplete(RuntimeError):
    """Raised by bootstrap_user when a user already exists."""


class WeakPasswordError(ValueError):
    """Raised when the supplied password is too short."""


async def _user_exists(session: AsyncSession) -> bool:
    result = await session.execute(select(func.count()).select_from(User))
    return (result.scalar_one() or 0) > 0


async def bootstrap_user(session: AsyncSession, username: str, password: str) -> User:
    """Create the single application user. Race safe."""
    if not username or not username.strip():
        raise ValueError("username is required")
    if password is None or len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    if await _user_exists(session):
        raise SetupAlreadyComplete("a user already exists")

    user = User(username=username.strip(), password_hash=hash_password(password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Lost the race with a concurrent bootstrap_user call.
        await session.rollback()
        raise SetupAlreadyComplete("a user already exists") from exc
    return user


async def find_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    """Return the user if username and password match, else None."""
    if not username or not password:
        return None
    user = await find_user_by_username(session, username)
    if user is None:
        # Burn the same argon2 time as a real check so response time does not
        # reveal whether the username exists.
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
