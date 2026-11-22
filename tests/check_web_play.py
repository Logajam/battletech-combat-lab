"""
tests/check_web_play.py - BATTLEROM IN THE BROWSER (INTEGRATION__PLAYER_DECISIONS.md Section 18): a person plays a team in the
browser build, on the page's own computer, and the battle is the SAME battle the desktop Lab plays.

    python tests/check_web_play.py [--rebuild]

Needs node + Playwright (global) + cargo and a built web_lab/ (built when missing). Serves web_lab/ with the two headers a
service worker would add on a real host (cross-origin isolation; the page's play worker sleeps on a shared buffer), then:
  1. the same scripted player plays the same setup and seed on the desktop Lab (play_poll / play_answer) and in the browser
     (LAB_WASM.api, the play worker): every question's kind and answer, and the end (winner, turns, final units), are equal;
     a query while a question waits (a weapon's mode, a charge's route) is answered in the browser too;
  2. a setup with no Human team, and a batch run that includes one, are refused in words;
  3. on a host that sends no special headers (a plain static server, as GitHub Pages is), the service worker (coi.js, coi-sw.js)
     makes the page isolated by itself after one reload;
  4. the real play page (play.html), started the way the Lab page starts it, plays a whole battle by tapping its controls
     in a phone-sized window, with no page error.
Exit code 0 = every check passed; 77 = skipped (no node / Playwright / cargo).
"""
import argparse
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
LAB = os.path.join(ENGINE, "target", "release", "combatlab")
WEB = os.path.join(REPO_ROOT, "web_lab")

SETUP = {"teams": [
    {"name": "Red", "colour": "#4b8fd8", "bot": "human", "units": [{"unit": "Atlas AS7-K.mtf", "gunnery": 4, "piloting": 5}, {"unit": "Griffin GRF-1N.mtf", "gunnery": 4, "piloting": 5}]},
    {"name": "Blue", "colour": "#d86a4b", "bot": "gladiator", "units": [{"unit": "Awesome AWS-8Q.mtf", "gunnery": 4, "piloting": 5}, {"unit": "Hunchback HBK-4G.mtf", "gunnery": 4, "piloting": 5}]}],
    "board": "16x17_Grassland_1.board", "battles": 1, "seed": 11, "max_turns": 100}


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def ask(port, name, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/{name}", data=json.dumps(body or {}).encode(), method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


COI_NODE = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const page = await (await b.newContext()).newPage();
  await page.goto(process.argv[2] + "/index.html");
  await page.waitForFunction(() => window.crossOriginIsolated, null, { timeout: 20000 }).catch(() => {});
  console.log("ISOLATED " + (await page.evaluate(() => window.crossOriginIsolated)));
  await b.close();
})();
"""


class Plain(http.server.SimpleHTTPRequestHandler):
    """Static files and nothing else: the host's own behaviour."""
    def log_message(self, *a):
        pass


class Isolated(http.server.SimpleHTTPRequestHandler):
    """Static files plus the headers that make a page cross-origin isolated (what coi-sw.js adds on a real host)."""
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, *a):
        pass


def desktop_game(port):
    """The scripted player (the same policy as POLICY in the page script below) on the desktop Lab: (answers, end)."""
    gid = ask(port, "play_start", {"setup": SETUP, "seed": 11})["game"]
    log = []
    for _ in range(20000):
        p = ask(port, "play_poll", {"game": gid, "wait_ms": 30000})
        if p["state"] == "waiting":
            continue
        if p["state"] == "failed":
            raise SystemExit("the desktop engine stopped: " + p["error"])
        if p["state"] == "done":
            return log, p["end"]
        r, seq = p["request"], p["seq"]
        k = r["kind"]
        if k == "deploy":
            ans = {"hex": r["hexes"][0], "facing": "N"}
        elif k == "move_order":
            ans = {"unit": r["candidates"][0]}
        elif k == "movement":
            best = max(r["options"], key=lambda o: (o["mode"] == "Run", o["mp"]), default=None)
            ans = {"stay": True} if best is None else {"hex": best["hex"], "facing": best["facing"], "mode": best["mode"]}
        elif k == "target":
            ans = {"target": r["enemies"][0]["id"]}
        elif k == "declaration":
            ans = {"weapons": [w["id"] for w in r["weapons"] if w["in_range"] and not w["needs_twist"]]}
        elif k == "stand_up":
            ans = {"stand": True}
        elif k == "boost":
            ans = {"use": False}
        elif k in ("spot", "tag"):
            ans = {"target": None}
        elif k == "end_phase":
            ans = {}
        else:
            ans = {"kind": r["kinds"][0]["kind"]}
        log.append([k, ans])
        ask(port, "play_answer", {"game": gid, "seq": seq, "answer": ans})
    raise SystemExit("the desktop battle did not end")


