from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime, utcnow

class ProductChange(Base):
    """A silent record of a product's price or discounts changing between polls.

    Separate from ``Event`` so History and the delivery safe alert rules are
    untouched: nothing here is ever pushed.
    """
    __tablename__ = "product_change"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    field: Mapped[str]  # "price" | "discounts"
    old: Mapped[Optional[str]] = mapped_column(default=None)
    new: Mapped[Optional[str]] = mapped_column(default=None)
