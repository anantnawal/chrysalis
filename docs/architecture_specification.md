> [!NOTE]
> This is the original technical design specification for Project Chrysalis. For how to install, run and reset the current implementation, see the [repository README](../README.md) and the [Agent Platform edition README](../agent_platform_version/README.md).

# Project Chrysalis: Self-Evolving Autonomous Resiliency & FinOps Engine

## Technical Architecture & Implementation Specification for Google ADK 2.0 with Gemini 3.7 Flash

## 1\. Executive Summary & Problem Formulation

Autonomous Site Reliability Engineering (SRE) agents operating in production environments face a fundamental trilemma:

1. **Exploration Risk & Execution Cost:** Live trial-and-error in production risks catastrophic cascades, thread starvation, and runaway infrastructure billing.

2. **Brittle Generalization:** Remediating a point incident with an ad-hoc action does not create durable, abstract operational knowledge.

3. **Coarse Credit Assignment:** In multi-step diagnostic chains, agents cannot determine which specific sub-action resolved an incident versus which action exacerbated latency or costs.

**Project Chrysalis** resolves this trilemma by unifying three cutting-edge paradigms in recursive self-improvement and agent evolution into an extensible framework based on the **Google Agent Development Kit (ADK) 2.0** (`google-adk`) and powered end-to-end by **Gemini 3.7 Flash**:

* **Dream-RSI (arXiv:2609.14858):** Offline policy optimization that transforms incident execution trajectory trees into an empirical replay simulator ("dreaming"). This enables thousands of counterfactual policy variations to be evaluated offline with zero production risk and zero runtime compute expense.

* **APEX (arXiv:2606.15363):** A three-layer co-evolutionary pipeline:

  * *Layer 1 (Harness Patching):* Synthesizes transient, safe operational tools injected directly into the agent's active execution harness.

  * *Layer 2 (Principle Distillation):* Extracts generalized invariant heuristics from successful harness patches and records them in semantic memory.

  * *Layer 3 (Topology Re-Wiring):* Autonomously refactors the ADK multi-agent graph by spawning, wiring, and permanently commissioning specialized sub-agents.

* **AgentEvolver (arXiv:2511.10395):** Continuous autonomous learning via:

  * *Self-Questioning:* Proactive curiosity and boundary probing through synthetic fault injection in a shadow sandbox.

  * *Self-Navigating:* Trajectory guidance using vector-indexed historical failure traces.

  * *Self-Attributing:* Fine-grained token- and step-level credit assignment calculated over distributed telemetry deltas.

* **Unified Model Foundation (Gemini 3.7 Flash):** Every agentic role—including the supervisor orchestrator, diagnostic analyzer, AST tool code generator, principle distiller, and curiosity prober—is standardized on **Gemini 3.7 Flash**, utilizing its hybrid reasoning capabilities to conduct fast tactical triage and deep analytical synthesis across both the fast and offline evolutionary loops.

The architecture is dual-target: it can deploy to **Google Cloud / Gemini Enterprise Agent Platform** (using Cloud Run, Vertex AI Reasoning Engine, BigQuery, and Memorystore) or run entirely in an **ultra-compact, single-process, zero-cloud in-memory mode** (using FastAPI, `fakeredis`, SQLite connection semaphores, DuckDB, and in-memory vector stores).

## 2\. Theoretical Foundations & Synthesis

```
+----------------------------------------------------------------------------------------------------+
|                                    PROJECT CHRYSALIS ARCHITECTURE                                    |
|                       (Google ADK 2.0 Multi-Agent Framework + Gemini 3.7 Flash)                     |
+----------------------------------------------------------------------------------------------------+
                                                  |
         +----------------------------------------+----------------------------------------+
         |                                        |                                        |
         v                                        v                                        v
+----------------------------------+ +----------------------------------+ +----------------------------------+
|           AgentEvolver           | |               APEX               | |            Dream-RSI             |
|     (Continuous Feedback)        | |      (Tri-Level Co-Evolution)    | |     (Replay Meta-Simulation)     |
+----------------------------------+ +----------------------------------+ +----------------------------------+
| • Self-Navigating:               | | • Layer 1 (Harness Patching):    | | • Trajectory Forest:             |
|   Historical semantic routing    | |   Synthesizes dynamic Python     | |   Logs execution DAG to DuckDB/  |
|   over past failure patterns.    | |   FunctionTools at runtime.      | |   BigQuery.                      |
|                                  | |                                  | |                                  |
| • Self-Attributing:              | | • Layer 2 (Principle Extraction):| | • Counterfactual Replay:         |
|   Step-level telemetry delta     | |   Distills invariant rules into  | |   Replays historical telemetry   |
|   Shapley scoring ($S_i$).       | |   vector memory collections.     | |   offline across parameters.     |
|                                  | |                                  | |                                  |
| • Self-Questioning:              | | • Layer 3 (Topology Re-wiring):  | | • Zero-Risk Policy Search:       |
|   Curiosity-driven shadow chaos  | |   Mutates ADK Agent graph to add | |   Selects optimal thresholds     |
|   probes & proxy tasks.          | |   permanent specialist agents.   | |   before deploying to prod.      |
+----------------------------------+ +----------------------------------+ +----------------------------------+

```

