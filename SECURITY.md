# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | Yes       |

## Reporting a Vulnerability

Please report security vulnerabilities via GitHub Security Advisories or by
email to the maintainers. Do NOT open public issues for security findings.

## Security Controls

- API key authentication required for `/api/v1/admin/*` endpoints.
- Rate limiting: 120 requests/minute per API key.
- Security headers applied to all responses (CSP, HSTS, X-Frame-Options, etc.).
- Centralized error handling — no stack traces exposed to clients.
- Audit logging for auth and admin access events.