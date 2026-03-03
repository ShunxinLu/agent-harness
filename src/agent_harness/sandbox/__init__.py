"""
Harness Sandbox - Isolated testing environments for agent projects.

Provides LocalStack AWS mocking and DuckDB local database support.
"""

import os
import time
import yaml
from pathlib import Path
from typing import Optional

import boto3
import duckdb
from pydantic import BaseModel


class ServiceConfig(BaseModel):
    """Configuration for a single sandbox service."""
    name: str
    type: str  # localstack, duckdb
    services: list[str] = []  # For LocalStack: s3, sqs, dynamodb, etc.
    path: Optional[str] = None  # For DuckDB: database path


class SandboxConfig(BaseModel):
    """Sandbox configuration loaded from sandbox.yaml."""
    services: list[ServiceConfig] = []

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "SandboxConfig":
        """Load configuration from YAML file."""
        path = Path(yaml_path)
        if not path.exists():
            return cls()

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data or "services" not in data:
            return cls()

        services = []
        for svc in data["services"]:
            services.append(ServiceConfig(**svc))

        return cls(services=services)

    def has_localstack(self) -> bool:
        """Check if LocalStack services are configured."""
        return any(s.type == "localstack" for s in self.services)

    def has_duckdb(self) -> bool:
        """Check if DuckDB is configured."""
        return any(s.type == "duckdb" for s in self.services)

    def get_duckdb_path(self) -> Optional[str]:
        """Get DuckDB database path."""
        for svc in self.services:
            if svc.type == "duckdb" and svc.path:
                return svc.path
        return None


class SandboxManager:
    """
    Manages sandbox services lifecycle.

    Design: LocalStack runs as a persistent background daemon.
    This class checks health and resets state between runs.
    """

    def __init__(self, config: SandboxConfig):
        self.config = config
        self.localstack_endpoint = os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        self._s3_client = None
        self._sqs_client = None
        self._dynamodb_client = None

    def is_daemon_healthy(self) -> bool:
        """Check if LocalStack daemon is running and healthy."""
        import urllib.request
        import urllib.error

        try:
            with urllib.request.urlopen(f"{self.localstack_endpoint}/_localstack/health", timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    def ensure_daemon_running(self) -> bool:
        """
        Ensure LocalStack daemon is running.
        Returns True if healthy, False otherwise.
        """
        if not self.config.has_localstack():
            return True  # No LocalStack needed

        if not self.is_daemon_healthy():
            return False

        return True

    def wait_for_healthy(self, timeout: int = 60, poll_interval: float = 2.0) -> bool:
        """Wait for LocalStack to become healthy."""
        start = time.time()

        while time.time() - start < timeout:
            if self.is_daemon_healthy():
                return True
            time.sleep(poll_interval)

        return False

    def reset_state(self):
        """
        Reset LocalStack state between test runs.
        Purges S3 buckets, SQS queues, etc.
        """
        if not self.config.has_localstack():
            return

        if not self.is_daemon_healthy():
            return

        # Reset S3
        try:
            s3 = self.get_s3_client()
            response = s3.list_buckets()

            for bucket in response.get("Buckets", []):
                bucket_name = bucket["Name"]
                if not bucket_name.startswith("__"):
                    # Delete all objects
                    try:
                        objects = s3.list_objects_v2(Bucket=bucket_name)
                        if "Contents" in objects:
                            keys = [{"Key": obj["Key"]} for obj in objects["Contents"]]
                            s3.delete_objects(Bucket=bucket_name, Delete={"Objects": keys})
                        s3.delete_bucket(Bucket=bucket_name)
                    except Exception:
                        pass  # Best effort cleanup

        except Exception:
            pass  # Best effort cleanup

    def get_s3_client(self):
        """Get boto3 S3 client connected to LocalStack."""
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.localstack_endpoint,
                region_name="us-east-1",
                aws_access_key_id="test",
                aws_secret_access_key="test",
            )
        return self._s3_client

    def get_sqs_client(self):
        """Get boto3 SQS client connected to LocalStack."""
        if self._sqs_client is None:
            self._sqs_client = boto3.client(
                "sqs",
                endpoint_url=self.localstack_endpoint,
                region_name="us-east-1",
                aws_access_key_id="test",
                aws_secret_access_key="test",
            )
        return self._sqs_client

    def get_dynamodb_client(self):
        """Get boto3 DynamoDB client connected to LocalStack."""
        if self._dynamodb_client is None:
            self._dynamodb_client = boto3.client(
                "dynamodb",
                endpoint_url=self.localstack_endpoint,
                region_name="us-east-1",
                aws_access_key_id="test",
                aws_secret_access_key="test",
            )
        return self._dynamodb_client

    def get_duckdb_connection(self, db_path: Optional[str] = None) -> duckdb.DuckDBPyConnection:
        """Get DuckDB connection."""
        path = db_path or self.config.get_duckdb_path() or ":memory:"

        if path != ":memory:":
            # Ensure directory exists
            db_file = Path(path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

        return duckdb.connect(path)


# Convenience functions for direct use
_default_manager: Optional[SandboxManager] = None


def get_default_manager() -> Optional[SandboxManager]:
    """Get or create default sandbox manager from .harness/sandbox.yaml."""
    global _default_manager

    if _default_manager is None:
        # Try to load from current directory
        sandbox_yaml = Path(".harness/sandbox.yaml")
        if sandbox_yaml.exists():
            config = SandboxConfig.from_yaml(str(sandbox_yaml))
            _default_manager = SandboxManager(config)
            _default_manager.ensure_daemon_running()

    return _default_manager


def get_s3_client():
    """Get S3 client from default manager."""
    manager = get_default_manager()
    if manager:
        return manager.get_s3_client()

    # Safe-by-default: do not implicitly fall back to real AWS.
    if os.getenv("HARNESS_ALLOW_REAL_AWS", "").lower() in {"1", "true", "yes"}:
        return boto3.client("s3")

    raise RuntimeError(
        "No sandbox manager configured. Refusing direct AWS S3 access by default. "
        "Configure .harness/sandbox.yaml, or set HARNESS_ALLOW_REAL_AWS=1 to opt in explicitly."
    )


def get_duckdb_connection(db_path: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    """Get DuckDB connection from default manager."""
    manager = get_default_manager()
    if manager:
        return manager.get_duckdb_connection(db_path)

    # Fallback to in-memory
    return duckdb.connect(db_path or ":memory:")
