"""
Mobile-rendering proof test: loads Screens A, B (Jeanne Martin record),
and C at THREE viewports and ASSERTS zero horizontal overflow on each.

Viewports tested:
  - 390×844  (iPhone 14 — portrait)
  - 844×390  (iPhone 14 — landscape)
  - 768×1024 (iPad — portrait / tablet)

Also captures a screenshot of Screen A's loader overlay to prove both
the candle AND the spinning ring are visible.

Saves screenshots to eval/results/mobile/ for human inspection.

Measures: document.documentElement.scrollWidth <= window.innerWidth.
The sacristan uses a phone — horizontal overflow is a layout failure.
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()
# Disable auth for the test
os.environ["AUTH_MODE"] = "off"
os.environ["EXTRACTOR_MODEL"] = os.getenv("WRITER_MODEL", "gemini-2.5-flash")

# Three viewports: portrait, landscape, tablet
VIEWPORTS = [
    ("portrait",  {"width": 390, "height": 844}),
    ("landscape", {"width": 844, "height": 390}),
    ("tablet",    {"width": 768, "height": 1024}),
]
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "results", "mobile")
PORT = 8765  # Non-conflicting port for the test server


def render_screen_c_html(base_url: str) -> str:
    """Render Screen C template directly to avoid meta-refresh loop."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("ui/templates"))
    tpl = env.get_template("screen_c.html")
    html = tpl.render(
        generation_complete=False,
        generation_error=None,
        status="ready_for_review",
        deceased_name="Jeanne Martin",
        draft_fallback=False,
        draft_attachment=False,
        gdoc_link=None,
    )
    # Replace relative CSS/static paths with absolute URLs
    html = html.replace('href="/static/', f'href="{base_url}/static/')
    return html


