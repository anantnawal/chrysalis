"""In-memory telemetry collector and OpenTelemetry-compatible span buffer."""
import threading
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import numpy as np
from app.adk_agents.schemas import SystemMetrics, ActionExecutionSpan, utc_now


class TelemetryCollector:
    """Thread-safe in-memory telemetry buffer tracking metrics and action execution spans."""

    def __init__(self, cache_service=None, db_service=None):
        self.cache_service = cache_service
        self.db_service = db_service
        self._lock = threading.Lock()

        # Sliding window request metrics
        self.request_latencies_ms: List[float] = []
        self.total_requests: int = 0
        self.status_2xx_count: int = 0
        self.status_5xx_count: int = 0
        self.window_start_time: float = time.time()

        # Detailed request log for DuckDB counterfactual replay
        self.request_logs: List[Dict[str, Any]] = []

        # Action execution trace spans for AgentEvolver credit attribution
        self.action_spans: List[ActionExecutionSpan] = []

    def record_request(
        self,
        request_id: str,
        endpoint: str,
        status_code: int,
        latency_ms: float,
        cache_miss: bool,
        admitted: bool = True,
    ) -> None:
        """Record an incoming HTTP request trace."""
        with self._lock:
            self.total_requests += 1
            if 200 <= status_code < 300:
                self.status_2xx_count += 1
            elif status_code >= 500:
                self.status_5xx_count += 1

            self.request_latencies_ms.append(latency_ms)
            # Keep sliding window bounded
            if len(self.request_latencies_ms) > 2000:
                self.request_latencies_ms = self.request_latencies_ms[-1000:]

            self.request_logs.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request_id": request_id,
                "endpoint": endpoint,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "cache_miss": int(cache_miss),
                "admitted": int(admitted),
            })

    def record_action_span(self, span: ActionExecutionSpan) -> None:
        """Record an agent execution span into the trace buffer."""
        with self._lock:
            self.action_spans.append(span)

    def get_current_metrics(self) -> SystemMetrics:
        """Calculate and return real-time SystemMetrics snapshot."""
        with self._lock:
            elapsed = max(time.time() - self.window_start_time, 0.001)
            active_rps = len(self.request_latencies_ms) / elapsed

            # Calculate P99 latency
            if self.request_latencies_ms:
                p99 = float(np.percentile(self.request_latencies_ms, 99))
            else:
                p99 = 20.0  # nominal baseline

            # Calculate 5xx rate
            total_reqs = self.status_2xx_count + self.status_5xx_count
            http_5xx_rate = (self.status_5xx_count / total_reqs) if total_reqs > 0 else 0.0

            # Cache metrics
            if self.cache_service:
                cache_stats = self.cache_service.get_stats()
                cache_hit_ratio = cache_stats["hit_ratio"]
                cache_eviction_count = cache_stats["eviction_count"]
            else:
                cache_hit_ratio = 1.0
                cache_eviction_count = 0

            # DB pool metrics
            if self.db_service:
                db_stats = self.db_service.get_pool_stats()
                db_active_connections = db_stats["active_connections"]
                db_waiting_threads = db_stats["waiting_threads"]
                # Report peak saturation within the current window: bursts complete before
                # metrics are sampled, so the instantaneous value would always read ~0%.
                db_pool_utilization = max(
                    db_stats["pool_utilization"],
                    db_stats.get("peak_pool_utilization", 0.0),
                )
            else:
                db_active_connections = 0
                db_waiting_threads = 0
                db_pool_utilization = 0.0

            return SystemMetrics(
                timestamp=utc_now(),
                active_requests_per_sec=round(active_rps, 1),
                p99_latency_ms=round(p99, 1),
                http_5xx_rate=round(http_5xx_rate, 3),
                cache_hit_ratio=round(cache_hit_ratio, 3),
                cache_eviction_count=cache_eviction_count,
                db_active_connections=db_active_connections,
                db_waiting_threads=db_waiting_threads,
                db_pool_utilization=round(db_pool_utilization, 2),
            )

    def get_action_spans(self) -> List[ActionExecutionSpan]:
        """Return a copy of the recorded action execution spans."""
        with self._lock:
            return list(self.action_spans)

    def get_request_logs(self) -> List[Dict[str, Any]]:
        """Return recorded request logs for offline DuckDB simulation."""
        with self._lock:
            return list(self.request_logs)

    def start_new_window(self) -> None:
        """Start a fresh metrics window (P99, 5xx rate, cache hit ratio, pool saturation).

        Historical request_logs and action_spans are preserved for Dream-RSI replay and
        credit attribution.
        """
        with self._lock:
            self.request_latencies_ms.clear()
            self.total_requests = 0
            self.status_2xx_count = 0
            self.status_5xx_count = 0
            self.window_start_time = time.time()
        if self.cache_service is not None and hasattr(self.cache_service, "reset_stats"):
            self.cache_service.reset_stats()
        if self.db_service is not None and hasattr(self.db_service, "reset_window"):
            self.db_service.reset_window()

    def reset(self) -> None:
        """Reset telemetry sliding window."""
        with self._lock:
            self.request_latencies_ms.clear()
            self.total_requests = 0
            self.status_2xx_count = 0
            self.status_5xx_count = 0
            self.window_start_time = time.time()
            self.request_logs.clear()
            self.action_spans.clear()
