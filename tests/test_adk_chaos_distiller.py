"""Unit tests verifying CuriosityChaosAgent and PrincipleDistillerAgent as native Google ADK agents."""
import pytest
from app.evolution.principle_store import SemanticPrincipleStore
from app.adk_agents.distiller_agent import ChrysalisDistillerAgentRunner
from app.adk_agents.chaos_agent import ChrysalisChaosAgentRunner
from app.adk_agents.schemas import StepCreditAttribution
from app.config import MODEL_NAME


@pytest.mark.asyncio
async def test_adk_principle_distiller_agent_execution():
    """Verify that PrincipleDistillerAgent runs via ADK Runner and invokes publish_operational_principle."""
    store = SemanticPrincipleStore()
    distiller_runner = ChrysalisDistillerAgentRunner(principle_store=store, model_name=MODEL_NAME)

    attrs = [
        StepCreditAttribution(
            span_id="s1", tool_name="reboot_database", action_type="reboot",
            delta_latency=-1500.0, delta_5xx_rate=-0.3, delta_pool_pressure=-1.0,
            attribution_score=-0.49, rationale="Database restarted while connections saturated"
        ),
        StepCreditAttribution(
            span_id="s2", tool_name="token_bucket_patch", action_type="rate_limit",
            delta_latency=1200.0, delta_5xx_rate=0.35, delta_pool_pressure=0.8,
            attribution_score=0.94, rationale="Throttled excess requests and restored availability"
        )
    ]

    result = await distiller_runner.distill("INC-UNIT-TEST", attrs)
    assert result["status"] == "DISTILLATION_COMPLETE"
    assert len(result["tool_calls"]) > 0
    assert any(c["name"] == "publish_operational_principle" for c in result["tool_calls"])
    assert result["principle"] is not None
    assert len(store.principles) >= 3


@pytest.mark.asyncio
async def test_adk_curiosity_chaos_agent_tool_loop():
    """Verify that CuriosityChaosAgent executes autonomous tool calls across shadow sandbox."""
    chaos_runner = ChrysalisChaosAgentRunner(model_name=MODEL_NAME, tested_capacity=10, tested_rate=40.0)

    directive = (
        "Red Team mission: purge shadow cache, execute a 30-request burst, and assert system invariant."
    )
    result = await chaos_runner.run_chaos_probe(directive)

    assert result["status"] == "PROBE_COMPLETE"
    assert len(result["tool_calls"]) >= 2
    tool_names = [c["name"] for c in result["tool_calls"]]
    assert "fire_shadow_concurrent_burst" in tool_names or "inject_shadow_cache_purge" in tool_names
    assert result["verdict"] in ["VERIFIED_RESILIENT", "INVARIANT_VIOLATED"]
