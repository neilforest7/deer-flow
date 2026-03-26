"""Sync PostgreSQL checkpointer factory."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator

from langgraph.types import Checkpointer

from deerflow.config.app_config import get_app_config
from deerflow.config.checkpointer_config import CheckpointerConfig, get_checkpointer_config

logger = logging.getLogger(__name__)

POSTGRES_INSTALL = (
    "langgraph-checkpoint-postgres is required for the PostgreSQL checkpointer. "
    "Install it with: uv add langgraph-checkpoint-postgres psycopg[binary] psycopg-pool"
)
POSTGRES_CONN_REQUIRED = (
    "checkpointer configuration is required. Configure checkpointer.type=postgres "
    "and checkpointer.connection_string in config.yaml."
)


@contextlib.contextmanager
def _sync_checkpointer_cm(config: CheckpointerConfig) -> Iterator[Checkpointer]:
    """Context manager that creates and tears down a sync PostgreSQL checkpointer."""
    if config.type != "postgres":
        raise ValueError(
            f"Unsupported checkpointer backend: {config.type!r}. DeerFlow requires postgres."
        )

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as exc:
        raise ImportError(POSTGRES_INSTALL) from exc

    if not config.connection_string:
        raise ValueError(POSTGRES_CONN_REQUIRED)

    with PostgresSaver.from_conn_string(config.connection_string) as saver:
        saver.setup()
        logger.info("Checkpointer: using PostgresSaver")
        yield saver


_checkpointer: Checkpointer | None = None
_checkpointer_ctx = None


def get_checkpointer() -> Checkpointer:
    """Return the global sync checkpointer singleton, creating it on first call."""
    global _checkpointer, _checkpointer_ctx

    if _checkpointer is not None:
        return _checkpointer

    config = get_checkpointer_config()
    if config is None:
        app_config = get_app_config()
        config = app_config.checkpointer
    if config is None:
        raise ValueError(POSTGRES_CONN_REQUIRED)

    _checkpointer_ctx = _sync_checkpointer_cm(config)
    _checkpointer = _checkpointer_ctx.__enter__()
    return _checkpointer


def reset_checkpointer() -> None:
    """Reset the sync singleton, forcing recreation on the next call."""
    global _checkpointer, _checkpointer_ctx
    if _checkpointer_ctx is not None:
        try:
            _checkpointer_ctx.__exit__(None, None, None)
        except Exception:
            logger.warning("Error during checkpointer cleanup", exc_info=True)
        _checkpointer_ctx = None
    _checkpointer = None


@contextlib.contextmanager
def checkpointer_context() -> Iterator[Checkpointer]:
    """Yield a fresh PostgreSQL checkpointer and clean it up on exit."""
    config = get_app_config().checkpointer
    if config is None:
        raise ValueError(POSTGRES_CONN_REQUIRED)
    with _sync_checkpointer_cm(config) as saver:
        yield saver
