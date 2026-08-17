"""Tests for settings_schema.py — the single source of truth for every
generic setting's validation rules and the Agent Defaults matrix."""

import pytest

from src.settings_schema import (
    AGENT_BUILTIN_DEFAULTS,
    PRESETS,
    compute_preset_agent_config,
    validate_agent_config,
    validate_setting_value,
)


def test_validate_setting_value_number_within_range():
    assert validate_setting_value("credit_limit_usd", "15.5") == "15.5"


def test_validate_setting_value_number_rejects_below_min():
    with pytest.raises(ValueError):
        validate_setting_value("credit_limit_usd", -1)


def test_validate_setting_value_number_rejects_above_max():
    with pytest.raises(ValueError):
        validate_setting_value("budget_alert_threshold_pct", 150)


def test_validate_setting_value_number_rejects_non_numeric():
    with pytest.raises(ValueError):
        validate_setting_value("credit_limit_usd", "not-a-number")


def test_validate_setting_value_none_or_empty_clears():
    assert validate_setting_value("credit_limit_usd", None) == ""
    assert validate_setting_value("credit_limit_usd", "") == ""


def test_validate_setting_value_select_accepts_valid_option():
    assert validate_setting_value("default_agent", "coder") == "coder"


def test_validate_setting_value_select_rejects_invalid_option():
    with pytest.raises(ValueError):
        validate_setting_value("default_agent", "not-a-real-agent")


def test_validate_setting_value_textarea_enforces_max_length():
    with pytest.raises(ValueError):
        validate_setting_value("custom_instructions", "x" * 2000)


def test_validate_setting_value_textarea_accepts_within_limit():
    assert validate_setting_value("custom_instructions", "be concise") == "be concise"


def test_validate_setting_value_unknown_key_raises():
    with pytest.raises(ValueError):
        validate_setting_value("not_a_real_setting", "x")


def test_validate_agent_config_accepts_valid_entries():
    cleaned = validate_agent_config(
        {
            "brainstorm": {
                "enabled": False,
                "model": "cheaper",
                "temperature": 0.5,
                "max_tokens": 512,
            },
            "coder": {"enabled": True},
        }
    )
    assert cleaned["brainstorm"] == {
        "enabled": False,
        "model": "cheaper",
        "temperature": 0.5,
        "max_tokens": 512,
    }
    assert cleaned["coder"] == {"enabled": True}


def test_validate_agent_config_rejects_unknown_agent():
    with pytest.raises(ValueError):
        validate_agent_config({"not_a_real_agent": {"enabled": True}})


def test_validate_agent_config_rejects_non_object_entry():
    with pytest.raises(ValueError):
        validate_agent_config({"coder": "not an object"})


def test_validate_agent_config_rejects_non_bool_enabled():
    with pytest.raises(ValueError):
        validate_agent_config({"coder": {"enabled": "yes"}})


def test_validate_agent_config_rejects_unknown_model():
    with pytest.raises(ValueError):
        validate_agent_config({"coder": {"model": "gpt-5"}})


def test_validate_agent_config_rejects_out_of_range_temperature():
    with pytest.raises(ValueError):
        validate_agent_config({"coder": {"temperature": 5}})


def test_validate_agent_config_rejects_out_of_range_max_tokens():
    with pytest.raises(ValueError):
        validate_agent_config({"coder": {"max_tokens": 999999}})


def test_validate_agent_config_empty_input_returns_empty():
    assert validate_agent_config({}) == {}
    assert validate_agent_config(None) == {}


# ---- Presets ----


def test_presets_list_has_frugal_and_max_quality():
    ids = {p["id"] for p in PRESETS}
    assert ids == {"frugal", "max_quality"}


def test_compute_preset_rejects_unknown_id():
    with pytest.raises(ValueError):
        compute_preset_agent_config("does-not-exist")


def test_frugal_preset_covers_every_agent():
    delta = compute_preset_agent_config("frugal")
    assert set(delta.keys()) == set(AGENT_BUILTIN_DEFAULTS.keys())


def test_frugal_preset_sets_cheaper_model_for_every_agent():
    delta = compute_preset_agent_config("frugal")
    assert all(entry["model"] == "cheaper" for entry in delta.values())


def test_frugal_preset_halves_max_tokens():
    delta = compute_preset_agent_config("frugal")
    assert (
        delta["coder"]["max_tokens"]
        == AGENT_BUILTIN_DEFAULTS["coder"]["max_tokens"] // 2
    )


def test_frugal_preset_floors_max_tokens_at_256():
    # deployer's default max_tokens (512) halves to exactly 256, the floor —
    # this pins the floor logic even if that default ever drops further.
    delta = compute_preset_agent_config("frugal")
    assert delta["deployer"]["max_tokens"] >= 256


def test_max_quality_preset_clears_every_agent_override():
    delta = compute_preset_agent_config("max_quality")
    assert set(delta.keys()) == set(AGENT_BUILTIN_DEFAULTS.keys())
    assert all(entry == {"model": None, "max_tokens": None} for entry in delta.values())


def test_frugal_preset_deltas_pass_validation():
    # Every preset's output must itself be acceptable input to
    # validate_agent_config — this is exactly how main.py uses it.
    cleaned = validate_agent_config(compute_preset_agent_config("frugal"))
    assert cleaned["coder"]["model"] == "cheaper"
    assert cleaned["coder"]["max_tokens"] == 512


def test_max_quality_preset_deltas_pass_validation():
    cleaned = validate_agent_config(compute_preset_agent_config("max_quality"))
    # None values mean "not provided" to validate_agent_config, so a
    # cleared agent ends up with an empty entry, not explicit nulls.
    assert cleaned == {agent_id: {} for agent_id in AGENT_BUILTIN_DEFAULTS}
