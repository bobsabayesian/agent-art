"""Drop agents one at a time, in order; each draws a path the next ones can see."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .agent import walk
from .paper import Paper, border_paths, resolve_paper
from .mapping import Drops, build_drops, load_signals
from .species import Species, assign, species_from_config
from .world import World


def _max_vision(sp: Species) -> float:
    v = sp.vision
    return float(max(v) if isinstance(v, (list, tuple)) else v)


@dataclass
class Result:
    width: float
    height: float
    species: list[Species]
    paths: list[np.ndarray]      # math coords (y up)
    species_ids: list[int]
    thickness: list[float]
    drops: Drops
    signals: dict
    paper: Paper | None = None
    border: list | None = None   # polylines (math coords)


def run(cfg: dict, cache_dir: str = ".cache", refresh: bool = False) -> Result:
    paper = resolve_paper(cfg.get("canvas"))
    w, h, margin = paper.width, paper.height, paper.art_inset   # margin = where the drawing area starts
    n = int(cfg.get("agents", 200))
    seed = int(cfg.get("seed", 0))
    e_lo, e_hi = cfg.get("energy_range", [50, 400])
    boundary = cfg.get("boundary", "reflect")

    ss = np.random.SeedSequence(seed)
    root, *agent_seeds = ss.spawn(n + 1)
    rng = np.random.default_rng(root)

    species = species_from_config(cfg["species"])
    ids = assign(species, n, rng)
    signals = load_signals(cfg, cache_dir, refresh)
    drops = build_drops(cfg, n, rng, signals)

    world = World(w, h, cell=max(_max_vision(sp) for sp in species))
    paths, thick = [], []
    for i in range(n):
        arng = np.random.default_rng(agent_seeds[i])
        sp = species[ids[i]]
        traits = sp.sample(arng)
        for m in drops.trait_mods:   # applied after sampling so the random stream is unchanged
            if m.applies(sp.name):
                traits[m.trait] = m.value(i)
        drivers = [(d.target, d.gain, d.profile(i, n)) for d in drops.walkers if d.applies(sp.name)]
        x = margin + drops.x[i] * (w - 2 * margin)
        y = margin + drops.y[i] * (h - 2 * margin)
        inset = margin + traits["thickness"] / 2   # keep the whole stroke inside the drawing area
        bounds = (inset, inset, w - inset, h - inset)
        energy = e_lo + drops.energy[i] * (e_hi - e_lo)
        path = walk(world, arng, traits, int(ids[i]), x, y, energy, boundary, bounds=bounds, drivers=drivers)
        world.add_path(path, int(ids[i]))
        paths.append(path)
        thick.append(traits["thickness"])
    return Result(w, h, species, paths, [int(i) for i in ids], thick, drops, signals, paper, border_paths(paper))
