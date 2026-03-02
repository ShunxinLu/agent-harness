"""
Runners - Test execution backends for different frameworks.

Supports: pytest, bun, npm, maven, gradle, sbt, cargo, go, pyspark
"""

from .pytest_runner import PytestRunner
from .bun_runner import BunRunner
from .generic_runner import GenericRunner, get_runner

__all__ = ["PytestRunner", "BunRunner", "GenericRunner", "get_runner"]
