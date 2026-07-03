# Security & Privacy

See `specs/architecture.md` and `AGENTS.md` for security requirements.

- **No auto-send** — Gmail drafts only (no send scope).
- **Allowlist + roles** — only allowlisted emails get access. No public access.
- **Data minimization** — structured fields only; no raw photos persisted.
- **EU region** (`europe-west9`, Paris) as processing target (GDPR).
- **Secrets** in env vars only.
