"""
GET /api/movements
Returns paginated movements for the authenticated user from Supabase.
Query params: page (default 1), per_page (default 100), type, search
"""
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from _lib.auth import require_user
from _lib.db import supabase_admin


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            user_id = require_user(self.headers)
        except PermissionError as e:
            self._json({"error": str(e)}, 401); return

        qs       = parse_qs(urlparse(self.path).query)
        page     = int(qs.get("page",     ["1"])[0])
        per_page = int(qs.get("per_page", ["100"])[0])
        mov_type = qs.get("type",   [None])[0]
        search   = qs.get("search", [None])[0]

        per_page = min(per_page, 300)
        offset   = (page - 1) * per_page

        sb = supabase_admin()

        query = (
            sb.table("movements")
            .select("id,amount,currency,post_date,transaction_date,description,type,pending,reference_id,comment,account_name,sender_data,recipient_data", count="exact")
            .eq("user_id", user_id)
            .order("post_date", desc=True)
            .range(offset, offset + per_page - 1)
        )

        if mov_type and mov_type != "all":
            if mov_type == "other":
                # Supabase doesn't have NOT IN easily, filter client-side on small sets
                pass
            else:
                query = query.eq("type", mov_type)

        if search:
            query = query.ilike("description", f"%{search}%")

        res   = query.execute()
        total = res.count or 0

        # Parse JSON fields
        movements = []
        for m in (res.data or []):
            m["sender_data"]    = json.loads(m["sender_data"])    if m.get("sender_data")    else None
            m["recipient_data"] = json.loads(m["recipient_data"]) if m.get("recipient_data") else None
            if mov_type == "other" and m.get("type") in ("transfer", "charge", "deposit"):
                continue
            movements.append(m)

        # Stats
        stats_res = sb.table("movements").select("amount").eq("user_id", user_id).execute()
        amounts   = [r["amount"] for r in (stats_res.data or [])]
        total_in  = sum(a for a in amounts if a > 0)
        total_out = sum(a for a in amounts if a < 0)

        self._json({
            "movements": movements,
            "total":     total,
            "page":      page,
            "per_page":  per_page,
            "stats": {
                "total_in":  total_in,
                "total_out": abs(total_out),
                "count":     len(amounts),
            },
        })

    def _json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()