NODE = r"""
const { chromium } = require('playwright');
const [,, base, setupFile] = process.argv;
const SETUP = JSON.parse(require('fs').readFileSync(setupFile, 'utf8'));
const POLICY = (r) => {
  const k = r.kind;
  if (k === "deploy") return { hex: r.hexes[0], facing: "N" };
  if (k === "move_order") return { unit: r.candidates[0] };
  if (k === "movement") {
    let best = null;
    for (const o of r.options) { const key = (o.mode === "Run" ? 1 : 0) * 1e6 + o.mp; if (!best || key > best.key) best = { key, o }; }   // the first of equals, as Python's max
    return best ? { hex: best.o.hex, facing: best.o.facing, mode: best.o.mode } : { stay: true };
  }
  if (k === "target") return { target: r.enemies[0].id };
  if (k === "declaration") return { weapons: r.weapons.filter((w) => w.in_range && !w.needs_twist).map((w) => w.id) };
  if (k === "stand_up") return { stand: true };
  if (k === "boost") return { use: false };
  if (k === "spot" || k === "tag") return { target: null };
  if (k === "end_phase") return {};
  return { kind: r.kinds[0].kind };
};
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 780 }, deviceScaleFactor: 1 });
  const errors = [];
  const out = { errors };
  // ---- 1 and 2: the api, scripted
  let page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base + "/index.html");
  await page.waitForFunction(() => window.LAB_WASM && window.crossOriginIsolated, null, { timeout: 60000 });
  out.isolated = await page.evaluate(() => window.crossOriginIsolated);
  out.noHuman = await page.evaluate(async (s) => {
    const plain = JSON.parse(JSON.stringify(s)); plain.teams.forEach((t) => (t.bot = "gladiator"));
    return { start: await LAB_WASM.api("play_start", { setup: plain }), run: await LAB_WASM.api("run", { setup: s }) };
  }, SETUP);
  out.game = await page.evaluate(async ([s, policySrc]) => {
    const POLICY = eval(policySrc);
    const g = await LAB_WASM.api("play_start", { setup: s, seed: 11 });
    if (g.error) return { error: g.error };
    const log = []; const extras = {};
    for (let i = 0; i < 20000; i++) {
      const p = await LAB_WASM.api("play_poll", { game: g.game, wait_ms: 30000 });
      if (p.state === "waiting") continue;
      if (p.state === "failed") return { error: "the engine stopped: " + p.error };
      if (p.state === "done") return { log, end: p.end, extras };
      const r = p.request;
      if (r.kind === "declaration" && !extras.set) {
        extras.set = await LAB_WASM.api("play_query", { game: g.game, query: { q: "set", unit: r.unit, modes: {} } });
        extras.switches = await LAB_WASM.api("play_query", { game: g.game, query: { q: "switches", unit: r.unit, switches: {} } });
      }
      const ans = POLICY(r);
      log.push([r.kind, ans]);
      const a = await LAB_WASM.api("play_answer", { game: g.game, seq: p.seq, answer: ans });
      if (a.error) return { error: a.error };
    }
    return { error: "the battle did not end" };
  }, [SETUP, POLICY.toString()]);
  if (out.game.extras) out.game.extras = { set: !!(out.game.extras.set && out.game.extras.set.weapons), switches: !!(out.game.extras.switches && out.game.extras.switches.equipment) };
  await page.close();
  // ---- 3: the real play page, started as the Lab page starts it, tapped through
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base + "/index.html");
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SETUP);
  await page.goto(base + "/play.html");
  const kinds = new Set();
  let over = false;
  for (let step = 0; step < 600; step++) {
    await page.waitForFunction(() => window.__bm && (window.__bm.req || window.__bm.over), null, { timeout: 120000 });
    const st = await page.evaluate(() => ({ kind: window.__bm.req && window.__bm.req.kind, over: window.__bm.over }));
    if (st.over) { over = true; break; }
    kinds.add(st.kind);
    const tap = (act, extra) => page.locator(`[data-act="${act}"]${extra || ""}`).first().click();
    if (st.kind === 'deploy') { await page.locator('[data-deploy]').first().dispatchEvent('click'); await tap('place'); }
    else if (st.kind === 'move_order') await tap('pick-unit');
    else if (st.kind === 'stand_up') await tap('stand', '[data-v="1"]');
    else if (st.kind === 'boost') await tap('boost', '[data-v="0"]');
    else if (st.kind === 'movement') {
      const hex = await page.evaluate(() => { const r = window.__bm.req; const o = r.options.filter((x) => x.mode === 'Walk').sort((a, b) => b.mp - a.mp)[0] || r.options[0]; return o && o.hex; });
      if (hex && !out.arrow) {
        // the turn arrows still work when another unit stands in the hex they point at: pick the cheapest hex with several facings,
        // put a friend next to it where an arrow points, and tap that arrow with a real mouse click
        const near = await page.evaluate(() => { const r = window.__bm.req; const by = {}; r.options.forEach((o) => (by[o.hex] = by[o.hex] || new Set()).add(o.facing)); const hs = Object.keys(by).filter((h) => by[h].size > 1); hs.sort((a, b) => Math.min(...r.options.filter((o) => o.hex === a).map((o) => o.mp)) - Math.min(...r.options.filter((o) => o.hex === b).map((o) => o.mp))); return hs[0] || null; });
        if (near) {
          await page.locator(`[data-reach="${near}"]`).first().dispatchEvent('click');
          const probe = await page.evaluate(() => {
            const f = [...document.querySelectorAll('[data-arrow]')][0]; if (!f) return null;
            const DIRS = { N: 4, NE: 5, SE: 0, S: 1, SW: 2, NW: 3 }; const facing = f.dataset.arrow;
            const target = neighbours(__bm.dest)[DIRS[facing]];
            const friend = __bm.units.find((u) => u.id !== __bm.req.unit && u.team === __bm.myTeam && !u.destroyed);
            if (friend) { friend.hex = target; redraw(); }
            const g = document.querySelector(`[data-arrow="${facing}"]`).getBoundingClientRect();
            return { facing, x: g.x + g.width / 2, y: g.y + g.height / 2, before: __bm.facing, blocked: !!friend };
          });
          if (probe) { await page.mouse.click(probe.x, probe.y); await page.waitForTimeout(100); out.arrow = { ...probe, after: await page.evaluate(() => __bm.facing) }; }
        }
      }
      if (hex) { await page.locator(`[data-reach="${hex}"]`).first().dispatchEvent('click'); await tap('commit'); }
      else await tap('stay');
    }
    else if (st.kind === 'spot') await tap('spot', '[data-id=""]');
    else if (st.kind === 'tag') await page.evaluate(() => send({ target: null }));
    else if (st.kind === 'target') await tap('target');
    else if (st.kind === 'declaration') { await tap('alpha'); await tap('fire-go'); }
    else if (st.kind === 'physical') await tap('phys', '[data-k=""]');
    else if (st.kind === 'end_phase') await tap('end-go');
    await page.waitForTimeout(60);
  }
  out.page = { over, kinds: [...kinds], arrow: out.arrow };
  console.log("RESULT " + JSON.stringify(out));
  await b.close();
})();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if not shutil.which("node") or not shutil.which("cargo"):
        print("SKIP: node and cargo are needed"); return 77
    node_path = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    if not os.path.isdir(os.path.join(node_path, "playwright")):
        print("SKIP: Playwright is not installed"); return 77
    if a.rebuild or not os.path.exists(os.path.join(WEB, "combatlab.wasm")):
        subprocess.check_call([sys.executable, os.path.join(REPO_ROOT, "tools", "build_web_lab.py")])
    lab_port, web_port = free_port(), free_port()
    lab = subprocess.Popen([LAB, "--no-browser", "--port", str(lab_port)], env={**os.environ, "BTSIM_ROOT": REPO_ROOT}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    handler = lambda *args, **kw: Isolated(*args, directory=WEB, **kw)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", web_port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    failures = 0
    try:
        for _ in range(60):
            try: ask(lab_port, "info"); break
            except Exception: time.sleep(0.5)
        log, end = desktop_game(lab_port)
        with tempfile.TemporaryDirectory() as tmp:
            sf = os.path.join(tmp, "setup.json"); json.dump(SETUP, open(sf, "w"))
            nf = os.path.join(tmp, "probe.js"); open(nf, "w").write(NODE)
            t0 = time.time()
            p = subprocess.run(["node", nf, f"http://127.0.0.1:{web_port}", sf], capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path}, timeout=1800)
            took = time.time() - t0
        line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
        if not line:
            print("FAIL: the browser gave no result\n", p.stdout[-2000:], p.stderr[-2000:]); return 1
        out = json.loads(line[7:])

        def report(ok, text):
            nonlocal failures
            print(f"{'ok  ' if ok else 'FAIL'} {text}")
            failures += 0 if ok else 1

        plain_port = free_port()
        plain = http.server.ThreadingHTTPServer(("127.0.0.1", plain_port), lambda *args, **kw: Plain(*args, directory=WEB, **kw))
        threading.Thread(target=plain.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory() as tmp:
            cf = os.path.join(tmp, "coi.js"); open(cf, "w").write(COI_NODE)
            q = subprocess.run(["node", cf, f"http://127.0.0.1:{plain_port}"], capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path}, timeout=120)
        plain.shutdown()
        report("ISOLATED true" in q.stdout, "on a plain static host the service worker makes the page cross-origin isolated by itself")
        report(out["isolated"], "the page is cross-origin isolated (the play worker can have shared memory)")
        g = out["game"]
        if "error" in g:
            report(False, "the browser game: " + g["error"])
        else:
            report(g["log"] == log, f"the same player's {len(log)} answers get the same questions in the browser as on the desktop")
            if g["log"] != log:
                for i, (x, y) in enumerate(zip(log, g["log"])):
                    if x != y:
                        print("   first difference at question", i, "\n   desktop", x, "\n   browser", y); break
            same_end = all(g["end"][k] == end[k] for k in ("winner", "turns", "destroyed", "units", "decisions"))
            report(same_end, f"the battle ends the same: {g['end']['winner']} after {g['end']['turns']} turns (desktop: {end['winner']}, {end['turns']})")
            report(g["extras"]["set"] and g["extras"]["switches"], "queries while a question waits (weapon modes, equipment switches) are answered in the browser")
        report("Human" in (out["noHuman"]["start"].get("error") or ""), "Play without a Human team is refused in words: " + str(out["noHuman"]["start"].get("error")))
        report("Human" in (out["noHuman"]["run"].get("error") or ""), "a batch with a Human team is refused in words: " + str(out["noHuman"]["run"].get("error")))
        ar = out["page"].get("arrow") or out.get("arrow")
        report(bool(ar) and ar["blocked"] and ar["after"] == ar["facing"] and ar["before"] != ar["after"], f"a turn arrow works with another unit in the hex it points at ({ar})")
        pg = out["page"]
        report(pg["over"] and {"deploy", "movement", "target", "declaration"} <= set(pg["kinds"]), f"the real play page played a whole battle by taps (questions seen: {sorted(pg['kinds'])})")
        report(not out["errors"], "no page error" + (": " + "; ".join(out["errors"][:3]) if out["errors"] else ""))
        print(f"(the browser played two battles in {took:.0f} s)")
    finally:
        lab.terminate(); httpd.shutdown()
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
