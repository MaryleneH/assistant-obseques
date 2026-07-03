---
name: secret-scan
description: Runs a secret and personal-data scan before any git commit or push, and blocks if anything is detected. Trigger before staging, committing, pushing, or when preparing the repository to go public.
---

# Secret scan before commit/push

This repository becomes **public at submission** and the product handles
highly sensitive funeral data. Defense is layered:

1. **Deterministic layer (the belt):** a pre-commit hook runs `gitleaks` on
   every commit (see `.pre-commit-config.yaml` at the repo root). This skill
   never replaces it.
2. **Agent layer (the suspenders):** before any commit or push, the agent
   follows the procedure below — even if the hook exists, even in a hurry.

## Procedure

1. Inspect what is about to be committed:
   ```bash
   git status --porcelain
   git diff --staged --stat
   ```
   Red flags: any `.env` file that is not `.env.example`, `*.key`, `*.pem`,
   `service-account*.json`, `credentials*.json`, database dumps, files under
   `data/`.
2. Run the scanner on the staged changes:
   ```bash
   gitleaks protect --staged --redact --verbose
   ```
   Before flipping the repo to public, scan the **entire history** once:
   ```bash
   gitleaks detect --redact --verbose
   ```
3. **Personal-data check (project-specific):** any real-looking name, email,
   or phone number outside the fictional data in `examples/` is a finding too
   (AGENTS.md hard rule 7 — fictional data only).
4. If anything is flagged: **stop**. Do not commit. Report the exact finding
   to the human. Never "fix" a finding by moving the secret to another file
   or encoding it.

## If a secret was already committed

Deleting the file in a new commit is **not** a fix — history keeps it.
Tell the human, in this order:
1. **Revoke / rotate** the credential immediately (assume it is burned).
2. Only then clean the history (or re-create the repo from a clean tree)
   before it ever goes public.
