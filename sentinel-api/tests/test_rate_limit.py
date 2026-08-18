"""Rate limiter backend selection + in-memory fallback tests."""

import time

import pytest

from app.security import RateLimiter


class TestMemoryBackend:
    def test_allows_up_to_rate(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        rl = RateLimiter(rate=3, per=60)
        assert rl.backend == "memory"
        assert [rl.is_allowed("ip1") for _ in range(3)] == [True, True, True]

    def test_blocks_over_rate(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        rl = RateLimiter(rate=2, per=60)
        assert rl.is_allowed("ip1") is True
        assert rl.is_allowed("ip1") is True
        assert rl.is_allowed("ip1") is False

    def test_keys_are_independent(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        rl = RateLimiter(rate=1, per=60)
        assert rl.is_allowed("a") is True
        assert rl.is_allowed("a") is False
        assert rl.is_allowed("b") is True  # different key unaffected

    def test_window_expiry(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        rl = RateLimiter(rate=1, per=1)
        assert rl.is_allowed("ip") is True
        assert rl.is_allowed("ip") is False
        # Backdate the bucket entry beyond the window
        rl.buckets["ip"][:] = [time.time() - 5]
        assert rl.is_allowed("ip") is True

    def test_remaining_counts_down(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        rl = RateLimiter(rate=3, per=60)
        assert rl.remaining("ip") == 3
        rl.is_allowed("ip")
        assert rl.remaining("ip") == 2


class FakeRedis:
    """Minimal in-test Redis stub (INCR/EXPIRE/GET)."""

    def __init__(self):
        self.store = {}
        self.fail = False

    def incr(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, ttl):
        return True

    def get(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        return self.store.get(key)


class TestRedisBackend:
    def test_uses_redis_when_available(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        rl = RateLimiter(rate=2, per=60)
        rl._redis = FakeRedis()
        assert rl.backend == "redis"
        assert rl.is_allowed("ip") is True
        assert rl.is_allowed("ip") is True
        assert rl.is_allowed("ip") is False  # over rate

    def test_falls_back_to_memory_on_error(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        rl = RateLimiter(rate=1, per=60)
        fake = FakeRedis()
        rl._redis = fake
        assert rl.is_allowed("ip") is True   # redis path, count=1
        fake.fail = True
        # Redis error -> transparent memory fallback, still enforces
        assert rl.is_allowed("ip") is True   # memory bucket empty -> allowed

    def test_no_url_means_memory(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        rl = RateLimiter(rate=5, per=60)
        assert rl._redis is None
        assert rl.backend == "memory"
