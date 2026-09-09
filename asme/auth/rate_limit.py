"""In-memory login rate limiting.

Two counters back every login attempt:

* ``(client ip, identifier)`` – the ordinary "this person is guessing" case;
* ``identifier`` alone, with a larger allowance – so an attacker spreading
  guesses for one account across many source addresses (or across a rotating
  ``X-Forwarded-For``) still runs into a wall.

Per-process by design: it exists to slow credential stuffing on a small
instance, not to be a distributed limiter.
"""

from __future__ import annotations

import time
from threading import Lock

# How many failures the identifier-only counter allows, as a multiple of the
# per-address allowance. Generous enough that a shared campus NAT does not lock
# a real member out, small enough to make distributed guessing expensive.
IDENTIFIER_ATTEMPT_MULTIPLIER = 4


class LoginRateLimiter:
    def __init__(self, window_seconds: int, max_attempts: int):
        self.window_seconds = max(1, int(window_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self._rows: dict[str, dict] = {}
        self._lock = Lock()

    @property
    def max_identifier_attempts(self) -> int:
        return self.max_attempts * IDENTIFIER_ATTEMPT_MULTIPLIER

    @staticmethod
    def _normalize(identifier: str) -> str:
        return (identifier or "").strip().lower()

    @classmethod
    def key(cls, client_ip: str, identifier: str) -> str:
        return f"{client_ip}|{cls._normalize(identifier)}"

    @classmethod
    def identifier_key(cls, identifier: str) -> str:
        return f"identifier|{cls._normalize(identifier)}"

    def _sweep(self, now: float) -> None:
        expired = [key for key, info in self._rows.items() if now > info.get("reset_at", 0)]
        for key in expired:
            self._rows.pop(key, None)

    def _bump(self, key: str, now: float) -> None:
        row = self._rows.get(key)
        if not row or now > row.get("reset_at", 0):
            self._rows[key] = {"count": 1, "reset_at": now + self.window_seconds}
            return
        row["count"] = int(row.get("count", 0)) + 1

    def _check(self, key: str, limit: int, now: float) -> tuple[bool, int]:
        row = self._rows.get(key)
        if not row or int(row.get("count", 0)) < limit:
            return False, 0
        return True, int(max(1, row.get("reset_at", 0) - now))

    def record_failure(self, client_ip: str, identifier: str) -> None:
        now = time.time()
        with self._lock:
            self._sweep(now)
            self._bump(self.key(client_ip, identifier), now)
            if self._normalize(identifier):
                self._bump(self.identifier_key(identifier), now)

    def clear(self, client_ip: str, identifier: str) -> None:
        """Forget a successful login's failures (both counters)."""
        with self._lock:
            self._rows.pop(self.key(client_ip, identifier), None)
            self._rows.pop(self.identifier_key(identifier), None)

    def is_limited(self, client_ip: str, identifier: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            self._sweep(now)
            limited, retry_after = self._check(self.key(client_ip, identifier), self.max_attempts, now)
            if limited:
                return True, retry_after
            if not self._normalize(identifier):
                return False, 0
            return self._check(self.identifier_key(identifier), self.max_identifier_attempts, now)

    def reset_all(self) -> None:
        with self._lock:
            self._rows.clear()
