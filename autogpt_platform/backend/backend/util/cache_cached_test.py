"""Tests for cache utilities."""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from backend.util.cache import cached, clear_thread_cache, thread_cached

class TestCache:
    """Tests for the unified @cache decorator (works for both sync and async)."""

    def test_basic_sync_caching(self):
        """Test basic sync caching functionality."""
        call_count = 0

        @cached(ttl_seconds=300)
        def expensive_sync_function(x: int, y: int = 0) -> int:
            nonlocal call_count
            call_count += 1
            return x + y

        # First call
        result1 = expensive_sync_function(1, 2)
        assert result1 == 3
        assert call_count == 1

        # Second call with same args - should use cache
        result2 = expensive_sync_function(1, 2)
        assert result2 == 3
        assert call_count == 1

        # Different args - should call function again
        result3 = expensive_sync_function(2, 3)
        assert result3 == 5
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_basic_async_caching(self):
        """Test basic async caching functionality."""
        call_count = 0

        @cached(ttl_seconds=300)
        async def expensive_async_function(x: int, y: int = 0) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate async work
            return x + y

        # First call
        result1 = await expensive_async_function(1, 2)
        assert result1 == 3
        assert call_count == 1

        # Second call with same args - should use cache
        result2 = await expensive_async_function(1, 2)
        assert result2 == 3
        assert call_count == 1

        # Different args - should call function again
        result3 = await expensive_async_function(2, 3)
        assert result3 == 5
        assert call_count == 2

    def test_sync_thundering_herd_protection(self):
        """Test that concurrent sync calls don't cause thundering herd."""
        call_count = 0
        results = []

        @cached(ttl_seconds=300)
        def slow_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)  # Simulate expensive operation
            return x * x

        def worker():
            result = slow_function(5)
            results.append(result)

        # Launch multiple concurrent threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker) for _ in range(5)]
            for future in futures:
                future.result()

        # All results should be the same
        assert all(result == 25 for result in results)
        # Only one thread should have executed the expensive operation
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_thundering_herd_protection(self):
        """Test that concurrent async calls don't cause thundering herd."""
        call_count = 0

        @cached(ttl_seconds=300)
        async def slow_async_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate expensive operation
            return x * x

        # Launch concurrent coroutines
        tasks = [slow_async_function(7) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All results should be the same
        assert all(result == 49 for result in results)
        # Only one coroutine should have executed the expensive operation
        assert call_count == 1

    def test_ttl_functionality(self):
        """Test TTL functionality with sync function."""
        call_count = 0

        @cached(maxsize=10, ttl_seconds=1)  # Short TTL
        def ttl_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 3

        # First call
        result1 = ttl_function(3)
        assert result1 == 9
        assert call_count == 1

        # Second call immediately - should use cache
        result2 = ttl_function(3)
        assert result2 == 9
        assert call_count == 1

        # Wait for TTL to expire
        time.sleep(1.1)

        # Third call after expiration - should call function again
        result3 = ttl_function(3)
        assert result3 == 9
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_ttl_functionality(self):
        """Test TTL functionality with async function."""
        call_count = 0

        @cached(maxsize=10, ttl_seconds=1)  # Short TTL
        async def async_ttl_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 4

        # First call
        result1 = await async_ttl_function(3)
        assert result1 == 12
        assert call_count == 1

        # Second call immediately - should use cache
        result2 = await async_ttl_function(3)
        assert result2 == 12
        assert call_count == 1

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Third call after expiration - should call function again
        result3 = await async_ttl_function(3)
        assert result3 == 12
        assert call_count == 2

    def test_cache_info(self):
        """Test cache info functionality."""

        @cached(maxsize=10, ttl_seconds=60)
        def info_test_function(x: int) -> int:
            return x * 3

        # Check initial cache info
        info = info_test_function.cache_info()
        assert info["size"] == 0
        assert info["maxsize"] == 10
        assert info["ttl_seconds"] == 60

        # Add an entry
        info_test_function(1)
        info = info_test_function.cache_info()
        assert info["size"] == 1

    def test_cache_clear(self):
        """Test cache clearing functionality."""
        call_count = 0

        @cached(ttl_seconds=300)
        def clearable_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 4

        # First call
        result1 = clearable_function(2)
        assert result1 == 8
        assert call_count == 1

        # Second call - should use cache
        result2 = clearable_function(2)
        assert result2 == 8
        assert call_count == 1

        # Clear cache
        clearable_function.cache_clear()

        # Third call after clear - should call function again
        result3 = clearable_function(2)
        assert result3 == 8
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_cache_clear(self):
        """Test cache clearing functionality with async function."""
        call_count = 0

        @cached(ttl_seconds=300)
        async def async_clearable_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 5

        # First call
        result1 = await async_clearable_function(2)
        assert result1 == 10
        assert call_count == 1

        # Second call - should use cache
        result2 = await async_clearable_function(2)
        assert result2 == 10
        assert call_count == 1

        # Clear cache
        async_clearable_function.cache_clear()

        # Third call after clear - should call function again
        result3 = await async_clearable_function(2)
        assert result3 == 10
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_function_returns_results_not_coroutines(self):
        """Test that cached async functions return actual results, not coroutines."""
        call_count = 0

        @cached(ttl_seconds=300)
        async def async_result_function(x: int) -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return f"result_{x}"

        # First call
        result1 = await async_result_function(1)
        assert result1 == "result_1"
        assert isinstance(result1, str)  # Should be string, not coroutine
        assert call_count == 1

        # Second call - should return cached result (string), not coroutine
        result2 = await async_result_function(1)
        assert result2 == "result_1"
        assert isinstance(result2, str)  # Should be string, not coroutine
        assert call_count == 1  # Function should not be called again

        # Verify results are identical
        assert result1 is result2  # Should be same cached object

    def test_cache_delete(self):
        """Test selective cache deletion functionality."""
        call_count = 0

        @cached(ttl_seconds=300)
        def deletable_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 6

        # First call for x=1
        result1 = deletable_function(1)
        assert result1 == 6
        assert call_count == 1

        # First call for x=2
        result2 = deletable_function(2)
        assert result2 == 12
        assert call_count == 2

        # Second calls - should use cache
        assert deletable_function(1) == 6
        assert deletable_function(2) == 12
        assert call_count == 2

        # Delete specific entry for x=1
        was_deleted = deletable_function.cache_delete(1)
        assert was_deleted is True

        # Call with x=1 should execute function again
        result3 = deletable_function(1)
        assert result3 == 6
        assert call_count == 3

        # Call with x=2 should still use cache
        assert deletable_function(2) == 12
        assert call_count == 3

        # Try to delete non-existent entry
        was_deleted = deletable_function.cache_delete(99)
        assert was_deleted is False

    @pytest.mark.asyncio
    async def test_async_cache_delete(self):
        """Test selective cache deletion functionality with async function."""
        call_count = 0

        @cached(ttl_seconds=300)
        async def async_deletable_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 7

        # First call for x=1
        result1 = await async_deletable_function(1)
        assert result1 == 7
        assert call_count == 1

        # First call for x=2
        result2 = await async_deletable_function(2)
        assert result2 == 14
        assert call_count == 2

        # Second calls - should use cache
        assert await async_deletable_function(1) == 7
        assert await async_deletable_function(2) == 14
        assert call_count == 2

        # Delete specific entry for x=1
        was_deleted = async_deletable_function.cache_delete(1)
        assert was_deleted is True

        # Call with x=1 should execute function again
        result3 = await async_deletable_function(1)
        assert result3 == 7
        assert call_count == 3

        # Call with x=2 should still use cache
        assert await async_deletable_function(2) == 14
        assert call_count == 3

        # Try to delete non-existent entry
        was_deleted = async_deletable_function.cache_delete(99)
        assert was_deleted is False


