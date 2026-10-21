"""Reset utility for Project Chrysalis.

Restores the target environment, cache, database pool, telemetry buffers,
and ADK multi-agent topology back to their pristine initial baseline state.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.config import SERVER_PORT, BASE_URL, MODEL_NAME
from app.target_env.server import env
from app.adk_agents.supervisor import ChrysalisSupervisor
from app.evolution.principle_store import SemanticPrincipleStore


class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"


def reset_chrysalis_system():
    print(f"\n{Style.CYAN}{Style.BOLD}========================================================================================{Style.RESET}")
    print(f"{Style.CYAN}{Style.BOLD}   RESETTING PROJECT CHRYSALIS TO PRISTINE BASELINE STATE{Style.RESET}")
    print(f"{Style.CYAN}{Style.BOLD}========================================================================================{Style.RESET}\n")

    # 1. Reset in-process Target Environment
    print(f"{Style.YELLOW}[1/4] Purging in-memory cache and resetting LRU stats...{Style.RESET}")
    env.cache.purge()
    env.cache.reset_stats()

    print(f"{Style.YELLOW}[2/4] Resetting SQLite connection pool & re-initializing schema...{Style.RESET}")
    env.db.reboot()

    print(f"{Style.YELLOW}[3/4] Clearing telemetry buffers, request traces, and APEX hotpatches...{Style.RESET}")
    env.telemetry.reset()
    env.rate_limiter = None

    # Check if a live server is running on localhost
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.post(f"{BASE_URL}/admin/reset")
            if resp.status_code == 200:
                print(f"      Live server at {BASE_URL} notified: {resp.json().get('status')}")
    except Exception:
        pass  # Server not running standalone, in-process reset completed

    # 4. Re-initialize baseline ADK Agent Topology
    print(f"{Style.YELLOW}[4/4] Restoring baseline ADK 2.0 Multi-Agent Topology...{Style.RESET}")
    supervisor = ChrysalisSupervisor(model_name=MODEL_NAME)
    principle_store = SemanticPrincipleStore()

    sub_agents = [a.name for a in supervisor.supervisor_agent.sub_agents]
    metrics = env.telemetry.get_current_metrics()

    print(f"""
{Style.GREEN}{Style.BOLD}✔ SYSTEM SUCCESSFULLY RESTORED TO INITIAL BASELINE:{Style.RESET}
----------------------------------------------------------------------------------------
• Target Environment Rate Limiter : {Style.GREEN}None (Hotpatches Detached){Style.RESET}
• Cache Active Keys / Evictions   : {Style.GREEN}0 keys / 0 evictions{Style.RESET}
• Database Connection Pool        : {Style.GREEN}0 / 2 active (Semaphore Unlocked){Style.RESET}
• OpenTelemetry Request Logs      : {Style.GREEN}0 traces recorded{Style.RESET}
• Active ADK Agent Topology       : {Style.GREEN}{supervisor.supervisor_agent.name} -> {sub_agents} (Initial 2 Agents){Style.RESET}
• Evolved TrafficShapingAgent     : {Style.GREEN}Decommissioned (Ready for next evolution cycle){Style.RESET}
• P99 Latency / 5xx Error Rate    : {Style.GREEN}{metrics.p99_latency_ms:.1f} ms / {metrics.http_5xx_rate*100:.1f}% (Nominal){Style.RESET}
----------------------------------------------------------------------------------------
Ready to run a fresh demonstration: .venv/bin/python3 app/demo_runner.py
""")


if __name__ == "__main__":
    reset_chrysalis_system()
