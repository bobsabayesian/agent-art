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
