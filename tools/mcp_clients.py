"""
MCP Clients for Assistant Obsèques.

Provides integration wrappers for Google Sheets, Gmail, and Drive.
Each wrapper follows the MCP-first-with-fallback pattern:

    if flag is ON:
        try MCP server (runtime tool discovery)
    on ANY error:
        log WARNING, fall back to direct Google API SDK

The direct-API implementations are the battle-tested originals.
The MCP path is additive and never changes control flow on failure.
"""
import os
import sys
import logging
import asyncio
import json
import re
import concurrent.futures
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters, get_default_environment
from pathlib import Path

from agents.models import Record
from agents.auth import get_google_credentials
from tools.mcp_flags import use_mcp_sheets

logger = logging.getLogger(__name__)

# ── Module-level caches ──────────────────────────────────────────────
# Discovered MCP tools — populated once per server on first session.
_sheets_tools: Dict[str, Any] = {}
_sheets_tools_discovered: bool = False


# ══════════════════════════════════════════════════════════════════════
#  ASYNC BRIDGE
# ══════════════════════════════════════════════════════════════════════

def _run_async(coro: Any) -> Any:
    """Run an async coroutine from sync code, safe in ANY context.

    - No running loop (normal sync caller, Starlette background thread):
      use asyncio.run(coro).
    - Running loop present (async handler, pytest-asyncio): spin up a
      one-shot worker thread with its own loop.

    Why: Starlette dispatches sync BackgroundTasks in a threadpool (no
    loop), but future callers might be async.  asyncio.run() inside a
    running loop raises RuntimeError — the except would swallow it and
    MCP would silently never execute.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop → safe to use asyncio.run
        return asyncio.run(coro)
    # Loop exists → offload to a dedicated thread with its own loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


# ══════════════════════════════════════════════════════════════════════
#  MCP SHEETS — SESSION, DISCOVERY, TOOL SELECTION, SCHEMA MAPPING
# ══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def _sheets_mcp_session():
    """Open an MCP stdio session to @mcp-z/mcp-sheets.

    On first call: discovers tools via list_tools() and caches them.
    Catches FileNotFoundError (missing npx) and re-raises clearly.
    """
    global _sheets_tools, _sheets_tools_discovered

    # ── Detect npx binary name (Windows vs *nix) ──
    npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

    # ── Service-account key file — same as the direct-API path ──
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", "./service-account.json")

    # Use the SDK's safe default env (PATH, APPDATA, USERPROFILE, TEMP,
    # SYSTEMROOT, etc.) — NOT full os.environ, which would leak
    # GOOGLE_API_KEY, Langfuse keys, SESSION_SECRET to a community
    # npm server.
    child_env = dict(get_default_environment())

    # ── Windows file:// URI fix ────────────────────────────────────
    # Upstream bug in @mcp-z/mcp-sheets v1.0.7 on Windows + Node v24:
    # config.js:155 builds baseDir = path.join(homedir(), '.mcp-z'),
    # then runtime.js:25 builds tokenStoreUri = `file://${baseDir}/...`.
    # On Windows homedir()='C:\Users\x' → URI = 'file://C:\Users\x\...'.
    # Node URL parser: host='', pathname='/C:/Users/x/...' (leading /),
    # then keyv-registry resolveFilePath passes that to mkdirSync →
    # path.resolve('/C:/Users/x/...') → 'C:\C:\Users\x\...' → ENOENT.
    #
    # Fix: override TOKEN_STORE_URI and RESOURCE_STORE_URI with the
    # file://~ host syntax, which resolveFilePath handles correctly
    # (it expands ~ via os.homedir() then path.join — no double-drive).
    # Also pre-create the target dir as belt-and-suspenders.
    mcp_z_dir = Path.home() / ".mcp-z" / "mcp-sheets"
    mcp_z_dir.mkdir(parents=True, exist_ok=True)
    child_env["TOKEN_STORE_URI"] = "file://~/.mcp-z/mcp-sheets/tokens.json"
    child_env["RESOURCE_STORE_URI"] = "file://~/.mcp-z/mcp-sheets/files"

    child_env["AUTH_MODE"] = "service-account"
    # Upstream bug: @mcp-z/oauth-google v1.0.6 (dep of @mcp-z/mcp-sheets v1.0.7)
    # calls requiredEnv('GOOGLE_CLIENT_ID') in parseConfig()
    # (oauth-google/dist/esm/setup/config.js:134) unconditionally, BEFORE the
    # auth === 'service-account' branch, so the var is validated but never used
    # in SA mode.  Dummy satisfies the check; no OAuth flow ever runs on this path.
    child_env["GOOGLE_CLIENT_ID"] = "unused-in-service-account-mode"
    child_env["GOOGLE_SERVICE_ACCOUNT_KEY_FILE"] = str(
        Path(key_file).resolve()  # absolute native path, never "./relative"
    )

    params = StdioServerParameters(
        command=npx_cmd,
        args=["-y", "@mcp-z/mcp-sheets", "--auth=service-account"],
        env=child_env,
    )

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # ── Tool discovery (once per process) ──
                if not _sheets_tools_discovered:
                    tools_result = await session.list_tools()
                    for tool in tools_result.tools:
                        _sheets_tools[tool.name] = tool
                    _sheets_tools_discovered = True
                    tool_names = list(_sheets_tools.keys())
                    logger.info(
                        "MCP Sheets: discovered %d tools: %s",
                        len(tool_names), tool_names,
                    )

                yield session

    except FileNotFoundError as e:
        raise RuntimeError(
            f"MCP Sheets: '{npx_cmd}' not found — is Node.js installed? ({e})"
        ) from e


def _find_append_tool() -> Any:
    """Select the best append tool from the discovered tools.

    Priority:
      1. Exact name "rows-append"
      2. Any tool whose name contains "append" (prefer one also containing "row")
      3. Raise RuntimeError → triggers fallback

    Logs the selection reason and the tool's full inputSchema.
    """
    if not _sheets_tools:
        raise RuntimeError("MCP Sheets: no tools discovered (empty cache).")

    # 1. Exact match
    if "rows-append" in _sheets_tools:
        tool = _sheets_tools["rows-append"]
        logger.info(
            "MCP Sheets: selected tool 'rows-append' (reason: exact match). "
            "inputSchema=%s",
            json.dumps(tool.inputSchema, indent=2, default=str),
        )
        return tool

    # 2. Fuzzy: contains "append"
    append_tools = {
        name: t for name, t in _sheets_tools.items()
        if "append" in name.lower()
    }
    if append_tools:
        # Prefer one also containing "row"
        row_tools = {
            n: t for n, t in append_tools.items()
            if "row" in n.lower()
        }
        chosen_name, chosen = next(iter(row_tools.items())) if row_tools else next(iter(append_tools.items()))
        reason = "fuzzy match (contains 'append'" + (" + 'row'" if row_tools else "") + ")"
        logger.info(
            "MCP Sheets: selected tool '%s' (reason: %s). inputSchema=%s",
            chosen_name, reason,
            json.dumps(chosen.inputSchema, indent=2, default=str),
        )
        return chosen

    # 3. No match
    raise RuntimeError(
        f"MCP Sheets: no append tool found among: {list(_sheets_tools.keys())}"
    )


def _normalize_key(key: str) -> str:
    """Normalize a JSON property name to snake_case for matching.

    'spreadsheetId' → 'spreadsheet_id', 'sheet_name' → 'sheet_name'
    """
    # Insert underscore before uppercase letters, then lowercase
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return s1.lower().replace("-", "_")


def _map_args_to_schema(
    tool: Any,
    spreadsheet_id: str,
    sheet_gid: str,
    row_data: list,
    headers: list,
) -> Dict[str, Any]:
    """Build call_tool arguments by mapping our values to the tool's inputSchema.

    Reads the tool's inputSchema (JSON Schema dict with 'properties' and
    'required') and maps our semantic values to the ACTUAL property names.
    The actual @mcp-z/mcp-sheets rows-append schema expects:
      id   (str)  — spreadsheet ID
      gid  (str)  — sheet GID (numeric string, first tab is usually '0')
      rows (array) — 2D array of cell values
      headers (array, optional) — column names for blank sheets

    Raises RuntimeError if a required property cannot be mapped.
    """
    schema = tool.inputSchema or {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Candidate values keyed by EXACT property names from the discovered
    # schema, plus normalized aliases for resilience.
    candidates = {
        # Exact matches for @mcp-z/mcp-sheets v1.0.7 rows-append
        "id": spreadsheet_id,
        "gid": sheet_gid,
        "rows": [row_data],            # 2D array: [[cell, cell, ...]]
        "headers": headers,
        # Aliases for other server implementations
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet": spreadsheet_id,
        "sheet_id": sheet_gid,
        "values": [row_data],
        "data": [row_data],
    }

    args: Dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        norm = _normalize_key(prop_name)
        # Try exact normalized match
        if norm in candidates:
            args[prop_name] = candidates[norm]
            continue
        # Try substring match (e.g. 'spreadsheetId' normalized to
        # 'spreadsheet_id' matches candidate 'spreadsheet_id')
        matched = False
        for cand_key, cand_val in candidates.items():
            if cand_key in norm or norm in cand_key:
                args[prop_name] = cand_val
                matched = True
                break
        if not matched and prop_name in required:
            raise RuntimeError(
                f"MCP Sheets: cannot map required property '{prop_name}' "
                f"(normalized: '{norm}'). Schema: {json.dumps(schema, default=str)}"
            )

    logger.debug("MCP Sheets: mapped arguments: %s", json.dumps(args, default=str))
    return args


# ══════════════════════════════════════════════════════════════════════
#  SHARED HELPERS (used by both MCP and direct-API paths)
# ══════════════════════════════════════════════════════════════════════

def _build_row_data(record: Record) -> Tuple[List[str], List[Any]]:
    """Build the headers and row data for the ceremony sheet.

    Returns (headers, row_data).  Both paths call this — identical
    column order guaranteed.
    """
    headers = [
        "caseId", "status", "deceasedName", "deceasedAge",
        "contactName", "contactPhone", "contactEmail",
        "date", "time", "liturgy_json",
    ]
    # record.status may be a CeremonyStatus enum or a plain string
    # (the LLM output path sometimes returns a raw string).
    status_str = record.status.value if hasattr(record.status, "value") else str(record.status)
    row_data = [
        record.caseId,
        status_str,
        (record.deceased.name
         if hasattr(record.deceased, "name")
         else f"{record.deceased.lastName} {record.deceased.firstName}"),
        str(record.deceased.age),
        (record.participants.mainFamilyContact.name
         if record.participants.mainFamilyContact else ""),
        (record.participants.mainFamilyContact.phone
         if record.participants.mainFamilyContact else ""),
        (record.participants.mainFamilyContact.email
         if record.participants.mainFamilyContact else ""),
        record.ceremony.date,
        record.ceremony.time,
        json.dumps(
            [step.model_dump() for step in record.ceremony.liturgySteps],
            ensure_ascii=False,
        ),
    ]
    return headers, row_data


def _resolve_sheet_tab(sheet_id: str) -> str:
    """Resolve the target sheet tab name — identical logic for both paths.

    Checks SHEET_TAB env var first, then queries the Sheets API metadata
    to get the first tab's actual title (handles locale-specific names
    like 'Feuille 1' for French).
    """
    tab = os.getenv("SHEET_TAB")
    if tab:
        return tab

    # Metadata-only call via direct API (1 RPC, ~50ms)
    from googleapiclient.discovery import build

    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if key_file and os.path.isfile(key_file):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
    else:
        import google.auth
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )

    try:
        service = build("sheets", "v4", credentials=creds)
        meta = service.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields="sheets.properties.title",
        ).execute()
        tab_name = meta["sheets"][0]["properties"]["title"]
        logger.info("Sheets: Resolved tab name to '%s'", tab_name)
        return tab_name
    except Exception as e:
        logger.warning("Failed to resolve sheet tab name: %s. Defaulting to 'Sheet1'", e)
        return "Sheet1"


# ══════════════════════════════════════════════════════════════════════
#  MCP APPEND (async)
# ══════════════════════════════════════════════════════════════════════

async def _append_via_mcp(
    record: Record,
    sheet_id: str,
    sheet_gid: str,
    row_data: list,
    headers: list,
) -> Dict[str, Any]:
    """Append a ceremony row via the @mcp-z/mcp-sheets MCP server.

    Opens a stdio session, discovers tools (cached), selects the append
    tool, maps arguments from the discovered inputSchema, and calls it.
    """
    async with _sheets_mcp_session() as session:
        tool = _find_append_tool()
        args = _map_args_to_schema(tool, sheet_id, sheet_gid, row_data, headers)

        logger.info("MCP Sheets: calling tool '%s'...", tool.name)
        result = await session.call_tool(tool.name, arguments=args)

        # Extract a human-readable summary from the MCP result
        result_text = ""
        if hasattr(result, "content") and result.content:
            for block in result.content:
                if hasattr(block, "text"):
                    result_text += block.text
        logger.info("MCP Sheets: tool '%s' returned: %s", tool.name, result_text[:500])

        return {
            "integration_path": "mcp",
            "mcp_tool": tool.name,
            "mcp_result": result_text,
        }


# ══════════════════════════════════════════════════════════════════════
#  PUBLIC API — append_ceremony_row (MCP-first with direct-API fallback)
# ══════════════════════════════════════════════════════════════════════

def append_ceremony_row(record: Record) -> Any:
    """Appends a ceremony row to the sacristan's Google Sheet.

    MCP-first with automatic direct-API fallback:
      - If USE_MCP_SHEETS is true, tries the @mcp-z/mcp-sheets server.
      - On ANY error, logs a WARNING and falls back to the direct
        googleapiclient SDK path.
      - Returns a dict with 'integration_path': 'mcp' | 'api_fallback' | 'api'.

    Credentials: service-account (both paths use the same identity).
    """
    from googleapiclient.discovery import build

    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        raise ValueError("SHEET_ID env var must be set for Sheets API.")

    headers, row_data = _build_row_data(record)

    # ── MCP-first path ──────────────────────────────────────────
    if use_mcp_sheets():
        try:
            # MCP schema uses numeric GID, not tab name (default: first tab)
            sheet_gid = os.getenv("SHEET_GID", "0")
            result = _run_async(
                _append_via_mcp(record, sheet_id, sheet_gid, row_data, headers)
            )
            # integration_path already set to "mcp" by _append_via_mcp
            return result
        except Exception as e:
            logger.warning(
                "MCP Sheets failed (%s) — falling back to direct API.",
                e, exc_info=True,
            )

    # ── Direct-API path (original, unchanged logic) ─────────────
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if key_file and os.path.isfile(key_file):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    else:
        import google.auth
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        logger.info("Sheets: Using ambient ADC (no key file).")
    service = build("sheets", "v4", credentials=creds)

    sheet = service.spreadsheets()

    # Resolve tab (reuse shared logic)
    sheet_tab = os.getenv("SHEET_TAB")
    if not sheet_tab:
        try:
            sheet_meta = sheet.get(
                spreadsheetId=sheet_id,
                fields="sheets.properties.title",
            ).execute()
            sheet_tab = sheet_meta["sheets"][0]["properties"]["title"]
            logger.info("Sheets API: Resolved first tab name to '%s'", sheet_tab)
        except Exception as e:
            logger.warning(
                "Failed to resolve sheet tab name: %s. Defaulting to 'Sheet1'", e
            )
            sheet_tab = "Sheet1"

    range_a1 = f"'{sheet_tab}'!A1"
    range_a1_a2 = f"'{sheet_tab}'!A1:A2"

    # Bootstrap headers if the sheet is empty
    logger.info(
        "Sheets API: Checking if sheet %s is empty on tab '%s'...",
        sheet_id, sheet_tab,
    )
    try:
        result = sheet.values().get(
            spreadsheetId=sheet_id, range=range_a1_a2
        ).execute()
        values = result.get("values", [])
    except Exception as e:
        logger.warning("Failed to read sheet: %s. Assuming empty.", e)
        values = []

    if not values:
        logger.info("Sheets API: Sheet appears empty, bootstrapping headers...")
        body = {"values": [headers]}
        sheet.values().append(
            spreadsheetId=sheet_id,
            range=range_a1,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()

    logger.info("Sheets API: Appending ceremony row...")
    body = {"values": [row_data]}
    append_result = sheet.values().append(
        spreadsheetId=sheet_id,
        range=range_a1,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()

    updates = append_result.get("updates", {})
    logger.info("-> SHEETS ROW APPENDED: range=%s", updates.get("updatedRange"))

    # Tag the integration path for telemetry
    updates["integration_path"] = "api_fallback" if use_mcp_sheets() else "api"
    return updates


# ══════════════════════════════════════════════════════════════════════
#  GMAIL DRAFT (direct API only — USE_MCP_GMAIL=false for now)
# ══════════════════════════════════════════════════════════════════════

import base64
from email.message import EmailMessage


def create_gmail_draft(record: Record) -> Any:
    """Creates a Gmail draft for the ceremony preparation email.

    When a .docx déroulé exists (record.communication.documentLink),
    it is attached to the draft so the priest receives a self-sufficient
    email.  The draft is NEVER sent — gmail.compose covers draft
    creation/update; no send scope is requested.

    Fallback behavior: when no recipients are found in the record
    (no priestEmail, no teamEmails), the draft is addressed to
    SACRISTAN_EMAIL — the sacristan's own mailbox — so the deliverable
    always exists. She fills in real recipients at send time.

    Returns a dict with the Gmail API response, a 'fallback_recipient'
    boolean, and an 'attachment' boolean indicating if the .docx was
    attached.
    """
    recipients = []
    if record.communication.priestEmail:
        recipients.append(record.communication.priestEmail)
    if record.communication.teamEmails:
        recipients.extend(record.communication.teamEmails)

    fallback_used = False
    body_text = record.communication.emailBody or ""

    if not recipients:
        # No recipients in the notes — try the sacristan's own mailbox
        sacristan = os.getenv("SACRISTAN_EMAIL", "").strip()
        if not sacristan:
            logger.info(
                "Gmail: No recipients and SACRISTAN_EMAIL is unset. "
                "Skipping draft creation."
            )
            return None

        # The sacristan email must pass the same allowlist as any recipient
        allowed_raw = os.getenv("ALLOWED_EMAILS", "")
        allowed = {e.strip().lower() for e in allowed_raw.split(",") if e.strip()}
        if sacristan.lower() not in allowed:
            logger.info(
                "Gmail: SACRISTAN_EMAIL (%s) is not in ALLOWED_EMAILS. "
                "Skipping draft creation.", sacristan
            )
            return None

        recipients = [sacristan]
        fallback_used = True
        # Prepend a visible warning so the sacristan knows to add real recipients
        body_text = (
            "⚠️ Adresse du prêtre absente des notes — brouillon adressé "
            "à vous-même ; complétez les destinataires avant envoi.\n\n"
            + body_text
        )
        logger.info(
            "Gmail: No recipients in notes — fallback to SACRISTAN_EMAIL (%s).",
            sacristan,
        )

    creds = get_google_credentials()
    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds)

    subject = record.communication.emailSubject

    message = EmailMessage()
    message.set_content(body_text)
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject

    # Attach the .docx déroulé when it exists
    attachment_added = False
    docx_path = record.communication.documentLink
    if docx_path and os.path.isfile(docx_path):
        try:
            with open(docx_path, "rb") as f:
                docx_data = f.read()
            case_id = record.caseId or "ceremony"
            filename = f"deroule_{case_id}.docx"
            message.add_attachment(
                docx_data,
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=filename,
            )
            attachment_added = True
            logger.info("Gmail: Attached %s (%d bytes).", filename, len(docx_data))
        except Exception as att_err:
            logger.warning("Gmail: Failed to attach .docx: %s", att_err)
    else:
        logger.info(
            "Gmail: No .docx to attach (documentLink=%s). "
            "Draft created without attachment.", docx_path
        )

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {"message": {"raw": encoded_message}}

    try:
        logger.info("Gmail: Calling drafts().create()...")
        draft = service.users().drafts().create(
            userId="me", body=create_message
        ).execute()
        logger.info("-> GMAIL DRAFT CREATED: id=%s", draft["id"])
        draft["fallback_recipient"] = fallback_used
        draft["attachment"] = attachment_added
        return draft
    except Exception as e:
        logger.error("Failed to create Gmail draft: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════
#  GOOGLE DOC UPLOAD (direct API only)
# ══════════════════════════════════════════════════════════════════════

def create_deroule_gdoc(record: Record) -> str | None:
    """Upload the .docx déroulé to Google Drive as a native Google Doc.

    Uses the sacristan's own OAuth credentials (same grant as Gmail,
    scope: drive.file).  The document is created IN her Drive — she
    owns it, no sharing step needed.

    Service accounts have no Drive storage of their own (current Google
    policy), so using the SA would fail with storageQuotaExceeded.

    Returns the webViewLink on success, None on failure.
    Never raises — the pipeline must not abort for a Drive hiccup.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from agents.liturgy import french_date

    docx_path = record.communication.documentLink
    if not docx_path or not os.path.isfile(docx_path):
        logger.warning("Drive: No .docx to upload (documentLink=%s).", docx_path)
        return None

    first = record.deceased.firstName or ""
    last = record.deceased.lastName or ""
    name = f"{first} {last}".strip() or "inconnu"
    date_str = french_date(record.ceremony.date or "", capitalize=False)
    doc_title = f"Déroulé — {name}"
    if date_str:
        doc_title += f" — {date_str}"

    try:
        creds = get_google_credentials()
        drive = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": doc_title,
            "mimeType": "application/vnd.google-apps.document",
        }
        media = MediaFileUpload(
            docx_path,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            resumable=True,
        )
        logger.info("Drive: Uploading %s as Google Doc '%s'...", docx_path, doc_title)
        created = drive.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink",
        ).execute()

        file_id = created.get("id")
        web_link = created.get("webViewLink")
        logger.info(
            "-> GDOC CREATED in sacristan's Drive: id=%s, link=%s",
            file_id, web_link,
        )
        return web_link

    except Exception as e:
        logger.error("Drive: Failed to create Google Doc: %s", e, exc_info=True)
        return None