&nbsp;

## 3\. Synthetic Scenario: "Black Friday Cache Stampede"

### 3.1 The Production Environment

* **Frontend Service:** Async API gateway serving `/cart/checkout` requests.

* **Cache Layer:** In-memory key-value cache holding active shopping cart sessions.

* **Database Layer:** Relational transactional database maintaining customer ledger and cart state, constrained by a strict connection pool limit ($N=2$ in compact mode; $N=50$ in enterprise mode).

### 3.2 The Failure Arc

1. **Traffic Surge:** A marketing flash sale generates a $50\times$ burst of concurrent checkout requests.

2. **Key Eviction:** Cache memory capacity reaches its configured quota; LRU eviction sweeps hot cart keys.

3. **Cache Stampede:** Hundreds of concurrent requests experience cache misses simultaneously and bypass the cache to query the relational database directly to reconstruct session states.

4. **Connection Exhaustion:** Database connection pools saturate instantly. Waiting threads queue up, latency degrades from $25\text{ ms}$ to $>5{,}000\text{ ms}$, connection timeouts trigger, and the API gateway returns cascading `HTTP 500` errors.

### 3.3 The Autonomous Resolution & Evolution Lifecycle

* **Active Triage (Fast Loop):** The ADK 2.0 Supervisor (Gemini 3.7 Flash) invokes *Self-Navigating* memory, which issues an immediate warning: *"Under connection storm, restarting the database causes total system failure."* The agent aborts database restarts and triggers an **APEX Layer 1 Harness Patch**, prompting Gemini 3.7 Flash to dynamically synthesize an in-memory token-bucket rate limiter that throttles non-critical ingress and relieves thread starvation.

* **Credit Attribution (Offline Loop):** The *Self-Attributing* engine analyzes the OpenTelemetry execution trace, assigning $-0.85$ credit to database pool adjustments and $+0.92$ credit to ingress rate limiting.

* **Principle Distillation & Graph Rewiring:** **APEX Layer 2** distills the invariant heuristic using Gemini 3.7 Flash: *"When database saturation is driven by cache misses, throttle ingress at the boundary before altering backend pool configs."* **APEX Layer 3** alters the root agent's routing topology, instantiating a dedicated **Traffic Shaping Agent** backed by Gemini 3.7 Flash.

* **Counterfactual Simulation (Dream-RSI):** The agent replays the incident logs against DuckDB offline, simulating throughput across token replenishment rates ($r \in [10, 200]\text{ req/s}$) to calculate the exact mathematical Pareto frontier.

* **Curiosity Probing (AgentEvolver Self-Questioning):** In a background sandbox, Gemini 3.7 Flash formulates and injects synthetic cache drops under simulated load, verifying that the newly wired multi-agent topology prevents connection pool starvation automatically.

## 4\. Google ADK 2.0 System Architecture

The system is architected as an ADK 2.0 multi-agent workflow, coordinating specialized declarative `Agent` units, deterministic controllers, dynamic tools, and shared contextual memory. All LLM-driven components leverage **Gemini 3.7 Flash**.

