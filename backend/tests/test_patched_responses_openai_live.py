"""Live contract tests for PatchedResponsesOpenAI.

These tests are opt-in and target a concrete custom Responses endpoint.

Run explicitly:
    DEERFLOW_RESPONSES_TEST_API_KEY=... \
    DEERFLOW_RESPONSES_TEST_BASE_URL=http://192.168.31.7:23000/v1 \
    DEERFLOW_RESPONSES_TEST_MODEL=gpt-5.4 \
    PYTHONPATH=. uv run pytest tests/test_patched_responses_openai_live.py -v -s
"""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from deerflow.models.patched_responses_openai import PatchedResponsesOpenAI

API_KEY = os.environ.get("DEERFLOW_RESPONSES_TEST_API_KEY")
BASE_URL = os.environ.get("DEERFLOW_RESPONSES_TEST_BASE_URL", "http://192.168.31.7:23000/v1")
MODEL = os.environ.get("DEERFLOW_RESPONSES_TEST_MODEL", "gpt-5.4")

if os.environ.get("CI"):
    pytest.skip("Live tests skipped in CI", allow_module_level=True)

if not API_KEY:
    pytest.skip("DEERFLOW_RESPONSES_TEST_API_KEY is required for live custom Responses tests", allow_module_level=True)


@pytest.fixture(scope="module")
def model() -> PatchedResponsesOpenAI:
    return PatchedResponsesOpenAI(
        model=MODEL,
        api_key=API_KEY,
        base_url=BASE_URL,
        output_version="responses/v1",
        timeout=30.0,
        max_retries=0,
    )


@tool
def echo(text: str) -> str:
    """Echo text."""
    return text


def test_invoke_returns_expected_text(model: PatchedResponsesOpenAI):
    message = model.invoke([HumanMessage(content="Reply with exactly: OK")])

    text_blocks = [part["text"] for part in message.content if isinstance(part, dict) and part.get("type") == "text"]
    assert "OK" in "".join(text_blocks)


def test_stream_with_tools_avoids_invalid_tool_calls(model: PatchedResponsesOpenAI):
    chunks = list(model.bind_tools([echo]).stream([HumanMessage(content="Call the echo tool with text set to hi and do not answer directly.")]))

    assert chunks, "Expected at least one streamed chunk"
    assert all(not getattr(chunk, "invalid_tool_calls", None) for chunk in chunks)

    combined = chunks[0]
    for chunk in chunks[1:]:
        combined = combined + chunk

    assert combined.tool_calls
    assert combined.tool_calls[0]["name"] == "echo"
    assert combined.tool_calls[0]["args"] == {"text": "hi"}


def test_reasoning_multi_turn_stays_stable():
    reasoning_model = PatchedResponsesOpenAI(
        model=MODEL,
        api_key=API_KEY,
        base_url=BASE_URL,
        output_version="responses/v1",
        timeout=30.0,
        max_retries=0,
        reasoning={"effort": "low", "summary": "detailed"},
    )

    first = reasoning_model.invoke([HumanMessage(content="Think briefly and answer in one word: blue or red?")])
    second = reasoning_model.invoke(
        [
            HumanMessage(content="Think briefly and answer in one word: blue or red?"),
            first,
            HumanMessage(content="Repeat your answer in uppercase only."),
        ]
    )

    text_blocks = [part["text"] for part in second.content if isinstance(part, dict) and part.get("type") == "text"]
    assert text_blocks
