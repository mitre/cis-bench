# CHANGELOG


## v0.3.2 (2025-12-19)

### Documentation

- Add Catalog System section to architecture
  ([`5587850`](https://github.com/mitre/cis-bench/commit/558785066a7c48491c37ce6aff8ba8b114ad1bf7))

- Document SQLite database with SQLModel ORM - Document FTS5 full-text search implementation -
  Document schema with tables and relationships - Explain catalog metadata vs downloaded benchmarks
  distinction - Document Alembic migrations for schema versioning - Add platform inference patterns
  documentation - Update package structure to include catalog module - Update dependencies to
  include sqlmodel and alembic - Add catalog commands to Commands section

Authored by: Aaron Lippold <lippold@gmail.com>

- Reorganize design docs and fix documentation issues
  ([`dff7974`](https://github.com/mitre/cis-bench/commit/dff7974816510d2d548b5836eb61c8d7beb348be))

Session 29-30 documentation cleanup:

Design document reorganization: - Move ARCHITECTURE_PRINCIPLES.md → docs/design/design-principles.md
  - Move SYSTEM_ANALYSIS.md → docs/design/handler-reference.md - Move REFACTOR_PLAN.md →
  docs/design/xccdf-mapping-design.md - Move FINAL_PLAN.md → docs/design/architecture-decisions.md -
  Reduce total from 2,596 to 1,090 lines (58% reduction) - Add Design Documents section to
  mkdocs.yml navigation

Documentation fixes: - Fix Python version requirement: 3.8+ → 3.12+ (4 files) - Fix project version:
  1.0.0 → 0.3.1 (3 files) - Fix 12 broken links (case sensitivity: UPPERCASE → lowercase) -
  Standardize navigation header indentation (8 files) - Add CHANGELOG.md and NOTICE.md symlinks to
  docs/ - Add Third-Party Notices to About nav section - Fix NOTICE.md link path in licensing.md -
  Fix 3 missing anchor links (catalog-commands, scenario-4, yaml) - Fix mermaid syntax error (Loop →
  FieldLoop reserved keyword)

File cleanup: - Delete obsolete setup.py and requirements.txt - Move fix_markdown_lists.py →
  scripts/ - Add redownload_samples.py to scripts/ - Move python-project-setup-guide.md to root
  (general reference) - Update .pre-commit-config.yaml for new script location - Add RECOVERY*.md to
  .gitignore

Build verified: mkdocs build --strict passes with no warnings

Authored by: Aaron Lippold<lippold@gmail.com>


## v0.3.1 (2025-12-17)

### Bug Fixes

- Add --all-extras to packaging test step
  ([`bc5cf77`](https://github.com/mitre/cis-bench/commit/bc5cf77383c2d3a36a14587bc9ff249140ad7ac4))

Authored by: Aaron Lippold <lippold@gmail.com>

- Correct CLI packaging for pipx/uv installation
  ([`0a9a48b`](https://github.com/mitre/cis-bench/commit/0a9a48bb652a34fec3357d717c1de28a0f4be0aa))

- Add __main__.py for `python -m cis_bench` fallback - Add pipx.run entry point for pipx
  compatibility - Fix hardcoded version (now reads from importlib.metadata) - Update author to MITRE
  SAF Team - Add packaging verification job to CI (tests pipx install) - Update docs to recommend
  pipx/uv over pip (per Python Packaging Authority) - Fix 14 broken doc links (wrong case) - Add
  CHANGELOG to mkdocs nav - Docs now deploy after CI passes (not just after Release)

Authored by: Aaron Lippold <lippold@gmail.com>

- Update version test to use dynamic version
  ([`c1f307b`](https://github.com/mitre/cis-bench/commit/c1f307b97b73529e8e7777c44c95efb984ea1bf7))

Test was expecting hardcoded 1.0.0 instead of actual package version

Authored by: Aaron Lippold <lippold@gmail.com>

### Chores

- Release 0.3.1
  ([`e8d7bb8`](https://github.com/mitre/cis-bench/commit/e8d7bb8958fbe702977b0dd476796f91ebdcee3e))


## v0.3.0 (2025-12-17)

### Bug Fixes

- Preserve types in VariableSubstituter and fix empty element handling
  ([`a91b42b`](https://github.com/mitre/cis-bench/commit/a91b42b2b3512ac7c63729ce4abe797282e152d5))

VariableSubstituter changes: - Preserve original type for single-variable templates ({item.ig1}) -
  Convert to string only for mixed templates (text + variable) - Fixes boolean attributes (False →
  'false' for XML)

Empty element handling: - Allow elements with attributes but no content (DISA fix element) - Skip
  only if no value AND no attributes

Fixes: - CIS Controls ig1/ig2/ig3 now lowercase 'true'/'false' - DISA fix elements now generated

Authored by: Aaron Lippold <lippold@gmail.com>

### Chores

- Add OpenSCAP schema library for validation
  ([`ef78dc0`](https://github.com/mitre/cis-bench/commit/ef78dc0cfe856d7e70b3e87cbe0bb890bbb03cd4))

Add complete XCCDF/CPE/OVAL schema collection from OpenSCAP (551 XSD files).

Includes: - XCCDF 1.1 and 1.2 validation schemas - CPE 1.0, 2.0, 2.1, 2.3 schemas - OVAL 5.x schemas
  (all versions) - ARF (Asset Reporting Format) schemas

Updated XML catalog for proper schema resolution (local files, no network).

Enables NIST XCCDF schema validation without external dependencies.

Source: OpenSCAP/openscap (NIST certified SCAP 1.2 toolkit)

Authored by: Aaron Lippold <lippold@gmail.com>

- Release 0.3.0
  ([`e9408f2`](https://github.com/mitre/cis-bench/commit/e9408f2fa8cee7300eed80d5828d55f30730f69a))

### Continuous Integration

- Install libxml2-utils for xmllint schema validation
  ([`d6c7218`](https://github.com/mitre/cis-bench/commit/d6c7218c79c996dd9abb22bc0139a691b6be41ae))

The test_disa_export_validates_nist_schema test requires xmllint to validate XCCDF exports against
  the NIST schema.

Authored by: Aaron Lippold <lippold@gmail.com>

### Documentation

- Complete Phase 5 - comprehensive documentation updates
  ([`29faca9`](https://github.com/mitre/cis-bench/commit/29faca9bcdf90dee4b2443ba2bf72e675ab22cd2))

Updated ALL documentation files for generic structure refactor:

Core Docs Updated: - design-philosophy.md: DISA vs CIS export patterns - architecture.md: Generic
  handler architecture - mapping-engine-design.md: Handler specifications - mapping-engine-guide.md:
  Practical examples - how-to-add-xccdf-style.md: Zero-code extensibility -
  yaml-config-reference.md: Updated structure names

New Docs: - REFACTOR_SUMMARY.md: High-level overview - ARCHITECTURE_PRINCIPLES.md: Design
  enforcement - FINAL_PLAN.md: Implementation plan - SYSTEM_ANALYSIS.md: System review -
  adding-pci-dss.md: Framework extension guide

All references to deleted patterns removed: - official_cis_controls → metadata_from_config -
  enhanced_namespace → ident_from_list - custom_namespace → metadata_from_config -
  build_cis_controls → (deleted, now generic)

Documents DISA/CIS differences, generic patterns, extensibility.

Phase 5 complete.

Authored by: Aaron Lippold <lippold@gmail.com>

- Update documentation for generic structure handlers
  ([`b847a0d`](https://github.com/mitre/cis-bench/commit/b847a0d8043ca0a995405d03b1d637f20663237b))

Updates: - design-philosophy.md: Document DISA vs CIS export differences - REFACTOR_SUMMARY.md:
  High-level overview of changes - developer-guide/adding-pci-dss.md: Framework extension example

Key changes documented: - DISA uses idents only (no metadata) - fixes Vulcan errors - CIS uses dual
  representation (ident + metadata for CIS Controls) - MITRE now as idents (not in metadata -
  cleaner) - Profiles at Benchmark level (proper XCCDF standard) - Adding frameworks requires only
  YAML config

Phase 5 complete.

Authored by: Aaron Lippold <lippold@gmail.com>

### Features

- Add fix element to DISA exports
  ([`94f2858`](https://github.com/mitre/cis-bench/commit/94f2858ae94a267c6ff669842cf7f5da60af1ac3))

Add empty <fix id='...'/> elements to match official DISA STIG structure.

Official DISA STIGs have fix elements as placeholders with ID attributes. Required for full DISA
  STIG compliance.

Authored by: Aaron Lippold <lippold@gmail.com>

- Add LibCST utility for safe code refactoring
  ([`7ff8470`](https://github.com/mitre/cis-bench/commit/7ff84704a3e0736ce487105a16381efcdf2fb2b5))

Add scripts/remove_code.py with comprehensive test suite for safely removing functions, methods, and
  classes during refactoring.

- LibCST-based code removal (preserves formatting) - 27 comprehensive tests (edge cases covered) -
  Dry-run mode for safety - Handles decorators, async, dataclass, nested functions

This tool enables safe cleanup during XCCDF refactoring.

Authored by: Aaron Lippold <lippold@gmail.com>

- Config-driven STIG IDs and Vulcan compatibility
  ([`40522b5`](https://github.com/mitre/cis-bench/commit/40522b58ea67d4edbbb03e3a6446d392b2596596))

- Add config-driven ID generation (V-/SV- for DISA, descriptive for CIS) - Add ref_to_stig_number()
  helper (3.1.1 → 030101) - Add strip_version_prefix transform (v4.0.0 → 4.0.0) - Restructure
  configs: base.yaml + styles/{disa,cis}.yaml - Fix duplicate CCI deduplication - Remove status from
  Rules (belongs at Benchmark level only) - Add 40+ new tests for ID formats and Vulcan
  compatibility - Move test_remove_code_script.py to tests/scripts/

Tested: 583 tests pass, validated with stig_parser and Vulcan 2.2.1

Authored by: Aaron Lippold <lippold@gmail.com>

- Implement generic config-driven structure handlers
  ([`e46ef23`](https://github.com/mitre/cis-bench/commit/e46ef2338b8af5ceeb7acfea16372dfddadfc5f5))

Add three generic handlers for XCCDF generation:

1. generate_idents_from_config(): Generate ident elements from any list - Works for CCI, CIS
  Controls, MITRE, PCI-DSS, ISO 27001, etc. - Template-based (system, value, optional attributes)

2. generate_metadata_from_config(): Generate nested XML from config - Supports grouping (e.g., CIS
  Controls by version) - Recursive children with attributes and content - Requires post-processing
  flag for lxml injection

3. generate_profiles_from_rules(): Generate Benchmark-level Profiles - Builds Profile elements with
  select lists - Works for CIS Levels, DISA MAC, any applicability system

All handlers are fully config-driven (no hard-coded structures). Removes organization-specific
  methods (build_cis_controls, generate_cis_idents).

Tests: - 11 unit tests for metadata generation - 4 integration tests for profile generation - All
  passing

Authored by: Aaron Lippold <lippold@gmail.com>

### Refactoring

- Update CIS export to use generic patterns
  ([`058dacb`](https://github.com/mitre/cis-bench/commit/058dacbb82ae30511600290a36fced94eea219ab))

CIS configuration changes: - Use metadata_from_config for CIS Controls (with post-processing) - Use
  ident_from_list for MITRE (not metadata - cleaner) - Add profiles configuration - Remove old
  enhanced_namespace and official_cis_controls patterns

Exporter changes: - Implement generic _inject_metadata_from_config() method - Remove hard-coded
  CIS-specific injection - Metadata injection now config-driven (requires_post_processing flag)

Test updates: - Update CIS tests for new architecture - MITRE now as idents (not in enhanced
  metadata) - Profiles now at Benchmark level (not in metadata)

CIS exports now use dual representation: - CIS Controls in both ident and metadata (official
  pattern) - MITRE in idents only (no namespace pollution)

Authored by: Aaron Lippold <lippold@gmail.com>

### Testing

- Fix all skipped tests and improve assertions
  ([`5078775`](https://github.com/mitre/cis-bench/commit/5078775b791e7cf34d93b2d7a7b0a13b7933cfed))

- Remove skip from NIST schema validation (schemas now available) - Remove skip from DISA
  conventions validation (works correctly) - Fix CIS ident/metadata count assertion (dual
  representation = 2x idents) - Fix boolean attribute test (now checks for lowercase) - Add mock
  PCI-DSS config to prove extensibility - Fix Pydantic validator for total_recommendations count

All 575 tests now passing (0 skipped, 0 failed).

Authored by: Aaron Lippold <lippold@gmail.com>


## v0.2.3 (2025-12-16)

### Chores

- Release 0.2.3
  ([`475a10b`](https://github.com/mitre/cis-bench/commit/475a10b346d19dd5fd034fd1f8355097e361de7d))

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
