from __future__ import annotations

import logging

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

import deerflow.models.patched_responses_openai as patched_responses_openai
from deerflow.models.patched_responses_openai import (
    PatchedResponsesOpenAI,
    _normalize_ai_message,
    _normalize_chat_result,
    _normalize_generation_chunk,
    _should_suppress_partial_tool_call_chunk,
)


def _make_model(**kwargs) -> PatchedResponsesOpenAI:
    return PatchedResponsesOpenAI(
        model="gpt-5.4",
        api_key="test-key",
        base_url="https://example.com/v1",
        use_responses_api=True,
        output_version="responses/v1",
        **kwargs,
    )


def test_normalize_ai_message_promotes_reasoning_summary_to_reasoning_content():
    message = AIMessage(
        content=[
            {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": "First step."},
                    {"type": "summary_text", "text": "Second step."},
                ],
            },
            {"type": "text", "text": "Final answer."},
        ]
    )

    normalized = _normalize_ai_message(message)

    assert normalized.additional_kwargs["reasoning_content"] == "First step.\n\nSecond step."
    assert normalized.content == message.content


def test_normalize_ai_message_keeps_encrypted_reasoning_without_fake_summary():
    message = AIMessage(
        content=[
            {
                "type": "reasoning",
                "encrypted_content": "ciphertext",
                "summary": [],
            },
            {"type": "text", "text": "Final answer."},
        ]
    )

    normalized = _normalize_ai_message(message)

    assert "reasoning_content" not in normalized.additional_kwargs
    assert normalized.content == message.content


def test_partial_tool_call_chunks_are_suppressed():
    chunk = AIMessageChunk(
        content=[{"type": "function_call", "arguments": '{"', "index": 0}],
        tool_call_chunks=[{"type": "tool_call_chunk", "args": '{"', "index": 0}],
    )

    assert _should_suppress_partial_tool_call_chunk(chunk) is True
    assert _normalize_generation_chunk(ChatGenerationChunk(message=chunk)) is None


def test_final_chunk_is_not_suppressed():
    chunk = AIMessageChunk(
        content=[{"type": "text", "text": "Done", "index": 0}],
        chunk_position="last",
    )

    assert _should_suppress_partial_tool_call_chunk(chunk) is False
    normalized = _normalize_generation_chunk(ChatGenerationChunk(message=chunk))
    assert normalized is not None
    assert normalized.message.content == chunk.content


def test_complete_tool_call_chunk_is_not_suppressed():
    chunk = AIMessageChunk(
        content=[
            {
                "type": "function_call",
                "name": "echo",
                "arguments": '{"text":"hi"}',
                "call_id": "call-1",
                "id": "fc-1",
                "index": 0,
            }
        ],
        tool_call_chunks=[
            {
                "type": "tool_call_chunk",
                "name": "echo",
                "args": '{"text":"hi"}',
                "id": "call-1",
                "index": 0,
            }
        ],
    )

    assert _should_suppress_partial_tool_call_chunk(chunk) is False
    normalized = _normalize_generation_chunk(ChatGenerationChunk(message=chunk))
    assert normalized is not None
    assert normalized.message.tool_calls == [{"name": "echo", "args": {"text": "hi"}, "id": "call-1", "type": "tool_call"}]


def test_normalize_chat_result_updates_generation_messages():
    result = ChatResult(
        generations=[
            ChatGeneration(
                message=AIMessage(
                    content=[
                        {
                            "type": "reasoning",
                            "summary": [{"type": "summary_text", "text": "Reasoning."}],
                        },
                        {"type": "text", "text": "Answer."},
                    ]
                )
            )
        ],
        llm_output={"token_usage": {"total_tokens": 1}},
    )

    normalized = _normalize_chat_result(result)

    assert normalized.generations[0].message.additional_kwargs["reasoning_content"] == "Reasoning."
    assert normalized.llm_output == result.llm_output


