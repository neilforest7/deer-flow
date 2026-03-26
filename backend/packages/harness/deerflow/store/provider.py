"""Sync/async store providers for LangGraph BaseStore."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Iterator

from langgraph.store.base import BaseStore

from deerflow.config.app_config import get_app_config

logger = logging.getLogger(__name__)

POSTGRES_STORE_INSTALL = (
    "langgraph-checkpoint-postgres and psycopg[binary,pool] are required for the PostgreSQL store. "
    "Install them with: uv add langgraph-checkpoint-postgres psycopg[binary] psycopg-pool"
)
POSTGRES_CONN_REQUIRED = "store.connection_string is required for the postgres store backend"


@contextlib.contextmanager
def _sync_store_cm(config) -> Iterator[BaseStore]:
    if config.type != "postgres":
        raise ValueError(f"Unsupported store backend: {config.type!r}. DeerFlow project/store persistence requires postgres.")

    try:
        from langgraph.store.postgres import PostgresStore
    except ImportError as exc:
        raise ImportError(POSTGRES_STORE_INSTALL) from exc

    if not config.connection_string:
        raise ValueError(POSTGRES_CONN_REQUIRED)

    with PostgresStore.from_conn_string(config.connection_string) as store:
        store.setup()
        logger.info("Store: using PostgresStore")
        yield store


@contextlib.asynccontextmanager
async def _async_store_cm(config) -> AsyncIterator[BaseStore]:
    if config.type != "postgres":
        raise ValueError(f"Unsupported store backend: {config.type!r}. DeerFlow project/store persistence requires postgres.")

    try:
        from langgraph.store.postgres.aio import AsyncPostgresStore
    except ImportError as exc:
        raise ImportError(POSTGRES_STORE_INSTALL) from exc

    if not config.connection_string:
        raise ValueError(POSTGRES_CONN_REQUIRED)

    async with AsyncPostgresStore.from_conn_string(config.connection_string) as store:
        await store.setup()
        logger.info("Store: using AsyncPostgresStore")
        yield store


_store: BaseStore | None = None
_store_ctx = None


def get_store() -> BaseStore:
    """Return the global sync store singleton, creating it on first call."""
    global _store, _store_ctx

    if _store is not None:
        return _store

    config = get_app_config().store
    if config is None:
        raise ValueError("store configuration is required. Configure store.type=postgres and store.connection_string in config.yaml.")

    _store_ctx = _sync_store_cm(config)
    _store = _store_ctx.__enter__()
    return _store


def reset_store() -> None:
    """Reset the sync store singleton."""
    global _store, _store_ctx
    if _store_ctx is not None:
        try:
            _store_ctx.__exit__(None, None, None)
        except Exception:
            logger.warning("Error during store cleanup", exc_info=True)
        _store_ctx = None
    _store = None


@contextlib.contextmanager
def check_store_context() -> Iterator[BaseStore]:
    """Yield a fresh sync store and clean it up on exit."""
    config = get_app_config().store
    if config is None:
        raise ValueError("store configuration is required. Configure store.type=postgres and store.connection_string in config.yaml.")
    with _sync_store_cm(config) as store:
        yield store


@contextlib.asynccontextmanager
async def make_store() -> AsyncIterator[BaseStore]:
    """Yield a fresh async store and clean it up on exit."""
    config = get_app_config().store
    if config is None:
        raise ValueError("store configuration is required. Configure store.type=postgres and store.connection_string in config.yaml.")
    async with _async_store_cm(config) as store:
        yield store
