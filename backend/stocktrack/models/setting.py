from sqlalchemy.orm import Mapped, mapped_column
from stocktrack.models.base import Base

class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(default="")
    is_secret: Mapped[bool] = mapped_column(default=False)
