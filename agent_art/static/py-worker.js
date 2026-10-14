// Runs the Python simulation (agent_art) in the browser via Pyodide. Talks to the page with postMessage:
//   in:  {id, type: "run" | "preview", payload: <JSON string>}
//   out: {id, ok: true, result: <JSON string>} | {id, ok: false, error}   and {type: "status", text} while booting
// Must be started as a module worker: Pyodide 314 doesn't support classic workers.
import {loadPyodide} from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

const BASE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";

const status = text => postMessage({type: "status", text});

const ready = (async () => {
  status("loading Python runtime…");
  const py = await loadPyodide({indexURL: BASE});
  status("loading numpy…");
  await py.loadPackage("numpy");
  status("loading simulation…");
  const zip = await (await fetch(new URL("agent_art.zip", self.location.href))).arrayBuffer();
  py.unpackArchive(zip, "zip");
  const api = py.pyimport("agent_art.api");
  status("ready");
  return api;
})();
ready.catch(e => postMessage({type: "status", text: "failed to start Python: " + e.message, error: true}));

onmessage = async e => {
  const {id, type, payload} = e.data;
  try {
    const api = await ready;
    const fn = type === "preview" ? api.preview_json : api.run_json;
    postMessage({id, ok: true, result: fn(payload)});
  } catch (err) {
    postMessage({id, ok: false, error: String(err && err.message || err)});
  }
};
