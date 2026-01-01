# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of article-extractor seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please do NOT:
- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before we've had a chance to fix it

### Please DO:
1. **Use GitHub's private vulnerability reporting**: Go to the [Security tab](https://github.com/pankaj28843/article-extractor/security/advisories/new) of this repository and click "Report a vulnerability"
2. **Or email us directly**: Send details to pankaj28843@gmail.com with the subject line "SECURITY: article-extractor"

### What to include in your report:
- Type of issue (e.g., XSS, injection, denial of service)
- Full paths of source file(s) related to the issue
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### What to expect:
- **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours
- **Updates**: We will keep you informed of the progress towards a fix
- **Disclosure**: Once the issue is resolved, we will publicly disclose the vulnerability in our release notes
- **Credit**: We will credit you for the discovery (unless you prefer to remain anonymous)

## Security Measures

This project employs several security measures:

### Code Security
- **CodeQL Analysis**: Automated security scanning on every push and PR
- **Dependabot**: Automated dependency updates for security patches
- **Ruff Security Rules**: flake8-bandit security linting rules enabled

### Runtime Security
- **XSS-safe output**: HTML sanitization via JustHTML by default
- **No code execution**: No eval() or exec() calls on user input
- **Minimal dependencies**: Reduced attack surface

### Container Security
- **Non-root user**: Docker images run as non-root by default
- **Minimal base image**: Using slim Python images
- **Multi-platform support**: Verified builds for amd64 and arm64

## Security Features

The library includes built-in security features:
- `safe_markdown=True` (default) ensures XSS-safe Markdown output
- HTML sanitization removes potentially dangerous elements
- No network requests unless explicitly using async fetchers

## Dependency Security

We use GitHub's Dependabot to:
- Automatically create PRs for security updates
- Keep all dependencies up to date
- Monitor for known vulnerabilities in the dependency tree

## Security Updates

Security updates will be released as:
- Patch versions (e.g., 0.1.1 → 0.1.2) for backward-compatible fixes
- Published to PyPI immediately after validation
- Announced in GitHub releases with CVE references if applicable
