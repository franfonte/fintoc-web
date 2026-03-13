"""
POST /api/fintoc_webhook

Step 4 of the Fintoc lifecycle: receives asynchronous webhook events from Fintoc.

CONTRACT: ALWAYS return 200 OK to Fintoc — even when our internal processing
fails. Returning a non-2xx causes Fintoc to retry indefinitely, which will
duplicate inserts and spam logs.

Events handled:
  refresh_intent.succeeded
    → look up the affected link in our DB
    → fetch all new movements from Fintoc (incremental, using `since`)
    → upsert them into Supabase

Fintoc docs:
  Webhooks:   https://docs.fintoc.com/docs/webhooks
  Movements:  GET /v1/accounts/{account_id}/movements
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import json, requests
from http.server import BaseHTTPRequestHandler
from _lib.db import supabase_admin

FINTOC_SECRET = os.environ["FINTOC_SECRET_KEY"]
FINTOC_BASE   = "https://api.fintoc.com/v1"


# ── Fintoc API helpers ────────────────────────────────────────────────────────

def _fetch_accounts(link_token):
    """GET /v1/accounts — returns all accounts for a given link."""
    r = requests.get(
        f"{FINTOC_BASE}/accounts",
        headers={"Authorization": FINTOC_SECRET},
        params={"link_token": link_token},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _fetch_movements(account_id, link_token, since=None):
    """
    GET /v1/accounts/{account_id}/movements

    Fetches all movements for an account, following pagination via the
    HTTP Link response header:  <next_url>; rel="next"

    Args:
        since: ISO date string YYYY-MM-DD — Fintoc only returns movements
               posted on or after this date, making the sync incremental.
    """
    url    = f"{FINTOC_BASE}/accounts/{account_id}/movements"
    params = {"link_token": link_token, "per_page": 300}
    if since:
        params["since"] = since

    all_movements = []
    while url:
        r = requests.get(
            url,
            headers={"Authorization": FINTOC_SECRET},
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        all_movements.extend(r.json())

        # Extract the next page URL from the Link header
        link_header = r.headers.get("link", "")
        url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
        params = {}  # Params are already encoded in the next page URL

    return all_movements


# ── Event handler ─────────────────────────────────────────────────────────────

def _handle_refresh_succeeded(payload):
    """
    Handles the refresh_intent.succeeded event.

    The webhook payload contains a `data` object with the refresh intent
    details, including the Fintoc `link_id` that identifies which bank
    connection was refreshed. We use that to look up the link_token in our
    DB and then fetch + store the new movements.
    """
    data    = payload.get("data", {})
    link_id = data.get("link_id")  # Fintoc's Link ID from the webhook payload

    if not link_id:
        print("[webhook] refresh_intent.succeeded missing link_id — skipping")
        return

    sb = supabase_admin()

    # Look up the internal link record.
    # In Fintoc v1 the link_token == the Link `id`, so we can match directly.
    link_res = sb.table("links").select("*").eq("link_token", link_id).execute()
    if not link_res.data:
        print(f"[webhook] No matching link found for fintoc link_id={link_id}")
        return

    link       = link_res.data[0]
    user_id    = link["user_id"]
    link_token = link["link_token"]
    link_db_id = link["id"]

    # Incremental sync: only fetch movements newer than what we already have
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

    # Build a set of known movement IDs to deduplicate on the same day
    existing_res = sb.table("movements").select("id").eq("user_id", user_id).execute()
    existing_ids = {r["id"] for r in existing_res.data}

    try:
        accounts = _fetch_accounts(link_token)
    except Exception as e:
        print(f"[webhook] Failed to fetch accounts for link {link_db_id}: {e}")
        return

    new_count = 0
    for acc in accounts:
        try:
            movements = _fetch_movements(acc["id"], link_token, since=since)
        except Exception as e:
            print(f"[webhook] Failed to fetch movements for account {acc['id']}: {e}")
            continue

        to_insert = []
        for m in movements:
            if m["id"] in existing_ids:
                continue
            to_insert.append({
                "id":               m["id"],
                "user_id":          user_id,
                "link_id":          link_db_id,
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
                # Pass dicts directly — supabase handles jsonb serialization
                "sender_data":      m.get("sender_account"),
                "recipient_data":   m.get("recipient_account"),
                "raw":              m,
            })
            existing_ids.add(m["id"])

        if to_insert:
            sb.table("movements").insert(to_insert).execute()
            new_count += len(to_insert)

    print(f"[webhook] refresh_intent.succeeded — {new_count} new movements saved for user {user_id}")


# ── HTTP handler ──────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length)) if length else {}
        except json.JSONDecodeError:
            # Malformed payload — still return 200 so Fintoc doesn't retry
            self._ack(); return

        event_type = payload.get("type")
        print(f"[webhook] Received event: {event_type}")

        try:
            if event_type == "refresh_intent.succeeded":
                _handle_refresh_succeeded(payload)
            else:
                # Log unknown events for observability but do not error
                print(f"[webhook] Unhandled event type: {event_type}")
        except Exception as e:
            # Catch all internal errors — NEVER let them surface as a non-200
            print(f"[webhook] Internal error handling {event_type}: {e}")

        # Always acknowledge with 200 OK
        self._ack()

    def _ack(self):
        """Return 200 OK — the only response Fintoc should ever see."""
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
