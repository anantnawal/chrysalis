"""Unit tests for APEX Layer 1 Gemini code synthesis gates (sandbox policy, restricted compile, behaviour)."""
import pytest

from app.adk_agents.code_synthesis import (
    REFERENCE_LIMITER_CODE,
    compile_in_sandbox,
    run_gates,
    sandbox_violations,
    synthesize_rate_limiter,
)


@pytest.mark.parametrize(
    "snippet, expected",
    [
        ("import os\n", "Import not in allow-list: os"),
        ("import subprocess\n", "Import not in allow-list: subprocess"),
        ("from socket import socket\n", "Import not in allow-list: socket"),
        ("x = open('/etc/passwd')\n", "Forbidden builtin/name: open"),
        ("x = getattr(object, 'mro')\n", "Forbidden builtin/name: getattr"),
        ("x = ().__class__.__bases__\n", "Dunder attribute access not allowed: __class__"),
        ("def f():\n    global y\n", "global/nonlocal statements are not allowed"),
    ],
)
def test_sandbox_policy_rejects_dangerous_constructs(snippet, expected):
    assert expected in sandbox_violations(snippet)


def test_restricted_namespace_blocks_unlisted_imports_at_runtime():
    # Even if static checks were bypassed, the guarded __import__ refuses non-allow-listed modules.
    with pytest.raises(ImportError):
        compile_in_sandbox("import json\n")


def test_reference_template_passes_all_gates():
    cls, failures = run_gates(REFERENCE_LIMITER_CODE)
    assert failures == []
    limiter = cls(capacity=2, replenishment_rate=0.001)
    assert [limiter.acquire(), limiter.acquire(), limiter.acquire()] == [True, True, False]


def test_behavioural_gate_rejects_limiter_that_never_throttles():
    broken = REFERENCE_LIMITER_CODE.replace("if self.tokens >= tokens:", "if True:")
    cls, failures = run_gates(broken)
    assert cls is None
    assert any("burst capacity check failed" in f for f in failures)


def test_gate_rejects_limiter_without_lock():
    unlocked = REFERENCE_LIMITER_CODE.replace("self.lock = threading.Lock()", "self.lock = None").replace(
        "with self.lock:", "if True:"
    )
    cls, failures = run_gates(unlocked)
    assert cls is None
    assert any("thread-safety contract" in f for f in failures)


def test_synthesis_offline_falls_back_to_verified_reference_template():
    result = synthesize_rate_limiter("cache stampede", "gemini-3.7-flash", llm_available=False)
    assert result.source == "reference_template"
    assert result.code == REFERENCE_LIMITER_CODE
    assert result.limiter_cls is not None
    assert any("reference template" in g for g in result.gate_log)
