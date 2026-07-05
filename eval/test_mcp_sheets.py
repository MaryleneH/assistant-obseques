"""
MCP Sheets proof test — verifies the MCP-first integration path.

Three test cases:
  A. MCP happy path: USE_MCP_SHEETS=true, valid service-account
     → assert integration_path == "mcp"
  B. Graceful fallback: MCP path forced to fail (mock)
     → assert integration_path == "api_fallback"
  C. Flag off: USE_MCP_SHEETS=false
     → assert integration_path == "api"

Requires: Node.js (npx), a valid service-account.json, SHEET_ID set.
Marked as OPTIONAL in run_all.py (CI may lack npx).
"""
import os
import sys
import json
import logging
import importlib
from unittest.mock import patch, AsyncMock

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

# Force auth off
os.environ["AUTH_MODE"] = "off"

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s:%(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _reload_mcp_modules():
    """Reload both mcp_flags and mcp_clients to pick up env changes.

    The 'from tools.mcp_flags import use_mcp_sheets' in mcp_clients
    binds the name at import time.  After changing env vars we must
    reload mcp_flags FIRST, then mcp_clients so it re-imports the
    updated function.  Also reset the tool cache.
    """
    import tools.mcp_flags
    import tools.mcp_clients
    importlib.reload(tools.mcp_flags)
    importlib.reload(tools.mcp_clients)
    tools.mcp_clients._sheets_tools = {}
    tools.mcp_clients._sheets_tools_discovered = False


def _build_test_record():
    """Build a minimal Record from the Jeanne Martin fixture.

    Uses run_until_review (extraction + checker), then sets
    humanValidated so the record is ready for append.
    """
    notes_path = os.path.join(
        os.path.dirname(__file__), "..", "examples", "jeanne_martin", "notes.md"
    )
    with open(notes_path, encoding="utf-8") as f:
        notes_text = f.read()

    from agents.orchestrator import run_until_review
    record = run_until_review([notes_text])
    record.security.humanValidated = True
    return record


def test_a_mcp_happy_path():
    """Test A: MCP path actually executes — not a silent fallback."""
    print("\n" + "=" * 60)
    print("  TEST A: MCP happy path (USE_MCP_SHEETS=true)")
    print("=" * 60)

    os.environ["USE_MCP"] = "true"
    os.environ["USE_MCP_SHEETS"] = "true"
    _reload_mcp_modules()

    record = _build_test_record()

    from tools.mcp_clients import append_ceremony_row
    result = append_ceremony_row(record)

    print(f"\n  Result: {json.dumps(result, indent=2, default=str)}")

    assert result is not None, "append_ceremony_row returned None"
    assert result.get("integration_path") == "mcp", (
        f"Expected integration_path='mcp', got '{result.get('integration_path')}'. "
        "MCP path did not execute — check logs above for the error."
    )
    print("  ✓ integration_path == 'mcp' — MCP path executed!")
    return True


def test_b_fallback_on_mcp_failure():
    """Test B: MCP path fails → graceful fallback to direct API.

    Uses a mock to force _append_via_mcp to raise, simulating any
    MCP server failure.  The direct-API credentials remain valid so
    the fallback can actually write the row.
    """
    print("\n" + "=" * 60)
    print("  TEST B: Fallback on MCP failure (mock)")
    print("=" * 60)

    os.environ["USE_MCP"] = "true"
    os.environ["USE_MCP_SHEETS"] = "true"
    _reload_mcp_modules()

    record = _build_test_record()

    # Patch _append_via_mcp to raise — simulates MCP server crash,
    # bad credentials, missing npx, etc.  Direct API stays healthy.
    with patch(
        "tools.mcp_clients._append_via_mcp",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Simulated MCP failure for test"),
    ):
        from tools.mcp_clients import append_ceremony_row
        result = append_ceremony_row(record)

    print(f"\n  Result: {json.dumps(result, indent=2, default=str)}")

    assert result is not None, "append_ceremony_row returned None"
    assert result.get("integration_path") == "api_fallback", (
        f"Expected 'api_fallback', got '{result.get('integration_path')}'"
    )
    print("  ✓ integration_path == 'api_fallback' — graceful fallback!")
    return True


def test_c_flag_off():
    """Test C: Flag off → pure direct API, no MCP attempt."""
    print("\n" + "=" * 60)
    print("  TEST C: Flag off (USE_MCP_SHEETS=false)")
    print("=" * 60)

    os.environ["USE_MCP"] = "true"
    os.environ["USE_MCP_SHEETS"] = "false"
    _reload_mcp_modules()

    record = _build_test_record()

    from tools.mcp_clients import append_ceremony_row
    result = append_ceremony_row(record)

    print(f"\n  Result: {json.dumps(result, indent=2, default=str)}")

    assert result is not None, "append_ceremony_row returned None"
    assert result.get("integration_path") == "api", (
        f"Expected 'api', got '{result.get('integration_path')}'"
    )
    print("  ✓ integration_path == 'api' — no MCP attempt!")
    return True


def main():
    """Run all three MCP Sheets tests."""
    results = {}

    for name, fn in [
        ("A_mcp_happy", test_a_mcp_happy_path),
        ("B_fallback", test_b_fallback_on_mcp_failure),
        ("C_flag_off", test_c_flag_off),
    ]:
        try:
            results[name] = fn()
        except Exception as e:
            logger.error("Test %s exception:", name, exc_info=True)
            print(f"\n  ✗ {name} FAILED: {e}")
            results[name] = False

    print("\n" + "=" * 60)
    print("  MCP SHEETS TEST RESULTS")
    print("=" * 60)

    all_passed = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n  === ALL MCP SHEETS TESTS PASSED ===")
    else:
        print("\n  === SOME TESTS FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