```
                                +-------------------------------------------+
                                |      TARGET ENVIRONMENT (COMPACT / GCP)   |
                                |     (FastAPI, Cache, Database, Spans)     |
                                +-------------------------------------------+
                                          |                       ^
                 Telemetry & Trace Spans  |                       | Mitigation Hotpatches
                                          v                       |
+---------------------------------------------------------------------------------------------------------+
| GOOGLE ADK 2.0 RUNTIME ENGINE (google-adk)                                                             |
|                                                                                                         |
|   +-------------------------------------------------------------------------------------------------+   |
|   | ADK Multi-Agent Topology (APEX Layer 3 Dynamic Graph)                                           |   |
|   |                                                                                                 |   |
|   |                  +----------------------------------------------+                               |   |
|   |                  |          Supervisor Router Agent             |                               |   |
|   |                  |          (ADK 2.0 LlmAgent: Gemini 3.7 Flash)|                               |   |
|   |                  +----------------------------------------------+                               |   |
|   |                    /                    |                     \                                 |   |
|   |         +---------+                     |                      +----------+                     |   |
|   |         v                               v                                 v                     |   |
|   |  +--------------------+        +--------------------+           +--------------------+          |   |
|   |  | Diagnostic SRE     |        | Remediation Agent  |           | Traffic Shaping    |          |   |
|   |  | Agent (Gemini 3.7) |        | (FinOps / Scaling) |           | Agent (Evolved L3) |          |   |
|   |  +--------------------+        +--------------------+           +--------------------+          |   |
|   |            \                             /                                |                     |   |
|   |             +---------------------------+---------------------------------+                     |   |
|   |                                         |                                                       |   |
|   |                                         v                                                       |   |
|   |                     +---------------------------------------+                                   |   |
|   |                     | Dynamic Tool Registry (APEX Layer 1)  |                                   |   |
|   |                     | (FunctionTool: Injected Hotpatches)   |                                   |   |
|   |                     +---------------------------------------+                                   |   |
|   +-------------------------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------------------------+
                                              | Structured Trace Trees & Logs
                                              v
+---------------------------------------------------------------------------------------------------------+
| OFFLINE RECURSIVE EVOLUTION & SIMULATION ENGINE                                                         |
|                                                                                                         |
|   +---------------------------+    +----------------------------+    +------------------------------+   |
|   |  Trajectory Tree DAG      | -> |  Dream-RSI Replay Engine   | -> |  AgentEvolver Curiosity      |   |
|   |  (DuckDB / BigQuery)      |    |  (Zero-Cost Simulators)    |    |  (Self-Questioning Sandbox)  |   |
|   +---------------------------+    +----------------------------+    +------------------------------+   |
|                 |                                |                                 |                    |
|                 v                                v                                 v                    |
|   +---------------------------+    +----------------------------+    +------------------------------+   |
|   |  Self-Attributing Matrix  | -> |  APEX Layer 2 Distillation | -> |  Automated Graph Mutator     |   |
|   |  (Fine-Grained Credit)    |    |  (Gemini 3.7 Flash Vector) |    |  (Topology Re-wiring)        |   |
|   +---------------------------+    +----------------------------+    +------------------------------+   |
+---------------------------------------------------------------------------------------------------------+

```

&nbsp;

## 5\. Formal Data Contracts & Schemas

To ensure an automated coding agent can implement the entire system without ambiguity, all data models are formally specified using standard Pydantic schemas.

### 5.1 Telemetry & Incident Context

```
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class SystemMetrics(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    active_requests_per_sec: float
    p99_latency_ms: float
    http_5xx_rate: float
    cache_hit_ratio: float
    cache_eviction_count: int
    db_active_connections: int
    db_waiting_threads: int
    db_pool_utilization: float  # Percentage (0.0 - 1.0)

class IncidentContext(BaseModel):
    incident_id: str
    trigger_symptom: str
    initial_metrics: SystemMetrics
    status: str  # "DETECTED", "DIAGNOSING", "MITIGATING", "RESOLVED", "POST_MORTEM"
    timeline_events: List[Dict[str, Any]] = []

```

&nbsp;

### 5.2 Trajectory DAG & Credit Assignment

```
class ActionExecutionSpan(BaseModel):
    span_id: str
    parent_span_id: Optional[str] = None
    agent_name: str
    tool_name: str
    input_parameters: Dict[str, Any]
    output_result: Dict[str, Any]
    pre_state_metrics: SystemMetrics
    post_state_metrics: SystemMetrics
    cost_usd: float = 0.0
    execution_duration_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StepCreditAttribution(BaseModel):
    span_id: str
    tool_name: str
    action_type: str
    delta_latency: float
    delta_5xx_rate: float
    delta_pool_pressure: float
    attribution_score: float  # Scaled [-1.0, +1.0]
    rationale: str

class TrajectoryTree(BaseModel):
    incident_id: str
    spans: List[ActionExecutionSpan]
    root_cause_identified: str
    overall_recovery_duration_sec: float

```

