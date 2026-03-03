import pytest


pytestmark = pytest.mark.integration


def test_localstack_s3_container_smoke():
    testcontainers_localstack = pytest.importorskip("testcontainers.localstack")
    boto3 = pytest.importorskip("boto3")
    botocore_exceptions = pytest.importorskip("botocore.exceptions")

    LocalStackContainer = testcontainers_localstack.LocalStackContainer
    EndpointConnectionError = botocore_exceptions.EndpointConnectionError

    try:
        with LocalStackContainer(image="localstack/localstack:3.5") as localstack:
            s3_client = boto3.client(
                "s3",
                endpoint_url=localstack.get_url(),
                aws_access_key_id="test",
                aws_secret_access_key="test",
                region_name="us-east-1",
            )

            bucket_name = "harness-integration-bucket"
            s3_client.create_bucket(Bucket=bucket_name)
            buckets = s3_client.list_buckets()

            assert any(bucket["Name"] == bucket_name for bucket in buckets.get("Buckets", []))
    except EndpointConnectionError as exc:
        pytest.skip(f"Container runtime unavailable for integration test: {exc}")
    except Exception as exc:
        if "docker" in str(exc).lower():
            pytest.skip(f"Container runtime unavailable for integration test: {exc}")
        raise

