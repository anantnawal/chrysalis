"""Tests for the governed APEX pipeline: Binary Authorization signature checks, policy-gated agent
tools, BigQuery engine labelling, and the traffic-shaping policy rollout fallback."""
import asyncio

import pytest

from app.config import PROJECT_ID
from app.adk_agents.code_synthesis import REFERENCE_LIMITER_CODE, compile_in_sandbox
from app.evolution.bigquery_dream_rsi import BigQueryDreamRSIEngine, ENGINE_BIGQUERY, ENGINE_LOCAL
from app.evolution.topology_mutator import apply_policy_via_traffic_agent, set_rate_limit
from app.governance.kms_signer import CloudKmsSigner
from app.target_env.server import platform_env


@pytest.fixture
def attached_limiter():
    limiter = compile_in_sandbox(REFERENCE_LIMITER_CODE)(capacity=10, replenishment_rate=40.0)
    sig = platform_env.kms_signer.sign_artifact(REFERENCE_LIMITER_CODE, artifact_type="DYNAMIC_TOOL")
    platform_env.attach_verified_rate_limiter(limiter, sig, code=REFERENCE_LIMITER_CODE)
    yield limiter
    platform_env.rate_limiter = None
    platform_env.rate_limiter_signature = None


def test_binary_authorization_rejects_code_that_does_not_match_signature():
    signer = CloudKmsSigner(project_id=PROJECT_ID)
    sig = signer.sign_artifact(REFERENCE_LIMITER_CODE, artifact_type="DYNAMIC_TOOL")
    tampered = REFERENCE_LIMITER_CODE + "\n# injected after signing\n"
    limiter = compile_in_sandbox(REFERENCE_LIMITER_CODE)(capacity=10, replenishment_rate=40.0)
    with pytest.raises(PermissionError, match="Binary Authorization"):
        platform_env.attach_verified_rate_limiter(limiter, sig, code=tampered)


def test_set_rate_limit_tool_is_policy_gated(attached_limiter):
    # Below the SLA floor (10 req/s) -> rejected, limiter unchanged
    rejected = set_rate_limit(capacity=8, replenishment_rate=2.0)
    assert rejected["status"] == "POLICY_REJECTED"
    assert attached_limiter.replenishment_rate == 40.0

    applied = set_rate_limit(capacity=8, replenishment_rate=35.0)
    assert applied["status"] == "SUCCESS"
    assert (attached_limiter.capacity, attached_limiter.replenishment_rate) == (8, 35.0)


def test_policy_rollout_falls_back_when_agents_do_not_apply(attached_limiter):
    class SilentSupervisor:
        async def run_directive(self, directive):
            return {"text": "ack", "tool_calls": [], "agents": ["supervisor_router_agent"]}

    result = asyncio.run(apply_policy_via_traffic_agent(SilentSupervisor(), 8, 30.0))
    assert result["source"] == "deterministic_fallback"
    assert result["applied"] is True
    assert result["active_limiter"] == {"capacity": 8, "replenishment_rate": 30.0}


def test_dream_rsi_reports_engine_actually_used():
    engine = BigQueryDreamRSIEngine(project_id=PROJECT_ID)
    engine.load_trajectory_data([])  # synthetic burst
    results, optimal, _ = engine.run_counterfactual_sweep([10.0, 20.0, 40.0], [5, 8, 20])
    expected = ENGINE_BIGQUERY if engine.loaded_to_bigquery else ENGINE_LOCAL
    assert engine.engine == expected
    assert all(r["engine"] == expected for r in results)
    assert optimal["simulated_5xx_count"] == 0
    assert optimal["tested_value"]["capacity"] < 10  # burst tolerance of the 2-slot pool is 10 cold misses


def test_reset_restores_day0_baseline_and_expires_open_tickets(attached_limiter):
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from app.target_env.server import app

    client = TestClient(app)
    store = platform_env.principle_store
    seeded = dict(store.principles)
    learned = store.add_principle("learned during incident", ["reboot_database"], ["token_bucket"], 0.9, "INC-TEST")
    ticket = platform_env.hitl_gate.request_approval("MUTATE_MULTI_AGENT_TOPOLOGY", 2, "test", {})
    platform_env.policy_controller.evaluate_rate_limiter_policy(8, 35.0)
    generation_before = platform_env._generation

    resp = client.post("/admin/reset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["expired_hitl_tickets"] >= 1 and body["forgotten_principles"] >= 1

    assert platform_env.rate_limiter is None and platform_env.rate_limiter_signature is None
    assert dict(store.principles) == seeded and learned.principle_id not in store.principles
    assert platform_env.policy_controller.total_evaluations == 0
    assert [a.name for a in platform_env.supervisor_runner.supervisor_agent.sub_agents] == ["diagnostic_agent"]
    # A ticket raised before the reset can no longer rewire the agent graph
    assert client.post("/api/hitl/approve", json={"request_id": ticket.request_id}).status_code == 404
    # Results computed before the reset are refused
    with pytest.raises(HTTPException) as exc:
        with platform_env._commit(generation_before):
            pass
    assert exc.value.status_code == 409


def test_hitl_ticket_cannot_be_approved_twice_or_after_rejection():
    from app.governance.hitl_gate import HitlApprovalGate

    gate = HitlApprovalGate()
    approved = gate.request_approval("MUTATE_MULTI_AGENT_TOPOLOGY", 2, "t", {})
    gate.approve_request(approved.request_id)
    with pytest.raises(ValueError):
        gate.approve_request(approved.request_id)

    rejected = gate.request_approval("MUTATE_MULTI_AGENT_TOPOLOGY", 2, "t", {})
    gate.reject_request(rejected.request_id, reason="no")
    with pytest.raises(ValueError):
        gate.approve_request(rejected.request_id)
