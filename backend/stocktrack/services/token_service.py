"""API tokens for machine clients: create, list, revoke, verify.

A token is ``st_`` + 32 random bytes (base64url); the prefix lets secret
scanners and people recognise one. Only ``sha256(token).hexdigest()`` is
stored. Plain SHA-256 (not argon2) is right here: the token is 256 bits of
randomness, not a guessable password. Verification hashes the presented
token and compares it with every active hash in constant time.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from stocktrack.models import ApiToken

TOKEN_PREFIX = "st_"
# Touch last_used_at at most this often per token, not a write per request.
LAST_USED_RESOLUTION = timedelta(minutes=1)


class DuplicateTokenName(ValueError):
    """Raised when an unrevoked token with this name already exists."""


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_token(session: AsyncSession, name: str,
                       expires_in_days: int | None) -> tuple[ApiToken, str]:
    """Create a token; returns the row and the token, which is never stored.

    The name must be unique among unrevoked tokens; a revoked one's name is
    free again.
    """
    taken = (await session.execute(
        select(ApiToken.id).where(ApiToken.name == name,
                                  ApiToken.revoked_at.is_(None)).limit(1)
    )).scalar_one_or_none()
    if taken is not None:
        raise DuplicateTokenName(name)
    token = generate_token()
    now = datetime.now(timezone.utc)
    row = ApiToken(
        name=name,
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + timedelta(days=expires_in_days) if expires_in_days else None,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Lost a race with a concurrent create of the same name.
        await session.rollback()
        raise DuplicateTokenName(name) from exc
    return row, token


async def list_tokens(session: AsyncSession) -> list[ApiToken]:
    return list((await session.execute(
        select(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    )).scalars().all())


async def revoke_token(session: AsyncSession, token_id: int) -> ApiToken | None:
    """Revoke a token; idempotent (a second revoke keeps the first time)."""
    row = await session.get(ApiToken, token_id)
    if row is None:
        return None
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()
    return row


async def verify_token(session: AsyncSession, presented: str) -> ApiToken | None:
    """Return the active token matching ``presented``, else None.

    Unknown, revoked and expired tokens all give None: the caller answers
    401 without saying which.
    """
    now = datetime.now(timezone.utc)
    presented_hash = hash_token(presented).encode("ascii")
    active = (await session.execute(
        select(ApiToken).where(
            ApiToken.revoked_at.is_(None),
            or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now),
        ))).scalars().all()
    match = None
    for row in active:  # no early exit: every active hash is compared
        if hmac.compare_digest(row.token_hash.encode("ascii"), presented_hash):
            match = row
    if match is None:
        return None
    if match.last_used_at is None or now - match.last_used_at >= LAST_USED_RESOLUTION:
        match.last_used_at = now
        await session.commit()
    return match
