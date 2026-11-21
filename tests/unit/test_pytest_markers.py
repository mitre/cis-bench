"""Each declared test category marker selects exactly the tests it names.

`pytest tests -m unit` (and integration, e2e, regression) runs the tests in that folder
under tests/, `pytest tests/scripts -m scripts` the script tests, and `pytest tests -m
architecture` the architecture compliance modules, so the commands in CLAUDE.md run what
they say.
"""

import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[1]
ROOT = TESTS.parent


def _collected(*args: str) -> set[str]:
    """Node ids pytest collects with these arguments (run from the repository root).

    -qq prints one node id per line even with --verbose in the configured addopts.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-qq", "-p", "no:cacheprovider", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 5), result.stdout + result.stderr
    return {line for line in result.stdout.splitlines() if "::" in line}


@pytest.mark.parametrize("category", ["unit", "integration", "e2e", "regression"])
def test_a_category_marker_selects_exactly_its_folder(category):
    folder = _collected(f"tests/{category}")
    assert folder, f"tests/{category} has no tests"

    assert _collected("tests", "-m", category) == folder


def test_the_scripts_marker_selects_the_script_tests():
    # tests/scripts is left out of `pytest tests` (norecursedirs) and run on its own.
    folder = _collected("tests/scripts")
    assert folder

    assert _collected("tests/scripts", "-m", "scripts") == folder


def test_the_architecture_marker_selects_the_compliance_modules():
    compliance = _collected(
        "tests/unit/test_architecture_compliance.py",
        "tests/regression/test_architecture_compliance.py",
    )
    assert compliance

    assert _collected("tests", "-m", "architecture") == compliance
