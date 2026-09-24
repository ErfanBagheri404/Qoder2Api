"""Qoder2API - OpenAI-compatible proxy for Qoder (qoder.com).

Usage:
  python qoder2api.py login     # open browser, approve, save token
  python qoder2api.py serve     # start the proxy (default :61025)
  python qoder2api.py status    # show login/plan
  python qoder2api.py test      # one-shot smoke test
"""

import argparse
import json
import os
import sys
import time
import urllib.request

import auth as A
import client

VERSION = "0.1.0"
DEFAULT_PORT = 61025

BANNER = r"""
+=====================================================+
|              Qoder2API  v{ver:<6}                  |
|   OpenAI-compatible proxy for Qoder (qoder.com)     |
|   Upstream: api2-v2.qoder.sh/model/v1               |
+=====================================================+
""".format(ver=VERSION)


def cmd_login():
    url, verifier, nonce = client.login_url()
    A.save_auth({**(A.load_auth() or {}),
                 "loginVerifier": verifier, "loginNonce": nonce})
    print("\nOpen this URL in your browser and approve the login:\n")
    print("  " + url + "\n")
    print("Waiting up to 5 minutes...")
    try:
        creds = client.poll_login(nonce, verifier, timeout=300)
    except TimeoutError:
        print("Timed out. Nothing saved.")
        return 1
    s = A.load_auth() or {}
    s.update(creds)
    s.pop("loginNonce", None)
    s.pop("loginVerifier", None)
    A.save_auth(s)
    print("Logged in. Token saved to " + A.AUTH_PATH)
    return 0


def cmd_status():
    s = A.load_auth()
    if not s or not s.get("token"):
        print("Not logged in. Run: python qoder2api.py login")
        return 1
    tok = client.token()
    print("Token: %s...%s (len %d)" % (tok[:6], tok[-4:], len(tok)))
    try:
        info = client.userinfo()
        print("Account: %s (%s)" % (info.get("name") or info.get("username"),
                                    info.get("email") or ""))
    except Exception as e:
        print("userinfo failed:", e)
    try:
        p = client.plan()
        print("Plan: %s | paid=%s | trial=%s" % (
            p.get("plan_tier_name"), p.get("is_paid_plan"),
            p.get("user_type")))
    except Exception as e:
        print("plan failed:", e)
    return 0


def cmd_serve(port):
    import server
    print(BANNER)
    server.main(port)


def cmd_test():
    body = {"model": "qwen-flash",
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "stream": False, "max_tokens": 32}
    t0 = time.time()
    try:
        r = client.post_chat(body, timeout=120)
        data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print("FAILED:", e)
        return 1
    ch = (data.get("choices") or [{}])[0].get("message", {})
    u = data.get("usage") or {}
    print("OK in %.1fs | content=%r | prompt=%s completion=%s" % (
        time.time() - t0, (ch.get("content") or "")[:60],
        u.get("prompt_tokens"), u.get("completion_tokens")))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="qoder2api",
                                 description="OpenAI-compatible proxy for Qoder")
    ap.add_argument("command", nargs="?", default="serve",
                    choices=["login", "serve", "status", "test"])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    a = ap.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if a.command == "login":
        sys.exit(cmd_login())
    if a.command == "status":
        sys.exit(cmd_status())
    if a.command == "test":
        sys.exit(cmd_test())
    cmd_serve(a.port)


if __name__ == "__main__":
    main()
