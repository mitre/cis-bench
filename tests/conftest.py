"""Shared pytest fixtures for all tests.

Professional pytest configuration following best practices:
- Path fixtures for all directories/files
- Data fixtures for common test objects
- Mock fixtures for external dependencies
- Helper functions for common test operations

NO HARDCODED PATHS in tests - everything via fixtures.

Test organization:
- tests/scripts/ - Project utility tests (optional, requires libcst)
  Run with: uv run pytest tests/scripts/
- All other tests - cis-bench package tests (default)
  Run with: uv run pytest
"""

import json
import os
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.client import HTTPMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from click.testing import CliRunner
from requests.adapters import BaseAdapter

from cis_bench.models.benchmark import Benchmark, Recommendation

# ============================================================================
# Test Environment Setup
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def test_environment(tmp_path_factory):
    """Point every test at its own folder, never the developer's XDG folders or ~/.cis-bench.

    CIS_BENCH_HOME places config.toml, catalog.db, benchmarks/ and session.cookies in one
    folder. A retired CIS_BENCH_ENV or CIS_BENCH_DATA_DIR left in the developer's shell is
    removed: the settings refuse them.
    """
    previous = {
        name: os.environ.pop(name, None)
        for name in ("CIS_BENCH_ENV", "CIS_BENCH_DATA_DIR", "CIS_BENCH_HOME")
    }
    os.environ["CIS_BENCH_HOME"] = str(tmp_path_factory.mktemp("cis-bench-data"))
    yield
    os.environ.pop("CIS_BENCH_HOME", None)
    for name, value in previous.items():
        if value is not None:
            os.environ[name] = value


# ============================================================================
# Path Fixtures - Single Source of Truth for ALL Paths
# ============================================================================


@pytest.fixture(scope="session")
def project_root():
    """Return project root directory.

    All other paths derive from this fixture.
    """
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def src_dir(project_root):
    """Return src/ directory (package source)."""
    return project_root / "src"


@pytest.fixture(scope="session")
def package_dir(src_dir):
    """Return cis_bench package directory."""
    return src_dir / "cis_bench"


@pytest.fixture(scope="session")
def exporters_dir(package_dir):
    """Return exporters directory."""
    return package_dir / "exporters"


@pytest.fixture(scope="session")
def configs_dir(exporters_dir):
    """Return exporters config directory."""
    return exporters_dir / "configs"


@pytest.fixture(scope="session")
def styles_dir(configs_dir):
    """Return styles directory within configs."""
    return configs_dir / "styles"


@pytest.fixture(scope="session")
def utils_dir(package_dir):
    """Return utils directory."""
    return package_dir / "utils"


@pytest.fixture(scope="session")
def fixtures_dir(project_root):
    """Return test fixtures directory."""
    return project_root / "tests" / "fixtures"


@pytest.fixture(scope="session")
def benchmark_fixtures(fixtures_dir):
    """Return benchmark fixtures directory."""
    return fixtures_dir / "benchmarks"


@pytest.fixture(scope="session")
def xccdf_fixtures(fixtures_dir):
    """Return XCCDF fixtures directory."""
    return fixtures_dir / "xccdf"


@pytest.fixture(scope="session")
def html_fixtures(fixtures_dir):
    """Return HTML fixtures directory."""
    return fixtures_dir / "html"


# ============================================================================
# Configuration File Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def disa_config_path(styles_dir):
    """Path to DISA style configuration YAML."""
    return styles_dir / "disa.yaml"


@pytest.fixture(scope="session")
def cis_config_path(styles_dir):
    """Path to CIS style configuration YAML."""
    return styles_dir / "cis.yaml"


@pytest.fixture(scope="session")
def disa_vulcan_compat_config_path(styles_dir):
    """Path to DISA Vulcan-compatible style configuration YAML."""
    return styles_dir / "disa_vulcan_compat.yaml"


# ============================================================================
# Source File Fixtures (for architecture tests)
# ============================================================================


@pytest.fixture(scope="session")
def mapping_engine_file(exporters_dir):
    """Path to mapping_engine.py source file."""
    return exporters_dir / "mapping_engine.py"


@pytest.fixture(scope="session")
def unified_xccdf_exporter_file(exporters_dir):
    """Path to xccdf_unified_exporter.py source file."""
    return exporters_dir / "xccdf_unified_exporter.py"


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def synthetic_complete_file(benchmark_fixtures):
    """Path to complete synthetic benchmark JSON (20 recommendations)."""
    return benchmark_fixtures / "synthetic_complete.json"


@pytest.fixture(scope="session")
def synthetic_complete_benchmark(synthetic_complete_file):
    """Load complete synthetic benchmark (cached for session)."""
    return Benchmark.from_json_file(str(synthetic_complete_file))


@pytest.fixture(scope="session")
def valid_disa_xccdf_file(xccdf_fixtures):
    """Path to valid DISA XCCDF export (our known-good output)."""
    return xccdf_fixtures / "generated" / "disa" / "valid_disa_full.xml"


