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


def test_record_usage_inserts_new_row_when_none_exists_today():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_select_execute = MagicMock()
    mock_select_execute.data = []
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
        mock_select_execute
    )

    db.record_usage(
        agent_type="brainstorm", model_name="llama-3-70b", tokens_used=30, cost=0.001
    )

    insert_call = mock_supabase.table.return_value.insert.call_args
    inserted = insert_call.args[0]
    assert inserted["agent_type"] == "brainstorm"
    assert inserted["tokens_used"] == 30
    assert inserted["calls_count"] == 1
    assert inserted["cost_currency"] == "USD"


def test_record_usage_accumulates_into_existing_row():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_select_execute = MagicMock()
    mock_select_execute.data = [
        {"id": "row-1", "calls_count": 2, "tokens_used": 100, "cost": 0.01}
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
        mock_select_execute
    )

    db.record_usage(
        agent_type="coder", model_name="deepseek-coder-33b", tokens_used=50, cost=0.005
    )

    update_call = mock_supabase.table.return_value.update.call_args
    updated = update_call.args[0]
    assert updated["calls_count"] == 3
    assert updated["tokens_used"] == 150
    assert round(updated["cost"], 3) == 0.015


def test_record_usage_never_raises_on_db_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    db.record_usage(
        agent_type="brainstorm", model_name="llama-3-70b", tokens_used=1, cost=0.0
    )


def test_get_usage_summary_aggregates_today_and_total():
    db, mock_supabase = _client_with_mocked_supabase()
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    mock_execute = MagicMock()
    mock_execute.data = [
        {"date": today, "tokens_used": 100, "cost": 0.01},
        {"date": today, "tokens_used": 50, "cost": 0.005},
        {"date": "2020-01-01", "tokens_used": 500, "cost": 0.05},
    ]
    mock_supabase.table.return_value.select.return_value.execute.return_value = (
        mock_execute
    )

    summary = db.get_usage_summary()

    assert summary["tokens_used_today"] == 150
    assert summary["tokens_used_total"] == 650
    assert summary["estimated_cost_usd_today"] == 0.015
    assert summary["estimated_cost_usd_total"] == 0.065


def test_get_usage_summary_returns_zeros_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    summary = db.get_usage_summary()
    assert summary["tokens_used_today"] == 0
    assert summary["estimated_cost_usd_total"] == 0.0
