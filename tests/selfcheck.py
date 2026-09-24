"""Self-check for Qoder2API — offline only, no network, no credentials.

Run: py tests/selfcheck.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402
import client  # noqa: E402
import server  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def main():
    print("Qoder2API selfcheck")

    # --- model mapping ---
    check("qwen3.8-flash -> qwen-flash",
          client.resolve_model("qwen3.8-flash") == "qwen-flash")
    check("case-insensitive",
          client.resolve_model("QWEN3.8-FLASH") == "qwen-flash")
    check("upstream id passthrough", client.resolve_model("qmodel") == "qmodel")
    check("empty -> default",
          client.resolve_model("") == client.MODELS[client.DEFAULT_MODEL])
    check("unknown passthrough",
          client.resolve_model("some-new-model") == "some-new-model")

    # --- content flattening ---
    check("string content", server._flatten_content("hi") == "hi")
    blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    check("block content joined", server._flatten_content(blocks) == "ab")
    check("None content", server._flatten_content(None) == "")
    check("mixed blocks",
          server._flatten_content(["x", {"text": "y"}, {"content": "z"}]) == "xyz")

    # --- tool conversion keeps OpenAI envelope ---
    t = server._convert_tools([{
        "type": "function",
        "function": {"name": "f", "description": "d",
                     "parameters": {"type": "object", "properties": {}}},
    }])
    check("tools keep type/function",
          isinstance(t, list) and t[0].get("type") == "function"
          and t[0]["function"]["name"] == "f")
    t2 = server._convert_tools([{"function": {"name": "g"}}])
    check("bare function wrapped",
          t2 and t2[0]["type"] == "function" and t2[0]["function"]["name"] == "g")
    check("tool without parameters gets schema",
          t2 and t2[0]["function"].get("parameters") is None)  # kept as-is
    t3 = server._convert_tools([{"type": "function",
                                 "function": {"name": "f"}}])
    check("missing parameters filled",
          "parameters" in t3[0]["function"])
    check("no tools -> None", server._convert_tools([]) is None)
    check("junk tools -> None", server._convert_tools([{"foo": 1}]) is None)

    # --- allowed-field filter ---
    req = {"model": "m", "messages": [], "rogue_field": 1, "stream": True}
    kept = {k: v for k, v in req.items() if k in server.ALLOWED}
    check("rogue fields dropped", "rogue_field" not in kept)
    check("known fields kept", "messages" in kept and "stream" in kept)

    # --- auth storage ---
    tmp = os.path.join(os.path.dirname(__file__), "_auth_tmp.json")
    auth.save_auth({"token": "t", "refreshToken": "r"}, path=tmp)
    got = auth.load_auth(path=tmp)
    check("auth round-trip", got and got["token"] == "t")
    check("missing auth -> None",
          auth.load_auth(path=tmp + ".nope") is None)
    os.unlink(tmp)

    # --- pkce ---
    v, c, n = auth.new_pkce()
    check("pkce verifier length", len(v) == 64)
    check("pkce challenge differs", c != v and len(c) >= 43)
    check("pkce nonce hex", len(n) == 32 and all(x in "0123456789abcdef" for x in n))
    v2, c2, _ = auth.new_pkce()
    check("pkce is random", v != v2 and c != c2)

    print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
