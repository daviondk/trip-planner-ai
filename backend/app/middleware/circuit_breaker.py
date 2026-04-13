import time
import structlog
from enum import Enum
from typing import Callable, TypeVar
from functools import wraps
from prometheus_client import Gauge, Counter

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Circuit breaker pattern implementation for external API calls."""
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: int = 60,
        recovery_timeout: int = 60
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout  # Cooldown period in seconds
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.success_count = 0  # For HALF_OPEN state
        
        # Prometheus metrics
        self._circuit_state = Gauge(
            f'circuit_breaker_state_{name}',
            f'Circuit breaker state for {name}',
            ['state']
        )
        self._failure_count_metric = Counter(
            f'circuit_breaker_failures_{name}',
            f'Circuit breaker failures for {name}'
        )
        
        self._update_metrics()
    
    def _update_metrics(self):
        """Update Prometheus metrics."""
        # Reset all states
        for state in CircuitState:
            self._circuit_state.labels(state=state.value).set(0)
        # Set current state
        self._circuit_state.labels(state=self.state.value).set(1)
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt to reset from OPEN to HALF_OPEN."""
        if self.state != CircuitState.OPEN:
            return False
        if self.last_failure_time is None:
            return False
        return (time.time() - self.last_failure_time) >= self.recovery_timeout
    
    def _record_success(self):
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 1:  # Successful probe
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info("circuit_closed", name=self.name)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0  # Reset on success in CLOSED state
        self._update_metrics()
    
    def _record_failure(self):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.success_count = 0
            logger.warning("circuit_open_after_probe", name=self.name)
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning("circuit_open", name=self.name, failure_count=self.failure_count)
        
        self._failure_count_metric.inc()
        self._update_metrics()
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        # Check if circuit is OPEN
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info("circuit_half_open", name=self.name)
                self._update_metrics()
            else:
                logger.warning("circuit_rejected", name=self.name, state=self.state.value)
                raise Exception(f"Circuit breaker OPEN for {self.name}")
        
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise


# Global circuit breaker instances
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create circuit breaker instance."""
    if name not in _circuit_breakers:
        from app.config.settings import settings
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=settings.CIRCUIT_BREAKER_THRESHOLD,
            timeout=settings.CIRCUIT_BREAKER_COOLDOWN,
            recovery_timeout=settings.CIRCUIT_BREAKER_COOLDOWN
        )
    return _circuit_breakers[name]


def with_circuit_breaker(name: str):
    """Decorator to apply circuit breaker to a function."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            cb = get_circuit_breaker(name)
            return cb.call(func, *args, **kwargs)
        return wrapper
    return decorator
