"""Tests for DatabaseClient, with the Supabase SDK mocked out so these
run offline and don't depend on a real project existing."""

from unittest.mock import MagicMock, patch

import pytest

from src.database.client import DatabaseClient


def _client_with_mocked_supabase():
    with patch("src.database.client.create_client") as mock_create_client:
        mock_supabase = MagicMock()
        mock_create_client.return_value = mock_supabase
        db = DatabaseClient()
        return db, mock_supabase


def test_missing_credentials_raise(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with pytest.raises(ValueError):
        DatabaseClient()


def test_health_check_true_on_success():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.return_value.select.return_value.limit.return_value.execute.return_value = (
        MagicMock()
    )
    assert db.health_check() is True


def test_health_check_false_on_failure():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.health_check() is False


def test_save_task_returns_id():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "abc-123"}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        mock_execute
    )

    task_id = db.save_task(agent_type="brainstorm", input_data={"topic": "test"})

    assert task_id == "abc-123"
    mock_supabase.table.assert_called_with("tasks")


def test_list_tasks_returns_empty_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.list_tasks() == []
