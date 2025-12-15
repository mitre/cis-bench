# CHANGELOG


## v0.0.2 (2025-12-15)

### Bug Fixes

- Use GitHub Actions for Pages deployment instead of gh-deploy
  ([`af233f2`](https://github.com/mitre/cis-bench/commit/af233f24ff3841e33d462a83cdf7e5c0e7288adb))

Authored by: Aaron Lippold <lippold@gmail.com>

### Chores

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
