"""
Performance Module - Provides performance optimization utilities for Terminator IDE
"""

import time
import logging
import asyncio
import functools
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, Coroutine

F = TypeVar('F', bound=Callable[..., Any])
R = TypeVar('R')

class PerformanceOptimizer:
    """Class providing performance optimization utilities for Terminator IDE"""
    
    # Cache for expensive function results
    _cache: Dict[str, Dict[str, Any]] = {}
    
    @staticmethod
    def memoize(ttl: int = 300):
        """
        Decorator for caching function results to improve performance
        
        Args:
            ttl: Time to live for cached results in seconds (default: 5 minutes)
            
        Returns:
            Decorator function
        """
        def decorator(func: F) -> F:
            cache_key = f"{func.__module__}.{func.__qualname__}"
            
            if cache_key not in PerformanceOptimizer._cache:
                PerformanceOptimizer._cache[cache_key] = {}
                
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Create a hash from the arguments
                arg_key = str(hash(str(args) + str(sorted(kwargs.items()))))
                
                # Check if we have a cached result that's still valid
                cache_entry = PerformanceOptimizer._cache[cache_key].get(arg_key)
                
                if cache_entry and time.time() - cache_entry['timestamp'] < ttl:
                    return cache_entry['result']
                
                # No valid cache entry, call the function
                result = func(*args, **kwargs)
                
                # Cache the result
                PerformanceOptimizer._cache[cache_key][arg_key] = {
                    'result': result,
                    'timestamp': time.time()
                }
                
                return result
            
            return wrapper  # type: ignore
        
        return decorator

    @staticmethod
    def async_memoize(ttl: int = 300):
        """
        Decorator for caching async function results to improve performance
        
        Args:
            ttl: Time to live for cached results in seconds (default: 5 minutes)
            
        Returns:
            Decorator function
        """
        def decorator(func):
            cache_key = f"{func.__module__}.{func.__qualname__}"
            
            if cache_key not in PerformanceOptimizer._cache:
                PerformanceOptimizer._cache[cache_key] = {}
                
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Create a hash from the arguments
                arg_key = str(hash(str(args) + str(sorted(kwargs.items()))))
                
                # Check if we have a cached result that's still valid
                cache_entry = PerformanceOptimizer._cache[cache_key].get(arg_key)
                
                if cache_entry and time.time() - cache_entry['timestamp'] < ttl:
                    return cache_entry['result']
                
                # No valid cache entry, call the function
                result = await func(*args, **kwargs)
                
                # Cache the result
                PerformanceOptimizer._cache[cache_key][arg_key] = {
                    'result': result,
                    'timestamp': time.time()
                }
                
                return result
            
            return wrapper
        
        return decorator

    @staticmethod
    def parallel_run(coroutines: List[Coroutine]) -> List[Any]:
        """
        Run multiple coroutines in parallel and return their results
        
        Args:
            coroutines: List of coroutines to run
            
        Returns:
            List of results from the coroutines
        """
        return asyncio.gather(*coroutines)
    
    @staticmethod
    def clear_cache(namespace: Optional[str] = None) -> None:
        """
        Clear the function cache
        
        Args:
            namespace: Optional namespace to clear (function qualified name)
                      If None, clear the entire cache
        """
        if namespace:
            if namespace in PerformanceOptimizer._cache:
                PerformanceOptimizer._cache[namespace] = {}
        else:
            PerformanceOptimizer._cache = {}

