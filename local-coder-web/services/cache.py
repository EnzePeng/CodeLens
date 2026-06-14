"""
Cache Manager - LRU cache for search results and tool outputs
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional, Callable
from functools import wraps


class LRUCache:
    """Generic LRU cache with TTL support."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                self._cache.move_to_end(key)
                self._hits += 1
                return value
            else:
                del self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            del self._cache[key]
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (value, time.time())

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def invalidate(self, pattern: str) -> int:
        """Invalidate keys matching pattern."""
        to_delete = [k for k in self._cache if pattern in k]
        for k in to_delete:
            del self._cache[k]
        return len(to_delete)

    def get_stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0,
        }


def cached(cache: LRUCache, key_func: Optional[Callable] = None):
    """Decorator for caching function results."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            result = await func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# Global caches
search_cache = LRUCache(max_size=200, ttl_seconds=600)
tool_cache = LRUCache(max_size=50, ttl_seconds=120)
llm_cache = LRUCache(max_size=100, ttl_seconds=300)


def get_search_cache() -> LRUCache:
    return search_cache


def get_tool_cache() -> LRUCache:
    return tool_cache


def get_llm_cache() -> LRUCache:
    return llm_cache
