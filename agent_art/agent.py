"""Single-agent walk: steering from random turn, jitter, preferences, and neighbors."""
from __future__ import annotations

import math

import numpy as np

from .goals import make_template
from .world import World


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def walk(world: World, rng: np.random.Generator, traits: dict, species_id: int,
         x: float, y: float, energy: float, boundary: str = "reflect",
         bounds: tuple[float, float, float, float] | None = None,
         max_steps: int = 20000, drivers: list | None = None) -> np.ndarray:
    """Return the path (N,2) of one agent. Coordinates are math-style (y up).

    drivers: [(target, gain, profile)] where profile is the 0..1 signal values the agent sees as
    its path progresses (fraction of energy spent) from 0 to 1.
    """
    t = traits
    xmin, ymin, xmax, ymax = bounds or (0.0, 0.0, world.width, world.height)
    x, y = min(max(x, xmin), xmax), min(max(y, ymin), ymax)
    heading = math.radians(t["init_angle"])
    step = t["step"]
    tpl = None
    if t.get("goal"):
        tpl = make_template(t["goal"], t["goal_size"], t["init_angle"], t["goal_mirror"], (x, y))
        heading = tpl.tangent(0)
    gi = 0  # progress index along the template
    base_heading = heading
    energy0 = energy
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

        nb = world.neighbors(x, y, t["vision"])
        if len(nb):
            dx, dy = nb[:, 0] - x, nb[:, 1] - y
            d = np.hypot(dx, dy)
            m = (d <= t["vision"]) & (d > 1e-9)
            if m.any():
                dx, dy, d = dx[m], dy[m], d[m]
                a = np.where(nb[m, 2] == species_id, t["affinity_same"], t["affinity_other"])
                s_ = np.where(a >= 0, a * np.clip((d - t["comfort_distance"]) / t["vision"], -1, 1),
                              a * (1 - d / t["vision"]))
                fx, fy = float((s_ * dx / d).mean()), float((s_ * dy / d).mean())
                turn += t["social_strength"] * min(math.hypot(fx, fy), 1.0) * math.sin(math.atan2(fy, fx) - heading)

        if tpl is not None:
            # advance to the nearest template point ahead, then steer toward a lookahead point
            look = max(int(step * 3 / tpl.spacing), 1)
            idx = np.arange(gi, gi + 2 * look + 1)
            win = tpl.pts[idx % (tpl.k - 1) if tpl.closed else np.minimum(idx, tpl.k - 1)]
            gi += int(np.argmin(np.hypot(win[:, 0] - x, win[:, 1] - y)))
            if not tpl.closed and gi >= tpl.k - 1 - look:
                tpl = None  # open shape finished: back to free walking
            else:
                tx, ty = tpl.pts[tpl.index(gi + look)]
                diff = _wrap(math.atan2(ty - y, tx - x) - heading)
                g = t["goal_strength"]
                turn = (1 - g) * turn + g * max(-0.8, min(0.8, 0.6 * diff))

        step_mult = 1.0
        if drivers:
            f = 1 - energy / energy0
            for target, gain, prof in drivers:
                u = float(prof[min(int(f * (len(prof) - 1)), len(prof) - 1)])
                c = 2 * u - 1  # -1..1
                if target == "turn":
                    turn += gain * c
                elif target == "heading":   # lean toward base heading + gain*c
                    turn += 0.5 * _wrap(base_heading + gain * c - heading)
                elif target == "step":
                    step_mult *= max(0.05, 1 + gain * c)
                elif target == "jitter":
                    turn += rng.normal() * gain * u

        heading = _wrap(heading + turn)
        step_len = min(step * step_mult, energy)
        nx, ny = x + step_len * math.cos(heading), y + step_len * math.sin(heading)
        if not (xmin <= nx <= xmax and ymin <= ny <= ymax):
            if boundary == "stop":
                break
            if not xmin <= nx <= xmax:
                heading = math.pi - heading
            if not ymin <= ny <= ymax:
                heading = -heading
            nx = min(max(x + step_len * math.cos(heading), xmin), xmax)
            ny = min(max(y + step_len * math.sin(heading), ymin), ymax)
        x, y = nx, ny
        pts.append((x, y))
        energy -= step_len
        step *= t["momentum_decay"]
    return np.array(pts)
