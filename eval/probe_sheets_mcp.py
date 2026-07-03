import asyncio
import os
import sys
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from dotenv import load_dotenv

async def run():
    # Force load .env properly
    load_dotenv(override=True)
    
    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        print("Error: SHEET_ID not set")
        return
        
    env = os.environ.copy()
    if "GOOGLE_SERVICE_ACCOUNT_KEY_FILE" not in env:
        print("Error: GOOGLE_SERVICE_ACCOUNT_KEY_FILE not in env! Is .env fixed?")
        return

    # Add dummy vars to bypass @mcp-z/oauth-google config validation bug
    if "GOOGLE_CLIENT_ID" not in env:
        env["GOOGLE_CLIENT_ID"] = "dummy"
    if "GOOGLE_CLIENT_SECRET" not in env:
        env["GOOGLE_CLIENT_SECRET"] = "dummy"

    print("--- Sheets MCP Probe ---")
    server_params = StdioServerParameters(
        command="npx.cmd" if os.name == 'nt' else "npx",
        args=["-y", "@mcp-z/mcp-sheets", "--auth=service-account"],
        env=env
    )
    
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            # list_tools
            tools = await session.list_tools()
            print("Tools discovered:", [t.name for t in tools.tools])
            
            # append one probe row
            headers = ["caseId", "status", "probe", "test"]
            print("Appending probe row...")
            result = await session.call_tool("rows-append", arguments={
                "spreadsheetId": sheet_id,
                "range": "Sheet1!A1",
                "values": [headers]
            })
            if result.isError:
                print("Error appending row:", result.content)
            else:
                print("Result:", result.content)

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
