# AGENTS.md — Assistant Obsèques

> Contract for any coding agent working in this repo (Antigravity, CLI, etc.).
> Read this first. `specs/` holds the detailed design; this file holds the rules
> that must never be broken.

## What we are building

A **human-in-the-loop** AI assistant that helps a Catholic sacristan turn
free-form / multi-page interview notes into a structured ceremony record, a
sober order of service, a universal prayer, a Google Doc, and a Gmail **draft**.
Track: *Concierge Agents* (Kaggle × Google AI Agents capstone).

**Guiding principle: the AI proposes, the human validates.** Nothing leaves the
system without an explicit human validation step.

## Stack (do not substitute without asking)

- **Language:** Python **3.13, pinned** (`requires-python == 3.13.*`). Keep
  local dev and the Agent Engine deployment runtime on the **same minor
  version**: Agent Engine serializes the agent with cloudpickle, and
  cross-version pickles break. Do not move to 3.14 during the sprint (youngest
  supported runtime; a single missing wheel in a transitive dep costs hours).
- **Agent framework:** Google ADK (multi-agent: 1 orchestrator + 3 sub-agents)
- **Models:** a Gemini **multimodal** model for photo/PDF extraction; a Gemini
  **reasoning** model for the writer. Exact model IDs live in `.env`
  (`EXTRACTOR_MODEL`, `WRITER_MODEL`) — confirm the latest available IDs and
  `europe-west9` availability during the codelab; do **not** hardcode older IDs.
- **Tool interoperability:** **MCP** for Google Docs, Gmail (drafts), Google
  Sheets. **Consume** existing MCP servers — do **not** hand-write Google API
  wrappers.
- **Persistence:** the sacristan's own **Google Sheet** (one row per ceremony).
  No third-party database.
- **Human validation UI:** **A2UI** (fallback: a minimal web screen if A2UI
  blocks — see `specs/architecture.md`).
- **Ceremony deliverable (v1 scope):** runtime skill
  `skills/deroule-obseques/` — one-page A4 Word (.docx) déroulé. Node.js +
  `docx` npm package (the script is ported as-is from a proven personal skill;
  do not rewrite it, wire it).
- **Observability (bonus, time-boxed):** Langfuse via OpenTelemetry, EU region.
- **Deploy / eval:** **Agents CLI** → Agent Engine (Gemini Enterprise Agent
  Platform); LLM-as-judge eval on the fixed Jeanne Martin case.

## Hard rules (non-negotiable)

1. **Never send email.** Gmail integration creates **drafts only**. No
   `gmail.send`, no send scope.
2. **Never invent data.** Missing information → `null` and add it to
   `extraction.missingFields`. Never guess a name, date, email, or reading.
3. **Human validation gate.** No Google Doc, no Gmail draft, no Sheet write may
   happen **before** the human has validated the record in the A2UI screen
   (`security.humanValidated == true`).
4. **Respect `avoidMentioning`.** Topics the family asked to avoid must be
   carried through every agent and must never appear in generated text.
5. **Handwriting is uncertain.** Any field read from a photo/handwriting gets a
   confidence score and is listed in `extraction.needsHumanReview`.
6. **No secrets in code.** Credentials come from environment variables only.
   `.env` is gitignored; only `.env.example` is committed.
7. **Fictional data only.** Tests, examples, demo, and anything committed use
   fictional data (see `examples/jeanne_martin/`). Never commit real personal
   data.
8. **Data minimization.** Do not persist raw photos to the Sheet — store only
   structured fields. EU-region processing is the target.

## Conventions

- **Directory map (two worlds — build-time vs runtime):**
  - `specs/` — the design (this is the source of truth; code is regenerable).
  - `.agent/skills/` — **build-time** skills for the coding agent (engineering
    habits, e.g. keeping a CHANGELOG, running a security review).
  - `agents/` — **runtime** ADK agents (orchestrator + sub-agents).
  - `tools/` — **runtime** custom tool code (e.g. the multimodal photo
    extraction call). MCP-consumed tools (Docs/Gmail/Sheets) are **not** here.
  - `skills/` — **runtime** product skills: `deroule-obseques/` (one-page Word
    order-of-service formatter — rules + ported script, v1 scope).
  - `integrations/mcp/` — MCP server configuration.
  - `ui/` — the A2UI validation screen.
  - `security/`, `eval/`, `examples/`, `docs/`.
- Type hints everywhere. Docstrings on every agent and tool.
- **Comment the *why*** (design decisions, safety behaviours) — the competition
  grades code comments.
- Structured logging; graceful error handling (no bare `except`).
- Verify every imported package actually exists before relying on it.

## Workflow for the coding agent

1. **Plan first, no YOLO.** For any non-trivial task, produce a Task List and an
   Implementation Plan and **wait for human review** before writing code.
2. **One agent / one feature at a time.** Build incrementally; keep the pipeline
   runnable at each step.
3. **Tests/eval before or with code.** The Jeanne Martin case in `examples/` is
   the acceptance contract; wire it into `eval/`.
4. **Human reviews every diff.** Especially imports, error handling, and
   anything touching Gmail, Sheets, or personal data.
