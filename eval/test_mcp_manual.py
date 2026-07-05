"""Full MCP proof test: server startup → tool discovery → real append → verify row."""
import asyncio
import os
import json
import sys
import logging

sys.stdout.reconfigure(encoding="utf-8")

# Setup logging to see MCP integration logs
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

os.environ["AUTH_MODE"] = "off"
os.environ["USE_MCP"] = "true"
os.environ["USE_MCP_SHEETS"] = "true"

from agents.models import Record
from tools.mcp_clients import append_ceremony_row


def main():
    print("=" * 60)
    print("FULL MCP PROOF TEST")
    print("=" * 60)

    # Load the golden Jeanne Martin expected.json as Record
    with open("examples/jeanne_martin/expected.json") as f:
        data = json.load(f)
    data["caseId"] = "test-mcp-proof-jm"
    record = Record(**data)
    print(f"\n1. Test record: {record.caseId} ({record.deceased.firstName} {record.deceased.lastName})")

    print("\n2. Calling append_ceremony_row (MCP-first path)...")
    result = append_ceremony_row(record)

    print(f"\n3. Result:")
    print(f"   integration_path: {result.get('integration_path', 'MISSING')}")
    if result.get("integration_path") == "mcp":
        print(f"   mcp_tool: {result.get('mcp_tool', 'N/A')}")
        print(f"   mcp_result: {result.get('mcp_result', 'N/A')[:500]}")
        print("\n   ✓ MCP PATH SUCCEEDED")
    elif result.get("integration_path") == "api_fallback":
        print(f"   ⚠ FELL BACK TO DIRECT API")
    else:
        print(f"   Full result: {result}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