def test_streamed_reasoning_preserves_reasoning_content_without_final_chunk():
    partial_chunks = [
        ChatGenerationChunk(
            message=AIMessageChunk(
                content=[
                    {
                        "type": "reasoning",
                        "summary": [{"index": 0, "type": "summary_text", "text": "First "}],
                        "index": 0,
                        "id": "rs_1",
                    }
                ]
            )
        ),
        ChatGenerationChunk(
            message=AIMessageChunk(
                content=[
                    {
                        "type": "reasoning",
                        "summary": [{"index": 0, "type": "summary_text", "text": "step."}],
                        "index": 0,
                        "id": "rs_1",
                    }
                ]
            )
        ),
        ChatGenerationChunk(
            message=AIMessageChunk(
                content=[
                    {
                        "type": "reasoning",
                        "summary": [{"index": 1, "type": "summary_text", "text": ""}],
                        "index": 1,
                        "id": "rs_1",
                    }
                ]
            )
        ),
        ChatGenerationChunk(
            message=AIMessageChunk(
                content=[
                    {
                        "type": "reasoning",
                        "summary": [{"index": 1, "type": "summary_text", "text": "Second step."}],
                        "index": 1,
                        "id": "rs_1",
                    }
                ]
            )
        ),
    ]

    normalized_partials = [_normalize_generation_chunk(chunk) for chunk in partial_chunks]
    assert all(chunk is not None for chunk in normalized_partials)
    assert [chunk.message.additional_kwargs["reasoning_content"] for chunk in normalized_partials] == [
        "First ",
        "step.",
        "\n\n",
        "Second step.",
    ]

    combined = normalized_partials[0].message
    for chunk in normalized_partials[1:]:
        combined = combined + chunk.message

    assert combined.additional_kwargs["reasoning_content"] == "First step.\n\nSecond step."


def test_provider_defaults_to_responses_api_mode():
    model = _make_model()

    assert model.use_responses_api is True


