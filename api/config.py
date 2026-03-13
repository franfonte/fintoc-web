"""
GET /api/config
Returns public config needed by the frontend (Fintoc public key).
No auth required — public key is safe to expose.
"""
from http.server import BaseHTTPRequestHandler
import json, os


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "fintoc_public_key":  os.environ["FINTOC_PUBLIC_KEY"],
            "supabase_url":       os.environ["SUPABASE_URL"],
            "supabase_anon_key":  os.environ["SUPABASE_ANON_KEY"],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
