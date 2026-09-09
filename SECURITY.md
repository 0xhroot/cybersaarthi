# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities. Instead,
report them privately so they can be addressed before disclosure.

How to report:

- Open a **private advisory** on GitHub: the repository's
  **Security → Report a vulnerability** flow, or
- Email the maintainers directly (contact information on the owner profile) if
  private advisonaries are unavailable.

Please include:

- A description of the vulnerability and the potential impact.
- Steps to reproduce, or a minimal proof of concept.
- Affected versions / components (backend API, frontend, a dependency).

We aim to acknowledge receipt within a few business days and will coordinate a
responsible disclosure.

## Supported versions

Security fixes are applied to the current `main` branch and the latest release.
Older release branches are supported on a best-effort basis.

## Security posture

This project is **not** advertised as "100% secure" — no software is. It ships
with defense-in-depth controls (JWT auth, RBAC, case isolation, IDOR guards,
rate-limited login throttling, token revocation, audit logging) that are
continuously reviewed. See [`docs/audit/`](docs/audit/) for the security
audit summary and controls.

## Do not expose secrets

- The real `.env` file is gitignored and must never be committed.
- Only `.env.example` files (non-secret placeholders) are tracked.
- Report any discovered secrets (e.g. a leaked token or credential) to the
  maintainers privately, and rotate the credential after confirmation.
