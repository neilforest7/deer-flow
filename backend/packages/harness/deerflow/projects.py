"""Shared helpers for DeerFlow Project Delivery OS."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from deerflow.store import DEFAULT_PROJECT_TEAM_NAME
from deerflow.store.repositories import utc_now

PROJECT_GRAPH_ID = "project_lead_agent"
PROJECT_VISIBLE_AGENT_NAME = "lead-agent"
PROJECT_MEMORY_SCOPE = "lead-agent"
PROJECT_PHASES = (
    "intake",
    "discovery",
    "architecture",
    "planning",
    "build",
    "qa_gate",
    "delivery",
    "closed",
)
PROJECT_ACTIONS = ("pause", "resume", "abort")
PROJECT_BATCHED_PHASES = frozenset({"build", "qa_gate", "delivery"})
PROJECT_CANONICAL_WORK_ORDER_PHASES = frozenset({"build", "qa_gate", "delivery"})
PROJECT_RETRYABLE_WORK_ORDER_STATUSES = frozenset({"planned", "pending", "failed", "rework_required"})
PROJECT_COMPLETED_WORK_ORDER_STATUSES = frozenset({"completed"})
PROJECT_PHASE_BY_SPECIALIST = {
    "discovery-agent": "discovery",
    "architect-agent": "architecture",
    "planner-agent": "planning",
    "design-agent": "build",
    "frontend-agent": "build",
    "backend-agent": "build",
    "integration-agent": "build",
    "data-agent": "build",
    "devops-agent": "build",
    "qa-agent": "qa_gate",
    "delivery-agent": "delivery",
}

STATUS_PATTERN = re.compile(r"(?im)^\s*(?:status|gate status)\s*[:\-]\s*(pass_with_risk|pass|fail)\s*$")
SECTION_PATTERN = re.compile(
    r"(?ims)^##?\s*(summary|changes_or_findings|risks|verification|blockers|handoff_to)\s*$"
)
JSON_CODE_BLOCK_PATTERN = re.compile(r"```json\s*(?P<payload>\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)


def create_project_id() -> str:
    """Create a new project identifier."""
    return str(uuid.uuid4())


def build_project_brief(*, title: str, objective: str | None = None) -> dict[str, Any]:
    """Build the canonical initial `ProjectBrief` payload."""
    scoped_objective = (objective or title).strip() or title
    return {
        "objective": scoped_objective,
        "target_users": [],
        "deliverables": [],
        "scope_in": [],
        "scope_out": [],
        "constraints": [],
        "success_criteria": [],
        "project_tags": ["software-project"],
    }


def build_project_control(*, pause_requested: bool = False, abort_requested: bool = False) -> dict[str, Any]:
    """Build the canonical project control payload."""
    return {
        "pause_requested": pause_requested,
        "abort_requested": abort_requested,
        "updated_at": utc_now(),
    }


def build_initial_project_state(
    *,
    project_id: str,
    title: str,
    objective: str | None = None,
    team_name: str = DEFAULT_PROJECT_TEAM_NAME,
) -> dict[str, Any]:
    """Build the initial LangGraph state for a new project thread."""
    brief = build_project_brief(title=title, objective=objective)
    control_flags = build_project_control()
    return {
        "project_id": project_id,
        "project_title": title,
        "title": title,
        "team_name": team_name,
        "project_phase": "intake",
        "project_status": "draft",
        "project_brief": brief,
        "work_orders": [],
        "agent_reports": [],
        "gate_decision": None,
        "delivery_pack": None,
        "active_batch": None,
        "control_flags": control_flags,
        "artifacts": [],
        "messages": [],
    }


def build_project_index(
    *,
    project_id: str,
    thread_id: str,
    title: str,
    objective: str | None = None,
    team_name: str = DEFAULT_PROJECT_TEAM_NAME,
) -> dict[str, Any]:
    """Build the project index record stored in LangGraph Store."""
    now = utc_now()
    return {
        "project_id": project_id,
        "thread_id": thread_id,
        "assistant_id": PROJECT_GRAPH_ID,
        "visible_agent_name": PROJECT_VISIBLE_AGENT_NAME,
        "title": title,
        "description": (objective or title).strip() or title,
        "status": "draft",
        "phase": "intake",
        "team_name": team_name,
        "created_at": now,
        "updated_at": now,
        "artifacts": [],
        "latest_gate": None,
    }


def compose_project_record(
    index: dict[str, Any],
    *,
    snapshot: dict[str, Any] | None = None,
    control_flags: dict[str, Any] | None = None,
    runtime_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge index, snapshot, and latest runtime values into one API payload."""
    snapshot = deepcopy(snapshot or {})
    control_flags = deepcopy(control_flags or build_project_control())
    runtime_values = deepcopy(runtime_values or {})
    merged = deepcopy(index)

    source = snapshot
    if runtime_values:
        source.update({k: v for k, v in runtime_values.items() if v is not None})

    merged.update(
        {
            "project_title": source.get("project_title") or merged.get("title"),
            "project_brief": source.get("project_brief"),
            "work_orders": source.get("work_orders") or [],
            "agent_reports": source.get("agent_reports") or [],
            "gate_decision": source.get("gate_decision"),
            "delivery_pack": source.get("delivery_pack"),
            "active_batch": source.get("active_batch"),
            "artifacts": source.get("artifacts") or merged.get("artifacts") or [],
            "control_flags": control_flags,
        }
    )

    merged["phase"] = source.get("project_phase") or merged.get("phase", "intake")
    merged["status"] = source.get("project_status") or merged.get("status", "draft")
    return merged


