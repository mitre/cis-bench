"""Shared pytest fixtures for all tests.

Professional pytest configuration following best practices:
- Path fixtures for all directories/files
- Data fixtures for common test objects
- Mock fixtures for external dependencies
- Helper functions for common test operations

NO HARDCODED PATHS in tests - everything via fixtures.
"""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from cis_bench.models.benchmark import Benchmark, Recommendation

# ============================================================================
# Test Environment Setup
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """Set test environment for all tests.

    This ensures tests use test databases/paths, not production.
    Sets CIS_BENCH_ENV=test for all test runs.
    """
    os.environ["CIS_BENCH_ENV"] = "test"
    yield
    # Cleanup
    os.environ.pop("CIS_BENCH_ENV", None)


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
def disa_config_path(configs_dir):
    """Path to DISA style configuration YAML."""
    return configs_dir / "disa_style.yaml"


@pytest.fixture(scope="session")
def cis_native_config_path(configs_dir):
    """Path to CIS native style configuration YAML."""
    return configs_dir / "cis_native_style.yaml"


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
def almalinux_complete_file(benchmark_fixtures):
    """Path to complete AlmaLinux benchmark JSON (322 recommendations)."""
    return benchmark_fixtures / "almalinux_complete.json"


@pytest.fixture(scope="session")
def almalinux_complete_benchmark(almalinux_complete_file):
    """Load complete AlmaLinux benchmark (cached for session)."""
    return Benchmark.from_json_file(str(almalinux_complete_file))


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
        title="Ensure AIDE is installed",
        url="https://workbench.cisecurity.org/sections/1/recommendations/1",
        assessment_status="Automated",
        description="<p>AIDE is an intrusion detection tool.</p>",
        rationale="<p>Monitoring filesystem state.</p>",
        impact="<p>None expected</p>",
        audit="<p>Run: rpm -q aide</p>",
        remediation="<p>Run: dnf install aide</p>",
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
def isolated_filesystem(cli_runner):
    """Isolated filesystem for CLI file operations."""
    with cli_runner.isolated_filesystem():
        yield Path.cwd()


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


# ============================================================================
# Helper Functions (not fixtures, but shared utilities)
# ============================================================================


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
