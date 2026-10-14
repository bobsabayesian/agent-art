"""Pure JSON-in / JSON-out API shared by the local server and the in-browser (Pyodide) app."""
from __future__ import annotations

import json
import time
from dataclasses import MISSING, fields

import numpy as np

from .goals import SHAPES
from .mapping import WALK_TARGETS, resample
from .paper import BORDER_STYLES, SIZES, UNITS
from .server_meta import TRAIT_RANGES
from .sim import run
from .species import TRAITS, Species
from .svg import to_svg

MAX_AGENTS = 2000


def meta(examples: list[str] | None = None) -> dict:
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
        "examples": sorted(examples or []),
        "species_defaults": {"pen": defaults["pen"], "color": defaults["color"], "weight": defaults["weight"]},
    }


def _strip_prolog(svg: str) -> str:
    return svg.split("?>", 1)[1].lstrip() if svg.startswith("<?xml") else svg


def api_run(cfg: dict, cache_dir: str | None = ".cache", refresh: bool = False) -> dict:
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


def _wrap(fn, payload: str) -> str:
    """JSON string in, JSON string out; errors become {"error": ...} (used from the browser)."""
    try:
        return json.dumps(fn(json.loads(payload)))
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


def run_json(payload: str) -> str:
    """payload: {"config": {...}} -> api_run result. Signals must already be resolved (synthetic / inline)."""
    return _wrap(lambda b: api_run(b["config"], None, False), payload)


def preview_json(payload: str) -> str:
    return _wrap(api_preview, payload)
