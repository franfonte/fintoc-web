"""
POST /api/sync
Fetches only NEW movements from Fintoc (since the latest stored one)
and saves them to Supabase for the authenticated user.
"""
from http.server import BaseHTTPRequestHandler
import json, os, requests
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from _lib.auth import require_user
from _lib.db import supabase_admin

FINTOC_SECRET = os.environ["FINTOC_SECRET_KEY"]
FINTOC_BASE   = "https://api.fintoc.com/v1"


def fetch_accounts(link_token):
    r = requests.get(
        f"{FINTOC_BASE}/accounts",
        headers={"Authorization": FINTOC_SECRET},
        params={"link_token": link_token},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def fetch_movements(account_id, link_token, since=None):
    url    = f"{FINTOC_BASE}/accounts/{account_id}/movements"
    params = {"link_token": link_token, "per_page": 300}
    if since:
        params["since"] = since

    all_movements = []
    while url:
        r = requests.get(url, headers={"Authorization": FINTOC_SECRET}, params=params, timeout=20)
        r.raise_for_status()
        all_movements.extend(r.json())
        link_header = r.headers.get("link", "")
        url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
        params = {}
    return all_movements


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            user_id = require_user(self.headers)
        except PermissionError as e:
            self._json({"error": str(e)}, 401); return

        sb = supabase_admin()

        # Get all links for this user
        links_res = sb.table("links").select("*").eq("user_id", user_id).execute()
        links = links_res.data
        if not links:
            self._json({"ok": True, "new": 0, "total": 0, "message": "No bank connected yet"}); return

        # Find latest stored movement date for this user
        latest_res = (
            sb.table("movements")
            .select("post_date")
            .eq("user_id", user_id)
            .order("post_date", desc=True)
            .limit(1)
            .execute()
        )
        since = None
        if latest_res.data:
            since = latest_res.data[0]["post_date"][:10]  # YYYY-MM-DD

        # Get existing movement IDs to avoid duplicates
        existing_res = sb.table("movements").select("id").eq("user_id", user_id).execute()
        existing_ids = {r["id"] for r in existing_res.data}

        new_count = 0
        errors    = []

        for link in links:
            link_token = link["link_token"]
            link_id    = link["id"]
            try:
                accounts = fetch_accounts(link_token)
            except Exception as e:
                errors.append(str(e)); continue

            for acc in accounts:
                try:
                    movements = fetch_movements(acc["id"], link_token, since=since)
                except Exception as e:
                    errors.append(str(e)); continue

                to_insert = []
                for m in movements:
                    if m["id"] in existing_ids:
                        continue
                    to_insert.append({
                        "id":               m["id"],
                        "user_id":          user_id,
                        "link_id":          link_id,
                        "amount":           m.get("amount", 0),
                        "currency":         m.get("currency", "CLP"),
                        "post_date":        m.get("post_date"),
                        "transaction_date": m.get("transaction_date"),
                        "description":      m.get("description"),
                        "type":             m.get("type"),
                        "pending":          m.get("pending", False),
                        "reference_id":     m.get("reference_id"),
                        "comment":          m.get("comment"),
                        "account_name":     acc.get("name"),
                        # Pass dicts directly — supabase handles jsonb serialization.
                        # Do NOT json.dumps() here: that produces a JSON string inside
                        # a jsonb column (double-encoded), breaking reads.
                        "sender_data":      m.get("sender_account"),
                        "recipient_data":   m.get("recipient_account"),
                        "raw":              m,
                    })
                    existing_ids.add(m["id"])

                if to_insert:
                    sb.table("movements").insert(to_insert).execute()
                    new_count += len(to_insert)

        total_res = sb.table("movements").select("id", count="exact").eq("user_id", user_id).execute()
        total     = total_res.count or 0

        self._json({
            "ok":    not errors or new_count > 0,
            "new":   new_count,
            "total": total,
            "errors": errors,
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
