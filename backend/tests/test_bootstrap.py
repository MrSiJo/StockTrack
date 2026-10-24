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


def test_auth_process_config_defaults(monkeypatch):
    """COOKIE_SECURE defaults to true (prod is HTTPS); sessions last 7 days."""
    from stocktrack.bootstrap import Settings
    monkeypatch.setenv("APP_SECRET_KEY", "k" * 32)
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.delenv("SESSION_MAX_AGE_SECONDS", raising=False)
    s = Settings(_env_file=None)
    assert s.cookie_secure is True
    assert s.session_max_age_seconds == 604800


def test_auth_process_config_from_env(monkeypatch):
    from stocktrack.bootstrap import Settings
    monkeypatch.setenv("APP_SECRET_KEY", "k" * 32)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("SESSION_MAX_AGE_SECONDS", "3600")
    s = Settings(_env_file=None)
    assert s.cookie_secure is False
    assert s.session_max_age_seconds == 3600
