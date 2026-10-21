"""APEX Layer 1 Dynamic Tool Loader: AST safety validation, runtime compilation, and ADK tool injection."""
import ast
import hashlib
import time
import threading
from typing import Dict, Any, Tuple
from google.adk.tools import FunctionTool
from app.adk_agents.schemas import DynamicToolDefinition, utc_now
from app.adk_agents.code_synthesis import sandbox_violations, compile_in_sandbox
from app.target_env.server import env

DISALLOWED_MODULES = {
    "os", "sys", "subprocess", "shutil", "builtins.eval",
    "builtins.exec", "socket", "pty", "posix",
}

DISALLOWED_CALLS = {
    "eval", "exec", "__import__", "compile", "breakpoint",
}


class ASTSafetyViolation(Exception):
    """Raised when generated tool code violates safety policy."""
    pass


class ASTSafetyChecker(ast.NodeVisitor):
    """Validates AST nodes against security constraints."""

    def __init__(self):
        self.errors = []

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in DISALLOWED_MODULES:
                self.errors.append(f"Disallowed import: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in DISALLOWED_MODULES:
            self.errors.append(f"Disallowed from-import: {node.module}")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_CALLS:
            self.errors.append(f"Disallowed function call: {node.func.id}")
        self.generic_visit(node)


def validate_code_safety(code_str: str) -> None:
    """Parse and assert AST safety of generated tool code."""
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        raise ASTSafetyViolation(f"Generated tool has syntax errors: {e}")

    checker = ASTSafetyChecker()
    checker.visit(tree)
    errors = list(checker.errors)
    # Strict sandbox policy (import allow-list, forbidden builtins, no dunder access)
    errors += [v for v in sandbox_violations(code_str) if v not in errors]
    if errors:
        raise ASTSafetyViolation("; ".join(errors))


class TokenBucketRateLimiter:
    """In-memory thread-safe token bucket rate limiter for traffic shaping."""

    def __init__(self, capacity: int = 50, replenishment_rate: float = 40.0):
        self.capacity = capacity
        self.replenishment_rate = replenishment_rate  # tokens per sec
        self.tokens = float(capacity)
        self.last_update = time.perf_counter()
        self.lock = threading.Lock()
        self.total_throttled = 0
        self.total_admitted = 0

    def acquire(self, tokens: int = 1) -> bool:
        """Attempt to acquire tokens; refills tokens according to elapsed time."""
        with self.lock:
            now = time.perf_counter()
            elapsed = now - self.last_update
            self.last_update = now

            # Replenish
            self.tokens = min(float(self.capacity), self.tokens + (elapsed * self.replenishment_rate))

            if self.tokens >= tokens:
                self.tokens -= tokens
                self.total_admitted += 1
                return True
            else:
                self.total_throttled += 1
                return False

    def get_stats(self) -> Dict[str, Any]:
        """Return rate limiter statistics."""
        with self.lock:
            return {
                "capacity": self.capacity,
                "replenishment_rate": self.replenishment_rate,
                "current_tokens": round(self.tokens, 2),
                "total_admitted": self.total_admitted,
                "total_throttled": self.total_throttled,
            }


def register_dynamic_tool(
    agent,
    code_string: str,
    tool_name: str = "token_bucket_rate_limiter",
    description: str = "Dynamic APEX Layer 1 in-memory token bucket rate limiter to throttle ingress burst.",
    target_env=env,
    capacity: int = 10,
    replenishment_rate: float = 40.0,
) -> Tuple[DynamicToolDefinition, FunctionTool]:
    """Validate AST safety, compile tool in the restricted sandbox, attach to agent and target environment."""
    # 1. AST Safety Validation
    validate_code_safety(code_string)

    # 2. Compute verification hash
    code_hash = hashlib.sha256(code_string.encode("utf-8")).hexdigest()

    # 3. Compile in the restricted sandbox namespace (curated builtins, guarded imports)
    limiter_cls = compile_in_sandbox(code_string)
    if limiter_cls:
        limiter_instance = limiter_cls(capacity=capacity, replenishment_rate=replenishment_rate)
    else:
        limiter_instance = TokenBucketRateLimiter(capacity=capacity, replenishment_rate=replenishment_rate)

    # Attach directly into target environment middleware
    if target_env is not None:
        target_env.rate_limiter = limiter_instance

    # Define tool callable for ADK agents
    def configure_rate_limiter(capacity: int = 45, replenishment_rate: float = 40.0) -> Dict[str, Any]:
        """Reconfigure active in-memory token bucket rate limiter parameters."""
        limiter_instance.capacity = capacity
        limiter_instance.replenishment_rate = replenishment_rate
        return {
            "status": "APEX_PATCH_ACTIVE",
            "capacity": capacity,
            "replenishment_rate": replenishment_rate,
            "target": "target_env.server",
        }

    # Wrap into Google ADK FunctionTool
    dynamic_adk_tool = FunctionTool(configure_rate_limiter)

    # Dynamically inject into active agent's tool collection
    if hasattr(agent, "tools"):
        if agent.tools is None:
            agent.tools = []
        agent.tools.append(dynamic_adk_tool)

    definition = DynamicToolDefinition(
        tool_name=tool_name,
        description=description,
        python_code=code_string,
        input_schema={"capacity": "int", "replenishment_rate": "float"},
        verification_hash=code_hash,
        created_at=utc_now(),
    )

    return definition, dynamic_adk_tool
