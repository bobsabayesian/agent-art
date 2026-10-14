"""Tiny local web UI server (stdlib only): static page + JSON API around sim.run."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import MAX_AGENTS, api_preview, api_run, meta as _meta
from .cli import load_config

STATIC = Path(__file__).parent / "static"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
MAX_BODY = 32_000_000


def meta() -> dict:
    return _meta([p.stem for p in EXAMPLES.glob("*.yaml") if p.stem != "species"])


def make_handler(cache_dir: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/meta":
                self._json(meta())
            elif path.startswith("/api/example/"):
                name = path.rsplit("/", 1)[1]
                f = EXAMPLES / f"{name}.yaml"
                if not f.is_file() or f.parent != EXAMPLES:
                    return self._json({"error": "no such example"}, 404)
                self._json(load_config(str(f)))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size > MAX_BODY:
                    return self._json({"error": f"request too large ({size // 1_000_000} MB; limit {MAX_BODY // 1_000_000} MB)"}, 413)
                body = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/api/run":
                    cfg = body["config"]
                    self._json(api_run(cfg, cache_dir, bool(body.get("refresh"))))
                elif self.path == "/api/preview":
                    self._json(api_preview(body))
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:  # surface config / network problems in the UI
                self._json({"error": f"{type(e).__name__}: {e}"}, 400)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, cache_dir: str = ".cache") -> None:
    srv = ThreadingHTTPServer((host, port), make_handler(cache_dir))
    print(f"agent-art UI on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
