# ──────────────────────────────────────────────────────────────
# Dockerfile — Assistant Obsèques (Cloud Run)
#
# The container carries BOTH Python 3.13 AND Node LTS because
# the Word déroulé skill shells out to `node` to generate the
# .docx file.  Two-stage build keeps the image reasonably slim.
# ──────────────────────────────────────────────────────────────
FROM python:3.13-slim AS base

# ── System deps + Node LTS (nodesource) ──────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg && \
    # NodeSource setup for Node LTS
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    # Cleanup
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Node deps (docx package for the Word skill) ─────────────
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ── Python deps ──────────────────────────────────────────────
COPY pyproject.toml ./
# Minimal copy so pip can resolve the project metadata
COPY agents/ agents/
COPY tools/ tools/
COPY utils/ utils/
RUN pip install --no-cache-dir .

# ── Application code ─────────────────────────────────────────
COPY skills/ skills/
COPY ui/ ui/
COPY examples/ examples/
COPY integrations/ integrations/

# ── Runtime ──────────────────────────────────────────────────
# Cloud Run injects PORT; default 8002 for local parity
ENV PORT=8080
EXPOSE ${PORT}

# uvicorn serves the FastAPI app; Cloud Run routes traffic here
CMD ["sh", "-c", "uvicorn ui.app:app --host 0.0.0.0 --port ${PORT}"]
