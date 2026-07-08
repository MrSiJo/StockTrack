"""DB-backed settings with encrypted secrets + env seed."""
import logging
from typing import Optional
from stocktrack.crypto import decrypt, encrypt
from stocktrack.models.setting import Setting

log = logging.getLogger(__name__)


def truthy(v) -> bool:
    """Parse a stored/string/bool setting value as a boolean."""
    return str(v).strip().lower() in ("1", "true", "yes", "on")

async def get(session, key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a setting value by key. Returns the stored value as-is.

    Secret settings are stored encrypted; use get_secret to decrypt them.
    """
    row = await session.get(Setting, key)
    if row is None:
        return default
    return row.value  # plain value; secrets are stored encrypted

async def get_secret(session, key: str, secret_key: str, default: str = "") -> str:
    """Get and decrypt a secret setting."""
    row = await session.get(Setting, key)
    if row is None or not row.value:
        return default
    try:
        return decrypt(row.value, secret_key)
    except Exception:
        # An empty gotify_token reads as "unconfigured", so a decrypt failure
        # would otherwise silently disable all alerts while state advances.
        log.error("decrypt of setting %r failed — has APP_SECRET_KEY changed? "
                  "Re-save the secret in the UI to restore notifications.", key)
        return default

async def set_value(session, key: str, value: str, *, is_secret: bool = False,
                    secret_key: str = "") -> None:
    """Upsert a setting. Encrypts if is_secret=True."""
    stored = encrypt(value, secret_key) if is_secret and value else value
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=stored, is_secret=is_secret))
    else:
        row.value = stored
        row.is_secret = is_secret


def _coerce(value, type_: str):
    if type_ == "bool":
        return truthy(value)
    if type_ == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if type_ == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return "" if value is None else str(value)


async def store_config_kwargs(session, handler) -> dict:
    """Build configure() kwargs: global early_access_days + the handler's
    declared per-store settings, each coerced to its Python type."""
    kwargs = {"early_access_days": int(await get(session, "early_access_days", "30") or 30)}
    for spec in getattr(handler, "settings_spec", []) or []:
        key = spec["key"]
        default = spec.get("default", "")
        raw = await get(session, key, str(default))
        kwargs[key] = _coerce(raw, spec.get("type", "str"))
    return kwargs


async def gotify_config(session, secret_key: str) -> dict:
    """Return the Gotify configuration dict for use in gotify.send()."""
    url = await get(session, "gotify_url", "")
    token = await get_secret(session, "gotify_token", secret_key, "")
    retries = await get(session, "gotify_send_retries", "3")
    return {"url": url or "", "token": token, "retries": int(retries or 3)}

async def seed_from_env(session, env, secret_key: str) -> None:
    """Seed settings from environment defaults (only if not already set)."""
    defaults = {
        "gotify_url": (env.gotify_url, False),
        "gotify_token": (env.gotify_token, True),
        "gotify_priority": (str(env.gotify_priority), False),
        "restock_priority": (str(env.restock_priority), False),
        "new_product_priority": (str(env.new_product_priority), False),
        "oos_priority": (str(env.oos_priority), False),
        "gotify_send_retries": (str(env.gotify_send_retries), False),
        "default_interval_seconds": (str(env.default_interval_seconds), False),
        "failure_alert_after": (str(env.failure_alert_after), False),
        "event_retention_days": (str(env.event_retention_days), False),
        "product_archive_days": (str(env.product_archive_days), False),
        "dashboard_url": (env.dashboard_url, False),
        "heartbeat_hours": (str(env.heartbeat_hours), False),
        "early_access_days": (str(env.early_access_days), False),
        "ao_member": (str(env.ao_member).lower(), False),
        "price_drop_min_pct": (str(env.price_drop_min_pct), False),
        "price_drop_min_abs": (str(env.price_drop_min_abs), False),
        "price_drop_priority": (str(env.price_drop_priority), False),
        "lead_time_priority": (str(env.lead_time_priority), False),
        "lead_time_min_change_days": (str(env.lead_time_min_change_days), False),
        "alert_group_threshold": (str(env.alert_group_threshold), False),
        "price_drop_in_stock_only": (str(env.price_drop_in_stock_only).lower(), False),
        "digest_cadence": (env.digest_cadence, False),
        "digest_hour": (str(env.digest_hour), False),
        "digest_priority": (str(env.digest_priority), False),
        "cp_delivery_postcode": (env.cp_delivery_postcode, False),
        "cp_collection_branch_id": (env.cp_collection_branch_id, False),
    }
    for key, (value, is_secret) in defaults.items():
        existing = await session.get(Setting, key)
        if existing is None:
            await set_value(session, key, value, is_secret=is_secret, secret_key=secret_key)
    await session.commit()
