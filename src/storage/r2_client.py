"""Cloudflare R2 storage client.

R2 speaks the S3 API, so this wraps boto3's S3 client rather than
needing a separate Cloudflare-specific SDK.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
from botocore.client import Config as BotoConfig

logger = logging.getLogger(__name__)


class R2Client:
    """Thin wrapper around an S3-compatible client pointed at R2."""

    def __init__(self):
        account_id = os.getenv("CLOUDFLARE_R2_ACCOUNT_ID")
        access_key = os.getenv("CLOUDFLARE_R2_ACCESS_KEY")
        secret_key = os.getenv("CLOUDFLARE_R2_SECRET_KEY")
        endpoint = os.getenv("CLOUDFLARE_R2_ENDPOINT")
        self.bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET_NAME", "jarvis-data")

        if not account_id or not access_key or not secret_key:
            raise ValueError(
                "CLOUDFLARE_R2_ACCOUNT_ID, CLOUDFLARE_R2_ACCESS_KEY and "
                "CLOUDFLARE_R2_SECRET_KEY are required"
            )

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )
        logger.info("R2 storage client initialized (bucket=%s)", self.bucket_name)

    def health_check(self) -> bool:
        """True if the configured bucket is reachable."""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as exc:  # noqa: BLE001 - health check must never raise
            logger.error("R2 health check failed: %s", exc)
            return False

    def upload_json(self, key: str, data: Dict[str, Any]) -> bool:
        """Upload a dict as a JSON object under the given key."""
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(data, default=str).encode("utf-8"),
                ContentType="application/json",
            )
            logger.info("Uploaded %s to R2", key)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to upload %s to R2: %s", key, exc)
            raise

    def download_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Download and parse a JSON object, or None if missing/unreachable."""
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            return json.loads(response["Body"].read())
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to download %s from R2: %s", key, exc)
            return None

    def save_task_output(self, task_id: str, output: Dict[str, Any]) -> bool:
        """Back up a task's output under work/<task_id>.json, for
        analysis/backup independent of the database."""
        return self.upload_json(f"work/{task_id}.json", output)

    def get_storage_stats(self, max_objects: int = 5000) -> Dict[str, Any]:
        """Total size and object count in the bucket, for the dashboard's
        usage popover. R2 (like S3) has no single "bucket size" call —
        this pages through `list_objects_v2` and sums each object's
        `Size`, capped at `max_objects` so a very large bucket can't make
        a sidebar popover hang.

        Best-effort like `health_check()`: storage stats are a
        nice-to-have display, not on the critical path of saving a task,
        so a failure here degrades to zeros rather than raising.
        """
        total_bytes = 0
        object_count = 0
        truncated = False
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket_name):
                for obj in page.get("Contents", []):
                    total_bytes += obj["Size"]
                    object_count += 1
                    if object_count >= max_objects:
                        truncated = True
                        break
                if truncated:
                    break
            return {
                "total_bytes": total_bytes,
                "object_count": object_count,
                "truncated": truncated,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get R2 storage stats: %s", exc)
            return {
                "total_bytes": 0,
                "object_count": 0,
                "truncated": False,
                "error": str(exc),
            }