def apply_project_action_payload(current: dict[str, Any], action: str) -> dict[str, Any]:
    """Return the next control payload for a project action."""
    if action not in PROJECT_ACTIONS:
        raise ValueError(f"Unsupported project action: {action}")

    pause_requested = bool(current.get("pause_requested"))
    abort_requested = bool(current.get("abort_requested"))

    if action == "pause":
        pause_requested = True
    elif action == "resume":
        pause_requested = False
        abort_requested = False
    elif action == "abort":
        pause_requested = False
        abort_requested = True

    return build_project_control(
        pause_requested=pause_requested,
        abort_requested=abort_requested,
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _split_markdown_section_lines(content: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {
        "summary": [],
        "changes_or_findings": [],
        "risks": [],
        "verification": [],
        "blockers": [],
        "handoff_to": [],
    }
    current_section: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        section_match = SECTION_PATTERN.match(line)
        if section_match:
            current_section = section_match.group(1).lower()
            continue

        if current_section is None:
            continue

        parsed[current_section].append(line.removeprefix("- ").strip())

    return parsed


def normalize_work_order(raw: Mapping[str, Any], *, now: str | None = None) -> dict[str, Any] | None:
    order_id = str(raw.get("id") or "").strip()
    owner_agent = str(raw.get("owner_agent") or "").strip()
    if not order_id or not owner_agent:
        return None

    phase = str(raw.get("phase") or PROJECT_PHASE_BY_SPECIALIST.get(owner_agent, "build"))
    if phase not in PROJECT_PHASES:
        phase = PROJECT_PHASE_BY_SPECIALIST.get(owner_agent, "build")

    description = str(raw.get("description") or raw.get("goal") or order_id).strip() or order_id
    goal = str(raw.get("goal") or description).strip() or description
    status = str(raw.get("status") or "planned").strip().lower() or "planned"

    return {
        "id": order_id,
        "owner_agent": owner_agent,
        "description": description,
        "prompt": str(raw.get("prompt") or "").strip(),
        "goal": goal,
        "read_scope": _string_list(raw.get("read_scope")),
        "write_scope": _string_list(raw.get("write_scope")),
        "dependencies": _string_list(raw.get("dependencies")),
        "verification_steps": _string_list(raw.get("verification_steps")),
        "done_definition": _string_list(raw.get("done_definition")),
        "status": status,
        "phase": phase,
        "result": str(raw.get("result") or "").strip(),
        "updated_at": str(raw.get("updated_at") or now or utc_now()),
    }


def parse_work_orders_from_report(content: str, *, now: str | None = None) -> list[dict[str, Any]]:
    payloads = list(JSON_CODE_BLOCK_PATTERN.finditer(content))
    blocks = [match.group("payload") for match in payloads]
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        blocks.append(stripped)

    for raw_block in reversed(blocks):
        try:
            parsed = json.loads(raw_block)
        except json.JSONDecodeError:
            continue

        if not isinstance(parsed, Mapping):
            continue
        work_orders = parsed.get("work_orders")
        if not isinstance(work_orders, list):
            continue

        normalized = [
            normalized_order
            for item in work_orders
            if isinstance(item, Mapping)
            and (normalized_order := normalize_work_order(item, now=now)) is not None
        ]
        if normalized:
            return normalized

    return []


def merge_canonical_work_orders(
    existing_orders: Sequence[Mapping[str, Any]],
    canonical_orders: Sequence[Mapping[str, Any]],
    *,
    now: str | None = None,
) -> list[dict[str, Any]]:
    timestamp = now or utc_now()
    existing_by_id = {
        item["id"]: dict(item)
        for item in existing_orders
        if isinstance(item, Mapping) and item.get("id")
    }

    preserved_orders = [
        dict(item)
        for item in existing_orders
        if isinstance(item, Mapping) and item.get("phase") not in PROJECT_CANONICAL_WORK_ORDER_PHASES
    ]

    merged_canonical: list[dict[str, Any]] = []
    for raw_order in canonical_orders:
        normalized = normalize_work_order(raw_order, now=timestamp)
        if normalized is None:
            continue

        existing = existing_by_id.get(normalized["id"])
        if existing is not None:
            existing_status = str(existing.get("status") or "").lower()
            if existing_status and existing_status != "planned":
                normalized["status"] = existing_status
                normalized["result"] = str(existing.get("result") or normalized["result"])
                normalized["updated_at"] = str(existing.get("updated_at") or normalized["updated_at"])
            if not normalized["prompt"]:
                normalized["prompt"] = str(existing.get("prompt") or "")
            if not normalized["description"]:
                normalized["description"] = str(existing.get("description") or normalized["goal"])
        merged_canonical.append(normalized)

    return preserved_orders + merged_canonical


def is_work_order_retryable(order: Mapping[str, Any]) -> bool:
    status = str(order.get("status") or "").lower()
    if status == "in_progress":
        return False
    if status in PROJECT_COMPLETED_WORK_ORDER_STATUSES:
        return False
    return status in PROJECT_RETRYABLE_WORK_ORDER_STATUSES or not status


def dependencies_satisfied(order: Mapping[str, Any], work_orders_by_id: Mapping[str, Mapping[str, Any]]) -> bool:
    dependencies = _string_list(order.get("dependencies"))
    if not dependencies:
        return True

    for dependency_id in dependencies:
        dependency = work_orders_by_id.get(dependency_id)
        if dependency is None:
            return False
        if str(dependency.get("status") or "").lower() not in PROJECT_COMPLETED_WORK_ORDER_STATUSES:
            return False
    return True


def _normalize_scope_path(path: str) -> str:
    candidate = path.strip().replace("\\", "/")
    if not candidate:
        return ""

    pure_path = PurePosixPath(candidate)
    normalized_parts = [part for part in pure_path.parts if part not in ("", ".", "/")]
    normalized = "/".join(normalized_parts)
    if candidate.startswith("/"):
        normalized = f"/{normalized}" if normalized else "/"
    return normalized.rstrip("/") or normalized


def write_scopes_conflict(left_scope: Sequence[str], right_scope: Sequence[str]) -> bool:
    left_paths = [_normalize_scope_path(path) for path in left_scope if _normalize_scope_path(path)]
    right_paths = [_normalize_scope_path(path) for path in right_scope if _normalize_scope_path(path)]
    if not left_paths or not right_paths:
        return False

    for left_path in left_paths:
        for right_path in right_paths:
            if left_path == right_path:
                return True
            left_prefix = f"{left_path}/"
            right_prefix = f"{right_path}/"
            if right_path.startswith(left_prefix) or left_path.startswith(right_prefix):
                return True
    return False


def select_active_batch(
    work_orders: Sequence[Mapping[str, Any]],
    *,
    phase: str,
    max_parallelism: int,
    now: str | None = None,
) -> dict[str, Any] | None:
    if phase not in PROJECT_BATCHED_PHASES:
        return None

    timestamp = now or utc_now()
    parallelism = max(1, int(max_parallelism or 1))
    work_orders_by_id = {
        str(item["id"]): dict(item)
        for item in work_orders
        if isinstance(item, Mapping) and item.get("id")
    }

    in_progress = [
        item
        for item in work_orders
        if isinstance(item, Mapping)
        and item.get("phase") == phase
        and str(item.get("status") or "").lower() == "in_progress"
    ]
    if in_progress:
        return {
            "batch_id": f"batch-{timestamp}",
            "phase": phase,
            "work_order_ids": [str(item["id"]) for item in in_progress if item.get("id")],
            "status": "running",
            "started_at": timestamp,
            "updated_at": timestamp,
        }

    ready_orders = [
        dict(item)
        for item in work_orders
        if isinstance(item, Mapping)
        and item.get("phase") == phase
        and is_work_order_retryable(item)
        and dependencies_satisfied(item, work_orders_by_id)
    ]
    if not ready_orders:
        return None

    selected: list[dict[str, Any]] = []
    for order in ready_orders:
        if phase in {"qa_gate", "delivery"}:
            selected = [order]
            break

        write_scope = _string_list(order.get("write_scope"))
        if not write_scope:
            selected = [order]
            break

        if any(write_scopes_conflict(write_scope, _string_list(current.get("write_scope"))) for current in selected):
            continue

        selected.append(order)
        if len(selected) >= parallelism:
            break

    if not selected:
        selected = [ready_orders[0]]

    return {
        "batch_id": f"batch-{timestamp}",
        "phase": phase,
        "work_order_ids": [str(item["id"]) for item in selected if item.get("id")],
        "status": "ready",
        "started_at": timestamp,
        "updated_at": timestamp,
    }


def project_work_order_by_id(work_orders: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): dict(item)
        for item in work_orders
        if isinstance(item, Mapping) and item.get("id")
    }


def compute_project_state_projection(
    state: Mapping[str, Any],
    *,
    control_flags: Mapping[str, Any] | None = None,
    max_parallelism: int = 3,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    work_orders: dict[str, dict[str, Any]] = {
        item["id"]: dict(item)
        for item in (state.get("work_orders") or [])
        if isinstance(item, Mapping) and item.get("id")
    }
    reports: dict[str, dict[str, Any]] = {
        item["id"]: dict(item)
        for item in (state.get("agent_reports") or [])
        if isinstance(item, Mapping) and item.get("id")
    }
    gate_decision = dict(state.get("gate_decision") or {}) or None
    delivery_pack = dict(state.get("delivery_pack") or {}) or None
    tool_call_work_order_ids: dict[str, str] = {}

    for message in state.get("messages", []) or []:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls or []:
                if tool_call.get("name") != "task":
                    continue

                tool_call_id = str(tool_call.get("id") or "").strip()
                args = tool_call.get("args", {}) or {}
                owner_agent = str(args.get("subagent_type") or "general-purpose")
                work_order_id = str(args.get("work_order_id") or tool_call_id).strip()
                if not work_order_id:
                    continue

                existing = work_orders.get(work_order_id, {})
                work_orders[work_order_id] = {
                    "id": work_order_id,
                    "owner_agent": owner_agent,
                    "description": str(args.get("description") or existing.get("description") or work_order_id).strip(),
                    "prompt": str(args.get("prompt") or existing.get("prompt") or "").strip(),
                    "goal": str(existing.get("goal") or args.get("description") or work_order_id).strip(),
                    "read_scope": _string_list(existing.get("read_scope")),
                    "write_scope": _string_list(existing.get("write_scope")),
                    "dependencies": _string_list(existing.get("dependencies")),
                    "verification_steps": _string_list(existing.get("verification_steps")),
                    "done_definition": _string_list(existing.get("done_definition")),
                    "status": "in_progress",
                    "phase": PROJECT_PHASE_BY_SPECIALIST.get(owner_agent, str(existing.get("phase") or "build")),
                    "result": str(existing.get("result") or ""),
                    "updated_at": timestamp,
                }
                if tool_call_id:
                    tool_call_work_order_ids[tool_call_id] = work_order_id

        elif isinstance(message, ToolMessage):
            tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
            work_order_id = tool_call_work_order_ids.get(tool_call_id, tool_call_id)
            if not work_order_id or work_order_id not in work_orders:
                continue

            result = _extract_text(message.content).strip()
            order = work_orders[work_order_id]
            owner_agent = str(order.get("owner_agent") or "general-purpose")
            status = "completed"
            if result.startswith("Task failed.") or result.startswith("Task timed out") or result.startswith("Error:"):
                status = "failed"

            order["status"] = status
            order["result"] = result
            order["updated_at"] = timestamp

            structured_sections = _split_markdown_section_lines(result)
            summary_lines = structured_sections.get("summary") or []
            summary_text = summary_lines[0] if summary_lines else (order.get("description") or work_order_id)
            reports[work_order_id] = {
                "id": work_order_id,
                "owner_agent": owner_agent,
                "summary": summary_text,
                "details": result,
                "changes_or_findings": structured_sections.get("changes_or_findings", []),
                "risks": structured_sections.get("risks", []),
                "verification": structured_sections.get("verification", []),
                "blockers": structured_sections.get("blockers", []),
                "handoff_to": structured_sections.get("handoff_to", []),
                "updated_at": timestamp,
            }

            if owner_agent == "planner-agent":
                planner_work_orders = parse_work_orders_from_report(result, now=timestamp)
                if planner_work_orders:
                    merged_orders = merge_canonical_work_orders(
                        list(work_orders.values()),
                        planner_work_orders,
                        now=timestamp,
                    )
                    work_orders = project_work_order_by_id(merged_orders)

            if owner_agent == "qa-agent":
                status_match = STATUS_PATTERN.search(result)
                gate_status = status_match.group(1) if status_match else ("fail" if "fail" in result.lower() else "pass")
                gate_decision = {
                    "status": gate_status,
                    "blocking_issues": structured_sections.get("blockers", []),
                    "residual_risks": structured_sections.get("risks", []),
                    "required_rework": structured_sections.get("handoff_to", []),
                    "updated_at": timestamp,
                }
                if gate_status == "fail":
                    delivery_pack = None

            if owner_agent == "delivery-agent":
                delivery_pack = {
                    "status": "packaged" if status == "completed" else "failed",
                    "artifacts": list(state.get("artifacts") or []),
                    "notes": [result[:500]] if result else [],
                    "updated_at": timestamp,
                }

    control = dict(control_flags or state.get("control_flags") or {})
    phase, status = derive_project_phase_and_status(
        state,
        work_orders=list(work_orders.values()),
        gate_decision=gate_decision,
        delivery_pack=delivery_pack,
        control_flags=control,
    )
    active_batch = select_active_batch(
        list(work_orders.values()),
        phase=phase,
        max_parallelism=max_parallelism,
        now=timestamp,
    )

    return {
        "work_orders": list(work_orders.values()),
        "agent_reports": list(reports.values()),
        "gate_decision": gate_decision,
        "delivery_pack": delivery_pack,
        "active_batch": active_batch,
        "project_phase": phase,
        "project_status": status,
    }


def derive_project_phase_and_status(
    state: Mapping[str, Any],
    *,
    work_orders: Sequence[Mapping[str, Any]],
    gate_decision: Mapping[str, Any] | None,
    delivery_pack: Mapping[str, Any] | None,
    control_flags: Mapping[str, Any] | None,
) -> tuple[str, str]:
    control = dict(control_flags or {})
    current_phase = str(state.get("project_phase") or "intake")
    current_status = str(state.get("project_status") or "draft")

    if control.get("abort_requested"):
        return "closed", "aborted"
    if control.get("pause_requested"):
        return current_phase, "paused"

    gate_status = str((gate_decision or {}).get("status") or "").lower()
    delivery_status = str((delivery_pack or {}).get("status") or "").lower()
    canonical_orders = [dict(item) for item in work_orders if isinstance(item, Mapping)]

    build_orders = [item for item in canonical_orders if item.get("phase") == "build"]
    build_pending = [item for item in build_orders if is_work_order_retryable(item)]
    qa_orders = [item for item in canonical_orders if item.get("phase") == "qa_gate"]
    qa_pending = [item for item in qa_orders if is_work_order_retryable(item)]
    delivery_orders = [item for item in canonical_orders if item.get("phase") == "delivery"]
    delivery_pending = [item for item in delivery_orders if is_work_order_retryable(item)]

    if gate_status == "fail":
        if build_pending:
            return "build", "rework_required"
        return "planning", "rework_required"

    if delivery_status == "packaged" and gate_status in {"pass", "pass_with_risk"}:
        return "closed", "ready_with_risk" if gate_status == "pass_with_risk" else "completed"

    if build_pending or any(str(item.get("status") or "").lower() == "in_progress" for item in build_orders):
        return "build", "active"
    if build_orders and not gate_status:
        return "qa_gate", "active"
    if qa_pending or any(str(item.get("status") or "").lower() == "in_progress" for item in qa_orders):
        return "qa_gate", "active"
    if any(str(item.get("status") or "").lower() == "in_progress" for item in delivery_orders):
        return "delivery", "active"
    if gate_status in {"pass", "pass_with_risk"}:
        return "delivery", "ready_with_risk" if gate_status == "pass_with_risk" else "ready_for_delivery"
    if delivery_pending or any(str(item.get("status") or "").lower() == "in_progress" for item in delivery_orders):
        return "delivery", "active"

    if canonical_orders:
        latest = sorted(canonical_orders, key=lambda item: str(item.get("updated_at") or ""))[-1]
        latest_phase = str(latest.get("phase") or current_phase)
        if latest_phase in PROJECT_PHASES:
            return latest_phase, "active"

    return current_phase, current_status
