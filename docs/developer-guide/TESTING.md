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
uv run pytest tests/
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

!!! important "Always use `uv run`"
    This project uses `uv` with a local `.venv`. All commands must use `uv run` to ensure the correct environment is used.

### Full Test Suite
```bash
uv run pytest tests/
# 1200+ tests, uses test database automatically
```

### Specific Test Modules
```bash
uv run pytest tests/unit/test_catalog_database.py  # Unit tests
uv run pytest tests/integration/                    # Integration tests
uv run pytest tests/e2e/                            # End-to-end CLI tests
```

### With Coverage
```bash
uv run pytest tests/ --cov=src/cis_bench --cov-report=html
open htmlcov/index.html
```

### Verbose Output
```bash
uv run pytest tests/ -v    # Verbose test names
uv run pytest tests/ -vv   # Very verbose
uv run pytest tests/ -s    # Show print statements
```

---

## Test Organization

### Folder Structure

```
tests/
├── unit/                    # Isolated component tests (sync)
│   ├── test_catalog_tab_pane.py   # Widget bindings, methods
│   └── test_*.py
├── integration/             # Component interaction tests
│   ├── test_main_tui.py           # Async app tests with run_test()
│   └── test_*.py
├── e2e/                     # Full CLI workflow tests
│   └── test_cli_*.py
└── regression/              # Architecture compliance tests
    └── test_*_compliance.py
```

### Unit Tests (`tests/unit/`)

- Test individual functions/classes in isolation
- Use mocks for external dependencies
- Fast (run in < 1 second each)
- Use `tmp_path` fixtures for temporary files/databases
- **Sync only** - no `async def` or `app.run_test()`

**Example: Widget unit tests**
```python
class TestCatalogTabPaneBindings:
    """Test bindings exist (sync, no app context needed)."""

    def test_has_view_binding(self):
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane
        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "v" in binding_keys
```

### Integration Tests (`tests/integration/`)

- Test components working together
- May use real files/databases (in temp locations)
- Test exporters, fetchers, validators
- **Async TUI tests** - use `async with app.run_test()`

**Example: TUI integration tests**
```python
class TestMainTUIStructure:
    """Test app behavior (async, requires app context)."""

    @pytest.mark.asyncio
    async def test_app_has_tabbed_content(self):
        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            tabbed = app.query_one(TabbedContent)
            assert tabbed is not None
```

### E2E Tests (`tests/e2e/`)

- Test complete workflows via CLI
- Use `CliRunner` to invoke commands
- Test user-facing behavior
- Still isolated (test environment)

### Design Decision: Splitting Mixed Test Files

When a test file has both sync (unit) and async (integration) tests, **split them**:

| Test Type | Characteristics | Location |
|-----------|-----------------|----------|
| Sync unit | Method existence, bindings, pure functions | `tests/unit/` |
| Async integration | `app.run_test()`, full widget behavior | `tests/integration/` |

**Example split (TUI tests):**
```
# Before: All in one file
tests/integration/test_main_tui.py  # 39 mixed tests

# After: Split by type
tests/unit/test_catalog_tab_pane.py       # 23 sync unit tests
tests/integration/test_main_tui.py        # 16 async integration tests
```

This pattern:

- Makes unit tests faster (no async overhead)
- Clarifies test purpose
- Follows Python/pytest conventions

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
6. **Separate sync from async** - Don't mix unit and integration tests in one file
7. **Mirror source structure** - `test_catalog_tab_pane.py` tests `catalog/pane.py`
8. **One class per feature area** - Group related tests in test classes

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
  run: uv run pytest tests/ --cov
```

---

## Test Coverage

Current coverage: 1200+ tests across:

- 285 original tests (exporters, fetchers, models)
- 41 catalog database tests
- 12 catalog parser tests
- 16 catalog scraper tests
- 21 catalog search tests
- 15 catalog downloader tests
- 15 catalog e2e tests

All tests pass with proper isolation.
