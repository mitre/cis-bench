# CHANGELOG


## v0.2.3 (2025-12-16)

### Documentation

- Add comprehensive Python project setup guide
  ([`d4b383f`](https://github.com/mitre/cis-bench/commit/d4b383f5d9248ac652488ec1c69af82d9c16d036))

Reusable template for MITRE Python projects covering uv, ruff, semantic-release, CI/CD, testing, and
  community health files.

Also copied to repo-minder for organizational reuse.

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.2.2 (2025-12-15)

### Chores

- Release 0.2.2
  ([`9b4cd5b`](https://github.com/mitre/cis-bench/commit/9b4cd5b2b9d64fde720c61b3d14bdd3d56ad8adc))

### Documentation

- Add community health files and document gitflow workflow
  ([`8b13420`](https://github.com/mitre/cis-bench/commit/8b1342033e8cb9a36ede5ae38df8ad0c03133528))

- Add SECURITY.md (vulnerability disclosure policy) - Add CODE_OF_CONDUCT.md (Contributor Covenant)
  - Rename LICENSE to LICENSE.md (standard naming) - Update contributing.md with gitflow workflow
  documentation - Document branch-based development (required for semantic-release) - Add
  conventional commit guidelines - Update setup instructions to use uv - Explain why we don't commit
  directly to main

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.2.1 (2025-12-15)

### Chores

- Release 0.2.1
  ([`e4e1d11`](https://github.com/mitre/cis-bench/commit/e4e1d11d99978c487ad04909c2ea6e485c58027c))

### Documentation

- Add community health files and document gitflow workflow
  ([`5de6095`](https://github.com/mitre/cis-bench/commit/5de6095b91e21d8f41f3f8e1354b0680c68eb2c5))

- Add SECURITY.md (vulnerability disclosure policy) - Add CODE_OF_CONDUCT.md (Contributor Covenant)
  - Rename LICENSE to LICENSE.md (standard naming) - Update contributing.md with gitflow workflow
  documentation - Document branch-based development (required for semantic-release) - Add
  conventional commit guidelines - Update setup instructions to use uv - Explain why we don't commit
  directly to main

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.2.0 (2025-12-15)

### Bug Fixes

- Add --all-extras to all uv run commands in CI
  ([`e9f5443`](https://github.com/mitre/cis-bench/commit/e9f544368a9bfae11fa5207fa5f8eb12413be299))

- Ensures dev dependencies (pytest, ruff, etc.) are installed - Fixes 'pytest: command not found'
  errors

Authored by: Aaron Lippold <lippold@gmail.com>

- Docs deploy only after successful release
  ([`6393d9f`](https://github.com/mitre/cis-bench/commit/6393d9fec59dffda8400f0fdbaafc42076acdb2e))

- Change docs workflow to depend on Release success, not CI - Ensures documentation matches
  published PyPI version - Prevents docs updates for failed releases - Add PyPI version badge to
  README - Update Python version badge to 3.12+ - Add CI status badge - Update installation to use
  PyPI package

Authored by: Aaron Lippold <lippold@gmail.com>

- Use --frozen instead of --locked in CI workflows
  ([`d7d3129`](https://github.com/mitre/cis-bench/commit/d7d3129b59a2544a25226afd3532f15be0cad2da))

- Change from --locked to --frozen for uv commands - --frozen allows metadata updates while using
  lock file - Fixes lockfile update errors in CI - Simplify security job to use uv run --with bandit

Authored by: Aaron Lippold <lippold@gmail.com>

### Chores

- Release 0.2.0
  ([`74973fc`](https://github.com/mitre/cis-bench/commit/74973fc89aaf6ad9d69ee9fab64ca3572b69a6a3))

### Features

- Complete migration to uv package manager
  ([`fb30489`](https://github.com/mitre/cis-bench/commit/fb3048978bc79f8da423db717ad7c4c1575c2cc4))

- Update CI workflow to use setup-uv@v7 with caching - Use uv sync --locked for reproducible builds
  - Use uv run for all commands (pytest, ruff, bandit) - Remove ruff-action, use uv run ruff instead
  - Add uv.lock for dependency locking - Update README to recommend uv installation - Faster CI runs
  (10-100x faster than pip) - Consistent with modern Python ecosystem (2025)

Authored by: Aaron Lippold <lippold@gmail.com>

- Migrate to uv for dependency management
  ([`edfbb7c`](https://github.com/mitre/cis-bench/commit/edfbb7c55b37d334fe228f03d1863633f6256ca1))

- Add uv.lock for reproducible builds - Update README to recommend uv for installation - Align local
  development with CI (already uses uv) - 10-100x faster than pip - Better dependency resolution

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.1.0 (2025-12-15)

### Chores

- Release 0.1.0
  ([`42b6a0e`](https://github.com/mitre/cis-bench/commit/42b6a0e0c09926967887c63e31b35e7b87fc0536))

### Features

- Initial PyPI release
  ([`0f6440e`](https://github.com/mitre/cis-bench/commit/0f6440ef20dd69a478c7201b4b7b621e3dea5444))

Enable automated PyPI publishing via trusted publisher

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.0.4 (2025-12-15)

### Bug Fixes

- Add missing test fixtures and fix workflow dependencies
  ([`7d53bc8`](https://github.com/mitre/cis-bench/commit/7d53bc8882d15f66a7d96e79f193b904be1585e6))

- Fix .gitignore to only exclude root-level outputs, not test fixtures - Add missing test data
  files: - tests/fixtures/benchmarks/almalinux_complete.json (2MB fixture) -
  tests/fixtures/benchmarks/almalinux_10recs_sample.json - src/cis_bench/data/cis-cci-mapping.json
  (CCI lookup data) - Fix workflow ordering: - Release workflow now runs AFTER CI completes
  successfully - Docs workflow now runs AFTER CI completes successfully - Prevents
  releases/deployments with failing tests - CI must pass before any Release or Docs deployment

Authored by: Aaron Lippold <lippold@gmail.com>

- Remove black, use only ruff for linting and formatting
  ([`52b5d78`](https://github.com/mitre/cis-bench/commit/52b5d78101fdf29456a2ba34594bd2b259c80e6f))

- Remove psf/black from CI workflow - Remove [tool.black] config section - Use only
  astral-sh/ruff-action@v3 (handles both linting and formatting) - Fix security scan to use uv sync
  and uv run bandit - Eliminates black/ruff formatting conflicts

Authored by: Aaron Lippold <lippold@gmail.com>

- Use dev dependencies in CI for consistent tool versions
  ([`4616b79`](https://github.com/mitre/cis-bench/commit/4616b7985d68d3d2022bff6dfb0bb5f5632749bf))

- Install package with [dev] extras instead of manually installing black/ruff - Ensures CI uses same
  tool versions as local development - Prevents version mismatch between local checks and CI checks

Authored by: Aaron Lippold <lippold@gmail.com>

- Use official GitHub Actions for linting and formatting
  ([`62e389f`](https://github.com/mitre/cis-bench/commit/62e389f494b680624a0d309a3c643a66e47264a3))

- Use psf/black@stable action for formatting checks - Use chartboost/ruff-action for linting - Use
  mdegis/bandit-action for security scanning - Eliminates PATH issues with manually installed tools

Authored by: Aaron Lippold <lippold@gmail.com>

- Use proper GitHub Actions pattern for CI
  ([`5d8a92b`](https://github.com/mitre/cis-bench/commit/5d8a92bd6756dacc68cc4726f5087f6bdfdd51b9))

Based on working examples from established projects: - Use psf/black@stable with use_pyproject: true
  - Use astral-sh/ruff-action@v3 (official action) - Use astral-sh/setup-uv@v5 for UV setup - Use uv
  sync for dependency installation - Separate jobs for format, lint, security, and test

Authored by: Aaron Lippold <lippold@gmail.com>

- Use python -m prefix for black and ruff in CI
  ([`2922267`](https://github.com/mitre/cis-bench/commit/2922267e792fb03c9d67fef448154537cf133b46))

Ensures tools are found after pip install

Authored by: Aaron Lippold <lippold@gmail.com>

### Chores

- Release 0.0.4
  ([`24085cb`](https://github.com/mitre/cis-bench/commit/24085cb7fb3e5e2b43dbddfecaaf3c5ddb5313fd))

- Update pre-commit hooks and fix formatting
  ([`526aaf6`](https://github.com/mitre/cis-bench/commit/526aaf6b00baa1a56c2dae69a1663018001ec7e7))

- Update pre-commit hooks to latest versions: - pre-commit-hooks: v5.0.0 → v6.0.0 - ruff: v0.8.4 →
  v0.14.9 - bandit: 1.7.10 → 1.9.2 - Remove S320 references (rule removed from ruff) - Install
  pre-commit hooks (.git/hooks/pre-commit) - Remove invalid JSON fixture (unused) - Auto-format
  files with latest ruff-format - Auto-fix markdown list formatting - All pre-commit hooks now
  passing

Authored by: Aaron Lippold <lippold@gmail.com>

- Update setup.py Python version requirement
  ([`6a88a60`](https://github.com/mitre/cis-bench/commit/6a88a6034e0ce00a8626d3fcf422d0b914982bb1))

- Update python_requires to >=3.12 to match pyproject.toml

Authored by: Aaron Lippold <lippold@gmail.com>


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

### Chores

- Release 0.0.3
  ([`51973ce`](https://github.com/mitre/cis-bench/commit/51973ce1b1488fe093364036355dca87f4ca2488))


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
