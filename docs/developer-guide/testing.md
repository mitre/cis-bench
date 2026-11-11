# Testing Guide

!!! info "Documentation Path"
**You are here:** Developer Guide > Testing

- **For contributing:** See [Contributing Guide](contributing.md)
- **For architecture:** See [Architecture Overview](architecture.md)

## Test Environment Isolation

This project uses environment-based configuration to ensure tests never pollute production or development data.

### Environments

**Default:**
```bash
# No environment variable set
cis-bench catalog refresh
# Uses: ~/.local/share/cis-bench/catalog.db
```

**Development (one folder for everything):**
```bash
export CIS_BENCH_HOME=~/cis-bench-dev
cis-bench catalog refresh
# Uses: ~/cis-bench-dev/catalog.db
```

**Test (automatic in pytest):**
```bash
pytest tests/
# Uses: a new temporary folder per run
```

### How It Works

**Config Module:**

- `src/cis_bench/config.py` has one `Settings` class (pydantic-settings)
- The folders are the XDG base directories (`config.toml` in `~/.config/cis-bench`, `catalog.db` and `benchmarks/` in `~/.local/share/cis-bench`, `session.cookies` in `~/.local/state/cis-bench`); `CIS_BENCH_HOME` puts them all in one folder
- `CIS_BENCH_DATA_DIR` and `CIS_BENCH_ENV` are no longer read; a set one is a configuration error

**Pytest Fixture:**

- `tests/conftest.py` has the `test_environment` fixture
- `autouse=True`, `scope="session"`: applies to every test, set once at start
- Sets `CIS_BENCH_HOME` to a temporary folder and removes any `CIS_BENCH_ENV` or `CIS_BENCH_DATA_DIR` from your shell

**Result:**

- Tests use a temporary folder
- Dev work uses whatever `CIS_BENCH_HOME` you set, or the XDG folders
- Your own folders are never touched by tests

---

## Running Tests

### Full Test Suite
```bash
pytest tests/
# uses a temporary folder automatically
```

### Specific Test Modules
```bash
pytest tests/unit/test_catalog_database.py # Unit tests
pytest tests/integration/ # Integration tests
pytest tests/e2e/ # End-to-end CLI tests
```

### By Category

Each folder under `tests/` is a category, and `tests/conftest.py` marks its tests with the
folder's name, so a category can be selected with `-m` (and combined: `-m "unit or
regression"`, `-m "not e2e"`). A new folder needs its marker declared under
`[tool.pytest.ini_options] markers` in `pyproject.toml`, or collection stops with an error.

```bash
pytest tests -m unit           # tests/unit
pytest tests -m integration    # tests/integration
pytest tests -m e2e            # tests/e2e
pytest tests -m regression     # tests/regression
pytest tests -m architecture   # the architecture compliance modules
pytest tests/scripts           # project utility scripts; not part of `pytest tests`
```

### With Coverage
```bash
pytest tests/ --cov=src/cis_bench --cov-report=html
open htmlcov/index.html
```

### Verbose Output
```bash
pytest tests/ -v # Verbose test names
pytest tests/ -vv # Very verbose
pytest tests/ -s # Show print statements
```

---

## Test Organization

### Unit Tests (`tests/unit/`)

- Test individual functions/classes in isolation
- Use mocks for external dependencies
- Fast (run in < 1 second each)
- Use `tmp_path` fixtures for temporary files/databases

### Integration Tests (`tests/integration/`)

- Test components working together
- May use real files/databases (in temp locations)
- Test exporters, fetchers, validators

### E2E Tests (`tests/e2e/`)

- Test complete workflows via CLI
- Use `CliRunner` to invoke commands
- Test user-facing behavior
- Still isolated (test environment)

---

## Database Testing

### Temporary Databases

**Unit tests:**
```python
@pytest.fixture
def temp_db(tmp_path):
"""Create temporary catalog database, closed when the test is done."""
db = CatalogDatabase(tmp_path / "test.db")
db.initialize_schema()
yield db
db.close()
```

A database left open is a defect: the suite runs with `ResourceWarning` (and pytest's
unraisable-exception warning, the form a warning raised at garbage collection takes) as
errors, so an unclosed connection fails a test on Python 3.13. Close a database you open
(`db.close()`, or `with closing(CatalogDatabase(path)) as db:`), and close raw
`sqlite3.connect(...)` connections with `contextlib.closing` (sqlite3's own `with` block
only commits).

**E2E tests:**

- Automatically use `<temporary data folder>/catalog.db`
- No manual setup needed
- A new folder each test run

### Test Data Factories

We use pytest fixtures (not factory_boy) for test data:

```python
@pytest.fixture
def sample_benchmark_data():
return {
"benchmark_id": "23598",
"title": "CIS Ubuntu Linux 20.04",
# ...
}
```

### Synthetic Benchmarks

The repository holds no CIS content. Tests and documentation examples that need whole
benchmarks use the synthetic ones in `tests/fixtures/benchmarks/`: every tool, path, setting
and sentence in them is invented, and each follows the shape of a kind of real copy, so
commands take the paths real downloads take.

