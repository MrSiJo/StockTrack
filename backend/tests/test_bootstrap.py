import pytest
from stocktrack.bootstrap import Settings

def test_settings_load_minimal(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
    s = Settings()
    assert s.app_secret_key == "x" * 32
    assert s.database_url.startswith("sqlite+aiosqlite")
    assert s.restock_priority == 8
    assert s.gotify_send_retries == 3

def test_settings_rejects_short_secret(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "tooshort")
    with pytest.raises(ValueError):
        Settings()
