# Troubleshooting

Common issues and solutions.

!!! info "Documentation Path"
    **You are here:** User Guide > Troubleshooting

    - **For configuration:** See [Configuration](configuration.md)
    - **For commands:** See [Commands Reference](commands-reference.md)
    - **For workflows:** See [Workflows](workflows.md)

## Installation Issues

### "Command not found: cis-bench"

**Cause:** The `cis-bench` command is not in your PATH. This is common when using `pip install` instead of the recommended installation methods.

**Solution 1 (Recommended):** Reinstall with pipx or uv
```bash
# Uninstall pip version
pip uninstall cis-bench

# Install properly with pipx (handles PATH correctly)
pipx install cis-bench

# Or with uv
uv tool install cis-bench

# Verify
cis-bench --version
```

**Solution 2:** Use module syntax (always works)
```bash
python -m cis_bench --version
python -m cis_bench download 23598
```

**Solution 3:** Fix your PATH (if you must use pip)
```bash
# Add pip's bin directory to PATH
export PATH="$HOME/.local/bin:$PATH"

# Add to shell config for persistence
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc  # or ~/.zshrc
source ~/.bashrc
```

!!! tip "Why pipx?"
    Per [Python Packaging Authority guidelines](https://packaging.python.org/en/latest/guides/installing-stand-alone-command-line-tools/), CLI tools should be installed with pipx or uv tool, not pip. These tools create isolated environments and handle PATH correctly.

### "No module named 'cis_bench'"

**Cause:** Package not installed, or installed in a different Python environment.

**Solution:**
```bash
# Check which Python
which python
python --version

# Install with same Python
python -m pip install cis-bench

# Or use pipx (recommended)
pipx install cis-bench
```

---

## Authentication Issues

### "Not authenticated" / Login redirect

**Cause:** Not logged into CIS WorkBench in browser.

**Solution:**
1. Open browser
2. Go to https://workbench.cisecurity.org
3. Log in
4. Try CLI command again

### "Failed to extract cookies"

**Cause:** Browser database locked or no cookies found.

**Solutions:**

- Close all browser windows
- Try different browser: `cis-bench auth login --browser firefox`
- Use cookie file instead: `cis-bench auth login --cookies cookies.txt`
- Check you're logged into correct site

### Windows: "requires admin" or permission errors

**Cause:** Chrome 127+ uses App-Bound Encryption on Windows, which requires admin access for cookie extraction.

**Solutions:**

```bash
# Use Firefox instead (works without admin)
cis-bench auth login --browser firefox

# Or export cookies manually and load from file
cis-bench auth login --cookies cookies.txt
```

Firefox doesn't use App-Bound Encryption and works reliably on Windows.

### SSL Certificate Error

**Cause:** A proxy that re-signs TLS traffic, or a missing corporate CA in the trust store.

**Default:** Verification is on (`CIS_BENCH_VERIFY_SSL` unset or `true`).

**Solutions:**
```bash
# Preferred: trust your proxy's CA bundle
export REQUESTS_CA_BUNDLE=/etc/ssl/corporate-ca-bundle.crt

# Last resort: disable verification for one login
cis-bench auth login --browser chrome --no-verify-ssl

# Or for every command, via environment / ~/.cis-bench/.env
export CIS_BENCH_VERIFY_SSL=false
```

---

## Catalog Issues

### "Catalog not found"

**Cause:** Catalog not initialized.

**Solution:**
```bash
# First authenticate (if not already done)
cis-bench auth login --browser chrome

# Then build the catalog
cis-bench catalog refresh
```

### "No benchmarks found"

**Causes:**

- Search too specific
- Wrong status filter
- Catalog out of date

**Solutions:**
```bash
# Broader search
cis-bench catalog search "linux"

# Try without filters
cis-bench catalog list

# Include archived
cis-bench catalog search "benchmark" --status Archived

# Refresh catalog
cis-bench catalog update
```

### Slow Catalog Refresh

**Normal:** A full refresh takes under a minute: about 80 pages, fetched five at a time in batches of ten with a 2-second pause between batches. Much longer usually means slow responses or retries; run with `-v` to see them.

**Alternatives:**

- Use `catalog update` for quick refresh (~30 sec)
- Test with `--max-pages 5` first
- Shorten the pause between batches with `--rate-limit 1` (less polite to CIS)

---

## Export Issues

### "Unknown transformation"

**Cause:** Transform function not registered.

**Check:**

- Transform name in YAML config
- Function exists in code
- Registered with TransformRegistry

### "No converter registered for _Element"

**Cause:** Trying to serialize lxml Elements directly.

**This is a bug** - report with:

- Which style you're using
- Sample benchmark data

### "HtmlTextType is not derived from HtmlTextWithSubType"

**Cause:** Wrong XCCDF type for element.

**Check:**

- `rule_elements` section in YAML
- Using correct type (HtmlTextType vs HtmlTextWithSubType)
- XCCDF version (1.1.4 vs 1.2)

---

## Download Issues

### "Benchmark not found"

**Cause:** Invalid ID or not in catalog.

**Solutions:**
```bash
# Search first
cis-bench catalog search "name"

# Check ID
cis-bench catalog info 23598

# Refresh catalog
cis-bench catalog update
```

### Download stalls or a recommendation fails to fetch

Every WorkBench request has a timeout (30 seconds to read by default, 10 to
connect) and is retried twice on a timeout, a connection error or a 502/503/504
response. A recommendation that still fails is logged with its URL and
skipped, so a download finishes with fewer recommendations rather than
hanging. Each retry is logged as a warning with the attempt number and the
wait before the next try; `-v` adds the full debug trace around it.

On a slow or lossy connection raise the read timeout:
```bash
export CIS_BENCH_REQUEST_TIMEOUT=90
```

If the same URL keeps failing, open it in a browser while logged in to check
whether WorkBench itself is returning an error for that page.

### "Already up-to-date"

**Not an error** - Benchmark hasn't changed.

**Force re-download:**
```bash
cis-bench catalog download 23598 --force
```

---

## Database Issues

### Catalog Database Locked

**Cause:** Multiple processes accessing database.

**Solution:**

- Close other cis-bench processes
- Wait a moment and retry
- Check for zombie processes: `ps aux | grep cis-bench`

### Catalog Database Corrupted

**Symptoms:**

- Random SQL errors
- Missing data
- Crashes

**Solution:**
```bash
# Backup first
cp ~/.cis-bench/catalog.db ~/.cis-bench/catalog.db.backup

# Rebuild
rm ~/.cis-bench/catalog.db
cis-bench catalog refresh
```

---

## Test Issues

### Tests Polluting Production Database

**Should not happen** - tests use isolated database.

**Check:**
```bash
# Verify test env is set
python3 -c "import os; print(os.getenv('CIS_BENCH_ENV'))"
# Should print: None (when not in tests)

# In tests, should be: test
```

**If tests use production DB:**

- Check `tests/conftest.py` has `test_environment` fixture
- Verify `autouse=True` on fixture

---

## Performance Issues

### Slow Exports

**Normal for large benchmarks:**

- 322 recs to XCCDF: ~5-10 seconds
- Includes metadata generation
- XML serialization
- Post-processing

**If extremely slow (>30 sec):**

- Check --verbose output
- May be issue with specific mapping
- Report with benchmark size

### Slow Search

**FTS5 should be <1ms.**

**If slow:**

- Check database size
- Run `VACUUM` on SQLite
- Rebuild FTS5 index:
```bash
sqlite3 ~/.cis-bench/catalog.db "DELETE FROM benchmarks_fts"
# Then refresh catalog
```

---

## Common Errors

### `ModuleNotFoundError`

**Missing dependency.**

```bash
pip install -e ".[dev]"
```

### `ValidationError` from Pydantic

**Invalid data in benchmark.**

Check:

- Source benchmark JSON
- Required fields present
- Field types correct

### `click.Abort`

**User canceled or error in CLI command.**

**Check preceding error message** for details.

---

## Getting Help

### Enable Verbose Logging

```bash
cis-bench --verbose catalog refresh
```

Shows detailed debug information.

### Check Logs

Logs go to stderr. Redirect to file:
```bash
cis-bench catalog refresh 2> debug.log
```

### Report Issues

https://github.com/mitre/cis-bench/issues

Include:

- Command you ran
- Error message
- `--verbose` output
- Platform (OS, Python version)

---

## See Also

- [Configuration](configuration.md) - Environment settings
- [Commands Reference](commands-reference.md) - All commands
- [Testing Guide](../developer-guide/testing.md) - Testing setup
