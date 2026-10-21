"""AgentEvolver Self-Questioning Curiosity Engine & Shadow Chaos Sandbox."""
import asyncio
import json
import time
import httpx
from typing import Dict, Any, List
from google import genai
from app.config import MODEL_NAME
from app.target_env.cache_service import CacheService
from app.target_env.db_service import DatabaseService, DatabaseConnectionTimeoutError
from app.target_env.telemetry import TelemetryCollector
from app.adk_agents.dynamic_registry import TokenBucketRateLimiter


class ShadowSandboxEnvironment:
    """Isolated shadow sandbox for safe synthetic fault injection and boundary probing."""

    def __init__(self, capacity: int = 42, replenishment_rate: float = 40.0):
        self.cache = CacheService(max_keys=3)  # halving cache capacity to probe boundary
        self.db = DatabaseService()
        self.telemetry = TelemetryCollector(cache_service=self.cache, db_service=self.db)
        # Apply evolved traffic shaping policy
        self.rate_limiter = TokenBucketRateLimiter(capacity=capacity, replenishment_rate=replenishment_rate)

    async def execute_request(self, cart_id: str) -> Dict[str, Any]:
        """Simulate single request through the shadow sandbox pipeline."""
        start = time.perf_counter()

        # Check rate limiter
        admitted = self.rate_limiter.acquire(1)
        if not admitted:
            lat = (time.perf_counter() - start) * 1000.0
            self.telemetry.record_request("shadow_req", "/checkout", 429, lat, False, admitted=False)
            return {"status_code": 429, "latency_ms": lat}

        # Cache check
        item = self.cache.get(cart_id)
        if item is None:
            loop = asyncio.get_running_loop()
            try:
                db_res = await loop.run_in_executor(None, self.db.query_cart, cart_id)
                self.cache.set(cart_id, json.dumps(db_res))
                status = 200
            except DatabaseConnectionTimeoutError:
                status = 500
            except Exception:
                status = 500
        else:
            status = 200

        lat = (time.perf_counter() - start) * 1000.0
        self.telemetry.record_request("shadow_req", "/checkout", status, lat, item is None, admitted=True)
        return {"status_code": status, "latency_ms": lat}


class SelfQuestioningEngine:
    """Proactive curiosity prober generating synthetic edge-case hypotheses via Gemini."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = genai.Client()
        return self._client

    def generate_curiosity_hypothesis(self, incident_context: str) -> Dict[str, Any]:
        """Prompt Gemini to synthesize a challenging 'What-If?' edge-case stress scenario."""
        prompt = f"""You are the AgentEvolver Self-Questioning Curiosity Engine.
Given that the incident was mitigated by APEX and re-wired with a TrafficShapingAgent:
Context: {incident_context}

Formulate a proactive, edge-case chaos stress hypothesis to probe system boundaries in a shadow sandbox.
Return ONLY valid JSON with this format:
{{
  "hypothesis": "What if cache memory is reduced by 50% and a sudden 60-request burst arrives simultaneously?",
  "probe_type": "SYNTHETIC_CACHE_DROP_BURST",
  "concurrent_burst_size": 50,
  "cache_purge_before_burst": true,
  "expected_invariant": "Zero HTTP 500 errors and database pool utilization below 85%"
}}
"""
        try:
            client = self._get_client()
            resp = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            raw = resp.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            return {
                "hypothesis": "What if cache memory is halved and 50 concurrent requests arrive during key eviction?",
                "probe_type": "SYNTHETIC_CACHE_DROP_BURST",
                "concurrent_burst_size": 50,
                "cache_purge_before_burst": True,
                "expected_invariant": "Zero HTTP 500 errors; DB connection pool protected by evolved TrafficShapingAgent.",
            }

    async def run_shadow_chaos_probe(
        self,
        hypothesis: Dict[str, Any],
        tested_capacity: int = 42,
        tested_rate: float = 40.0,
    ) -> Dict[str, Any]:
        """Execute the synthetic edge case in the isolated shadow sandbox and verify invariant."""
        sandbox = ShadowSandboxEnvironment(capacity=tested_capacity, replenishment_rate=tested_rate)

        # 1. Fault injection: Purge cache before the burst
        if hypothesis.get("cache_purge_before_burst", True):
            sandbox.cache.purge()

        burst_size = hypothesis.get("concurrent_burst_size", 50)

        # 2. Fire concurrent burst requests
        tasks = [
            sandbox.execute_request(cart_id=f"cart_{100 + (i % 8)}")
            for i in range(burst_size)
        ]
        results = await asyncio.gather(*tasks)

        # 3. Analyze verification metrics
        http_200_count = sum(1 for r in results if r["status_code"] == 200)
        http_429_count = sum(1 for r in results if r["status_code"] == 429)
        http_500_count = sum(1 for r in results if r["status_code"] == 500)

        metrics = sandbox.telemetry.get_current_metrics()
        invariant_passed = (http_500_count == 0)

        return {
            "hypothesis": hypothesis.get("hypothesis"),
            "burst_size": burst_size,
            "http_200_admitted": http_200_count,
            "http_429_throttled": http_429_count,
            "http_500_errors": http_500_count,
            "p99_latency_ms": metrics.p99_latency_ms,
            "db_pool_utilization": metrics.db_pool_utilization,
            "invariant_verified": invariant_passed,
            "verdict": "VERIFIED_RESILIENT" if invariant_passed else "INVARIANT_VIOLATED",
        }
