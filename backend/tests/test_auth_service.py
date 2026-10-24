"""auth_service: one-shot race safe setup and credential checks."""
from unittest.mock import patch

import pytest

from stocktrack.passwords import hash_password, verify_password
from stocktrack.services import auth_service
from stocktrack.services.auth_service import (
    SetupAlreadyComplete,
    WeakPasswordError,
    authenticate,
    bootstrap_user,
    warm_dummy_hash,
)

PW = "very-strong-pass"


def test_password_hash_is_argon2id_with_template_params():
    h = hash_password(PW)
    assert h.startswith("$argon2id$")
    assert "m=65536,t=2,p=2" in h
    assert verify_password(PW, h)
    assert not verify_password("wrong-password", h)
    assert not verify_password(PW, "not-a-hash")
    assert not verify_password("", h)


async def test_bootstrap_creates_the_user(sessionmaker_):
    async with sessionmaker_() as s:
        user = await bootstrap_user(s, " admin ", PW)
    assert user.username == "admin"
    assert user.password_hash != PW
    assert verify_password(PW, user.password_hash)


async def test_bootstrap_is_one_shot(sessionmaker_):
    async with sessionmaker_() as s:
        await bootstrap_user(s, "admin", PW)
    async with sessionmaker_() as s:
        with pytest.raises(SetupAlreadyComplete):
            await bootstrap_user(s, "second", PW)


async def test_bootstrap_is_race_safe(sessionmaker_, monkeypatch):
    """Two setups that both pass the existence check (the race) still cannot
    both create a user: the singleton unique constraint refuses the second,
    even with a different username."""
    async with sessionmaker_() as s:
        await bootstrap_user(s, "first", PW)

    async def _no_user_yet(session):
        return False

    monkeypatch.setattr(auth_service, "_user_exists", _no_user_yet)
    async with sessionmaker_() as s:
        with pytest.raises(SetupAlreadyComplete):
            await bootstrap_user(s, "racer", PW)

    from sqlalchemy import func, select
    from stocktrack.models import User
    async with sessionmaker_() as s:
        assert (await s.execute(select(func.count()).select_from(User))).scalar_one() == 1


async def test_bootstrap_rejects_weak_password(sessionmaker_):
    async with sessionmaker_() as s:
        with pytest.raises(WeakPasswordError):
            await bootstrap_user(s, "admin", "short")


async def test_bootstrap_rejects_blank_username(sessionmaker_):
    async with sessionmaker_() as s:
        with pytest.raises(ValueError):
            await bootstrap_user(s, "   ", PW)


async def test_authenticate(sessionmaker_):
    async with sessionmaker_() as s:
        await bootstrap_user(s, "admin", PW)
    async with sessionmaker_() as s:
        assert (await authenticate(s, "admin", PW)) is not None
        assert (await authenticate(s, "admin", "wrong-password-x")) is None
        assert (await authenticate(s, "nobody", PW)) is None
        assert (await authenticate(s, "", PW)) is None


async def test_unknown_user_still_runs_verify_password(sessionmaker_):
    async with sessionmaker_() as s:
        with patch.object(auth_service, "verify_password", return_value=False) as spy:
            assert (await authenticate(s, "nobody", "whatever-password")) is None
    spy.assert_called_once()
    plain, hashed = spy.call_args.args
    assert plain == "whatever-password"
    assert hashed.startswith("$argon2")


def test_warm_dummy_hash_builds_it_once(monkeypatch):
    monkeypatch.setattr(auth_service, "_DUMMY_HASH", None)
    warm_dummy_hash()
    assert auth_service._DUMMY_HASH is not None
    with patch.object(auth_service, "hash_password") as hasher:
        warm_dummy_hash()
    hasher.assert_not_called()


def _recording(real, seen):
    import threading

    def wrapper(*args):
        seen.append(threading.get_ident())
        return real(*args)
    return wrapper


async def test_argon2_runs_off_the_event_loop(sessionmaker_, monkeypatch):
    """argon2 is deliberately slow (64 MiB, tens of ms): on the loop thread
    it would stall every other request while a login or setup hashes."""
    import threading
    loop_thread = threading.get_ident()
    hashed, verified = [], []
    monkeypatch.setattr(auth_service, "hash_password",
                        _recording(auth_service.hash_password, hashed))
    monkeypatch.setattr(auth_service, "verify_password",
                        _recording(auth_service.verify_password, verified))
    async with sessionmaker_() as s:
        await bootstrap_user(s, "admin", PW)
    async with sessionmaker_() as s:
        assert await authenticate(s, "admin", PW) is not None
        assert await authenticate(s, "nobody", PW) is None
    assert hashed and verified
    assert loop_thread not in hashed + verified


async def test_at_most_two_argon2_operations_run_at_once(sessionmaker_, monkeypatch):
    """Each argon2 call takes 64 MiB: parallel logins must queue, not stack."""
    import threading
    import time
    lock = threading.Lock()
    running, peak = [0], [0]

    def slow_verify(plain, hashed):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return False

    async with sessionmaker_() as s:
        await bootstrap_user(s, "admin", PW)
    monkeypatch.setattr(auth_service, "verify_password", slow_verify)

    async def attempt(name):
        async with sessionmaker_() as s:
            return await authenticate(s, name, "wrong-password-x")

    import asyncio
    results = await asyncio.gather(*(attempt("admin" if i % 2 else "nobody")
                                     for i in range(6)))
    assert results == [None] * 6
    assert peak[0] == auth_service.ARGON2_CONCURRENCY == 2
