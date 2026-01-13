"""Integration tests for MinIO S3 storage.

These tests verify that MinIO is properly configured and accessible
when running in Docker Compose. They test the S3 API using boto3.
"""
import os
from typing import Final

import boto3
import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError

_TEST_BUCKET: Final = 'photo-album'
_TEST_FILE_KEY: Final = 'test-file.txt'
_TEST_FILE_CONTENT: Final = b'Hello from MinIO integration test!'


@pytest.fixture
def s3_client() -> BaseClient:
    """Create S3 client for MinIO.

    Returns:
        Configured boto3 S3 client for MinIO.
    """
    minio_endpoint = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
    access_key = os.getenv('MINIO_ROOT_USER', 'minioadmin')
    secret_key = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')

    return boto3.client(
        's3',
        endpoint_url=minio_endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='us-east-1',
    )


@pytest.fixture
def test_bucket(s3_client: BaseClient) -> str:
    """Ensure test bucket exists.

    Args:
        s3_client: boto3 S3 client.

    Returns:
        Name of the test bucket.
    """
    try:
        s3_client.head_bucket(Bucket=_TEST_BUCKET)
    except ClientError:
        s3_client.create_bucket(Bucket=_TEST_BUCKET)

    return _TEST_BUCKET


@pytest.mark.integration
def test_s3_client_connection(s3_client: BaseClient) -> None:
    """Test that S3 client can connect to MinIO."""
    # List buckets to verify connection
    response = s3_client.list_buckets()
    assert 'Buckets' in response


@pytest.mark.integration
def test_create_bucket(s3_client: BaseClient) -> None:
    """Test bucket creation in MinIO."""
    try:
        s3_client.head_bucket(Bucket=_TEST_BUCKET)
    except ClientError:
        s3_client.create_bucket(Bucket=_TEST_BUCKET)

    # Verify bucket exists
    response = s3_client.head_bucket(Bucket=_TEST_BUCKET)
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200


@pytest.mark.integration
def test_upload_object(s3_client: BaseClient, test_bucket: str) -> None:
    """Test uploading an object to MinIO.

    Args:
        s3_client: boto3 S3 client.
        test_bucket: Name of the test bucket.
    """
    s3_client.put_object(
        Bucket=test_bucket,
        Key=_TEST_FILE_KEY,
        Body=_TEST_FILE_CONTENT,
    )

    # Verify object exists
    response = s3_client.head_object(Bucket=test_bucket, Key=_TEST_FILE_KEY)
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200
    assert response['ContentLength'] == len(_TEST_FILE_CONTENT)


@pytest.mark.integration
def test_list_objects(s3_client: BaseClient, test_bucket: str) -> None:
    """Test listing objects in MinIO bucket.

    Args:
        s3_client: boto3 S3 client.
        test_bucket: Name of the test bucket.
    """
    # Upload a test object
    s3_client.put_object(
        Bucket=test_bucket,
        Key=_TEST_FILE_KEY,
        Body=_TEST_FILE_CONTENT,
    )

    # List objects
    response = s3_client.list_objects_v2(Bucket=test_bucket)
    assert 'Contents' in response

    # Find our test object
    test_obj = None
    for obj in response['Contents']:
        if obj['Key'] == _TEST_FILE_KEY:
            test_obj = obj
            break

    assert test_obj is not None
    assert test_obj['Size'] == len(_TEST_FILE_CONTENT)


@pytest.mark.integration
def test_download_object(s3_client: BaseClient, test_bucket: str) -> None:
    """Test downloading an object from MinIO.

    Args:
        s3_client: boto3 S3 client.
        test_bucket: Name of the test bucket.
    """
    # Upload test object
    s3_client.put_object(
        Bucket=test_bucket,
        Key=_TEST_FILE_KEY,
        Body=_TEST_FILE_CONTENT,
    )

    # Download and verify
    response = s3_client.get_object(Bucket=test_bucket, Key=_TEST_FILE_KEY)
    downloaded_content = response['Body'].read()

    assert downloaded_content == _TEST_FILE_CONTENT


@pytest.mark.integration
def test_delete_object(s3_client: BaseClient, test_bucket: str) -> None:
    """Test deleting an object from MinIO.

    Args:
        s3_client: boto3 S3 client.
        test_bucket: Name of the test bucket.
    """
    # Upload test object
    s3_client.put_object(
        Bucket=test_bucket,
        Key=_TEST_FILE_KEY,
        Body=_TEST_FILE_CONTENT,
    )

    # Delete object
    s3_client.delete_object(Bucket=test_bucket, Key=_TEST_FILE_KEY)

    # Verify object is deleted
    with pytest.raises(ClientError) as exc_info:
        s3_client.head_object(Bucket=test_bucket, Key=_TEST_FILE_KEY)

    assert exc_info.value.response['Error']['Code'] == '404'
