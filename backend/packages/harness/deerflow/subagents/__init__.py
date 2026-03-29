from .config import SubagentConfig

__all__ = [
    "SubagentConfig",
    "SubagentExecutor",
    "SubagentResult",
    "get_available_subagent_names",
    "get_subagent_config",
    "list_subagents",
]


def __getattr__(name: str):
    if name in {"SubagentExecutor", "SubagentResult"}:
        from .executor import SubagentExecutor, SubagentResult

        exports = {
            "SubagentExecutor": SubagentExecutor,
            "SubagentResult": SubagentResult,
        }
        return exports[name]
    if name in {
        "get_available_subagent_names",
        "get_subagent_config",
        "list_subagents",
    }:
        from .registry import (
            get_available_subagent_names,
            get_subagent_config,
            list_subagents,
        )

        exports = {
            "get_available_subagent_names": get_available_subagent_names,
            "get_subagent_config": get_subagent_config,
            "list_subagents": list_subagents,
        }
        return exports[name]
    raise AttributeError(name)
