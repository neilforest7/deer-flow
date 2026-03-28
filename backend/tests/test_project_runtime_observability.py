from types import SimpleNamespace

from deerflow.project_runtime.observability import (
    build_delivery_specialist_metadata,
    build_discovery_specialist_metadata,
    build_planning_specialist_metadata,
    resolve_trace_id,
)


def test_resolve_trace_id_prefers_persisted_state(monkeypatch):
    monkeypatch.setattr(
        "deerflow.project_runtime.observability.get_config",
        lambda: {"metadata": {"trace_id": "config-trace"}},
    )

    trace_id = resolve_trace_id(
        {"trace_id": "state-trace"},
        runtime=SimpleNamespace(context={"trace_id": "context-trace"}),
    )

    assert trace_id == "state-trace"


def test_resolve_trace_id_prefers_runtime_context_over_config(monkeypatch):
    monkeypatch.setattr(
        "deerflow.project_runtime.observability.get_config",
        lambda: {"metadata": {"trace_id": "config-trace"}},
    )

    trace_id = resolve_trace_id({}, runtime=SimpleNamespace(context={"trace_id": "context-trace"}))

    assert trace_id == "context-trace"


def test_resolve_trace_id_prefers_config_metadata_over_generated(monkeypatch):
    monkeypatch.setattr(
        "deerflow.project_runtime.observability.get_config",
        lambda: {"metadata": {"trace_id": "config-trace"}},
    )

    trace_id = resolve_trace_id({})

    assert trace_id == "config-trace"


def test_resolve_trace_id_generates_short_id_when_no_source_exists(monkeypatch):
    monkeypatch.setattr("deerflow.project_runtime.observability.get_config", lambda: {})
    monkeypatch.setattr("deerflow.project_runtime.observability.uuid.uuid4", lambda: "generated-trace-id")

    trace_id = resolve_trace_id({})

    assert trace_id == "generate"


def test_build_discovery_specialist_metadata_contains_expected_fields():
    metadata = build_discovery_specialist_metadata(
        thread_id="thread-1",
        plan_status="draft",
        trace_id="trace-root",
        owner_agent="architect-agent",
        attempt=2,
    )

    assert set(metadata) == {
        "runtime",
        "thread_id",
        "phase",
        "plan_status",
        "project_runtime_version",
        "trace_id",
        "work_order_id",
        "owner_agent",
        "execution_kind",
    }
    assert metadata["phase"] == "discovery"
    assert metadata["execution_kind"] == "discovery_specialist"
    assert metadata["owner_agent"] == "architect-agent"
    assert metadata["trace_id"] == "trace-root"
    assert metadata["work_order_id"] == "phase:discovery:architect-agent:attempt:2"


def test_build_planning_specialist_metadata_contains_expected_fields():
    metadata = build_planning_specialist_metadata(
        thread_id="thread-2",
        plan_status="awaiting_approval",
        trace_id="planning-trace",
        attempt=3,
    )

    assert set(metadata) == {
        "runtime",
        "thread_id",
        "phase",
        "plan_status",
        "project_runtime_version",
        "trace_id",
        "work_order_id",
        "owner_agent",
        "execution_kind",
    }
    assert metadata["phase"] == "planning"
    assert metadata["execution_kind"] == "planning_specialist"
    assert metadata["owner_agent"] == "planner-agent"
    assert metadata["trace_id"] == "planning-trace"
    assert metadata["work_order_id"] == "phase:planning:planner-agent:attempt:3"


def test_build_delivery_specialist_metadata_contains_expected_fields():
    metadata = build_delivery_specialist_metadata(
        thread_id="thread-3",
        plan_status="approved",
        trace_id="delivery-trace",
        attempt=4,
    )

    assert set(metadata) == {
        "runtime",
        "thread_id",
        "phase",
        "plan_status",
        "project_runtime_version",
        "trace_id",
        "work_order_id",
        "owner_agent",
        "execution_kind",
    }
    assert metadata["phase"] == "delivery"
    assert metadata["execution_kind"] == "delivery_specialist"
    assert metadata["owner_agent"] == "delivery-agent"
    assert metadata["trace_id"] == "delivery-trace"
    assert metadata["work_order_id"] == "phase:delivery:delivery-agent:attempt:4"
