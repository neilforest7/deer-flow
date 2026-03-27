from types import SimpleNamespace

from deerflow.project_runtime.qa import run_acceptance_check, run_qa_gate


def _state():
    return {
        "project_brief": {
            "objective": "Ship runtime",
            "scope": ["backend runtime"],
            "constraints": ["keep lead_agent unchanged"],
            "deliverables": ["runtime"],
            "success_criteria": ["tests pass"],
        },
        "work_orders": [
            {
                "id": "wo-1",
                "owner_agent": "backend-agent",
                "title": "Implement runtime",
                "goal": "Ship runtime",
                "read_scope": ["backend"],
                "write_scope": ["backend"],
                "dependencies": [],
                "acceptance_checks": ["uv run pytest tests/test_project_runtime_graph.py -q", "Review summary quality"],
                "status": "completed",
            }
        ],
        "active_work_order_ids": [],
        "agent_reports": [
            {
                "work_order_id": "wo-1",
                "agent_name": "backend-agent",
                "summary": "done",
                "changes": ["backend/packages/harness/deerflow/project_runtime/graph.py"],
                "risks": [],
                "verification": ["graph tests"],
            }
        ],
        "build_error": None,
    }


def test_run_qa_gate_returns_blocked_when_build_error_exists():
    state = _state()
    state["build_error"] = "tool failure"

    result = run_qa_gate(state, thread_id="thread-1")

    assert result["result"] == "blocked"
    assert "tool failure" in result["findings"][0]


def test_run_qa_gate_returns_fail_with_actionable_rework_for_failed_check():
    class FailingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            return SimpleNamespace(status="failed", error="pytest failed")

    result = run_qa_gate(
        _state(),
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="bash"), SimpleNamespace(name="read_file")],
        executor_cls=FailingExecutor,
    )

    assert result["result"] == "fail"
    assert any("wo-1" in item for item in result["required_rework"])
    assert any("uv run pytest" in item for item in result["findings"])


def test_run_qa_gate_fails_when_completed_subagent_reports_fail_verdict():
    class VerdictFailExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            return SimpleNamespace(status="completed", result="VERDICT: FAIL\nEVIDENCE: pytest reported 2 failures")

    result = run_qa_gate(
        _state(),
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="bash"), SimpleNamespace(name="read_file")],
        executor_cls=VerdictFailExecutor,
    )

    assert result["result"] == "fail"
    assert any("pytest reported 2 failures" in item for item in result["findings"])


def test_run_qa_gate_fails_when_completed_subagent_omits_verdict():
    class MissingVerdictExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            return SimpleNamespace(status="completed", result="pytest failed with one assertion error")

    result = run_qa_gate(
        _state(),
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="bash"), SimpleNamespace(name="read_file")],
        executor_cls=MissingVerdictExecutor,
    )

    assert result["result"] == "fail"
    assert any("uv run pytest" in item for item in result["findings"])


def test_run_qa_gate_returns_pass_and_records_manual_findings_for_non_executable_checks():
    class PassingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            return SimpleNamespace(status="completed", result="VERDICT: PASS\nEVIDENCE: pytest passed")

    result = run_qa_gate(
        _state(),
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="bash"), SimpleNamespace(name="read_file")],
        executor_cls=PassingExecutor,
    )

    assert result["result"] == "pass"
    assert any("Acceptance check passed" in item for item in result["findings"])
    assert any("Manual QA review noted" in item for item in result["findings"])
    assert result["required_rework"] == []


def test_run_acceptance_check_executes_env_prefixed_commands():
    captured = {}

    class CapturingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            captured["parent_model"] = parent_model

        def execute(self, task):
            captured["task"] = task
            return SimpleNamespace(status="completed", result="VERDICT: PASS\nEVIDENCE: pytest passed")

    result = run_acceptance_check(
        _state(),
        _state()["work_orders"][0],
        "PYTHONPATH=. uv run pytest tests/test_project_runtime_graph.py -q",
        thread_id="thread-1",
        parent_model="project-model",
        available_tools=[SimpleNamespace(name="bash"), SimpleNamespace(name="read_file")],
        executor_cls=CapturingExecutor,
    )

    assert result.executable is True
    assert result.passed is True
    assert "PYTHONPATH=. uv run pytest" in captured["task"]
    assert captured["parent_model"] == "project-model"


def test_run_qa_gate_fails_when_completed_work_order_has_no_report():
    state = _state()
    state["agent_reports"] = []

    result = run_qa_gate(state, thread_id="thread-1")

    assert result["result"] == "fail"
    assert any("no agent report" in item for item in result["findings"])


def test_run_acceptance_check_uses_latest_report_for_reworked_work_order():
    state = _state()
    state["agent_reports"] = [
        {
            "work_order_id": "wo-1",
            "agent_name": "backend-agent",
            "summary": "older report",
            "changes": [],
            "risks": [],
            "verification": [],
        },
        {
            "work_order_id": "wo-1",
            "agent_name": "backend-agent",
            "summary": "latest rerun report",
            "changes": [],
            "risks": [],
            "verification": [],
        },
    ]
    captured = {}

    class CapturingExecutor:
        def __init__(self, config, tools, parent_model=None, sandbox_state=None, thread_data=None, thread_id=None):
            pass

        def execute(self, task):
            captured["task"] = task
            return SimpleNamespace(status="completed", result="VERDICT: PASS\nEVIDENCE: pytest passed")

    result = run_acceptance_check(
        state,
        state["work_orders"][0],
        "uv run pytest tests/test_project_runtime_graph.py -q",
        thread_id="thread-1",
        available_tools=[SimpleNamespace(name="bash"), SimpleNamespace(name="read_file")],
        executor_cls=CapturingExecutor,
    )

    assert result.passed is True
    assert "latest rerun report" in captured["task"]
    assert "older report" not in captured["task"]
