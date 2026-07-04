"""
Auth gate tests: verify that the application-level Google Sign-In
gate works correctly in both AUTH_MODE=on and AUTH_MODE=off.

Tests:
  1. AUTH_MODE=on: anonymous GET / → 302 /login
  2. AUTH_MODE=on: forged token → 401
  3. AUTH_MODE=on: non-allowlisted email → 403 + French message
  4. AUTH_MODE=on: allowlisted email → session created → access
  5. AUTH_MODE=off: anonymous GET / → 200 (no gate)
  6. /login is always accessible
  7. /auth/logout clears session → redirect /login
"""
import os
import sys
from unittest.mock import patch

# Set up env BEFORE importing the app
from dotenv import load_dotenv
load_dotenv()
os.environ["EXTRACTOR_MODEL"] = os.getenv("WRITER_MODEL", "gemini-2.5-flash")

# Start with AUTH_MODE=on for most tests
os.environ["AUTH_MODE"] = "on"
os.environ["AUTH_ALLOWED_EMAILS"] = "sacristine@example.com"
os.environ["GOOGLE_WEB_CLIENT_ID"] = "test-client-id.apps.googleusercontent.com"
os.environ["SESSION_SECRET"] = "test-secret-key-at-least-32-bytes-long!!"

# NOW import the app (picks up env vars at module level)
from fastapi.testclient import TestClient
import ui.app as app_module

client = TestClient(app_module.app)


def test_auth_mode_on_anonymous_redirect():
    """AUTH_MODE=on: anonymous GET / → 302 /login."""
    # Use a fresh client (no cookies) to simulate anonymous
    c = TestClient(app_module.app, cookies={})
    resp = c.get("/", follow_redirects=False)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
    assert "/login" in resp.headers.get("location", "")
    print("✓ AUTH_MODE=on: anonymous → 302 /login")


def test_auth_mode_on_forged_token():
    """AUTH_MODE=on: forged token → 401."""
    c = TestClient(app_module.app, cookies={})
    resp = c.post("/auth/google", data={"credential": "forged-garbage-token"})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    assert "invalide" in resp.text.lower()
    print("✓ AUTH_MODE=on: forged token → 401")


def test_auth_mode_on_non_allowlisted():
    """AUTH_MODE=on: valid token but non-allowlisted email → 403 + French."""
    c = TestClient(app_module.app, cookies={})

    fake_idinfo = {
        "email": "hacker@evil.com",
        "email_verified": True,
        "aud": "test-client-id.apps.googleusercontent.com",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_idinfo):
        resp = c.post("/auth/google", data={"credential": "valid-looking-token"})
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
    assert "pas autorisé" in resp.text.lower()
    print("✓ AUTH_MODE=on: non-allowlisted email → 403 French")


def test_auth_mode_on_allowlisted():
    """AUTH_MODE=on: allowlisted email → session → access to /."""
    c = TestClient(app_module.app, cookies={})

    fake_idinfo = {
        "email": "sacristine@example.com",
        "email_verified": True,
        "aud": "test-client-id.apps.googleusercontent.com",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_idinfo):
        resp = c.post(
            "/auth/google",
            data={"credential": "valid-token"},
            follow_redirects=False,
        )
    assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
    assert resp.headers.get("location") == "/"

    # Now GET / should work (session cookie is on the client)
    resp2 = c.get("/", follow_redirects=False)
    assert resp2.status_code == 200, f"Expected 200 after login, got {resp2.status_code}"
    print("✓ AUTH_MODE=on: allowlisted email → session → 200")


def test_auth_mode_off_no_gate():
    """AUTH_MODE=off: anonymous GET / → 200 (gate disabled).
    
    We temporarily patch the module-level AUTH_MODE to 'off'.
    """
    original = app_module.AUTH_MODE
    app_module.AUTH_MODE = "off"
    try:
        c = TestClient(app_module.app, cookies={})
        resp = c.get("/", follow_redirects=False)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("✓ AUTH_MODE=off: anonymous → 200 (no gate)")
    finally:
        app_module.AUTH_MODE = original


def test_login_always_accessible():
    """GET /login is accessible even with AUTH_MODE=on."""
    c = TestClient(app_module.app, cookies={})
    resp = c.get("/login")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "Connexion" in resp.text or "connexion" in resp.text.lower()
    print("✓ /login always accessible")


def test_logout_clears_session():
    """GET /auth/logout clears session → redirect /login."""
    c = TestClient(app_module.app, cookies={})

    # Login first
    fake_idinfo = {
        "email": "sacristine@example.com",
        "email_verified": True,
        "aud": "test-client-id.apps.googleusercontent.com",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_idinfo):
        c.post("/auth/google", data={"credential": "valid-token"})

    # Logout
    resp = c.get("/auth/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")

    # GET / should now redirect to /login again
    resp2 = c.get("/", follow_redirects=False)
    assert resp2.status_code == 302
    assert "/login" in resp2.headers.get("location", "")
    print("✓ /auth/logout clears session → redirect /login")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== AUTH GATE TESTS ===\n")

    test_auth_mode_on_anonymous_redirect()
    test_auth_mode_on_forged_token()
    test_auth_mode_on_non_allowlisted()
    test_auth_mode_on_allowlisted()
    test_auth_mode_off_no_gate()
    test_login_always_accessible()
    test_logout_clears_session()

    print("\n=== ALL AUTH TESTS PASSED ===")
