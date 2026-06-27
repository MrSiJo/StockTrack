"""DB-backed settings with encrypted secrets + env seed."""
from typing import Optional
from sqlalchemy import select
from stocktrack.crypto import decrypt, encrypt
from stocktrack.models.setting import Setting

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
        "oos_priority": (str(env.oos_priority), False),
        "gotify_send_retries": (str(env.gotify_send_retries), False),
        "default_interval_seconds": (str(env.default_interval_seconds), False),
        "failure_alert_after": (str(env.failure_alert_after), False),
        "heartbeat_hours": (str(env.heartbeat_hours), False),
        "early_access_days": (str(env.early_access_days), False),
    }
    for key, (value, is_secret) in defaults.items():
        existing = await session.get(Setting, key)
        if existing is None:
            await set_value(session, key, value, is_secret=is_secret, secret_key=secret_key)
    await session.commit()
