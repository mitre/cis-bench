# CHANGELOG


## v0.0.3 (2025-12-15)

### Bug Fixes

- Upgrade to Python 3.12+ and fix CI issues
  ([`e7777f1`](https://github.com/mitre/cis-bench/commit/e7777f14ce2400dd861f3109dffce7b9e34066f4))

- Require Python >=3.12 (modern standard) - Update CI matrix to test 3.12 and 3.13 - Fix black regex
  pattern for extend-exclude - Configure bandit to read pyproject.toml config - Keep truststore for
  system certificate support - Update all tool target versions to py312/py313

Authored by: Aaron Lippold <lippold@gmail.com>

- Upgrade to Python 3.12+ and resolve all CI issues
  ([`dda54b7`](https://github.com/mitre/cis-bench/commit/dda54b776dac01cc5abfac8f220e045bfdf26fe8))

- Require Python >=3.12 (modern standard, 2025) - Update CI matrix to test Python 3.12 and 3.13 -
  Fix security issues in auth.py: - Add URL validation for CIS WorkBench domain - Use shutil.which()
  for full executable paths - Remove shell=True on Windows (use webbrowser module) - Add subprocess
  output capture - Fix type annotation compatibility: - Add __future__ annotations for lxml/Cython
  compatibility - Auto-upgrade deprecated typing syntax (ruff --fix): - typing.Union -> X | Y syntax
  - typing.List -> list - collections.abc imports - Auto-format code (black) - Fix black regex
  pattern in pyproject.toml - Configure bandit to read pyproject.toml config - All checks passing:
  black ✓, ruff ✓, bandit ✓, tests ✓ (512 passed)

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.0.2 (2025-12-15)

### Bug Fixes

- Use GitHub Actions for Pages deployment instead of gh-deploy
  ([`af233f2`](https://github.com/mitre/cis-bench/commit/af233f24ff3841e33d462a83cdf7e5c0e7288adb))

Authored by: Aaron Lippold <lippold@gmail.com>

### Chores

- Release 0.0.2
  ([`17b039d`](https://github.com/mitre/cis-bench/commit/17b039d1cac4535a650352d2a43f5df4860f1c1c))

- Standardize documentation filenames to lowercase
  ([`e862941`](https://github.com/mitre/cis-bench/commit/e862941fa3ec23536a0eeb9cb7e7d38a1d93b011))

- Rename all documentation files to lowercase-with-dashes format - Update mkdocs.yml navigation to
  match new filenames - Move release-process.md to about/ section

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.0.1 (2025-12-15)

### Chores

- Initial commit - CIS Benchmark CLI v1.0.0
  ([`0450ef8`](https://github.com/mitre/cis-bench/commit/0450ef8ff637e6c49fd7869fd5a5cc9b9e67c2ec))

Production-ready CLI tool for fetching, managing, and exporting CIS benchmarks from CIS WorkBench to
  multiple formats including XCCDF.

Features: - Download CIS benchmarks via browser cookie authentication - Export to YAML, CSV,
  Markdown, and XCCDF (DISA/CIS styles) - SQLite catalog with full-text search -
  Configuration-driven XCCDF mapping engine - Comprehensive test suite (285 tests) - Automated
  releases via python-semantic-release - Complete documentation with MkDocs

Authored by: Aaron Lippold <lippold@gmail.com>

- Release 0.0.1
  ([`b3693ee`](https://github.com/mitre/cis-bench/commit/b3693ee0548c5068a01887a4fa9ad3ab7f38a480))
