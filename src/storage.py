"""Fetch a job's file.

Jobs reference an object in STORAGE_BUCKET by `file_key` (S3, or any S3-compatible store
via S3_ENDPOINT_URL: MinIO, GCS interoperability, R2), so RabbitMQ only carries small
messages. Inline base64 (`file_b64`, or `pdf_b64` from older API versions) is still
accepted so the API can move to object storage without a flag day.
"""
import base64
import os
from functools import lru_cache

from .errors import TransientError

STORAGE_BUCKET = os.getenv("STORAGE_BUCKET")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or None


@lru_cache(maxsize=1)
def _s3():
    import boto3

    return boto3.client("s3", endpoint_url=S3_ENDPOINT_URL)


def _check_size(size: int, max_bytes: int):
    if size > max_bytes:
        raise ValueError(f"File is {size / 1048576:.1f} MB; the limit is {max_bytes / 1048576:.0f} MB")


def _download_object(key: str, path: str, max_bytes: int):
    from botocore.exceptions import BotoCoreError, ClientError

    if not STORAGE_BUCKET:
        raise RuntimeError("Job references file_key but STORAGE_BUCKET is not set")
    try:
        _check_size(_s3().head_object(Bucket=STORAGE_BUCKET, Key=key)["ContentLength"], max_bytes)
        _s3().download_file(STORAGE_BUCKET, key, path)
    except ClientError as e:
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        code = e.response.get("Error", {}).get("Code", "")
        if status >= 500 or status == 429 or code in {"SlowDown", "Throttling", "RequestTimeout"}:
            raise TransientError(f"Object storage unavailable: {code or status}") from e
        raise ValueError(f"Could not fetch {key}: {code or status}") from e
    except BotoCoreError as e:
        raise TransientError(f"Object storage unreachable: {type(e).__name__}") from e


def download(payload: dict, path: str, max_bytes: int):
    """Write the job's file to `path`. ValueError when it is missing or over max_bytes."""
    key = payload.get("file_key")
    if key:
        _download_object(key, path, max_bytes)
        return
    encoded = payload.get("file_b64") or payload.get("pdf_b64")
    if not encoded:
        raise ValueError("Job has no file (expected file_key or file_b64)")
    _check_size(len(encoded) * 3 // 4, max_bytes)
    with open(path, "wb") as f:
        f.write(base64.b64decode(encoded))
