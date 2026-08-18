# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Sentinel, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email **security@sentinel.dev** with details
3. Include: description, steps to reproduce, impact assessment
4. We will respond within 48 hours
5. We will coordinate a fix and disclosure timeline

## Security Measures

### Authentication & Authorization

- **JWT Bearer tokens** for all API endpoints (except `/health`)
- **RBAC** with three roles:
  - `admin`: Full access (rules CRUD, settings, analysis)
  - `analyst`: Analysis and view access
  - `viewer`: Read-only access
- Tokens expire after 60 minutes (configurable via `JWT_EXPIRE_MINUTES`)

### Input Validation

- All API inputs validated via Pydantic models
- Log event fields sanitized before rule evaluation
- SQL injection prevention via parameterized queries (when database is used)
- Path traversal prevention in rule file operations

### Rate Limiting

- Default: 100 requests per 60 seconds per IP
- Configurable via `RATE_LIMIT` and `RATE_WINDOW` environment variables
- Returns `429 Too Many Requests` with `Retry-After` header

### Security Headers

All API responses include:
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security` (production only)
- `Content-Security-Policy` (production only)

### Dependency Security

- **Rust**: `cargo audit` (requires Rust 1.80+)
- **Python**: `pip-audit` — run regularly, fix critical/high vulnerabilities
- **Node.js**: `npm audit` — 0 vulnerabilities as of v1.1
- **Container**: Trivy scanning in CI pipeline

### Secrets Management

- API keys stored in environment variables only
- Never logged or exposed in API responses
- `.env` files in `.gitignore`
- `JWT_SECRET` must be at least 32 characters in production

### Container Security

- All Docker images run as non-root user (`sentinel`)
- Multi-stage builds to minimize image size
- `.dockerignore` prevents sensitive files from being included
- No hardcoded secrets in Dockerfiles

## Security Best Practices for Deployment

1. **Use HTTPS** in production (TLS 1.2+)
2. **Set strong JWT_SECRET**: `openssl rand -base64 32`
3. **Restrict CORS**: Set `CORS_ORIGINS` to your frontend domain only
4. **Enable audit logging**: Set `AUDIT_LOG_ENABLED=true`
5. **Regular updates**: Keep dependencies up to date
6. **Network isolation**: Run in a private network with firewall rules
7. **Monitor alerts**: Set up Prometheus alerting for suspicious activity

## Known Limitations

- Rate limiting is in-memory (not distributed across multiple instances)
- RBAC roles are configured via environment variables (not a database)
- Audit logs are written to local filesystem (not a centralized log store)

These will be addressed in future versions with distributed rate limiting, database-backed RBAC, and centralized logging.
