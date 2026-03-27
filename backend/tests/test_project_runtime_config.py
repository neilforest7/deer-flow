from textwrap import dedent

from deerflow.config.app_config import AppConfig, reset_app_config


def test_app_config_loads_project_runtime_allowlist(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    example_path = tmp_path / "config.example.yaml"
    config_path.write_text(
        dedent(
            """
            config_version: 3
            sandbox:
              use: deerflow.sandbox.local:LocalSandboxProvider
            models: []
            tools: []
            tool_groups: []
            project_runtime:
              acp_allowed_specialists:
                - backend-agent
              default_model_name: qa-model
              enable_phase_specialists: true
              allow_deterministic_phase_fallback: false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    example_path.write_text("config_version: 3\n", encoding="utf-8")
    monkeypatch.setenv("DEER_FLOW_CONFIG_PATH", str(config_path))

    reset_app_config()
    config = AppConfig.from_file()

    assert config.project_runtime.acp_allowed_specialists == ["backend-agent"]
    assert config.project_runtime.default_model_name == "qa-model"
    assert config.project_runtime.enable_phase_specialists is True
    assert config.project_runtime.allow_deterministic_phase_fallback is False
