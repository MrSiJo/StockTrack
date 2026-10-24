import secrets
from datetime import datetime
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime, utcnow


def new_session_nonce() -> str:
    return secrets.token_urlsafe(16)


class User(Base):
    """The single login user, created once by /api/setup."""
    __tablename__ = "user"
    # AUTOINCREMENT: SQLite would otherwise hand a re-created user the id of
    # the deleted one, and ids must never be reused.
    __table_args__ = {"sqlite_autoincrement": True}
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Always 1. The unique constraint is what makes setup race safe: two
    # setups that both passed the "no user yet" check cannot both insert,
    # whatever usernames they chose.
    singleton: Mapped[int] = mapped_column(default=1, unique=True)
    # Random per user, carried in every session cookie. A cookie is only
    # valid while it matches, so a re-created user never inherits an old
    # session, and rotating it (sign out) ends every session at once.
    session_nonce: Mapped[str] = mapped_column(String(64), default=new_session_nonce)
