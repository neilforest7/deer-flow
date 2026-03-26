"""Configuration for LangGraph checkpointer persistence."""

from typing import Literal

from pydantic import BaseModel, Field

CheckpointerType = Literal["postgres"]


class CheckpointerConfig(BaseModel):
    """Configuration for LangGraph checkpoint persistence."""

    type: CheckpointerType = Field(
        default="postgres",
        description="Checkpoint backend type. DeerFlow requires PostgreSQL-backed LangGraph checkpoints.",
    )
    connection_string: str = Field(
        description="PostgreSQL DSN for LangGraph checkpoints.",
    )


_checkpointer_config: CheckpointerConfig | None = None


def get_checkpointer_config() -> CheckpointerConfig | None:
    """Get the current checkpointer configuration, or None if not configured."""
    return _checkpointer_config


def set_checkpointer_config(config: CheckpointerConfig | None) -> None:
    """Set the checkpointer configuration."""
    global _checkpointer_config
    _checkpointer_config = config


def load_checkpointer_config_from_dict(config_dict: dict) -> None:
    """Load checkpointer configuration from a dictionary."""
    global _checkpointer_config
    _checkpointer_config = CheckpointerConfig(**config_dict)
