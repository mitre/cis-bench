# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CIS Benchmark CLI** (`cis-bench`) - Command-line tool for downloading and managing CIS security benchmarks from CIS WorkBench.

- Download CIS benchmarks with browser cookie authentication
- Store as JSON (Pydantic-validated, 19 fields per recommendation)
- Export to YAML, CSV, Markdown, JSON, XCCDF (DISA STIG or CIS native)
- Search and discover 1,300+ benchmarks with platform filtering
- SQLite catalog with FTS5 full-text search

## Essential Commands

### Development
```bash
# Install with dev dependencies (ALWAYS use uv, not pip)
uv pip install -e ".[dev]"

# Run full test suite (1100+ tests)
pytest tests/

# Run specific test file
pytest tests/unit/test_catalog_database.py

# Run single test
pytest tests/unit/test_catalog_database.py::test_function_name -v

# Linting (auto-fix)
ruff check --fix .
ruff format .

# Security scanning
bandit -c pyproject.toml -r src/

# Pre-commit hooks (run manually)
pre-commit run --all-files
```

### CLI Usage (Testing Changes)
```bash
# Run via installed package
cis-bench --help

# Run via module (always works)
python -m cis_bench --help

# Key commands
cis-bench auth login --browser chrome
cis-bench catalog refresh
cis-bench search "ubuntu 22"
cis-bench download 23598
cis-bench export 23598 --format xccdf --style cis
cis-bench get "ubuntu 22" --format xccdf
```

### Test Markers
```bash
pytest -m unit           # Fast, isolated tests
pytest -m integration    # Component integration
pytest -m e2e            # Full CLI workflows
pytest -m architecture   # Architecture compliance
```

## Architecture

### Package Structure (src/ layout)
```
src/cis_bench/
├── cli/               # Click commands (app.py, commands/)
├── catalog/           # SQLite catalog (database, parser, search, scraper)
├── exporters/         # Format exporters + MappingEngine
│   └── configs/       # YAML mapping configs for XCCDF
├── fetcher/           # WorkBench scraper with strategy pattern
│   └── strategies/    # HTML version adapters (v1_current.py)
├── models/            # Pydantic models + xsdata XCCDF models
├── utils/             # Shared utilities (xml, parsers, transformers)
└── validators/        # XCCDF/DISA compliance validators
```

### Key Design Patterns

**Config-Driven XCCDF Export**: XCCDF field mappings defined in YAML configs (`src/cis_bench/exporters/configs/styles/`), not hard-coded. MappingEngine reads config and drives all transformations.

**Strategy Pattern (Fetcher)**: HTML parsing strategies adapt to CIS WorkBench HTML changes. Auto-detection chooses correct strategy. Add new strategy class when HTML structure changes.

**Factory Pattern (Exporters)**: Pluggable exporters implement BaseExporter interface. Register with ExporterFactory to add new formats.

### Data Flow
```
CIS WorkBench HTML
    ↓ (WorkbenchScraper + Strategy)
Pydantic Benchmark Model (19 fields per recommendation)
    ↓ (MappingEngine + YAML Config)
xsdata XCCDF Models
    ↓ (XML Serialization)
XCCDF 1.2/1.1.4 Output
```

### XCCDF Styles
- **DISA**: XCCDF 1.1.4, CCI mappings, VulnDiscussion, DoD/STIG compatible
- **CIS**: XCCDF 1.2, full CIS Controls v8, MITRE ATT&CK, enhanced namespace

## Testing

### Test Isolation
Tests automatically use isolated environment (`CIS_BENCH_ENV=test`):
- Test database: `/tmp/cis-bench-test/catalog.db`
- Production: `~/.cis-bench/catalog.db`
- Development: `~/.cis-bench-dev/catalog.db` (set `CIS_BENCH_ENV=dev`)

### Test Fixtures
All test data via fixtures in `tests/conftest.py`. NO hardcoded paths.
- `project_root`, `src_dir`, `package_dir` - Path fixtures
- `fixtures_dir`, `benchmark_fixtures`, `xccdf_fixtures` - Test data paths
- `sample_recommendation_minimal/complete` - Test data objects
- `cli_runner` - Click test runner

## Configuration

### Environment Variables
- `CIS_BENCH_ENV` - Environment (test/dev/production)
- `CIS_BENCH_BROWSER` - Default browser for auth

### Config Paths
- Session storage: `~/.cis-bench/session.json`
- Catalog database: `~/.cis-bench/catalog.db`
- Downloaded benchmarks: `~/.cis-bench/benchmarks/`

