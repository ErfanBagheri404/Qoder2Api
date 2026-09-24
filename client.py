"""Qoder direct model API client (api2-v2.qoder.sh).

Discovered in the desktop SDK bundle:
  POST https://api2-v2.qoder.sh/model/v1/chat/completions
  Authorization: Bearer <device token>
Plain OpenAI request/response. No COSY envelope needed.
"""

import json
import time
import urllib.error
import urllib.request

from auth import load_auth, save_auth

API_HOST = "https://api2-v2.qoder.sh"
CHAT_PATH = "/model/v1/chat/completions"
PLAN_URL = "https://openapi.qoder.sh/api/v2/user/plan"
USERINFO_URL = "https://openapi.qoder.sh/api/v1/userinfo"
REFRESH_URL = "https://openapi.qoder.sh/api/v1/deviceToken/refresh"
QUOTA_URL = "https://openapi.qoder.sh/api/v2/quota/usage"

UA = "Qoder/1.1.61 (Windows; x64) node/20"

# Model ids accepted by the direct endpoint, verified live.
MODELS = {
    "qwen3.8-flash": "qwen-flash",   # Qwen3.8-Flash; provider qwen3.5-flash
    "qwen3.7-plus": "qmodel",
    "qwen3.5-flash": "qwen-flash",
    "kimi-k2.7-code": "kmodel",
    "deepseek-v4-pro": "dmodel",
    "minimax-m2.5": "mmodel",
}
DEFAULT_MODEL = "qwen3.8-flash"
# Upstream ids pass through unchanged.
PASSTHROUGH = {"qwen-flash", "qmodel", "kmodel", "dmodel", "mmodel"}


def resolve_model(name):
    if not name:
        return MODELS[DEFAULT_MODEL]
    n = name.strip()
    low = n.lower()
    if low in MODELS:
        return MODELS[low]
    if low in PASSTHROUGH:
        return low
    return n


def token(state=None):
    s = state or load_auth()
    if not s:
        return None
    tok = s.get("token") or ""
    if _expired(s):
        tok = _refresh(s) or tok
    return tok or None


def get_token(state=None):
    # Back-compat alias for earlier probes.
    return token(state)


def _expired(s):
    exp = s.get("expiresAt") or 0
    try:
        return bool(exp) and time.time() * 1000 >= float(exp)
    except (TypeError, ValueError):
        return False


def _refresh(s):
    rt = s.get("refreshToken")
    if not rt:
        return None
    verifier = s.get("refreshVerifier") or s.get("loginVerifier")
    data = {"refresh_token": rt}
    if verifier:
        data["verifier"] = verifier
    try:
        req = urllib.request.Request(
            REFRESH_URL, data=json.dumps(data).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    d = j.get("data") or j
    tok = d.get("token") or d.get("access_token") or d.get("accessToken")
    if not tok:
        return None
    s["token"] = tok
    if d.get("refresh_token") or d.get("refreshToken"):
        s["refreshToken"] = d.get("refresh_token") or d.get("refreshToken")
    if d.get("expires_at") or d.get("expiresAt"):
        s["expiresAt"] = d.get("expires_at") or d.get("expiresAt")
    save_auth(s)
    return tok


def _auth_header(tok=None):
    t = tok or token()
    if not t:
        raise RuntimeError("not logged in: run `python qoder2api.py login`")
    return {"Authorization": "Bearer " + t}


def post_chat(body, tok=None, timeout=300):
    """POST to the direct chat endpoint; returns the open HTTP response."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API_HOST + CHAT_PATH, data=data, method="POST")
    for k, v in _auth_header(tok).items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream" if body.get("stream")
                   else "application/json")
    req.add_header("User-Agent", UA)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, tok=None, timeout=30):
    req = urllib.request.Request(url, method="GET")
    for k, v in _auth_header(tok).items():
        req.add_header(k, v)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def plan():
    return get_json(PLAN_URL)


def quota():
    """Credit balances. qwen-flash is free and never decrements these."""
    return get_json(QUOTA_URL)


def userinfo():
    return get_json(USERINFO_URL)


# ---- device login (kept from the COSY-era client; unchanged flow) ----
import os
from urllib.parse import urlencode

from auth import AUTH_BASE, CLIENT_ID, REDIRECT_URI, OPENAPI_BASE, POLL_PATH


def _machine_id():
    home = os.path.expanduser("~")
    p = os.path.join(home, ".qoder", ".auth", "machine_id")
    if os.path.exists(p):
        return open(p, "r", encoding="utf-8").read().strip()
    p2 = os.path.join(home, ".qoder2api-machine-id")
    if os.path.exists(p2):
        return open(p2, "r", encoding="utf-8").read().strip()
    import uuid as _u
    mid = str(_u.uuid4())
    os.makedirs(os.path.dirname(p2), exist_ok=True)
    with open(p2, "w", encoding="utf-8") as f:
        f.write(mid)
    return mid


def login_url():
    from auth import new_pkce
    verifier, challenge, nonce = new_pkce()
    mid = _machine_id()
    q = urlencode({
        "challenge": challenge,
        "challenge_method": "S256",
        "nonce": nonce,
        "machine_id": mid,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    })
    return f"{AUTH_BASE}/device/selectAccounts?{q}", verifier, nonce


def poll_login(nonce, verifier, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = f"{OPENAPI_BASE}{POLL_PATH}?" + urlencode({
            "nonce": nonce, "verifier": verifier, "challenge_method": "S256",
        })
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                st, txt = r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            st, txt = e.code, e.read().decode("utf-8", "replace")
        if st == 200:
            try:
                j = json.loads(txt)
            except Exception:
                j = {}
            data = j.get("data") or j
            tok = (data.get("token") or data.get("access_token")
                   or data.get("accessToken"))
            if tok:
                return {
                    "token": tok,
                    "refreshToken": (data.get("refresh_token")
                                     or data.get("refreshToken") or ""),
                    "refreshTokenExpiresAt": (
                        data.get("refresh_token_expires_at")
                        or data.get("refreshTokenExpiresAt") or ""),
                    "expiresAt": (data.get("expires_at")
                                  or data.get("expiresAt") or ""),
                    "uid": ((data.get("user") or {}).get("uid")
                            or data.get("uid") or ""),
                }
        time.sleep(3)
    raise TimeoutError("login timed out; run login again")
