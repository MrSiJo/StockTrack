from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Event(Base):
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    kind: Mapped[str]  # "early_access" | "public" | "oos"
    price: Mapped[Optional[float]] = mapped_column(default=None)
    available_seconds: Mapped[Optional[int]] = mapped_column(default=None)
