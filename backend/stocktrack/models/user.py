from datetime import datetime
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base, UTCDateTime, utcnow

class User(Base):
    """The single login user, created once by /api/setup."""
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Always 1. The unique constraint is what makes setup race safe: two
    # setups that both passed the "no user yet" check cannot both insert,
    # whatever usernames they chose.
    singleton: Mapped[int] = mapped_column(default=1, unique=True)
