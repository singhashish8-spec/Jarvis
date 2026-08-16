"""Tests for the BrainstormAgent directly (no HTTP layer)."""

from src.agents.brainstorm_agent import BrainstormAgent


def test_brainstorm_agent_initialization():
    agent = BrainstormAgent()
    assert agent.agent_type == "brainstorm"
    assert agent.model_name == "llama-70b"


def test_brainstorm_basic(sample_brainstorm_input):
    agent = BrainstormAgent()
    result = agent.brainstorm(**sample_brainstorm_input)

    assert "ideas" in result
    assert len(result["ideas"]) > 0
    assert "reasoning" in result
    assert "task_id" in result


def test_brainstorm_with_context():
    agent = BrainstormAgent()
    result = agent.brainstorm(
        topic="Design a mobile app",
        context="For architects, non-technical users",
        style="concise",
    )

    assert result is not None
    assert "ideas" in result


def test_brainstorm_defaults_context_and_style():
    agent = BrainstormAgent()
    result = agent.brainstorm(topic="Design a mobile app")

    assert result["task_id"]
    assert result["ideas"]