| ID | File | Shape |
| --- | --- | --- |
| 90001 | `synthetic_complete.json` | A copy the first scraper saved: HTML text, full CIS Controls, MITRE and NIST mappings |
| 90002 | `synthetic_linux_current.json` | A current Linux benchmark: Markdown, profile definitions, Server/Workstation Level 1/2, refs five deep, code blocks, `<placeholder>`s, backslashes |
| 90003 | `synthetic_linux_previous.json` | The previous version of 90002, stored the way earlier versions stored copies (no form fields, `\r\n` line breaks, an HTML artifact title), with no MITRE or NIST; against 90002 it has a recommendation added, removed, renumbered, modified and reformatted |
| 90004 | `synthetic_cloud_foundations.json` | A cloud account's foundations: Level 1/Level 2 only, about half Manual, console steps and CLI commands, links, no NIST, no artifacts |
| 90005 | `synthetic_windows_server.json` | A Windows-style server: Domain Controller/Member Server and Next Generation profiles, refs six deep, registry paths, impact and default value on every recommendation, no parents, MITRE or NIST |

Text for a new synthetic benchmark is written fresh, never adapted from a real one: compare
it with real downloads before committing it, and reword any title or run of words that
matches.

The synthetic benchmarks are prose about passwords, keys and tokens, which a secret scanner
can read as credentials (`sets a password: <command>` was reported as a password); the
documentation's example commands and outputs are the same kind of text.
`.gitguardian.yaml` leaves `tests/fixtures/` and `docs/` out of secret scanning by
`ggshield`, GitGuardian's command-line scanner, and adds no exclusion anywhere else; other
paths stay under the scanner's own settings and limits. GitGuardian's documentation describes
only the filepath exclusions set in its dashboard for its GitHub check, so the same two
folders need excluding there too, linked to this repository (a workspace setting, outside
the repository; a leading `/`, as in `/tests/fixtures/`, anchors a dashboard pattern at the
repository root). Rewording a sentence so that `password` is not followed by an assignment such as
`:` or `=` keeps it from being reported the way the one above was.

`scripts/synthetic_home.py` builds a data folder holding all of them as catalog rows and
downloaded copies, each stored as its file holds it. No session is saved and nothing is sent
to CIS WorkBench. Point `CIS_BENCH_HOME` at the folder to run any command against it:

```bash
uv run python scripts/synthetic_home.py synthetic-home
```

```text
90001  CIS Synthetic Enterprise Platform Benchmark v1.0.0 v1.0.0
90002  CIS Synthetic Linux Server Benchmark v2.0.0
90003  CIS Synthetic Linux Server Benchmark v1.0.0
90004  CIS Synthetic Cloud Foundations Benchmark v3.0.0
90005  CIS Synthetic Windows Server Benchmark v1.0.0

Use it with: CIS_BENCH_HOME=synthetic-home cis-bench list
```

```bash
CIS_BENCH_HOME=synthetic-home cis-bench diff 90003 90002 --format summary
```

```text
Benchmark: CIS Synthetic Linux Server Benchmark
Version:   v1.0.0 → v2.0.0

  ✚ 1 added  ✖ 1 removed  ⟳ 9 modified  ≈ 1 reformatted  ↷ 1 renumbered

Total: 13 recommendations (0 unchanged)
```

The folder must be new or empty; the script never writes into one that holds anything:

```text
$ uv run python scripts/synthetic_home.py synthetic-home
synthetic-home is not an empty folder; give a new or empty one.
```

`tests/e2e/test_synthetic_data.py` builds the folder once and runs the commands over it:
`list`, `cache status`, `search`, every export format and both XCCDF styles for every
benchmark (each export read back in its own format and compared with the benchmark's
recommendations, each XCCDF export through `validate`), and `diff` of the two Linux
versions. It also checks the script's refusals (a folder that holds anything, however
`CIS_BENCH_HOME` would spell it; a file; a blank name) and that each synthetic
recommendation numbers its section and artifacts from its own ref.

---

## Best Practices

1. **Never hardcode paths** - Use fixtures and `tmp_path`; library tests pass values such as `base_url` and `timeout` directly, CLI tests set `CIS_BENCH_*` with `monkeypatch.setenv`
2. **Use tmp_path** - Pytest's built-in temp directory fixture; a CLI test whose command reads or writes relative paths takes the `working_dir` fixture (an empty current directory) instead of `CliRunner.isolated_filesystem`, which Click deprecated in 8.5
3. **Mock external APIs** - Do not hit real CIS WorkBench in tests
4. **Test isolation** - Each test independent
5. **Proper cleanup** - Use fixtures with yield/cleanup

---

## Writing New Tests

### Example Unit Test
```python
def test_database_operation(tmp_path):
"""Test with isolated database."""
with closing(CatalogDatabase(tmp_path / "test.db")) as db:
db.initialize_schema()

# Test operation
db.insert_benchmark({...})

# Verify
result = db.get_benchmark("123")
assert result is not None
```

### Example E2E Test
```python
def test_cli_command(runner):
"""Test CLI command."""
# Environment already set to test
result = runner.invoke(cli, ["catalog", "list"])

# Verify
assert result.exit_code == 0
```

---

## Continuous Integration

Tests run automatically on commit via pre-commit hooks:

- `ruff` - Linting
- `ruff-format` - Code formatting
- `bandit` - Security checks

Full test suite runs in CI/CD (when set up):
```yaml
# .github/workflows/test.yml

- name: Run tests
run: pytest tests/ --cov
```

---

## Test Coverage

Current coverage: 405 tests across:

- 285 original tests (exporters, fetchers, models)
- 41 catalog database tests
- 12 catalog parser tests
- 16 catalog scraper tests
- 21 catalog search tests
- 15 catalog downloader tests
- 15 catalog e2e tests

All tests pass with proper isolation.
