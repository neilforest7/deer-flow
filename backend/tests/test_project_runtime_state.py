from deerflow.agents.thread_state import merge_artifacts
from deerflow.project_runtime import AgentReport, Phase, PlanStatus, ProjectThreadState, WorkOrder, WorkOrderStatus, make_project_thread_state_defaults
from deerflow.project_runtime.state import merge_active_work_order_ids, merge_agent_reports, merge_work_orders


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


def test_project_thread_state_agent_reports_reducer_appends_parallel_updates():
    existing = [AgentReport(work_order_id="wo-1", agent_name="agent-a", summary="done")]
    new = [AgentReport(work_order_id="wo-2", agent_name="agent-b", summary="done")]

    merged = merge_agent_reports(existing, new)

    assert [report.work_order_id for report in merged] == ["wo-1", "wo-2"]


def test_project_thread_state_active_work_order_ids_reducer_deduplicates_in_order():
    merged = merge_active_work_order_ids(["wo-1", "wo-2"], ["wo-2", "wo-3", "wo-1"])

    assert merged == ["wo-1", "wo-2", "wo-3"]


def test_project_thread_state_work_orders_reducer_upserts_by_id_without_reordering():
    existing = [
        WorkOrder(
            id="wo-1",
            owner_agent="backend-agent",
            title="Initial",
            goal="Ship runtime",
            acceptance_checks=["pytest"],
            status=WorkOrderStatus.READY,
        ),
        WorkOrder(
            id="wo-2",
            owner_agent="qa-agent",
            title="QA",
            goal="Verify runtime",
            acceptance_checks=["pytest"],
            status=WorkOrderStatus.PENDING,
        ),
    ]
    new = [
        WorkOrder(
            id="wo-1",
            owner_agent="backend-agent",
            title="Initial",
            goal="Ship runtime",
            acceptance_checks=["pytest"],
            status=WorkOrderStatus.ACTIVE,
        ),
        WorkOrder(
            id="wo-3",
            owner_agent="docs-agent",
            title="Docs",
            goal="Document runtime",
            acceptance_checks=["pytest"],
            status=WorkOrderStatus.PENDING,
        ),
    ]

    merged = merge_work_orders(existing, new)

    assert [work_order.id for work_order in merged] == ["wo-1", "wo-2", "wo-3"]
    assert merged[0].status is WorkOrderStatus.ACTIVE
