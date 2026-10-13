"""Single-agent walk: steering from random turn, jitter, preferences, and neighbors."""
from __future__ import annotations

import math

import numpy as np

from .goals import make_template
from .world import World


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def walk(world: World, rng: np.random.Generator, traits: dict, species_id: int, agent_id: int,
         x: float, y: float, energy: float, boundary: str = "reflect",
         max_steps: int = 20000) -> np.ndarray:
    """Return the path (N,2) of one agent. Coordinates are math-style (y up)."""
    t = traits
    heading = math.radians(t["init_angle"])
    step = t["step"]
    tpl = None
    if t.get("goal"):
        tpl = make_template(t["goal"], t["goal_size"], t["init_angle"], t["goal_mirror"], (x, y))
        heading = tpl.tangent(0)
    gi = 0  # progress index along the template
    pts = [(x, y)]
    bias = math.hypot(t["like_x"], t["like_y"])
    bias_angle = math.atan2(t["like_y"], t["like_x"])
    for _ in range(max_steps):
        if energy <= 0 or step < t["min_step"]:
            break
        turn = rng.normal() * t["turn_propensity"] + rng.normal() * t["jitter"]
        turn += t["like_total_angle"] * t["turn_propensity"] * 0.5

        if bias > 0:
            turn += min(bias, 1.0) * 0.2 * math.sin(bias_angle - heading)

        fx = fy = 0.0
        count = 0
        for px, py, sp, ag, d in world.near(x, y, t["vision"]):
            if ag == agent_id or d < 1e-9:
                continue
            a = t["affinity_same"] if sp == species_id else t["affinity_other"]
            if a >= 0:
                s = a * max(-1.0, min(1.0, (d - t["comfort_distance"]) / t["vision"]))
            else:
                s = a * (1 - d / t["vision"])
            fx += s * (px - x) / d
            fy += s * (py - y) / d
            count += 1
        if count:
            fx, fy = fx / count, fy / count
            turn += t["social_strength"] * min(math.hypot(fx, fy), 1.0) * math.sin(math.atan2(fy, fx) - heading)

        if tpl is not None:
            # advance to the nearest template point ahead, then steer toward a lookahead point
            look = max(int(step * 3 / tpl.spacing), 1)
            win = tpl.pts[[tpl.index(j) for j in range(gi, gi + 2 * look + 1)]]
            gi += int(np.argmin(np.hypot(win[:, 0] - x, win[:, 1] - y)))
            if not tpl.closed and gi >= tpl.k - 1 - look:
                tpl = None  # open shape finished: back to free walking
            else:
                tx, ty = tpl.pts[tpl.index(gi + look)]
                diff = _wrap(math.atan2(ty - y, tx - x) - heading)
                g = t["goal_strength"]
                turn = (1 - g) * turn + g * max(-0.8, min(0.8, 0.6 * diff))

        heading = _wrap(heading + turn)
        step_len = min(step, energy)
        nx, ny = x + step_len * math.cos(heading), y + step_len * math.sin(heading)
        if not (0 <= nx <= world.width and 0 <= ny <= world.height):
            if boundary == "stop":
                break
            if not 0 <= nx <= world.width:
                heading = math.pi - heading
            if not 0 <= ny <= world.height:
                heading = -heading
            nx = min(max(x + step_len * math.cos(heading), 0), world.width)
            ny = min(max(y + step_len * math.sin(heading), 0), world.height)
        x, y = nx, ny
        pts.append((x, y))
        energy -= step_len
        step *= t["momentum_decay"]
    return np.array(pts)
