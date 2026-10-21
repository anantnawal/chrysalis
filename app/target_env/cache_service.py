"""In-memory cache service using fakeredis with strict LRU capacity and eviction listener."""
import threading
from collections import OrderedDict
from typing import Optional, Dict, Any, Callable, List
import fakeredis
from app.config import CACHE_MAX_KEYS


class CacheService:
    """In-memory cache wrapping fakeredis with LRU tracking and eviction hooks."""

    def __init__(self, max_keys: int = CACHE_MAX_KEYS, eviction_listener: Optional[Callable[[str], None]] = None):
        self.max_keys = max_keys
        self.eviction_listener = eviction_listener
        self._redis = fakeredis.FakeRedis(decode_responses=True)
        self._lock = threading.Lock()
        self._access_order: OrderedDict[str, float] = OrderedDict()
        self.hits: int = 0
        self.misses: int = 0
        self.evictions: int = 0
        self.evicted_keys_log: List[Dict[str, Any]] = []

    def get(self, key: str) -> Optional[str]:
        """Retrieve key value from cache, updating LRU access order."""
        with self._lock:
            val = self._redis.get(key)
            if val is not None:
                self.hits += 1
                if key in self._access_order:
                    self._access_order.move_to_end(key)
                return val
            else:
                self.misses += 1
                return None

    def set(self, key: str, value: str) -> None:
        """Store key-value pair, enforcing max_keys capacity via LRU eviction."""
        with self._lock:
            # Check if key is new and capacity is reached
            if not self._redis.exists(key) and len(self._access_order) >= self.max_keys:
                # Evict least recently used key (first item in OrderedDict)
                evicted_key, _ = self._access_order.popitem(last=False)
                self._redis.delete(evicted_key)
                self.evictions += 1
                eviction_event = {"key": evicted_key, "action": "LRU_EVICTED"}
                self.evicted_keys_log.append(eviction_event)
                if self.eviction_listener:
                    try:
                        self.eviction_listener(evicted_key)
                    except Exception:
                        pass

            self._redis.set(key, value)
            self._access_order[key] = True
            self._access_order.move_to_end(key)

    def delete(self, key: str) -> bool:
        """Explicitly delete a key."""
        with self._lock:
            if key in self._access_order:
                del self._access_order[key]
            return bool(self._redis.delete(key))

    def purge(self) -> int:
        """Purge all keys from cache (simulating cache wipe/drop)."""
        with self._lock:
            count = len(self._access_order)
            keys = list(self._access_order.keys())
            for k in keys:
                self._redis.delete(k)
                if self.eviction_listener:
                    try:
                        self.eviction_listener(k)
                    except Exception:
                        pass
            self.evictions += count
            self._access_order.clear()
            return count

    def get_stats(self) -> Dict[str, Any]:
        """Return cache health metrics."""
        with self._lock:
            total = self.hits + self.misses
            hit_ratio = (self.hits / total) if total > 0 else 1.0
            return {
                "active_keys": len(self._access_order),
                "max_keys": self.max_keys,
                "hits": self.hits,
                "misses": self.misses,
                "hit_ratio": round(hit_ratio, 3),
                "eviction_count": self.evictions,
                "recent_evictions": self.evicted_keys_log[-5:],
            }

    def reset_stats(self) -> None:
        """Reset operational hit/miss counters."""
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.evictions = 0
            self.evicted_keys_log.clear()
