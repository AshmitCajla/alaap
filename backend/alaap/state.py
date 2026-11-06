"""Live conversation state (message history + skill context).
Redis when REDIS_URL is set, otherwise an in-process dict."""

import json
import threading

from . import config

TTL_SECONDS = 6 * 3600


class MemoryStore:
    def __init__(self):
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            raw = self._data.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = json.dumps(value, default=str)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class RedisStore:
    def __init__(self, url: str):
        import redis

        self.r = redis.Redis.from_url(url)

    def get(self, key: str) -> dict | None:
        raw = self.r.get(f"alaap:{key}")
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict) -> None:
        self.r.set(f"alaap:{key}", json.dumps(value, default=str), ex=TTL_SECONDS)

    def delete(self, key: str) -> None:
        self.r.delete(f"alaap:{key}")


_store = None


def store():
    global _store
    if _store is None:
        _store = RedisStore(config.REDIS_URL) if config.REDIS_URL else MemoryStore()
    return _store