&nbsp;

### 5.3 Evolutionary Models (APEX & Dream-RSI)

```
class DynamicToolDefinition(BaseModel):
    """APEX Layer 1 Tool Patch synthesized by Gemini 3.7 Flash."""
    tool_name: str
    description: str
    python_code: str
    input_schema: Dict[str, Any]
    verification_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class OperationalPrinciple(BaseModel):
    """APEX Layer 2 Distilled Invariant extracted by Gemini 3.7 Flash."""
    principle_id: str
    trigger_pattern: str
    contraindicated_actions: List[str]
    recommended_actions: List[str]
    confidence_score: float
    source_incident_id: str
    embedding: Optional[List[float]] = None

class CounterfactualReplayResult(BaseModel):
    """Dream-RSI Simulation Output."""
    policy_parameter_name: str
    tested_value: Any
    simulated_p99_latency_ms: float
    simulated_5xx_count: int
    simulated_database_max_load: float
    projected_cost_usd: float
    is_pareto_optimal: bool

```

&nbsp;

## 6\. Mathematical Formulations

### 6.1 AgentEvolver: Step-Level Credit Attribution

Given an incident trajectory consisting of $T$ sequential actions $a_1, a_2, \dots, a_T$, where each action ${a}_{t}$ transitions the system state from ${S}_{t-1}$ to ${S}_{t}$.

The system health vector at state ${S}_{t}$ is defined as:

$$
H(S_t) = w_1 \cdot \frac{L(S_t)}{L_{\text{target}}} + w_2 \cdot E(S_t) + w_3 \cdot U_{\text{pool}}(S_t)
$$

&nbsp;

Where:

* $L({S}_{t})$ is the P99 latency in milliseconds ($L_{\text{target}} = 50\text{ ms}$).

* $E({S}_{t})\in [0,1]$ is the HTTP 5xx error rate.

* $U_{\text{pool}}(S_t) \in [0, 1]$ is the database connection pool utilization.

* Weights are normalized: $\sum\limits_{i=1}^{3}{w}_{i}=1.0$ (default configuration: ${w}_{1}=0.35$, ${w}_{2}=0.40$, ${w}_{3}=0.25$).

The fine-grained credit attribution score $C({a}_{t})$ for action ${a}_{t}$ is computed as the normalized change in system health:

$$\Delta H({a}_{t})=H({S}_{t-1})-H({S}_{t})$$

&nbsp;

$$
C(a_t) = \tanh\left(\alpha \cdot \Delta H(a_t) - \beta \cdot \text{Cost}(a_t)\right)
$$

&nbsp;

Where:

* A positive value $C({a}_{t})>0$ indicates that the action contributed to system recovery (rewarded).

* A negative value $C({a}_{t})<0$ indicates that the action exacerbated instability or degraded availability (penalized).

* $\text{Cost}(a_t)$ reflects computational or monetary overhead of the mitigation.

### 6.2 Dream-RSI: Counterfactual Replay Optimization

In Dream-RSI, the trajectory tree $\mathcal{T}_{\text{hist}}$ stores the recorded requests $R = \{r_1, r_2, \dots, r_M\}$ over the incident timeline. The objective is to find the optimal rate limit policy parameter $\theta^* = (\text{capacity}, \text{replenishment\_rate})$ that maximizes accepted requests while strictly enforcing database pool stability:

$$
\theta^* = \arg\max_{\theta \in \Theta} \sum_{k=1}^M \text{Admit}(r_k; \theta)
$$

&nbsp;

Subject to the simulated invariant:

$$
\max_{t} U_{\text{pool}}^{\text{sim}}(t; \theta) \le U_{\text{threshold}} \quad (\text{e.g., } 0.85)
$$

&nbsp;

$$
\text{Simulated } \text{P99 Latency}(t; \theta) \le 100\text{ ms}
$$

&nbsp;

Because all request timestamps and cache miss flags are recorded in local DuckDB tables, $\text{Admit}(r_k; \theta)$ and $U_{\text{pool}}^{\text{sim}}(t; \theta)$ are computed purely through vectorized SQL queries without making any live network calls or running physical services.

