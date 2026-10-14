import numpy as np
import pytest

from agent_art import signals
from agent_art.cli import load_config
from agent_art.mapping import normalize, resample
from agent_art.sim import run
from agent_art.species import Species, assign
from agent_art.svg import to_svg

CFG = {
    "seed": 3, "agents": 40, "canvas": {"width": 100, "height": 80, "margin": 5},
    "energy_range": [20, 100],
    "signals": {"a": {"provider": "synthetic", "seed": 1}, "b": {"provider": "synthetic", "kind": "sine"}},
    "bind": {"x": {"signal": "a"}, "y": {"signal": "b"}, "energy": {"signal": "a", "scale": "rank"}},
    "species": [
        {"name": "p", "pen": "black", "weight": 1, "step": [1, 2]},
        {"name": "q", "pen": "red", "color": "#f00", "weight": 3, "like_total_angle": 1},
    ],
}


def test_deterministic():
    assert to_svg(run(CFG)) == to_svg(run(CFG))
    assert to_svg(run(CFG)) != to_svg(run({**CFG, "seed": 4}))


def test_paths_in_bounds_and_energy_budget():
    res = run(CFG)
    for p in res.paths:
        assert (p[:, 0] >= 0).all() and (p[:, 0] <= 100).all()
        assert (p[:, 1] >= 0).all() and (p[:, 1] <= 80).all()
        assert np.hypot(*np.diff(p, axis=0).T).sum() <= 100 + 1e-6


def test_drop_positions_follow_signals():
    res = run(CFG)
    a = np.array(signals.fetch(CFG["signals"]["a"]).values)
    xs = np.array([p[0, 0] for p in res.paths])
    # x is min-max of resampled series -> same ordering
    assert np.corrcoef(xs, resample(a, 40))[0, 1] > 0.999


def test_species_weights():
    sp = [Species("a", weight=1), Species("b", weight=9)]
    ids = assign(sp, 5000, np.random.default_rng(0))
    assert 0.85 < (ids == 1).mean() < 0.95


def test_svg_layers_per_pen():
    svg = to_svg(run(CFG))
    assert svg.count('inkscape:groupmode="layer"') == 2
    assert 'inkscape:label="red"' in svg


def test_normalize():
    v = np.array([1.0, 2, 4, 100])
    assert normalize(v).tolist()[0] == 0 and normalize(v)[-1] == 1
    assert normalize(v, invert=True)[0] == 1
    assert normalize(v, "rank").tolist() == [0, 1 / 3, 2 / 3, 1]
    assert normalize(v, clip=(0, 2))[-1] == 1
    assert normalize(np.ones(3)).tolist() == [0, 0, 0]


def test_unknown_species_key():
    with pytest.raises(ValueError):
        run({**CFG, "species": [{"name": "x", "bogus": 1}]})


def test_cache_roundtrip(tmp_path, monkeypatch):
    calls = []
    def fake(p):
        calls.append(1)
        return signals.Series("l", [1.0, 2.0], ["t1", "t2"])
    monkeypatch.setitem(signals.PROVIDERS, "yahoo", fake)
    spec = {"provider": "yahoo", "symbol": "x"}
    s1 = signals.fetch(spec, tmp_path)
    s2 = signals.fetch(spec, tmp_path)
    assert s1 == s2 and len(calls) == 1
    signals.fetch(spec, tmp_path, refresh=True)
    assert len(calls) == 2


def test_examples_load():
    assert len(load_config("examples/real.yaml")["species"]) == 3


def _goal_cfg(goal, strength=1.0, **extra):
    sp = {"name": "g", "goal": goal, "goal_size": 15, "goal_strength": strength, "step": 1.0,
          "momentum_decay": 1.0, "turn_propensity": 0.0, "min_step": 0.1, **extra}
    return {"seed": 1, "agents": 1, "canvas": {"width": 200, "height": 200, "margin": 60},
            "energy_range": [400, 400], "species": [sp]}


def test_circle_goal_is_traced_repeatedly():
    p = run(_goal_cfg("circle")).paths[0]
    c = p[0] + 0  # start on the circle; center is at distance 15 from the start
    # fit center: mean of points over whole loops
    center = p.mean(axis=0)
    r = np.hypot(*(p - center).T)
    assert abs(r.mean() - 15) < 1.0 and r.std() < 1.0
    assert np.hypot(*(p[-1] - p[0])) < 40  # many loops stayed local, did not wander off


@pytest.mark.parametrize("name", ["square", "triangle", "star", "figure8", "heart", "hexagon"])
def test_closed_goals_stay_local(name):
    p = run(_goal_cfg(name)).paths[0]
    assert len(p) > 100
    assert np.ptp(p, axis=0).max() < 15 * 2.6


