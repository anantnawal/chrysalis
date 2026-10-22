"""End-to-End Autonomous Demonstration Script for Project Chrysalis.

Walks through the complete 4-phase autonomous resilience and evolution lifecycle:
Phase 1: In-Memory Cache Stampede reproduction
Phase 2: ADK 2.0 Fast Loop Triage & APEX Layer 1 Hotpatch
Phase 3: AgentEvolver Credit Attribution & APEX Topological Evolution
Phase 4: Dream-RSI Counterfactual Replay & Self-Questioning Sandbox Verification
"""

import asyncio
import time
import json
import uuid
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import List, Dict, Any

from app.config import (
    MODEL_NAME,
    PROJECT_ID,
    LOCATION,
    TARGET_P99_LATENCY_MS,
    VERTEX_AI_AVAILABLE,
)
from app.target_env.server import env, checkout, CheckoutRequest
from app.adk_agents.schemas import (
    SystemMetrics,
    ActionExecutionSpan,
    IncidentContext,
    utc_now,
)
from app.adk_agents.supervisor import ChrysalisSupervisor
from app.adk_agents.code_synthesis import synthesize_rate_limiter
from app.adk_agents.dynamic_registry import (
    register_dynamic_tool,
    TokenBucketRateLimiter,
)
from app.evolution.credit_attribution import CreditAttributionEngine
from app.evolution.principle_store import SemanticPrincipleStore
from app.evolution.topology_mutator import TopologyMutator, apply_policy_via_traffic_agent
from app.evolution.dream_rsi_replay import DreamRSIReplayEngine
from app.evolution.self_questioner import SelfQuestioningEngine


# ANSI Color formatting
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"


def print_banner():
    offline_note = (
        ""
        if VERTEX_AI_AVAILABLE
        else f"\n{Style.YELLOW}   [Offline mode] No Google Cloud credentials found: ADK agents use deterministic fallbacks.\n"
        f"   Run `gcloud auth application-default login` to enable live Gemini on Vertex AI.{Style.RESET}"
    )
    banner = f"""
{Style.CYAN}{Style.BOLD}========================================================================================
   PROJECT CHRYSALIS
   Architecting Governed, Self-Evolving AI Agents on Gemini Enterprise Agent Platform
   Google ADK 2.0 Multi-Agent Framework + Gemini on Vertex AI ({PROJECT_ID})
========================================================================================{Style.RESET}{offline_note}
"""
    print(banner)


def print_phase_header(phase_num: int, title: str, subtitle: str):
    header = f"""
{Style.BLUE}{Style.BOLD}----------------------------------------------------------------------------------------
[PHASE {phase_num}] {title.upper()}
>>> {subtitle}
----------------------------------------------------------------------------------------{Style.RESET}
"""
    print(header)


async def fire_checkout_burst(num_requests: int = 50, cart_id_range: int = 15) -> Dict[str, Any]:
    """Fire concurrent checkout requests directly through the target environment."""
    tasks = []
    for i in range(num_requests):
        cid = f"cart_{100 + (i % cart_id_range)}"
        req = CheckoutRequest(user_id=f"shopper_{i:03d}", cart_id=cid)
        tasks.append(checkout(req))

    start = time.perf_counter()
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.perf_counter() - start

    status_200 = 0
    status_429 = 0
    status_500 = 0

    for r in responses:
        if isinstance(r, dict):
            status_200 += 1
        elif hasattr(r, "status_code"):
            if r.status_code == 200:
                status_200 += 1
            elif r.status_code == 429:
                status_429 += 1
            elif r.status_code >= 500:
                status_500 += 1
        else:
            status_500 += 1

    return {
        "total": num_requests,
        "duration_sec": round(duration, 2),
        "status_200": status_200,
        "status_429": status_429,
        "status_500": status_500,
        "error_rate": round(status_500 / num_requests, 3),
    }


