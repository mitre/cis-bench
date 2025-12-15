# Release Process

This document describes the automated release process for CIS Benchmark CLI using Python Semantic Release.

## Overview

The project uses **python-semantic-release** for fully automated releases, similar to Google's Release Please. Releases are triggered automatically when commits are merged to the main branch.

## Conventional Commits

All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>: <description>

[optional body]

[optional footer]
```

### Commit Types

**Version-bumping types:**

- `feat:` - New feature (triggers **minor** version bump: 1.0.0 → 1.1.0)
- `fix:` - Bug fix (triggers **patch** version bump: 1.0.0 → 1.0.1)
- `BREAKING CHANGE:` - Breaking change in footer (triggers **major** version bump: 1.0.0 → 2.0.0)

**Non-version-bumping types:**

- `docs:` - Documentation changes
- `chore:` - Maintenance tasks
- `refactor:` - Code refactoring
- `test:` - Test changes
- `ci:` - CI/CD changes

### Examples

```bash
# Patch release (1.0.0 → 1.0.1)
git commit -m "fix: resolve XCCDF namespace validation error"

# Minor release (1.0.0 → 1.1.0)
git commit -m "feat: add support for XCCDF 1.3 schema"

# Major release (1.0.0 → 2.0.0)
git commit -m "feat: redesign CLI command structure

BREAKING CHANGE: removed --format flag, use subcommands instead"

# No release
git commit -m "docs: update installation instructions"
```

## Automated Release Workflow

When commits are pushed to `main`:

1. **Analyze Commits** - python-semantic-release reads commit history since last release
2. **Determine Version** - Calculates next version based on commit types
3. **Update Version** - Updates `version` field in `pyproject.toml`
4. **Generate Changelog** - Creates/updates `CHANGELOG.md` with release notes
5. **Create Git Tag** - Tags commit with version (e.g., `v1.0.0`)
6. **GitHub Release** - Creates GitHub release with changelog
7. **Build Package** - Builds wheel and sdist
8. **Publish to PyPI** - Uploads to PyPI via trusted publisher (if release created)

**All of this happens automatically on merge to main.**

## Release Types

### Patch Release (1.0.0 → 1.0.1)

Triggered by commits with types: `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`

```bash
git commit -m "fix: handle missing CIS Controls gracefully"
git push origin main
# Auto-releases v1.0.1
```

### Minor Release (1.0.0 → 1.1.0)

Triggered by commits with type: `feat:`

```bash
git commit -m "feat: add catalog search by platform"
git push origin main
# Auto-releases v1.1.0
```

### Major Release (1.0.0 → 2.0.0)

Triggered by commits with `BREAKING CHANGE:` in footer:

```bash
git commit -m "feat: restructure export command

BREAKING CHANGE: --style flag now required for XCCDF exports"
git push origin main
# Auto-releases v2.0.0
```

## Manual Release (Emergency)

If automation fails or manual release is needed:

```bash
# Install semantic-release
pip install python-semantic-release

# Dry run (see what would happen)
semantic-release version --noop

# Create release
semantic-release version

# Publish to PyPI
semantic-release publish
```

## CI/CD Workflows

### CI Workflow (.github/workflows/ci.yml)

Runs on every push and pull request:

- **Test** - Run pytest across Python 3.8-3.12
- **Lint** - Check code style (black, ruff)
- **Security** - Scan with bandit

### Documentation Workflow (.github/workflows/docs.yml)

Deploys documentation to GitHub Pages:

- Triggered on changes to `docs/` or `mkdocs.yml`
- Builds MkDocs site
- Publishes to gh-pages branch

### Release Workflow (.github/workflows/release.yml)

Automated releases on main branch:

- Analyzes commits since last release
- Bumps version if needed
- Creates GitHub release
- Publishes to PyPI via trusted publisher

## PyPI Trusted Publisher Setup

**One-time setup after creating the GitHub repository:**

1. Go to [PyPI Publishing](https://pypi.org/manage/account/publishing/)
2. Add new pending publisher:

   - **PyPI Project Name:** `cis-bench`
   - **Owner:** `mitre`
   - **Repository:** `cis-bench`
   - **Workflow:** `release.yml`
   - **Environment:** (leave blank)
3. Save

The workflow will automatically publish to PyPI using OIDC (no API tokens needed).

## Version Number Format

Versions follow [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH

1.0.0 → Initial release
1.0.1 → Patch (bug fixes)
1.1.0 → Minor (new features, backward compatible)
2.0.0 → Major (breaking changes)
```

## Checking Current Version

```bash
# In code
cis-bench --version

# From git
git describe --tags

# From PyPI
pip show cis-bench
```

## Troubleshooting

**No release created after merge:**

Check if commits use conventional format:

```bash
git log --oneline -10
```

Commits must start with `feat:`, `fix:`, etc.

**Release failed:**

1. Check [workflow runs](https://github.com/mitre/cis-bench/actions)
2. Verify PyPI trusted publisher is configured
3. Check commit permissions in workflow

**Need to skip release:**

Use commit types that don't trigger releases:

```bash
git commit -m "docs: update README"  # Won't release
git commit -m "chore: update dependencies"  # Won't release
```
