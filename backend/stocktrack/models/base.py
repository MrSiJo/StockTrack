from datetime import timezone
from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase


class UTCDateTime(TypeDecorator):
    """Stores datetime as UTC; always returns timezone-aware datetime."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass
