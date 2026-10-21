"""Unit tests for Google Cloud Target Infrastructure components."""
import pytest
from app.config import PROJECT_ID
from app.target_env.memorystore_service import CloudMemorystoreService
from app.target_env.cloudsql_service import CloudSqlDatabaseService
from app.target_env.cloud_telemetry import CloudTelemetryCollector


def test_memorystore_lru_eviction():
    cache = CloudMemorystoreService(max_keys=3)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    cache.set("k3", "v3")

    # Access k1 so it becomes recently used
    assert cache.get("k1") == "v1"

    # Insert k4 -> should evict k2 (oldest accessed)
    cache.set("k4", "v4")

    stats = cache.get_stats()
    assert stats["active_keys"] == 3
    assert stats["eviction_count"] == 1
    assert cache.get("k2") is None
    assert cache.get("k1") == "v1"


def test_cloudsql_pool_starvation():
    db = CloudSqlDatabaseService(max_connections=1, query_latency_ms=10.0)

    # Acquire only available connection
    assert db.semaphore.acquire(blocking=False) is True

    # Next attempt should timeout
    with pytest.raises(TimeoutError):
        db.execute_checkout_transaction("cart_blocked", timeout_s=0.05)

    db.semaphore.release()
    db.reset_pool()


def test_cloud_telemetry_metrics():
    telemetry = CloudTelemetryCollector(project_id=PROJECT_ID)
    telemetry.record_request("req_1", "/checkout", 200, 20.0, cache_miss=False)
    telemetry.record_request("req_2", "/checkout", 500, 1500.0, cache_miss=True)

    metrics = telemetry.get_current_metrics()
    assert metrics["total_requests"] == 2
    assert metrics["status_2xx"] == 1
    assert metrics["status_5xx"] == 1
    assert metrics["http_5xx_rate"] == 0.5
