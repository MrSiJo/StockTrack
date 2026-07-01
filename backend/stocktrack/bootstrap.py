from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_secret_key: str
    database_url: str = "sqlite+aiosqlite:///./data/stocktrack.db"
    data_dir: str = "./data"
    auth_enabled: bool = True
    cookie_secure: bool = True
    backend_port: int = 9180
    log_level: str = "INFO"
    tz: str = "Europe/London"
    gotify_url: str = ""
    gotify_token: str = ""
    gotify_priority: int = 7
    restock_priority: int = 8
    oos_priority: int = 4
    gotify_send_retries: int = 3
    failure_alert_after: int = 6
    heartbeat_hours: float = 0
    default_interval_seconds: int = 300
    early_access_days: int = 30
    ao_member: bool = False
    price_drop_min_pct: float = 5
    price_drop_min_abs: float = 5
    price_drop_priority: int = 6
    lead_time_priority: int = 5
    alert_group_threshold: int = 3
    price_drop_in_stock_only: bool = True
    cp_delivery_postcode: str = ""
    cp_collection_branch_id: str = ""
    seed_ao_url: str = ""
    seed_jl_url: str = ""

    @field_validator("app_secret_key")
    @classmethod
    def _secret_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("APP_SECRET_KEY must be at least 32 characters")
        return v

@lru_cache
def get_settings() -> Settings:
    return Settings()
