"""
Supabase admin client.
Uses the service_role key — bypasses RLS.
Only used server-side, never exposed to frontend.
"""
import os
from supabase import create_client, Client


def supabase_admin() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
