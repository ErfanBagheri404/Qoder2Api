# Qoder2API

OpenAI-compatible proxy for [Qoder](https://qoder.com) — use Qoder's models (including the free **Qwen3.8-Flash**) through any OpenAI-compatible client (9router, Hermes, etc.).

Upstream: `https://api2-v2.qoder.sh/model/v1/chat/completions` (plain OpenAI format, direct model endpoint used by the Qoder desktop app).

This is an open-source community project, not affiliated with Qoder.

## Verified models

| Proxy id | Upstream id | Notes |
|---|---|---|
| `qwen3.8-flash` (default) | `qwen-flash` | **Free** — zero credit usage, verified live |
| `qwen3.7-plus` | `qmodel` | trial credits |
| `kimi-k2.7-code` | `kmodel` | trial credits |
| `deepseek-v4-pro` | `dmodel` | trial credits |
| `minimax-m2.5` | `mmodel` | trial credits |

Upstream ids (`qwen-flash`, `qmodel`, …) also work directly. Unknown ids pass through.

## Setup

```bash
pip install cryptography
python qoder2api.py login    # open the printed URL, approve in browser
python qoder2api.py status   # confirm account + plan
python qoder2api.py serve    # proxy on http://127.0.0.1:61025/v1
```

Token is stored in `~/.qoder2api-auth.json` (never commit it). Refresh is automatic via the stored refresh token.

## Endpoints

- `POST /v1/chat/completions` — OpenAI chat, stream + non-stream, tools
- `GET /v1/models` — proxy model list
- `GET /v1/plan` — account plan
- `GET /v1/quota` — credit balances (free model never decrements these)
- `GET /healthz` — `{"ok": true}` when logged in
- `POST /login/url`, `POST /login/poll` — device login for scripted use

## 9router

Add connection: base URL `http://127.0.0.1:61025/v1`, model `qwen3.8-flash` (or any id above). Any API key works; auth is the saved device token.

## Notes

- The app's agent endpoint (`agent_chat_generation`) needs a COSY signed envelope and is slow (~19s first frame). This proxy uses the direct model endpoint instead — first frame in ~5-12s.
- `reasoning_content` in deltas is passed through; clients that ignore unknown delta fields are unaffected.
- `role: tool` messages are folded into `user` turns (`Tool result: ...`) since upstream has no tool role.
- Run `py tests/selfcheck.py` for the offline test suite.
