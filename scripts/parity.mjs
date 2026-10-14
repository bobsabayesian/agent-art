// Checks that the Python running inside Pyodide (what the browser uses) draws the same picture as the CLI.
// Needs `npm run build` first and network access (Pyodide fetches numpy from the CDN).
//
// Structure must match exactly (same agents, species, start points). Most paths are byte-identical; WebAssembly's
// libm rounds sin/cos slightly differently from native code, and wobbly goal-shape paths can amplify that to ~0.01 mm,
// so we require >= 75% byte-identical paths and report the rest.
import { loadPyodide } from "pyodide";
import { readFileSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

const py = process.env.PYTHON ?? (existsSync(".venv/bin/python") ? ".venv/bin/python" : "python3");
const examples = ["demo", "goals", "signal-walk"];   // offline ones (no network signals)
const sha = s => createHash("sha256").update(s).digest("hex").slice(0, 16);

console.log("loading Pyodide…");
const pyodide = await loadPyodide();
await pyodide.loadPackage("numpy");
pyodide.unpackArchive(new Uint8Array(readFileSync("dist/agent_art.zip")), "zip");
const api = pyodide.pyimport("agent_art.api");

let failed = 0;
for (const name of examples) {
  const cfg = JSON.parse(readFileSync(`dist/examples/${name}.json`, "utf8"));
  const t0 = performance.now();
  const web = JSON.parse(api.run_json(JSON.stringify({ config: cfg })));
  const ms = Math.round(performance.now() - t0);
  if (web.error) { console.log(`FAIL ${name}: ${web.error}`); failed++; continue; }
  const ref = spawnSync(py, ["-c", `
import json, sys
from agent_art.api import api_run
print(api_run(json.load(open("dist/examples/${name}.json")), None)["svg"], end="")
`], { encoding: "utf8", maxBuffer: 1 << 28 });
  if (ref.status !== 0) { console.log(`FAIL ${name}: reference run failed\n${ref.stderr}`); failed++; continue; }
  const parse = svg => [...svg.matchAll(/<path d="([^"]+)" [^>]*?data-species="([^"]*)"/g)].map(m => ({ d: m[1], sp: m[2], start: m[1].split(" ")[0] }));
  const [a, b] = [parse(ref.stdout), parse(web.svg)];
  const structural = a.length === b.length && a.every((p, i) => p.sp === b[i].sp && p.start === b[i].start);
  const identical = a.filter((p, i) => b[i] && p.d === b[i].d).length;
  const frac = a.length ? identical / a.length : 0;
  const exact = ref.stdout === web.svg;
  const ok = structural && frac >= 0.75;
  console.log(`${ok ? "ok  " : "FAIL"} ${name}: pyodide ${ms} ms, ${exact ? "byte-identical" : `${identical}/${a.length} paths byte-identical, structure ${structural ? "matches" : "DIFFERS"}`}`);
  if (!ok) failed++;
}
process.exit(failed ? 1 : 0);
