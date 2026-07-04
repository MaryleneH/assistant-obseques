"""
Observability module — Langfuse tracing for the orchestrator pipeline.

Opt-in: traces are created ONLY when LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY,
and LANGFUSE_HOST are all set.  Otherwise a lightweight no-op object is returned
so the orchestrator can call the same interface without branching.

PRIVACY DEFAULT: traces carry operational METADATA only (model id, duration,
step count, status).  Note/record CONTENT is never sent unless the env flag
LANGFUSE_TRACE_CONTENT=true is set — intended for fictional dev runs only.
Rationale: the sacristan's notes contain personal family data (names, dates,
topics to avoid); telemetry must never become a data exfiltration channel.
"""
import os
import logging
import time
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── No-op span — same interface as the real context manager ────────────
class _NoOpSpan:
    """Mimics the LangfuseSpan context-manager interface when tracing is off."""

    def update(self, **kwargs: Any) -> None:
        """Accept and discard all keyword arguments."""
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *exc: Any) -> None:
        pass


class _NoOpClient:
    """Mimics the Langfuse client interface when tracing is disabled.

    Every method silently no-ops so the orchestrator never needs to check
    ``if client:`` before tracing calls.
    """

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any):
        """Yield a no-op span."""
        yield _NoOpSpan()

    def start_observation(self, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


# ── Public API ─────────────────────────────────────────────────────────

# Module-level singleton — initialized once by init_telemetry().
_client: Any = None
_content_enabled: bool = False


def init_telemetry() -> Any:
    """Initialize Langfuse if all three env vars are present.

    Returns the client (real or no-op).  Safe to call multiple times;
    the first call wins.
    """
    global _client, _content_enabled

    if _client is not None:
        return _client

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_HOST", "").strip()

    _content_enabled = os.getenv("LANGFUSE_TRACE_CONTENT", "").strip().lower() == "true"

    if not (public_key and secret_key and host):
        logger.info("Langfuse: credentials incomplete — telemetry disabled (no-op).")
        _client = _NoOpClient()
        return _client

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        logger.info("Langfuse: telemetry initialized (host=%s, content=%s).",
                     host, "ON" if _content_enabled else "OFF")
        return _client
    except Exception as e:
        logger.warning("Langfuse: init failed (%s) — falling back to no-op.", e)
        _client = _NoOpClient()
        return _client


def get_client() -> Any:
    """Return the current telemetry client (no-op if uninitialised)."""
    if _client is None:
        return init_telemetry()
    return _client


def content_enabled() -> bool:
    """True when LANGFUSE_TRACE_CONTENT=true — allows sending payloads."""
    return _content_enabled


def safe_metadata(metadata: dict) -> dict:
    """Pass-through: metadata is always safe (no personal content)."""
    return metadata


def safe_input(data: Any) -> Optional[Any]:
    """Return data only if content tracing is enabled, else None."""
    return data if _content_enabled else None


def safe_output(data: Any) -> Optional[Any]:
    """Return data only if content tracing is enabled, else None."""
    return data if _content_enabled else None
