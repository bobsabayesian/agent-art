"""Signal providers: each returns a Series, cached to disk for reproducibility."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Series:
    label: str
    values: list[float]
    times: list[str]


def _http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "agent-art/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def _synthetic(p: dict) -> Series:
    n = int(p.get("n", 200))
    rng = np.random.default_rng(int(p.get("seed", 0)))
    t = np.arange(n)
    kind = p.get("kind", "walk")
    if kind == "sine":
        v = np.sin(2 * np.pi * t / float(p.get("period", 50)) + float(p.get("phase", 0)))
    elif kind == "noise":
        v = rng.random(n)
    else:
        v = np.cumsum(rng.normal(size=n))
    return Series(p.get("label", f"synthetic-{kind}"), v.tolist(), [str(i) for i in t])


def _open_meteo(p: dict) -> Series:
    var = p.get("variable", "temperature_2m")
    q = urllib.parse.urlencode({
        "latitude": p["lat"], "longitude": p["lon"],
        "start_date": p["start"], "end_date": p["end"],
        "hourly": var,
    })
    data = json.loads(_http_get(f"https://archive-api.open-meteo.com/v1/archive?{q}"))
    times, vals = data["hourly"]["time"], data["hourly"][var]
    keep = [(t, v) for t, v in zip(times, vals) if v is not None]
    return Series(p.get("label", var), [v for _, v in keep], [t for t, _ in keep])


def _yahoo(p: dict) -> Series:
    """Unofficial Yahoo chart endpoint (no key). field: close | volume | return (daily % change)."""
    from datetime import datetime, timezone
    ts = lambda d: int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())
    q = urllib.parse.urlencode({"period1": ts(p["start"]), "period2": ts(p["end"]), "interval": "1d"})
    sym = p["symbol"].upper()
    data = json.loads(_http_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}"))
    res = (data.get("chart") or {}).get("result")
    if not res:
        raise RuntimeError(f"yahoo returned no data for {sym}: {data.get('chart', {}).get('error')}")
    r = res[0]
    quote = r["indicators"]["quote"][0]
    rows = [(t, c, v) for t, c, v in zip(r["timestamp"], quote["close"], quote["volume"])
            if c is not None and v is not None]
    times = [datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d") for t, _, _ in rows]
    close = np.array([c for _, c, _ in rows], float)
    field = p.get("field", "close")
    if field == "close":
        v = close
    elif field == "volume":
        v = np.array([x for _, _, x in rows], float)
    elif field == "return":
        v = np.concatenate([[0.0], np.diff(close) / close[:-1] * 100])
    else:
        raise ValueError(f"unknown yahoo field {field!r}")
    return Series(p.get("label", f"{sym}-{field}"), v.tolist(), times)


def _csv(p: dict) -> Series:
    with open(p["path"], newline="") as f:
        rows = list(csv.DictReader(f))
    col, tcol = p["column"], p.get("time_column")
    return Series(p.get("label", col), [float(r[col]) for r in rows],
                  [r[tcol] if tcol else str(i) for i, r in enumerate(rows)])


PROVIDERS = {"synthetic": _synthetic, "open_meteo": _open_meteo, "yahoo": _yahoo, "csv": _csv}
_OFFLINE = {"synthetic", "csv"}  # no need to cache


def fetch(spec: dict, cache_dir: str | Path = ".cache", refresh: bool = False) -> Series:
    """spec: {provider: name, ...params}. Network results are cached by param hash."""
    spec = dict(spec)
    name = spec.pop("provider")
    if name not in PROVIDERS:
        raise ValueError(f"unknown provider {name!r}; choose from {sorted(PROVIDERS)}")
    if name in _OFFLINE:
        return PROVIDERS[name](spec)
    key = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    path = Path(cache_dir) / f"{name}-{key}.json"
    if path.exists() and not refresh:
        return Series(**json.loads(path.read_text()))
    s = PROVIDERS[name](spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(s.__dict__))
    return s
