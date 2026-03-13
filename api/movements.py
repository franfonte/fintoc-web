"""
GET /api/movements
Returns paginated movements for the authenticated user from Supabase.
Query params: page (default 1), per_page (default 100), type, search,
date_from (YYYY-MM-DD), date_to (YYYY-MM-DD), bank
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
        date_from = qs.get("date_from", [None])[0]
        date_to   = qs.get("date_to",   [None])[0]
        bank      = qs.get("bank",      [None])[0]

        per_page = min(per_page, 300)
        offset   = (page - 1) * per_page

        sb = supabase_admin()

        # Build a link_id -> institution map to enrich each movement with bank data.
        links_res = sb.table("links").select("id,institution").eq("user_id", user_id).execute()
        links = links_res.data or []
        institution_by_link_id = {l["id"]: (l.get("institution") or "Banco desconocido") for l in links}

        query = (
            sb.table("movements")
            .select("id,link_id,amount,currency,post_date,transaction_date,description,type,pending,reference_id,comment,account_name,sender_data,recipient_data", count="exact")
            .eq("user_id", user_id)
            .order("post_date", desc=True)
            .range(offset, offset + per_page - 1)
        )

        if date_from:
            query = query.gte("post_date", f"{date_from}T00:00:00")
        if date_to:
            query = query.lte("post_date", f"{date_to}T23:59:59")

        if bank and bank != "all":
            # Bank filter is resolved through links table institutions.
            matching_link_ids = [lid for lid, inst in institution_by_link_id.items() if inst == bank]
            if matching_link_ids:
                query = query.in_("link_id", matching_link_ids)
            else:
                self._json({
                    "movements": [],
                    "total": 0,
                    "page": page,
                    "per_page": per_page,
                    "available_banks": sorted(set(institution_by_link_id.values())),
                    "stats": {"total_in": 0, "total_out": 0, "count": 0},
                })
                return

        if mov_type and mov_type != "all":
            if mov_type == "other":
                # Exclude the known explicit types server-side so pagination is accurate
                query = query.not_.in_("type", ["transfer", "charge", "deposit"])
            else:
                query = query.eq("type", mov_type)

        if search:
            query = query.ilike("description", f"%{search}%")

        res   = query.execute()
        total = res.count or 0

        # sender_data / recipient_data are jsonb — supabase returns them as dicts.
        # No manual json.loads() needed (that was only required to undo double-encoding).
        movements = []
        for m in (res.data or []):
            m["institution"] = institution_by_link_id.get(m.get("link_id"), "Banco desconocido")
            movements.append(m)

        # Stats — fetches all amounts for this user to compute totals.
        # TODO: replace with a Supabase RPC aggregate function (sum) for large datasets
        #       to avoid pulling every row. Example:
        #       sb.rpc("get_movement_stats", {"p_user_id": user_id}).execute()
        stats_res = sb.table("movements").select("amount").eq("user_id", user_id).execute()
        amounts   = [r["amount"] for r in (stats_res.data or [])]
        total_in  = sum(a for a in amounts if a > 0)
        total_out = sum(a for a in amounts if a < 0)

        self._json({
            "movements": movements,
            "total":     total,
            "page":      page,
            "per_page":  per_page,
            "available_banks": sorted(set(institution_by_link_id.values())),
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
