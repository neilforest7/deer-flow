from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

ApprovalIntent = Literal["approve", "revise", "cancel", "ambiguous"]

_REVISION_HINTS = (
    "revise",
    "change",
    "adjust",
    "update",
    "split",
    "separate",
    "modify",
    "tighten",
    "rework",
    "fix",
    "add",
    "remove",
)


def parse_approval_intent(messages: list[Any] | None) -> ApprovalIntent:
    text = _latest_user_message_text(messages).strip()
    lowered = text.lower()

    if lowered == "/approve":
        return "approve"
    if lowered.startswith("/revise"):
        return "revise"
    if lowered == "/cancel":
        return "cancel"
    if lowered.startswith("/"):
        return "ambiguous"
    if any(hint in lowered for hint in _REVISION_HINTS):
        return "revise"
    return "ambiguous"


def resolve_approval_update(state: Mapping[str, Any]) -> dict[str, str]:
    plan_status = state.get("plan_status")
    if plan_status == "approved":
        return {"phase": "build", "plan_status": "approved", "goto": "build"}
    if plan_status == "needs_revision":
        return {"phase": "planning", "plan_status": "needs_revision", "goto": "planning"}
    if state.get("phase") == "done":
        return {"phase": "done", "plan_status": str(plan_status or "needs_revision"), "goto": "done"}
    phase = state.get("phase")
    if phase is not None and phase != "awaiting_approval":
        return {"phase": "awaiting_approval", "plan_status": "awaiting_approval", "goto": "__end__"}

    intent = parse_approval_intent(state.get("messages"))
    if intent == "approve":
        return {"phase": "build", "plan_status": "approved", "goto": "build"}
    if intent == "revise":
        return {"phase": "planning", "plan_status": "needs_revision", "goto": "planning"}
    if intent == "cancel":
        return {"phase": "done", "plan_status": str(plan_status or "awaiting_approval"), "goto": "done"}
    return {"phase": "awaiting_approval", "plan_status": str(plan_status or "awaiting_approval"), "goto": "__end__"}


def _latest_user_message_text(messages: list[Any] | None) -> str:
    for message in reversed(messages or []):
        role = _message_role(message)
        if role in {"human", "user"}:
            return _message_text(message).strip()
    return ""


def _message_role(message: Any) -> str | None:
    message_type = getattr(message, "type", None)
    if isinstance(message_type, str):
        return message_type
    if isinstance(message, Mapping):
        role = message.get("type") or message.get("role")
        return role if isinstance(role, str) else None
    class_name = type(message).__name__.lower()
    if "human" in class_name or "user" in class_name:
        return "human"
    return None


def _message_text(message: Any) -> str:
    if isinstance(message, Mapping):
        content = message.get("content")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)
