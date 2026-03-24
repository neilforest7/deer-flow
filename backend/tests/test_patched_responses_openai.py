from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

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
        content=[{"type": "function_call", "arguments": "{\"", "index": 0}],
        tool_call_chunks=[{"type": "tool_call_chunk", "args": "{\"", "index": 0}],
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


def test_provider_defaults_to_responses_api_mode():
    model = _make_model()

    assert model.use_responses_api is True


def test_stream_routes_to_patched_responses_handler(monkeypatch):
    model = _make_model()
    expected = ChatGenerationChunk(
        message=AIMessageChunk(content=[{"type": "text", "text": "OK", "index": 0}])
    )

    monkeypatch.setattr(PatchedResponsesOpenAI, "_use_responses_api", lambda self, payload: True)
    monkeypatch.setattr(
        PatchedResponsesOpenAI,
        "_stream_responses",
        lambda self, *args, **kwargs: iter([expected]),
    )

    chunks = list(model._stream([HumanMessage(content="hello")]))

    assert chunks == [expected]
