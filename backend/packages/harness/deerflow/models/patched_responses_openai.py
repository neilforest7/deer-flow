"""Patched ChatOpenAI adapter for custom OpenAI-compatible Responses endpoints.

This provider keeps LangChain/OpenAI transport behavior but smooths over two
DeerFlow-specific integration issues we observed on custom Responses endpoints:

1. Streaming tool-call argument fragments show up as transient invalid tool calls.
2. Reasoning summaries are returned as Responses blocks rather than the
   ``additional_kwargs.reasoning_content`` field DeerFlow's frontend already knows.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from json import JSONDecodeError
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import _convert_responses_chunk_to_generation_chunk


def _content_blocks(content: Any) -> list[dict[str, Any]]:
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def _get_value(data: Any, key: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)


def _extract_reasoning_summary_text(content: Any) -> str | None:
    reasoning_parts: list[str] = []

    for block in _content_blocks(content):
        if block.get("type") != "reasoning":
            continue
        summary = block.get("summary")
        if not isinstance(summary, list):
            continue
        for item in summary:
            if not isinstance(item, dict) or item.get("type") != "summary_text":
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                reasoning_parts.append(text.strip())

    return "\n\n".join(reasoning_parts) if reasoning_parts else None


def _normalize_ai_message(message: AIMessage | AIMessageChunk) -> AIMessage | AIMessageChunk:
    reasoning_summary = _extract_reasoning_summary_text(message.content)
    if not reasoning_summary:
        return message

    additional_kwargs = dict(message.additional_kwargs)
    existing = additional_kwargs.get("reasoning_content")
    if isinstance(existing, str) and existing.strip():
        merged = [existing.strip()]
        if reasoning_summary not in merged:
            merged.append(reasoning_summary)
        additional_kwargs["reasoning_content"] = "\n\n".join(merged)
    else:
        additional_kwargs["reasoning_content"] = reasoning_summary

    return message.model_copy(update={"additional_kwargs": additional_kwargs})


def _should_suppress_partial_tool_call_chunk(message: AIMessageChunk) -> bool:
    if getattr(message, "chunk_position", None) == "last":
        return False

    if getattr(message, "invalid_tool_calls", None):
        return True

    tool_call_chunks = getattr(message, "tool_call_chunks", None) or []
    for chunk in tool_call_chunks:
        args = chunk.get("args")
        name = chunk.get("name")
        call_id = chunk.get("id")
        if not isinstance(args, str) or not args.strip():
            return True
        if not name or not call_id:
            return True
        try:
            json.loads(args)
        except JSONDecodeError:
            return True

    for block in _content_blocks(message.content):
        if block.get("type") != "function_call":
            continue
        arguments = block.get("arguments")
        if not isinstance(arguments, str) or not arguments.strip():
            return True
        if not block.get("name") or not block.get("call_id"):
            return True
        try:
            json.loads(arguments)
        except JSONDecodeError:
            return True

    return False


def _normalize_generation_chunk(chunk: ChatGenerationChunk) -> ChatGenerationChunk | None:
    message = chunk.message
    if isinstance(message, AIMessageChunk) and _should_suppress_partial_tool_call_chunk(message):
        return None

    normalized_message = _normalize_ai_message(message)
    if normalized_message is message:
        return chunk

    return ChatGenerationChunk(message=normalized_message, generation_info=chunk.generation_info)


def _normalize_chat_result(result: ChatResult) -> ChatResult:
    generations: list[ChatGeneration] = []

    for generation in result.generations:
        normalized_message = _normalize_ai_message(generation.message)
        if normalized_message is generation.message:
            generations.append(generation)
            continue

        generations.append(
            ChatGeneration(
                message=normalized_message,
                generation_info=generation.generation_info,
            )
        )

    return ChatResult(generations=generations, llm_output=result.llm_output)


def _build_tool_call_generation_chunk(item: Any, *, index: int, metadata: dict | None = None) -> ChatGenerationChunk:
    arguments = _get_value(item, "arguments", "")
    content = [
        {
            "type": "function_call",
            "name": _get_value(item, "name"),
            "arguments": arguments,
            "call_id": _get_value(item, "call_id"),
            "id": _get_value(item, "id"),
            "index": index,
        }
    ]
    tool_call_chunks = [
        {
            "type": "tool_call_chunk",
            "name": _get_value(item, "name"),
            "args": arguments,
            "id": _get_value(item, "call_id"),
            "index": index,
        }
    ]
    message = AIMessageChunk(
        content=content,
        tool_call_chunks=tool_call_chunks,
        response_metadata={"model_provider": "openai", **(metadata or {})},
    )
    return ChatGenerationChunk(message=message)


class PatchedResponsesOpenAI(ChatOpenAI):
    """ChatOpenAI adapter specialized for custom Responses endpoints."""

    use_responses_api: bool | None = True

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        if self._use_responses_api({**kwargs, **self.model_kwargs}):
            return self._stream_responses(*args, **kwargs)
        return super()._stream(*args, **kwargs)

    async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        if self._use_responses_api({**kwargs, **self.model_kwargs}):
            async for chunk in self._astream_responses(*args, **kwargs):
                yield chunk
            return

        async for chunk in super()._astream(*args, **kwargs):
            yield chunk

    def _generate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        return _normalize_chat_result(result)

    async def _agenerate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        result = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        return _normalize_chat_result(result)

    def _stream_responses(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        self._ensure_sync_client_available()
        kwargs["stream"] = True
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        if self.include_response_headers:
            raw_context_manager = self.root_client.with_raw_response.responses.create(**payload)
            context_manager = raw_context_manager.parse()
            headers = {"headers": dict(raw_context_manager.headers)}
        else:
            context_manager = self.root_client.responses.create(**payload)
            headers = {}
        original_schema_obj = kwargs.get("response_format")

        with context_manager as response:
            is_first_chunk = True
            current_index = -1
            current_output_index = -1
            current_sub_index = -1
            has_reasoning = False
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            for raw_chunk in response:
                chunk_type = _get_value(raw_chunk, "type")
                if chunk_type == "response.output_item.added" and _get_value(_get_value(raw_chunk, "item"), "type") == "function_call":
                    output_index = _get_value(raw_chunk, "output_index", -1)
                    if current_output_index != output_index:
                        current_index += 1
                    current_output_index = output_index
                    current_sub_index = -1
                    item = _get_value(raw_chunk, "item")
                    pending_tool_calls[output_index] = {
                        "index": current_index,
                        "name": _get_value(item, "name"),
                        "call_id": _get_value(item, "call_id"),
                        "id": _get_value(item, "id"),
                        "arguments": _get_value(item, "arguments", ""),
                    }
                    continue

                if chunk_type == "response.function_call_arguments.delta":
                    output_index = _get_value(raw_chunk, "output_index", -1)
                    pending = pending_tool_calls.setdefault(
                        output_index,
                        {"index": current_index, "name": None, "call_id": None, "id": _get_value(raw_chunk, "item_id"), "arguments": ""},
                    )
                    pending["arguments"] = f"{pending.get('arguments', '')}{_get_value(raw_chunk, 'delta', '')}"
                    current_output_index = output_index
                    continue

                if chunk_type == "response.function_call_arguments.done":
                    continue

                if chunk_type == "response.output_item.done" and _get_value(_get_value(raw_chunk, "item"), "type") == "function_call":
                    output_index = _get_value(raw_chunk, "output_index", -1)
                    pending = pending_tool_calls.pop(output_index, {})
                    item = _get_value(raw_chunk, "item")
                    item_data = item.model_dump(exclude_none=True, mode="json") if hasattr(item, "model_dump") else dict(item)
                    if pending:
                        item_data.setdefault("name", pending.get("name"))
                        item_data.setdefault("call_id", pending.get("call_id"))
                        item_data.setdefault("id", pending.get("id"))
                        item_data["arguments"] = item_data.get("arguments") or pending.get("arguments", "")
                    normalized_chunk = _normalize_generation_chunk(
                        _build_tool_call_generation_chunk(
                            item_data,
                            index=pending.get("index", current_index),
                            metadata=headers if is_first_chunk else {},
                        )
                    )
                    if normalized_chunk is None:
                        continue
                    if run_manager:
                        run_manager.on_llm_new_token(normalized_chunk.text, chunk=normalized_chunk)
                    is_first_chunk = False
                    yield normalized_chunk
                    continue

                metadata = headers if is_first_chunk else {}
                (
                    current_index,
                    current_output_index,
                    current_sub_index,
                    generation_chunk,
                ) = _convert_responses_chunk_to_generation_chunk(
                    raw_chunk,
                    current_index,
                    current_output_index,
                    current_sub_index,
                    schema=original_schema_obj,
                    metadata=metadata,
                    has_reasoning=has_reasoning,
                    output_version=self.output_version,
                )
                if generation_chunk is None:
                    continue

                normalized_chunk = _normalize_generation_chunk(generation_chunk)
                if normalized_chunk is None:
                    continue

                if run_manager:
                    run_manager.on_llm_new_token(normalized_chunk.text, chunk=normalized_chunk)
                is_first_chunk = False
                if "reasoning_content" in normalized_chunk.message.additional_kwargs or "reasoning" in normalized_chunk.message.additional_kwargs:
                    has_reasoning = True
                yield normalized_chunk

    async def _astream_responses(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        kwargs["stream"] = True
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        if self.include_response_headers:
            raw_context_manager = await self.root_async_client.with_raw_response.responses.create(**payload)
            context_manager = raw_context_manager.parse()
            headers = {"headers": dict(raw_context_manager.headers)}
        else:
            context_manager = await self.root_async_client.responses.create(**payload)
            headers = {}
        original_schema_obj = kwargs.get("response_format")

        async with context_manager as response:
            is_first_chunk = True
            current_index = -1
            current_output_index = -1
            current_sub_index = -1
            has_reasoning = False
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            async for raw_chunk in response:
                chunk_type = _get_value(raw_chunk, "type")
                if chunk_type == "response.output_item.added" and _get_value(_get_value(raw_chunk, "item"), "type") == "function_call":
                    output_index = _get_value(raw_chunk, "output_index", -1)
                    if current_output_index != output_index:
                        current_index += 1
                    current_output_index = output_index
                    current_sub_index = -1
                    item = _get_value(raw_chunk, "item")
                    pending_tool_calls[output_index] = {
                        "index": current_index,
                        "name": _get_value(item, "name"),
                        "call_id": _get_value(item, "call_id"),
                        "id": _get_value(item, "id"),
                        "arguments": _get_value(item, "arguments", ""),
                    }
                    continue

                if chunk_type == "response.function_call_arguments.delta":
                    output_index = _get_value(raw_chunk, "output_index", -1)
                    pending = pending_tool_calls.setdefault(
                        output_index,
                        {"index": current_index, "name": None, "call_id": None, "id": _get_value(raw_chunk, "item_id"), "arguments": ""},
                    )
                    pending["arguments"] = f"{pending.get('arguments', '')}{_get_value(raw_chunk, 'delta', '')}"
                    current_output_index = output_index
                    continue

                if chunk_type == "response.function_call_arguments.done":
                    continue

                if chunk_type == "response.output_item.done" and _get_value(_get_value(raw_chunk, "item"), "type") == "function_call":
                    output_index = _get_value(raw_chunk, "output_index", -1)
                    pending = pending_tool_calls.pop(output_index, {})
                    item = _get_value(raw_chunk, "item")
                    item_data = item.model_dump(exclude_none=True, mode="json") if hasattr(item, "model_dump") else dict(item)
                    if pending:
                        item_data.setdefault("name", pending.get("name"))
                        item_data.setdefault("call_id", pending.get("call_id"))
                        item_data.setdefault("id", pending.get("id"))
                        item_data["arguments"] = item_data.get("arguments") or pending.get("arguments", "")
                    normalized_chunk = _normalize_generation_chunk(
                        _build_tool_call_generation_chunk(
                            item_data,
                            index=pending.get("index", current_index),
                            metadata=headers if is_first_chunk else {},
                        )
                    )
                    if normalized_chunk is None:
                        continue
                    if run_manager:
                        await run_manager.on_llm_new_token(normalized_chunk.text, chunk=normalized_chunk)
                    is_first_chunk = False
                    yield normalized_chunk
                    continue

                metadata = headers if is_first_chunk else {}
                (
                    current_index,
                    current_output_index,
                    current_sub_index,
                    generation_chunk,
                ) = _convert_responses_chunk_to_generation_chunk(
                    raw_chunk,
                    current_index,
                    current_output_index,
                    current_sub_index,
                    schema=original_schema_obj,
                    metadata=metadata,
                    has_reasoning=has_reasoning,
                    output_version=self.output_version,
                )
                if generation_chunk is None:
                    continue

                normalized_chunk = _normalize_generation_chunk(generation_chunk)
                if normalized_chunk is None:
                    continue

                if run_manager:
                    await run_manager.on_llm_new_token(normalized_chunk.text, chunk=normalized_chunk)
                is_first_chunk = False
                if "reasoning_content" in normalized_chunk.message.additional_kwargs or "reasoning" in normalized_chunk.message.additional_kwargs:
                    has_reasoning = True
                yield normalized_chunk
