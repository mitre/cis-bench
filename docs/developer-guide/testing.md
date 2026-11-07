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
"""Create temporary catalog database."""
db = CatalogDatabase(tmp_path / "test.db")
db.initialize_schema()
return db
```

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
db = CatalogDatabase(tmp_path / "test.db")
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
