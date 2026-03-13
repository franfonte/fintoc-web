"""
Shared auth helper.
Validates the Supabase JWT sent in the Authorization header.
Uses supabase-py to verify the token server-side.
"""
import os
from supabase import create_client


def require_user(headers) -> str:
    """
    Extracts and validates the Bearer JWT from headers.
    Returns the user_id (UUID string) or raises PermissionError.
    """
    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise PermissionError("Missing Authorization header")

    token = auth_header.removeprefix("Bearer ").strip()

    sb = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_ANON_KEY"],
    )

    try:
        # get_user validates the JWT against Supabase Auth server
        res = sb.auth.get_user(token)
        if not res or not res.user:
            raise PermissionError("Invalid token")
        return res.user.id
    except Exception as e:
        raise PermissionError(f"Auth failed: {e}")
