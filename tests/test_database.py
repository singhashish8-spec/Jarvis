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


def test_missing_credentials_degrades_instead_of_raising(monkeypatch):
    # Previously raised, which took the whole Flask app down at import time
    # (see main.py's _init_client) — a missing/bad Supabase credential
    # should disable DB-backed features, not the entire app, including
    # routes (the dashboard, /health) that never touch the database.
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    db = DatabaseClient()
    assert db.client is None
    # And every read method already degrades gracefully when self.client
    # is None, the same way it degrades for any other Supabase failure.
    assert db.get_setting("credit_limit_usd") is None
    assert db.health_check() is False


def test_invalid_credentials_degrade_instead_of_raising(monkeypatch):
    # Present but rejected by Supabase (e.g. a malformed key) — same
    # degrade-don't-crash contract as the missing-credentials case above.
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "not-a-valid-key")
    with patch(
        "src.database.client.create_client",
        side_effect=Exception("Invalid API key"),
    ):
        db = DatabaseClient()
    assert db.client is None
    assert db.get_setting("credit_limit_usd") is None


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


def test_get_usage_by_agent_today_returns_todays_rows():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [
        {"agent_type": "brainstorm", "tokens_used": 100, "cost": 0.01},
        {"agent_type": "coder", "tokens_used": 50, "cost": 0.005},
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )
    rows = db.get_usage_by_agent_today()
    assert rows == mock_execute.data


def test_get_usage_by_agent_today_returns_empty_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.get_usage_by_agent_today() == []


def test_get_agent_cost_stats_computes_average_and_weekly_rate():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"cost": 0.01}, {"cost": 0.02}, {"cost": 0.03}]
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute
    ).return_value = mock_execute

    stats = db.get_agent_cost_stats("coder", days=30)

    assert stats["call_count"] == 3
    assert stats["avg_cost_per_call"] == pytest.approx(0.02)
    assert stats["calls_per_week"] == pytest.approx(3 / 30 * 7)
    assert stats["days_sampled"] == 30


def test_get_agent_cost_stats_no_calls_returns_zeros():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = []
    (
        mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute
    ).return_value = mock_execute

    stats = db.get_agent_cost_stats("coder")
    assert stats == {
        "call_count": 0,
        "avg_cost_per_call": 0.0,
        "calls_per_week": 0.0,
        "days_sampled": 30,
    }


def test_get_agent_cost_stats_returns_zeros_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    stats = db.get_agent_cost_stats("coder", days=14)
    assert stats["call_count"] == 0
    assert stats["days_sampled"] == 14


def test_get_table_counts_returns_count_per_table():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.count = 7
    mock_supabase.table.return_value.select.return_value.execute.return_value = (
        mock_execute
    )
    counts = db.get_table_counts()
    assert counts == {"tasks": 7, "usage": 7, "skills": 7}


def test_get_table_counts_zero_for_failing_table():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    counts = db.get_table_counts()
    assert counts == {"tasks": 0, "usage": 0, "skills": 0}


def test_delete_task_returns_true_on_success():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )
    assert db.delete_task("task-1") is True


def test_delete_task_returns_false_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.delete_task("task-1") is False


def test_count_recent_tasks_counts_rows_in_window():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    mock_supabase.table.return_value.select.return_value.gte.return_value.execute.return_value = (
        mock_execute
    )
    assert db.count_recent_tasks(60) == 3


def test_count_recent_tasks_returns_zero_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.count_recent_tasks(60) == 0


def test_purge_tasks_older_than_returns_deleted_count():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "1"}, {"id": "2"}]
    mock_supabase.table.return_value.delete.return_value.lt.return_value.execute.return_value = (
        mock_execute
    )
    assert db.purge_tasks_older_than(30) == 2


def test_purge_tasks_older_than_raises_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    with pytest.raises(Exception):
        db.purge_tasks_older_than(30)


def test_reset_usage_deletes_all_rows():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.return_value.delete.return_value.neq.return_value.execute.return_value = (
        MagicMock()
    )
    db.reset_usage()
    mock_supabase.table.assert_called_with("usage")


def test_reset_usage_raises_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    with pytest.raises(Exception):
        db.reset_usage()


def test_reset_all_settings_deletes_rows_except_connector_tokens():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.return_value.delete.return_value.not_.in_.return_value.execute.return_value = (
        MagicMock()
    )
    db.reset_all_settings()
    mock_supabase.table.assert_called_with("settings")
    mock_supabase.table.return_value.delete.return_value.not_.in_.assert_called_with(
        "key",
        [
            "dropbox_refresh_token",
            "dropbox_account_email",
            "github_access_token",
            "github_account_login",
        ],
    )


def test_list_skills_filters_by_agent_type():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "s1", "agent_type": "coder"}]
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
        mock_execute
    )
    skills = db.list_skills(agent_type="coder")
    assert skills == [{"id": "s1", "agent_type": "coder"}]


def test_list_skills_returns_empty_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.list_skills() == []


def test_get_skill_returns_row():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "s1", "template": "Hi $name"}]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )
    assert db.get_skill("s1") == {"id": "s1", "template": "Hi $name"}


def test_get_skill_returns_none_when_missing():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = []
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )
    assert db.get_skill("missing") is None


def test_get_skill_returns_none_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.get_skill("s1") is None


def test_create_skill_returns_new_id():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "new-skill-id"}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = (
        mock_execute
    )
    skill_id = db.create_skill(
        agent_type="coder",
        skill_name="Terse code",
        template="Write $requirements tersely.",
    )
    assert skill_id == "new-skill-id"


def test_create_skill_raises_on_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("no such column: template")
    with pytest.raises(Exception):
        db.create_skill(agent_type="coder", skill_name="x", template="y")


def test_update_skill_calls_update_with_fields():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )
    db.update_skill("s1", is_active=False)
    mock_supabase.table.return_value.update.assert_called_with({"is_active": False})


def test_delete_skill_calls_delete():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )
    db.delete_skill("s1")
    mock_supabase.table.assert_called_with("skills")


def test_get_setting_returns_value_when_present():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = [{"value": "10.0"}]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )

    assert db.get_setting("credit_limit_usd") == "10.0"


def test_get_setting_returns_none_when_absent():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_execute = MagicMock()
    mock_execute.data = []
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_execute
    )

    assert db.get_setting("credit_limit_usd") is None


def test_get_setting_returns_none_on_db_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("connection refused")
    assert db.get_setting("credit_limit_usd") is None


def test_set_setting_upserts():
    db, mock_supabase = _client_with_mocked_supabase()
    db.set_setting("credit_limit_usd", "25.0")
    mock_supabase.table.return_value.upsert.assert_called_with(
        {"key": "credit_limit_usd", "value": "25.0"}
    )


def test_set_setting_raises_on_db_error():
    db, mock_supabase = _client_with_mocked_supabase()
    mock_supabase.table.side_effect = Exception("settings table doesn't exist")
    with pytest.raises(Exception):
        db.set_setting("credit_limit_usd", "25.0")
