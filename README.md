# Qoder2API

OpenAI-compatible proxy for [Qoder](https://qoder.com) — use Qoder's models (including the free **Qwen3.8-Flash**) through any OpenAI-compatible client (9router, Hermes, etc.). No desktop app required after login.

Upstream: `https://api2-v2.qoder.sh/model/v1/chat/completions` (plain OpenAI format, the direct model endpoint used by the Qoder desktop app).

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

## Quick start

Windows: double-click `Qoder2API.bat`, or:

```bash
pip install cryptography
python main.py            # interactive menu
```

Headless:

```bash
python main.py --login                    # open browser, approve, exit
python main.py --no-menu --port 61025     # serve on http://localhost:61025/v1
python main.py --no-menu --api-key sk-anything   # require a Bearer key on /v1/*
```

Token is stored in `~/.qoder2api-auth.json` (never commit it). Refresh is automatic via the stored refresh token.

## Menu

```
1. Status        - account, plan, credit balances
2. Start server  - the OpenAI-compatible proxy
3. List models   - proxy ids -> upstream ids
4. Test chat     - one-shot smoke test
5. Re-login      - redo device login
6. Quit
```

## Endpoints

- `POST /v1/chat/completions` — OpenAI chat, stream + non-stream, tools
- `GET /v1/models` — proxy model list
- `GET /v1/plan` — account plan
- `GET /v1/quota` — credit balances (the free model never decrements these)
- `GET /healthz` — `{"ok": true}` when logged in
- `POST /login/url`, `POST /login/poll` — device login for scripted use

## 9router

Add a connection: base URL `http://127.0.0.1:61025/v1`, model `qwen3.8-flash` (or any id above). If you passed `--api-key`, send it as the Bearer key; otherwise any key works.

## Notes

- The app's agent endpoint (`agent_chat_generation`) needs a COSY signed envelope and is slow (~19s first frame). This proxy uses the direct model endpoint instead — first frame in ~5-12s.
- `reasoning_content` in deltas is passed through; clients that ignore unknown delta fields are unaffected.
- `role: tool` messages are folded into `user` turns (`Tool result: ...`) since upstream has no tool role.
- Run `py tests/selfcheck.py` for the offline test suite.