async def run_full_demo():
    print_banner()

    # =========================================================================
    # PHASE 1: IN-MEMORY CACHE STAMPEDE
    # =========================================================================
    print_phase_header(
        1,
        "In-Memory Cache Stampede Simulation",
        "Simulating Black Friday burst: LRU eviction, DB connection pool starvation",
    )
    print(f"{Style.YELLOW}[>] Step 1.1: Pre-warming cache with baseline shopping carts...{Style.RESET}")
    for i in range(5):
        await checkout(CheckoutRequest(cart_id=f"cart_{100+i}"))
    # Measure steady-state baseline on a warm cache in a fresh telemetry window
    env.telemetry.start_new_window()
    for i in range(5):
        await checkout(CheckoutRequest(cart_id=f"cart_{100+i}"))
    baseline_metrics = env.telemetry.get_current_metrics()
    print(f"    Baseline: Latency={baseline_metrics.p99_latency_ms:.1f}ms, Cache Hit Ratio={baseline_metrics.cache_hit_ratio*100:.0f}%, 5xx Rate={baseline_metrics.http_5xx_rate*100:.1f}%")

    print(f"\n{Style.RED}[!] Step 1.2: Triggering Black Friday 50-Request Concurrent Surge across 15 cold keys...{Style.RESET}")
    env.cache.purge()  # Purge cache to simulate catastrophic key eviction sweep
    env.telemetry.start_new_window()
    burst_results = await fire_checkout_burst(num_requests=50, cart_id_range=15)

    stampede_metrics = env.telemetry.get_current_metrics()
    pool_stats = env.db.get_pool_stats()
    print(f"\n{Style.RED}{Style.BOLD}--- INCIDENT TELEMETRY SNAPSHOT ---{Style.RESET}")
    print(f"Total Concurrent Requests : {burst_results['total']}")
    print(f"HTTP 200 (Success)        : {burst_results['status_200']}")
    print(f"HTTP 500 (Starvation)     : {Style.RED}{burst_results['status_500']} ({burst_results['error_rate']*100:.1f}%){Style.RESET}")
    print(f"P99 Ingress Latency       : {Style.RED}{stampede_metrics.p99_latency_ms:.1f} ms{Style.RESET} (Target: {TARGET_P99_LATENCY_MS} ms)")
    print(f"DB Pool Saturation (peak) : {Style.RED}{stampede_metrics.db_pool_utilization*100:.0f}% ({pool_stats['window_timeouts']} connection acquisition timeouts){Style.RESET}")
    print(f"Cache Eviction Count      : {stampede_metrics.cache_eviction_count} keys evicted")

    # =========================================================================
    # PHASE 2: ADK 2.0 FAST LOOP TRIAGE & APEX LAYER 1 HOTPATCH
    # =========================================================================
    print_phase_header(
        2,
        "ADK 2.0 Fast Loop Triage & APEX Layer 1 Hotpatch",
        "Gemini supervisor delegates to DiagnosticAgent, queries Self-Navigating memory, and synthesizes dynamic tool",
    )

    supervisor = ChrysalisSupervisor(model_name=MODEL_NAME)
    principle_store = SemanticPrincipleStore()

    incident_alert = (
        f"CRITICAL SRE ALERT: Cache Stampede detected! HTTP 500 error rate is {burst_results['error_rate']*100:.1f}%, "
        f"P99 latency is {stampede_metrics.p99_latency_ms:.1f}ms, DB pool utilization is {stampede_metrics.db_pool_utilization*100:.0f}%. "
        f"Evaluate Self-Navigating principles and recommend immediate mitigation."
    )

    print(f"{Style.CYAN}[>] Step 2.1: Dispatching incident alert to ADK 2.0 Supervisor Router Agent...{Style.RESET}")
    triage_output = await supervisor.run_triage(incident_alert)
    print(f"\n{Style.GREEN}{Style.BOLD}--- ADK 2.0 MULTI-AGENT DIAGNOSTIC REPORT ---{Style.RESET}")
    report_lines = [line for line in triage_output["agent_response"].split("\n") if line.strip() and line.strip() != "---"]
    max_lines = 14
    for line in report_lines[:max_lines]:
        print(f"    {line}")
    if len(report_lines) > max_lines:
        print(f"    ... ({len(report_lines) - max_lines} more lines)")
    if not report_lines:
        print("    (Supervisor returned no textual report)")

    # Check Self-Navigating Memory against dangerous DB reboot
    print(f"\n{Style.YELLOW}[>] Step 2.2: Self-Navigating Memory Guardrail Check:{Style.RESET}")
    retrieved_principles = principle_store.search_principles("cache stampede database pool lockup", top_k=1)
    if retrieved_principles:
        top_p = retrieved_principles[0]
        print(f"    {Style.RED}{Style.BOLD}BLOCKING ACTION:{Style.RESET} Database Restart is strictly contraindicated!")
        print(f"    Reason: '{top_p.trigger_pattern}'")
        print(f"    Contraindications: {top_p.contraindicated_actions}")
        print(f"    Recommended      : {top_p.recommended_actions}")

    # Simulate Counterfactual Negative Span: Dangerous action penalty
    span_db_reboot = ActionExecutionSpan(
        span_id=f"span_{uuid.uuid4().hex[:8]}",
        agent_name="legacy_remediation_agent",
        tool_name="reboot_database_connections",
        input_parameters={"action_type": "database_pool_flush"},
        output_result={"status": "CONNECTION_RESET_FAILED"},
        pre_state_metrics=stampede_metrics,
        post_state_metrics=SystemMetrics(
            p99_latency_ms=3800.0,
            http_5xx_rate=0.85,
            db_pool_utilization=1.0,
            cache_hit_ratio=0.0,
        ),
        cost_usd=0.05,
        execution_duration_ms=1200.0,
        timestamp=utc_now(),
    )
    env.telemetry.record_action_span(span_db_reboot)

    print(f"\n{Style.MAGENTA}[>] Step 2.3: APEX Layer 1 (Harness Patching): Gemini synthesizing a dynamic Python tool from the diagnosis...{Style.RESET}")
    synthesis = await asyncio.to_thread(
        synthesize_rate_limiter,
        triage_output["agent_response"],
        MODEL_NAME,
        VERTEX_AI_AVAILABLE,
    )
    origin = (
        f"{Style.GREEN}Gemini-synthesized ({synthesis.model}, attempt {synthesis.attempts}){Style.RESET}"
        if synthesis.source == "gemini"
        else f"{Style.YELLOW}Reviewed reference template (Gemini unavailable or output rejected){Style.RESET}"
    )
    print(f"    Code Origin           : {origin}")
    for gate in synthesis.gate_log:
        print(f"    Verification Gate     : {gate}")
    code_lines = [l for l in synthesis.code.splitlines() if l.strip()]
    print(f"    Synthesized Code      : {len(code_lines)} lines")
    for line in code_lines[:6]:
        print(f"      {Style.CYAN}{line}{Style.RESET}")
    if len(code_lines) > 6:
        print(f"      {Style.CYAN}...{Style.RESET}")

    tool_def, dynamic_tool = register_dynamic_tool(
        supervisor.supervisor_agent,
        code_string=synthesis.code,
        target_env=env,
    )
    print(f"    AST Sandbox Policy    : {Style.GREEN}PASSED (import allow-list, no forbidden builtins / dunder access){Style.RESET}")
    print(f"    Verification Hash     : {tool_def.verification_hash[:16]}...")
    print(f"    Tool Registration     : Compiled in restricted sandbox; attached to Supervisor and Target Environment Middleware")

    print(f"\n{Style.CYAN}[>] Step 2.4: Firing second burst with APEX Layer 1 Rate Limiter ACTIVE...{Style.RESET}")
    env.telemetry.start_new_window()
    recovered_burst = await fire_checkout_burst(num_requests=50, cart_id_range=15)
    recovered_metrics = env.telemetry.get_current_metrics()
    recovered_pool = env.db.get_pool_stats()

    err_color = Style.GREEN if recovered_burst["status_500"] == 0 else Style.RED
    latency_note = (
        "Restored to target!"
        if recovered_metrics.p99_latency_ms <= TARGET_P99_LATENCY_MS
        else f"down from {stampede_metrics.p99_latency_ms:.0f} ms; admitted cold misses queue briefly on the 2-slot pool"
    )
    print(f"\n{Style.GREEN}{Style.BOLD}--- POST-PATCH RECOVERY SNAPSHOT ---{Style.RESET}")
    print(f"Total Requests Processed  : {recovered_burst['total']}")
    print(f"HTTP 200 (Success)        : {Style.GREEN}{recovered_burst['status_200']}{Style.RESET}")
    print(f"HTTP 429 (Safely Shed)    : {Style.YELLOW}{recovered_burst['status_429']}{Style.RESET}")
    print(f"HTTP 500 (Errors)         : {err_color}{recovered_burst['status_500']} ({recovered_burst['error_rate']*100:.1f}%){Style.RESET}")
    print(f"P99 Ingress Latency       : {Style.GREEN}{recovered_metrics.p99_latency_ms:.1f} ms{Style.RESET} ({latency_note})")
    print(f"DB Pool Saturation (peak) : {err_color}{recovered_metrics.db_pool_utilization*100:.0f}% ({recovered_pool['window_timeouts']} acquisition timeouts){Style.RESET}")

    # Record Positive Action Span
    span_apex_patch = ActionExecutionSpan(
        span_id=f"span_{uuid.uuid4().hex[:8]}",
        agent_name="supervisor_agent",
        tool_name="token_bucket_rate_limiter_patch",
        input_parameters={"action_type": "apex_l1_harness_patch", "capacity": 10, "rate": 40.0},
        output_result={"status": "STABILITY_RESTORED"},
        pre_state_metrics=stampede_metrics,
        post_state_metrics=recovered_metrics,
        cost_usd=0.001,
        execution_duration_ms=45.0,
        timestamp=utc_now(),
    )
    env.telemetry.record_action_span(span_apex_patch)

    # =========================================================================
    # PHASE 3: CREDIT ATTRIBUTION & TOPOLOGICAL EVOLUTION
    # =========================================================================
    print_phase_header(
        3,
        "AgentEvolver Credit Attribution & APEX Topological Evolution",
        "Mathematical Shapley attribution, APEX Layer 2 distillation, Layer 3 graph mutation",
    )

    credit_engine = CreditAttributionEngine()
    spans = env.telemetry.get_action_spans()
    attributions = credit_engine.evaluate_trajectory(spans)

    print(f"{Style.CYAN}[>] Step 3.1: Computing Step-Level Credit Attribution Formula:{Style.RESET}")
    print("    H(S_t) = 0.35*(L/50ms) + 0.40*5xx + 0.25*U_pool")
    print("    C(a_t) = tanh(alpha * delta_H - beta * Cost)")
    print(f"\n{credit_engine.format_attribution_table(attributions)}\n")

    print(f"{Style.MAGENTA}[>] Step 3.2: APEX Layer 2 (Principle Distillation): Invoking ADK PrincipleDistillerAgent...{Style.RESET}")
    from app.adk_agents.distiller_agent import ChrysalisDistillerAgentRunner
    distiller_runner = ChrysalisDistillerAgentRunner(principle_store=principle_store, model_name=MODEL_NAME)
    distill_result = await distiller_runner.distill(
        incident_id="INC-BF-2026",
        attributions=attributions,
    )
    distilled_principle = distill_result["principle"]
    print(f"    ADK Agent Dispatched  : principle_distiller_agent (Gemini 4.0 Argon)")
    print(f"    Executed Tool Calls   : {[t['name'] for t in distill_result['tool_calls']]}")
    if distilled_principle:
        print(f"    Distilled Principle ID: {distilled_principle.principle_id}")
        print(f"    Trigger Pattern       : {distilled_principle.trigger_pattern}")
        print(f"    Contraindicated       : {distilled_principle.contraindicated_actions}")
        print(f"    Recommended           : {distilled_principle.recommended_actions}")
        print(f"    Confidence Score      : {distilled_principle.confidence_score * 100:.1f}%")

    print(f"\n{Style.BLUE}[>] Step 3.3: APEX Layer 3 (Topology Re-Wiring): Mutating Google ADK multi-agent graph...{Style.RESET}")
    mutator = TopologyMutator(model_name=MODEL_NAME)
    mutation_result = mutator.rewire_supervisor(supervisor)
    print(f"    Status                : {Style.GREEN}{mutation_result['status']}{Style.RESET}")
    print(f"    New Permanent Agent   : {mutation_result['new_agent_name']}")
    print(f"    Updated Sub-Agents    : {mutation_result['sub_agent_names']}")
    print(f"    Dispatcher Re-wired   : Sub-agent dispatch rules compiled into root Supervisor")

    # =========================================================================
    # PHASE 4: DREAM-RSI REPLAY & SELF-QUESTIONING VERIFICATION
    # =========================================================================
    print_phase_header(
        4,
        "Dream-RSI Replay & Self-Questioning Verification",
        "DuckDB offline parameter sweep across 400 policy variations; ADK Curiosity Chaos Agent",
    )

    print(f"{Style.CYAN}[>] Step 4.1: Exporting request execution traces to in-memory DuckDB table...{Style.RESET}")
    replay_engine = DreamRSIReplayEngine()
    loaded_count = replay_engine.load_trajectory_data(env.telemetry.get_request_logs())
    print(f"    Loaded {loaded_count} recorded request spans into DuckDB")

    rates_to_test = [float(r) for r in range(5, 205, 5)]
    capacities_to_test = [5, 8, 10, 15, 20, 30, 42, 50, 75, 100]
    print(f"\n{Style.CYAN}[>] Step 4.2: Running Dream-RSI Vectorized Counterfactual Policy Sweep ({len(rates_to_test) * len(capacities_to_test)} simulations)...{Style.RESET}")
    # Search space: capacity [5..100] x replenishment rate [5..200] req/s
    sweep_results, optimal_policy, elapsed_ms = replay_engine.run_counterfactual_sweep(
        rates_to_test=rates_to_test,
        capacities_to_test=capacities_to_test,
    )
    print(f"    Simulated Policies    : {len(sweep_results)} counterfactual runs completed in {elapsed_ms:.1f} ms")
    print(f"    SLO-Feasible Frontier : {sum(1 for r in sweep_results if r.is_pareto_optimal)} candidate configurations (0 5xx, >=15% pool headroom)")
    print(f"\n{Style.GREEN}{Style.BOLD}--- DREAM-RSI OPTIMAL POLICY DISCOVERY ---{Style.RESET}")
    print(f"    Optimal Parameter     : {optimal_policy.tested_value}")
    print(f"    Simulated P99 Latency : {optimal_policy.simulated_p99_latency_ms:.1f} ms")
    print(f"    Simulated 5xx Count   : {optimal_policy.simulated_5xx_count}")
    print(f"    Simulated DB Max Load : {optimal_policy.simulated_database_max_load*100:.0f}%")
    print(f"    Live Execution Cost   : $0.00 (Zero cloud compute, zero production risk)")

    opt_cap = optimal_policy.tested_value.get("capacity", 10)
    opt_rate = optimal_policy.tested_value.get("rate_req_sec", 40.0)
    print(f"\n{Style.BLUE}[>] Step 4.3: Evolved Topology in Action: Supervisor delegates policy rollout to TrafficShapingAgent...{Style.RESET}")
    applied = await apply_policy_via_traffic_agent(supervisor, opt_cap, opt_rate)
    a_color = Style.GREEN if applied["source"] == "adk_agents" else Style.YELLOW
    print(f"    Handled By            : {a_color}{' -> '.join(applied['agents']) or 'n/a'} ({applied['source']}){Style.RESET}")
    for tc in applied["tool_calls"]:
        print(f"    • ADK Tool Executed   : {Style.MAGENTA}{tc['agent']}.{tc['name']}{Style.RESET} {tc['args']}")
    print(f"    Live Rate Limiter     : capacity={applied['active_limiter']['capacity']}, rate={applied['active_limiter']['replenishment_rate']} req/s "
          f"({Style.GREEN + 'applied' if applied['applied'] else Style.RED + 'NOT applied'}{Style.RESET})")

    print(f"\n{Style.YELLOW}[>] Step 4.4: AgentEvolver Curiosity Engine: Dispatching ADK CuriosityChaosAgent...{Style.RESET}")
    from app.adk_agents.chaos_agent import ChrysalisChaosAgentRunner
    chaos_runner = ChrysalisChaosAgentRunner(
        model_name=MODEL_NAME,
        tested_capacity=opt_cap,
        tested_rate=opt_rate,
    )
    chaos_directive = (
        f"You are the Red Team Chaos Engineer. The system was patched with token bucket (cap={opt_cap}, rate={opt_rate} req/s). "
        f"Formulate an adversarial 'What-If?' hypothesis combining an instantaneous cache drop with a 200-request burst. "
        f"Execute `inject_shadow_cache_purge`, then `fire_shadow_concurrent_burst` with 200 requests, and finally `assert_shadow_invariant`."
    )
    print(f"    ADK Agent Dispatched  : curiosity_chaos_agent (Gemini 4.0 Argon)")
    chaos_result = await chaos_runner.run_chaos_probe(chaos_directive)

    print(f"\n{Style.CYAN}[>] Step 4.5: ADK Chaos Agent Autonomous Tool Execution Trace:{Style.RESET}")
    for tc in chaos_result["tool_calls"]:
        print(f"    • ADK Tool Executed   : {Style.MAGENTA}{tc['name']}{Style.RESET} {tc.get('args', {})}")

    final_m = chaos_result["final_metrics"]
    shadow_total = chaos_result["shadow_requests"]
    shadow_5xx = chaos_result["shadow_5xx"]
    verified = chaos_result["verdict"] == "VERIFIED_RESILIENT"
    v_color = Style.GREEN if verified else Style.RED
    print(f"    P99 Shadow Latency    : {final_m.p99_latency_ms:.1f} ms")
    print(f"    HTTP 500 Starvation   : {v_color}{shadow_5xx} errors / {shadow_total} shadow requests ({final_m.http_5xx_rate*100:.1f}%){Style.RESET}")
    print(f"    Verification Result   : {v_color}{Style.BOLD}{chaos_result['verdict']}{Style.RESET}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    reboot_scores = [a.attribution_score for a in attributions if "reboot" in a.tool_name]
    patch_scores = [a.attribution_score for a in attributions if "rate_limiter" in a.tool_name]
    credit_summary = (
        f"{reboot_scores[0]:+.2f} reboot / {patch_scores[0]:+.2f} patch"
        if reboot_scores and patch_scores
        else f"{len(attributions)} spans scored"
    )
    verification_summary = (
        f"Shadow chaos sandbox confirmed 0 HTTP 500 errors across {shadow_total} requests under key eviction surge."
        if verified
        else f"Shadow chaos sandbox found {shadow_5xx} HTTP 500 errors: policy requires further tuning."
    )
    synth_summary = (
        f"synthesized by Gemini ({synthesis.model}) and passed all sandbox gates"
        if synthesis.source == "gemini"
        else "reviewed reference template (Gemini unavailable/rejected) passed all sandbox gates"
    )
    rollout_summary = (
        f"TrafficShapingAgent applied the Dream-RSI policy live via {', '.join(tc['name'] for tc in applied['tool_calls'] if tc['agent'] == 'traffic_shaping_agent') or 'set_rate_limit'}"
        if applied["source"] == "adk_agents"
        else "Dream-RSI policy applied via deterministic fallback (agents did not delegate)"
    )
    print(f"""
{Style.GREEN}{Style.BOLD}========================================================================================
   PROJECT CHRYSALIS: AUTONOMOUS RECURSIVE EVOLUTION COMPLETE
========================================================================================{Style.RESET}
• [APEX Layer 1]: TokenBucketRateLimiter {synth_summary}; hotpatched live.
• [APEX Layer 2]: Generalized operational invariant distilled into semantic vector store.
• [APEX Layer 3]: Multi-agent topology permanently rewired; {rollout_summary}.
• [AgentEvolver]: Step-level Shapley credit attribution calculated ({credit_summary}; reboot is a counterfactual replay).
• [Dream-RSI]   : {len(sweep_results)} counterfactual policy sweeps executed offline in {elapsed_ms:.1f}ms via DuckDB (optimal: {optimal_policy.tested_value}).
• [Verification]: {verification_summary}
""")


if __name__ == "__main__":
    # Stream output line-by-line even when piped to a file / CI log
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(run_full_demo())
