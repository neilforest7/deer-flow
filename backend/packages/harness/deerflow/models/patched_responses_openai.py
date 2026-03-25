"""Patched ChatOpenAI adapter for custom OpenAI-compatible Responses endpoints.

This provider keeps LangChain/OpenAI transport behavior but smooths over two
DeerFlow-specific integration issues we observed on custom Responses endpoints:

1. Streaming tool-call argument fragments show up as transient invalid tool calls.
2. Reasoning summaries are returned as Responses blocks rather than the
   ``additional_kwargs.reasoning_content`` field DeerFlow's frontend already knows.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator
from json import JSONDecodeError
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import (
    _construct_lc_result_from_responses_api,
    _construct_responses_api_payload,
    _convert_responses_chunk_to_generation_chunk,
    _is_pydantic_class,
)

logger = logging.getLogger(__name__)

_REASONING_ENCRYPTED_CONTENT_INCLUDE = "reasoning.encrypted_content"
_RESPONSES_OUTPUT_ITEM_TYPES = {
    "code_interpreter_call",
    "computer_call",
    "custom_tool_call",
    "file_search_call",
    "function_call",
    "image_generation_call",
    "mcp_approval_request",
    "mcp_call",
    "mcp_list_tools",
    "message",
    "reasoning",
    "web_search_call",
}


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
        summary_parts: list[str] = []
        for item in summary:
            if not isinstance(item, dict) or item.get("type") != "summary_text":
                continue
            text = item.get("text")
            if isinstance(text, str) and text:
                summary_parts.append(text)

        if summary_parts:
            reasoning_parts.append("\n\n".join(summary_parts))

    if not reasoning_parts:
        return None

    reasoning_summary = "\n\n".join(reasoning_parts).strip()
    return reasoning_summary or None


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


def _ensure_reasoning_encrypted_content_include(payload: dict[str, Any]) -> None:
    include = payload.get("include")
    if include is None:
        payload["include"] = [_REASONING_ENCRYPTED_CONTENT_INCLUDE]
        return

    include_values = list(include)
    if _REASONING_ENCRYPTED_CONTENT_INCLUDE not in include_values:
        include_values.append(_REASONING_ENCRYPTED_CONTENT_INCLUDE)
    payload["include"] = include_values


def _should_auto_use_previous_response_id(
    use_previous_response_id: bool | None,
    store: bool,
) -> bool:
    return store is not False and use_previous_response_id is not False


def _response_metadata_allows_previous_response_id(
    response_metadata: dict[str, Any],
    *,
    allow_unverified: bool,
) -> bool:
    if allow_unverified:
        return True
    return response_metadata.get("store") is True


def _get_messages_after_response_id(
    messages: list[Any],
    response_id: str,
) -> list[Any] | None:
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, AIMessage):
            continue
        msg_response_id = msg.response_metadata.get("id")
        if isinstance(msg_response_id, str) and msg_response_id == response_id:
            return list(messages[i + 1 :])

    return None


def _get_last_messages_for_custom_responses(
    messages: list[Any],
    *,
    allow_unverified_previous_response_id: bool = False,
) -> tuple[list[Any], str | None]:
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, AIMessage):
            continue
        response_id = msg.response_metadata.get("id")
        if isinstance(response_id, str) and response_id.strip():
            if not _response_metadata_allows_previous_response_id(
                msg.response_metadata,
                allow_unverified=allow_unverified_previous_response_id,
            ):
                logger.info(
                    "Responses replay falling back to stateless mode because the prior response was not confirmed as stored: response_id=%s store=%r",
                    response_id,
                    msg.response_metadata.get("store"),
                )
                return list(messages), None
            return list(messages[i + 1 :]), response_id

    return list(messages), None


def _is_replayed_responses_output_item(item: dict[str, Any]) -> bool:
    item_type = item.get("type")
    if item_type not in _RESPONSES_OUTPUT_ITEM_TYPES:
        return False
    if item_type == "message":
        return item.get("role") == "assistant"
    return True


def _sanitize_responses_input(
    input_items: list[Any],
) -> tuple[list[Any], bool, bool]:
    sanitized_input: list[Any] = []
    has_reasoning = False
    has_encrypted_reasoning = False

    for item in input_items:
        if not isinstance(item, dict):
            sanitized_input.append(item)
            continue

        sanitized_item = dict(item)
        if _is_replayed_responses_output_item(sanitized_item):
            sanitized_item.pop("id", None)

        if sanitized_item.get("type") == "reasoning":
            has_reasoning = True
            encrypted_content = sanitized_item.get("encrypted_content")
            if isinstance(encrypted_content, str) and encrypted_content:
                has_encrypted_reasoning = True

        sanitized_input.append(sanitized_item)

    return sanitized_input, has_reasoning, has_encrypted_reasoning


def _extract_response_metadata_flags(response: Any) -> dict[str, Any]:
    if response is None:
        return {}

    if hasattr(response, "model_dump"):
        data = response.model_dump(exclude_none=True, mode="json")
    elif isinstance(response, dict):
        data = response
    else:
        data = {}

    metadata: dict[str, Any] = {}
    for key in ("store", "previous_response_id"):
        if key in data:
            metadata[key] = data[key]
    return metadata


def _apply_response_metadata_flags_to_message(
    message: AIMessage | AIMessageChunk,
    metadata_flags: dict[str, Any],
) -> AIMessage | AIMessageChunk:
    if not metadata_flags:
        return message

    response_metadata = dict(message.response_metadata)
    response_metadata.update(metadata_flags)
    return message.model_copy(update={"response_metadata": response_metadata})


def _apply_response_metadata_flags_to_result(
    result: ChatResult,
    metadata_flags: dict[str, Any],
) -> ChatResult:
    if not metadata_flags:
        return result

    generations: list[ChatGeneration] = []
    for generation in result.generations:
        updated_message = _apply_response_metadata_flags_to_message(
            generation.message,
            metadata_flags,
        )
        if updated_message is generation.message:
            generations.append(generation)
            continue
        generations.append(
            ChatGeneration(
                message=updated_message,
                generation_info=generation.generation_info,
            )
        )

    return ChatResult(generations=generations, llm_output=result.llm_output)


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

    if isinstance(message, AIMessageChunk) and getattr(message, "chunk_position", None) != "last":
        reasoning_fragment = _extract_reasoning_stream_fragment(message.content)
        if reasoning_fragment is None:
            return chunk

        additional_kwargs = dict(message.additional_kwargs)
        existing = additional_kwargs.get("reasoning_content")
        if isinstance(existing, str):
            additional_kwargs["reasoning_content"] = f"{existing}{reasoning_fragment}"
        else:
            additional_kwargs["reasoning_content"] = reasoning_fragment

        normalized_message = message.model_copy(update={"additional_kwargs": additional_kwargs})
        return ChatGenerationChunk(message=normalized_message, generation_info=chunk.generation_info)

    normalized_message = _normalize_ai_message(message)
    if normalized_message is message:
        return chunk

    return ChatGenerationChunk(message=normalized_message, generation_info=chunk.generation_info)


def _extract_reasoning_stream_fragment(content: Any) -> str | None:
    fragments: list[str] = []

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
            summary_index = item.get("index")
            if text == "":
                if isinstance(summary_index, int) and summary_index > 0:
                    fragments.append("\n\n")
                continue
            if isinstance(text, str):
                fragments.append(text)

    if not fragments:
        return None
    return "".join(fragments)


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
    use_previous_response_id: bool | None = None

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        invocation_kwargs = dict(kwargs)
        if stop is not None:
            invocation_kwargs["stop"] = stop

        if not self._use_responses_api({**self._default_params, **invocation_kwargs}):
            return super()._get_request_payload(input_, stop=stop, **kwargs)

        messages = self._convert_input(input_).to_messages()
        use_previous_response_id = invocation_kwargs.pop(
            "use_previous_response_id",
            self.use_previous_response_id,
        )
        payload = {**self._default_params, **invocation_kwargs}
        store = payload.get("store")
        if store is None:
            payload["store"] = True
            store = True

        should_sanitize_replayed_input = False
        explicit_previous_response_id = payload.get("previous_response_id")
        if explicit_previous_response_id:
            trimmed_messages = _get_messages_after_response_id(
                messages,
                explicit_previous_response_id,
            )
            if trimmed_messages is None or not trimmed_messages:
                payload_to_use = messages
                should_sanitize_replayed_input = True
            else:
                payload_to_use = trimmed_messages
        elif _should_auto_use_previous_response_id(use_previous_response_id, store):
            last_messages, previous_response_id = _get_last_messages_for_custom_responses(
                messages,
                allow_unverified_previous_response_id=use_previous_response_id is True,
            )
            payload_to_use = last_messages if previous_response_id else messages
            if previous_response_id:
                payload["previous_response_id"] = previous_response_id
        else:
            payload_to_use = messages

        payload = _construct_responses_api_payload(payload_to_use, payload)

        if store is False and payload.get("reasoning") is not None:
            _ensure_reasoning_encrypted_content_include(payload)

        if payload.get("previous_response_id") is None or should_sanitize_replayed_input:
            sanitized_input, has_reasoning, has_encrypted_reasoning = _sanitize_responses_input(payload.get("input", []))
            payload["input"] = sanitized_input
            if has_reasoning and not has_encrypted_reasoning:
                logger.warning("Responses replay is sending reasoning items without encrypted_content; multi-turn reasoning continuity may degrade.")

        return payload

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
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        if not self._use_responses_api(payload):
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            return _normalize_chat_result(result)

        self._ensure_sync_client_available()
        raw_response = None
        generation_info = None
        original_schema_obj = kwargs.get("response_format")
        try:
            if original_schema_obj and _is_pydantic_class(original_schema_obj):
                raw_response = self.root_client.responses.with_raw_response.parse(**payload)
            else:
                raw_response = self.root_client.responses.with_raw_response.create(**payload)
            response = raw_response.parse()
        except Exception as e:
            if raw_response is not None and hasattr(raw_response, "http_response"):
                e.response = raw_response.http_response  # type: ignore[attr-defined]
            raise

        if self.include_response_headers and raw_response is not None and hasattr(raw_response, "headers"):
            generation_info = {"headers": dict(raw_response.headers)}

        result = _construct_lc_result_from_responses_api(
            response,
            schema=original_schema_obj,
            metadata=generation_info,
            output_version=self.output_version,
        )
        result = _apply_response_metadata_flags_to_result(
            result,
            _extract_response_metadata_flags(response),
        )
        return _normalize_chat_result(result)

    async def _agenerate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        if not self._use_responses_api(payload):
            result = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            return _normalize_chat_result(result)

        raw_response = None
        generation_info = None
        original_schema_obj = kwargs.get("response_format")
        try:
            if original_schema_obj and _is_pydantic_class(original_schema_obj):
                raw_response = await self.root_async_client.responses.with_raw_response.parse(**payload)
            else:
                raw_response = await self.root_async_client.responses.with_raw_response.create(**payload)
            response = raw_response.parse()
        except Exception as e:
            if raw_response is not None and hasattr(raw_response, "http_response"):
                e.response = raw_response.http_response  # type: ignore[attr-defined]
            raise

        if self.include_response_headers and raw_response is not None and hasattr(raw_response, "headers"):
            generation_info = {"headers": dict(raw_response.headers)}

        result = _construct_lc_result_from_responses_api(
            response,
            schema=original_schema_obj,
            metadata=generation_info,
            output_version=self.output_version,
        )
        result = _apply_response_metadata_flags_to_result(
            result,
            _extract_response_metadata_flags(response),
        )
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
            emitted_stream_reasoning_content = False
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            for raw_chunk in response:
                chunk_type = _get_value(raw_chunk, "type")
                response_metadata_flags = _extract_response_metadata_flags(_get_value(raw_chunk, "response"))
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
                if response_metadata_flags:
                    generation_chunk = ChatGenerationChunk(
                        message=_apply_response_metadata_flags_to_message(
                            generation_chunk.message,
                            response_metadata_flags,
                        ),
                        generation_info=generation_chunk.generation_info,
                    )

                normalized_chunk = _normalize_generation_chunk(generation_chunk)
                if normalized_chunk is None:
                    continue

                if emitted_stream_reasoning_content and getattr(normalized_chunk.message, "chunk_position", None) == "last":
                    additional_kwargs = dict(normalized_chunk.message.additional_kwargs)
                    additional_kwargs.pop("reasoning_content", None)
                    normalized_chunk = ChatGenerationChunk(
                        message=normalized_chunk.message.model_copy(update={"additional_kwargs": additional_kwargs}),
                        generation_info=normalized_chunk.generation_info,
                    )

                if run_manager:
                    run_manager.on_llm_new_token(normalized_chunk.text, chunk=normalized_chunk)
                is_first_chunk = False
                if "reasoning_content" in normalized_chunk.message.additional_kwargs and getattr(normalized_chunk.message, "chunk_position", None) != "last":
                    emitted_stream_reasoning_content = True
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
            emitted_stream_reasoning_content = False
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            async for raw_chunk in response:
                chunk_type = _get_value(raw_chunk, "type")
                response_metadata_flags = _extract_response_metadata_flags(_get_value(raw_chunk, "response"))
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
                if response_metadata_flags:
                    generation_chunk = ChatGenerationChunk(
                        message=_apply_response_metadata_flags_to_message(
                            generation_chunk.message,
                            response_metadata_flags,
                        ),
                        generation_info=generation_chunk.generation_info,
                    )

                normalized_chunk = _normalize_generation_chunk(generation_chunk)
                if normalized_chunk is None:
                    continue

                if emitted_stream_reasoning_content and getattr(normalized_chunk.message, "chunk_position", None) == "last":
                    additional_kwargs = dict(normalized_chunk.message.additional_kwargs)
                    additional_kwargs.pop("reasoning_content", None)
                    normalized_chunk = ChatGenerationChunk(
                        message=normalized_chunk.message.model_copy(update={"additional_kwargs": additional_kwargs}),
                        generation_info=normalized_chunk.generation_info,
                    )

                if run_manager:
                    await run_manager.on_llm_new_token(normalized_chunk.text, chunk=normalized_chunk)
                is_first_chunk = False
                if "reasoning_content" in normalized_chunk.message.additional_kwargs and getattr(normalized_chunk.message, "chunk_position", None) != "last":
                    emitted_stream_reasoning_content = True
                if "reasoning_content" in normalized_chunk.message.additional_kwargs or "reasoning" in normalized_chunk.message.additional_kwargs:
                    has_reasoning = True
                yield normalized_chunk
