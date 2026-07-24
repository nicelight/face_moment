from __future__ import annotations

import argparse
import sys

from botocore.exceptions import ClientError
from sqlalchemy import create_engine, text

from face_moment.infrastructure.object_store import s3_client
from face_moment.infrastructure.settings import Settings

PROBE_TABLE = "face_moment.foundation_runtime_probe"


def write(settings: Settings, probe_id: str) -> None:
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {PROBE_TABLE} "
                "(probe_id text PRIMARY KEY, payload text NOT NULL)"
            )
        )
        connection.execute(
            text(
                f"INSERT INTO {PROBE_TABLE} (probe_id, payload) "
                "VALUES (:probe_id, :payload) "
                "ON CONFLICT (probe_id) DO UPDATE SET payload = EXCLUDED.payload"
            ),
            {"probe_id": probe_id, "payload": "foundation-persisted"},
        )
    engine.dispose()
    s3_client(settings).put_object(
        Bucket=settings.s3_bucket,
        Key=f"foundation-probe/{probe_id}",
        Body=b"foundation-persisted",
    )
    print("storage_probe_write=ok")


def read(settings: Settings, probe_id: str) -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        payload = connection.execute(
            text(f"SELECT payload FROM {PROBE_TABLE} WHERE probe_id = :probe_id"),
            {"probe_id": probe_id},
        ).scalar_one()
    engine.dispose()
    response = s3_client(settings).get_object(
        Bucket=settings.s3_bucket,
        Key=f"foundation-probe/{probe_id}",
    )
    object_payload = response["Body"].read().decode()
    if payload != "foundation-persisted" or object_payload != payload:
        raise RuntimeError("Storage probe payloads did not converge")
    print("storage_probe_read=ok")


def delete(settings: Settings, probe_id: str) -> None:
    client = s3_client(settings)
    key = f"foundation-probe/{probe_id}"
    client.delete_object(Bucket=settings.s3_bucket, Key=key)

    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {PROBE_TABLE}"))
    with engine.connect() as connection:
        relation = connection.execute(
            text("SELECT to_regclass(:relation)"),
            {"relation": PROBE_TABLE},
        ).scalar_one_or_none()
    engine.dispose()
    if relation is not None:
        raise RuntimeError("Probe relation was not removed")

    try:
        client.head_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as error:
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status != 404:
            raise
    else:
        raise RuntimeError("Probe object was not removed")
    print("storage_probe_delete=ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("write", "read", "delete"))
    parser.add_argument("--probe-id", required=True)
    args = parser.parse_args()
    settings = Settings.from_env()
    actions = {"write": write, "read": read, "delete": delete}
    actions[args.action](settings, args.probe_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"storage_probe_error={type(error).__name__}", file=sys.stderr)
        raise
