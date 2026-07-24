from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import ClientError

from face_moment.infrastructure.settings import Settings


def s3_client(settings: Settings) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    )


def assert_bucket_ready(settings: Settings) -> None:
    s3_client(settings).head_bucket(Bucket=settings.s3_bucket)


def ensure_bucket(settings: Settings) -> None:
    client = s3_client(settings)
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError as error:
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status not in {404, 400}:
            raise
        client.create_bucket(Bucket=settings.s3_bucket)

