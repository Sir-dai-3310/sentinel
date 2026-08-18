# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.2.x   | ✅ Yes             |
| 1.1.x   | ✅ Yes             |
| 1.0.x   | ❌ No              |
| < 1.0   | ❌ No              |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security vulnerabilities to **security@sentinel.dev**.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within **48 hours** and coordinate a fix and disclosure timeline.

## Security Measures

- JWT Bearer authentication on all API endpoints
- RBAC with admin/analyst/viewer roles
- Rate limiting (100 req/60s/IP)
- Security headers (CSP, HSTS, X-Frame-Options)
- Non-root Docker containers
- Audit logging for all security events
- Dependency scanning (cargo audit, pip-audit, npm audit)

## Bug Bounty

We do not currently offer a paid bug bounty program, but we deeply appreciate responsible disclosure and will acknowledge contributors in our release notes.
