---
name: git-commit-formatter
description: Formats every git commit message according to the Conventional Commits specification, with a why-driven body in English. Trigger whenever changes are about to be staged or committed, or when the user asks for a commit message.
---

# Git commit formatter

Adapted from the official Google Antigravity skills tutorial ("Hello World"
skill, Google Cloud Community — rominirani/antigravity-skills), extended with
this project's house rules. The agent acts as the enforcer: no lazy messages
("wip", "fix bug", "update") ever reach the history.

## Rules

1. **Format:** `type(scope): subject`
   Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `ci`, `build`.
   Scope = the area touched (`extractor`, `checker`, `writer`, `ui`, `mcp`,
   `skills`, `specs`, `security`, `eval`).
2. **Subject:** imperative mood, ≤ 72 characters, no trailing period,
   **English only** — for the competition jury who reads this history.
3. **Body — required for any non-trivial change:** explain the **why**, not
   the what (the diff already shows the what). Wrap lines at 72 characters.
   Design decisions and safety behaviours belong here.
4. **One logical change per commit.** If the staged diff mixes concerns,
   propose splitting it before committing.
5. Never mention secrets, tokens, or real personal data in a message.

## Examples

Good:

```
feat(extractor): consolidate multi-page notes into one record

Sacristans take notes across several pages. Merging them in a single
pass lets the checker surface cross-page contradictions (two different
ceremony times) instead of silently keeping the last value read.
```

```
chore(security): add gitleaks pre-commit hook

The repo goes public at submission. A deterministic scan on every
commit is the belt; the agent-side secret-scan skill is the suspenders.
```

Bad: `wip` · `fix stuff` · `update` · any French-only or mixed-language
message · a subject describing the diff line-by-line with no why.
