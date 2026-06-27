from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from stocktrack.services.history import Episode, build_episodes


@dataclass
class Ev:  # stand-in for a stocktrack.models.Event row
    ts: datetime
    kind: str
    price: Optional[float] = None
    available_seconds: Optional[int] = None


BASE = datetime(2026, 6, 27, 6, 0, tzinfo=timezone.utc)
def at(mins): return BASE + timedelta(minutes=mins)


def test_full_episode_early_public_oos():
    evs = [Ev(at(0), "early_access", 629.0),
           Ev(at(17), "public", 629.0),
           Ev(at(47), "oos", available_seconds=47 * 60)]
    [ep] = build_episodes(evs, now=at(60))
    assert ep.started_ts == at(0)
    assert ep.early_access_ts == at(0) and ep.public_ts == at(17)
    assert ep.ended_ts == at(47) and ep.ongoing is False
    assert ep.buyable_seconds == 47 * 60
    assert ep.early_lead_seconds == 17 * 60
    assert ep.price == 629.0


def test_early_only_never_public():
    evs = [Ev(at(0), "early_access", 599.0), Ev(at(6), "oos", available_seconds=6 * 60)]
    [ep] = build_episodes(evs, now=at(60))
    assert ep.early_access_ts == at(0) and ep.public_ts is None
    assert ep.early_lead_seconds is None and ep.buyable_seconds == 6 * 60


def test_public_only_no_early_access():
    evs = [Ev(at(0), "public", 539.0), Ev(at(15), "oos", available_seconds=15 * 60)]
    [ep] = build_episodes(evs, now=at(60))
    assert ep.early_access_ts is None and ep.public_ts == at(0)
    assert ep.started_ts == at(0) and ep.early_lead_seconds is None


def test_ongoing_episode_duration_from_now():
    evs = [Ev(at(0), "early_access", 629.0), Ev(at(17), "public", 629.0)]
    [ep] = build_episodes(evs, now=at(29))
    assert ep.ongoing is True and ep.ended_ts is None
    assert ep.buyable_seconds == 29 * 60  # now - started_ts


def test_leading_oos_with_no_open_episode_is_ignored():
    evs = [Ev(at(0), "oos", available_seconds=None),
           Ev(at(5), "public", 539.0), Ev(at(20), "oos", available_seconds=15 * 60)]
    eps = build_episodes(evs, now=at(60))
    assert len(eps) == 1 and eps[0].started_ts == at(5)


def test_multiple_episodes_chronological():
    evs = [Ev(at(0), "public", 629.0), Ev(at(10), "oos", available_seconds=600),
           Ev(at(40), "early_access", 629.0), Ev(at(45), "oos", available_seconds=300)]
    eps = build_episodes(evs, now=at(60))
    assert [e.started_ts for e in eps] == [at(0), at(40)]


def test_buyable_seconds_falls_back_to_span_when_available_seconds_missing():
    evs = [Ev(at(0), "public", 539.0), Ev(at(15), "oos", available_seconds=None)]
    [ep] = build_episodes(evs, now=at(60))
    assert ep.buyable_seconds == 15 * 60
