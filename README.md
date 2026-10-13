# agent-art

Agent-based SVG generator driven by real-world time series. Agents are dropped one at a time in
chronological order; each walks, draws one polyline, and the next agent reacts to everything already drawn.

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/agent-art run examples/demo.yaml -o out/demo.svg     # offline, synthetic signals
.venv/bin/agent-art run examples/real.yaml -o out/real.svg     # Yahoo (SPY) + Open-Meteo, cached in .cache/
```

- **Signals** (`signals.py`): `synthetic`, `csv`, `open_meteo`, `yahoo` (fields: close, volume, return). Network results cache to `.cache/`; `--refresh` refetches.
- **Binding** (`bind:` in config): any signal can drive `x`, `y`, or `energy`, with `scale: linear|log|rank`, `invert`, `range`. Agent *i* takes sample *i* of each series. Unbound roles are seeded-random. Y is up (high values at top).
- **Species** (`species.yaml`): each trait is a number or `[lo, hi]` (sampled per agent). Traits: `like_x`, `like_y`, `like_total_angle`, `init_angle`, `turn_propensity`, `jitter`, `step`, `momentum_decay`, `min_step`, `vision`, `comfort_distance`, `affinity_same`, `affinity_other`, `social_strength`, `thickness`, plus `pen`/`color`/`weight`.
- **Goal shapes**: a species can set `goal` (a name or list to pick from per agent: circle, square, triangle, pentagon, hexagon, star, figure8, heart, spiral, wave, line), `goal_size` (mm) and `goal_strength` (0 ignores the shape, 1 traces it tightly; the rest of the steering is scaled by `1 - goal_strength`). The shape starts at the drop point with random rotation/direction. Closed shapes loop until energy runs out; open ones (spiral, wave, line) finish once, then the agent free-walks. See `examples/goals.yaml`.
- **Energy** is a path-length budget in mm (`energy_range`); an agent also stops when its step decays below `min_step`.
- `like_total_angle` biases cumulative turning direction (spirals). Neighbors closer than `comfort_distance` repel and farther ones (within `vision`) attract, scaled by the same/other-species affinity; negative affinity always repels.
- Output: one Inkscape-style layer per `pen`, mm units, `--simplify` for RDP point reduction.

Same config + seed + cached signals gives a byte-identical SVG. Tests: `.venv/bin/pytest`.
