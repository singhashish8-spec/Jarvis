"""Tests for each agent directly (no HTTP layer), with Replicate calls
mocked so these run offline and don't cost anything."""

from unittest.mock import MagicMock

from src.agents.brainstorm_agent import BrainstormAgent
from src.agents.coder_agent import CoderAgent
from src.agents.deployer_agent import DeployerAgent
from src.agents.document_agent import DocumentAgent
from src.agents.qa_agent import QAAgent
from src.agents.tester_agent import TesterAgent


def _run_result(output: str) -> dict:
    """Matches ReplicateClient.run()'s real return shape, so agent tests
    exercise the same unpacking code the live path uses."""
    return {
        "output": output,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "predict_time_seconds": 1.0,
            "estimated_cost_usd": 0.0014,
        },
    }


def test_brainstorm_agent_initialization():
    agent = BrainstormAgent()
    assert agent.agent_type == "brainstorm"
    assert agent.model_name == "llama-3-70b"


def test_brainstorm_basic(monkeypatch, sample_brainstorm_input):
    agent = BrainstormAgent()
    monkeypatch.setattr(
        agent.replicate_client,
        "run",
        MagicMock(return_value=_run_result("idea one, idea two")),
    )

    result = agent.brainstorm(**sample_brainstorm_input)

    assert result["output"] == "idea one, idea two"
    assert result["task_id"]
    assert result["usage"]["total_tokens"] == 30


def test_brainstorm_defaults_context_and_style(monkeypatch):
    agent = BrainstormAgent()
    monkeypatch.setattr(
        agent.replicate_client, "run", MagicMock(return_value=_run_result("ideas"))
    )

    result = agent.brainstorm(topic="Design a mobile app")

    assert result["task_id"]
    assert result["output"]


def test_brainstorm_propagates_replicate_errors(monkeypatch):
    agent = BrainstormAgent()
    monkeypatch.setattr(
        agent.replicate_client,
        "run",
        MagicMock(side_effect=RuntimeError("model failed")),
    )

    try:
        agent.brainstorm(topic="test")
        assert False, "expected RuntimeError to propagate"
    except RuntimeError:
        assert agent.current_task["status"] == "failed"


def test_coder_agent_generates_code(monkeypatch):
    agent = CoderAgent()
    monkeypatch.setattr(
        agent.replicate_client,
        "run",
        MagicMock(return_value=_run_result("def add(a, b):\n    return a + b")),
    )

    result = agent.generate_code(requirements="add two numbers", tech_stack="Python")

    assert "def add" in result["output"]
    assert result["tech_stack"] == "Python"
    assert result["task_id"]


def test_tester_agent_writes_tests(monkeypatch):
    agent = TesterAgent()
    monkeypatch.setattr(
        agent.replicate_client,
        "run",
        MagicMock(return_value=_run_result("def test_add(): assert add(1, 2) == 3")),
    )

    result = agent.write_tests(code="def add(a, b): return a + b", framework="pytest")

    assert "test_add" in result["output"]
    assert result["framework"] == "pytest"


def test_deployer_agent_plans_deployment(monkeypatch):
    agent = DeployerAgent()
    monkeypatch.setattr(
        agent.replicate_client,
        "run",
        MagicMock(return_value=_run_result("1. Run tests\n2. Deploy\n3. Verify")),
    )

    result = agent.plan_deployment(change_summary="Add login page", target="Vercel")

    assert result["output"]
    assert result["target"] == "Vercel"


def test_document_agent_writes_docs(monkeypatch):
    agent = DocumentAgent()
    monkeypatch.setattr(
        agent.replicate_client,
        "run",
        MagicMock(return_value=_run_result("# Login Page\nDocs here.")),
    )

    result = agent.write_docs(subject="Login page")

    assert "Login Page" in result["output"]


def test_qa_agent_reviews_code(monkeypatch):
    agent = QAAgent()
    monkeypatch.setattr(
        agent.replicate_client,
        "run",
        MagicMock(return_value=_run_result("No issues found.")),
    )

    result = agent.review_code(code="def add(a, b): return a + b")

    assert result["output"]