@pytest.fixture
def sample_recommendation_minimal():
    """Minimal valid recommendation for unit testing."""
    return Recommendation(
        ref="1.1.1",
        title="Test Recommendation",
        url="https://workbench.cisecurity.org/sections/1/recommendations/1",
        assessment_status="Automated",
    )


@pytest.fixture
def sample_recommendation_complete():
    """Complete recommendation with all fields for integration testing."""
    return Recommendation(
        ref="6.1.1",
        title="Ensure filesystem integrity verification agent is active",
        url="https://workbench.cisecurity.org/sections/1/recommendations/1",
        assessment_status="Automated",
        description="<p>Periodic cryptographic checksum verification detects unauthorized file changes.</p>",
        rationale="<p>Continuous integrity checks surface tampering across critical system paths.</p>",
        impact="<p>Scheduled verification scans increase transient disk I/O.</p>",
        audit="<p>Run: <code>integrity-agent --status</code></p>",
        remediation="<p>Run: <code>service-ctl enable --now integrity-agent</code></p>",
        profiles=["Level 1 - Server", "Level 1 - Workstation"],
        cis_controls=[
            {
                "version": 8,
                "control": "8.5",
                "title": "Collect Detailed Audit Logs",
                "ig1": False,
                "ig2": True,
                "ig3": True,
            }
        ],
        nist_controls=["AU-2", "AU-12", "SI-4"],
    )


# ============================================================================
# CLI Testing Fixtures
# ============================================================================


@pytest.fixture
def cli_runner():
    """Click CLI test runner for command testing."""
    return CliRunner()


@pytest.fixture
def working_dir(tmp_path_factory, monkeypatch):
    """An empty current directory, for a command that reads or writes relative paths.

    It is a directory of its own, apart from tmp_path, so what a command wrote to the
    current directory is never mixed with the folders a test set up.
    """
    path = tmp_path_factory.mktemp("cwd")
    monkeypatch.chdir(path)
    return path


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_session(mocker):
    """Mock requests.Session for HTTP testing."""
    return mocker.Mock()


@pytest.fixture
def mock_browser_cookies(mocker):
    """Mock browser_cookie3 for authentication testing."""
    mock_chrome = mocker.patch("browser_cookie3.chrome")
    mock_firefox = mocker.patch("browser_cookie3.firefox")
    mock_edge = mocker.patch("browser_cookie3.edge")
    mock_safari = mocker.patch("browser_cookie3.safari")

    return {
        "chrome": mock_chrome,
        "firefox": mock_firefox,
        "edge": mock_edge,
        "safari": mock_safari,
    }


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """This test's own data folder (CIS_BENCH_HOME): catalog.db and session.cookies live here."""
    monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def auth_manager_class():
    """AuthManager replaced by a mock class, for CLI tests that must not touch browsers or WorkBench.

    The CLI builds its AuthManager from the run's settings. The instance this mock class builds
    keeps the values it was built with (workbench_url, verify_ssl, session_file,
    request_policy, timeout, workbench_host), so a command prints and checks real ones; every
    method is a mock the test configures on ``auth_manager_class.return_value``. The constructor
    arguments are on ``auth_manager_class.call_args``.
    """
    from unittest.mock import MagicMock, patch
    from urllib.parse import urlparse

    from cis_bench.fetcher.auth import AuthManager

    instance = MagicMock(spec=AuthManager)

    def build(*, workbench_url, verify_ssl, session_file, request_policy, timeout):
        instance.workbench_url = workbench_url
        instance.verify_ssl = verify_ssl
        instance.session_file = session_file
        instance.request_policy = request_policy
        instance.timeout = timeout
        instance.workbench_host = urlparse(workbench_url).netloc
        return instance

    with patch("cis_bench.fetcher.auth.AuthManager") as cls:
        cls.return_value = instance
        cls.side_effect = build
        yield cls


# ============================================================================
# Helper Functions (not fixtures, but shared utilities)
# ============================================================================


def unusable_command_hints(output: str) -> list[str]:
    """The `cis-bench ...` command lines in CLI output that Click would refuse.

    Each hint is parsed the way Click parses a real command line (options, their values and
    choices, required and surplus arguments, at the root and at every subcommand), without
    running any command. A placeholder such as <ID> stands for a value, a trailing
    `# comment` or shell pipe is ignored, and a file a hint names need not exist.
    Call it outside any patch(): resolving a command imports its module, and a module first
    imported while a name is patched keeps the mock.
    """
    import contextlib
    import io
    import re
    import shlex

    import click

    from cis_bench.cli.app import cli

    root = click.Context(cli, info_name="cis-bench")
    names = "|".join(re.escape(name) for name in cli.list_commands(root))
    problems = []
    for match in re.finditer(rf"cis-bench ((?:-\S+ )*(?:{names})\b[^\n'`]*)", output):
        text = re.split(r"\s(?:\||&&|>)\s", match.group(1).split("#")[0])[
            0
        ]  # up to a shell operator
        text = re.sub(r"<[^>]+>", "23598", text).strip().rstrip(".,;:")
        try:
            args = shlex.split(text)
        except ValueError as error:
            problems.append(f"{text}: {error}")
            continue
        command: click.Command = cli
        parent = None
        name = "cis-bench"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                while isinstance(command, click.Group):
                    ctx = click.Context(command, info_name=name, parent=parent)
                    _, rest, _ = command.make_parser(ctx).parse_args(list(args))
                    if not rest:
                        break  # a group named alone shows its help
                    name, *args = rest
                    sub = command.get_command(ctx, name)
                    if sub is None:
                        problems.append(f"{text}: no such command {name}")
                        break
                    command, parent = sub, ctx
                else:
                    command.make_context(name, list(args), parent=parent)
        except click.exceptions.Exit:
            pass  # --help or --version: Click answered it
        except click.BadParameter as error:
            if "does not exist" not in error.format_message():
                problems.append(f"{text}: {error.format_message()}")
        except click.UsageError as error:
            problems.append(f"{text}: {error.format_message()}")
    return problems


