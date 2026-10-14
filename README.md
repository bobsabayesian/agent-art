# agent-art

Agent-based SVG generator driven by real-world time series. Agents are dropped one at a time in
chronological order; each walks, draws one polyline, and the next agent reacts to everything already drawn.

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/agent-art run examples/demo.yaml -o out/demo.svg     # offline, synthetic signals
.venv/bin/agent-art run examples/real.yaml -o out/real.svg     # Yahoo (SPY) + Open-Meteo, cached in .cache/
```

- **UI**: `.venv/bin/agent-art serve` then open http://127.0.0.1:8000. Edit canvas, signals (with sparklines), what drives x / y / energy, and species (sliders are `[min, max]` ranges, goal shapes, color/pen, a live preview thumbnail each; hover a species card to highlight its lines). It regenerates as you change things; load examples, download the SVG or the config (a JSON config also runs from the CLI). Stdlib server, no build step.
- **Paper, margin, border** (`canvas:`): `size` is a named paper (ISO `a0`–`a6`, `b3`–`b5`; US `letter`, `legal`, `tabloid`, `ansi_c`/`d`/`e`, `arch_a`–`arch_e`; frames like `8x10in`, `11x14in`, `30x40cm`; or `custom`), with `orientation: landscape|portrait`. `custom` takes `width`/`height`. `unit: mm|cm|in` applies to custom dimensions and `margin`. A bare `{width, height, margin}` in mm still works. **Agents never cross the margin** (their stroke edge included), and drops land inside it. `border: {style: none|single|double|dotted|striped, width, ...}` is drawn inside the margin band (default: centered in it; `inset` moves it; `gap` for double, `dot_spacing` for dotted, `dash`/`dash_gap` for striped; `pen`/`color`); a border that doesn't fit inside the margin is an error. Dots and dashes are real geometry (not SVG dash styles) so plotter software draws them. A border whose `pen` matches a species' pen is drawn on that pen's layer.
- **Signals** (`signals.py`): `synthetic`, `csv`, `open_meteo`, `yahoo` (fields: close, volume, return). Network results cache to `.cache/`; `--refresh` refetches.
- **Binding** (`bind:` in config): any signal can drive `x`, `y`, or `energy`, with `scale: linear|log|rank`, `invert`, `range`. Agent *i* takes sample *i* of each series. Unbound roles are seeded-random. Y is up (high values at top).
- **Modulate traits** (`modulate:`): a signal sets any species trait per agent (by drop order), replacing that species' own sampled value: `turn_propensity: {signal: perf, span: [0.02, 0.3], scale?, invert?, species?: [names]}`. `span` defaults to the trait's slider range; reversing it inverts the effect.
- **Walk drivers** (`walk:`): a signal read *while an agent draws*. Progress along the agent's path (fraction of energy spent) scrubs through a window of the series. `- {signal, target, gain, window, start, scale?, invert?, species?}`.
  - `target: heading` leans the path away from its start direction by `gain` radians x (signal centered on 0, -1..1), so the line traces the chart; `turn` adds `gain` x signal to each turn; `step` scales step size by `1 + gain x signal`; `jitter` adds noise of `gain` x signal.
  - `window` is the fraction of the series one agent reads over its lifetime (default 0.15). `start: drop` (default) slides the window with drop order so later agents read later data; `start: zero` has every agent read from the beginning.
  - See `examples/signal-walk.yaml`. Both blocks are optional; without them configs behave as before.
- **Species** (`species.yaml`): each trait is a number (fixed), `{mean: m, sd: s}` (normal around the mean, truncated to the trait's valid range; `init_angle` wraps around 360; low sd = agents cluster at the mean, high sd = close to uniform), or the older `[lo, hi]` (uniform). Each agent draws its own value. In the UI the left slider is the mean and the right is the spread (sd). Traits: `like_x`, `like_y`, `like_total_angle`, `init_angle`, `turn_propensity`, `jitter`, `step`, `momentum_decay`, `min_step`, `vision`, `comfort_distance`, `affinity_same`, `affinity_other`, `social_strength`, `thickness`, plus `pen`/`color`/`weight`.
- **Goal shapes**: a species can set `goal` (a name or list to pick from per agent: circle, square, triangle, pentagon, hexagon, star, figure8, heart, spiral, wave, line), `goal_size` (mm) and `goal_strength` (0 ignores the shape, 1 traces it tightly; the rest of the steering is scaled by `1 - goal_strength`). The shape starts at the drop point with random rotation/direction. Closed shapes loop until energy runs out; open ones (spiral, wave, line) finish once, then the agent free-walks. See `examples/goals.yaml`.
- **Energy** is a path-length budget in mm (`energy_range`); an agent also stops when its step decays below `min_step`.
- `like_total_angle` biases cumulative turning direction (spirals). Neighbors closer than `comfort_distance` repel and farther ones (within `vision`) attract, scaled by the same/other-species affinity; negative affinity always repels.
- Output: one Inkscape-style layer per `pen`, mm units, `--simplify` for RDP point reduction.

Same config + seed + cached signals gives a byte-identical SVG. Tests: `.venv/bin/pytest`.
