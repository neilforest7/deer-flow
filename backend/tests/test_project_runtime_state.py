from deerflow.agents.thread_state import merge_artifacts
from deerflow.project_runtime import Phase, PlanStatus, ProjectThreadState, make_project_thread_state_defaults


def test_project_thread_state_defaults_are_stable():
    defaults = make_project_thread_state_defaults()

    assert defaults == {
        "phase": Phase.INTAKE.value,
        "plan_status": PlanStatus.DRAFT.value,
        "project_brief": None,
        "work_orders": [],
        "active_work_order_ids": [],
        "agent_reports": [],
        "qa_gate": None,
        "delivery_summary": None,
        "project_runtime_version": "m1",
    }


def test_project_thread_state_accepts_minimal_state_shape():
    state: ProjectThreadState = {
        "messages": [],
        **make_project_thread_state_defaults(),
    }

    assert state["phase"] == Phase.INTAKE.value
    assert state["work_orders"] == []


def test_project_thread_state_defaults_are_not_shared():
    first = make_project_thread_state_defaults()
    second = make_project_thread_state_defaults()

    first["work_orders"].append("mutated")

    assert second["work_orders"] == []


def test_project_thread_state_inherits_artifact_reducer_behavior():
    existing = ["/tmp/a.txt"]
    new = ["/tmp/a.txt", "/tmp/b.txt"]

    assert merge_artifacts(existing, new) == ["/tmp/a.txt", "/tmp/b.txt"]
