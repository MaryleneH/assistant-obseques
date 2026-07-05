"""
MCP feature flags — controls whether integrations use MCP servers
or fall back to direct Google API SDK calls.

Each flag defaults to the value shown below.  Override via env vars.
The MCP path automatically falls back to direct API on ANY error,
so enabling MCP is always safe: worst case = a WARNING log line.

Usage:
    from tools.mcp_flags import use_mcp_sheets, use_mcp_gmail
"""
import os
import logging

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool) -> bool:
    """Read a boolean env var (true/false/1/0, case-insensitive)."""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("true", "1", "yes")


# ── Global kill-switch ──
USE_MCP: bool = _bool_env("USE_MCP", True)

# ── Per-integration flags ──
USE_MCP_SHEETS: bool = _bool_env("USE_MCP_SHEETS", True)
USE_MCP_GMAIL: bool = _bool_env("USE_MCP_GMAIL", False)   # future


def use_mcp_sheets() -> bool:
    """True when Sheets should attempt the MCP path first."""
    return USE_MCP and USE_MCP_SHEETS


def use_mcp_gmail() -> bool:
    """True when Gmail should attempt the MCP path first (future)."""
    return USE_MCP and USE_MCP_GMAIL