## 7\. Component Specifications & Logic

### 7.1 Compact In-Memory Target Environment

* **FastAPI Server (`app/target_env/server.py`):** Exposes `/checkout` and `/metrics`.

* **In-Memory Cache (`fakeredis`):** Initialized with `maxmemory 1mb` and `maxmemory-policy allkeys-lru`.

* **In-Memory Relational Database (`SQLite :memory:`):** Wrapped with a threading `Semaphore(value=2)` to simulate connection pool starvation under concurrent load.

* **Telemetry Collector:** An in-process OpenTelemetry tracer that records execution traces into local memory buffers.

### 7.2 ADK 2.0 Multi-Agent Fast Loop (Gemini 3.7 Flash)

* **Supervisor Router Agent (`LlmAgent`):**

  * Model: `gemini-3.7-flash` (leveraging native dynamic reasoning to orchestrate sub-agents, validate guardrails, and arbitrate mitigation options).

  * Instructions: Ingests telemetry alerts; delegates diagnostic queries to `DiagnosticAgent`; evaluates recommendations; verifies guardrails; triggers dynamic tool execution.

* **Diagnostic SRE Agent (`Agent`):**

  * Model: `gemini-3.7-flash`.

  * Tools: `query_cache_stats`, `inspect_db_connections`, `retrieve_historical_principles`.

  * Logic: Identifies correlations between key evictions and database pool lockups.

* **Self-Navigating Principle Retrieval:**

  * Uses in-memory vector embeddings generated via `text-embedding-004` (or cosine similarity over local JSON/ChromaDB) to retrieve prior incident lessons before recommending dangerous actions.

### 7.3 APEX Tri-Level Evolutionary Engine (Gemini 3.7 Flash Powered)

* **Layer 1 (Harness Patching):**

  * When no built-in tool solves the incident, Gemini 3.7 Flash generates Python source code for an in-memory `TokenBucketRateLimiter`.

  * The code is validated against an AST safety parser (disallowing `os`, `sys`, `subprocess`) and dynamically registered as an active ADK `FunctionTool` via `agent.add_tool()`.

* **Layer 2 (Principle Distillation):**

  * Upon incident resolution, Gemini 3.7 Flash analyzes the full execution trajectory, extracts generalized invariants, and writes structured rules to the semantic principle store.  
* **Layer 3 (Topology Re-Wiring):**

  * Dynamically reconfigures the ADK multi-agent structure. It instantiates a permanent `TrafficShapingAgent` (backed by Gemini 3.7 Flash), adds it as a sub-agent to the Supervisor, and updates routing instructions.

### 7.4 Dream-RSI: DuckDB Replay Simulator

* **Trajectory Ingestion:** Dumps trace logs and request streams into in-memory DuckDB tables (`traces`, `requests`, `metrics`).

* **Counterfactual Policy Sweep:** Executes parameterized SQL queries simulating token bucket leaks against the exact historical timestamps to determine the optimal rate-limiting threshold.

### 7.5 AgentEvolver: Curiosity & Shadow Sandbox

* **Self-Questioning Engine:** Gemini 3.7 Flash generates synthetic "What If?" hypotheses (e.g., *"What if the flash sale duration doubles while cache memory is halved?"*).

* **Fault Injection:** Triggers synthetic cache drops and concurrent request bursts against the shadow test environment to verify that the newly wired `TrafficShapingAgent` automatically maintains system availability.

## 8\. Enterprise Cloud vs Compact In-Memory Mapping

| Architectural Role | Compact In-Memory Demo (Single Process) | Enterprise Production Stack (Google Cloud) |
| :---- | :---- | :---- |
| **Agent Orchestration** | `google-adk` local Python runtime | Vertex AI Reasoning Engine \+ Cloud Run |
| **Primary LLM Model** | Gemini 3.7 Flash API (`gemini-3.7-flash`) | Gemini 3.7 Flash on Vertex AI & Gemini Enterprise |
| **Cache Store** | `fakeredis` with LRU eviction policy | Cloud Memorystore for Redis |
| **Relational DB** | SQLite `:memory:` with `threading.Semaphore(2)` | Cloud SQL (PostgreSQL) with limited pool |
| **Trajectory Store** | In-Memory `DuckDB` table | Google BigQuery Partitioned Tables |
| **Vector Memory** | In-Memory `ChromaDB` / NumPy cosine matrix | Vertex AI Vector Search |
| **Distributed Tracing** | In-Memory OpenTelemetry SDK Exporter | Google Cloud Trace & Cloud Logging |
| **Tool Sandbox** | In-process AST-inspected execution | Cloud Run Ephemeral Jobs / gVisor |

