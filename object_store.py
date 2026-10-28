"""Hand uploaded files to the workers through object storage.

With STORAGE_BUCKET set (S3, or any S3-compatible store via S3_ENDPOINT_URL: MinIO,
GCS interoperability, R2), each file is uploaded to uploads/<job_id>/<filename> and the
job message carries only its key, so RabbitMQ never holds whole documents. Without a
bucket, files travel inline as base64: fine for tests and a laptop, not for production.

Give the bucket a lifecycle rule that expires uploads/ (e.g. after 7 days); the workers
only read the objects.
"""
import base64
import logging
import os
from functools import lru_cache
from typing import List, Tuple

logger = logging.getLogger("object_store")

STORAGE_BUCKET = os.getenv("STORAGE_BUCKET")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or None


class StorageUnavailable(Exception):
    pass


@lru_cache(maxsize=1)
def _s3():
    import boto3

    return boto3.client("s3", endpoint_url=S3_ENDPOINT_URL)


def file_refs(job_id: str, files: List[Tuple[str, bytes]]) -> List[dict]:
    """The message fields that point a worker at each file, uploading the files first if a bucket is set."""
    if not STORAGE_BUCKET:
        return [{"file_b64": base64.b64encode(data).decode()} for _, data in files]

    from botocore.exceptions import BotoCoreError, ClientError

    refs = []
    try:
        for name, data in files:
            key = f"uploads/{job_id}/{name}"
            _s3().put_object(Bucket=STORAGE_BUCKET, Key=key, Body=data)
            refs.append({"file_key": key})
    except (BotoCoreError, ClientError) as e:
        delete(job_id, [ref["file_key"] for ref in refs])
        raise StorageUnavailable(f"{type(e).__name__}") from e
    return refs


def delete(job_id: str, keys: List[str]):
    """Best-effort cleanup when a job can't be queued after its files were uploaded."""
    if not STORAGE_BUCKET or not keys:
        return
    try:
        _s3().delete_objects(Bucket=STORAGE_BUCKET, Delete={"Objects": [{"Key": k} for k in keys]})
    except Exception:
        logger.warning(f"Could not delete uploads of job {job_id}; the bucket lifecycle rule will expire them")