def test_open_goal_then_free_walk():
    p = run(_goal_cfg("line", step=1.0, goal_size=10)).paths[0]
    assert len(p) > 30  # continues past the 20mm line instead of stopping


def test_goal_off_is_unchanged_and_unknown_goal_errors():
    assert to_svg(run(CFG)) == to_svg(run(CFG))
    with pytest.raises(ValueError):
        run(_goal_cfg("blob"))


def _mod_cfg(**extra):
    base = {"seed": 2, "agents": 30, "canvas": {"width": 200, "height": 200, "margin": 20},
            "energy_range": [40, 40],
            "signals": {"ramp": {"provider": "synthetic", "kind": "sine", "period": 60},
                        "walk": {"provider": "synthetic", "kind": "walk", "seed": 4}},
            "species": [{"name": "a", "pen": "k"}, {"name": "b", "pen": "r", "color": "#f00"}]}
    return base | extra


def test_trait_modulation_follows_signal():
    cfg = _mod_cfg(modulate={"thickness": {"signal": "walk", "span": [0.1, 1.0]}})
    res = run(cfg)
    from agent_art.mapping import normalize, resample
    series = signals.fetch(cfg["signals"]["walk"]).values
    expect = 0.1 + 0.9 * normalize(resample(np.array(series), 30))
    assert np.allclose(res.thickness, expect)


def test_trait_modulation_species_filter_and_invert():
    cfg = _mod_cfg(modulate={"thickness": {"signal": "walk", "span": [0.1, 1.0], "species": ["a"], "invert": True}})
    res = run(cfg)
    for t, sid in zip(res.thickness, res.species_ids):
        if res.species[sid].name == "b":
            assert t == 0.3  # untouched default
        else:
            assert 0.1 <= t <= 1.0


def test_modulation_keeps_random_stream():
    base = to_svg(run(_mod_cfg()))
    same = to_svg(run(_mod_cfg(modulate={}, walk=[])))
    assert base == same


def _straight(**extra):
    sp = {"name": "s", "init_angle": 0, "turn_propensity": 0, "step": 1.0, "momentum_decay": 1.0, "like_x": 0}
    return _mod_cfg(species=[sp], agents=1, energy_range=[120, 120],
                    canvas={"width": 400, "height": 400, "margin": 150}, **extra)


def test_walk_heading_driver_makes_path_follow_signal():
    flat = run(_straight()).paths[0]
    wavy = run(_straight(walk=[{"signal": "ramp", "target": "heading", "gain": 1.2, "window": 0.5}])).paths[0]
    assert np.ptp(flat[:, 1]) < 1e-6
    assert np.ptp(wavy[:, 1]) > 5


def test_walk_step_driver_changes_length_of_steps():
    flat = run(_straight()).paths[0]
    slow = run(_straight(walk=[{"signal": "ramp", "target": "step", "gain": 0.9, "window": 1.0}])).paths[0]
    assert len(slow) > len(flat) * 0.9 and len(slow) != len(flat)


def test_walk_deterministic_and_window_slides_with_drop_order():
    cfg = _mod_cfg(agents=6, walk=[{"signal": "walk", "target": "turn", "gain": 0.3, "window": 0.2}])
    assert to_svg(run(cfg)) == to_svg(run(cfg))
    from agent_art.mapping import build_drops, load_signals
    d = build_drops(cfg, 6, np.random.default_rng(0), load_signals(cfg))
    w = d.walkers[0]
    first, last = w.profile(0, 6), w.profile(5, 6)
    series = w.norm
    assert first[0] == series[0] and last[-1] == series[-1]


@pytest.mark.parametrize("bad", [
    {"modulate": {"nonsense": {"signal": "walk"}}},
    {"modulate": {"thickness": {"signal": "missing"}}},
    {"walk": [{"signal": "walk", "target": "sideways"}]},
    {"walk": [{"signal": "walk", "target": "turn", "window": 0}]},
    {"walk": [{"signal": "walk", "target": "turn", "start": "later"}]},
])
def test_bad_modulation_configs(bad):
    with pytest.raises(ValueError):
        run(_mod_cfg(**bad))


def _draw_many(key, v, n=4000):
    from agent_art.species import _draw
    rng = np.random.default_rng(0)
    return np.array([_draw(key, v, rng) for _ in range(n)])


