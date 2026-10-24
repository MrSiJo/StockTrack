from datetime import datetime
from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime, utcnow

class ApiToken(Base):
    """A machine client's bearer token. Only its SHA-256 is ever stored:
    the token itself is shown once, at creation."""
    __tablename__ = "api_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
