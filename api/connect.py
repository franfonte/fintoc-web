"""
POST /api/connect
Called after a user connects their bank via the Fintoc Widget.
Receives the exchange_token, gets the link_token from Fintoc,
stores it in Supabase tied to the authenticated user.
"""
from http.server import BaseHTTPRequestHandler
import json, os, requests
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from _lib.auth import require_user
from _lib.db import supabase_admin

FINTOC_SECRET = os.environ["FINTOC_SECRET_KEY"]
FINTOC_BASE   = "https://api.fintoc.com/v1"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            user_id = require_user(self.headers)
        except PermissionError as e:
            self._json({"error": str(e)}, 401); return

        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length))
        exchange_token = body.get("exchange_token")

        if not exchange_token:
            self._json({"error": "exchange_token required"}, 400); return

        # Exchange token for link_token via Fintoc
        try:
            r = requests.post(
                f"{FINTOC_BASE}/links/exchange",
                headers={"Authorization": FINTOC_SECRET},
                json={"exchange_token": exchange_token},
                timeout=10,
            )
            r.raise_for_status()
            fintoc_link = r.json()
        except Exception as e:
            self._json({"error": f"Fintoc exchange failed: {e}"}, 502); return

        link_token  = fintoc_link.get("link_token") or fintoc_link.get("id")
        institution = (fintoc_link.get("institution") or {}).get("name", "")

        # Save to Supabase
        try:
            sb = supabase_admin()
            # Upsert in case user reconnects same bank
            existing = sb.table("links").select("id").eq("user_id", user_id).eq("link_token", link_token).execute()
            if existing.data:
                link_id = existing.data[0]["id"]
            else:
                res = sb.table("links").insert({
                    "user_id":     user_id,
                    "link_token":  link_token,
                    "institution": institution,
                }).execute()
                link_id = res.data[0]["id"]
        except Exception as e:
            self._json({"error": f"DB error: {e}"}, 500); return

        self._json({"ok": True, "link_id": link_id, "institution": institution})

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
