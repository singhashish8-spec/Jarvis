"""Tests for R2Client.get_storage_stats(), with boto3 mocked out so
these run offline and don't depend on a real bucket existing."""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("CLOUDFLARE_R2_ACCOUNT_ID", "test-account-id")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-access-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret-key")
os.environ.setdefault(
    "CLOUDFLARE_R2_ENDPOINT", "https://test-account-id.r2.cloudflarestorage.com"
)

from src.storage.r2_client import R2Client  # noqa: E402


def _client_with_mocked_boto3():
    with patch("src.storage.r2_client.boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        return R2Client(), mock_s3


def test_get_storage_stats_sums_object_sizes():
    client, mock_s3 = _client_with_mocked_boto3()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Size": 100}, {"Size": 250}]},
        {"Contents": [{"Size": 50}]},
    ]
    mock_s3.get_paginator.return_value = mock_paginator

    stats = client.get_storage_stats()

    assert stats == {"total_bytes": 400, "object_count": 3, "truncated": False}


def test_get_storage_stats_handles_empty_bucket():
    client, mock_s3 = _client_with_mocked_boto3()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{}]
    mock_s3.get_paginator.return_value = mock_paginator

    stats = client.get_storage_stats()

    assert stats == {"total_bytes": 0, "object_count": 0, "truncated": False}


def test_get_storage_stats_caps_at_max_objects():
    client, mock_s3 = _client_with_mocked_boto3()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Size": 1}, {"Size": 1}, {"Size": 1}]},
    ]
    mock_s3.get_paginator.return_value = mock_paginator

    stats = client.get_storage_stats(max_objects=2)

    assert stats["object_count"] == 2
    assert stats["truncated"] is True


def test_get_storage_stats_degrades_to_zeros_on_error():
    client, mock_s3 = _client_with_mocked_boto3()
    mock_s3.get_paginator.side_effect = Exception("connection refused")

    stats = client.get_storage_stats()

    assert stats["total_bytes"] == 0
    assert stats["object_count"] == 0
    assert "error" in stats
