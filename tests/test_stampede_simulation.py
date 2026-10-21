"""Unit tests verifying cache stampede reproduction and target environment behavior."""
import pytest
import asyncio
from app.target_env.server import env, checkout, CheckoutRequest
from app.target_env.cache_service import CacheService
from app.target_env.db_service import DatabaseService, DatabaseConnectionTimeoutError


@pytest.mark.asyncio
async def test_cache_lru_eviction():
    """Verify that inserting more than CACHE_MAX_KEYS triggers LRU eviction."""
    cache = CacheService(max_keys=3)
    cache.set("key1", "val1")
    cache.set("key2", "val2")
    cache.set("key3", "val3")
    assert cache.get_stats()["active_keys"] == 3

    # Add 4th key: key1 should be LRU evicted
    cache.set("key4", "val4")
    stats = cache.get_stats()
    assert stats["active_keys"] == 3
    assert stats["eviction_count"] == 1
    assert cache.get("key1") is None
    assert cache.get("key4") == "val4"


@pytest.mark.asyncio
async def test_database_semaphore_starvation():
    """Verify that concurrent requests exceeding pool size N=2 experience timeouts."""
    db = DatabaseService(max_connections=2, query_delay_sec=0.15, acquisition_timeout_sec=0.1)

    async def run_query(cid):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, db.query_cart, cid)

    # 4 concurrent queries when timeout is 0.1s and query takes 0.15s:
    # First 2 acquire semaphore immediately.
    # 3rd and 4th wait, but timeout after 0.1s before slots free up!
    results = await asyncio.gather(
        run_query("cart_101"),
        run_query("cart_102"),
        run_query("cart_103"),
        run_query("cart_104"),
        return_exceptions=True,
    )

    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) > 0
    assert any(isinstance(e, DatabaseConnectionTimeoutError) for e in exceptions)


@pytest.mark.asyncio
async def test_stampede_checkout_burst():
    """Verify that a cold cache burst generates HTTP 500 errors due to DB pool exhaustion."""
    env.rate_limiter = None
    env.cache.purge()

    tasks = [
        checkout(CheckoutRequest(cart_id=f"cold_cart_{i % 10}"))
        for i in range(25)
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    http_500_count = sum(
        1 for r in responses
        if (hasattr(r, "status_code") and r.status_code >= 500)
        or (isinstance(r, dict) and r.get("status") == "ERROR")
    )
    assert http_500_count > 0, "Expected cache stampede to cause database timeouts under concurrent load"