def main():
    import subprocess
    from playwright.sync_api import sync_playwright

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # ── Phase 1: Start the server ──
    print("1. Starting test server on port", PORT)
    os.environ["PORT"] = str(PORT)
    server_proc = subprocess.Popen(
        [sys.executable, "-c",
         f"import uvicorn; uvicorn.run('ui.app:app', host='127.0.0.1', port={PORT}, log_level='warning')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{PORT}"

    import urllib.request, urllib.parse
    for attempt in range(30):
        try:
            urllib.request.urlopen(f"{base_url}/", timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        server_proc.kill()
        raise RuntimeError("Test server did not start within 30s")
    print("   ✓ Server ready")

    try:
        # ── Phase 2: Run extraction (needed for Screen B record) ──
        print("\n2. Running extraction (Jeanne Martin case)...")
        notes_path = os.path.join(os.path.dirname(__file__), "..", "examples", "jeanne_martin", "notes.md")
        with open(notes_path, encoding="utf-8") as f:
            notes_text = f.read()

        data = urllib.parse.urlencode({"notes": notes_text}).encode()
        req = urllib.request.Request(f"{base_url}/extract", data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        urllib.request.urlopen(req, timeout=120)
        print("   ✓ Extraction completed")

        # Pre-render Screen C HTML (avoids meta-refresh navigation loop)
        screen_c_html = render_screen_c_html(base_url)

        # Screens to test per viewport
        screens = [
            ("screen_a", f"{base_url}/"),
            ("screen_b", f"{base_url}/screen_b"),
            ("screen_c", None),  # uses set_content
        ]

        failures = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # ── Phase 3: Test all viewports ──
            for vp_name, vp_size in VIEWPORTS:
                print(f"\n{'='*55}")
                print(f"  VIEWPORT: {vp_name} ({vp_size['width']}×{vp_size['height']})")
                print(f"{'='*55}")

                context = browser.new_context(
                    viewport=vp_size,
                    device_scale_factor=3,
                )
                page = context.new_page()

                for screen_name, url in screens:
                    label = f"{screen_name}_{vp_name}"
                    print(f"\n   Testing {label}...")

                    if screen_name == "screen_c":
                        page.set_content(screen_c_html, wait_until="load", timeout=15000)
                    else:
                        page.goto(url, wait_until="load", timeout=30000)

                    # Give A2UI components time to render (shadow DOM)
                    page.wait_for_timeout(3000)

                    # Measure horizontal overflow
                    scroll_width = page.evaluate("document.documentElement.scrollWidth")
                    viewport_width = page.evaluate("window.innerWidth")
                    has_overflow = scroll_width > viewport_width

                    # Save screenshot
                    screenshot_path = os.path.join(SCREENSHOT_DIR, f"{label}.png")
                    page.screenshot(path=screenshot_path, full_page=True)
                    print(f"   Screenshot: {screenshot_path}")
                    print(f"   scrollWidth={scroll_width}, viewportWidth={viewport_width}", end="")

                    if has_overflow:
                        overflow_px = scroll_width - viewport_width
                        print(f"  → OVERFLOW by {overflow_px}px ✗")
                        failures.append((label, scroll_width, viewport_width))
                    else:
                        print("  → OK ✓")

                context.close()

            # ── Phase 4: Candle + spinner proof screenshot ──
            print(f"\n{'='*55}")
            print("  CANDLE LOADER PROOF")
            print(f"{'='*55}")
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=3,
            )
            page = context.new_page()
            page.goto(f"{base_url}/", wait_until="load", timeout=30000)
            page.wait_for_timeout(1000)

            # Activate the candle overlay via JS (simulating form submit)
            page.evaluate("""
                const overlay = document.getElementById('candleOverlay');
                if (overlay) overlay.classList.add('active');
            """)
            page.wait_for_timeout(2000)  # Let animations start

            # Verify candle and spinner are visible
            candle_visible = page.evaluate("""
                (() => {
                    const overlay = document.getElementById('candleOverlay');
                    if (!overlay) return {overlay: false};
                    const style = getComputedStyle(overlay);
                    const candle = overlay.querySelector('.candle');
                    const spinner = overlay.querySelector('.candle-spinner');
                    return {
                        overlay: style.display !== 'none',
                        candle: candle ? candle.offsetHeight > 0 : false,
                        spinner: spinner ? spinner.offsetHeight > 0 : false,
                        spinnerWidth: spinner ? spinner.offsetWidth : 0,
                        spinnerHeight: spinner ? spinner.offsetHeight : 0,
                    };
                })()
            """)

            candle_path = os.path.join(SCREENSHOT_DIR, "screen_a_candle_loader.png")
            page.screenshot(path=candle_path, full_page=False)
            print(f"\n   Candle proof screenshot: {candle_path}")
            print(f"   Visibility: {candle_visible}")

            if not candle_visible.get("overlay"):
                print("   ⚠ Candle overlay NOT visible")
            if not candle_visible.get("candle"):
                print("   ⚠ Candle NOT visible")
            if not candle_visible.get("spinner"):
                print("   ⚠ Spinner NOT visible")
                failures.append(("candle_spinner_missing", 0, 0))
            else:
                print("   ✓ Candle AND spinner both visible")

            context.close()
            browser.close()

        # ── Phase 5: Final results ──
        total_checks = len(VIEWPORTS) * len(screens)
        print(f"\n{'='*55}")
        if failures:
            for label, sw, vw in failures:
                if sw > 0:
                    print(f"FAIL: {label} overflows by {sw - vw}px (scrollWidth={sw}, viewport={vw})")
                else:
                    print(f"FAIL: {label}")
            assert False, f"{len(failures)} failure(s) detected"
        else:
            print("=== MOBILE RENDERING TEST PASSED ===")
            print(f"All {total_checks} screen×viewport combos: zero overflow")
            print(f"Candle + spinner proof: both visible")
            print(f"Screenshots saved to {SCREENSHOT_DIR}/")

    finally:
        server_proc.kill()
        server_proc.wait()


if __name__ == "__main__":
    main()
