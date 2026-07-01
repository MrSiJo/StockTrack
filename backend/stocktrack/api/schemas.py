from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── Watch ──────────────────────────────────────────────────────────────────

class WatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    store: str
    url: str
    label: str
    include_filter: str
    exclude_filter: str
    interval_seconds: int
    enabled: bool
    kind: str
    track_price_drops: bool
    track_price_rises: bool
    price_drop_min_pct: Optional[float]
    price_drop_min_abs: Optional[float]
    price_target: Optional[float]
    created_at: datetime
    last_checked_at: Optional[datetime]
    last_ok_at: Optional[datetime]
    consecutive_failures: int
    last_error: str


class WatchCreate(BaseModel):
    store: str
    url: str
    label: str = ""
    include_filter: str = ""
    exclude_filter: str = ""
    interval_seconds: int = 300
    enabled: bool = True
    kind: str = "listing"
    track_price_drops: bool = False
    track_price_rises: bool = False
    price_drop_min_pct: Optional[float] = None
    price_drop_min_abs: Optional[float] = None
    price_target: Optional[float] = None


class WatchUpdate(BaseModel):
    store: Optional[str] = None
    url: Optional[str] = None
    label: Optional[str] = None
    include_filter: Optional[str] = None
    exclude_filter: Optional[str] = None
    interval_seconds: Optional[int] = None
    enabled: Optional[bool] = None
    kind: Optional[str] = None
    track_price_drops: Optional[bool] = None
    track_price_rises: Optional[bool] = None
    price_drop_min_pct: Optional[float] = None
    price_drop_min_abs: Optional[float] = None
    price_target: Optional[float] = None


# ── Status ─────────────────────────────────────────────────────────────────

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    store: str
    code: str
    title: str
    url: str
    brand: str
    availability: str
    basket_url: str
    delivery: str
    current_in_stock: bool
    current_price: Optional[float]
    lowest_price: Optional[float]
    available_since: Optional[datetime]
    last_checked: Optional[datetime]


class WatchStatusOut(BaseModel):
    id: int
    store: str
    url: str
    label: str
    enabled: bool
    last_checked_at: Optional[datetime]
    last_ok_at: Optional[datetime]
    consecutive_failures: int
    last_error: str
    products: list[ProductOut]


# ── Events ─────────────────────────────────────────────────────────────────

class EventOut(BaseModel):
    id: int
    ts: datetime
    kind: str
    price: Optional[float]
    available_seconds: Optional[int]
    product_title: str
    store: str
    url: str
    basket_url: str


# ── Stores ─────────────────────────────────────────────────────────────────

class StoreSettingOut(BaseModel):
    key: str
    label: str
    type: str
    default: bool | int | float | str


class StoreOut(BaseModel):
    name: str
    kinds: list[str]
    supported: bool
    settings: list[StoreSettingOut]


# ── Preview ────────────────────────────────────────────────────────────────

class PreviewRequest(BaseModel):
    store: str
    url: str
    kind: str = "listing"
    include_filter: str = ""
    exclude_filter: str = ""


class PreviewProductOut(BaseModel):
    code: str
    title: str
    brand: str
    url: str
    in_stock: bool
    price: Optional[float]
    delivery: str
    availability: str
    basket_url: str


# ── Settings ───────────────────────────────────────────────────────────────

class SettingsOut(BaseModel):
    gotify_url: str
    gotify_token_set: bool
    gotify_priority: int
    restock_priority: int
    new_product_priority: int
    oos_priority: int
    gotify_send_retries: int
    default_interval_seconds: int
    failure_alert_after: int
    heartbeat_hours: float
    early_access_days: int
    ao_member: bool
    price_drop_min_pct: float
    price_drop_min_abs: float
    price_drop_priority: int
    lead_time_priority: int
    alert_group_threshold: int
    price_drop_in_stock_only: bool
    cp_delivery_postcode: str
    cp_collection_branch_id: str


class SettingsUpdate(BaseModel):
    gotify_url: Optional[str] = None
    gotify_token: Optional[str] = None   # write-only; never returned
    gotify_priority: Optional[int] = None
    restock_priority: Optional[int] = None
    new_product_priority: Optional[int] = None
    oos_priority: Optional[int] = None
    gotify_send_retries: Optional[int] = None
    default_interval_seconds: Optional[int] = None
    failure_alert_after: Optional[int] = None
    heartbeat_hours: Optional[float] = None
    early_access_days: Optional[int] = None
    ao_member: Optional[bool] = None
    price_drop_min_pct: Optional[float] = None
    price_drop_min_abs: Optional[float] = None
    price_drop_priority: Optional[int] = None
    lead_time_priority: Optional[int] = None
    alert_group_threshold: Optional[int] = None
    price_drop_in_stock_only: Optional[bool] = None
    cp_delivery_postcode: Optional[str] = None
    cp_collection_branch_id: Optional[str] = None


# ── History ────────────────────────────────────────────────────────────────

class EpisodeOut(BaseModel):
    started_ts: datetime
    early_access_ts: Optional[datetime] = None
    public_ts: Optional[datetime] = None
    ended_ts: Optional[datetime] = None
    ongoing: bool
    buyable_seconds: Optional[int] = None
    early_lead_seconds: Optional[int] = None
    price: Optional[float] = None


class ProductRefOut(BaseModel):
    id: int
    title: str
    store: str
    url: str
    basket_url: str


class HistorySummaryOut(BaseModel):
    episodes: int
    avg_buyable_seconds: Optional[float] = None
    avg_early_lead_seconds: Optional[float] = None


class ProductHistoryOut(BaseModel):
    product: ProductRefOut
    summary: HistorySummaryOut
    episodes: list[EpisodeOut]