def test_mean_sd_low_spread_stays_near_mean_and_high_spread_wanders():
    tight = _draw_many("like_x", {"mean": 0.0, "sd": 0.05})
    loose = _draw_many("like_x", {"mean": 0.0, "sd": 1.0})
    assert abs(tight.mean()) < 0.01 and tight.std() < 0.06
    assert loose.std() > 0.45 and loose.min() >= -1 and loose.max() <= 1  # truncated, near-uniform


def test_mean_sd_edge_cases():
    assert _draw_many("like_x", {"mean": 0.3, "sd": 0}, 5).tolist() == [0.3] * 5
    a = _draw_many("init_angle", {"mean": 350, "sd": 30})
    assert a.min() >= 0 and a.max() < 360
    assert (a < 40).sum() > 200 and (a > 300).sum() > 200  # wraps around 360
    u = _draw_many("like_x", [0.2, 0.8])  # legacy uniform range still works
    assert 0.2 <= u.min() and u.max() <= 0.8
    assert _draw_many("like_x", 0.25, 3).tolist() == [0.25] * 3
    with pytest.raises(ValueError):
        _draw_many("like_x", {"mean": 0, "stddev": 1}, 1)


def test_species_traits_accept_mean_sd():
    sp = Species("a", like_x={"mean": 0.5, "sd": 0.01})
    xs = [sp.sample(np.random.default_rng(i))["like_x"] for i in range(50)]
    assert abs(np.mean(xs) - 0.5) < 0.02


# ---------- paper, margin, border ----------
from agent_art.paper import SIZES, border_paths, resolve_paper


def test_named_sizes_orientation_units():
    a4 = resolve_paper({"size": "A4"})
    assert (a4.width, a4.height) == (297, 210)                      # landscape default
    p = resolve_paper({"size": "a4", "orientation": "portrait"})
    assert (p.width, p.height) == (210, 297)
    lt = resolve_paper({"size": "Letter", "orientation": "portrait"})
    assert (round(lt.width, 1), round(lt.height, 1)) == (215.9, 279.4)
    assert resolve_paper({"size": "Arch D"}).width == pytest.approx(36 * 25.4)
    c = resolve_paper({"size": "custom", "unit": "in", "width": 10, "height": 8, "margin": 0.5})
    assert (c.width, c.height, c.margin) == (254, 203.2, 12.7)
    legacy = resolve_paper({"width": 297, "height": 210, "margin": 10})  # old configs still mean mm
    assert (legacy.width, legacy.height, legacy.margin) == (297, 210, 10)
    assert {"a0", "a4", "letter", "legal", "tabloid", "ansi_d", "arch_e", "8x10in", "30x40cm"} <= set(SIZES)


@pytest.mark.parametrize("bad", [
    {"size": "A99"}, {"size": "A4", "orientation": "sideways"}, {"unit": "ft"},
    {"width": 100, "height": 100, "margin": 60}, {"border": {"style": "wavy"}},
    {"border": {"style": "single", "bogus": 1}}, {"border": {"style": "single", "width": 0}},
    {"width": 100, "height": 100, "margin": 44, "border": {"style": "single", "width": 5}},   # no room left inside
    {"width": 100, "height": 100, "margin": 30, "border": {"style": "double", "width": 1, "gap": 20}},
    {"width": 100, "height": 100, "margin": 10, "padding": -1, "border": "single"},
    {"width": 100, "height": 100, "margin": 10, "border": {"style": "single", "inset": 5}},     # removed option
])
def test_bad_canvas(bad):
    with pytest.raises(ValueError):
        resolve_paper(bad)


def _cfg_margin():
    return _mod_cfg(canvas={"size": "A5", "margin": 15, "border": {"style": "single", "width": 0.6}},
                    agents=60, energy_range=[300, 600],
                    species=[{"name": "a", "thickness": {"mean": 1.2, "sd": 0}, "turn_propensity": 0.3, "step": 2.0, "like_x": 0.8}])


@pytest.mark.parametrize("boundary", ["reflect", "stop"])
def test_nothing_drawn_outside_margin(boundary):
    res = run(_cfg_margin() | {"boundary": boundary})
    w, h, m = res.width, res.height, 15
    lo = res.paper.art_inset + 1.2 / 2 - 1e-9
    for p in res.paths:
        assert (p[:, 0] >= lo).all() and (p[:, 0] <= w - lo).all()
        assert (p[:, 1] >= lo).all() and (p[:, 1] <= h - lo).all()


def test_goal_shapes_also_confined_to_margin():
    cfg = _cfg_margin()
    cfg["species"] = [{"name": "g", "goal": "star", "goal_size": 80, "goal_strength": 0.9, "step": 1.5}]
    res = run(cfg)
    for p in res.paths:
        assert (p >= 15).all() and (p[:, 0] <= res.width - 15).all() and (p[:, 1] <= res.height - 15).all()


