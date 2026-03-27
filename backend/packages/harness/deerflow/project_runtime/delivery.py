from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow.project_runtime.types import AgentReport, WorkOrder, WorkOrderStatus


def _normalize_work_order(value: WorkOrder | Mapping[str, Any]) -> WorkOrder:
    return WorkOrder.model_validate(value)


def _normalize_report(value: AgentReport | Mapping[str, Any]) -> AgentReport:
    return AgentReport.model_validate(value)


def build_delivery_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    work_orders = [_normalize_work_order(item) for item in state.get("work_orders") or []]
    reports = {_normalize_report(item).work_order_id: _normalize_report(item) for item in state.get("agent_reports") or []}
    qa_gate = state.get("qa_gate") or {}

    completed_work: list[dict[str, str]] = []
    artifacts: list[str] = []
    verification: list[str] = []
    follow_ups: list[str] = []

    for work_order in work_orders:
        if work_order.status is not WorkOrderStatus.COMPLETED:
            continue
        report = reports.get(work_order.id)
        completed_work.append(
            {
                "work_order_id": work_order.id,
                "title": work_order.title,
                "summary": report.summary if report is not None else "",
            }
        )
        if report is not None:
            artifacts.extend(report.changes)
            verification.extend(report.verification)
            follow_ups.extend(report.risks)

    verification.extend(str(item) for item in qa_gate.get("findings") or [])
    follow_ups.extend(str(item) for item in qa_gate.get("required_rework") or [])
    artifacts.extend(str(item) for item in state.get("artifacts") or [])

    def _dedupe(items: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in items if item))

    return {
        "completed_work": completed_work,
        "artifacts": _dedupe(artifacts),
        "verification": _dedupe(verification),
        "follow_ups": _dedupe(follow_ups),
    }
