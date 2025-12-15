"""Utility functions for retry logic and state polling"""
import logging
import time
from typing import Callable, Optional, List

log = logging.getLogger("maas_automation.utils")


def retry(fn: Callable, retries: int = 5, delay: float = 1.0, backoff: float = 2.0):
    """Retry a function with exponential backoff"""
    last = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            log.debug(f"Retry {i+1}/{retries} failed: {e}")
            if i < retries - 1:
                sleep_time = delay * (backoff ** i)
                time.sleep(sleep_time)
    raise last


def wait_for_state(check_fn: Callable[[], str], 
                   target_states: List[str], 
                   timeout: int = 600, 
                   poll_interval: int = 5,
                   error_states: Optional[List[str]] = None) -> str:
    """
    Poll until machine reaches one of the target states or times out.
    
    Args:
        check_fn: Function that returns current state
        target_states: List of acceptable final states
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        error_states: States that indicate failure
        
    Returns:
        Final state reached
        
    Raises:
        TimeoutError: If timeout is exceeded
        RuntimeError: If error state is reached
    """
    error_states = error_states or ["FAILED", "FAILED_COMMISSIONING", "FAILED_DEPLOYMENT", 
                                     "FAILED_RELEASING", "FAILED_DISK_ERASING"]
    
    start = time.time()
    last_state = None
    
    while time.time() - start < timeout:
        try:
            current_state = check_fn()
            
            if current_state != last_state:
                log.info(f"State: {current_state}")
                last_state = current_state
            
            if current_state in target_states:
                log.info(f"✓ Reached target state: {current_state}")
                return current_state
            
            if current_state in error_states:
                raise RuntimeError(f"Machine entered error state: {current_state}")
            
            time.sleep(poll_interval)
            
        except Exception as e:
            log.warning(f"State check failed: {e}")
            time.sleep(poll_interval)
    
    raise TimeoutError(f"Timeout waiting for states {target_states}. Last state: {last_state}")


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"
