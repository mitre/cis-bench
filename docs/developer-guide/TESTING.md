# Testing Guide

!!! info "Documentation Path"
**You are here:** Developer Guide > Testing

- **For contributing:** See [Contributing Guide](contributing.md)
- **For architecture:** See [Architecture Overview](architecture.md)

## Test Environment Isolation

This project uses environment-based configuration to ensure tests never pollute production or development data.

### Environments

**Production (default):**
```bash
# No environment variable set
cis-bench catalog refresh
# Uses: ~/.cis-bench/catalog.db
```

**Development:**
```bash
export CIS_BENCH_ENV=dev
cis-bench catalog refresh
# Uses: ~/.cis-bench-dev/catalog.db
```

**Test (automatic in pytest):**
```bash
# Set automatically by pytest fixture
pytest tests/
# Uses: /tmp/cis-bench-test/catalog.db
```

### How It Works

**Config Module:**

- `src/cis_bench/config.py` provides environment-aware paths
- Checks `CIS_BENCH_ENV` environment variable
- Returns appropriate paths based on environment

**Pytest Fixture:**

- `tests/conftest.py` has `test_environment` fixture
- `autouse=True` - applies to all tests automatically
- `scope="session"` - sets once at start
- Sets `CIS_BENCH_ENV=test` for entire test run

**Result:**

- Tests use `/tmp/cis-bench-test/` (ephemeral)
- Dev work uses `~/.cis-bench-dev/` (isolated)
- Production uses `~/.cis-bench/` (safe)

---

## Running Tests

### Full Test Suite
```bash
pytest tests/
# 405 tests, uses test database automatically
```

### Specific Test Modules
```bash
pytest tests/unit/test_catalog_database.py # Unit tests
pytest tests/integration/ # Integration tests
pytest tests/e2e/ # End-to-end CLI tests
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

- Automatically use `/tmp/cis-bench-test/catalog.db`
- No manual setup needed
- Cleaned between test runs

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

1. **Never hardcode paths** - Use fixtures or Config
2. **Use tmp_path** - Pytest's built-in temp directory fixture
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
