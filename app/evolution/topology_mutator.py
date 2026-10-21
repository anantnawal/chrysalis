"""APEX Layer 3 Topology Re-Wiring: Dynamically mutates Google ADK multi-agent graph to commission permanent specialist agents."""
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from app.config import MODEL_NAME
from app.target_env.server import env


# Specialist tools for TrafficShapingAgent
def set_rate_limit(capacity: int, replenishment_rate: float) -> Dict[str, Any]:
    """Set the live ingress token bucket parameters (burst capacity in tokens, replenishment rate in req/s)."""
    if env.rate_limiter is not None:
        previous = {"capacity": env.rate_limiter.capacity, "replenishment_rate": env.rate_limiter.replenishment_rate}
        env.rate_limiter.capacity = int(capacity)
        env.rate_limiter.replenishment_rate = float(replenishment_rate)
        return {
            "status": "CONFIGURED",
            "previous": previous,
            "capacity": int(capacity),
            "replenishment_rate": float(replenishment_rate),
            "message": "Token bucket active on live ingress pipeline",
        }
    return {
        "status": "NO_LIMITER_ATTACHED",
        "message": "Rate limiter instance not attached to target environment",
    }


def inspect_queue_depth() -> Dict[str, Any]:
    """Inspect current queue depth and rate-limiting throttling statistics."""
    if env.rate_limiter is not None:
        stats = env.rate_limiter.get_stats()
        return {
            "rate_limiter_active": True,
            "available_tokens": stats["current_tokens"],
            "total_admitted": stats["total_admitted"],
            "total_throttled": stats["total_throttled"],
        }
    return {
        "rate_limiter_active": False,
        "available_tokens": 0,
        "total_admitted": 0,
        "total_throttled": 0,
    }


def adjust_token_replenishment(rate: float) -> Dict[str, Any]:
    """Dynamically adjust token replenishment rate per second based on load."""
    if env.rate_limiter is not None:
        env.rate_limiter.replenishment_rate = rate
        return {"status": "UPDATED", "replenishment_rate": rate}
    return {"status": "FAILED", "reason": "No active rate limiter"}


tool_set_rate_limit = FunctionTool(set_rate_limit)
tool_inspect_queue = FunctionTool(inspect_queue_depth)
tool_adjust_replenish = FunctionTool(adjust_token_replenishment)

TRAFFIC_SHAPING_INSTRUCTION = """You are the Chrysalis Permanent Traffic Shaping Specialist Agent powered by Gemini.
You were synthesized and wired into the multi-agent graph via APEX Layer 3 Topology Re-Wiring.

Your Responsibilities:
1. Shape ingress request bursts using `set_rate_limit` to prevent database connection pool saturation.
2. Monitor real-time queue depth and throttling counts using `inspect_queue_depth`.
3. Dynamically modulate token replenishment via `adjust_token_replenishment` to maintain zero HTTP 500 errors while maximizing request throughput.
"""


class TopologyMutator:
    """Modifies the active ADK multi-agent graph at runtime."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.evolved_agents: List[LlmAgent] = []

    def spawn_traffic_shaping_agent(self) -> LlmAgent:
        """Instantiate the permanent TrafficShapingAgent."""
        agent = LlmAgent(
            name="traffic_shaping_agent",
            description="Permanent evolved specialist agent responsible for boundary ingress rate limiting, queue monitoring, and load shedding.",
            model=self.model_name,
            instruction=TRAFFIC_SHAPING_INSTRUCTION,
            tools=[tool_set_rate_limit, tool_inspect_queue, tool_adjust_replenish],
        )
        self.evolved_agents.append(agent)
        return agent

    def rewire_supervisor(self, supervisor_wrapper) -> Dict[str, Any]:
        """Rewire the SupervisorRouterAgent to incorporate the new TrafficShapingAgent."""
        supervisor_agent = supervisor_wrapper.supervisor_agent

        # 1. Mutate sub_agents list (idempotent: only commission the agent once)
        if supervisor_agent.sub_agents is None:
            supervisor_agent.sub_agents = []
        existing = next((a for a in supervisor_agent.sub_agents if a.name == "traffic_shaping_agent"), None)
        if existing is None:
            traffic_agent = self.spawn_traffic_shaping_agent()
            # ADK wires parent links only at construction time; set it explicitly so
            # transfer_to_agent routing (and transfers back to the root) work for the new node.
            traffic_agent.parent_agent = supervisor_agent
            supervisor_agent.sub_agents.append(traffic_agent)
        else:
            traffic_agent = existing

        # 2. Update supervisor routing instructions to include traffic shaping delegation
        routing_rule = """
5. Dynamic Topology Routing (APEX Layer 3):
   You now have access to a permanent specialist sub-agent `traffic_shaping_agent`.
   When diagnosing an ingress surge, cache stampede, or connection saturation, immediately delegate traffic rate limiting to `traffic_shaping_agent`.
"""
        if "Dynamic Topology Routing (APEX Layer 3):" not in supervisor_agent.instruction:
            supervisor_agent.instruction += routing_rule

        # 3. Re-bind the ADK Runner with the evolved multi-agent graph
        supervisor_wrapper.runner = Runner(
            app_name="chrysalis",
            agent=supervisor_wrapper.supervisor_agent,
            session_service=supervisor_wrapper.session_service,
            auto_create_session=True,
        )

        return {
            "status": "TOPOLOGY_MUTATED",
            "new_agent_name": traffic_agent.name,
            "total_sub_agents": len(supervisor_wrapper.supervisor_agent.sub_agents),
            "sub_agent_names": [a.name for a in supervisor_wrapper.supervisor_agent.sub_agents],
        }


async def apply_policy_via_traffic_agent(supervisor_wrapper, capacity: int, replenishment_rate: float) -> Dict[str, Any]:
    """Have the evolved multi-agent graph apply a Dream-RSI policy to the live limiter.

    The root supervisor receives a directive and must delegate to the commissioned
    `traffic_shaping_agent`, whose `set_rate_limit` tool retunes the live token bucket. The
    outcome is verified against the actual limiter state; if the agents did not apply it (or
    Vertex AI is unavailable) the tool is invoked directly and labelled as such.
    """
    capacity, replenishment_rate = int(capacity), float(replenishment_rate)
    directive = (
        "Dream-RSI counterfactual replay selected the optimal ingress policy for the live token bucket: "
        f"capacity={capacity} tokens, replenishment_rate={replenishment_rate} req/s. "
        "Delegate to `traffic_shaping_agent` to apply exactly these values now with `set_rate_limit`, "
        "then briefly confirm the active settings."
    )
    trace = await supervisor_wrapper.run_directive(directive)

    def _limiter_matches() -> bool:
        lim = env.rate_limiter
        return lim is not None and int(lim.capacity) == capacity and abs(float(lim.replenishment_rate) - replenishment_rate) < 1e-6

    agent_applied = _limiter_matches() and any(tc["name"] == "set_rate_limit" for tc in trace["tool_calls"])
    if not agent_applied:
        set_rate_limit(capacity, replenishment_rate)

    lim = env.rate_limiter
    return {
        "source": "adk_agents" if agent_applied else "deterministic_fallback",
        "agents": trace["agents"],
        "tool_calls": trace["tool_calls"],
        "response": trace["text"],
        "applied": _limiter_matches(),
        "active_limiter": {"capacity": lim.capacity, "replenishment_rate": lim.replenishment_rate} if lim else None,
    }
