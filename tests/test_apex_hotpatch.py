"""Unit tests verifying APEX Layer 1 dynamic tool generation, AST safety, and execution."""
import pytest
from google.adk.agents import LlmAgent
from app.adk_agents.dynamic_registry import (
    validate_code_safety,
    ASTSafetyViolation,
    register_dynamic_tool,
    TokenBucketRateLimiter,
)
from app.target_env.server import env


def test_ast_safety_checker_blocks_malicious_code():
    """Verify that dangerous imports and system calls are rejected by AST validator."""
    malicious_snippets = [
        "import os\nos.system('rm -rf /')",
        "import subprocess\nsubprocess.run(['ls'])",
        "import sys\nsys.exit(1)",
        "eval('1 + 1')",
        "from shutil import rmtree",
    ]
    for code in malicious_snippets:
        with pytest.raises(ASTSafetyViolation):
            validate_code_safety(code)


def test_ast_safety_checker_allows_safe_code():
    """Verify that legitimate traffic shaping and math code passes AST validator."""
    safe_code = """
import time
import threading

class SafeLimiter:
    def __init__(self, capacity: int = 10):
        self.capacity = capacity
        self.lock = threading.Lock()
    def check(self):
        return True
"""
    # Should not raise exception
    validate_code_safety(safe_code)


def test_token_bucket_rate_limiter_logic():
    """Verify that TokenBucketRateLimiter admits up to capacity and throttles excess."""
    limiter = TokenBucketRateLimiter(capacity=3, replenishment_rate=1.0)
    assert limiter.acquire(1) is True
    assert limiter.acquire(1) is True
    assert limiter.acquire(1) is True
    # 4th request must be throttled
    assert limiter.acquire(1) is False
    stats = limiter.get_stats()
    assert stats["total_admitted"] == 3
    assert stats["total_throttled"] == 1


def test_dynamic_tool_registration():
    """Verify dynamic compilation, ADK FunctionTool wrapping, and live agent attachment."""
    agent = LlmAgent(
        name="test_supervisor",
        model="gemini-2.5-flash",
        instruction="Supervisor test",
        tools=[],
    )
    code = """
class TokenBucketRateLimiter:
    def __init__(self, capacity: int = 20, replenishment_rate: float = 30.0):
        self.capacity = capacity
        self.replenishment_rate = replenishment_rate
    def acquire(self, tokens: int = 1):
        return True
    def get_stats(self):
        return {"capacity": self.capacity}
"""
    tool_def, dynamic_tool = register_dynamic_tool(agent, code, target_env=env)

    assert tool_def.tool_name == "token_bucket_rate_limiter"
    assert len(agent.tools) == 1
    assert dynamic_tool.name == "configure_rate_limiter"
    assert env.rate_limiter is not None
