"""
POST /api/link_intent
Creates a Fintoc Link Intent and returns the widget_token needed to open the Widget.
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

        try:
            r = requests.post(
                f"{FINTOC_BASE}/link_intents",
                headers={
                    "Authorization": FINTOC_SECRET,
                    "Content-Type": "application/json",
                },
                json={
                    "product":  "movements",
                    "country":  "cl",
                    "username": user_id,
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self._json({"error": f"Fintoc error: {e}"}, 502); return

        self._json({
            "ok":          True,
            "widget_token": data.get("widget_token"),
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
