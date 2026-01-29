# CIS Benchmark CLI

> Professional command-line tool for downloading and managing CIS security benchmarks from CIS WorkBench

[![PyPI version](https://img.shields.io/pypi/v/cis-bench.svg)](https://pypi.org/project/cis-bench/)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/mitre/cis-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/mitre/cis-bench/actions/workflows/ci.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

---

## What is CIS Benchmark CLI?

`cis-bench` downloads CIS security benchmarks from CIS WorkBench and exports them to multiple formats, including NIST XCCDF for use with SCAP compliance scanners like OpenSCAP, SCC, and Nessus.

**Use Cases:**

- **Discover** - Search 1,300+ CIS benchmarks with platform filtering
- **Download** - Fetch benchmarks with browser-based authentication
- **Convert** - Export to YAML, CSV, Markdown, or NIST XCCDF
- **Comply** - Generate DISA STIG-compatible XCCDF for DoD environments
- **Analyze** - Extract 19 fields including CIS Controls, MITRE ATT&CK, NIST mappings

---

## Quick Start

```bash
# 1. Install (choose one)
pipx install cis-bench    # Recommended - isolated environment, no PATH issues
uv tool install cis-bench # Alternative - fast, modern
pip install cis-bench     # Not recommended - may have PATH issues

# 2. Login (one-time)
cis-bench auth login --browser chrome

# 3. Build catalog (one-time, ~2 minutes)
cis-bench catalog refresh

# 4. Get a benchmark
cis-bench get "ubuntu 22.04" --format xccdf --style cis

# Done! You have a SCAP-compliant XCCDF file
```

**[Get Started Guide](https://mitre.github.io/cis-bench/getting-started/)** for detailed setup

---

## Key Features

### Session-Based Authentication
Login once, use everywhere. No more passing `--browser` on every command.

```bash
cis-bench auth login --browser chrome
cis-bench download 23598 # Uses saved session
```

### Searchable Catalog
Fast local search of 1,300+ benchmarks with FTS5 full-text search and platform taxonomy.

```bash
cis-bench search "oracle" --platform-type cloud
cis-bench search --platform-type database --latest
```

### Unified Get Command
Search + download + export in one step.

```bash
cis-bench get "ubuntu 22" --format xccdf --style cis
```

### Database Caching
Downloaded benchmarks cached in SQLite for instant re-export.

```bash
cis-bench export 23598 --format xccdf # Instant (from cache)
```

### Multiple Export Formats

- **YAML** - Human-readable structured data
- **CSV** - Spreadsheet import
- **Markdown** - Documentation
- **JSON** - Machine-readable
- **XCCDF** - SCAP compliance (DISA STIG or CIS native)

### Platform Filtering
Two-level taxonomy: category (cloud/os/database) + specific platform (aws/ubuntu/oracle).

```bash
cis-bench search --platform-type cloud # All cloud benchmarks
cis-bench search --platform ubuntu # All Ubuntu versions
```

### Scriptable and Automatable
All commands support JSON output for piping to `jq`, scripting, CI/CD.

```bash
cis-bench search oracle --output-format json | jq -r '.[].benchmark_id'
```

### Performance

- Parallel catalog scraping (~2 min for 1,300+ benchmarks)
- Retry logic with exponential backoff
- Progress bars on long operations

---

## Documentation

📚 **Full documentation:** [https://mitre.github.io/cis-bench/](https://mitre.github.io/cis-bench/)

### For Users

- **[Getting Started](https://mitre.github.io/cis-bench/getting-started/)** - Installation and first steps
- **[End-to-End Workflows](https://mitre.github.io/cis-bench/user-guide/workflows/)** - Real-world scenarios
- **[Commands Reference](https://mitre.github.io/cis-bench/user-guide/commands-reference/)** - Complete command syntax and options
- **[Catalog Guide](https://mitre.github.io/cis-bench/user-guide/catalog-guide/)** - Search and discovery workflows
- **[XCCDF Export Guide](https://mitre.github.io/cis-bench/user-guide/xccdf-guide/)** - SCAP compliance export
- **[Configuration](https://mitre.github.io/cis-bench/user-guide/configuration/)** - Environment variables and settings
- **[Troubleshooting](https://mitre.github.io/cis-bench/user-guide/troubleshooting/)** - Common issues and solutions

### For Developers

- **[Architecture Overview](https://mitre.github.io/cis-bench/developer-guide/architecture/)** - System design and components
- **[Data Flow Pipeline](https://mitre.github.io/cis-bench/developer-guide/data-flow-pipeline/)** - Complete transformation pipeline
- **[MappingEngine Guide](https://mitre.github.io/cis-bench/developer-guide/mapping-engine-guide/)** - Working with YAML configs
- **[Contributing Guide](https://mitre.github.io/cis-bench/developer-guide/contributing/)** - Code standards and development workflow
- **[Testing Guide](https://mitre.github.io/cis-bench/developer-guide/testing/)** - Running and writing tests
- **[How to Add XCCDF Style](https://mitre.github.io/cis-bench/developer-guide/how-to-add-xccdf-style/)** - Extending XCCDF export

### Technical Reference

- **[Data Model](https://mitre.github.io/cis-bench/technical-reference/data-model/)** - Pydantic models and field definitions
- **[Mapping Engine Design](https://mitre.github.io/cis-bench/technical-reference/mapping-engine-design/)** - Technical architecture
- **[XCCDF Styles](https://mitre.github.io/cis-bench/technical-reference/xccdf-styles/)** - DISA vs CIS format comparison
- **[YAML Config Reference](https://mitre.github.io/cis-bench/technical-reference/yaml-config-reference/)** - Mapping configuration syntax

---

## Example Workflows

### Export AlmaLinux 10 for OpenSCAP Scanning

```bash
cis-bench auth login --browser chrome
cis-bench search "almalinux 10"
# Shows: Benchmark ID 23598

cis-bench download 23598
cis-bench export 23598 --format xccdf --style cis -o almalinux10-cis.xml

# Use with OpenSCAP
oscap xccdf eval --profile Level_1 almalinux10-cis.xml
```

### Batch Export All Cloud Benchmarks

```bash
# Search and download all cloud benchmarks
cis-bench search --platform-type cloud --output-format json | \
jq -r '.[].benchmark_id' | \
head -5 | \
xargs -I {} cis-bench download {}

# Export all to DISA STIG format
cis-bench list --output-format json | \
jq -r '.[].file' | \
xargs -I {} cis-bench export {} --format xccdf --style disa
```

### Create Compliance Spreadsheet

```bash
cis-bench download 24008 # Oracle Cloud Infrastructure
cis-bench export 24008 --format csv -o oci-compliance.csv

# Open in Excel/Numbers for tracking
open oci-compliance.csv
```

**More examples in [User Guide](https://mitre.github.io/cis-bench/user-guide/workflows/)**

---

## XCCDF Export

Generate NIST XCCDF 1.2 format compatible with SCAP compliance tools:

**Two Styles Available:**

### DISA STIG Style (For DoD/Government)
```bash
cis-bench export 23598 --format xccdf --style disa
```

**Features:**

- XCCDF 1.1.4 (DISA standard)
- CCI mappings (2,161 DoD Control Correlation Identifiers)
- VulnDiscussion elements
- STIG-compatible structure

### CIS Native Style (For Full Metadata)
```bash
cis-bench export 23598 --format xccdf --style cis
```

**Features:**

- XCCDF 1.2 (latest standard)
- Full CIS Controls v8 metadata (318 controls)
- MITRE ATT&CK techniques (296 mappings)
- Enhanced namespace for custom fields

**[XCCDF Styles Comparison](https://mitre.github.io/cis-bench/technical-reference/xccdf-styles/)** for detailed differences

---

## Architecture

### Design Principles

**Config-Driven** - XCCDF field mappings defined in YAML, not hard-coded
**Extensible** - Strategy pattern for HTML changes, Factory pattern for exporters
**Validated** - xsdata-generated models from NIST XSD schemas
**Tested** - 1,100+ tests with 96% coverage

### Component Overview

```
CIS WorkBench HTML
 (WorkbenchScraper + Strategy Pattern)
Pydantic Models (19 fields)
 (MappingEngine + YAML Config)
xsdata XCCDF Models
 (XML Serialization)
NIST XCCDF Output
```

**[Architecture Documentation](https://mitre.github.io/cis-bench/developer-guide/architecture/)** for complete system design

---

## Project Status

**Version:** 0.4.0 (Beta)
**Tests:** 1,100+ tests with 96% coverage
**Python:** 3.12+
**License:** Apache 2.0

**Current Features:**

- Session-based authentication
- Searchable catalog with 1,300+ benchmarks
- Platform taxonomy (cloud/os/database/container/application)
- Unified `get` command
- Database caching
- Multiple export formats
- Batch export (multiple benchmarks at once)
- XCCDF export (both DISA and CIS styles)
- Parallel catalog scraping
- Output formats for scripting (json/csv/yaml)

**Future Features:**

- Offline mode
- Benchmark comparison/diff
- Recommendation search across benchmarks

**[Future Features](https://mitre.github.io/cis-bench/about/future-features/)** for roadmap

---

## Installation

### From PyPI (Recommended)

Per [Python Packaging Authority guidelines](https://packaging.python.org/en/latest/guides/installing-stand-alone-command-line-tools/), CLI tools should be installed with **pipx** or **uv tool**, not pip directly.

```bash
# RECOMMENDED: pipx (isolated environment, correct PATH)
pipx install cis-bench

# ALTERNATIVE: uv tool (fast, modern)
uv tool install cis-bench

# Verify
cis-bench --version
```

> **Why not pip?** `pip install` installs to a directory that may not be in your PATH, causing "command not found" errors. pipx and uv tool handle this correctly.

<details>
<summary><strong>Using pip anyway?</strong> (click to expand)</summary>

```bash
pip install cis-bench
```

If you get `cis-bench: command not found`:

```bash
# Option 1: Use module syntax (always works)
python -m cis_bench --version

# Option 2: Add pip's bin to PATH
export PATH="$HOME/.local/bin:$PATH"  # Add to ~/.bashrc or ~/.zshrc
```

</details>

### From Source

```bash
git clone https://github.com/mitre/cis-bench.git
cd cis-bench

# Install for development
pipx install -e .
# Or: uv tool install -e .

# Verify
cis-bench --version
```

### Development Install

```bash
# Clone and install with dev dependencies
git clone https://github.com/mitre/cis-bench.git
cd cis-bench
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/ -v
```

**[Getting Started](https://mitre.github.io/cis-bench/getting-started/)** for detailed installation

---

## Requirements

**Runtime:**

- Python 3.12+
- CIS WorkBench account (free registration at workbench.cisecurity.org)
- Supported browser (Chrome, Firefox, Edge, or Safari)

**Development:**

- All runtime requirements
- pytest, ruff, bandit, pre-commit (installed via `[dev]` extras)

---

## Support and Contributing

**Found a bug?** Open an issue at [GitHub Issues](https://github.com/mitre/cis-bench/issues)

**Want to contribute?** See [Contributing Guide](https://mitre.github.io/cis-bench/developer-guide/contributing/)

**Questions?** Check [Documentation](https://mitre.github.io/cis-bench/) or open a discussion

---

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details

**Acknowledgments:**

- Based on proof-of-concept by m-ghonim (Mohamed Ghoneam)
- CIS WorkBench for providing benchmark data
- NIST for XCCDF schema specifications
- DISA for STIG formatting conventions

---

## Quick Links

**User Documentation:**

- [Getting Started](https://mitre.github.io/cis-bench/getting-started/)
- [End-to-End Workflows](https://mitre.github.io/cis-bench/user-guide/workflows/)
- [Commands Reference](https://mitre.github.io/cis-bench/user-guide/commands-reference/) - Complete command syntax
- [XCCDF Guide](https://mitre.github.io/cis-bench/user-guide/xccdf-guide/)

**Developer Documentation:**

- [Architecture](https://mitre.github.io/cis-bench/developer-guide/architecture/)
- [Data Flow Pipeline](https://mitre.github.io/cis-bench/developer-guide/data-flow-pipeline/)
- [MappingEngine Guide](https://mitre.github.io/cis-bench/developer-guide/mapping-engine-guide/)
- [Contributing](https://mitre.github.io/cis-bench/developer-guide/contributing/)
- [Testing](https://mitre.github.io/cis-bench/developer-guide/testing/)

**Need Help?**

- Check [Troubleshooting Guide](https://mitre.github.io/cis-bench/user-guide/troubleshooting/)
- Review [Configuration Options](https://mitre.github.io/cis-bench/user-guide/configuration/)
- Browse [Full Documentation](https://mitre.github.io/cis-bench/)
