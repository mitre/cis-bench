# Security Policy

## Reporting Security Issues

The MITRE SAF team takes security seriously. If you discover a security vulnerability in CIS Benchmark CLI, please report it responsibly.

### Contact Information

- **Email**: [saf-security@mitre.org](mailto:saf-security@mitre.org)
- **GitHub**: Use the [Security tab](https://github.com/mitre/cis-bench/security) to report vulnerabilities privately

### What to Include

When reporting security issues, please provide:

1. **Description** of the vulnerability
2. **Steps to reproduce** the issue
3. **Potential impact** assessment
4. **Suggested fix** (if you have one)
5. **Version affected** (check with `cis-bench --version`)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Fix Timeline**: Varies by severity

## Security Best Practices

### For Users

- **Keep Updated**: Use the latest version from PyPI (`pip install --upgrade cis-bench`)
- **Secure Credentials**: Never commit browser cookies or authentication tokens
- **Use HTTPS**: Always access CIS WorkBench over HTTPS
- **Review Exports**: Validate XCCDF exports before deploying to production

### For Contributors

- **Dependency Scanning**: Run `uv run bandit` before submitting PRs
- **Credential Handling**: Never log or expose CIS WorkBench session cookies
- **Input Validation**: Sanitize all user inputs and URL parameters
- **Test Security**: Include security tests for new features

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x+  | ✅ Yes    |

## Security Testing

The project includes comprehensive security testing:

```bash
# Run security scan
uv run bandit -c pyproject.toml -r src/cis_bench/

# Check for vulnerable dependencies
uv pip list --outdated

# Run full test suite
uv run pytest tests/
```

## Known Security Considerations

### Browser Cookie Authentication
- CIS Benchmark CLI extracts browser cookies for CIS WorkBench authentication
- Cookies are stored locally in `~/.cis-bench/cookies.json`
- Ensure this file has appropriate permissions (600)
- Never commit this file to version control

### URL Validation
- Browser opening features validate CIS WorkBench URLs
- Only `https://workbench.cisecurity.org` is allowed
- Full executable paths used for subprocess calls

### XML Processing
- XCCDF export uses lxml for XML generation
- Only processes data the tool itself generated
- No external/untrusted XML parsing

### Subprocess Security
- Browser launching uses validated URLs and full executable paths
- No shell=True on Windows (uses webbrowser module)
- All subprocess calls use hardcoded or validated inputs
