"""Tool-level resilience: retry with backoff + circuit breaker.

Circuit breaker states:
    CLOSED  → normal operation, failures are counted
    OPEN    → all calls short-circuit immediately with fallback
    HALF_OPEN → one probe call allowed; success → CLOSED, failure → OPEN
"""
import functools
import threading
import time
from enum import Enum
from typing import Callable

from loguru import logger


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-tool circuit breaker with configurable thresholds."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("[CircuitBreaker:{}] OPEN → HALF_OPEN", self.name)
            return self._state

    def record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("[CircuitBreaker:{}] HALF_OPEN → CLOSED", self.name)
            self._failure_count = 0

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("[CircuitBreaker:{}] HALF_OPEN → OPEN (probe failed)", self.name)
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "[CircuitBreaker:{}] CLOSED → OPEN (failures={}/{})",
                    self.name, self._failure_count, self.failure_threshold,
                )

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
            return False
        return False


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(name=name, **kwargs)
        return _breakers[name]


def resilient_tool(
    retries: int = 2,
    backoff_base: float = 1.0,
    circuit_name: str | None = None,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    fallback_message: str = "服务暂时不可用，请稍后重试。",
    retryable_exceptions: tuple = (Exception,),
):
    """Decorator that adds retry + circuit breaker to a tool function.

    Usage:
        @tool
        @resilient_tool(retries=2, circuit_name="twitter_api")
        def fetch_and_save_profile(...) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        name = circuit_name or func.__name__
        breaker = get_breaker(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not breaker.allow_request():
                logger.warning("[Resilience:{}] Circuit OPEN, returning fallback", name)
                return f"[熔断] {fallback_message}"

            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    result = func(*args, **kwargs)
                    breaker.record_success()
                    return result
                except retryable_exceptions as e:
                    last_exc = e
                    if attempt < retries:
                        wait = backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            "[Resilience:{}] Attempt {}/{} failed: {}. Retrying in {:.1f}s",
                            name, attempt, retries, str(e)[:100], wait,
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            "[Resilience:{}] All {} attempts failed: {}",
                            name, retries, str(e)[:200],
                        )

            breaker.record_failure()
            return f"[重试失败] {fallback_message} — {name}（共尝试 {retries} 次）: {str(last_exc)[:200]}"

        return wrapper
    return decorator


def get_circuit_status() -> dict[str, str]:
    """Return current state of all circuit breakers (for health checks)."""
    with _breakers_lock:
        return {name: cb.state.value for name, cb in _breakers.items()}
