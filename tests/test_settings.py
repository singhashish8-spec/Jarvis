"""Tests for src/settings.py — resolving Agent Defaults, Custom
Instructions, and active Skills into what an agent actually uses for a
single request."""

import json
from unittest.mock import MagicMock

from src.settings import (
    is_agent_enabled,
    render_skill_template,
    resolve_agent_settings,
    resolve_model_and_version,
)
from src.settings_schema import CHEAPER_MODEL


def _db(settings=None, skills=None):
    """A minimal fake DatabaseClient exposing just get_setting/get_skill."""
    settings = settings or {}
    skills = skills or {}
    db = MagicMock()
    db.get_setting.side_effect = lambda key: settings.get(key)
    db.get_skill.side_effect = lambda skill_id: skills.get(skill_id)
    return db


def test_is_agent_enabled_defaults_true_with_no_config():
    db = _db()
    assert is_agent_enabled(db, "coder") is True


def test_is_agent_enabled_respects_disabled_flag():
    db = _db({"agent_config": json.dumps({"coder": {"enabled": False}})})
    assert is_agent_enabled(db, "coder") is False
    assert is_agent_enabled(db, "brainstorm") is True


def test_resolve_agent_settings_defaults_with_nothing_configured():
    db = _db()
    settings = resolve_agent_settings(db, "brainstorm")
    assert settings == {
        "enabled": True,
        "model": None,
        "temperature": None,
        "max_tokens": None,
        "custom_instructions": "",
        "skill_template": None,
    }


def test_resolve_agent_settings_reads_model_temperature_max_tokens():
    db = _db(
        {
            "agent_config": json.dumps(
                {"coder": {"model": "cheaper", "temperature": 0.9, "max_tokens": 256}}
            )
        }
    )
    settings = resolve_agent_settings(db, "coder")
    assert settings["model"] == CHEAPER_MODEL
    assert settings["temperature"] == 0.9
    assert settings["max_tokens"] == 256


def test_resolve_agent_settings_reads_custom_instructions():
    db = _db({"custom_instructions": "  Always answer in Hindi.  "})
    settings = resolve_agent_settings(db, "qa")
    assert settings["custom_instructions"] == "Always answer in Hindi."


def test_resolve_agent_settings_reads_active_skill_template():
    db = _db(
        settings={"active_skill:brainstorm": "skill-1"},
        skills={"skill-1": {"template": "Ideas for $topic", "is_active": True}},
    )
    settings = resolve_agent_settings(db, "brainstorm")
    assert settings["skill_template"] == "Ideas for $topic"


def test_resolve_agent_settings_ignores_inactive_skill():
    db = _db(
        settings={"active_skill:brainstorm": "skill-1"},
        skills={"skill-1": {"template": "Ideas for $topic", "is_active": False}},
    )
    settings = resolve_agent_settings(db, "brainstorm")
    assert settings["skill_template"] is None


def test_resolve_agent_settings_never_raises_on_broken_json():
    db = _db({"agent_config": "not valid json"})
    settings = resolve_agent_settings(db, "brainstorm")
    assert settings["model"] is None


def test_resolve_model_and_version_uses_default_when_no_override():
    settings = {"model": None}
    assert resolve_model_and_version(settings, "meta/meta-llama-3-70b-instruct") == (
        "meta/meta-llama-3-70b-instruct",
        None,
    )


def test_resolve_model_and_version_cheaper_override_drops_version():
    settings = {"model": CHEAPER_MODEL}
    model, version = resolve_model_and_version(
        settings, "kcaverly/deepseek-coder-33b-instruct-gguf", "some-version-hash"
    )
    assert model == CHEAPER_MODEL
    assert version is None


def test_render_skill_template_substitutes_known_variables():
    result = render_skill_template(
        "Ideas for $topic in $context", {"topic": "a shed", "context": "rural"}
    )
    assert result == "Ideas for a shed in rural"


def test_render_skill_template_leaves_unknown_variables_literal():
    result = render_skill_template("Hello $unknown_var", {"topic": "x"})
    assert result == "Hello $unknown_var"
