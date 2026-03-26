"""Unit tests for Postgres-only checkpointer config and factory."""

import sys
from unittest.mock import MagicMock, patch

import pytest

import deerflow.config.app_config as app_config_module
from deerflow.agents.checkpointer import get_checkpointer, reset_checkpointer
from deerflow.config.checkpointer_config import (
    CheckpointerConfig,
    get_checkpointer_config,
    load_checkpointer_config_from_dict,
    set_checkpointer_config,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset singleton state before each test."""
    app_config_module._app_config = None
    set_checkpointer_config(None)
    reset_checkpointer()
    yield
    app_config_module._app_config = None
    set_checkpointer_config(None)
    reset_checkpointer()


class TestCheckpointerConfig:
    def test_load_postgres_config(self):
        load_checkpointer_config_from_dict(
            {"type": "postgres", "connection_string": "postgresql://localhost/db"}
        )
        config = get_checkpointer_config()
        assert config is not None
        assert config.type == "postgres"
        assert config.connection_string == "postgresql://localhost/db"

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            load_checkpointer_config_from_dict({"type": "sqlite", "connection_string": "/tmp/test.db"})

    def test_connection_string_is_required(self):
        with pytest.raises(Exception):
            CheckpointerConfig(type="postgres")

    def test_set_config_to_none(self):
        load_checkpointer_config_from_dict(
            {"type": "postgres", "connection_string": "postgresql://localhost/db"}
        )
        set_checkpointer_config(None)
        assert get_checkpointer_config() is None


class TestGetCheckpointer:
    def test_raises_when_not_configured(self):
        with patch(
            "deerflow.agents.checkpointer.provider.get_app_config",
            return_value=MagicMock(checkpointer=None),
        ):
            with pytest.raises(ValueError, match="checkpointer configuration is required"):
                get_checkpointer()

    def test_postgres_raises_when_package_missing(self):
        load_checkpointer_config_from_dict(
            {"type": "postgres", "connection_string": "postgresql://localhost/db"}
        )
        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": None}):
            reset_checkpointer()
            with pytest.raises(ImportError, match="langgraph-checkpoint-postgres"):
                get_checkpointer()

    def test_postgres_creates_saver(self):
        load_checkpointer_config_from_dict(
            {"type": "postgres", "connection_string": "postgresql://localhost/db"}
        )

        mock_saver_instance = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_saver_instance)
        mock_cm.__exit__ = MagicMock(return_value=False)

        mock_saver_cls = MagicMock()
        mock_saver_cls.from_conn_string = MagicMock(return_value=mock_cm)

        mock_pg_module = MagicMock()
        mock_pg_module.PostgresSaver = mock_saver_cls

        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": mock_pg_module}):
            reset_checkpointer()
            cp = get_checkpointer()

        assert cp is mock_saver_instance
        mock_saver_cls.from_conn_string.assert_called_once_with("postgresql://localhost/db")
        mock_saver_instance.setup.assert_called_once()

    def test_reset_clears_singleton(self):
        load_checkpointer_config_from_dict(
            {"type": "postgres", "connection_string": "postgresql://localhost/db"}
        )

        mock_saver_instance_1 = MagicMock()
        mock_cm_1 = MagicMock()
        mock_cm_1.__enter__ = MagicMock(return_value=mock_saver_instance_1)
        mock_cm_1.__exit__ = MagicMock(return_value=False)

        mock_saver_instance_2 = MagicMock()
        mock_cm_2 = MagicMock()
        mock_cm_2.__enter__ = MagicMock(return_value=mock_saver_instance_2)
        mock_cm_2.__exit__ = MagicMock(return_value=False)

        mock_saver_cls = MagicMock()
        mock_saver_cls.from_conn_string = MagicMock(side_effect=[mock_cm_1, mock_cm_2])
        mock_pg_module = MagicMock()
        mock_pg_module.PostgresSaver = mock_saver_cls

        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": mock_pg_module}):
            cp1 = get_checkpointer()
            reset_checkpointer()
            cp2 = get_checkpointer()

        assert cp1 is mock_saver_instance_1
        assert cp2 is mock_saver_instance_2


class TestClientCheckpointerFallback:
    def test_client_uses_config_checkpointer_when_none_provided(self):
        """DeerFlowClient._ensure_agent falls back to get_checkpointer() when checkpointer=None."""
        from deerflow.client import DeerFlowClient

        load_checkpointer_config_from_dict(
            {"type": "postgres", "connection_string": "postgresql://localhost/db"}
        )

        captured_kwargs = {}

        def fake_create_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        model_mock = MagicMock()
        config_mock = MagicMock()
        config_mock.models = [model_mock]
        config_mock.get_model_config.return_value = MagicMock(supports_vision=False)
        config_mock.checkpointer = None

        explicit_cp = MagicMock()
        with (
            patch("deerflow.client.get_app_config", return_value=config_mock),
            patch("deerflow.client.create_agent", side_effect=fake_create_agent),
            patch("deerflow.client.create_chat_model", return_value=MagicMock()),
            patch("deerflow.client._build_middlewares", return_value=[]),
            patch("deerflow.client.apply_prompt_template", return_value=""),
            patch("deerflow.client.get_store", return_value=MagicMock()),
            patch("deerflow.client.DeerFlowClient._get_tools", return_value=[]),
            patch("deerflow.agents.checkpointer.get_checkpointer", return_value=explicit_cp),
        ):
            client = DeerFlowClient(checkpointer=None)
            config = client._get_runnable_config("test-thread")
            client._ensure_agent(config)

        assert captured_kwargs["checkpointer"] is explicit_cp

    def test_client_explicit_checkpointer_takes_precedence(self):
        from deerflow.client import DeerFlowClient

        explicit_cp = MagicMock()
        captured_kwargs = {}

        def fake_create_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        model_mock = MagicMock()
        config_mock = MagicMock()
        config_mock.models = [model_mock]
        config_mock.get_model_config.return_value = MagicMock(supports_vision=False)
        config_mock.checkpointer = None

        with (
            patch("deerflow.client.get_app_config", return_value=config_mock),
            patch("deerflow.client.create_agent", side_effect=fake_create_agent),
            patch("deerflow.client.create_chat_model", return_value=MagicMock()),
            patch("deerflow.client._build_middlewares", return_value=[]),
            patch("deerflow.client.apply_prompt_template", return_value=""),
            patch("deerflow.client.get_store", return_value=MagicMock()),
            patch("deerflow.client.DeerFlowClient._get_tools", return_value=[]),
        ):
            client = DeerFlowClient(checkpointer=explicit_cp)
            config = client._get_runnable_config("test-thread")
            client._ensure_agent(config)

        assert captured_kwargs["checkpointer"] is explicit_cp
