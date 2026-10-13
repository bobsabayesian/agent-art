"""Bind signals to the drop parameters x, y, energy (one sample per agent)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .signals import Series, fetch

ROLES = ("x", "y", "energy")


def resample(values: np.ndarray, n: int) -> np.ndarray:
    """Linearly resample to n points (chronological order preserved)."""
    if len(values) == 1:
        return np.full(n, values[0], dtype=float)
    return np.interp(np.linspace(0, len(values) - 1, n), np.arange(len(values)), values)


def normalize(values: np.ndarray, scale: str = "linear", invert: bool = False,
              clip: tuple[float, float] | None = None) -> np.ndarray:
    """Map to 0..1. scale: linear | log | rank. clip is a (lo, hi) value range."""
    v = np.asarray(values, dtype=float)
    if scale == "log":
        v = np.log1p(np.maximum(v - v.min(), 0))
    elif scale == "rank":
        v = np.argsort(np.argsort(v, kind="stable"), kind="stable").astype(float)
    elif scale != "linear":
        raise ValueError(f"unknown scale {scale!r}")
    lo, hi = clip if clip else (v.min(), v.max())
    out = np.zeros_like(v) if hi == lo else np.clip((v - lo) / (hi - lo), 0, 1)
    return 1 - out if invert else out


@dataclass
class Drops:
    x: np.ndarray       # 0..1
    y: np.ndarray       # 0..1
    energy: np.ndarray  # 0..1
    labels: dict[str, str]


def build_drops(cfg: dict, n: int, rng: np.random.Generator,
                cache_dir: str = ".cache", refresh: bool = False) -> Drops:
    """cfg: {signals: {name: spec}, bind: {x: {signal, scale?, invert?, range?}, ...}}."""
    signals: dict[str, Series] = {}
    for name, spec in (cfg.get("signals") or {}).items():
        signals[name] = fetch(spec, cache_dir, refresh)
    bind = cfg.get("bind") or {}
    out, labels = {}, {}
    for role in ROLES:
        b = bind.get(role)
        if b is None:  # unbound -> seeded random
            out[role] = rng.random(n)
            labels[role] = "random"
            continue
        s = signals[b["signal"]]
        out[role] = normalize(resample(np.array(s.values, float), n), b.get("scale", "linear"),
                              b.get("invert", False), tuple(b["range"]) if b.get("range") else None)
        labels[role] = s.label
    return Drops(labels=labels, **out)
