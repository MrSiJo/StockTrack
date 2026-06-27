from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Watch(Base):
    __tablename__ = "watch"
    id: Mapped[int] = mapped_column(primary_key=True)
    store: Mapped[str]
    url: Mapped[str]
    label: Mapped[str] = mapped_column(default="")
    include_filter: Mapped[str] = mapped_column(default="")
    exclude_filter: Mapped[str] = mapped_column(default="")
    interval_seconds: Mapped[int] = mapped_column(default=300)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(default="")