def get_source_code(file_path: Path) -> str:
    """Read source code file (helper for architecture tests).

    Args:
        file_path: Path to source file

    Returns:
        Source code as string
    """
    return file_path.read_text()


def load_test_benchmark(file_path: Path) -> Benchmark:
    """Load benchmark from file (helper for tests).

    Args:
        file_path: Path to benchmark JSON

    Returns:
        Loaded Benchmark object
    """
    return Benchmark.from_json_file(str(file_path))


# ============================================================================
# HTTP stub transport
# ============================================================================


@pytest.fixture
def small_catalog(tmp_path):
    """A real catalog database file with five Published 'CIS Sample Benchmark' entries."""
    from cis_bench.catalog.database import CatalogDatabase

    path = tmp_path / "catalog.db"
    db = CatalogDatabase(path)
    try:
        db.initialize_schema()
        for n in range(1, 6):
            db.insert_benchmark(
                {
                    "benchmark_id": str(600 + n),
                    "title": f"CIS Sample Benchmark {n}",
                    "version": "v1.0.0",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{600 + n}",
                    "status": "Published",
                }
            )
        db.mark_latest_versions()  # as a catalog refresh does
    finally:
        db.engine.dispose()
    return path


class LocalHTTPServer:
    """A real HTTP server on 127.0.0.1, for tests that need requests' whole transport.

    Unlike stub_session, requests sent here go through the session's mounted adapter, so
    urllib3 retries, the rate limiter, timeouts and cookie handling all run for real.
    ``respond(handler)`` answers each GET on a server thread; use it as a context manager.
    """

    def __init__(self, respond):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                respond(self)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._httpd.server_port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()


@dataclass
class StubReply:
    """What the stub transport answers: a body (text, or a dict sent as JSON), an HTTP status,
    and Set-Cookie header values that the session processes as it would a real response."""

    body: str | dict = ""
    status: int = 200
    set_cookies: tuple[str, ...] = ()


class _StubTransport(BaseAdapter):
    """Transport adapter that answers from handler(url) instead of the network.

    handler returns page text, a dict (sent as JSON), a StubReply, or raises (for example
    requests.Timeout). Mounted on a real Session, it is shared by the per-thread session copies,
    so it sees every request whichever thread sends it. Records each request's url, headers and
    transport settings (timeout, verify), and the peak number of requests in flight at once.
    """

    def __init__(self, handler):
        super().__init__()
        self.handler = handler
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.settings: list[dict[str, object]] = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self._lock = threading.Lock()

    def send(self, request, **kwargs):
        with self._lock:
            self.urls.append(request.url)
            self.headers.append(dict(request.headers))
            self.settings.append({"timeout": kwargs.get("timeout"), "verify": kwargs.get("verify")})
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            reply = self.handler(request.url)
        finally:
            with self._lock:
                self.in_flight -= 1
        if not isinstance(reply, StubReply):
            reply = StubReply(body=reply)
        response = requests.Response()
        response.status_code = reply.status
        response.reason = HTTPStatus(reply.status).phrase
        response.url = request.url
        response.request = request
        if isinstance(reply.body, dict):
            response._content = json.dumps(reply.body).encode()
            response.headers["Content-Type"] = "application/json"
        else:
            response._content = reply.body.encode()
            response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.encoding = "utf-8"
        # requests reads response cookies from the raw HTTP message (cookies.extract_cookies_to_jar).
        message = HTTPMessage()
        for value in reply.set_cookies:
            message["Set-Cookie"] = value
        response.raw = SimpleNamespace(_original_response=SimpleNamespace(msg=message))
        return response

    def close(self):
        pass


@pytest.fixture
def stub_session():
    """Factory: a real requests.Session whose https:// requests are answered by handler(url).

    Returns (session, transport). Scrapers copy the caller's session for each worker thread and
    the copies share its mounted adapters, so the stub sees every request; a Mock session cannot
    be copied that way.
    """

    def make(handler):
        session = requests.Session()
        transport = _StubTransport(handler)
        session.mount("https://", transport)
        return session, transport

    return make


@pytest.fixture
def new_york_clock(monkeypatch):
    """The process's local zone is America/New_York for the test, as a user's terminal would set it."""
    import time

    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()
