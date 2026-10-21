from typing import Dict, Any, List, Optional
from google.adk.tools import FunctionTool
from app.target_env.server import platform_env
from app.evolution.cloud_principle_store import CloudPrincipleStore

_principle_store: Optional[CloudPrincipleStore] = None


def get_principle_store() -> CloudPrincipleStore:
    """Lazy-load the CloudPrincipleStore to prevent slow remote calls during import."""
    global _principle_store
    if _principle_store is None:
        _principle_store = CloudPrincipleStore()
    return _principle_store


def read_system_metrics() -> Dict[str, Any]:
    """Read real-time SRE metrics (P99 latency, 5xx rate, active RPS) from Cloud Telemetry."""
    return platform_env.telemetry.get_current_metrics()


def inspect_cache_status() -> Dict[str, Any]:
    """Inspect Cloud Memorystore for Redis key capacity, eviction counts, and hit ratio."""
    return platform_env.cache.get_stats()


def inspect_db_pool() -> Dict[str, Any]:
    """Inspect Cloud SQL database connection pool saturation, active connections, and waiting threads."""
    return platform_env.db.get_pool_stats()


def retrieve_historical_principles(incident_context: str) -> List[Dict[str, Any]]:
    """Query Self-Navigating Vertex AI vector memory for past failure principles and contraindicated actions."""
    store = get_principle_store()
    results = store.query_similar_principles(incident_context, top_k=2)
    output = []
    for p, score in results:
        output.append({
            "principle_id": p.principle_id,
            "trigger_pattern": p.trigger_pattern,
            "contraindicated_actions": p.contraindicated_actions,
            "recommended_actions": p.recommended_actions,
            "confidence_score": p.confidence_score,
            "similarity_score": round(score, 3),
            "kms_signed": (p.kms_signature is not None),
        })
    return output


tool_read_metrics = FunctionTool(read_system_metrics)
tool_inspect_cache = FunctionTool(inspect_cache_status)
tool_inspect_db = FunctionTool(inspect_db_pool)
tool_retrieve_principles = FunctionTool(retrieve_historical_principles)

DIAGNOSTIC_TOOLS = [
    tool_read_metrics,
    tool_inspect_cache,
    tool_inspect_db,
    tool_retrieve_principles,
]
