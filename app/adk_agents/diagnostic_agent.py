"""Diagnostic SRE Specialist Agent built with Google ADK 2.0 and Gemini."""
from google.adk.agents import LlmAgent
from app.config import MODEL_NAME
from app.adk_agents.tools_library import (
    tool_inspect_cache,
    tool_inspect_db_pool,
    tool_read_metrics,
    tool_retrieve_principles,
)

DIAGNOSTIC_INSTRUCTION = """You are the Chrysalis Diagnostic SRE Specialist Agent powered by Gemini.
Your primary role is to diagnose production anomalies, pinpoint root causes, and verify operational guardrails.

When diagnosing an incident:
1. Call `read_system_metrics` to examine P99 latency and 5xx error rates.
2. Call `inspect_cache_status` to detect key evictions or cache churn.
3. Call `inspect_db_pool` to evaluate connection pool saturation and thread starvation.
4. Call `retrieve_historical_principles` using Self-Navigating memory to query prior incident lessons.
5. If database pool exhaustion is correlated with cache misses/evictions, check if restarting the database is contraindicated.
6. Provide a concise, structured root cause report:
   - Root Cause: (e.g. Cache Stampede overloading DB connection pool)
   - Status: CRITICAL
   - Contraindicated Actions: (explicitly state what NOT to do based on Self-Navigating memory)
   - Recommended Mitigation: (e.g. Ingress rate-limiting / Token Bucket patch)
"""


def create_diagnostic_agent() -> LlmAgent:
    """Instantiate the Diagnostic SRE Specialist Agent."""
    return LlmAgent(
        name="diagnostic_agent",
        description="Specialist SRE agent that inspects cache hit ratios, DB connection starvation, and retrieves Self-Navigating principles.",
        model=MODEL_NAME,
        instruction=DIAGNOSTIC_INSTRUCTION,
        tools=[
            tool_read_metrics,
            tool_inspect_cache,
            tool_inspect_db_pool,
            tool_retrieve_principles,
        ],
    )
