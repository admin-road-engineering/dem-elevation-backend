"""
Thread Pool Service - Performance Enhancement Phase 2.1

Provides dedicated thread pools for CPU-intensive operations to prevent event loop blocking.
Optimizes resource utilization with proper thread pool sizing and lifecycle management.
"""

import asyncio
import logging
import concurrent.futures
from typing import Optional, Callable, Any, Awaitable
from concurrent.futures import ThreadPoolExecutor
import os
import psutil

logger = logging.getLogger(__name__)


class ThreadPoolService:
    """
    Dedicated thread pool service for CPU-intensive operations.
    
    Performance Benefits:
    - Prevents event loop blocking for CPU-bound tasks
    - Optimal thread pool sizing based on CPU cores
    - Separate pools for different operation types (I/O vs CPU)
    - Proper resource cleanup and lifecycle management
    """
    
    def __init__(self, cpu_workers: Optional[int] = None, io_workers: Optional[int] = None):
        """
        Initialize thread pool service with optimal sizing.
        
        Args:
            cpu_workers: Number of threads for CPU-bound tasks (default: CPU cores)
            io_workers: Number of threads for I/O-bound tasks (default: CPU cores * 4)
        """
        self.cpu_cores = os.cpu_count() or 4
        
        # Performance Fix Phase 2.1: Optimal thread pool sizing
        self.cpu_workers = cpu_workers or self.cpu_cores
        self.io_workers = io_workers or min(self.cpu_cores * 4, 32)  # Cap at 32 threads
        
        # Create dedicated thread pools
        self._cpu_pool: Optional[ThreadPoolExecutor] = None
        self._io_pool: Optional[ThreadPoolExecutor] = None
        
        logger.info(f"ThreadPoolService configured: CPU workers={self.cpu_workers}, I/O workers={self.io_workers}")
    
    @property
    def cpu_pool(self) -> ThreadPoolExecutor:
        """Get or create the CPU-bound thread pool"""
        if self._cpu_pool is None:
            self._cpu_pool = ThreadPoolExecutor(
                max_workers=self.cpu_workers,
                thread_name_prefix="dem-cpu"
            )
            logger.info(f"CPU thread pool created with {self.cpu_workers} workers")
        return self._cpu_pool
    
    @property  
    def io_pool(self) -> ThreadPoolExecutor:
        """Get or create the I/O-bound thread pool"""
        if self._io_pool is None:
            self._io_pool = ThreadPoolExecutor(
                max_workers=self.io_workers,
                thread_name_prefix="dem-io"
            )
            logger.info(f"I/O thread pool created with {self.io_workers} workers")
        return self._io_pool
    
    async def run_cpu_task(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute CPU-intensive task in dedicated CPU thread pool.
        
        Use this for:
        - GDAL/rasterio operations
        - NumPy array operations
        - Heavy computational tasks
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func execution
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.cpu_pool, func, *args, **kwargs)
    
    async def run_io_task(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute I/O-bound task in dedicated I/O thread pool.
        
        Use this for:
        - Synchronous S3 operations
        - File system operations
        - Synchronous HTTP requests
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func execution
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.io_pool, func, *args, **kwargs)
    
    def get_pool_stats(self) -> dict:
        """Get thread pool statistics for monitoring"""
        stats = {
            "cpu_pool": {
                "max_workers": self.cpu_workers,
                "active": self._cpu_pool is not None,
            },
            "io_pool": {
                "max_workers": self.io_workers, 
                "active": self._io_pool is not None,
            },
            "system_info": {
                "cpu_cores": self.cpu_cores,
                "memory_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            }
        }
        
        # Add runtime stats if pools exist
        if self._cpu_pool is not None:
            stats["cpu_pool"]["threads"] = self._cpu_pool._threads if hasattr(self._cpu_pool, '_threads') else None
            
        if self._io_pool is not None:
            stats["io_pool"]["threads"] = self._io_pool._threads if hasattr(self._io_pool, '_threads') else None
            
        return stats
    
    def close(self):
        """Shutdown thread pools and cleanup resources"""
        pools_closed = 0
        
        if self._cpu_pool is not None:
            try:
                self._cpu_pool.shutdown(wait=True, cancel_futures=False)
                self._cpu_pool = None
                pools_closed += 1
                logger.info("CPU thread pool shutdown completed")
            except Exception as e:
                logger.warning(f"Error shutting down CPU thread pool: {e}")
        
        if self._io_pool is not None:
            try:
                self._io_pool.shutdown(wait=True, cancel_futures=False)
                self._io_pool = None
                pools_closed += 1
                logger.info("I/O thread pool shutdown completed")
            except Exception as e:
                logger.warning(f"Error shutting down I/O thread pool: {e}")
        
        if pools_closed > 0:
            logger.info(f"ThreadPoolService closed {pools_closed} thread pools")


# Utility function for backward compatibility
async def run_in_cpu_pool(func: Callable, *args, **kwargs) -> Any:
    """
    Utility function to run CPU-intensive tasks in thread pool.
    
    This is a convenience function that uses the default executor.
    For better performance, use ThreadPoolService directly.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)