"""Async PostgreSQL checkpointer factory."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator

from langgraph.types import Checkpointer

from deerflow.agents.checkpointer.provider import (
    POSTGRES_CONN_REQUIRED,
    POSTGRES_INSTALL,
)
from deerflow.config.app_config import get_app_config

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def _async_checkpointer(config) -> AsyncIterator[Checkpointer]:
    """Async context manager that constructs and tears down a PostgreSQL checkpointer."""
    if config.type != "postgres":
        raise ValueError(
            f"Unsupported checkpointer backend: {config.type!r}. DeerFlow requires postgres."
        )

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:
        raise ImportError(POSTGRES_INSTALL) from exc

    if not config.connection_string:
        raise ValueError(POSTGRES_CONN_REQUIRED)

    async with AsyncPostgresSaver.from_conn_string(config.connection_string) as saver:
        await saver.setup()
        logger.info("Checkpointer: using AsyncPostgresSaver")
        yield saver


@contextlib.asynccontextmanager
async def make_checkpointer() -> AsyncIterator[Checkpointer]:
    """Yield an async PostgreSQL checkpointer for the caller's lifetime."""
    config = get_app_config().checkpointer
    if config is None:
        raise ValueError(POSTGRES_CONN_REQUIRED)

    async with _async_checkpointer(config) as saver:
        yield saver
