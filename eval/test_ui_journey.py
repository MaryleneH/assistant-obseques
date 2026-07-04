"""
End-to-end UI journey test for Assistant Obsèques.
Tests the full flow: Screen A → Screen B → Validate → Screen C → Download.
Includes security assertions (leak-canary, path traversal, traceback suppression).
Requires the server to be running on localhost:8002 before execution.
"""
import asyncio
import sys
import time
import urllib.request
import urllib.error
import subprocess

from playwright.async_api import async_playwright
import httpx

sys.stdout.reconfigure(encoding='utf-8')


async def verify_security_leaks():
    """Grep static files and templates for credential patterns at test time."""
    print("--- VERIFYING SECURITY LEAKS ---")
    # Search for API key and client_secret patterns in static and template files
    for pattern, folder in [("AIza", "ui\\static"), ("client_secret", "ui\\static"),
                            ("AIza", "ui\\templates"), ("client_secret", "ui\\templates")]:
        result = subprocess.run(
            ["findstr", "/s", "/i", pattern, f"{folder}\\*"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            print(f"LEAK FOUND: '{pattern}' in {folder}: {result.stdout.strip()}")
            sys.exit(1)
    print("Static files and templates are clean.")


async def verify_download_traversal():
    """Confirm the download route rejects client-supplied path traversal attempts."""
    print("--- VERIFYING PATH TRAVERSAL ---")
    async with httpx.AsyncClient() as client:
        res = await client.get("http://localhost:8002/api/download_deroule?path=../../.env")
        if res.status_code not in [404, 202]:
            print(f"Path traversal test failed: expected 404 or 202, got {res.status_code}")
            sys.exit(1)
    print("Path traversal blocked.")


async def verify_no_traceback():
    """Hit a non-existent route; confirm no Python traceback in the response body."""
    print("--- VERIFYING NO TRACEBACK LEAK ---")
    async with httpx.AsyncClient() as client:
        res = await client.get("http://localhost:8002/nonexistent_route_xyz")
        body = res.text.lower()
        if "traceback" in body or "file \"" in body or "exception" in body:
            print(f"Traceback leak detected in error response!")
            sys.exit(1)
    print("No traceback leaked.")


async def verify_response_no_secrets(response):
    """Leak-canary: check every HTTP response body for credential patterns."""
    try:
        body = await response.text()
        for pattern in ["AIza", "client_secret", "GOCSPX"]:
            if pattern in body:
                print(f"LEAK in {response.url}: found '{pattern}'")
                sys.exit(1)
    except Exception:
        pass


async def main():
    await verify_security_leaks()
    await verify_download_traversal()
    await verify_no_traceback()

    print("\n--- VERIFYING UI PIPELINE (Playwright) ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Attach leak-canary to every response
        page.on("response", lambda response: asyncio.create_task(verify_response_no_secrets(response)))

        # Log browser console for debugging
        page.on("console", lambda msg: print(f"  BROWSER [{msg.type}]: {msg.text}"))

        # ── Step 1: Load Screen A, submit minimal notes (BLOCKING case) ──
        print("\n1. Screen A → submit minimal notes (expect BLOCKING)...")
        await page.goto("http://localhost:8002/")
        await page.fill("textarea[name='notes']", "Jeanne Martin")
        await page.click("button[type='submit']", timeout=60000)
        await page.wait_for_url("**/screen_b", timeout=60000)
        await page.wait_for_selector("my-app", state="attached")
        await page.wait_for_function("window.a2ui_processor !== undefined")

        # ── Step 2: Verify 409 on BLOCKING ──
        print("2. Verifying 409 on BLOCKING state...")
        async with page.expect_request("**/api/action") as action_info:
            await page.evaluate("""
                const processor = window.a2ui_processor;
                const surface = processor.model.surfaces.get('actions');
                surface.dispatchAction({ event: { name: 'validate', context: {} } }, 'btn_valider');
            """)
        action_res = await action_info.value
        response = await action_res.response()
        if response.status != 409:
            print(f"Expected 409 on BLOCKING, got {response.status}")
            sys.exit(1)
        print("   ✓ 409 received correctly.")

        # ── Step 3: Multi-surface data merge ──
        print("3. Verifying edited field survival (multi-surface)...")
        await page.evaluate("""
            const processor = window.a2ui_processor;
            const surfaces = Array.from(processor.model.surfaces.values());
            for (const s of surfaces) {
                if (s.id === 'info_generales') {
                    s.dataModel.set('/deceased/firstName', 'MODIFIED_FIRST_NAME');
                }
                if (s.id === 'deroule') {
                    s.dataModel.set('/ceremony/liturgySteps/0/title', 'MODIFIED_GOSPEL');
                }
            }
        """)

        async with page.expect_request("**/api/action") as req_info:
            await page.evaluate("""
                const processor = window.a2ui_processor;
                const surface = processor.model.surfaces.get('actions');
                surface.dispatchAction({ event: { name: 'validate', context: {} } }, 'btn_valider');
            """)

        req = await req_info.value
        payload = req.post_data_json
        surfaces = payload.get('dataModel', {}).get('surfaces', {})

        first_name = surfaces.get('info_generales', {}).get('deceased', {}).get('firstName')
        gospel = surfaces.get('deroule', {}).get('ceremony', {}).get('liturgySteps', [{}])[0].get('title')

        if first_name != 'MODIFIED_FIRST_NAME' or gospel != 'MODIFIED_GOSPEL':
            print(f"   Multi-surface data merge failed! firstName={first_name}, gospel={gospel}")
            sys.exit(1)
        print("   ✓ Multi-surface data merge verified.")

        # ── Step 4: Successful journey (full notes → WARNING → validate → Screen C → download) ──
        print("\n4. Successful journey (full Jeanne Martin notes)...")
        await page.goto("http://localhost:8002/")

        with open("examples/jeanne_martin/notes.md", "r", encoding="utf-8") as f:
            full_notes = f.read()

        await page.fill("textarea[name='notes']", full_notes)
        await page.click("button[type='submit']", timeout=60000)
        await page.wait_for_url("**/screen_b", timeout=60000)
        await page.wait_for_selector("my-app", state="attached")
        await page.wait_for_function("window.a2ui_processor !== undefined")

        # This time the status should be WARNING (not BLOCKING) → validate should succeed
        async with page.expect_response("**/api/action") as action_res_info:
            await page.evaluate("""
                const processor = window.a2ui_processor;
                const surface = processor.model.surfaces.get('actions');
                surface.dispatchAction({ event: { name: 'validate', context: {} } }, 'btn_valider');
            """)

        action_response = await action_res_info.value
        if action_response.status == 409:
            body = await action_response.json()
            print(f"   ✗ Got 409 — should be WARNING not BLOCKING! Detail: {body}")
            sys.exit(1)
        print(f"   ✓ Validation accepted (status {action_response.status}).")

        await page.wait_for_url("**/screen_c", timeout=60000)
        print("   ✓ Redirected to Screen C.")

        # Poll the download route until generation completes (200 with non-empty body)
        print("   Waiting for document generation...")
        max_attempts = 30
        success = False
        for i in range(max_attempts):
            try:
                req = urllib.request.Request("http://localhost:8002/api/download_deroule")
                res = urllib.request.urlopen(req)
                if res.getcode() == 200:
                    data = res.read()
                    if len(data) > 0:
                        print(f"   ✓ Download route returned 200, document size: {len(data)} bytes.")
                        success = True
                        break
            except urllib.error.HTTPError as e:
                if e.code == 202:
                    pass  # Still generating
                else:
                    print(f"   Unexpected HTTP error on download: {e.code}")
            time.sleep(2)

        if not success:
            print("   ✗ Failed to download document after generation!")
            sys.exit(1)

        await browser.close()

    print("\n=== ALL UI JOURNEY TESTS PASSED ===")


if __name__ == '__main__':
    asyncio.run(main())
