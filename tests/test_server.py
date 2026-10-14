import json

import pytest

from agent_art import server
from agent_art.species import TRAITS
from agent_art.cli import load_config


def test_meta_covers_all_traits():
    m = server.meta()
    assert set(m["traits"]) == set(TRAITS)
    assert "circle" in m["goals"] and "demo" in m["examples"] and "species" not in m["examples"]


def test_run_returns_svg_counts_and_series():
    out = server.api_run(load_config("examples/goals.yaml") | {"agents": 15}, ".cache", False)
    assert out["svg"].startswith("<svg") and sum(out["counts"].values()) == 15
    assert set(out["series"]) == {"vol", "temp"}
    json.dumps(out)  # fully serializable


def test_run_limits_agents():
    with pytest.raises(ValueError):
        server.api_run({"agents": 99999, "species": [{"name": "a"}]}, ".cache", False)


def test_preview_escapes_names():
    svg = server.api_preview({"species": {"name": 'a"<b', "goal": ["star"]}})["svg"]
    assert 'a&quot;&lt;b' in svg


def test_json_wrappers_for_the_browser():
    from agent_art import api
    cfg = load_config("examples/demo.yaml") | {"agents": 8}
    out = json.loads(api.run_json(json.dumps({"config": cfg})))
    assert out["svg"].startswith("<svg") and sum(out["counts"].values()) == 8
    err = json.loads(api.run_json(json.dumps({"config": {"agents": 0, "species": [{"name": "a"}]}})))
    assert err["error"].startswith("ValueError")
    pv = json.loads(api.preview_json(json.dumps({"species": {"name": "x"}})))
    assert pv["svg"].startswith("<svg")
    assert json.loads(api.run_json("not json"))["error"]
