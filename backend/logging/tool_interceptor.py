"""
Interceptor for logging tool calls during RIM and baseline loops.
Captures all tool execution details for debugging and analysis.
"""

import logging
import time
from typing import Any, Dict, Optional, Callable
from functools import wraps

logger = logging.getLogger(__name__)


class ToolCallInterceptor:
    """Intercepts and logs tool calls with full context"""

    def __init__(self, structured_log):
        self.structured_log = structured_log
        self.turn_counter = 0

    def wrap_tool_call(self, tool_name: str, is_rim: bool) -> Callable:
        """Decorator to wrap and log tool calls"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                self.turn_counter += 1
                start_time = time.perf_counter()

                try:
                    result = await func(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    # Log successful tool call
                    self.structured_log.log_tool_call(
                        tool_name=tool_name,
                        arguments=kwargs,
                        is_rim=is_rim,
                        turn_number=self.turn_counter,
                        execution_time_ms=elapsed_ms,
                        success=True,
                        result=result
                    )

                    return result

                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    # Log failed tool call
                    self.structured_log.log_tool_call(
                        tool_name=tool_name,
                        arguments=kwargs,
                        is_rim=is_rim,
                        turn_number=self.turn_counter,
                        execution_time_ms=elapsed_ms,
                        success=False,
                        error=str(e)
                    )

                    raise

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                self.turn_counter += 1
                start_time = time.perf_counter()

                try:
                    result = func(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    # Log successful tool call
                    self.structured_log.log_tool_call(
                        tool_name=tool_name,
                        arguments=kwargs,
                        is_rim=is_rim,
                        turn_number=self.turn_counter,
                        execution_time_ms=elapsed_ms,
                        success=True,
                        result=result
                    )

                    return result

                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    # Log failed tool call
                    self.structured_log.log_tool_call(
                        tool_name=tool_name,
                        arguments=kwargs,
                        is_rim=is_rim,
                        turn_number=self.turn_counter,
                        execution_time_ms=elapsed_ms,
                        success=False,
                        error=str(e)
                    )

                    raise

            # Check if function is async
            import inspect
            if inspect.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    def log_tool_execution(self, tool_name: str, is_rim: bool,
                          arguments: Dict[str, Any],
                          result: Optional[Dict[str, Any]] = None,
                          error: Optional[str] = None,
                          execution_time_ms: float = 0.0):
        """Manually log a tool execution"""
        self.turn_counter += 1

        self.structured_log.log_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            is_rim=is_rim,
            turn_number=self.turn_counter,
            execution_time_ms=execution_time_ms,
            success=error is None,
            result=result,
            error=error
        )