&nbsp;

## 9\. Complete Project File Manifest

A coding agent implementing this system should generate the following file tree:

```
project_chrysalis/
├── README.md                           # Execution guide & CLI commands
├── pyproject.toml                      # Dependencies (google-adk, google-genai, fastapi, fakeredis, duckdb, etc.)
├── app/
│   ├── __init__.py
│   ├── config.py                       # Global settings (specifying gemini-3.7-flash model ID)
│   ├── target_env/                     # The simulated target infrastructure
│   │   ├── __init__.py
│   │   ├── server.py                   # FastAPI app with /checkout and /metrics
│   │   ├── cache_service.py            # fakeredis wrapper with memory caps
│   │   ├── db_service.py               # SQLite connection pool with semaphore locks
│   │   └── telemetry.py                # In-memory metrics buffer and span collector
│   ├── adk_agents/                     # Google ADK 2.0 multi-agent implementation (Gemini 3.7 Flash)
│   │   ├── __init__.py
│   │   ├── schemas.py                  # Pydantic models for metrics, traces, and principles
│   │   ├── supervisor.py               # Root Supervisor Router Agent (gemini-3.7-flash)
│   │   ├── diagnostic_agent.py         # SRE Diagnostic specialist (gemini-3.7-flash)
│   │   ├── tools_library.py            # Standard read-only diagnostic tools
│   │   └── dynamic_registry.py         # APEX Layer 1 Dynamic Tool Loader
│   ├── evolution/                      # The offline learning engines
│   │   ├── __init__.py
│   │   ├── credit_attribution.py       # AgentEvolver Self-Attributing math engine
│   │   ├── principle_store.py          # APEX Layer 2 vector memory & distillation (gemini-3.7-flash)
│   │   ├── topology_mutator.py         # APEX Layer 3 graph re-wiring logic
│   │   ├── dream_rsi_replay.py         # Dream-RSI DuckDB counterfactual replay engine
│   │   └── self_questioner.py          # AgentEvolver shadow sandbox & chaos injector (gemini-3.7-flash)
│   └── demo_runner.py                  # End-to-end 5-minute automated demonstration script
└── tests/
    ├── test_stampede_simulation.py     # Verifies cache stampede reproduction
    ├── test_apex_hotpatch.py           # Tests dynamic tool generation & execution
    └── test_dream_rsi.py               # Tests DuckDB counterfactual replay accuracy

```

&nbsp;

## 10\. Step-by-Step Implementation Guide for Coding Agents

### Step 1: Target Environment Setup

1. Implement `app/target_env/cache_service.py` using `fakeredis`. Configure a strict key limit (5 keys) and a custom eviction listener that logs key drops to the telemetry buffer.

2. Implement `app/target_env/db_service.py` using SQLite in-memory mode. Enforce concurrency limits using `threading.Semaphore(2)` and add a simulated $100\text{ ms}$ processing delay to simulate real database query costs.

3. Implement `app/target_env/server.py` exposing:

   * `POST /checkout`: Attempts cache retrieval. On miss, acquires a database connection, performs cart reconstruction, updates the cache, and returns `HTTP 200`. If database acquisition times out ($>500\text{ ms}$), returns `HTTP 500`.

   * `GET /metrics`: Returns `SystemMetrics` (active connections, waiting threads, P99 latency, 5xx rate).

### Step 2: ADK 2.0 Multi-Agent Setup (Gemini 3.7 Flash)

1. Implement `app/adk_agents/tools_library.py`: Provide `FunctionTool` wrappers for `read_metrics`, `check_cache_status`, and `inspect_db_pool`.

2. Implement `app/adk_agents/supervisor.py`: Construct the root agent using `from google.adk import Agent` configured with `model="gemini-3.7-flash"`. Define explicit routing instructions to delegate diagnostics to the `DiagnosticAgent`.

