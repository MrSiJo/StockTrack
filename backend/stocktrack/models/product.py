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
    lowest_price: Mapped[Optional[float]] = mapped_column(default=None)
    muted_until: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    available_since: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    spec_watts: Mapped[int | None] = mapped_column(default=None)
    # Offers (plugin API 2). discounts_json NULL = unknown; "[]" = none listed.
    variant: Mapped[str] = mapped_column(default="")
    seller: Mapped[str] = mapped_column(default="")
    seller_rating: Mapped[Optional[float]] = mapped_column(default=None)
    discounts_json: Mapped[Optional[str]] = mapped_column(default=None)
    extra_json: Mapped[str] = mapped_column(default="")
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_checked: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, default=None)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
