"""Circuit breaker for external service calls (OpenAI, etc.)."""

import asyncio
import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple async circuit breaker.

    - CLOSED: requests pass through normally.
    - OPEN: requests fail immediately (fast-fail) for `recovery_timeout` seconds.
    - HALF_OPEN: one probe request is allowed; success closes, failure re-opens.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    async def __aenter__(self):
        async with self._lock:
            current = self.state
            if current == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is OPEN — "
                    f"failing fast (recovery in {self.recovery_timeout - (time.time() - self._last_failure_time):.0f}s)"
                )
            if current == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max:
                    raise CircuitOpenError(f"Circuit breaker '{self.name}' is HALF_OPEN — max probes reached")
                self._half_open_calls += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            if exc_type is None:
                self._on_success()
            else:
                self._on_failure()
        return False

    def _on_success(self):
        if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info("Circuit breaker '%s' recovered → CLOSED", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._half_open_calls = 0
            logger.warning(
                "Circuit breaker '%s' tripped → OPEN after %d failures",
                self.name, self._failure_count,
            )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
        }


class CircuitOpenError(Exception):
    pass


# Global circuit breakers
openai_circuit = CircuitBreaker("openai", failure_threshold=5, recovery_timeout=30.0)
