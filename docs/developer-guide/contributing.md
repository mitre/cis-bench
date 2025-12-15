# Contributing

Thank you for contributing to CIS Benchmark CLI!

!!! info "Documentation Path"
**You are here:** Developer Guide > Contributing

- **For architecture:** See [Architecture Overview](architecture.md)
- **For testing:** See [Testing Guide](TESTING.md)
- **For data flow:** See [Data Flow Pipeline](data-flow-pipeline.md)

## Git Workflow

**IMPORTANT: This project uses semantic-release for automated versioning.**

### Branch-Based Development (Required)

**DO NOT commit directly to `main`**. Always work on feature/fix branches:

```bash
# Create a feature branch
git checkout -b feat/add-new-capability

# Or a fix branch
git checkout -b fix/resolve-bug

# Make changes and commit
git commit -m "feat: add new capability"

# Push branch to GitHub
git push origin feat/add-new-capability

# Create Pull Request to main
gh pr create --title "Add new capability" --body "Description..."
```

### Why Branch-Based Development?

- **Semantic-release** runs on `main` and creates version commits
- Working directly on `main` causes constant rebase conflicts
- PRs allow code review before merging to `main`
- Clean git history with automated releases

### Conventional Commits

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature (minor version bump)
- `fix:` - Bug fix (patch version bump)
- `docs:` - Documentation only
- `chore:` - Maintenance tasks
- `refactor:` - Code refactoring
- `test:` - Test changes

## Development Setup

### Prerequisites

- **Python 3.12+** (modern Python)
- **uv** (fast Python package manager)
- Git

### Setup with uv (Recommended)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/mitre/cis-bench.git
cd cis-bench

# Install dependencies (creates .venv automatically)
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install

# Verify setup
uv run pytest tests/
```

### Alternative: Setup with pip

```bash
# Clone repository
git clone https://github.com/mitre/cis-bench.git
cd cis-bench

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify setup
pytest tests/
```

---

## Code Quality Standards

### WE DO NOT COMMIT BROKEN CODE

**Before ANY commit:**

- All tests must pass
- All linting must pass
- No ruff errors
- No bandit security issues

```bash
# Run before committing
pytest tests/
ruff check --fix .
ruff format .
```

Pre-commit hooks enforce this automatically.

---

## Testing Requirements

### Write Tests for ALL Code

**Coverage required:**

- Unit tests for functions/classes
- Integration tests for components
- E2E tests for CLI commands

**Test file naming:**
```
src/cis_bench/catalog/database.py
tests/unit/test_catalog_database.py
```

### Test Isolation

**All tests must use isolated databases:**

- Unit tests: `tmp_path` fixtures
- E2E tests: `CIS_BENCH_ENV=test` (automatic)
- NO touching production data

**See:** [Testing Guide](TESTING.md)

---

## Architecture Principles

### 1. Config-Driven, Not Hardcoded

**DO:**
```yaml
# In YAML config
field_mappings:
new_field:
target_element: "element"
source_field: "field"
```

**DON'T:**
```python
# Hardcoded field list
if field_name == "new_field":
...
```

### 2. Loop Through Config

**DO:**
```python
for field_name, mapping in config.field_mappings.items():
# Process field
```

**DON'T:**
```python
# Manually list fields
process_field("title")
process_field("description")
...
```

### 3. No Direct XCCDF Imports

**DO:**
```python
FieldType = self.get_xccdf_class("IdentType")
```

**DON'T:**
```python
from cis_bench.models.xccdf.xccdf_1_2 import IdentType
```

**Why:** Version-agnostic (supports XCCDF 1.1.4 and 1.2).

---

## Adding Features

### Adding New Export Format

**Example:** Add PDF export

1. Create exporter:
```python
# src/cis_bench/exporters/pdf_exporter.py
class PDFExporter(BaseExporter):
def export(self, benchmark, output_path):
# Generate PDF
pass

def format_name(self):
return "PDF"

def get_file_extension(self):
return "pdf"

ExporterFactory.register("pdf", PDFExporter)
```

2. Add to `__init__.py`:
```python
from . import pdf_exporter
```

3. Write tests:
```python
# tests/unit/test_pdf_exporter.py
def test_pdf_export():
exporter = ExporterFactory.create("pdf")
exporter.export(benchmark, "output.pdf")
assert Path("output.pdf").exists()
```

4. Use:
```bash
cis-bench export benchmark.json --format pdf
```

### Adding New XCCDF Style

See: [How to Add XCCDF Style](how-to-add-xccdf-style.md)

**Summary:**
1. Create `{style}_style.yaml` in configs/
2. Define field mappings
3. No code changes needed!

---

## Coding Standards

### Python Style

- **PEP 8** compliance (enforced by ruff)
- **Type hints** where helpful
- **Docstrings** for all public functions/classes
- **Descriptive names** (no abbreviations)

### Documentation

- **Docstrings:** Google style
- **Comments:** Explain WHY, not WHAT
- **TODOs:** Include issue number

### Commit Messages

Format:
```
type: Short description

Longer explanation if needed.

- Bullet points for changes
- Reference issues: #123

Authored by: Your Name <email@example.com>
```

**Types:**

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `test:` Tests
- `refactor:` Code restructuring
- `chore:` Maintenance

---

## Git Workflow

### Branch Strategy

- `main` - Production-ready code
- Feature branches for new work

### Commit Rules

**ONE CHANGE PER COMMIT:**

- Do not mix features
- Separate logical changes
- Each commit should build

**NEVER:**

- `git add .` or `git add -A`
- Commit without testing
- Commit broken code

**ALWAYS:**
```bash
# Add files specifically
git add file1.py file2.py

# Run tests first
pytest tests/

# Then commit
git commit -m "feat: Add specific feature"
```

---

## Code Review

### Before Submitting PR

- [ ] All tests pass (405+)
- [ ] Ruff linting passes
- [ ] Bandit security scan passes
- [ ] Documentation updated
- [ ] Commit messages clear
- [ ] No debug code left
- [ ] Reviewed own changes

### PR Description

Include:

- What changed
- Why it changed
- How to test
- Related issues

---

## Architecture Compliance

### Tests Enforce Architecture

**Architecture compliance tests will FAIL if you:**

- Hardcode field lists instead of looping config
- Import XCCDF models directly
- Add hardcoded field checks (`if field_name == "title"`)

**See:** `tests/unit/test_architecture_compliance.py`

### Design Documents

**Follow the design:**

- Read design docs before implementing
- Do not improvise or "improve"
- If design is wrong, update design FIRST, then code

---

## Development Environment

### Recommended Setup

```bash
# Use dev environment
export CIS_BENCH_ENV=dev

# Your work goes to ~/.cis-bench-dev/
# Production stays clean
```

### Running Tests

```bash
# All tests
pytest tests/

# Specific module
pytest tests/unit/test_catalog_database.py

# With coverage
pytest tests/ --cov=src/cis_bench

# Verbose
pytest tests/ -v
```

---

## Release Process

(When maintainer releases):

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Run full test suite
4. Tag release: `git tag v1.0.0`
5. Build: `python -m build`
6. Publish: `twine upload dist/*`

---

## Getting Help

### Documentation

- Read existing docs in `docs/`
- Check architecture diagrams
- Review YAML config reference

### Ask Questions

- GitHub Discussions
- Issues (for bugs)

### Code of Conduct

Be professional, respectful, and collaborative.

---

## See Also

- [Architecture](architecture.md) - System design
- [Testing Guide](TESTING.md) - Test practices
- [How to Add XCCDF Style](how-to-add-xccdf-style.md) - Extension guide
