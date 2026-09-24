"""Shared constants, PKCE login helpers, and token storage for Qoder2API."""

import base64
import hashlib
import json
import os
import secrets
import string
import uuid

# --- endpoints (prod channel) ---
AUTH_BASE = "https://qoder.com"
OPENAPI_BASE = "https://openapi.qoder.sh"
CLIENT_ID = "732aef47-9cf2-46a2-95fe-4cebb5d0d1fa"
REDIRECT_URI = "qoder-app://"

POLL_PATH = "/api/v1/deviceToken/poll"
REFRESH_PATH = "/api/v1/deviceToken/refresh"
USERINFO_PATH = "/api/v1/userinfo"
PLAN_PATH = "/api/v2/user/plan"

AUTH_PATH = os.path.join(os.path.expanduser("~"), ".qoder2api-auth.json")


def new_pkce():
    """PKCE verifier + S256 challenge + nonce, mirroring the desktop app."""
    alphabet = string.ascii_letters + string.digits + "-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    nonce = uuid.uuid4().hex
    return verifier, challenge, nonce


def load_auth(path=None):
    p = path or AUTH_PATH
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_auth(data, path=None):
    p = path or AUTH_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
