import asyncio
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from google.auth.transport.requests import Request
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agents.auth import get_google_credentials

async def run():
    creds = get_google_credentials()
    # 1. Refresh credentials explicitly
    creds.refresh(Request())
    
    # 2. Handshake & list_tools
    print("--- Gmail MCP Handshake ---")
    params = StreamableHTTPConnectionParams(url='https://gmailmcp.googleapis.com/mcp/v1', headers={'Authorization': f'Bearer {creds.token}'})
    toolset = McpToolset(connection_params=params)
    tools = await toolset.get_tools(None)
    print("Tools discovered:", [t.name for t in tools])
    
    # 3. Try create_draft once
    draft_tool = next(t for t in tools if t.name == 'create_draft')
    args = {'subject': 'MCP probe — ne pas envoyer', 'body': 'test', 'to': ['pere.bernard@example.com']}
    print("--- Calling create_draft ---")
    try:
        res = await draft_tool.run_async(args=args, tool_context=None)
        print("Result:", res)
    except Exception as e:
        print("Exception:", e)

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
