"""Prometheus metrics for all modules."""
from prometheus_client import Counter, Histogram, Gauge

# HTTP metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently in progress',
    ['method', 'endpoint']
)

# Orchestrator metrics
orchestrator_invocations_total = Counter(
    'orchestrator_invocations_total',
    'Total orchestrator invocations',
    ['intent']
)

orchestrator_duration_seconds = Histogram(
    'orchestrator_duration_seconds',
    'Orchestrator execution duration',
    ['intent']
)

orchestrator_iterations_total = Counter(
    'orchestrator_iterations_total',
    'Total orchestrator iterations',
    ['intent']
)

orchestrator_degraded_total = Counter(
    'orchestrator_degraded_total',
    'Total degraded orchestrator responses',
    ['degradation_type']
)

orchestrator_partial_total = Counter(
    'orchestrator_partial_total',
    'Total partial orchestrator responses'
)

# Node metrics
node_invocations_total = Counter(
    'node_invocations_total',
    'Total node invocations',
    ['node_name']
)

node_duration_seconds = Histogram(
    'node_duration_seconds',
    'Node execution duration',
    ['node_name']
)

node_errors_total = Counter(
    'node_errors_total',
    'Total node errors',
    ['node_name', 'error_type']
)

# Tool metrics
tool_invocations_total = Counter(
    'tool_invocations_total',
    'Total tool invocations',
    ['tool_name']
)

tool_duration_seconds = Histogram(
    'tool_duration_seconds',
    'Tool execution duration',
    ['tool_name']
)

tool_errors_total = Counter(
    'tool_errors_total',
    'Total tool errors',
    ['tool_name', 'error_type']
)

# Session metrics
active_sessions = Gauge(
    'active_sessions',
    'Number of active sessions'
)

session_duration_seconds = Histogram(
    'session_duration_seconds',
    'Session duration'
)

session_tokens_total = Histogram(
    'session_tokens_total',
    'Total tokens per session'
)

session_expired_total = Counter(
    'session_expired_total',
    'Total expired sessions'
)

# LLM metrics
llm_invocations_total = Counter(
    'llm_invocations_total',
    'Total LLM invocations',
    ['model', 'agent']
)

llm_duration_seconds = Histogram(
    'llm_duration_seconds',
    'LLM response duration',
    ['model', 'agent']
)

llm_tokens_total = Counter(
    'llm_tokens_total',
    'Total LLM tokens',
    ['model', 'type']  # type: input, output
)

llm_cost_total = Counter(
    'llm_cost_total',
    'Total LLM cost',
    ['model']
)

llm_errors_total = Counter(
    'llm_errors_total',
    'Total LLM errors',
    ['model', 'error_type']
)

# Circuit breaker metrics
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Circuit breaker state',
    ['name', 'state']  # state: 0=CLOSED, 1=OPEN, 2=HALF_OPEN
)

circuit_breaker_failures_total = Counter(
    'circuit_breaker_failures_total',
    'Circuit breaker failures',
    ['name']
)

circuit_breaker_trips_total = Counter(
    'circuit_breaker_trips_total',
    'Circuit breaker trips',
    ['name']
)
