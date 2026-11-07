"""Tests for SessionKeepAlive: pings WorkBench through the run's AuthManager during a long TUI
session; only a rejection counts as an expired session, a failure to ask does not."""

from unittest.mock import MagicMock

import pytest

from cis_bench.exceptions import FetchError, TLSVerificationError


@pytest.fixture
def auth():
    """An AuthManager stand-in whose validate_session the tests set."""
    manager = MagicMock()
    manager.validate_session.return_value = True
    return manager


class TestSessionKeepAliveExists:
    """Test SessionKeepAlive is importable and has expected interface."""

    def test_session_keepalive_importable(self):
        """SessionKeepAlive should be importable."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        assert SessionKeepAlive is not None

    def test_session_keepalive_accepts_session(self, auth):
        """SessionKeepAlive should accept a session."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth)
        assert ka.session is mock_session

    def test_session_keepalive_accepts_interval(self, auth):
        """SessionKeepAlive should accept custom interval."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth, interval_minutes=10)
        assert ka.interval_seconds == 600  # 10 * 60

    def test_session_keepalive_default_interval(self, auth):
        """SessionKeepAlive should have 5 minute default interval."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth)
        assert ka.interval_seconds == 300  # 5 * 60


class TestSessionKeepAliveLifecycle:
    """Test SessionKeepAlive start/stop lifecycle."""

    def test_start_creates_thread(self, auth):
        """start() should create and start a background thread."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth, interval_minutes=0.001)  # Very short for test

        assert not ka.is_running
        ka.start()
        assert ka.is_running
        ka.stop()
        assert not ka.is_running

    def test_stop_is_idempotent(self, auth):
        """stop() should be safe to call multiple times."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth)

        # Stop without start - should not error
        ka.stop()
        ka.stop()

    def test_start_is_idempotent(self, auth):
        """start() should be safe to call multiple times."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth, interval_minutes=1)

        ka.start()
        ka.start()  # Should not error or create second thread
        assert ka.is_running
        ka.stop()


class TestSessionKeepAliveContextManager:
    """Test SessionKeepAlive as context manager."""

    def test_context_manager_starts_and_stops(self, auth):
        """Context manager should start on enter and stop on exit."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()

        with SessionKeepAlive(mock_session, auth, interval_minutes=1) as ka:
            assert ka.is_running

        assert not ka.is_running

    def test_context_manager_stops_on_exception(self, auth):
        """Context manager should stop even on exception."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth, interval_minutes=1)

        with pytest.raises(ValueError):
            with ka:
                assert ka.is_running
                raise ValueError("test error")

        assert not ka.is_running


class TestSessionKeepAlivePing:
    """A ping asks WorkBench through the run's AuthManager."""

    def test_ping_validates_the_session_through_the_given_manager(self, auth):
        from cis_bench.fetcher.auth import SessionKeepAlive

        mock_session = MagicMock()
        ka = SessionKeepAlive(mock_session, auth)

        assert ka._ping() is True
        auth.validate_session.assert_called_once_with(mock_session)

    def test_ping_updates_count(self, auth):
        from cis_bench.fetcher.auth import SessionKeepAlive

        ka = SessionKeepAlive(MagicMock(), auth)

        assert ka.ping_count == 0
        ka._ping()
        assert ka.ping_count == 1
        ka._ping()
        assert ka.ping_count == 2

    def test_a_rejected_session_is_unhealthy_and_reported_once(self, auth):
        from cis_bench.fetcher.auth import SessionKeepAlive

        expired = MagicMock()
        ka = SessionKeepAlive(MagicMock(), auth, on_session_expired=expired)

        ka._ping()
        assert ka.is_healthy is True
        auth.validate_session.return_value = False
        assert ka._ping() is False

        assert ka.is_healthy is False
        expired.assert_called_once_with()

    @pytest.mark.parametrize(
        "failure",
        [
            FetchError("https://workbench.cisecurity.org/benchmarks", 3, "timed out"),
            TLSVerificationError("certificate verify failed"),
        ],
        ids=["network", "tls"],
    )
    def test_a_failure_to_ask_is_not_an_expired_session(self, auth, failure):
        """Nothing is known about the session when WorkBench could not be asked."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        expired = MagicMock()
        ka = SessionKeepAlive(MagicMock(), auth, on_session_expired=expired)
        auth.validate_session.side_effect = failure

        assert ka._ping() is None

        assert ka.is_healthy is True
        expired.assert_not_called()
        assert ka.ping_count == 1

    def test_an_unexpected_error_is_not_swallowed(self, auth):
        """A bug in the ping surfaces instead of being reported as an expired session."""
        from cis_bench.fetcher.auth import SessionKeepAlive

        expired = MagicMock()
        ka = SessionKeepAlive(MagicMock(), auth, on_session_expired=expired)
        auth.validate_session.side_effect = KeyError("bug")

        with pytest.raises(KeyError):
            ka._ping()
        expired.assert_not_called()


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
        assert "auth" in params


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


class TestRunApp:
    """The TUI keeps the session alive only online, with both a session and the run's
    AuthManager; otherwise the app simply runs."""

    def test_online_with_a_session_and_auth_the_app_runs_inside_the_keep_alive(self, auth):
        from unittest.mock import patch

        from cis_bench.cli.commands.tui.base import run_app

        app, session = MagicMock(), MagicMock()
        with patch("cis_bench.fetcher.auth.SessionKeepAlive") as keep_alive:
            run_app(app, offline=False, session=session, auth=auth, keep_alive_interval=2.5)

        keep_alive.assert_called_once_with(session, auth, interval_minutes=2.5)
        keep_alive.return_value.__enter__.assert_called_once()
        app.run.assert_called_once_with()

    @pytest.mark.parametrize(
        ("offline", "has_session", "has_auth"),
        [(True, True, True), (False, False, True), (False, True, False)],
        ids=["offline", "no-session", "no-auth"],
    )
    def test_otherwise_the_app_runs_without_it(self, auth, offline, has_session, has_auth):
        from unittest.mock import patch

        from cis_bench.cli.commands.tui.base import run_app

        app = MagicMock()
        with patch("cis_bench.fetcher.auth.SessionKeepAlive") as keep_alive:
            run_app(
                app,
                offline=offline,
                session=MagicMock() if has_session else None,
                auth=auth if has_auth else None,
                keep_alive_interval=5.0,
            )

        keep_alive.assert_not_called()
        app.run.assert_called_once_with()
