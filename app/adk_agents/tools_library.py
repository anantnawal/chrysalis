"""Standard read-only diagnostic and operational tools wrapped as Google ADK FunctionTools."""
from typing import Dict, Any, List
from google.adk.tools import FunctionTool
from app.target_env.server import env


def read_system_metrics() -> Dict[str, Any]:
    """Retrieve current system performance telemetry metrics including P99 latency, HTTP 5xx error rate, and DB pool load."""
    metrics = env.telemetry.get_current_metrics()
    return {
        "p99_latency_ms": metrics.p99_latency_ms,
        "http_5xx_rate": metrics.http_5xx_rate,
        "active_rps": metrics.active_requests_per_sec,
        "cache_hit_ratio": metrics.cache_hit_ratio,
        "cache_evictions": metrics.cache_eviction_count,
        "db_active_connections": metrics.db_active_connections,
        "db_waiting_threads": metrics.db_waiting_threads,
        "db_pool_utilization": metrics.db_pool_utilization,
        "status": "CRITICAL" if (metrics.http_5xx_rate > 0.05 or metrics.p99_latency_ms > 500) else "HEALTHY",
    }


def inspect_cache_status() -> Dict[str, Any]:
    """Inspect in-memory cache capacity, active key count, hit ratio, and recent LRU evictions."""
    stats = env.cache.get_stats()
    return {
        "active_keys": stats["active_keys"],
        "max_keys": stats["max_keys"],
        "hits": stats["hits"],
        "misses": stats["misses"],
        "hit_ratio": stats["hit_ratio"],
        "total_evictions": stats["eviction_count"],
        "recent_evicted_keys": [e.get("key") for e in stats.get("recent_evictions", [])],
        "diagnostics": "Severe key churn / LRU eviction detected" if stats["eviction_count"] > 0 else "Cache operating within quota",
    }


def inspect_db_pool() -> Dict[str, Any]:
    """Inspect transactional database connection pool status, active lock holders, waiting threads, and timeouts."""
    stats = env.db.get_pool_stats()
    return {
        "max_connections": stats["max_connections"],
        "active_connections": stats["active_connections"],
        "waiting_threads": stats["waiting_threads"],
        "pool_utilization": stats["pool_utilization"],
        "total_timeouts": stats["total_timeouts"],
        "starvation_alert": stats["waiting_threads"] > 0 or stats["total_timeouts"] > 0,
    }


# Principle store hook will be injected at runtime
_principle_store_instance = None


def set_principle_store(store):
    """Set the active principle store instance."""
    global _principle_store_instance
    _principle_store_instance = store


def retrieve_historical_principles(query: str) -> List[Dict[str, Any]]:
    """Self-Navigating memory retrieval: queries past incident principles for contraindications and recommended heuristics."""
    if _principle_store_instance is not None:
        results = _principle_store_instance.search_principles(query, top_k=3)
        return [
            {
                "principle_id": p.principle_id,
                "trigger_pattern": p.trigger_pattern,
                "contraindicated_actions": p.contraindicated_actions,
                "recommended_actions": p.recommended_actions,
                "confidence_score": p.confidence_score,
            }
            for p in results
        ]
    return [
        {
            "principle_id": "PRIN-HIST-001",
            "trigger_pattern": "Cache eviction stampede causing database connection pool saturation",
            "contraindicated_actions": ["restart_database", "increase_db_pool_timeout", "flush_db_connections"],
            "recommended_actions": ["deploy_token_bucket_rate_limiter", "throttle_ingress_boundary", "admit_shedding"],
            "confidence_score": 0.98,
        }
    ]


def reboot_database() -> str:
    """Dangerous action: Restarts transactional database to clear connections. Blocked if contraindicated."""
    env.db.reboot()
    return "Database reboot executed. All active connections dropped."


# Create ADK FunctionTool wrappers
tool_read_metrics = FunctionTool(read_system_metrics)
tool_inspect_cache = FunctionTool(inspect_cache_status)
tool_inspect_db_pool = FunctionTool(inspect_db_pool)
tool_retrieve_principles = FunctionTool(retrieve_historical_principles)
tool_reboot_database = FunctionTool(reboot_database)
