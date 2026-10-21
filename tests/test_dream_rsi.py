"""Unit tests verifying Dream-RSI DuckDB counterfactual replay optimization."""
import pytest
from app.evolution.dream_rsi_replay import DreamRSIReplayEngine


def test_dream_rsi_duckdb_ingestion():
    """Verify that request traces are properly ingested into DuckDB tables."""
    engine = DreamRSIReplayEngine()
    dummy_logs = [
        {"timestamp": "2026-10-02T12:00:00Z", "request_id": "r1", "endpoint": "/checkout", "status_code": 200, "latency_ms": 25.0, "cache_miss": 0, "admitted": 1},
        {"timestamp": "2026-10-02T12:00:01Z", "request_id": "r2", "endpoint": "/checkout", "status_code": 500, "latency_ms": 3200.0, "cache_miss": 1, "admitted": 1},
    ]
    count = engine.load_trajectory_data(dummy_logs)
    assert count == 2

    row_count = engine.conn.execute("SELECT COUNT(*) FROM recorded_requests").fetchone()[0]
    assert row_count == 2


def test_dream_rsi_counterfactual_sweep_pareto():
    """Verify that Dream-RSI discovers a Pareto-optimal configuration with zero 5xx errors."""
    engine = DreamRSIReplayEngine()
    engine.load_trajectory_data([])  # Generates realistic synthetic burst

    results, optimal_policy, elapsed_ms = engine.run_counterfactual_sweep(
        rates_to_test=[10.0, 20.0, 40.0, 80.0, 150.0],
        capacities_to_test=[5, 8, 10, 42],
    )

    assert len(results) == 20
    assert elapsed_ms < 1000.0  # Offline sweep should finish in milliseconds
    assert optimal_policy is not None
    assert optimal_policy.simulated_5xx_count == 0
    assert optimal_policy.simulated_database_max_load <= 0.85
    # Burst capacity must leave headroom below the pool's cold-miss burst tolerance (2 conns * 500ms/100ms = 10)
    assert optimal_policy.tested_value["capacity"] < 10
    # Oversized buckets (42 tokens) must be flagged as unsafe by the replay
    assert all(not r.is_pareto_optimal for r in results if r.tested_value["capacity"] == 42)