def test_request_payload_defaults_to_stateful_responses_mode():
    model = _make_model()
    previous = AIMessage(
        content=[{"type": "text", "text": "Hello", "id": "msg_123"}],
        response_metadata={"id": "resp_123", "store": True},
    )

    payload = model._get_request_payload([HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")])

    assert payload["store"] is True
    assert payload["previous_response_id"] == "resp_123"
    assert payload["input"] == [{"content": "Again?", "role": "user"}]


def test_request_payload_accepts_custom_previous_response_id_formats():
    model = _make_model()
    previous = AIMessage(
        content=[{"type": "text", "text": "Hello", "id": "msg_123"}],
        response_metadata={"id": "gateway-123", "store": True},
    )

    payload = model._get_request_payload([HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")])

    assert payload["store"] is True
    assert payload["previous_response_id"] == "gateway-123"
    assert payload["input"] == [{"content": "Again?", "role": "user"}]


def test_request_payload_sanitizes_replayed_ids_for_stateless_mode():
    model = _make_model(
        store=False,
        reasoning={"effort": "low", "summary": "detailed"},
    )
    previous = AIMessage(
        content=[
            {
                "type": "reasoning",
                "id": "rs_123",
                "summary": [{"type": "summary_text", "text": "Thought."}],
                "encrypted_content": "ciphertext",
            },
            {"type": "text", "text": "Hello", "id": "msg_123"},
        ],
        response_metadata={"id": "resp_123"},
    )

    payload = model._get_request_payload([HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")])

    assert payload["store"] is False
    assert "previous_response_id" not in payload
    assert "reasoning.encrypted_content" in payload["include"]

    reasoning_item = next(item for item in payload["input"] if item.get("type") == "reasoning")
    assistant_message = next(item for item in payload["input"] if item.get("type") == "message" and item.get("role") == "assistant")

    assert "id" not in reasoning_item
    assert reasoning_item["encrypted_content"] == "ciphertext"
    assert "id" not in assistant_message


def test_request_payload_sanitizes_replayed_ids_when_previous_response_id_is_unavailable():
    model = _make_model()
    previous = AIMessage(
        content=[
            {
                "type": "reasoning",
                "id": "rs_123",
                "summary": [{"type": "summary_text", "text": "Thought."}],
                "encrypted_content": "ciphertext",
            },
            {"type": "text", "text": "Hello", "id": "msg_123"},
        ]
    )

    payload = model._get_request_payload([HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")])

    assert payload["store"] is True
    assert "previous_response_id" not in payload

    reasoning_item = next(item for item in payload["input"] if item.get("type") == "reasoning")
    assistant_message = next(item for item in payload["input"] if item.get("type") == "message" and item.get("role") == "assistant")

    assert "id" not in reasoning_item
    assert reasoning_item["encrypted_content"] == "ciphertext"
    assert "id" not in assistant_message


def test_stateless_reasoning_replay_warns_without_encrypted_content(caplog: pytest.LogCaptureFixture):
    model = _make_model(
        store=False,
        reasoning={"effort": "low", "summary": "detailed"},
    )
    previous = AIMessage(
        content=[
            {
                "type": "reasoning",
                "id": "rs_123",
                "summary": [{"type": "summary_text", "text": "Thought."}],
            }
        ],
        response_metadata={"id": "resp_123"},
    )

    with caplog.at_level(logging.WARNING):
        payload = model._get_request_payload([HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")])

    assert payload["store"] is False
    assert "reasoning.encrypted_content" in payload["include"]
    assert "multi-turn reasoning continuity may degrade" in caplog.text


def test_stream_responses_avoids_duplicate_reasoning_when_final_chunk_repeats_summary(monkeypatch):
    model = _make_model()

    class _FakeResponse:
        def __init__(self, chunks):
            self._chunks = chunks

        def __enter__(self):
            return iter(self._chunks)

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeResponsesClient:
        def __init__(self, chunks):
            self._chunks = chunks

        def create(self, **payload):
            return _FakeResponse(self._chunks)

    raw_chunks = [
        {"type": "test.partial-1", "generation_chunk": ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "reasoning", "summary": [{"index": 0, "type": "summary_text", "text": "First "}], "index": 0, "id": "rs_1"}]))},
        {"type": "test.partial-2", "generation_chunk": ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "reasoning", "summary": [{"index": 0, "type": "summary_text", "text": "step."}], "index": 0, "id": "rs_1"}]))},
        {"type": "test.partial-3", "generation_chunk": ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "reasoning", "summary": [{"index": 1, "type": "summary_text", "text": ""}], "index": 1, "id": "rs_1"}]))},
        {"type": "test.partial-4", "generation_chunk": ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "reasoning", "summary": [{"index": 1, "type": "summary_text", "text": "Second step."}], "index": 1, "id": "rs_1"}]))},
        {
            "type": "test.final",
            "generation_chunk": ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[
                        {
                            "type": "reasoning",
                            "summary": [{"type": "summary_text", "text": "First step."}],
                            "index": 0,
                            "id": "rs_1",
                        },
                        {
                            "type": "reasoning",
                            "summary": [{"type": "summary_text", "text": "Second step."}],
                            "index": 1,
                            "id": "rs_1",
                        },
                    ],
                    chunk_position="last",
                )
            ),
        },
    ]

    monkeypatch.setattr(model, "_ensure_sync_client_available", lambda: None)
    monkeypatch.setattr(model, "_get_request_payload", lambda *args, **kwargs: {"stream": True})
    monkeypatch.setattr(model, "root_client", type("RootClient", (), {"responses": _FakeResponsesClient(raw_chunks)})())

    def _fake_convert(raw_chunk, current_index, current_output_index, current_sub_index, **kwargs):
        return current_index, current_output_index, current_sub_index, raw_chunk["generation_chunk"]

    monkeypatch.setattr(
        patched_responses_openai,
        "_convert_responses_chunk_to_generation_chunk",
        _fake_convert,
    )

    chunks = list(model._stream_responses([HumanMessage(content="hello")]))

    assert len(chunks) == 5
    assert chunks[-1].message.additional_kwargs == {}

    combined = chunks[0].message
    for chunk in chunks[1:]:
        combined = combined + chunk.message

    assert combined.additional_kwargs["reasoning_content"] == "First step.\n\nSecond step."


def test_stateless_reasoning_effort_payload_requests_encrypted_reasoning():
    model = _make_model(
        store=False,
        reasoning_effort="low",
    )

    payload = model._get_request_payload([HumanMessage(content="Hi")])

    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "low"}
    assert "reasoning.encrypted_content" in payload["include"]


def test_explicit_previous_response_id_is_respected_even_when_store_is_false():
    model = _make_model(store=False)

    payload = model._get_request_payload(
        [HumanMessage(content="Again?")],
        previous_response_id="resp_123",
    )

    assert payload["store"] is False
    assert payload["previous_response_id"] == "resp_123"
    assert payload["input"] == [{"content": "Again?", "role": "user"}]


