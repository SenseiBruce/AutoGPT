"""Tests for cache utilities."""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from backend.util.cache import cached, clear_thread_cache, thread_cached

class TestSharedCache:
    """Tests for shared_cache (Redis-backed) functionality."""

    def test_sync_shared_cache_basic(self):
        """Test basic shared cache functionality with sync function."""
        call_count = 0

        @cached(ttl_seconds=30, shared_cache=True)
        def shared_sync_function(x: int, y: int = 0) -> int:
            nonlocal call_count
            call_count += 1
            return x + y

        # Clear any existing cache
        shared_sync_function.cache_clear()

        # First call
        result1 = shared_sync_function(10, 20)
        assert result1 == 30
        assert call_count == 1

        # Second call - should use Redis cache
        result2 = shared_sync_function(10, 20)
        assert result2 == 30
        assert call_count == 1

        # Different args - should call function again
        result3 = shared_sync_function(15, 25)
        assert result3 == 40
        assert call_count == 2

        # Cleanup
        shared_sync_function.cache_clear()

    @pytest.mark.asyncio
    async def test_async_shared_cache_basic(self):
        """Test basic shared cache functionality with async function."""
        call_count = 0

        @cached(ttl_seconds=30, shared_cache=True)
        async def shared_async_function(x: int, y: int = 0) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x + y

        # Clear any existing cache
        shared_async_function.cache_clear()

        # First call
        result1 = await shared_async_function(10, 20)
        assert result1 == 30
        assert call_count == 1

        # Second call - should use Redis cache
        result2 = await shared_async_function(10, 20)
        assert result2 == 30
        assert call_count == 1

        # Different args - should call function again
        result3 = await shared_async_function(15, 25)
        assert result3 == 40
        assert call_count == 2

        # Cleanup
        shared_async_function.cache_clear()

    def test_shared_cache_ttl_refresh(self):
        """Test TTL refresh functionality with shared cache."""
        call_count = 0

        @cached(ttl_seconds=2, shared_cache=True, refresh_ttl_on_get=True)
        def ttl_refresh_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 10

        # Clear any existing cache
        ttl_refresh_function.cache_clear()

        # First call
        result1 = ttl_refresh_function(3)
        assert result1 == 30
        assert call_count == 1

        # Wait 1 second
        time.sleep(1)

        # Second call - should refresh TTL and use cache
        result2 = ttl_refresh_function(3)
        assert result2 == 30
        assert call_count == 1

        # Wait another 1.5 seconds (total 2.5s from first call, 1.5s from second)
        time.sleep(1.5)

        # Third call - TTL should have been refreshed, so still cached
        result3 = ttl_refresh_function(3)
        assert result3 == 30
        assert call_count == 1

        # Wait 2.1 seconds - now it should expire
        time.sleep(2.1)

        # Fourth call - should call function again
        result4 = ttl_refresh_function(3)
        assert result4 == 30
        assert call_count == 2

        # Cleanup
        ttl_refresh_function.cache_clear()

    def test_shared_cache_without_ttl_refresh(self):
        """Test that TTL doesn't refresh when refresh_ttl_on_get=False."""
        call_count = 0

        @cached(ttl_seconds=2, shared_cache=True, refresh_ttl_on_get=False)
        def no_ttl_refresh_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 10

        # Clear any existing cache
        no_ttl_refresh_function.cache_clear()

        # First call
        result1 = no_ttl_refresh_function(4)
        assert result1 == 40
        assert call_count == 1

        # Wait 1 second
        time.sleep(1)

        # Second call - should use cache but NOT refresh TTL
        result2 = no_ttl_refresh_function(4)
        assert result2 == 40
        assert call_count == 1

        # Wait another 1.1 seconds (total 2.1s from first call)
        time.sleep(1.1)

        # Third call - should have expired
        result3 = no_ttl_refresh_function(4)
        assert result3 == 40
        assert call_count == 2

        # Cleanup
        no_ttl_refresh_function.cache_clear()

    def test_shared_cache_complex_objects(self):
        """Test caching complex objects with shared cache (pickle serialization)."""
        call_count = 0

        @cached(ttl_seconds=30, shared_cache=True)
        def complex_object_function(x: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {
                "number": x,
                "squared": x**2,
                "nested": {"list": [1, 2, x], "tuple": (x, x * 2)},
                "string": f"value_{x}",
            }

        # Clear any existing cache
        complex_object_function.cache_clear()

        # First call
        result1 = complex_object_function(5)
        assert result1["number"] == 5
        assert result1["squared"] == 25
        assert result1["nested"]["list"] == [1, 2, 5]
        assert call_count == 1

        # Second call - should use cache
        result2 = complex_object_function(5)
        assert result2 == result1
        assert call_count == 1

        # Cleanup
        complex_object_function.cache_clear()

    def test_shared_cache_info(self):
        """Test cache_info for shared cache."""

        @cached(ttl_seconds=30, shared_cache=True)
        def info_shared_function(x: int) -> int:
            return x * 2

        # Clear any existing cache
        info_shared_function.cache_clear()

        # Check initial info
        info = info_shared_function.cache_info()
        assert info["size"] == 0
        assert info["maxsize"] is None  # Redis manages size
        assert info["ttl_seconds"] == 30

        # Add some entries
        info_shared_function(1)
        info_shared_function(2)
        info_shared_function(3)

        info = info_shared_function.cache_info()
        assert info["size"] == 3

        # Cleanup
        info_shared_function.cache_clear()

    def test_shared_cache_delete(self):
        """Test selective deletion with shared cache."""
        call_count = 0

        @cached(ttl_seconds=30, shared_cache=True)
        def delete_shared_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 3

        # Clear any existing cache
        delete_shared_function.cache_clear()

        # Add entries
        delete_shared_function(1)
        delete_shared_function(2)
        delete_shared_function(3)
        assert call_count == 3

        # Verify cached
        delete_shared_function(1)
        delete_shared_function(2)
        assert call_count == 3

        # Delete specific entry
        was_deleted = delete_shared_function.cache_delete(2)
        assert was_deleted is True

        # Entry for x=2 should be gone
        delete_shared_function(2)
        assert call_count == 4

        # Others should still be cached
        delete_shared_function(1)
        delete_shared_function(3)
        assert call_count == 4

        # Try to delete non-existent
        was_deleted = delete_shared_function.cache_delete(99)
        assert was_deleted is False

        # Cleanup
        delete_shared_function.cache_clear()

    @pytest.mark.asyncio
    async def test_async_shared_cache_thundering_herd(self):
        """Test that shared cache prevents thundering herd for async functions."""
        call_count = 0

        @cached(ttl_seconds=30, shared_cache=True)
        async def shared_slow_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return x * x

        # Clear any existing cache
        shared_slow_function.cache_clear()

        # Launch multiple concurrent tasks
        tasks = [shared_slow_function(8) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should return same result
        assert all(r == 64 for r in results)
        # Only one should have executed
        assert call_count == 1

        # Cleanup
        shared_slow_function.cache_clear()

    def test_shared_cache_clear_pattern(self):
        """Test pattern-based cache clearing (Redis feature)."""

        @cached(ttl_seconds=30, shared_cache=True)
        def pattern_function(category: str, item: int) -> str:
            return f"{category}_{item}"

        # Clear any existing cache
        pattern_function.cache_clear()

        # Add various entries
        pattern_function("fruit", 1)
        pattern_function("fruit", 2)
        pattern_function("vegetable", 1)
        pattern_function("vegetable", 2)

        info = pattern_function.cache_info()
        assert info["size"] == 4

        # Note: Pattern clearing with wildcards requires specific Redis scan
        # implementation. The current code clears by pattern but needs
        # adjustment for partial matching. For now, test full clear.
        pattern_function.cache_clear()
        info = pattern_function.cache_info()
        assert info["size"] == 0

    def test_shared_vs_local_cache_isolation(self):
        """Test that shared and local caches are isolated."""
        shared_count = 0
        local_count = 0

        @cached(ttl_seconds=30, shared_cache=True)
        def shared_function(x: int) -> int:
            nonlocal shared_count
            shared_count += 1
            return x * 2

        @cached(ttl_seconds=30, shared_cache=False)
        def local_function(x: int) -> int:
            nonlocal local_count
            local_count += 1
            return x * 2

        # Clear caches
        shared_function.cache_clear()
        local_function.cache_clear()

        # Call both with same args
        shared_result = shared_function(5)
        local_result = local_function(5)

        assert shared_result == local_result == 10
        assert shared_count == 1
        assert local_count == 1

        # Call again - both should use their respective caches
        shared_function(5)
        local_function(5)
        assert shared_count == 1
        assert local_count == 1

        # Clear only shared cache
        shared_function.cache_clear()

        # Shared should recompute, local should still use cache
        shared_function(5)
        local_function(5)
        assert shared_count == 2
        assert local_count == 1

        # Cleanup
        shared_function.cache_clear()
        local_function.cache_clear()

    @pytest.mark.asyncio
    async def test_shared_cache_concurrent_different_keys(self):
        """Test that concurrent calls with different keys work correctly."""
        call_counts = {}

        @cached(ttl_seconds=30, shared_cache=True)
        async def multi_key_function(key: str) -> str:
            if key not in call_counts:
                call_counts[key] = 0
            call_counts[key] += 1
            await asyncio.sleep(0.05)
            return f"result_{key}"

        # Clear cache
        multi_key_function.cache_clear()

        # Launch concurrent tasks with different keys
        keys = ["a", "b", "c", "d", "e"]
        tasks = []
        for key in keys:
            # Multiple calls per key
            tasks.extend([multi_key_function(key) for _ in range(3)])

        results = await asyncio.gather(*tasks)

        # Verify results
        for i, key in enumerate(keys):
            expected = f"result_{key}"
            # Each key appears 3 times in results
            key_results = results[i * 3 : (i + 1) * 3]
            assert all(r == expected for r in key_results)

        # Each key should only be computed once
        for key in keys:
            assert call_counts[key] == 1

        # Cleanup
        multi_key_function.cache_clear()

    def test_shared_cache_performance_comparison(self):
        """Compare performance of shared vs local cache."""
        import statistics

        shared_times = []
        local_times = []

        @cached(ttl_seconds=30, shared_cache=True)
        def shared_perf_function(x: int) -> int:
            time.sleep(0.01)  # Simulate work
            return x * 2

        @cached(ttl_seconds=30, shared_cache=False)
        def local_perf_function(x: int) -> int:
            time.sleep(0.01)  # Simulate work
            return x * 2

        # Clear caches
        shared_perf_function.cache_clear()
        local_perf_function.cache_clear()

        # Warm up both caches
        for i in range(5):
            shared_perf_function(i)
            local_perf_function(i)

        # Measure cache hit times
        for i in range(5):
            # Shared cache hit
            start = time.time()
            shared_perf_function(i)
            shared_times.append(time.time() - start)

            # Local cache hit
            start = time.time()
            local_perf_function(i)
            local_times.append(time.time() - start)

        # Local cache should be faster (no Redis round-trip)
        avg_shared = statistics.mean(shared_times)
        avg_local = statistics.mean(local_times)

        print(f"Avg shared cache hit time: {avg_shared:.6f}s")
        print(f"Avg local cache hit time: {avg_local:.6f}s")

        # Local should be significantly faster for cache hits
        # Redis adds network latency even for cache hits
        assert avg_local < avg_shared

        # Cleanup
        shared_perf_function.cache_clear()
        local_perf_function.cache_clear()
