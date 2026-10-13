"""Species definitions. Numeric traits may be a number or [lo, hi]; each agent samples its own."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

Range = "float | list[float]"


@dataclass
class Species:
    name: str
    pen: str = "black"            # also the layer name
    color: str = "#000000"
    weight: float = 1.0           # relative chance of being assigned
    thickness: Range = 0.3        # mm
    # preferences (-1..1)
    like_x: Range = 0.0           # + pulls toward high x
    like_y: Range = 0.0           # + pulls toward high y
    like_total_angle: Range = 0.0 # + accumulates counter-clockwise turning (spirals)
    init_angle: Range = (0, 360)  # degrees
    # motion
    turn_propensity: Range = 0.2  # radians of random turn per step
    jitter: Range = 0.0           # radians of extra per-step noise
    step: Range = 2.0             # mm, initial step length
    momentum_decay: Range = 0.99  # step multiplier per step
    min_step: Range = 0.2         # mm, agent stops when step shrinks below this
    # social
    vision: Range = 30.0          # mm
    comfort_distance: Range = 5.0 # mm, preferred distance to others
    affinity_same: Range = 0.0    # + attracted to own species, - repelled
    affinity_other: Range = 0.0
    social_strength: Range = 0.3  # radians of steering per step from neighbors
    # goal shape traced without lifting the pen (None = free walk). A name or a list to pick from.
    goal: "str | list[str] | None" = None
    goal_size: Range = 20.0       # mm (shape radius)
    goal_strength: Range = 0.5    # 0 ignores the shape, 1 tracks it tightly

    def sample(self, rng: np.random.Generator) -> dict:
        """Draw one concrete value per trait. Goal fields only consume randomness when a goal is set."""
        out: dict = {}
        for k in TRAITS:
            v = getattr(self, k)
            out[k] = float(rng.uniform(v[0], v[1])) if isinstance(v, (list, tuple)) else float(v)
        goals = [self.goal] if isinstance(self.goal, str) else list(self.goal or [])
        out["goal"] = goals[int(rng.integers(len(goals)))] if goals else None
        out["goal_mirror"] = bool(rng.integers(2)) if goals else False
        return out


TRAITS = ("thickness", "like_x", "like_y", "like_total_angle", "init_angle", "turn_propensity",
          "jitter", "step", "momentum_decay", "min_step", "vision", "comfort_distance",
          "affinity_same", "affinity_other", "social_strength", "goal_size", "goal_strength")


def species_from_config(items: list[dict]) -> list[Species]:
    fields = Species.__dataclass_fields__
    out = []
    for it in items:
        bad = set(it) - set(fields)
        if bad:
            raise ValueError(f"species {it.get('name')!r}: unknown keys {sorted(bad)}")
        out.append(Species(**it))
    if not out:
        raise ValueError("at least one species is required")
    return out


def assign(species: list[Species], n: int, rng: np.random.Generator) -> np.ndarray:
    w = np.array([s.weight for s in species], float)
    return rng.choice(len(species), size=n, p=w / w.sum())
