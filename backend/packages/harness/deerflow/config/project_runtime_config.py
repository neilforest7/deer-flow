from pydantic import BaseModel, Field


class ProjectRuntimeConfig(BaseModel):
    """Configuration for the optional project team runtime."""

    acp_allowed_specialists: list[str] = Field(default_factory=list, description="Specialists allowed to use ACP tools")
    default_model_name: str | None = Field(default=None, description="Optional default model override for project runtime")
