"""Supervisor Router Agent built with Google ADK 2.0 and Gemini."""
import asyncio
import uuid
from typing import Optional, List, Dict, Any
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import MODEL_NAME, LLM_MAX_ATTEMPTS
from app.adk_agents.diagnostic_agent import create_diagnostic_agent
from app.adk_agents.tools_library import tool_read_metrics, tool_retrieve_principles

SUPERVISOR_INSTRUCTION = """You are the Chrysalis Root SRE Supervisor Agent powered by Gemini.
You orchestrate the autonomous incident response lifecycle for the production infrastructure.

Operational Protocol:
1. When an incident alert arrives, delegate comprehensive triage to `diagnostic_agent`.
2. Review the diagnostic findings and check Self-Navigating operational principles.
3. If the diagnostic indicates a Cache Stampede with DB pool starvation:
   - Enforce the guardrail: NEVER reboot the database during active connection saturation.
   - Note that an APEX Layer 1 dynamic tool patch (TokenBucketRateLimiter) is required to throttle ingress and relieve thread starvation.
4. Conclude your assessment with an actionable remediation strategy.
"""


class ChrysalisSupervisor:
    """Manages the Google ADK 2.0 multi-agent hierarchy and execution lifecycle."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.diagnostic_agent = create_diagnostic_agent()
        self.session_service = InMemorySessionService()

        # Build supervisor agent
        self.supervisor_agent = LlmAgent(
            name="supervisor_agent",
            description="Root SRE supervisor responsible for high-level incident triage, sub-agent delegation, and guardrail verification.",
            model=self.model_name,
            instruction=SUPERVISOR_INSTRUCTION,
            sub_agents=[self.diagnostic_agent],
            tools=[tool_read_metrics, tool_retrieve_principles],
        )

        self.runner = Runner(
            app_name="chrysalis",
            agent=self.supervisor_agent,
            session_service=self.session_service,
            auto_create_session=True,
        )

    async def run_triage(self, incident_alert: str, user_id: str = "sre_admin", session_id: str = "inc_sess_01") -> Dict[str, Any]:
        """Execute multi-agent triage loop across supervisor and diagnostic sub-agent."""
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=incident_alert)],
        )

        last_error = "Vertex AI credentials not configured (offline mode)"
        for attempt in range(LLM_MAX_ATTEMPTS):
            try:
                events_log = []
                full_text_responses = []

                async for event in self.runner.run_async(
                    user_id=user_id,
                    session_id=f"{session_id}_{uuid.uuid4().hex[:6]}_{attempt}",
                    new_message=content,
                ):
                    event_dict = {"event_type": type(event).__name__}
                    if hasattr(event, "content") and event.content:
                        for part in getattr(event.content, "parts", None) or []:
                            if hasattr(part, "text") and part.text:
                                full_text_responses.append(part.text)
                                event_dict["text"] = part.text
                            elif hasattr(part, "function_call") and part.function_call:
                                event_dict["tool_call"] = {
                                    "name": part.function_call.name,
                                    "args": part.function_call.args,
                                }
                            elif hasattr(part, "function_response") and part.function_response:
                                event_dict["tool_response"] = {
                                    "name": part.function_response.name,
                                    "result": part.function_response.response,
                                }
                    events_log.append(event_dict)

                combined_text = "\n".join(full_text_responses)
                return {
                    "status": "TRIAGE_COMPLETE",
                    "events": events_log,
                    "agent_response": combined_text,
                }
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt < LLM_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(2)

        # Graceful deterministic fallback (e.g. fresh clone without Vertex AI credentials)
        return {
            "status": "TRIAGE_FALLBACK",
            "events": [{"event_type": "fallback", "error": last_error}],
            "agent_response": (
                "# SRE Diagnostic Report (Deterministic ADK Fallback - Vertex AI unavailable)\n"
                "- **Root Cause:** Cache eviction stampede exhausting the DB connection pool (2/2 active).\n"
                "- **Status:** CRITICAL\n"
                "- **Contraindicated Actions:** `restart_database`, `flush_db_connections` (PRIN-HIST-001).\n"
                "- **Recommended Mitigation:** Synthesize APEX Layer 1 `TokenBucketRateLimiter` at ingress."
            ),
        }

    async def run_directive(self, directive: str, user_id: str = "sre_admin") -> Dict[str, Any]:
        """Send an operational directive through the (possibly evolved) multi-agent graph.

        Returns the participating agents, executed tool calls and text. Retries until a tool is called.
        """
        content = types.Content(role="user", parts=[types.Part.from_text(text=directive)])
        trace: Dict[str, Any] = {"text": "", "tool_calls": [], "agents": []}
        for attempt in range(LLM_MAX_ATTEMPTS):
            attempt_trace: Dict[str, Any] = {"text": "", "tool_calls": [], "agents": []}
            try:
                async for event in self.runner.run_async(
                    user_id=user_id,
                    session_id=f"directive_{uuid.uuid4().hex[:8]}",
                    new_message=content,
                ):
                    author = getattr(event, "author", None)
                    if author and author != "user" and author not in attempt_trace["agents"]:
                        attempt_trace["agents"].append(author)
                    if hasattr(event, "content") and event.content:
                        for part in getattr(event.content, "parts", None) or []:
                            if hasattr(part, "text") and part.text:
                                attempt_trace["text"] += part.text
                            elif hasattr(part, "function_call") and part.function_call:
                                attempt_trace["tool_calls"].append({
                                    "agent": author,
                                    "name": part.function_call.name,
                                    "args": dict(part.function_call.args or {}),
                                })
                trace = attempt_trace
                if attempt_trace["tool_calls"]:
                    break
            except Exception:
                if attempt < LLM_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(2)
        return trace
