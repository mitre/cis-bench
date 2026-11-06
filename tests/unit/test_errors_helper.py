"""Unit tests for the user-facing error reports shared by the CLI commands."""

from io import StringIO

from rich.console import Console

from cis_bench.cli.helpers.errors import report_configuration_error, report_expired_session
from cis_bench.exceptions import AuthenticationError, ConfigurationError


def _console():
    buffer = StringIO()
    return Console(file=buffer, width=200), buffer


def test_configuration_error_prints_the_heading_and_the_message_verbatim():
    console, buffer = _console()

    report_configuration_error(
        console, ConfigurationError("CIS_BENCH_REQUEST_TIMEOUT has invalid value '[/x]'")
    )

    output = buffer.getvalue()
    assert "Configuration Error" in output
    assert "CIS_BENCH_REQUEST_TIMEOUT has invalid value '[/x]'" in output


def test_expired_session_names_the_login_command_and_shows_the_error_verbatim():
    console, buffer = _console()

    report_expired_session(console, AuthenticationError("the saved session has expired [/x]"))

    output = buffer.getvalue()
    assert "Authentication Failed" in output
    assert "the saved session has expired [/x]" in output
    assert "cis-bench auth login --browser chrome" in output
