// Builds dist/ using the project's venv if present, else python3 (needs numpy + pyyaml).
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";

const py = process.env.PYTHON ?? (existsSync(".venv/bin/python") ? ".venv/bin/python" : "python3");
const r = spawnSync(py, ["scripts/build_web.py"], { stdio: "inherit" });
if (r.status !== 0) {
  console.error(`build failed using ${py}. Make sure numpy and pyyaml are installed (pip install -e .) or set PYTHON=...`);
  process.exit(r.status ?? 1);
}
