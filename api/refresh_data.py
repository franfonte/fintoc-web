"""
POST /api/refresh_data

Step 3 of the Fintoc lifecycle: triggers a Refresh Intent for every bank
account linked by the authenticated user. Fintoc processes the refresh
asynchronously and fires a webhook when it's done.

CRITICAL auth rule for this endpoint:
  - The Authorization header sent to Fintoc MUST be the user's link_token,
    NOT the global FINTOC_SECRET_KEY.
  - Each link has its own link_token, so we iterate and trigger one Refresh
    Intent per link.

After calling this endpoint, the client should wait for the
`refresh_intent.succeeded` webhook — then call GET /api/movements to
retrieve the updated data.

Fintoc docs: POST /v1/refresh_intents
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json, requests
from http.server import BaseHTTPRequestHandler
from _lib.auth import require_user
from _lib.db   import supabase_admin

FINTOC_BASE = "https://api.fintoc.com/v1"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            user_id = require_user(self.headers)
        except PermissionError as e:
            self._json({"error": str(e)}, 401); return

        sb = supabase_admin()

        # ── Fetch all link_tokens saved for this user ────────────────────────
        # TODO: if you support multiple banks, optionally accept a link_id in
        # the request body to refresh a specific bank only.
        links_res = sb.table("links").select("*").eq("user_id", user_id).execute()
        links     = links_res.data
        if not links:
            self._json({
                "error": "No bank connected yet. Complete the Widget flow first."
            }, 404); return

        refresh_intents = []
        errors          = []

        for link in links:
            link_token  = link["link_token"]
            institution = link.get("institution", "unknown")

            # ── Trigger Refresh Intent ───────────────────────────────────────
            # IMPORTANT: Authorization here is the link_token, NOT the secret key.
            # Fintoc uses the link_token to identify which bank connection to refresh.
            try:
                r = requests.post(
                    f"{FINTOC_BASE}/refresh_intents",
                    headers={"Authorization": link_token},
                    timeout=15,
                )
                r.raise_for_status()
                intent = r.json()
                refresh_intents.append({
                    "institution":       institution,
                    "refresh_intent_id": intent.get("id"),
                    "status":            intent.get("status"),
                })
            except requests.exceptions.HTTPError as e:
                try:
                    fintoc_error = e.response.json()
                except Exception:
                    fintoc_error = e.response.text
                errors.append({"institution": institution, "error": fintoc_error})
            except Exception as e:
                errors.append({"institution": institution, "error": str(e)})

        self._json({
            "ok":              len(refresh_intents) > 0,
            "refresh_intents": refresh_intents,
            "errors":          errors,
            "message": (
                "Fintoc is processing the refresh in the background. "
                "New movements will be saved automatically when the webhook fires."
            ),
        })

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
