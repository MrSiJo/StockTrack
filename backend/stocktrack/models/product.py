from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime, utcnow

class Product(Base):
    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("watch_id", "code", name="uq_watch_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watch.id"))
    store: Mapped[str]
    code: Mapped[str]
    title: Mapped[str] = mapped_column(default="")
    brand: Mapped[str] = mapped_column(default="")
    url: Mapped[str] = mapped_column(default="")
    availability: Mapped[str] = mapped_column(default="oos")
    basket_url: Mapped[str] = mapped_column(default="")
    delivery: Mapped[str] = mapped_column(default="")
    current_in_stock: Mapped[bool] = mapped_column(default=False)
    current_price: Mapped[Optional[float]] = mapped_column(default=None)
    # Local price peak since the last drop alert — drop thresholds compare
    # against this so slow multi-tick creep still trips them.
    price_ref: Mapped[Optional[float]] = mapped_column(default=None)
    available_since: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    last_checked: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
