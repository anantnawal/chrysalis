"""In-memory SQLite database service with strict connection pool semaphore and simulated query latency."""
import sqlite3
import threading
import time
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.config import (
    DB_MAX_CONNECTIONS,
    DB_PROCESSING_DELAY_SEC,
    DB_ACQUISITION_TIMEOUT_SEC,
)


class DatabaseConnectionTimeoutError(Exception):
    """Raised when acquiring a database connection pool slot times out."""
    pass


class DatabaseService:
    """In-memory SQLite database simulating connection pool starvation and processing delays."""

    def __init__(
        self,
        max_connections: int = DB_MAX_CONNECTIONS,
        query_delay_sec: float = DB_PROCESSING_DELAY_SEC,
        acquisition_timeout_sec: float = DB_ACQUISITION_TIMEOUT_SEC,
    ):
        self.max_connections = max_connections
        self.query_delay_sec = query_delay_sec
        self.acquisition_timeout_sec = acquisition_timeout_sec

        self._semaphore = threading.Semaphore(value=self.max_connections)
        self._stats_lock = threading.Lock()
        self._active_connections = 0
        self._waiting_threads = 0
        self._total_queries = 0
        self._total_timeouts = 0
        # Peak saturation observed in the current telemetry window (bursts finish before
        # metrics are sampled, so instantaneous utilization alone would always read ~0%).
        self._peak_active_connections = 0
        self._window_timeouts = 0

        # SQLite connection. A single sqlite3 connection object is NOT safe for concurrent
        # use across threads, so every statement is serialized through _sql_lock.
        self._sql_lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize tables and seed base shopping cart states."""
        with self._sql_lock:
            self._init_schema_locked()

    def _init_schema_locked(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shopping_carts (
                cart_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                items_json TEXT NOT NULL,
                total_amount REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Prepopulate demo carts
        now_iso = datetime.now(timezone.utc).isoformat()
        sample_carts = [
            ("cart_101", "user_101", json.dumps([{"sku": "LAPTOP-X1", "qty": 1, "price": 1299.99}]), 1299.99, now_iso),
            ("cart_102", "user_102", json.dumps([{"sku": "HEADPHONE-PRO", "qty": 2, "price": 199.50}]), 399.00, now_iso),
            ("cart_103", "user_103", json.dumps([{"sku": "SMART-WATCH", "qty": 1, "price": 249.00}]), 249.00, now_iso),
            ("cart_104", "user_104", json.dumps([{"sku": "4K-MONITOR", "qty": 1, "price": 450.00}]), 450.00, now_iso),
            ("cart_105", "user_105", json.dumps([{"sku": "MECH-KEYBOARD", "qty": 1, "price": 120.00}]), 120.00, now_iso),
        ]
        cursor.executemany(
            "INSERT OR REPLACE INTO shopping_carts VALUES (?, ?, ?, ?, ?)",
            sample_carts,
        )
        self._conn.commit()

    def query_cart(self, cart_id: str) -> Optional[Dict[str, Any]]:
        """Query shopping cart by ID, acquiring a connection pool slot under timeout constraint."""
        with self._stats_lock:
            self._waiting_threads += 1

        # Hold a reference to the semaphore we acquire from, so a concurrent reboot()
        # (which swaps in a fresh semaphore) cannot cause us to release the wrong one.
        semaphore = self._semaphore
        acquired = semaphore.acquire(timeout=self.acquisition_timeout_sec)

        with self._stats_lock:
            self._waiting_threads -= 1

        if not acquired:
            with self._stats_lock:
                self._total_timeouts += 1
                self._window_timeouts += 1
            raise DatabaseConnectionTimeoutError(
                f"Connection pool exhausted: Failed to acquire DB slot within {self.acquisition_timeout_sec*1000:.0f}ms. "
                f"(Active: {self._active_connections}/{self.max_connections}, Waiting: {self._waiting_threads})"
            )

        try:
            with self._stats_lock:
                self._active_connections += 1
                self._total_queries += 1
                self._peak_active_connections = max(self._peak_active_connections, self._active_connections)

            # Simulate backend IO latency under load
            time.sleep(self.query_delay_sec)

            with self._sql_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT cart_id, user_id, items_json, total_amount, updated_at FROM shopping_carts WHERE cart_id = ?",
                    (cart_id,),
                )
                row = cursor.fetchone()
            if row:
                return {
                    "cart_id": row[0],
                    "user_id": row[1],
                    "items": json.loads(row[2]),
                    "total_amount": row[3],
                    "updated_at": row[4],
                }
            # Fallback mock cart if new id generated during burst
            return {
                "cart_id": cart_id,
                "user_id": f"guest_{cart_id}",
                "items": [{"sku": "SALE-ITEM-SPECIAL", "qty": 1, "price": 49.99}],
                "total_amount": 49.99,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            with self._stats_lock:
                self._active_connections = max(self._active_connections - 1, 0)
            semaphore.release()

    def reboot(self) -> None:
        """Simulate database restart: forcibly interrupts and reinitializes."""
        with self._stats_lock:
            # Drain connections and re-init
            self._active_connections = 0
            self._waiting_threads = 0
            # Reset semaphore
            self._semaphore = threading.Semaphore(value=self.max_connections)
            self._peak_active_connections = 0
            self._window_timeouts = 0
        self._init_schema()

    def reset_window(self) -> None:
        """Start a new observation window for peak saturation tracking."""
        with self._stats_lock:
            self._peak_active_connections = self._active_connections
            self._window_timeouts = 0

    def get_pool_stats(self) -> Dict[str, Any]:
        """Return real-time connection pool metrics."""
        with self._stats_lock:
            utilization = (
                self._active_connections / self.max_connections
                if self.max_connections > 0
                else 0.0
            )
            # Peak window saturation: 100% if any request timed out waiting for a slot.
            if self._window_timeouts > 0:
                peak_utilization = 1.0
            elif self.max_connections > 0:
                peak_utilization = self._peak_active_connections / self.max_connections
            else:
                peak_utilization = 0.0
            return {
                "max_connections": self.max_connections,
                "active_connections": self._active_connections,
                "waiting_threads": self._waiting_threads,
                "pool_utilization": round(utilization, 2),
                "peak_pool_utilization": round(peak_utilization, 2),
                "window_timeouts": self._window_timeouts,
                "total_queries": self._total_queries,
                "total_timeouts": self._total_timeouts,
            }
