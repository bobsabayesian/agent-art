# agent-art

Agent-based SVG generator driven by real-world time series. Agents are dropped one at a time in
chronological order; each walks, draws one polyline, and the next agent reacts to everything already drawn.

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/agent-art run examples/demo.yaml -o out/demo.svg     # offline, synthetic signals
.venv/bin/agent-art run examples/real.yaml -o out/real.svg     # Yahoo (SPY) + Open-Meteo, cached in .cache/
```

- **UI**: `.venv/bin/agent-art serve` then open http://127.0.0.1:8000. Edit canvas, signals (with sparklines), what drives x / y / energy, and species (sliders are `[min, max]` ranges, goal shapes, color/pen, a live preview thumbnail each; hover a species card to highlight its lines). It regenerates as you change things; load examples, download the SVG or the config (a JSON config also runs from the CLI). Stdlib server, no build step.
- **Paper, margin, border** (`canvas:`): `size` is a named paper (ISO `a0`–`a6`, `b3`–`b5`; US `letter`, `legal`, `tabloid`, `ansi_c`/`d`/`e`, `arch_a`–`arch_e`; frames like `8x10in`, `11x14in`, `30x40cm`; or `custom`), with `orientation: landscape|portrait`. `custom` takes `width`/`height`. `unit: mm|cm|in` applies to custom dimensions and `margin`. A bare `{width, height, margin}` in mm still works. Layout, outside in: **paper edge | margin | border | padding | drawing area**. Without a border the drawing area starts at the margin. The border's outer edge sits exactly on the margin line and `padding` (default 3 mm, same `unit` as margin) separates it from the artwork. Agents never cross into the margin, border or padding (their stroke edge included), and drops land inside the drawing area. `border: {style: none|single|double|dotted|striped, width, ...}` takes `gap` (clear space between the lines) for double, `dot_spacing` for dotted, `dash`/`dash_gap` for striped, and `pen`/`color`. Dots and dashes are real geometry (not SVG dash styles) so plotter software draws them. A border whose `pen` matches a species' pen is drawn on that pen's layer.
- **Uploading CSVs (UI)**: the "Data files" section takes one or more `.csv`/`.tsv` files (button or drag-and-drop onto the page). It handles quoted fields, `, ; tab |` delimiters, a BOM, `$`/`%`, thousands separators and decimal commas, blank cells, and a header row (or none). Every mostly-numeric column becomes a signal, named `file.column`, that appears in the Drives, Modulate and Walk dropdowns; the first text column (e.g. dates) labels the points. Columns over 5000 rows are downsampled. Used columns travel inside the config as `provider: inline` signals (`values`, optional `times`), so a downloaded config is self-contained and runs from the CLI. Files live only in the page (a reload clears them). From the CLI you can still use `provider: csv` with a path.
- **Signals** (`signals.py`): `synthetic`, `csv`, `inline`, `open_meteo`, `yahoo` (fields: close, volume, return). Network results cache to `.cache/`; `--refresh` refetches.
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


## Deploying to Cloudflare (single-user)

The deployed app runs the **same Python** in the browser (Pyodide, loaded from jsdelivr and cached by the browser, about 10 MB the first time), so a given config and seed draws the same picture as the CLI (byte-identical for most examples; goal-shape paths can differ by ~0.01 mm because WebAssembly's sin/cos round slightly differently). A Cloudflare Worker (`worker/`) only serves the page, fetches stock/weather data (Yahoo sends no CORS headers), and writes to R2. Each run takes about 1-5 s in the browser.

```
browser (page + Web Worker running Python)  <->  Cloudflare Worker (/api/*)  <->  R2 bucket "agent-art"
```

**R2 layout** (the bucket is `agent-art`; R2 names can't contain spaces or capitals):

```
sessions/<session-id>/runs/<utc-timestamp>-s<seed>.config.json   (+ .svg)   autosave and the Save button
sessions/<session-id>/exports/<utc-timestamp>-s<seed>.config.json (+ .svg)  every Download SVG / Download config click
cache/signals/<hash>.json                                                    fetched stock/weather series (Refresh data bypasses it)
```

A session id (`YYYYMMDD-HHMMSS-xxxx`, UTC) is created per browser tab and kept across reloads. Click the id chip to copy it, shift-click for a new session. Autosave writes the config and SVG once you stop changing things for 4 s (uncheck "autosave" to turn it off);

### One-time setup

```bash
npm install
npx wrangler login
npx wrangler r2 bucket create agent-art
npm run deploy                       # builds dist/ and publishes the Worker
```

Then lock it to yourself with **Cloudflare Access** (the API refuses every request until this is configured, so the bucket is never open):

1. Cloudflare dashboard -> Workers & Pages -> `agent-art` -> Settings -> Domains & Routes -> enable **Cloudflare Access** for the workers.dev URL (or create a self-hosted Access application for your own domain), with a policy that allows only your email.
2. Zero Trust -> Access -> Applications -> your app -> copy the **Application Audience (AUD) Tag**; Zero Trust -> Settings -> Custom pages shows your **team domain** (`<team>.cloudflareaccess.com`).
3. Put them in `wrangler.toml` under `[vars]` (`ACCESS_TEAM_DOMAIN`, `ACCESS_AUD`) and run `npm run deploy` again.

The Worker also verifies the Access login token itself (signature, audience, issuer, expiry) on every `/api/*` call, so a mistake in the Access policy can't expose R2.

### Local development and checks

```bash
cp .dev.vars.example .dev.vars   # turns the Access check off for local use only
npm run dev                      # builds dist/ and runs the Worker with a local, simulated R2 at http://127.0.0.1:8787
npm test                         # Worker tests (Access verification, R2 saving, signal fetching)
npm run typecheck
npm run test:parity              # Python in Pyodide vs the CLI, same seeds (needs network for the numpy wheel)
.venv/bin/pytest                 # Python tests
```

`agent-art serve` (the local Python server) still works and uses the same page; it just doesn't have sessions or R2.

Limits worth knowing: the `csv` signal provider (a file path) isn't available in the deployed app (upload CSVs under Data files instead); Yahoo's chart endpoint is unofficial and may rate-limit or block Cloudflare's network, in which case the stock signals report a 502 error (uploaded CSV data is unaffected).