## Key Files

### Must-Read Before Modifying
- `src/cis_bench/exporters/mapping_engine.py` - Core XCCDF mapping logic
- `src/cis_bench/exporters/configs/styles/*.yaml` - Style-specific mappings
- `src/cis_bench/models/benchmark.py` - Pydantic data models
- `docs/developer-guide/mapping-engine-guide.md` - MappingEngine documentation

### Architecture Docs
- `docs/developer-guide/architecture.md` - System design
- `docs/developer-guide/data-flow-pipeline.md` - Complete data transformation
- `docs/developer-guide/how-to-add-xccdf-style.md` - Adding new XCCDF styles

## Code Standards

### Architecture Compliance
- Types and mappings MUST be in YAML config, not hard-coded
- Use `MappingEngine.get_xccdf_class()` instead of direct model imports
- No version-specific imports (xccdf_1_2, xccdf_v1_1) in exporters
- If design doc exists, follow it exactly; update design first if wrong

### Red Flags (Stop and Reconsider)
- Hard-coded type names in Python code
- Direct imports of version-specific models in exporters
- Choosing types based on if/else instead of config
- Skipping config layer to "make it work faster"

## CI/CD Workflow

### Release Process
- Semantic-release auto-triggers when CI passes on main
- `feat:` commits → minor version bump (0.4.0 → 0.5.0)
- `fix:` commits → patch version bump (0.4.0 → 0.4.1)
- Manual trigger available: `gh workflow run release.yml --ref main`

### Avoiding Race Conditions
**Rule: Batch related changes into a single PR**

Do NOT push multiple separate commits to main in quick succession. This causes race conditions where:
1. CI starts on commit A
2. Commit B pushed while CI running
3. Release triggers on old commit A, fails due to branch drift

**Correct workflow:**
- Bundle all related changes (code, docs, config) into one PR
- Wait for full CI → Release cycle before pushing more changes
- If release fails, use manual trigger after fixing

## Dependencies

### Core
- **xsdata** - XCCDF model generation from NIST XSD schemas
- **Click** - CLI framework
- **Rich** - Terminal styling and progress
- **Pydantic** - Data validation
- **browser-cookie3** - Browser cookie extraction
- **lxml** - XML processing
- **SQLModel** - SQLite database (catalog)

### Development
- **pytest** - Testing
- **ruff** - Linting/formatting
- **bandit** - Security scanning
- **pre-commit** - Git hooks

## Beads Task Tracking

This project uses [beads](https://github.com/steveyegge/beads) for task tracking with dependencies.

### Structure: Parent/Child vs Dependencies

| Concept | Command | Purpose |
|---------|---------|---------|
| **Parent/Child** | `--parent <epic-id>` | Organizational grouping - "this task belongs to this epic" |
| **Dependencies** | `bd dep add <task> <blocker>` | Workflow blocking - "can't start until blocker is done" |

**Use BOTH together:**
- `--parent` groups all tasks under an epic (so `bd children <epic>` shows them)
- `bd dep add` enforces implementation order (so `bd ready` shows unblocked work)

### Creating Epics with Tasks

```bash
# 1. Create the epic
bd create "Feature Name" --type epic -d "Full description of the feature"
# Returns: cis-bench-xxx

# 2. Create tasks as children of the epic
bd create "Task 1" --parent cis-bench-xxx --type task
bd create "Task 2" --parent cis-bench-xxx --type task
bd create "Task 3" --parent cis-bench-xxx --type task

# 3. Add dependencies (Task 3 blocked by Task 1 and Task 2)
bd dep add <task-3-id> <task-1-id>
bd dep add <task-3-id> <task-2-id>
```

### Navigation Commands

```bash
bd show <epic-id>           # See epic details + vision
bd children <epic-id>       # See all tasks under epic
bd epic status <epic-id>    # See completion progress (X/Y complete)
bd ready                    # What can I work on now? (no blockers)
bd blocked                  # What's waiting on what?
bd dep tree <task-id>       # See dependency chain
bd list --parent <epic-id>  # Alternative to bd children
```

### Workflow

```bash
# Starting work
bd ready                              # Find available work
bd show <task-id>                     # Review task details
bd update <task-id> --status in_progress  # Claim it

# Completing work
bd close <task-id>                    # Mark complete
bd sync                               # Push to remote
```

### Session Recovery

When starting a new session, recover context with:
```bash
bd ready                    # See what's available
bd show <current-epic>      # Get full context
bd children <current-epic>  # See all related tasks
```
