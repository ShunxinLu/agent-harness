"""
Output optimization - Stack trace compression and JSON formatting.
"""

from .compressor import (
    CompressedError,
    TestResult,
    TestRunResult,
    extract_error_info,
    compress_stack_trace,
    format_result_json,
    format_summary,
)

__all__ = [
    "CompressedError",
    "TestResult",
    "TestRunResult",
    "extract_error_info",
    "compress_stack_trace",
    "format_result_json",
    "format_summary",
]
