"""Tests for SessionKeepAlive service."""

from unittest.mock import MagicMock, patch

import pytest


class TestSessionKeepAliveExists:
    """Test SessionKeepAlive is importable and has expected interface."""

    def test_session_keepalive_importable(self):
        """SessionKeepAlive should be importable."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        assert SessionKeepAlive is not None

    def test_session_keepalive_accepts_session(self):
        """SessionKeepAlive should accept a session."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session)
        assert ka.session is mock_session

    def test_session_keepalive_accepts_interval(self):
        """SessionKeepAlive should accept custom interval."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, interval_minutes=10)
        assert ka.interval_seconds == 600  # 10 * 60

    def test_session_keepalive_default_interval(self):
        """SessionKeepAlive should have 5 minute default interval."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session)
        assert ka.interval_seconds == 300  # 5 * 60


class TestSessionKeepAliveLifecycle:
    """Test SessionKeepAlive start/stop lifecycle."""

    def test_start_creates_thread(self):
        """start() should create and start a background thread."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, interval_minutes=0.001)  # Very short for test

        assert not ka.is_running
        ka.start()
        assert ka.is_running
        ka.stop()
        assert not ka.is_running

    def test_stop_is_idempotent(self):
        """stop() should be safe to call multiple times."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session)

        # Stop without start - should not error
        ka.stop()
        ka.stop()

    def test_start_is_idempotent(self):
        """start() should be safe to call multiple times."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, interval_minutes=1)

        ka.start()
        ka.start()  # Should not error or create second thread
        assert ka.is_running
        ka.stop()


class TestSessionKeepAliveContextManager:
    """Test SessionKeepAlive as context manager."""

    def test_context_manager_starts_and_stops(self):
        """Context manager should start on enter and stop on exit."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()

        with SessionKeepAlive(mock_session, interval_minutes=1) as ka:
            assert ka.is_running

        assert not ka.is_running

    def test_context_manager_stops_on_exception(self):
        """Context manager should stop even on exception."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, interval_minutes=1)

        with pytest.raises(ValueError):
            with ka:
                assert ka.is_running
                raise ValueError("test error")

        assert not ka.is_running


class TestSessionKeepAlivePing:
    """Test SessionKeepAlive ping behavior."""

    def test_ping_calls_validate_session(self):
        """_ping() should call AuthManager.validate_session."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session)

        with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
            mock_validate.return_value = True
            result = ka._ping()

            mock_validate.assert_called_once_with(mock_session, verify_ssl=True)
            assert result is True

    def test_ping_updates_count(self):
        """_ping() should increment ping count."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session)

        with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
            mock_validate.return_value = True

            assert ka.ping_count == 0
            ka._ping()
            assert ka.ping_count == 1
            ka._ping()
            assert ka.ping_count == 2

    def test_ping_tracks_health(self):
        """_ping() should update is_healthy based on result."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session)

        with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
            # Healthy ping
            mock_validate.return_value = True
            ka._ping()
            assert ka.is_healthy is True

            # Unhealthy ping
            mock_validate.return_value = False
            ka._ping()
            assert ka.is_healthy is False

    def test_ping_calls_callback_on_expiry(self):
        """_ping() should call on_session_expired when session expires."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        mock_callback = MagicMock()
        ka = SessionKeepAlive(mock_session, on_session_expired=mock_callback)

        with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
            mock_validate.return_value = False
            ka._ping()

            mock_callback.assert_called_once()


class TestRunCatalogBrowserKeepAlive:
    """Test that run_catalog_browser supports session keep-alive."""

    def test_run_catalog_browser_accepts_session_param(self):
        """run_catalog_browser should accept session parameter."""
        import inspect

        from cis_bench.cli.commands.tui.catalog import run_catalog_browser

        sig = inspect.signature(run_catalog_browser)
        params = list(sig.parameters.keys())
        assert "session" in params

    def test_run_catalog_browser_accepts_keep_alive_interval(self):
        """run_catalog_browser should accept keep_alive_interval parameter."""
        import inspect

        from cis_bench.cli.commands.tui.catalog import run_catalog_browser

        sig = inspect.signature(run_catalog_browser)
        params = list(sig.parameters.keys())
        assert "keep_alive_interval" in params


class TestRunInteractiveViewKeepAlive:
    """Test that run_interactive_view supports session keep-alive."""

    def test_run_interactive_view_accepts_session_param(self):
        """run_interactive_view should accept session parameter."""
        import inspect

        from cis_bench.cli.commands.tui.view import run_interactive_view

        sig = inspect.signature(run_interactive_view)
        params = list(sig.parameters.keys())
        assert "session" in params


class TestRunInteractiveDiffKeepAlive:
    """Test that run_interactive_diff supports session keep-alive."""

    def test_run_interactive_diff_accepts_session_param(self):
        """run_interactive_diff should accept session parameter."""
        import inspect

        from cis_bench.cli.commands.tui.diff import run_interactive_diff

        sig = inspect.signature(run_interactive_diff)
        params = list(sig.parameters.keys())
        assert "session" in params