class DebounceThrottle:
    """Utility class for debouncing and throttling function calls"""
    
    _timers: Dict[str, Dict[str, Any]] = {}
    _last_call: Dict[str, float] = {}
    
    @staticmethod
    def debounce(wait_time: float):
        """
        Decorator to debounce function calls - only call after wait_time with no new calls
        
        Args:
            wait_time: Time to wait in seconds before executing the function
            
        Returns:
            Decorator function
        """
        def decorator(func: F) -> F:
            func_key = f"{func.__module__}.{func.__qualname__}"
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Cancel previous timer if it exists
                if func_key in DebounceThrottle._timers:
                    timer_info = DebounceThrottle._timers[func_key]
                    if 'timer' in timer_info:
                        timer_info['timer'].cancel()
                
                # Create a new timer
                async def delayed_call():
                    await asyncio.sleep(wait_time)
                    # Call the function
                    func(*args, **kwargs)
                    # Remove the timer
                    if func_key in DebounceThrottle._timers:
                        del DebounceThrottle._timers[func_key]
                
                # Store the new timer
                task = asyncio.create_task(delayed_call())
                DebounceThrottle._timers[func_key] = {
                    'timer': task,
                    'timestamp': time.time()
                }
                
            return wrapper  # type: ignore
        
        return decorator
    
    @staticmethod
    def throttle(wait_time: float):
        """
        Decorator to throttle function calls - limit to one call per wait_time
        
        Args:
            wait_time: Minimum time between function calls in seconds
            
        Returns:
            Decorator function
        """
        def decorator(func: F) -> F:
            func_key = f"{func.__module__}.{func.__qualname__}"
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                current_time = time.time()
                
                # Check if enough time has passed since the last call
                if func_key in DebounceThrottle._last_call:
                    time_since_last = current_time - DebounceThrottle._last_call[func_key]
                    if time_since_last < wait_time:
                        # Not enough time has passed, skip this call
                        return None
                
                # Update the last call time
                DebounceThrottle._last_call[func_key] = current_time
                
                # Call the function
                return func(*args, **kwargs)
            
            return wrapper  # type: ignore
        
        return decorator

class TimingProfiler:
    """Utility class for profiling function execution time"""
    
    _timing_data: Dict[str, List[float]] = {}
    
    @staticmethod
    def profile(func: F) -> F:
        """
        Decorator to profile function execution time
        
        Args:
            func: Function to profile
            
        Returns:
            Wrapped function
        """
        func_key = f"{func.__module__}.{func.__qualname__}"
        
        if func_key not in TimingProfiler._timing_data:
            TimingProfiler._timing_data[func_key] = []
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            
            # Record the execution time
            execution_time = end_time - start_time
            TimingProfiler._timing_data[func_key].append(execution_time)
            
            # Log the execution time
            logging.debug(f"Function {func_key} executed in {execution_time:.4f} seconds")
            
            return result
        
        return wrapper  # type: ignore
    
    @staticmethod
    def async_profile(func):
        """
        Decorator to profile async function execution time
        
        Args:
            func: Async function to profile
            
        Returns:
            Wrapped function
        """
        func_key = f"{func.__module__}.{func.__qualname__}"
        
        if func_key not in TimingProfiler._timing_data:
            TimingProfiler._timing_data[func_key] = []
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)
            end_time = time.time()
            
            # Record the execution time
            execution_time = end_time - start_time
            TimingProfiler._timing_data[func_key].append(execution_time)
            
            # Log the execution time
            logging.debug(f"Async function {func_key} executed in {execution_time:.4f} seconds")
            
            return result
        
        return wrapper
    
    @staticmethod
    def get_stats(func_key: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        """
        Get timing statistics for profiled functions
        
        Args:
            func_key: Optional function key to get stats for
                    If None, get stats for all functions
                    
        Returns:
            Dictionary of timing statistics
        """
        stats = {}
        
        if func_key:
            # Get stats for a specific function
            if func_key in TimingProfiler._timing_data:
                times = TimingProfiler._timing_data[func_key]
                if times:
                    stats[func_key] = {
                        'count': len(times),
                        'avg': sum(times) / len(times),
                        'min': min(times),
                        'max': max(times),
                        'total': sum(times)
                    }
        else:
            # Get stats for all functions
            for key, times in TimingProfiler._timing_data.items():
                if times:
                    stats[key] = {
                        'count': len(times),
                        'avg': sum(times) / len(times),
                        'min': min(times),
                        'max': max(times),
                        'total': sum(times)
                    }
        
        return stats