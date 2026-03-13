"""
POST /api/link_intent

Step 1 of the Fintoc lifecycle: creates a Link Intent and returns a
widget_token to the frontend so the Fintoc Widget can be opened.

Key rules enforced here:
  - product must be "movements", country "cl"
  - holder_type is "individual" or "business" (validated)
  - internal user identifiers go inside `metadata`, NEVER in `username`
    (`username` is reserved for the bank credential the user types in the Widget)
  - Fintoc HTTP errors are unpacked via e.response.json() for clear diagnostics

Fintoc docs: POST /v1/link_intents
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json, requests
from http.server import BaseHTTPRequestHandler
from _lib.auth import require_user

FINTOC_SECRET = os.environ["FINTOC_SECRET_KEY"]
FINTOC_BASE   = "https://api.fintoc.com/v1"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            user_id = require_user(self.headers)
        except PermissionError as e:
            self._json({"error": str(e)}, 401); return

        # Optional body: { "holder_type": "individual" | "business" }
        length = int(self.headers.get("Content-Length", 0))
        body   = {}
        if length:
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._json({"error": "Invalid JSON body"}, 400); return

        holder_type = body.get("holder_type", "individual")
        if holder_type not in ("individual", "business"):
            self._json({"error": "holder_type must be 'individual' or 'business'"}, 400); return

        # ── Build Fintoc payload ──────────────────────────────────────────────
        # IMPORTANT: internal identifiers MUST live inside `metadata`.
        # Placing them in `username` breaks the Widget auth flow.
        payload = {
            "product":     "movements",
            "country":     "cl",
            "holder_type": holder_type,
            "metadata": {
                "internal_user_id": user_id,
            },
        }

        try:
            r = requests.post(
                f"{FINTOC_BASE}/link_intents",
                headers={"Authorization": FINTOC_SECRET},
                json=payload,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.HTTPError as e:
            # Extract the actual Fintoc error body for clear diagnostics
            try:
                fintoc_error = e.response.json()
            except Exception:
                fintoc_error = e.response.text
            self._json({"error": "Fintoc link_intent creation failed", "detail": fintoc_error}, 502); return
        except Exception as e:
            self._json({"error": f"Request failed: {e}"}, 502); return

        widget_token = data.get("widget_token")
        if not widget_token:
            self._json({"error": "Fintoc did not return a widget_token", "detail": data}, 502); return

        self._json({"widget_token": widget_token})

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()
