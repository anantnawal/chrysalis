"""Dream-RSI: DuckDB In-Memory Counterfactual Replay Simulator (Section 6.2 Mathematical Formulations)."""
import time
from typing import List, Dict, Any, Tuple
import duckdb
from app.adk_agents.schemas import CounterfactualReplayResult
from app.config import DB_MAX_CONNECTIONS, DB_PROCESSING_DELAY_SEC, DB_ACQUISITION_TIMEOUT_SEC


class DreamRSIReplayEngine:
    """Zero-risk offline replay meta-simulator executing vectorized counterfactual sweeps in DuckDB."""

    def __init__(
        self,
        db_max_connections: int = DB_MAX_CONNECTIONS,
        db_query_delay_sec: float = DB_PROCESSING_DELAY_SEC,
        db_acquisition_timeout_sec: float = DB_ACQUISITION_TIMEOUT_SEC,
        headroom_target: float = 0.85,
    ):
        self.db_max_connections = db_max_connections
        self.db_query_delay_sec = db_query_delay_sec
        self.db_acquisition_timeout_sec = db_acquisition_timeout_sec
        self.headroom_target = headroom_target
        self.conn = duckdb.connect(database=":memory:")
        self._init_duckdb_schema()

    def _init_duckdb_schema(self) -> None:
        """Create analytical tables for requests, execution traces, and simulation outputs."""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recorded_requests (
                seq_id INTEGER PRIMARY KEY,
                timestamp VARCHAR,
                request_id VARCHAR,
                endpoint VARCHAR,
                status_code INTEGER,
                latency_ms DOUBLE,
                cache_miss INTEGER,
                admitted INTEGER
            );
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS counterfactual_runs (
                tested_rate DOUBLE,
                tested_capacity INTEGER,
                admitted_count INTEGER,
                throttled_count INTEGER,
                simulated_p99_latency DOUBLE,
                simulated_5xx_count INTEGER,
                simulated_max_db_load DOUBLE,
                is_pareto_optimal BOOLEAN
            );
            """
        )

    def load_trajectory_data(self, request_logs: List[Dict[str, Any]]) -> int:
        """Load recorded incident request stream into in-memory DuckDB."""
        self.conn.execute("DELETE FROM recorded_requests;")
        if not request_logs:
            # Seed synthetic realistic Black Friday burst trajectory if empty
            request_logs = self._generate_synthetic_burst_logs()

        seq = 1
        insert_tuples = []
        for log in request_logs:
            insert_tuples.append((
                seq,
                str(log.get("timestamp", "")),
                str(log.get("request_id", f"req_{seq}")),
                str(log.get("endpoint", "/checkout")),
                int(log.get("status_code", 200)),
                float(log.get("latency_ms", 50.0)),
                int(log.get("cache_miss", 1)),
                int(log.get("admitted", 1)),
            ))
            seq += 1

        self.conn.executemany(
            "INSERT INTO recorded_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            insert_tuples,
        )
        return len(insert_tuples)

    def _generate_synthetic_burst_logs(self) -> List[Dict[str, Any]]:
        """Generate high-fidelity synthetic Black Friday burst requests for simulation."""
        logs = []
        for i in range(100):
            # First 50 requests during stampede suffered cache miss and lockup
            cache_miss = 1 if i < 70 else 0
            status = 500 if (cache_miss and i % 3 != 0) else 200
            latency = 3200.0 if status == 500 else (120.0 if cache_miss else 15.0)
            logs.append({
                "timestamp": f"2026-10-02T12:00:{i:02d}Z",
                "request_id": f"burst_req_{i:03d}",
                "endpoint": "/checkout",
                "status_code": status,
                "latency_ms": latency,
                "cache_miss": cache_miss,
                "admitted": 1,
            })
        return logs

    def run_counterfactual_sweep(
        self,
        rates_to_test: List[float] = None,
        capacities_to_test: List[int] = None,
    ) -> Tuple[List[CounterfactualReplayResult], CounterfactualReplayResult, float]:
        """Run vectorized sweep over token bucket parameters to discover Pareto-optimal policy."""
        if rates_to_test is None:
            # Test rates from 10 to 200 req/s in increments
            rates_to_test = [float(r) for r in range(10, 210, 10)]
        if capacities_to_test is None:
            # Test capacities from 10 to 100
            capacities_to_test = [10, 20, 30, 42, 50, 75, 100]

        total_requests = self.conn.execute("SELECT COUNT(*) FROM recorded_requests").fetchone()[0]
        total_misses = self.conn.execute("SELECT COUNT(*) FROM recorded_requests WHERE cache_miss = 1").fetchone()[0]

        start_time = time.perf_counter()
        results: List[CounterfactualReplayResult] = []

        # Backend envelope derived from the target environment's connection pool:
        #   Sustained throughput  = N / query_delay              (e.g. 2 / 0.1s  = 20 queries/sec)
        #   Burst tolerance       = N * (timeout / query_delay)  (e.g. 2 * 5     = 10 concurrent cold misses)
        # A token bucket admits up to `capacity` requests instantaneously, so the burst check
        # assumes the worst case (cold cache: every admitted request misses), while the
        # sustained check uses the observed miss ratio from the recorded trajectory.
        max_safe_backend_throughput = self.db_max_connections / self.db_query_delay_sec
        max_safe_burst = self.db_max_connections * (self.db_acquisition_timeout_sec / self.db_query_delay_sec)
        miss_ratio = (total_misses / total_requests) if total_requests > 0 else 0.5

        for cap in capacities_to_test:
            for rate in rates_to_test:
                sustained_load = (rate * miss_ratio) / max_safe_backend_throughput
                burst_load = cap / max_safe_burst
                load = max(sustained_load, burst_load)
                sim_pool_load = round(min(load, 1.0), 2)

                if load <= 1.0:
                    # Healthy zone: no thread starvation, mild queueing latency
                    sim_5xx = 0
                    sim_p99 = 25.0 + (load * 30.0)
                else:
                    # Starvation zone: threads queue past the acquisition timeout
                    excess_ratio = 1.0 - (1.0 / load)
                    sim_5xx = int(round(total_requests * excess_ratio * 0.7))
                    sim_p99 = 500.0 + (excess_ratio * 3500.0)

                # SLO-feasible frontier: zero 5xx with >= 15% pool headroom
                is_pareto = (sim_5xx == 0 and load <= self.headroom_target)

                result_entry = CounterfactualReplayResult(
                    policy_parameter_name="token_replenishment_rate",
                    tested_value={"capacity": cap, "rate_req_sec": rate},
                    simulated_p99_latency_ms=round(sim_p99, 1),
                    simulated_5xx_count=sim_5xx,
                    simulated_database_max_load=sim_pool_load,
                    projected_cost_usd=0.0,
                    is_pareto_optimal=is_pareto,
                )
                results.append(result_entry)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Select the optimal policy on the SLO-feasible frontier
        pareto_candidates = [r for r in results if r.is_pareto_optimal]
        if pareto_candidates:
            # Maximize sustained throughput first, then burst tolerance
            optimal_policy = max(
                pareto_candidates,
                key=lambda r: (r.tested_value["rate_req_sec"], r.tested_value["capacity"]),
            )
        else:
            # Fallback safest
            optimal_policy = min(results, key=lambda r: (r.simulated_5xx_count, r.simulated_database_max_load))

        return results, optimal_policy, elapsed_ms
