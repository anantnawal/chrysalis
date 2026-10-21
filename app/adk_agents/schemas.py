"""Formal Data Contracts & Schemas for Project Chrysalis."""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


class SystemMetrics(BaseModel):
    """Real-time system health and performance telemetry."""
    timestamp: datetime = Field(default_factory=utc_now)
    active_requests_per_sec: float = 0.0
    p99_latency_ms: float = 0.0
    http_5xx_rate: float = 0.0  # Fraction [0.0, 1.0]
    cache_hit_ratio: float = 1.0  # Fraction [0.0, 1.0]
    cache_eviction_count: int = 0
    db_active_connections: int = 0
    db_waiting_threads: int = 0
    db_pool_utilization: float = 0.0  # Fraction [0.0, 1.0]


class IncidentContext(BaseModel):
    """Contextual representation of an active or resolved incident."""
    incident_id: str
    trigger_symptom: str
    initial_metrics: SystemMetrics
    status: str = "DETECTED"  # "DETECTED", "DIAGNOSING", "MITIGATING", "RESOLVED", "POST_MORTEM"
    timeline_events: List[Dict[str, Any]] = []


class ActionExecutionSpan(BaseModel):
    """OpenTelemetry-compatible trace span for an agent mitigation action."""
    span_id: str
    parent_span_id: Optional[str] = None
    agent_name: str
    tool_name: str
    input_parameters: Dict[str, Any] = {}
    output_result: Dict[str, Any] = {}
    pre_state_metrics: SystemMetrics
    post_state_metrics: SystemMetrics
    cost_usd: float = 0.0
    execution_duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=utc_now)


class StepCreditAttribution(BaseModel):
    """Fine-grained credit attribution score computed for an execution span."""
    span_id: str
    tool_name: str
    action_type: str
    delta_latency: float
    delta_5xx_rate: float
    delta_pool_pressure: float
    attribution_score: float  # Scaled [-1.0, +1.0]
    rationale: str


class TrajectoryTree(BaseModel):
    """DAG of execution spans representing an end-to-end incident lifecycle."""
    incident_id: str
    spans: List[ActionExecutionSpan] = []
    root_cause_identified: str = ""
    overall_recovery_duration_sec: float = 0.0


class DynamicToolDefinition(BaseModel):
    """APEX Layer 1 Tool Patch synthesized dynamically by Gemini."""
    tool_name: str
    description: str
    python_code: str
    input_schema: Dict[str, Any] = {}
    verification_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class OperationalPrinciple(BaseModel):
    """APEX Layer 2 Distilled Invariant extracted by Gemini and stored in semantic memory."""
    principle_id: str
    trigger_pattern: str
    contraindicated_actions: List[str] = []
    recommended_actions: List[str] = []
    confidence_score: float = 0.95
    source_incident_id: str
    embedding: Optional[List[float]] = None


class CounterfactualReplayResult(BaseModel):
    """Dream-RSI Offline Simulation Policy Output."""
    policy_parameter_name: str
    tested_value: Any
    simulated_p99_latency_ms: float
    simulated_5xx_count: int
    simulated_database_max_load: float
    projected_cost_usd: float = 0.0
    is_pareto_optimal: bool = False
