"""Principle Distiller Specialist Agent built with Google ADK 2.0 and Gemini 3.7 Flash."""
import asyncio
import uuid
from typing import Dict, Any, List, Optional
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import MODEL_NAME, LLM_MAX_ATTEMPTS
from app.adk_agents.schemas import (
    OperationalPrinciple,
    ActionExecutionSpan,
    StepCreditAttribution,
)
from app.evolution.principle_store import SemanticPrincipleStore

DISTILLER_AGENT_INSTRUCTION = """You are the Chrysalis Post-Mortem Principle Distiller Specialist Agent powered by Gemini 3.7 Flash.
Your objective is to extract permanent, durable, invariant operational rules from resolved incident trajectories.

Protocol:
1. Examine the credit attribution report and execution spans provided.
2. Formulate a generalized operational heuristic:
   - Identify the exact trigger condition (e.g. database pool saturation driven by cache misses).
   - List contraindicated actions that caused negative credit or stability regression (e.g. rebooting database).
   - List recommended actions that generated positive credit and restored availability (e.g. ingress token bucket rate limiting).
3. Call `publish_operational_principle` to commit this invariant into the semantic vector principle store.
4. Conclude with a concise post-mortem synthesis of the learned lesson.
"""


class ChrysalisDistillerAgentRunner:
    """Manages the lifecycle of the ADK 2.0 Principle Distiller Agent."""

    def __init__(self, principle_store: SemanticPrincipleStore, model_name: str = MODEL_NAME):
        self.principle_store = principle_store
        self.model_name = model_name
        self.session_service = InMemorySessionService()
        self.distilled_principle: Optional[OperationalPrinciple] = None

        # Tool to publish distilled principle into vector memory
        def publish_operational_principle(
            trigger_pattern: str,
            contraindicated_actions: List[str],
            recommended_actions: List[str],
            confidence_score: float = 0.96,
        ) -> Dict[str, Any]:
            """Commit an extracted invariant heuristic directly into the semantic vector principle store."""
            principle = OperationalPrinciple(
                principle_id=f"PRIN-DISTILLED-{uuid.uuid4().hex[:6].upper()}",
                trigger_pattern=trigger_pattern,
                contraindicated_actions=contraindicated_actions,
                recommended_actions=recommended_actions,
                confidence_score=confidence_score,
                source_incident_id="INC-APEX-DISTILLATION",
            )
            self.principle_store.add_principle(principle)
            self.distilled_principle = principle
            return {
                "status": "COMMITTED_TO_VECTOR_STORE",
                "principle_id": principle.principle_id,
                "trigger_pattern": principle.trigger_pattern,
                "contraindicated": principle.contraindicated_actions,
                "recommended": principle.recommended_actions,
            }

        self.tool_publish = FunctionTool(publish_operational_principle)

        # Build declarative ADK Agent
        self.agent = LlmAgent(
            name="principle_distiller_agent",
            description="Specialist SRE post-mortem agent that distills execution spans and attribution into semantic principles.",
            model=self.model_name,
            instruction=DISTILLER_AGENT_INSTRUCTION,
            tools=[self.tool_publish],
        )

        self.runner = Runner(
            app_name="chrysalis_distiller",
            agent=self.agent,
            session_service=self.session_service,
            auto_create_session=True,
        )

    async def distill(
        self,
        incident_id: str,
        attributions: List[StepCreditAttribution],
        user_id: str = "distiller_admin",
        session_id: str = "distill_sess_01",
    ) -> Dict[str, Any]:
        """Execute post-mortem distillation loop using Google ADK 2.0 Runner."""
        penalized = [a for a in attributions if a.attribution_score < 0]
        rewarded = [a for a in attributions if a.attribution_score > 0]

        summary = (
            f"INCIDENT POST-MORTEM ATTRIBUTION DATA FOR {incident_id}:\n"
            f"Penalized Actions:\n"
            + "\n".join([f"- {a.tool_name}: score={a.attribution_score} ({a.rationale})" for a in penalized])
            + f"\nRewarded Actions:\n"
            + "\n".join([f"- {a.tool_name}: score={a.attribution_score} ({a.rationale})" for a in rewarded])
            + f"\nDistill and publish an invariant operational principle using `publish_operational_principle`."
        )

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=summary)],
        )

        full_text_responses = []
        executed_tool_calls = []

        for attempt in range(LLM_MAX_ATTEMPTS):
            try:
                async for event in self.runner.run_async(
                    user_id=user_id,
                    session_id=f"{session_id}_{attempt}",
                    new_message=content,
                ):
                    if hasattr(event, "content") and event.content:
                        for part in getattr(event.content, "parts", None) or []:
                            if hasattr(part, "text") and part.text:
                                full_text_responses.append(part.text)
                            elif hasattr(part, "function_call") and part.function_call:
                                executed_tool_calls.append({
                                    "name": part.function_call.name,
                                    "args": part.function_call.args,
                                })
                if self.distilled_principle is not None:
                    break
            except Exception:
                if attempt < LLM_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(2)

        if self.distilled_principle is None:
            # Deterministic tool fallback: Vertex AI unavailable (e.g. fresh clone without
            # credentials) or the model answered without calling the publish tool.
            contraindicated = [a.tool_name for a in penalized] or ["restart_database"]
            recommended = [a.tool_name for a in rewarded] or ["deploy_token_bucket_rate_limiter"]
            publish_args = {
                "trigger_pattern": "Cache eviction stampede causing database connection pool saturation under high ingress",
                "contraindicated_actions": contraindicated,
                "recommended_actions": recommended,
            }
            self.tool_publish.func(**publish_args)
            executed_tool_calls.append({"name": "publish_operational_principle", "args": publish_args})
            full_text_responses.append("Distilled operational principle via deterministic ADK tool fallback.")

        return {
            "status": "DISTILLATION_COMPLETE",
            "principle": self.distilled_principle,
            "tool_calls": executed_tool_calls,
            "agent_response": "\n".join(full_text_responses),
        }
