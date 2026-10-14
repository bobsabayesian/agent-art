"""Tiny local web UI server (stdlib only): static page + JSON API around sim.run."""
from __future__ import annotations

import json
import time
from dataclasses import MISSING, fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from .cli import load_config
from .goals import SHAPES
from .paper import BORDER_STYLES, SIZES, UNITS
from .mapping import WALK_TARGETS, resample
from .sim import run
from .species import TRAITS, Species
from .svg import to_svg

STATIC = Path(__file__).parent / "static"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
MAX_AGENTS = 2000

from .server_meta import TRAIT_RANGES  # noqa: E402


def meta() -> dict:
    defaults = {f.name: f.default for f in fields(Species) if f.default is not MISSING}
    traits = {}
    for k in TRAITS:
        lo, hi, st = TRAIT_RANGES[k]
        d = defaults[k]
        mean, sd = (d["mean"], d.get("sd", 0)) if isinstance(d, dict) else ((d[0] + d[1]) / 2, (d[1] - d[0]) / 12 ** 0.5) if isinstance(d, tuple) else (d, 0)
        traits[k] = {"min": lo, "max": hi, "step": st, "sd_max": (hi - lo) / 2, "default": {"mean": mean, "sd": sd}}
    return {
        "traits": traits,
        "goals": sorted(SHAPES),
        "walk_targets": list(WALK_TARGETS),
        "sizes": [{"key": k, "label": v[0], "group": v[1], "w": v[2], "h": v[3]} for k, v in SIZES.items()],
        "units": list(UNITS), "border_styles": list(BORDER_STYLES),
        "examples": sorted(p.stem for p in EXAMPLES.glob("*.yaml") if p.stem != "species"),
        "species_defaults": {"pen": defaults["pen"], "color": defaults["color"], "weight": defaults["weight"]},
    }


def _strip_prolog(svg: str) -> str:
    return svg.split("?>", 1)[1].lstrip() if svg.startswith("<?xml") else svg


def api_run(cfg: dict, cache_dir: str, refresh: bool) -> dict:
    n = int(cfg.get("agents", 200))
    if not 1 <= n <= MAX_AGENTS:
        raise ValueError(f"agents must be between 1 and {MAX_AGENTS}")
    t0 = time.time()
    res = run(cfg, cache_dir, refresh)
    svg = to_svg(res)
    counts = {}
    for sid in res.species_ids:
        counts[res.species[sid].name] = counts.get(res.species[sid].name, 0) + 1
    series = {}
    for name, s in res.signals.items():
        series[name] = {"label": s.label, "values": resample(np.array(s.values, float), min(len(s.values), 120)).tolist(),
                        "first": s.times[0], "last": s.times[-1], "n": len(s.values)}
    pp = res.paper
    return {"svg": _strip_prolog(svg), "paper": {"width": pp.width, "height": pp.height, "margin": pp.margin, "label": pp.label},
            "counts": counts, "labels": res.drops.labels, "series": series,
            "seconds": round(time.time() - t0, 2)}


def api_preview(body: dict) -> dict:
    cfg = {
        "seed": 1, "agents": 6, "canvas": {"width": 80, "height": 80, "margin": 4},
        "energy_range": body.get("energy_range", [50, 300]), "species": [body["species"]],
    }
    return {"svg": _strip_prolog(to_svg(run(cfg)))}


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
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
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
