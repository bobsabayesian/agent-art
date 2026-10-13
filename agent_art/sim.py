"""Drop agents one at a time, in order; each draws a path the next ones can see."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .agent import walk
from .mapping import Drops, build_drops
from .species import Species, assign, species_from_config
from .world import World


@dataclass
class Result:
    width: float
    height: float
    species: list[Species]
    paths: list[np.ndarray]      # math coords (y up)
    species_ids: list[int]
    thickness: list[float]
    drops: Drops


def run(cfg: dict, cache_dir: str = ".cache", refresh: bool = False) -> Result:
    canvas = cfg.get("canvas", {})
    w, h = float(canvas.get("width", 297)), float(canvas.get("height", 210))
    margin = float(canvas.get("margin", 10))
    n = int(cfg.get("agents", 200))
    seed = int(cfg.get("seed", 0))
    e_lo, e_hi = cfg.get("energy_range", [50, 400])
    boundary = cfg.get("boundary", "reflect")

    ss = np.random.SeedSequence(seed)
    root, *agent_seeds = ss.spawn(n + 1)
    rng = np.random.default_rng(root)

    species = species_from_config(cfg["species"])
    ids = assign(species, n, rng)
    drops = build_drops(cfg, n, rng, cache_dir, refresh)

    world = World(w, h)
    paths, thick = [], []
    for i in range(n):
        arng = np.random.default_rng(agent_seeds[i])
        sp = species[ids[i]]
        traits = sp.sample(arng)
        x = margin + drops.x[i] * (w - 2 * margin)
        y = margin + drops.y[i] * (h - 2 * margin)
        energy = e_lo + drops.energy[i] * (e_hi - e_lo)
        path = walk(world, arng, traits, int(ids[i]), i, x, y, energy, boundary)
        world.add_path(path, int(ids[i]), i)
        paths.append(path)
        thick.append(traits["thickness"])
    return Result(w, h, species, paths, [int(i) for i in ids], thick, drops)
