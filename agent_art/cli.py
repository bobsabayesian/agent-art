"""agent-art run config.yaml -o out.svg"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .sim import run
from .svg import to_svg


def load_config(path: str) -> dict:
    """Load YAML; `species_file` is resolved relative to the config and supplies `species`."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if "species_file" in cfg:
        with open(Path(path).parent / cfg.pop("species_file")) as f:
            cfg["species"] = yaml.safe_load(f)
    return cfg


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="agent-art")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="generate an SVG from a config")
    r.add_argument("config")
    r.add_argument("-o", "--output", default="out.svg")
    r.add_argument("--seed", type=int, help="override config seed")
    r.add_argument("--refresh", action="store_true", help="refetch signals ignoring cache")
    r.add_argument("--cache-dir", default=".cache")
    r.add_argument("--simplify", type=float, default=0.0, help="RDP tolerance in mm")
    r.add_argument("--background", help="optional background fill, e.g. white")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.seed is not None:
        cfg["seed"] = args.seed
    res = run(cfg, args.cache_dir, args.refresh)
    with open(args.output, "w") as f:
        f.write(to_svg(res, args.simplify, args.background))
    d = res.drops.labels
    print(f"{len(res.paths)} agents -> {args.output}  (x={d['x']}, y={d['y']}, energy={d['energy']})")
