"""Configuration for LangGraph store persistence."""

from typing import Literal

from pydantic import BaseModel, Field


class StoreConfig(BaseModel):
    """Configuration for LangGraph BaseStore persistence."""

    type: Literal["postgres"] = Field(
        default="postgres",
        description="Store backend type. DeerFlow project/runtime persistence is designed for PostgreSQL-backed LangGraph stores.",
    )
    connection_string: str = Field(
        description="PostgreSQL DSN for the LangGraph store.",
    )


_store_config: StoreConfig | None = None


def get_store_config() -> StoreConfig | None:
    """Get the current store configuration, or None if not configured."""
    return _store_config


def set_store_config(config: StoreConfig | None) -> None:
    """Set the store configuration."""
    global _store_config
    _store_config = config


def load_store_config_from_dict(config_dict: dict) -> None:
    """Load store configuration from a dictionary."""
    global _store_config
    _store_config = StoreConfig(**config_dict)
