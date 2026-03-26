"""
Per-provider circuit breaker to prevent cascading failures.

States:
- CLOSED (normal): requests flow through
- OPEN (tripped): requests are blocked, fallback is used
- HALF_OPEN (recovery): a single test request is allowed through

Uses Redis for state sharing across Celery workers.
Falls back to in-memory tracking if Redis is unavailable.
"""
import logging
import time
from typing import Optional

from app.extensions import redis_client

logger = logging.getLogger(__name__)

# Circuit breaker settings
FAILURE_THRESHOLD = 5       # failures before opening
RECOVERY_TIMEOUT = 300      # seconds before trying again (5 min)
SUCCESS_THRESHOLD = 2       # successes in half-open before closing

# Redis key prefixes
_PREFIX = 'cb:'


class CircuitBreaker:
    """Provider-level circuit breaker with Redis-backed state."""

    def __init__(self):
        # In-memory fallback when Redis is unavailable
        self._local_failures: dict[str, int] = {}
        self._local_opened_at: dict[str, float] = {}
        self._local_half_open_successes: dict[str, int] = {}

    def is_open(self, provider: str) -> bool:
        """Check if the circuit is open (blocking requests) for a provider."""
        failures = self._get_failures(provider)
        if failures < FAILURE_THRESHOLD:
            return False

        opened_at = self._get_opened_at(provider)
        if opened_at and (time.time() - opened_at) > RECOVERY_TIMEOUT:
            # Transition to half-open: allow a test request
            return False

        return True

    def record_failure(self, provider: str):
        """Record a failure for a provider."""
        failures = self._get_failures(provider) + 1
        self._set_failures(provider, failures)

        if failures >= FAILURE_THRESHOLD:
            self._set_opened_at(provider, time.time())
            self._set_half_open_successes(provider, 0)
            logger.warning(
                f'Circuit breaker OPENED for {provider} '
                f'({failures} consecutive failures)'
            )

    def record_success(self, provider: str):
        """Record a success for a provider."""
        failures = self._get_failures(provider)
        if failures >= FAILURE_THRESHOLD:
            # In half-open state
            successes = self._get_half_open_successes(provider) + 1
            self._set_half_open_successes(provider, successes)

            if successes >= SUCCESS_THRESHOLD:
                # Close the circuit
                self._set_failures(provider, 0)
                self._set_opened_at(provider, 0)
                self._set_half_open_successes(provider, 0)
                logger.info(f'Circuit breaker CLOSED for {provider} (recovered)')
        else:
            # Normal state — reset failure count
            self._set_failures(provider, 0)

    # ── Storage helpers (Redis with in-memory fallback) ──────────

    def _get_failures(self, provider: str) -> int:
        if redis_client:
            val = redis_client.get(f'{_PREFIX}{provider}:failures')
            return int(val) if val else 0
        return self._local_failures.get(provider, 0)

    def _set_failures(self, provider: str, count: int):
        if redis_client:
            redis_client.setex(f'{_PREFIX}{provider}:failures', 3600, str(count))
        else:
            self._local_failures[provider] = count

    def _get_opened_at(self, provider: str) -> Optional[float]:
        if redis_client:
            val = redis_client.get(f'{_PREFIX}{provider}:opened_at')
            return float(val) if val else None
        return self._local_opened_at.get(provider)

    def _set_opened_at(self, provider: str, ts: float):
        if redis_client:
            redis_client.setex(f'{_PREFIX}{provider}:opened_at', 3600, str(ts))
        else:
            self._local_opened_at[provider] = ts

    def _get_half_open_successes(self, provider: str) -> int:
        if redis_client:
            val = redis_client.get(f'{_PREFIX}{provider}:ho_successes')
            return int(val) if val else 0
        return self._local_half_open_successes.get(provider, 0)

    def _set_half_open_successes(self, provider: str, count: int):
        if redis_client:
            redis_client.setex(f'{_PREFIX}{provider}:ho_successes', 3600, str(count))
        else:
            self._local_half_open_successes[provider] = count

    def get_status(self, provider: str) -> str:
        """Get human-readable circuit state for a provider."""
        failures = self._get_failures(provider)
        if failures < FAILURE_THRESHOLD:
            return 'closed'
        opened_at = self._get_opened_at(provider)
        if opened_at and (time.time() - opened_at) > RECOVERY_TIMEOUT:
            return 'half_open'
        return 'open'
