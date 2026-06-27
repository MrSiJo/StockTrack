import os

import pytest
from sqlalchemy import select

os.environ.setdefault("APP_SECRET_KEY", "t" * 32)


async def test_seed_both_empty_creates_no_watches(sessionmaker_, monkeypatch):
    """With SEED_AO_URL and SEED_JL_URL both unset, seed_default_watches creates zero watches."""
    from stocktrack.bootstrap import get_settings
    from stocktrack.models import Watch
    from stocktrack.seed import seed_default_watches

    monkeypatch.setenv("SEED_AO_URL", "")
    monkeypatch.setenv("SEED_JL_URL", "")
    get_settings.cache_clear()

    async with sessionmaker_() as s:
        await seed_default_watches(s)
        await s.commit()
        result = (await s.execute(select(Watch))).scalars().all()

    get_settings.cache_clear()
    assert result == []


async def test_seed_with_both_urls_creates_two_watches(sessionmaker_, monkeypatch):
    """With both seed URLs set, seed_default_watches creates one watch per store."""
    from stocktrack.bootstrap import get_settings
    from stocktrack.models import Watch
    from stocktrack.seed import seed_default_watches

    monkeypatch.setenv("SEED_AO_URL", "https://ao.com/l/example")
    monkeypatch.setenv("SEED_JL_URL", "https://www.johnlewis.com/browse/example")
    get_settings.cache_clear()

    async with sessionmaker_() as s:
        await seed_default_watches(s)
        await s.commit()
        result = (await s.execute(select(Watch))).scalars().all()

    get_settings.cache_clear()
    assert len(result) == 2
    stores = {w.store for w in result}
    assert stores == {"ao", "johnlewis"}
    by_store = {w.store: w for w in result}
    assert by_store["ao"].url == "https://ao.com/l/example"
    assert by_store["ao"].include_filter == "Meaco"
    assert by_store["ao"].exclude_filter == "Heating"
    assert by_store["johnlewis"].url == "https://www.johnlewis.com/browse/example"
    assert by_store["johnlewis"].include_filter == "Cirro"
    assert by_store["johnlewis"].exclude_filter == ""


async def test_seed_only_ao_url_creates_one_watch(sessionmaker_, monkeypatch):
    """With only SEED_AO_URL set, seed_default_watches creates exactly one watch."""
    from stocktrack.bootstrap import get_settings
    from stocktrack.models import Watch
    from stocktrack.seed import seed_default_watches

    monkeypatch.setenv("SEED_AO_URL", "https://ao.com/l/example")
    monkeypatch.setenv("SEED_JL_URL", "")
    get_settings.cache_clear()

    async with sessionmaker_() as s:
        await seed_default_watches(s)
        await s.commit()
        result = (await s.execute(select(Watch))).scalars().all()

    get_settings.cache_clear()
    assert len(result) == 1
    assert result[0].store == "ao"


async def test_seed_skips_when_watches_exist(sessionmaker_, monkeypatch):
    """seed_default_watches is a no-op when watches already exist."""
    from stocktrack.bootstrap import get_settings
    from stocktrack.models import Watch
    from stocktrack.seed import seed_default_watches

    monkeypatch.setenv("SEED_AO_URL", "https://ao.com/l/example")
    monkeypatch.setenv("SEED_JL_URL", "https://www.johnlewis.com/browse/example")
    get_settings.cache_clear()

    async with sessionmaker_() as s:
        existing = Watch(store="ao", url="http://existing.example.com",
                         include_filter="", exclude_filter="")
        s.add(existing)
        await s.commit()

        await seed_default_watches(s)
        await s.commit()
        result = (await s.execute(select(Watch))).scalars().all()

    get_settings.cache_clear()
    assert len(result) == 1
    assert result[0].url == "http://existing.example.com"
