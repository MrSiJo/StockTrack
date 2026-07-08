from stocktrack.services.settings_service import get, get_secret, set_value, seed_from_env, gotify_config
from stocktrack.bootstrap import Settings, get_settings

KEY = "s" * 32

async def test_get_returns_default_when_missing(sessionmaker_):
    async with sessionmaker_() as s:
        assert await get(s, "nonexistent", "fallback") == "fallback"

async def test_set_and_get(sessionmaker_):
    async with sessionmaker_() as s:
        await set_value(s, "test_key", "test_val")
        await s.commit()
    async with sessionmaker_() as s:
        assert await get(s, "test_key") == "test_val"

async def test_secret_roundtrip(sessionmaker_):
    async with sessionmaker_() as s:
        await set_value(s, "my_secret", "supersecret", is_secret=True, secret_key=KEY)
        await s.commit()
    async with sessionmaker_() as s:
        val = await get_secret(s, "my_secret", KEY)
        assert val == "supersecret"

async def test_seed_from_env_idempotent(sessionmaker_, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", KEY)
    get_settings.cache_clear()
    env = Settings()
    async with sessionmaker_() as s:
        await seed_from_env(s, env, KEY)
    async with sessionmaker_() as s:
        await seed_from_env(s, env, KEY)  # second call should not raise
    async with sessionmaker_() as s:
        val = await get(s, "restock_priority")
        assert val == "8"

async def test_gotify_config(sessionmaker_):
    async with sessionmaker_() as s:
        await set_value(s, "gotify_url", "https://gotify.example")
        await set_value(s, "gotify_token", "mytoken", is_secret=True, secret_key=KEY)
        await set_value(s, "gotify_send_retries", "3")
        await s.commit()
    async with sessionmaker_() as s:
        cfg = await gotify_config(s, KEY)
        assert cfg["url"] == "https://gotify.example"
        assert cfg["token"] == "mytoken"
        assert cfg["retries"] == 3


async def test_get_secret_logs_on_decrypt_failure(sessionmaker_, caplog):
    """A changed APP_SECRET_KEY must not silently disable alerts — the
    decrypt failure is logged (and the default returned)."""
    import logging
    from stocktrack.services.settings_service import get_secret, set_value
    async with sessionmaker_() as s:
        await set_value(s, "gotify_token", "mytoken", is_secret=True, secret_key=KEY)
        await s.commit()
    async with sessionmaker_() as s:
        with caplog.at_level(logging.ERROR, logger="stocktrack.services.settings_service"):
            value = await get_secret(s, "gotify_token", "x" * 32, "")
        assert value == ""
        assert any("APP_SECRET_KEY" in r.message for r in caplog.records)


async def test_truthy_helper():
    from stocktrack.services.settings_service import truthy
    assert truthy("true") and truthy("True") and truthy("1") and truthy("yes")
    assert not truthy("false") and not truthy("") and not truthy(None) and not truthy("0")


async def test_seed_adds_price_drop_and_member_defaults(sessionmaker_):
    from types import SimpleNamespace
    from stocktrack.services.settings_service import get, seed_from_env
    env = SimpleNamespace(
        gotify_url="", gotify_token="", gotify_priority=7, restock_priority=8,
        new_product_priority=8,
        oos_priority=4, gotify_send_retries=3, default_interval_seconds=300,
        failure_alert_after=6, event_retention_days=0, early_access_days=30,
        ao_member=False, price_drop_min_pct=5, price_drop_min_abs=5,
        price_drop_priority=6, lead_time_priority=5,
        lead_time_min_change_days=7, alert_group_threshold=3,
        price_drop_in_stock_only=True,
        digest_cadence="off", digest_hour=8, digest_priority=4,
        cp_delivery_postcode="", cp_collection_branch_id="",
        product_archive_days=14, dashboard_url="",
        heartbeat_hours=24.0,
    )
    async with sessionmaker_() as s:
        await seed_from_env(s, env, "k" * 32)
        assert await get(s, "ao_member") == "false"
        assert await get(s, "price_drop_min_pct") == "5"
        assert await get(s, "price_drop_min_abs") == "5"
        assert await get(s, "price_drop_priority") == "6"
        assert await get(s, "alert_group_threshold") == "3"


async def test_new_setting_defaults_seeded(sessionmaker_, monkeypatch):
    """Fresh install: product_archive_days, dashboard_url, and the new
    event_retention_days default (180) are all seeded from bootstrap Settings.

    Note: seeded via a real bootstrap.Settings() rather than a bare `{}`,
    because seed_from_env reads every default via attribute access
    (env.gotify_url, env.product_archive_days, ...) — matching the existing
    convention in this module rather than dict-style .get() lookups.
    """
    monkeypatch.setenv("APP_SECRET_KEY", KEY)
    get_settings.cache_clear()
    env = Settings()
    async with sessionmaker_() as s:
        await seed_from_env(s, env, secret_key=KEY)
        assert await get(s, "product_archive_days") == "14"
        assert await get(s, "dashboard_url") == ""
        assert await get(s, "event_retention_days") == "180"
        assert await get(s, "heartbeat_hours") == "24.0"
