import psutil
import time
import functools
from typing import Any, Callable
from utils.logger import log
from utils.notifier import notifier

class MemoryGuard:
    CRITICAL_MB = 300      # Pause pipeline
    WARNING_MB = 500       # Log warning
    
    def check(self, context: str = "") -> dict:
        """
        Returns {available_mb, used_mb, percent_used, status: "ok"|"warning"|"critical"}
        """
        mem = psutil.virtual_memory()
        available_mb = mem.available / (1024 * 1024)
        used_mb = mem.used / (1024 * 1024)
        percent_used = mem.percent
        
        status = "ok"
        if available_mb < self.CRITICAL_MB:
            status = "critical"
            log.error(f"CRITICAL MEMORY: {available_mb:.1f}MB available", context=context)
        elif available_mb < self.WARNING_MB:
            status = "warning"
            log.warning(f"Low memory: {available_mb:.1f}MB available", context=context)
        
        return {
            "available_mb": available_mb,
            "used_mb": used_mb,
            "percent_used": percent_used,
            "status": status
        }
    
    def require(self, min_mb: int, context: str = "") -> bool:
        """
        Checks if min_mb is available. Waits and alerts if necessary.
        """
        check_res = self.check(context)
        if check_res["available_mb"] >= min_mb:
            return True
            
        log.warning(f"Memory requirement {min_mb}MB not met. Available: {check_res['available_mb']:.1f}MB. Waiting 10s...", context=context)
        time.sleep(10)
        
        check_res = self.check(context)
        if check_res["available_mb"] >= min_mb:
            return True
            
        log.error(f"CRITICAL: Memory requirement {min_mb}MB still not met after wait.", context=context)
        notifier.send(
            title="Memory Alert 🚨",
            message=f"System critically low on memory ({check_res['available_mb']:.1f}MB available). Pipeline paused at: {context}",
            priority="urgent",
            tags=["warning", "fire"]
        )
        return False
    
    @staticmethod
    def monitor_decorator(min_mb: int = 400):
        """
        Decorator that calls require() before the decorated function.
        """
        def decorator(func: Callable):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                guard = MemoryGuard()
                if guard.require(min_mb, context=func.__name__):
                    return func(*args, **kwargs)
                else:
                    log.error(f"Function {func.__name__} aborted due to insufficient memory.")
                    return None
            return wrapper
        return decorator

# Global instances for utilities
memory_guard = MemoryGuard()
