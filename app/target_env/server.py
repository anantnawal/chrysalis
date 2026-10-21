"""Target Environment FastAPI Server exposing /checkout, /metrics, and administrative chaos endpoints."""
import asyncio
import time
import uuid
import json
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import PROJECT_ID
from app.target_env.cache_service import CacheService
from app.target_env.db_service import DatabaseService, DatabaseConnectionTimeoutError
from app.target_env.telemetry import TelemetryCollector
from app.adk_agents.schemas import SystemMetrics


class CheckoutRequest(BaseModel):
    user_id: str = Field(default_factory=lambda: f"user_{uuid.uuid4().hex[:6]}")
    cart_id: str = "cart_101"
    items: Optional[List[Dict[str, Any]]] = None


class RateLimiterConfig(BaseModel):
    enabled: bool = True
    capacity: int = 50
    replenishment_rate: float = 40.0  # tokens per second


class TargetEnvironment:
    """Encapsulates target infrastructure and services."""

    def __init__(self):
        self.cache = CacheService()
        self.db = DatabaseService()
        self.telemetry = TelemetryCollector(cache_service=self.cache, db_service=self.db)
        self.rate_limiter = None
        self.rate_limiter_config = RateLimiterConfig(enabled=False)

        # Connect eviction listener to telemetry
        self.cache.eviction_listener = self._on_cache_eviction

    def _on_cache_eviction(self, evicted_key: str):
        # Eviction listener hook
        pass


env = TargetEnvironment()
app = FastAPI(title="Project Chrysalis Target Environment API", version="2.0.0")


@app.post("/checkout")
async def checkout(request: CheckoutRequest):
    """Checkout endpoint: checks cache, falls back to DB on miss, applies active rate limiting."""
    start_time = time.perf_counter()
    req_id = f"req_{uuid.uuid4().hex[:8]}"

    # Check active APEX dynamic rate limiter if configured
    if env.rate_limiter is not None:
        admitted = env.rate_limiter.acquire(tokens=1)
        if not admitted:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            env.telemetry.record_request(
                request_id=req_id,
                endpoint="/checkout",
                status_code=429,
                latency_ms=latency_ms,
                cache_miss=False,
                admitted=False,
            )
            return Response(
                content=json.dumps({"error": "Rate limit exceeded (throttled by APEX TokenBucket)"}),
                status_code=429,
                media_type="application/json",
            )

    # 1. Try cache retrieval
    cart_data = env.cache.get(request.cart_id)
    cache_miss = cart_data is None

    if cache_miss:
        # Cache stampede: must query transactional database with limited connection pool
        loop = asyncio.get_running_loop()
        try:
            # Run DB query in executor to avoid blocking asyncio event loop
            db_result = await loop.run_in_executor(None, env.db.query_cart, request.cart_id)
            # Populate back into cache (enforcing LRU capacity)
            env.cache.set(request.cart_id, json.dumps(db_result))
            status_code = 200
            response_payload = {"status": "SUCCESS", "source": "DATABASE", "cart": db_result}
        except DatabaseConnectionTimeoutError as ex:
            # Connection pool starvation!
            status_code = 500
            response_payload = {"status": "ERROR", "error": str(ex), "source": "DATABASE_TIMEOUT"}
        except Exception as ex:
            status_code = 500
            response_payload = {"status": "ERROR", "error": str(ex)}
    else:
        status_code = 200
        parsed_cart = json.loads(cart_data) if isinstance(cart_data, str) else cart_data
        response_payload = {"status": "SUCCESS", "source": "CACHE", "cart": parsed_cart}

    latency_ms = (time.perf_counter() - start_time) * 1000.0
    env.telemetry.record_request(
        request_id=req_id,
        endpoint="/checkout",
        status_code=status_code,
        latency_ms=latency_ms,
        cache_miss=cache_miss,
        admitted=True,
    )

    if status_code >= 500:
        return Response(
            content=json.dumps(response_payload),
            status_code=status_code,
            media_type="application/json",
        )

    return response_payload


@app.get("/metrics", response_model=SystemMetrics)
def get_metrics():
    """Retrieve real-time telemetry metrics."""
    return env.telemetry.get_current_metrics()


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "HEALTHY", "system": "Project Chrysalis Target Environment", "project_id": PROJECT_ID}


@app.get("/ui", response_class=Response)
@app.get("/dashboard", response_class=Response)
def get_dashboard_ui():
    """Serve the interactive visual Chrysalis console dashboard."""
    from pathlib import Path
    dashboard_path = Path(__file__).parent / "static" / "dashboard.html"
    if dashboard_path.exists():
        content = dashboard_path.read_text(encoding="utf-8")
        return Response(content=content, media_type="text/html")
    return Response(content="<h1>Dashboard file not found</h1>", media_type="text/html", status_code=404)


@app.post("/admin/cache/evict")
def admin_cache_evict():
    """Simulate cache memory quota saturation / sudden LRU eviction sweep."""
    purged_count = env.cache.purge()
    return {"status": "EVICTED", "purged_keys_count": purged_count}


@app.post("/admin/db/reboot")
def admin_db_reboot():
    """Simulate database reboot (dangerous action that drops all active connections)."""
    env.db.reboot()
    return {"status": "REBOOTED", "message": "Database connections reset"}


@app.post("/admin/rate_limiter/attach")
def admin_attach_rate_limiter(config: RateLimiterConfig):
    """Attach (or detach, with enabled=false) a token bucket rate limiter on the checkout ingress."""
    # Local import avoids a circular import (dynamic_registry imports this module's `env`).
    from app.adk_agents.dynamic_registry import TokenBucketRateLimiter

    env.rate_limiter = (
        TokenBucketRateLimiter(capacity=config.capacity, replenishment_rate=config.replenishment_rate)
        if config.enabled
        else None
    )
    env.rate_limiter_config = config
    return {"status": "ATTACHED" if config.enabled else "DETACHED", "has_limiter": env.rate_limiter is not None, "config": config}


@app.post("/admin/reset")
def admin_reset():
    """Reset target environment metrics, cache keys, db pool, and active hotpatches to baseline."""
    env.cache.purge()
    env.cache.reset_stats()
    env.db.reboot()
    env.telemetry.reset()
    env.rate_limiter = None
    env.rate_limiter_config = RateLimiterConfig(enabled=False)
    return {
        "status": "RESET_COMPLETE",
        "message": "Target environment, cache, DB pool, telemetry, and rate limiter restored to pristine baseline.",
    }