def test_explicit_previous_response_id_trims_buffered_history_without_store_gate():
    model = _make_model()
    previous = AIMessage(
        content=[
            {
                "type": "function_call",
                "name": "echo",
                "arguments": '{"text":"hi"}',
                "call_id": "call_123",
                "id": "fc_123",
                "status": "completed",
            }
        ],
        tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "call_123", "type": "tool_call"}],
        response_metadata={"id": "resp_123", "store": False},
    )
    tool_result = ToolMessage(content="hi", tool_call_id="call_123", name="echo")

    payload = model._get_request_payload(
        [HumanMessage(content="Start"), previous, tool_result, HumanMessage(content="Again?")],
        previous_response_id="resp_123",
    )

    assert payload["previous_response_id"] == "resp_123"
    assert payload["input"] == [
        {"type": "function_call_output", "output": "hi", "call_id": "call_123"},
        {"content": "Again?", "role": "user"},
    ]


def test_explicit_previous_response_id_keeps_current_behavior_when_buffer_does_not_contain_it():
    model = _make_model()
    previous = AIMessage(
        content=[{"type": "text", "text": "Hello", "id": "msg_123"}],
        response_metadata={"id": "resp_local"},
    )

    payload = model._get_request_payload(
        [HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")],
        previous_response_id="resp_external",
    )

    assert payload["previous_response_id"] == "resp_external"
    assert payload["input"] == [
        {"content": "Hi", "role": "user"},
        {"type": "message", "content": [{"type": "output_text", "text": "Hello", "annotations": []}], "role": "assistant"},
        {"content": "Again?", "role": "user"},
    ]


def test_request_payload_missing_store_does_not_auto_use_previous_response_id():
    model = _make_model()
    previous = AIMessage(
        content=[{"type": "text", "text": "Hello", "id": "msg_123"}],
        response_metadata={"id": "resp_123"},
    )

    payload = model._get_request_payload([HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")])

    assert "previous_response_id" not in payload
    assert payload["input"] == [
        {"content": "Hi", "role": "user"},
        {"type": "message", "content": [{"type": "output_text", "text": "Hello", "annotations": []}], "role": "assistant"},
        {"content": "Again?", "role": "user"},
    ]


def test_request_payload_falls_back_to_full_replay_when_previous_response_was_not_stored():
    model = _make_model()
    previous = AIMessage(
        content=[
            {
                "type": "function_call",
                "name": "echo",
                "arguments": '{"text":"hi"}',
                "call_id": "call_123",
                "id": "fc_123",
                "status": "completed",
            }
        ],
        tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "call_123", "type": "tool_call"}],
        response_metadata={"id": "resp_123", "store": False},
    )
    tool_result = ToolMessage(content="hi", tool_call_id="call_123", name="echo")

    payload = model._get_request_payload([HumanMessage(content="Again?"), previous, tool_result])

    assert payload["store"] is True
    assert "previous_response_id" not in payload
    assert payload["input"] == [
        {"content": "Again?", "role": "user"},
        {
            "arguments": '{"text":"hi"}',
            "call_id": "call_123",
            "name": "echo",
            "type": "function_call",
            "status": "completed",
        },
        {"type": "function_call_output", "output": "hi", "call_id": "call_123"},
    ]


def test_use_previous_response_id_true_can_force_stateful_follow_up_on_unstored_response():
    model = _make_model()
    previous = AIMessage(
        content=[{"type": "text", "text": "Hello", "id": "msg_123"}],
        response_metadata={"id": "resp_123", "store": False},
    )

    payload = model._get_request_payload(
        [HumanMessage(content="Hi"), previous, HumanMessage(content="Again?")],
        use_previous_response_id=True,
    )

    assert payload["previous_response_id"] == "resp_123"
    assert payload["input"] == [{"content": "Again?", "role": "user"}]


def test_chat_fallback_preserves_o_series_developer_role_rewrite():
    model = PatchedResponsesOpenAI(
        model="o3-mini",
        api_key="test-key",
        base_url="https://example.com/v1",
        use_responses_api=False,
    )

    payload = model._get_request_payload([SystemMessage(content="Follow the system rules."), HumanMessage(content="Hi")])

    assert payload["messages"][0]["role"] == "developer"
    assert payload["messages"][1]["role"] == "user"


def test_stream_routes_to_patched_responses_handler(monkeypatch):
    model = _make_model()
    expected = ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "text", "text": "OK", "index": 0}]))

    monkeypatch.setattr(PatchedResponsesOpenAI, "_use_responses_api", lambda self, payload: True)
    monkeypatch.setattr(
        PatchedResponsesOpenAI,
        "_stream_responses",
        lambda self, *args, **kwargs: iter([expected]),
    )

    chunks = list(model._stream([HumanMessage(content="hello")]))

    assert chunks == [expected]
