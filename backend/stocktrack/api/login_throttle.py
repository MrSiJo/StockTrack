"""In-memory per-username login throttle.

Complements the IP-based slowapi limit on ``/api/auth/login``: it tracks
consecutive failed login attempts *per username* and locks that username
for a cooldown once a threshold is crossed. This defends against the
distributed / rotating-IP brute force that a per-IP limit alone misses.

Single-worker only, like the rest of the app (SQLite plus an in process
scheduler): state is a process-local dict, which is safe precisely because
the API runs one uvicorn worker.

Trade-off: because failures are keyed by the *submitted* username, an
attacker can deliberately lock a known username (an account-lockout DoS).
That is acceptable for a single-user self-host where the per-IP limit
still applies to every attempt; revisit if the threat model widens.

Memory is bounded: every ``record_failure`` prunes entries whose lock and
window have both lapsed, and the dict is capped at ``max_entries``. When
full, the entry with the oldest ``first_failure_at`` is evicted, preferring
unlocked entries so a flood of random usernames cannot flush a real lock.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

# A username is locked after this many failures inside the rolling window.
DEFAULT_MAX_FAILURES = 10
# Length of the lockout once triggered.
DEFAULT_LOCKOUT_SECONDS = 15 * 60
# Failures older than this (with no new failure) don't count toward a lock.
DEFAULT_WINDOW_SECONDS = 15 * 60
# Upper bound on tracked usernames (submitted usernames are attacker-chosen).
DEFAULT_MAX_ENTRIES = 1000


@dataclass
class _Entry:
    failures: int = 0
    first_failure_at: float = 0.0
    locked_until: float = 0.0


class LoginThrottle:
    """Tracks failed logins per username and enforces a cooldown lock."""

    def __init__(
        self,
        max_failures: int = DEFAULT_MAX_FAILURES,
        lockout_seconds: int = DEFAULT_LOCKOUT_SECONDS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        time_func: Callable[[], float] = time.monotonic,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        self._time = time_func
        self._entries: dict[str, _Entry] = {}

    @staticmethod
    def _key(username: str) -> str:
        return username.strip().lower()

    def seconds_until_unlocked(self, username: str) -> int:
        """Seconds remaining on an active lock, or 0 if not locked."""
        entry = self._entries.get(self._key(username))
        if entry is None or entry.locked_until == 0.0:
            return 0
        remaining = entry.locked_until - self._time()
        if remaining <= 0:
            # Lock expired — clear the slate so the next failure starts fresh.
            self._entries.pop(self._key(username), None)
            return 0
        return math.ceil(remaining)

    def _prune(self, now: float) -> None:
        """Drop entries whose lock has expired and whose window has lapsed."""
        stale = [
            k
            for k, e in self._entries.items()
            if e.locked_until <= now and now - e.first_failure_at > self.window_seconds
        ]
        for k in stale:
            del self._entries[k]

    def _evict_for_new_key(self, now: float) -> None:
        """Make room for one new key: oldest unlocked first, locked only as a last resort."""
        while len(self._entries) >= self.max_entries and self._entries:
            unlocked = [k for k, e in self._entries.items() if e.locked_until <= now]
            pool = unlocked or list(self._entries)
            victim = min(pool, key=lambda k: self._entries[k].first_failure_at)
            del self._entries[victim]

    def record_failure(self, username: str) -> None:
        """Register one failed attempt; may transition the username to locked."""
        key = self._key(username)
        now = self._time()
        self._prune(now)
        entry = self._entries.get(key)

        if entry is not None and entry.locked_until > now:
            # Already locked — don't extend the window on further attempts.
            return

        if (
            entry is None
            or entry.first_failure_at == 0.0
            or (now - entry.first_failure_at > self.window_seconds)
        ):
            entry = _Entry(failures=1, first_failure_at=now)
        else:
            entry.failures += 1

        if entry.failures >= self.max_failures:
            entry.locked_until = now + self.lockout_seconds

        if key not in self._entries:
            self._evict_for_new_key(now)
        self._entries[key] = entry

    def reset(self, username: str) -> None:
        """Clear all failure state for a username (call on successful login)."""
        self._entries.pop(self._key(username), None)

    def clear(self) -> None:
        """Drop all tracked state (test hook)."""
        self._entries.clear()


# Module singleton wired into the login route (mirrors ``rate_limit.limiter``).
login_throttle = LoginThrottle()
