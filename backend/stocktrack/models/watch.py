from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime, utcnow

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
    kind: Mapped[str] = mapped_column(default="listing")
    track_price_drops: Mapped[bool] = mapped_column(default=False)
    track_price_rises: Mapped[bool] = mapped_column(default=False)
    # Optional per-watch overrides of the global price_drop_min_* settings,
    # and an absolute "alert when price reaches X" target.
    price_drop_min_pct: Mapped[Optional[float]] = mapped_column(default=None)
    price_drop_min_abs: Mapped[Optional[float]] = mapped_column(default=None)
    price_target: Mapped[Optional[float]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(default="")
