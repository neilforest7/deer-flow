"""Tests for the built-in project delivery lead-agent prompt."""

from deerflow.agents.lead_agent import prompt as prompt_module


def _stub_prompt_dependencies(monkeypatch):
    monkeypatch.setattr(prompt_module, "_get_memory_context", lambda agent_name=None: "")
    monkeypatch.setattr(prompt_module, "get_skills_prompt_section", lambda available_skills=None: "")
    monkeypatch.setattr(prompt_module, "get_deferred_tools_prompt_section", lambda: "")
    monkeypatch.setattr(prompt_module, "get_agent_soul", lambda agent_name: "")


def test_default_lead_prompt_stays_generic(monkeypatch):
    _stub_prompt_dependencies(monkeypatch)

    prompt = prompt_module.apply_prompt_template(
        subagent_enabled=True,
        max_concurrent_subagents=3,
    )

    assert "<project_delivery_team>" not in prompt
    assert "PROJECT DELIVERY TEAM MODE ACTIVE" not in prompt
    assert "SUBAGENT MODE ACTIVE - DECOMPOSE, DELEGATE, SYNTHESIZE" in prompt


def test_project_lead_prompt_includes_project_delivery_team(monkeypatch):
    _stub_prompt_dependencies(monkeypatch)

    prompt = prompt_module.apply_prompt_template(
        subagent_enabled=True,
        max_concurrent_subagents=3,
        project_delivery_mode=True,
    )

    assert "<project_delivery_team>" in prompt
    assert "lead-agent" in prompt
    assert "ProjectBrief" in prompt
    assert "WorkOrder" in prompt
    assert "AgentReport" in prompt
    assert "GateDecision" in prompt
    assert "qa-agent" in prompt
    assert "delivery-agent" in prompt
    assert "PROJECT DELIVERY TEAM MODE ACTIVE" in prompt


def test_custom_agent_prompt_keeps_generic_subagent_mode(monkeypatch):
    _stub_prompt_dependencies(monkeypatch)

    prompt = prompt_module.apply_prompt_template(
        subagent_enabled=True,
        max_concurrent_subagents=3,
        agent_name="support-bot",
    )

    assert "<project_delivery_team>" not in prompt
    assert "PROJECT DELIVERY TEAM MODE ACTIVE" not in prompt
    assert "SUBAGENT MODE ACTIVE - DECOMPOSE, DELEGATE, SYNTHESIZE" in prompt
