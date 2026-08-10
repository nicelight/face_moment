from __future__ import annotations

from typing import Any, cast

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


class PrivateObjectStore:
    """Private-bucket S3 operations without inventory business semantics."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def put(self, *, key: str, body: bytes) -> None:
        s3_client(self._settings).put_object(
            Bucket=self._settings.s3_bucket,
            Key=key,
            Body=body,
        )

    def read(self, *, key: str) -> bytes:
        response = s3_client(self._settings).get_object(
            Bucket=self._settings.s3_bucket,
            Key=key,
        )
        body = response["Body"]
        try:
            return cast(bytes, body.read())
        finally:
            body.close()

    def delete(self, *, key: str) -> None:
        s3_client(self._settings).delete_object(
            Bucket=self._settings.s3_bucket,
            Key=key,
        )

    def list_keys(self, *, prefix: str) -> set[str]:
        client = s3_client(self._settings)
        response = client.list_objects_v2(
            Bucket=self._settings.s3_bucket,
            Prefix=prefix,
        )
        return {
            item["Key"]
            for item in response.get("Contents", [])
            if isinstance(item.get("Key"), str)
        }
