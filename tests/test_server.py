import json

import pytest

from agent_art import server
from agent_art.cli import load_config


def test_meta_covers_all_traits():
    m = server.meta()
    assert set(m["traits"]) == set(server.TRAITS)
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
