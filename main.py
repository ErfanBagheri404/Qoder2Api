"""Qoder2API - OpenAI-compatible proxy for Qoder (qoder.com).

Interactive menu, same shape as Verdent2API / WorkBuddy2API / ClineDesktop2API.
"""
import argparse
import json
import sys
import time
import webbrowser

import auth as A
import client
from version import __version__

BANNER = r"""
+=====================================================+
|              Qoder2API  v{ver:<6}                  |
|   OpenAI-compatible proxy for Qoder (qoder.com)     |
|   Upstream: api2-v2.qoder.sh/model/v1               |
|   Free model: qwen3.8-flash (0 credits)             |
+=====================================================+
""".format(ver=__version__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 61025


def do_login(interactive=True):
    """Open the device-login URL, poll, save credentials."""
    url, verifier, nonce = client.login_url()
    A.save_auth({**(A.load_auth() or {}),
                 "loginVerifier": verifier, "loginNonce": nonce})
    if interactive:
        print(f"\n  Open this URL and approve the login:\n\n    {url}\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print("  Waiting up to 5 minutes...")
    try:
        creds = client.poll_login(nonce, verifier, timeout=300)
    except TimeoutError:
        print("  Timed out. Nothing saved.")
        return False
    s = A.load_auth() or {}
    s.update(creds)
    s.pop("loginNonce", None)
    s.pop("loginVerifier", None)
    A.save_auth(s)
    if interactive:
        print("  Logged in. Token saved to " + A.AUTH_PATH)
    return True


def cmd_status():
    s = A.load_auth()
    if not s or not s.get("token"):
        print("  Not logged in. Choose option 5 first.")
        return
    tok = client.token()
    print(f"  Logged in : yes (token {tok[:6]}...{tok[-4:]})")
    print(f"  Store     : {A.AUTH_PATH}")
    try:
        info = client.userinfo()
        print(f"  Account   : {info.get('name') or info.get('username')} "
              f"({info.get('email') or ''})")
    except Exception as e:
        print(f"  Account   : fetch failed ({e})")
    try:
        p = client.plan()
        exp = p.get("expiresAt")
        left = (exp - time.time() * 1000) / 86400000 if exp else None
        print(f"  Plan      : {p.get('plan_tier_name')} "
              f"(paid={p.get('is_paid_plan')}, ends in {left:.1f} days)"
              if left is not None else f"  Plan      : {p.get('plan_tier_name')}")
    except Exception as e:
        print(f"  Plan      : fetch failed ({e})")
    try:
        q = client.quota()
        u = q.get("userQuota") or {}
        a = q.get("addOnQuota") or {}
        print(f"  Credits   : {u.get('remaining')}/{u.get('total')} trial, "
              f"{a.get('remaining')}/{a.get('total')} add-on")
        print(f"  Free model: qwen3.8-flash never decrements credits")
    except Exception as e:
        print(f"  Credits   : fetch failed ({e})")


def cmd_models():
    print(f"  {len(client.MODELS)} models:")
    for k, up in client.MODELS.items():
        tag = " [FREE]" if k == "qwen3.8-flash" else ""
        print(f"    - {k} -> {up}{tag}")


def cmd_test_chat():
    if not client.token():
        print("  Not logged in.")
        return
    cmd_models()
    model = input("  Model [qwen3.8-flash]: ").strip() or "qwen3.8-flash"
    msg = input("  Message [Reply with exactly OK]: ").strip() \
        or "Reply with exactly OK"
    body = client.MODELS and {"model": model,
                              "messages": [{"role": "user", "content": msg}],
                              "stream": False, "max_tokens": 512}
    t0 = time.time()
    try:
        r = client.post_chat(body, timeout=120)
        d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"  FAILED: {e}")
        return
    msg0 = (d.get("choices") or [{}])[0].get("message", {})
    u = d.get("usage") or {}
    print(f"  [{time.time()-t0:.1f}s] "
          f"{(msg0.get('content') or '')[:600]}")
    print(f"  usage: prompt={u.get('prompt_tokens')} "
          f"completion={u.get('completion_tokens')}")


def cmd_start_server(host, port, api_key=None, headless=False):
    from server import start_server
    srv = start_server(host, port, api_key=api_key)
    url = f"http://{host}:{port}"
    print("\n  Qoder2API listening")
    print(f"  OpenAI base : {url}/v1")
    print(f"  Models      : {url}/v1/models")
    print(f"  Health      : {url}/healthz")
    print(f"  Quota       : {url}/v1/quota")
    if api_key:
        print("  API key     : (client must send it as Bearer key)")
    print("  Ctrl+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        srv.server_close()


def main():
    ap = argparse.ArgumentParser(prog="Qoder2API")
    ap.add_argument("--no-menu", action="store_true", help="run server directly")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--api-key", default=None,
                    help="require this key on /v1/*")
    ap.add_argument("--login", action="store_true", help="login then exit")
    args = ap.parse_args()

    if args.login:
        do_login()
        return

    if args.no_menu:
        if not client.token():
            print("Not logged in. Run: python main.py --login")
            sys.exit(1)
        cmd_start_server(args.host, args.port, args.api_key, headless=True)
        return

    print(BANNER)
    if not client.token():
        print("  No credentials found.\n")
        print("  Press Enter to open the browser and log in...")
        input()
        if not do_login():
            print("  Press Enter...")
            input()
            return
    while True:
        print("  1. Status")
        print("  2. Start server")
        print("  3. List models")
        print("  4. Test chat")
        print("  5. Re-login")
        print("  6. Quit")
        c = input("\n  > ").strip()
        if c == "1":
            cmd_status()
        elif c == "2":
            cmd_start_server(args.host, args.port, args.api_key)
        elif c == "3":
            cmd_models()
        elif c == "4":
            cmd_test_chat()
        elif c == "5":
            do_login()
        elif c in ("6", "q", "Q"):
            break
    print("  Bye.")


if __name__ == "__main__":
    main()
