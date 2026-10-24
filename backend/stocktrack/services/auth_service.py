"""Single user bootstrap and credential verification.

``bootstrap_user`` is one shot: it refuses when a ``user`` row exists, and the
``singleton`` unique column means two concurrent calls cannot both insert
(the loser hits the constraint and gets SetupAlreadyComplete too).

argon2 is deliberately slow and memory hard, so every hash and verify runs in
a worker thread (on the event loop it would stall every other request), and
at most ARGON2_CONCURRENCY run at once (each takes 64 MiB; a burst of logins
queues instead of stacking memory).
"""
import asyncio

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.models import User
from stocktrack.passwords import hash_password, verify_password

MIN_PASSWORD_LENGTH = 12
ARGON2_CONCURRENCY = 2

# Module level cap on concurrent argon2 work. The app runs one event loop;
# the semaphore is rebuilt only if a different loop shows up (a fresh loop
# per test under pytest), since an asyncio.Semaphore binds to one loop.
_argon2_slots: asyncio.Semaphore | None = None
_argon2_slots_loop: asyncio.AbstractEventLoop | None = None


def _slots() -> asyncio.Semaphore:
    global _argon2_slots, _argon2_slots_loop
    loop = asyncio.get_running_loop()
    if _argon2_slots is None or _argon2_slots_loop is not loop:
        _argon2_slots = asyncio.Semaphore(ARGON2_CONCURRENCY)
        _argon2_slots_loop = loop
    return _argon2_slots


async def _argon2(func, *args):
    """Run one argon2 call in a worker thread, at most ARGON2_CONCURRENCY at once."""
    async with _slots():
        return await asyncio.to_thread(func, *args)

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

    password_hash = await _argon2(hash_password, password)
    user = User(username=username.strip(), password_hash=password_hash)
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
        await _argon2(lambda: verify_password(password, _dummy_hash()))
        return None
    if not await _argon2(verify_password, password, user.password_hash):
        return None
    return user