@pytest.mark.parametrize("style,expect", [("single", 1), ("double", 2)])
def test_line_borders_are_closed_rectangles(style, expect):
    paper = resolve_paper({"width": 100, "height": 80, "margin": 10, "border": {"style": style}})
    paths = border_paths(paper)
    assert len(paths) == expect and all(np.allclose(p[0], p[-1]) for p in paths)
    allp = np.vstack(paths)
    assert allp.min() >= 10 and allp[:, 0].max() <= 90 and allp[:, 1].max() <= 70   # nothing in the margin
    if style == "double":  # two nested rectangles
        assert np.ptp(paths[0][:, 0]) > np.ptp(paths[1][:, 0])


def test_dotted_and_striped_borders():
    dots = border_paths(resolve_paper({"width": 100, "height": 80, "margin": 10,
                                       "border": {"style": "dotted", "dot_spacing": 4}}))
    assert len(dots) == pytest.approx(2 * (79.5 + 59.5) / 4, abs=4)   # perimeter of the band's centre line
    assert all(np.hypot(*(d[1] - d[0])) < 0.02 for d in dots)           # a dot is a tiny segment
    dashes = border_paths(resolve_paper({"width": 100, "height": 80, "margin": 10,
                                         "border": {"style": "striped", "dash": 6, "dash_gap": 3}}))
    lens = [np.hypot(*(d[1] - d[0])) for d in dashes]
    assert max(lens) <= 6 + 1e-9 and min(lens) > 3 and len(dashes) > 20


def test_border_svg_shares_layer_with_pen_and_skips_when_none():
    cfg = _cfg_margin()
    cfg["canvas"]["border"]["pen"] = "k"            # same pen name as species "a"? species default pen is black
    svg = to_svg(run(cfg))
    assert svg.count('data-border="single"') == 1 and 'inkscape:label="k"' in svg
    cfg["species"][0]["pen"] = "k"
    assert to_svg(run(cfg)).count('inkscape:groupmode="layer"') == 1   # merged into one pen layer
    cfg["canvas"]["border"]["style"] = "none"
    assert "data-border" not in to_svg(run(cfg))


def test_margin_is_outside_the_border_only():
    """paper edge | margin | border | padding | drawing area -- the margin is not applied twice."""
    paper = resolve_paper({"width": 100, "height": 80, "margin": 10, "padding": 4,
                           "border": {"style": "double", "width": 1, "gap": 3}})
    outer, inner = border_paths(paper)
    assert outer[:, 0].min() - 0.5 == pytest.approx(10)          # outer edge of the band is exactly the margin
    assert inner[:, 0].min() + 0.5 == pytest.approx(10 + 1 + 3 + 1)  # band is gap + 2 line widths wide = 5
    assert paper.art_inset == pytest.approx(10 + 5 + 4)           # + padding
    assert resolve_paper({"width": 100, "height": 80, "margin": 10}).art_inset == 10   # no border: art at margin
    assert resolve_paper({"width": 100, "height": 80, "margin": 10, "padding": 9}).art_inset == 10  # padding unused


def test_artwork_stays_inside_border_with_padding():
    cfg = _cfg_margin()
    cfg["canvas"] = {"size": "A5", "margin": 12, "padding": 3, "border": {"style": "single", "width": 0.6}}
    res = run(cfg)
    lo = 12 + 0.6 + 3 + 1.2 / 2 - 1e-9          # margin + border + padding + half the stroke
    assert res.paper.art_inset == pytest.approx(15.6)
    for p in res.paths:
        assert (p[:, 0] >= lo).all() and (p[:, 0] <= res.width - lo).all()
        assert (p[:, 1] >= lo).all() and (p[:, 1] <= res.height - lo).all()


def test_inline_signal_drives_agents_and_validates():
    vals = [0, 1, 4, 9, 16, 25]
    cfg = _mod_cfg(signals={"d": {"provider": "inline", "values": vals, "label": "squares", "times": list("abcdef")}},
                   bind={"x": {"signal": "d"}}, agents=6)
    res = run(cfg)
    xs = np.array([p[0, 0] for p in res.paths])
    assert np.allclose(np.diff(xs) > 0, True) and res.drops.labels["x"] == "squares"
    assert signals.fetch(cfg["signals"]["d"]).times == list("abcdef")
    for bad in ({"values": [1]}, {"values": "abc"}, {"values": [1, float("nan")]}, {}):
        with pytest.raises(ValueError):
            signals.fetch({"provider": "inline", **bad})
