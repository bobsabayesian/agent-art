"""Bind signals to the drop parameters x, y, energy (one sample per agent)."""
from __future__ import annotations

from dataclasses import dataclass, field

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


WALK_TARGETS = ("heading", "turn", "step", "jitter")


@dataclass
class TraitMod:
    """A signal that sets one species trait per agent (overrides the species' own sample)."""
    trait: str
    values: np.ndarray            # (n,) 0..1
    span: tuple[float, float]
    species: frozenset[str] | None

    def applies(self, name: str) -> bool:
        return self.species is None or name in self.species

    def value(self, i: int) -> float:
        return self.span[0] + float(self.values[i]) * (self.span[1] - self.span[0])


@dataclass
class WalkDriver:
    """A signal an agent reads *while walking*: progress along its path scrubs through a window of the series."""
    target: str                   # one of WALK_TARGETS
    gain: float
    norm: np.ndarray              # full-resolution series, normalized 0..1
    window: float                 # fraction of the series each agent reads over its lifetime
    start: str                    # "drop": window slides with drop order; "zero": every agent starts at the beginning
    species: frozenset[str] | None

    def applies(self, name: str) -> bool:
        return self.species is None or name in self.species

    def profile(self, i: int, n: int, points: int = 256) -> np.ndarray:
        """Values 0..1 the agent sees as its path progresses from 0 to 1."""
        last = len(self.norm) - 1
        p0 = 0.0 if self.start == "zero" or n < 2 else (i / (n - 1)) * (1 - self.window) * last
        pos = p0 + np.linspace(0, 1, points) * self.window * last
        return np.interp(pos, np.arange(len(self.norm)), self.norm)


@dataclass
class Drops:
    x: np.ndarray       # 0..1
    y: np.ndarray       # 0..1
    energy: np.ndarray  # 0..1
    labels: dict[str, str]
    trait_mods: list[TraitMod] = field(default_factory=list)
    walkers: list[WalkDriver] = field(default_factory=list)


def load_signals(cfg: dict, cache_dir: str = ".cache", refresh: bool = False) -> dict[str, Series]:
    return {name: fetch(spec, cache_dir, refresh) for name, spec in (cfg.get("signals") or {}).items()}


def _signal(signals: dict[str, Series], b: dict, where: str) -> Series:
    if b.get("signal") not in signals:
        raise ValueError(f"{where}: unknown signal {b.get('signal')!r}")
    return signals[b["signal"]]


def _norm(s: Series, b: dict, n: int | None = None) -> np.ndarray:
    v = np.array(s.values, float)
    if n is not None:
        v = resample(v, n)
    return normalize(v, b.get("scale", "linear"), b.get("invert", False),
                     tuple(b["range"]) if b.get("range") else None)


def _species_filter(b: dict) -> frozenset[str] | None:
    return frozenset(b["species"]) if b.get("species") else None


def build_drops(cfg: dict, n: int, rng: np.random.Generator, signals: dict[str, Series]) -> Drops:
    """cfg keys used:
      bind:      {x|y|energy: {signal, scale?, invert?, range?}}       -> drop position / energy
      modulate:  {trait: {signal, span?, scale?, invert?, species?}}   -> per-agent species trait
      walk:      [{signal, target, gain?, window?, start?, ...}]       -> read while walking
    """
    from .species import TRAITS
    from .server_meta import TRAIT_RANGES  # global span fallback

    bind = cfg.get("bind") or {}
    out, labels = {}, {}
    for role in ROLES:
        b = bind.get(role)
        if b is None:  # unbound -> seeded random
            out[role] = rng.random(n)
            labels[role] = "random"
            continue
        s = _signal(signals, b, f"bind.{role}")
        out[role] = _norm(s, b, n)
        labels[role] = s.label

    mods = []
    for trait, b in (cfg.get("modulate") or {}).items():
        if trait not in TRAITS:
            raise ValueError(f"modulate: unknown trait {trait!r}")
        s = _signal(signals, b, f"modulate.{trait}")
        span = tuple(b["span"]) if b.get("span") else TRAIT_RANGES[trait][:2]
        mods.append(TraitMod(trait, _norm(s, b, n), (float(span[0]), float(span[1])), _species_filter(b)))

    walkers = []
    for k, b in enumerate(cfg.get("walk") or []):
        if b.get("target") not in WALK_TARGETS:
            raise ValueError(f"walk[{k}]: target must be one of {WALK_TARGETS}, got {b.get('target')!r}")
        s = _signal(signals, b, f"walk[{k}]")
        window = float(b.get("window", 0.15))
        if not 0 < window <= 1:
            raise ValueError(f"walk[{k}]: window must be in (0, 1]")
        if b.get("start", "drop") not in ("drop", "zero"):
            raise ValueError(f"walk[{k}]: start must be 'drop' or 'zero'")
        norm = _norm(s, b)
        if len(norm) < 2:
            raise ValueError(f"walk[{k}]: signal needs at least 2 samples")
        walkers.append(WalkDriver(b["target"], float(b.get("gain", 1.0)), norm, window,
                                  b.get("start", "drop"), _species_filter(b)))
    return Drops(labels=labels, trait_mods=mods, walkers=walkers, **out)
