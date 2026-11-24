// Runs an event query (engine/lab/web/events_query.js - the SAME file the replay tab uses) over battles read from stdin.
//   line 1: the query (JSON); every later line: {"id", "events": [...], "teams": {...}}
//   output: one JSON line per battle: {"id", "matches": [...], "capped": bool}   (an error: {"error": message}, exit 2)
// Used by tools/search_events.py; not meant to be run by hand.
const readline = require("readline");
const path = require("path");
const Q = require(path.join(__dirname, "..", "engine", "lab", "web", "events_query.js"));
const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
let query = null;
rl.on("line", (line) => {
  if (!line.trim()) return;
  try {
    if (query === null) { query = JSON.parse(line); return; }
    const b = JSON.parse(line);
    const r = Q.run(query, b.events, b.teams || {});
    process.stdout.write(JSON.stringify({ id: b.id, matches: r.matches, capped: r.capped }) + "\n");
  } catch (e) {
    process.stdout.write(JSON.stringify({ error: String(e.message || e) }) + "\n");
    process.exit(2);
  }
});
