import pytest
import pytest_asyncio
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
