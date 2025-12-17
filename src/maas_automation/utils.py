"""Utility functions for retry logic and state polling"""
import logging
import time
from typing import Callable, Optional, List

log = logging.getLogger("maas_automation.utils")


def retry(fn: Callable, retries: int = 5, delay: float = 1.0, backoff: float = 2.0, max_delay: float = 60.0):
    """
    Retry a function with exponential backoff.
    
    Args:
        fn: Function to retry
        retries: Number of retries (0 = infinite)
        delay: Initial delay in seconds
        backoff: Backoff multiplier
        max_delay: Maximum delay between retries
        
    Returns:
        Result of fn()
        
    Raises:
        Last exception if all retries exhausted
    """
    last = None
    attempt = 0
    
    while True:
        try:
            return fn()
        except Exception as e:
            last = e
            attempt += 1
            
            # If retries is 0, retry forever
            if retries > 0 and attempt >= retries:
                log.error(f"All {retries} retries exhausted")
                raise last
            
            sleep_time = min(delay * (backoff ** (attempt - 1)), max_delay)
            retry_msg = f"infinite retries" if retries == 0 else f"{attempt}/{retries}"
            log.warning(f"Retry {retry_msg} failed: {e}. Waiting {sleep_time:.1f}s before retry...")
            time.sleep(sleep_time)


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
    consecutive_errors = 0
    max_consecutive_errors = 5
    elapsed = 0
    
    while elapsed < timeout:
        try:
            current_state = check_fn()
            consecutive_errors = 0  # Reset error count on success
            
            if current_state != last_state:
                elapsed = time.time() - start
                log.info(f"State: {current_state} (elapsed: {int(elapsed)}s / {timeout}s)")
                last_state = current_state
            
            if current_state in target_states:
                log.info(f"✓ Reached target state: {current_state}")
                return current_state
            
            if current_state in error_states:
                raise RuntimeError(f"Machine entered error state: {current_state}")
            
            time.sleep(poll_interval)
            elapsed = time.time() - start
            
        except RuntimeError:
            # Re-raise runtime errors (error states)
            raise
        except Exception as e:
            consecutive_errors += 1
            log.warning(f"State check failed ({consecutive_errors}/{max_consecutive_errors}): {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                raise RuntimeError(f"Too many consecutive state check failures: {e}")
            
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
