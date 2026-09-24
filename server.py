"""OpenAI-compatible proxy for Qoder's direct model API."""

import json
import shutil
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import auth
import client

PORT = 61025

# Fields the caller may set; everything else is stripped to avoid
# upstream-specific validation errors.
ALLOWED = {
    "model", "messages", "stream", "temperature", "top_p", "max_tokens",
    "max_completion_tokens", "stop", "presence_penalty", "frequency_penalty",
    "n", "seed", "tools", "tool_choice", "parallel_tool_calls",
    "response_format", "logprobs", "top_logprobs", "user", "reasoning_effort",
}


def _flatten_content(content):
    """Qoder expects text strings; join OpenAI content-block arrays."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                t = b.get("text") or b.get("content")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(content)


def _convert_tools(tools):
    """Upstream requires strict OpenAI format: {type:function, function:{...}}."""
    if not tools:
        return None
    out = []
    for t in tools:
        if t.get("type") == "function" and t.get("function"):
            f = t["function"]
            out.append({
                "type": "function",
                "function": {
                    "name": f.get("name", ""),
                    "description": f.get("description", ""),
                    "parameters": f.get("parameters") or {"type": "object",
                                                          "properties": {}},
                },
            })
        elif t.get("function"):
            out.append({"type": "function", "function": t["function"]})
    return out or None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Qoder2API/0.1.0"

    def log_message(self, *a):
        pass

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status, msg, etype="qoder_error"):
        self._json(status, {"error": {"message": str(msg), "type": etype,
                                      "code": status}})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/healthz":
            s = auth.load_auth()
            return self._json(200, {"ok": bool(s and s.get("token"))})
        if path == "/v1/models":
            created = int(time.time())
            data = [{"id": k, "object": "model", "created": created,
                     "owned_by": "qoder"} for k in client.MODELS]
            return self._json(200, {"object": "list", "data": data})
        if path == "/v1/plan":
            try:
                return self._json(200, client.plan())
            except Exception as e:
                return self._err(502, e)
        if path == "/v1/quota":
            try:
                return self._json(200, client.quota())
            except Exception as e:
                return self._err(502, e)
        return self._json(404, {"error": {"message": "unknown path",
                                          "type": "not_found"}})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login/url":
            url, verifier, nonce = client.login_url()
            auth.save_auth({**(auth.load_auth() or {}),
                            "loginVerifier": verifier, "loginNonce": nonce})
            return self._json(200, {"url": url})
        if path == "/login/poll":
            s = auth.load_auth() or {}
            nonce, verifier = s.get("loginNonce"), s.get("loginVerifier")
            if not nonce:
                return self._err(400, "no pending login")
            try:
                creds = client.poll_login(nonce, verifier, timeout=290)
            except TimeoutError as e:
                return self._err(408, e)
            s.update(creds)
            s.pop("loginNonce", None)
            s.pop("loginVerifier", None)
            auth.save_auth(s)
            return self._json(200, {"ok": True})
        if path != "/v1/chat/completions":
            return self._json(404, {"error": {"message": "unknown path",
                                              "type": "not_found"}})

        try:
            n = int(self.headers.get("content-length", 0))
        except ValueError:
            n = 0
        if n <= 0:
            return self._err(400, "empty request body")
        try:
            req = json.loads(self.rfile.read(n))
        except json.JSONDecodeError as e:
            return self._err(400, f"invalid JSON: {e}")

        if not client.token():
            return self._err(401, "not logged in; POST /login/url then /login/poll",
                             "auth_error")

        want_stream = bool(req.get("stream", False))
        msgs = []
        for m in req.get("messages") or []:
            role = m.get("role") or "user"
            text = _flatten_content(m.get("content"))
            if role == "tool":
                # Qoder has no tool role; fold results into a user turn.
                msgs.append({"role": "user",
                             "content": f"Tool result: {text}"})
            elif role == "assistant":
                msgs.append({"role": "assistant", "content": text})
            elif role in ("system", "developer", "user"):
                msgs.append({"role": role, "content": text})
            # function/other roles dropped: unsupported upstream.

        body = {k: v for k, v in req.items() if k in ALLOWED}
        body["model"] = client.resolve_model(req.get("model"))
        body["messages"] = msgs or [{"role": "user", "content": "Hello"}]
        body["stream"] = want_stream
        tools = _convert_tools(req.get("tools"))
        if tools:
            body["tools"] = tools
        elif "tools" in body:
            body.pop("tools")

        cid = "chatcmpl-" + uuid.uuid4().hex
        created = int(time.time())
        self._model = body["model"]
        try:
            resp = client.post_chat(body, timeout=300)
        except Exception as e:
            detail = getattr(e, "read", lambda: b"")()
            if isinstance(detail, bytes):
                try:
                    detail = detail.decode("utf-8", "replace")[:400]
                except Exception:
                    detail = ""
            return self._err(502, f"{e} {detail}".strip(), "upstream_error")

        if want_stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                self._relay_stream(resp, cid, created)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            try:
                raw = resp.read()
            except Exception as e:
                return self._err(502, f"upstream read failed: {e}")
            try:
                data = json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                return self._err(502, "upstream returned non-JSON")
            if not data.get("choices"):
                return self._err(502, data)
            data.setdefault("id", cid)
            data.setdefault("object", "chat.completion")
            data.setdefault("created", created)
            data.setdefault("model", body["model"])
            self._json(200, data)

    def _relay_stream(self, resp, cid, created):
        """Pass upstream SSE through, stamping OpenAI ids/roles."""
        first = True
        while True:
            try:
                line = resp.readline()
            except Exception:
                break
            if not line:
                break
            s = line.decode("utf-8", "replace").strip()
            if not s or not s.startswith("data:"):
                continue
            payload = s[5:].strip()
            if payload == "[DONE]":
                self._chunk({"id": cid, "object": "chat.completion.chunk",
                             "created": created,
                             "model": getattr(self, "_model", "qoder"),
                             "choices": [{"index": 0, "delta": {},
                                          "finish_reason": "stop"}]})
                self._chunk(None, done=True)
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            # Upstream SSE errors arrive as event: error frames.
            if obj.get("error") or obj.get("code"):
                self._chunk({"error": obj})
                self._chunk(None, done=True)
                break
            for ch in obj.get("choices", []):
                delta = ch.get("delta") or {}
                if first:
                    delta = {"role": "assistant", **delta}
                    first = False
                out = {"id": cid, "object": "chat.completion.chunk",
                       "created": created,
                       "model": getattr(self, "_model", "qoder"),
                       "choices": [{"index": ch.get("index", 0),
                                    "delta": delta,
                                    "finish_reason": ch.get("finish_reason")}]}
                if obj.get("usage"):
                    out["usage"] = obj["usage"]
                self._chunk(out)
        try:
            resp.close()
        except Exception:
            pass

    def _chunk(self, obj, done=False):
        if done:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        data = json.dumps(obj).encode()
        self.wfile.write(b"data: " + data + b"\n\n")
        self.wfile.flush()


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main(port=PORT):
    srv = Server(("127.0.0.1", port), Handler)
    print(f"Qoder2API on http://127.0.0.1:{port}/v1")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
