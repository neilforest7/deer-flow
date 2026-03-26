"""Regression tests for checkpointer configuration fail-fast behavior."""

from unittest.mock import MagicMock, patch

import pytest


class TestCheckpointerConfiguration:
    @pytest.mark.anyio
    async def test_async_make_checkpointer_raises_when_not_configured(self):
        from deerflow.agents.checkpointer.async_provider import make_checkpointer

        mock_config = MagicMock()
        mock_config.checkpointer = None

        with patch(
            "deerflow.agents.checkpointer.async_provider.get_app_config",
            return_value=mock_config,
        ):
            with pytest.raises(ValueError, match="checkpointer configuration is required"):
                async with make_checkpointer():
                    pass

    def test_sync_checkpointer_context_raises_when_not_configured(self):
        from deerflow.agents.checkpointer.provider import checkpointer_context

        mock_config = MagicMock()
        mock_config.checkpointer = None

        with patch(
            "deerflow.agents.checkpointer.provider.get_app_config",
            return_value=mock_config,
        ):
            with pytest.raises(ValueError, match="checkpointer configuration is required"):
                with checkpointer_context():
                    pass
