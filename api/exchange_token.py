"""
POST /api/exchange_token

Step 2 of the Fintoc lifecycle: receives the temporary exchange_token from
the frontend (issued by the Fintoc Widget after the user connects their bank),
exchanges it for a permanent link_token via the Fintoc API, and persists the
mapping (our user_id ↔ link_token) to Supabase.

Security notes:
  - The exchange_token is short-lived and single-use — exchange it immediately.
  - Authorization for the exchange call uses the global FINTOC_SECRET_KEY,
    not the link_token (that only exists after this call succeeds).
  - The link_token is stored server-side and never sent to the browser.

Fintoc docs: GET /v1/links/exchange
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json, requests
from http.server import BaseHTTPRequestHandler
from _lib.auth  import require_user
from _lib.db    import supabase_admin

FINTOC_SECRET = os.environ["FINTOC_SECRET_KEY"]
FINTOC_BASE   = "https://api.fintoc.com/v1"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            user_id = require_user(self.headers)
        except PermissionError as e:
            self._json({"error": str(e)}, 401); return

        length = int(self.headers.get("Content-Length", 0))
        if not length:
            self._json({"error": "Request body required"}, 400); return

        try:
            body = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._json({"error": "Invalid JSON body"}, 400); return

        exchange_token = body.get("exchange_token")
        if not exchange_token:
            self._json({"error": "exchange_token is required"}, 400); return

        # ── Step 1: Exchange the temporary token for a permanent link_token ──
        # Fintoc Exchange endpoint is GET /v1/links/exchange with
        # exchange_token as a query param.
        # Authorization here is the global secret key — the link_token
        # doesn't exist yet at this point in the flow.
        try:
            r = requests.get(
                f"{FINTOC_BASE}/links/exchange",
                headers={"Authorization": FINTOC_SECRET},
                params={"exchange_token": exchange_token},
                timeout=10,
            )
            r.raise_for_status()
            fintoc_link = r.json()
        except requests.exceptions.HTTPError as e:
            # Unpack the real Fintoc error for clear diagnostics
            try:
                fintoc_error = e.response.json()
            except Exception:
                fintoc_error = e.response.text
            self._json({"error": "Fintoc token exchange failed", "detail": fintoc_error}, 502); return
        except Exception as e:
            self._json({"error": f"Request failed: {e}"}, 502); return

        # ── Step 2: Parse the Fintoc response ───────────────────────────────
        # `link_token` is the permanent credential used for all future API calls.
        # `id` is the Fintoc Link ID (also equivalent to the link_token in v1).
        link_token  = fintoc_link.get("link_token") or fintoc_link.get("id")
        institution = (fintoc_link.get("institution") or {}).get("name", "")

        # ── Step 3: Persist the link_token mapped to our user_id ────────────
        # TODO: this is the critical mapping — our user_id ↔ Fintoc link_token.
        # Extend this block to store any additional metadata you need (e.g.
        # account holder name, account type, institution ID).
        try:
            sb = supabase_admin()

            # Upsert in case the user reconnects the same bank account
            existing = (
                sb.table("links")
                .select("id")
                .eq("user_id",    user_id)
                .eq("link_token", link_token)
                .execute()
            )
            if existing.data:
                link_db_id = existing.data[0]["id"]
            else:
                res = sb.table("links").insert({
                    "user_id":     user_id,
                    "link_token":  link_token,
                    "institution": institution,
                }).execute()
                link_db_id = res.data[0]["id"]
        except Exception as e:
            self._json({"error": f"DB error: {e}"}, 500); return

        self._json({
            "ok":          True,
            "link_id":     link_db_id,
            "institution": institution,
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