3. Implement `app/adk_agents/diagnostic_agent.py`: Construct the SRE diagnostic agent with `model="gemini-3.7-flash"` and bind the diagnostic tools.

4. Implement `app/adk_agents/dynamic_registry.py`: Provide `register_dynamic_tool(agent, code_string)` which parses generated Python code, validates safety, wraps it in an ADK `FunctionTool`, and registers it to the active agent tool set.

### Step 3: APEX Evolutionary Loop Implementation

1. **Layer 1:** In the triage loop, when the root cause is diagnosed as an ingress surge overwhelming database thread capacity, prompt Gemini 3.7 Flash to output a token-bucket rate limiter. Compile and register this limiter dynamically into the FastAPI middleware pipeline.

2. **Layer 2:** In `app/evolution/principle_store.py`, define an in-memory vector store that indexes invariant operational principles. Store the lesson distilled by Gemini 3.7 Flash: *"Do not restart database under cache-eviction connection saturation; deploy boundary rate-limiting first."*

3. **Layer 3:** In `app/evolution/topology_mutator.py`, programmatically modify the ADK agent topology. Instantiate a new `TrafficShapingAgent` (backed by `gemini-3.7-flash` with tools `set_rate_limit`, `inspect_queue_depth`) and link it to the `Supervisor` via sub-agent delegation.

### Step 4: AgentEvolver & Dream-RSI Implementation

1. Implement `app/evolution/credit_attribution.py`: Ingest the in-memory execution trace spans. Compute $\Delta H({a}_{t})$ using the mathematical health formula in Section 6.1. Assign explicit scalar credits to each step and print the attribution matrix.

2. Implement `app/evolution/dream_rsi_replay.py`: Load the recorded incident requests into DuckDB. Run parameterized simulation queries over token leak rates ($10$ to $200\text{ req/s}$) to discover the capacity value that maximizes throughput while keeping simulated database thread lockups at zero.

3. Implement `app/evolution/self_questioner.py`: Spin up an isolated shadow instance of the target environment. Prompt Gemini 3.7 Flash to formulate edge-case stress scenarios, fire a synthetic cache purge under load, and assert that the evolved multi-agent graph (with the new `TrafficShapingAgent`) handles the surge with zero `HTTP 500` errors.

## 11\. End-to-End Demo Script Walkthrough (`demo_runner.py`)

The demo runner script executes the complete 5-minute autonomous lifecycle:

* **\[Phase 1: 00:00 \- 01:00\] In-Memory Cache Stampede**

  * Launches FastAPI target server.

  * Fires 50 concurrent async checkout requests.

  * `fakeredis` evicts keys; SQLite connections lock; P99 latency jumps to $3{,}200\text{ ms}$; HTTP 500 rate reaches $68\%$.

* **\[Phase 2: 01:00 \- 02:30\] ADK 2.0 Fast Loop Triage & APEX Layer 1 Hotpatch**

  * ADK Supervisor (Gemini 3.7 Flash) queries `DiagnosticAgent`.

  * *Self-Navigating* memory blocks dangerous database reboot commands.

  * Gemini 3.7 Flash synthesizes `TokenBucketRateLimiter` code (APEX L1).

  * Dynamic tool registers and activates: non-critical requests are throttled into a virtual queue.

  * Database connections unlock; latency drops to $35\text{ ms}$; HTTP 500 rate returns to $0\%$.

* **\[Phase 3: 02:30 \- 03:45\] Credit Attribution & Topological Evolution**

  * *Self-Attributing* module evaluates trace spans:

    * DB Connection Timeout Increase: $-0.85$ credit.

    * Dynamic Rate Limiter Patch: $+0.94$ credit.

  * APEX Layer 2 distills invariant principle into memory using Gemini 3.7 Flash.

  * APEX Layer 3 mutates ADK graph: introduces permanent `TrafficShapingAgent` (Gemini 3.7 Flash).

* **\[Phase 4: 03:45 \- 05:00\] Dream-RSI Replay & Self-Questioning Verification**

  * Trajectory exported to in-memory DuckDB.

  * Dream-RSI runs 1,000 counterfactual parameter variations offline in $350\text{ ms}$, discovering the exact optimal capacity ($42\text{ req/s}$).

  * AgentEvolver (Gemini 3.7 Flash) runs a shadow chaos probe, verifying that a subsequent cache eviction causes zero service degradation.