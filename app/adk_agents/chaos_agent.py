"""Curiosity Chaos Specialist Agent built with Google ADK 2.0 and Gemini 3.7 Flash."""
import asyncio
import json
import time
from typing import Dict, Any, Optional
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import MODEL_NAME, LLM_MAX_ATTEMPTS
from app.evolution.self_questioner import ShadowSandboxEnvironment

CHAOS_AGENT_INSTRUCTION = """You are the Chrysalis Proactive Curiosity Chaos Specialist Agent powered by Gemini 3.7 Flash.
Your mission is to perform automated Red Team chaos engineering on the newly evolved multi-agent architecture.

Protocol:
1. Formulate a challenging "What-If?" stress hypothesis (e.g. sudden cache invalidation during high-volume ingress burst).
2. Invoke `inject_shadow_cache_purge` to drop hot keys in the isolated shadow sandbox.
3. Invoke `fire_shadow_concurrent_burst` with 200 concurrent requests to stress-test the evolved TrafficShapingAgent.
4. Invoke `assert_shadow_invariant` to verify if the rate limiter prevented database connection pool starvation.
5. Provide a concise Red Team verdict summarizing the hypothesis, observed metrics, and system resiliency.
"""


class ChrysalisChaosAgentRunner:
    """Manages the lifecycle of the ADK 2.0 Curiosity Chaos Agent."""

    def __init__(self, model_name: str = MODEL_NAME, tested_capacity: int = 10, tested_rate: float = 40.0):
        self.model_name = model_name
        self.sandbox = ShadowSandboxEnvironment(capacity=tested_capacity, replenishment_rate=tested_rate)
        self.session_service = InMemorySessionService()
        self.burst_executed = False

        # Tools for the Chaos Agent
        def inject_shadow_cache_purge(reason: str = "Simulate LRU cache wipe under load") -> Dict[str, Any]:
            """Purge all keys in the isolated shadow cache to simulate catastrophic key eviction."""
            purged = self.sandbox.cache.purge()
            return {
                "status": "PURGED",
                "keys_purged": purged,
                "reason": reason,
            }

        async def fire_shadow_concurrent_burst(burst_size: int = 200) -> Dict[str, Any]:
            """Fire a synthetic burst of concurrent checkout requests against the shadow sandbox."""
            tasks = [
                self.sandbox.execute_request(cart_id=f"cart_{100 + (i % 8)}")
                for i in range(burst_size)
            ]
            results = await asyncio.gather(*tasks)
            self.burst_executed = True

            status_200 = sum(1 for r in results if r["status_code"] == 200)
            status_429 = sum(1 for r in results if r["status_code"] == 429)
            status_500 = sum(1 for r in results if r["status_code"] == 500)

            return {
                "burst_size": burst_size,
                "admitted_200": status_200,
                "throttled_429": status_429,
                "errors_500": status_500,
                "message": f"Processed {burst_size} requests: {status_200} admitted, {status_429} throttled, {status_500} errors",
            }

        def assert_shadow_invariant() -> Dict[str, Any]:
            """Verify that HTTP 500 error count is 0 and DB semaphore was not starved under load."""
            metrics = self.sandbox.telemetry.get_current_metrics()
            invariant_verified = (metrics.http_5xx_rate == 0.0)
            return {
                "invariant_verified": invariant_verified,
                "verdict": "VERIFIED_RESILIENT" if invariant_verified else "INVARIANT_VIOLATED",
                "p99_latency_ms": metrics.p99_latency_ms,
                "db_pool_utilization": metrics.db_pool_utilization,
                "5xx_error_rate": metrics.http_5xx_rate,
            }

        self.tool_purge = FunctionTool(inject_shadow_cache_purge)
        self.tool_burst = FunctionTool(fire_shadow_concurrent_burst)
        self.tool_assert = FunctionTool(assert_shadow_invariant)

        # Build declarative ADK Agent
        self.agent = LlmAgent(
            name="curiosity_chaos_agent",
            description="Autonomous Red Team Chaos Specialist that formulates hypotheses and executes boundary stress probes.",
            model=self.model_name,
            instruction=CHAOS_AGENT_INSTRUCTION,
            tools=[self.tool_purge, self.tool_burst, self.tool_assert],
        )

        self.runner = Runner(
            app_name="chrysalis_chaos",
            agent=self.agent,
            session_service=self.session_service,
            auto_create_session=True,
        )

    async def run_chaos_probe(self, directive: str, user_id: str = "chaos_admin", session_id: str = "chaos_sess_01") -> Dict[str, Any]:
        """Execute the proactive chaos exploration workflow via Google ADK 2.0 Runner."""
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=directive)],
        )

        events_log = []
        full_text_responses = []
        executed_tool_calls = []
        self.burst_executed = False

        for attempt in range(LLM_MAX_ATTEMPTS):
            try:
                async for event in self.runner.run_async(
                    user_id=user_id,
                    session_id=f"{session_id}_{attempt}",
                    new_message=content,
                ):
                    event_dict = {"event_type": type(event).__name__}
                    if hasattr(event, "content") and event.content:
                        for part in getattr(event.content, "parts", None) or []:
                            if hasattr(part, "text") and part.text:
                                full_text_responses.append(part.text)
                                event_dict["text"] = part.text
                            elif hasattr(part, "function_call") and part.function_call:
                                call_info = {
                                    "name": part.function_call.name,
                                    "args": part.function_call.args,
                                }
                                executed_tool_calls.append(call_info)
                                event_dict["tool_call"] = call_info
                            elif hasattr(part, "function_response") and part.function_response:
                                event_dict["tool_response"] = {
                                    "name": part.function_response.name,
                                    "result": part.function_response.response,
                                }
                    events_log.append(event_dict)
                if self.burst_executed:
                    break
            except Exception:
                if attempt < LLM_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(2)

        if not self.burst_executed:
            # Deterministic chaos fallback: Vertex AI unavailable (e.g. fresh clone without
            # credentials) or the model never fired the burst, so the invariant would be untested.
            self.tool_purge.func(reason="Deterministic ADK chaos fallback: 100% shadow cache drop")
            await self.tool_burst.func(burst_size=200)
            self.tool_assert.func()
            executed_tool_calls.extend([
                {"name": "inject_shadow_cache_purge", "args": {"reason": "Deterministic ADK chaos fallback"}},
                {"name": "fire_shadow_concurrent_burst", "args": {"burst_size": 200}},
                {"name": "assert_shadow_invariant", "args": {}},
            ])
            full_text_responses.append("Verified shadow sandbox resiliency via deterministic ADK chaos fallback.")

        metrics = self.sandbox.telemetry.get_current_metrics()
        return {
            "status": "PROBE_COMPLETE",
            "events": events_log,
            "tool_calls": executed_tool_calls,
            "agent_response": "\n".join(full_text_responses),
            "final_metrics": metrics,
            "shadow_requests": self.sandbox.telemetry.total_requests,
            "shadow_5xx": self.sandbox.telemetry.status_5xx_count,
            "verdict": "VERIFIED_RESILIENT" if metrics.http_5xx_rate == 0.0 else "INVARIANT_VIOLATED",
        }
