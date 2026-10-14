"""Assemble dist/: the page, the Python package (zipped for Pyodide), meta.json and example configs.

Run from the repo root with an environment that has numpy and pyyaml (see scripts/build.mjs).
"""
from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_art.api import meta  # noqa: E402
from agent_art.cli import load_config  # noqa: E402

DIST = ROOT / "dist"
STATIC = ROOT / "agent_art" / "static"
PKG = ROOT / "agent_art"
EXCLUDE = {"cli.py", "server.py"}   # need pyyaml / sockets; the browser doesn't use them


def main() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    (DIST / "examples").mkdir(parents=True)

    html = (STATIC / "index.html").read_text()
    marker = '<meta name="agent-art-backend" content="local">'
    if marker not in html:
        raise SystemExit("index.html is missing the backend meta tag")
    (DIST / "index.html").write_text(html.replace(marker, '<meta name="agent-art-backend" content="web">'))
    shutil.copy(STATIC / "py-worker.js", DIST / "py-worker.js")

    # reproducible zip: fixed timestamps, sorted names
    with zipfile.ZipFile(DIST / "agent_art.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PKG.glob("*.py")):
            if f.name in EXCLUDE:
                continue
            info = zipfile.ZipInfo(f"agent_art/{f.name}", date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())

    names = []
    for f in sorted((ROOT / "examples").glob("*.yaml")):
        if f.stem == "species":
            continue
        (DIST / "examples" / f"{f.stem}.json").write_text(json.dumps(load_config(str(f))))
        names.append(f.stem)
    (DIST / "meta.json").write_text(json.dumps(meta(names)))
    print(f"dist/ ready: {len(names)} examples, {sum(p.stat().st_size for p in DIST.rglob('*') if p.is_file()) // 1024} KB")


if __name__ == "__main__":
    main()
