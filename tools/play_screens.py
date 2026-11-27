"""
tools/play_screens.py - BASELINE / COMPARISON SCREENSHOTS OF THE LIVE PLAY PAGE (INTEGRATION__TIMELINE_SYNC.md, the REC layer build).

    python tools/play_screens.py OUTDIR [--web DIR] [--rec]   # take the set
    python tools/play_screens.py --compare DIR_A DIR_B        # list the shots that differ (small tolerance), write diff notes

The set: phone upright 390x844, phone landscape 844x390, desktop 1280x800; each in the 3D view and the flat (2D) view; one movement question,
one fire question with the weapon buttons showing, a wing open, the inspector open. A Raven against an Atlas on the Grassland board, seed 5,
a scripted player: the same pictures every run. Serves `web_lab/` with the isolation headers (rebuild it first: tests/check_web_play.py
--rebuild, or tools/build_web_lab.py if that is what builds it). With REC closed the page must look the same as the baseline (the REC layer
build's rule 0); `--rec` is for later: it opens the REC layer in each shot.
"""
import argparse, http.server, os, shutil, subprocess, sys, tempfile, threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "web_lab")

NODE = r"""
const { chromium } = require('playwright');
const [,, base, outdir, rec] = process.argv;
const SOLO = { teams: [
 { name: "Red", colour: "#4b8fd8", bot: "human", units: [{ unit: "meks/3050U/Raven RVN-3L.mtf", gunnery: 4, piloting: 5 }] },
 { name: "Blue", colour: "#d86a4b", bot: "gladiator", units: [{ unit: "Atlas AS7-K.mtf", gunnery: 4, piloting: 5 }] }],
 board: "16x17_Grassland_1.board", battles: 1, seed: 5, max_turns: 10 };
const POLICY = (r) => { const k = r.kind;
 if (k === "deploy") return { hex: r.hexes[0], facing: "N" }; if (k === "move_order") return { unit: r.candidates[0] };
 if (k === "movement") { let best = null; for (const o of r.options) { if (!best || o.mp > best.mp) best = o; } return best ? { hex: best.hex, facing: best.facing, mode: best.mode } : { stay: true }; }
 if (k === "target") return { target: r.secondary ? null : r.enemies[0].id }; if (k === "declaration") return { weapons: r.weapons.filter((w) => w.in_range && !w.needs_twist).map((w) => w.id) };
 if (k === "stand_up") return { stand: true }; if (k === "boost" || k === "jump_boost") return { use: false }; if (k === "spot" || k === "tag") return { target: null }; if (k === "end_phase") return {}; return { kind: r.kinds[0].kind }; };
const VIEWS = { phone: [390, 844], land: [844, 390], desk: [1280, 800] };
(async () => {
  const b = await chromium.launch();
  for (const [vn, [w, h]] of Object.entries(VIEWS)) for (const mode of ["3d", "top"]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage(); const errs = []; page.on('pageerror', (e) => errs.push(String(e)));
    await page.goto(base + "/index.html"); await page.waitForFunction(() => window.LAB_WASM && window.crossOriginIsolated, null, { timeout: 60000 });
    await page.evaluate((s) => { localStorage.setItem("bm_play_setup", JSON.stringify(s)); localStorage.removeItem("bm_save"); }, SOLO);
    await page.goto(base + "/play.html?view=" + mode); await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
    const step = async () => { const before = await page.evaluate(() => window.__bm.seq);
      await page.waitForFunction(() => window.__bm.req || window.__bm.over, null, { timeout: 120000 });
      await page.evaluate((src) => { const P = eval(src); window.send(P(window.__bm.req)); }, POLICY.toString());
      await page.waitForFunction((x) => (window.__bm.req && window.__bm.seq !== x) || window.__bm.over, before, { timeout: 120000 }); };
    const toKind = async (kinds, tries) => { for (let i = 0; i < tries; i++) { await page.waitForFunction(() => window.__bm.req || window.__bm.over, null, { timeout: 120000 }); if (await page.evaluate((k) => !!(window.__bm.req && k.includes(window.__bm.req.kind)), kinds)) return true; await step(); } return false; };
    const closeReport = async () => { if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click().catch(() => {}); };
    const shot = async (name) => { await page.waitForTimeout(900); await page.screenshot({ path: `${outdir}/${vn}_${mode}_${name}.png` }); };
    if (rec === "1") { /* later: open the REC layer in each shot */ }
    await toKind(["movement"], 40); await closeReport(); await shot("move");
    await page.evaluate(() => { UI.wing = { L: 1, R: 0 }; chrome(); }); await shot("wing"); await page.evaluate(() => { UI.wing = { L: 0, R: 0 }; chrome(); });
    await page.evaluate(() => openInsp("Unit")); await shot("insp"); await page.evaluate(() => { UI.insp = { open: 0 }; chrome(); });
    await toKind(["target", "declaration"], 40); await closeReport(); await shot("fire");
    if (errs.length) console.log("PAGE ERRORS " + vn + " " + mode + ": " + errs.slice(0, 2).join(" | "));
    await ctx.close();
  }
  await b.close(); console.log("shots done");
})();
"""


NODE_REC = NODE.split("const VIEWS")[0] + r"""
const VIEWS = { phone: [390, 844], land: [844, 390], desk: [1280, 800] };
(async () => {
  const b = await chromium.launch();
  for (const [vn, [w, h]] of Object.entries(VIEWS)) for (const mode of ["3d", "top"]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage(); const errs = []; page.on('pageerror', (e) => errs.push(String(e)));
    await page.goto(base + "/index.html"); await page.waitForFunction(() => window.LAB_WASM && window.crossOriginIsolated, null, { timeout: 60000 });
    await page.evaluate((s) => { localStorage.setItem("bm_play_setup", JSON.stringify(s)); localStorage.removeItem("bm_save"); }, SOLO);
    await page.goto(base + "/play.html?view=" + mode); await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
    const step = async () => { const before = await page.evaluate(() => window.__bm.seq);
      await page.waitForFunction(() => window.__bm.req || window.__bm.over, null, { timeout: 120000 });
      await page.evaluate((src) => { const P = eval(src); window.send(P(window.__bm.req)); }, POLICY.toString());
      await page.waitForFunction((x) => (window.__bm.req && window.__bm.seq !== x) || window.__bm.over, before, { timeout: 120000 }); };
    for (let i = 0; i < 160; i++) { await page.waitForFunction(() => window.__bm.req || window.__bm.over, null, { timeout: 120000 });
      const t = await page.evaluate(() => +((window.__bm.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1] || 0));
      if (t >= 4) break; await step(); }
    const closeReport = async () => { if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click().catch(() => {}); };
    await closeReport();
    const shot = async (name) => { await page.waitForTimeout(1200); await page.screenshot({ path: `${outdir}/${vn}_${mode}_${name}.png` }); };
    const gotoStep = (pred) => page.evaluate((src) => { const st = TT._st, P = eval(src); const i = st.steps.findIndex(P); if (i < 0) return -1;
      for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), bb = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); bb.value = j; bb.dispatchEvent(new Event('input', { bubbles: true })); return i; } } return -1; }, pred.toString());
    await page.evaluate(() => document.querySelector('[data-act="rec"]').click());
    await page.waitForFunction(() => document.getElementById('tt-strip') && document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 30000 });
    await shot("rec_live");
    const mv = await gotoStep((s) => s.k === "move" && s.turn >= 3 && s.unit); await shot("rec_move");
    const fr = await gotoStep((s) => s.k === "fire" && s.turn >= 2 && s.unit && s.target && TT._st.rec.events.some((e) => e.k === "ATTACK" && e.u === s.unit && e.t === s.turn)); await shot("rec_fire");
    await page.evaluate(() => document.querySelector('#tt-tabs [data-tt-tab="timelines"]').click()); await shot("rec_timelines");
    await page.evaluate(() => document.querySelector('#tt-tabs [data-tt-tab="report"]').click()); await shot("rec_reporttab");
    console.log(vn + " " + mode + " move=" + mv + " fire=" + fr + (errs.length ? " ERRORS " + errs.slice(0, 2).join(" | ") : ""));
    await ctx.close();
  }
  await b.close(); console.log("rec shots done");
})();
"""


class Isolated(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin"); self.send_header("Cross-Origin-Embedder-Policy", "require-corp"); super().end_headers()
    def log_message(self, *a): pass


def take(outdir, web, rec=False):
    os.makedirs(outdir, exist_ok=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: Isolated(*a, directory=web, **k))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    np = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        nf = os.path.join(tmp, "shots.js"); open(nf, "w").write(NODE_REC if rec else NODE)
        p = subprocess.run(["node", nf, f"http://127.0.0.1:{srv.server_address[1]}", os.path.abspath(outdir), "0"], capture_output=True, text=True, env={**os.environ, "NODE_PATH": np}, timeout=1700)
    srv.shutdown(); print(p.stdout[-1500:], p.stderr[-1500:]); return p.returncode


def compare(a, b, tol=0.002):
    from PIL import Image, ImageChops
    bad = 0
    for f in sorted(os.listdir(a)):
        if not f.endswith(".png"): continue
        if not os.path.exists(os.path.join(b, f)): print("MISSING", f); bad += 1; continue
        ia, ib = Image.open(os.path.join(a, f)).convert("RGB"), Image.open(os.path.join(b, f)).convert("RGB")
        if ia.size != ib.size: print("SIZE", f); bad += 1; continue
        d = ImageChops.difference(ia, ib).convert("L").point(lambda v: 255 if v > 24 else 0)
        frac = sum(1 for v in d.getdata() if v) / (ia.size[0] * ia.size[1])
        print(("DIFF %.4f " if frac > tol else "same %.4f ") % frac + f); bad += frac > tol
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("outdir", nargs="?"); ap.add_argument("--web", default=WEB); ap.add_argument("--compare", nargs=2); ap.add_argument("--rec", action="store_true")
    a = ap.parse_args()
    sys.exit(compare(*a.compare) if a.compare else take(a.outdir, a.web, a.rec))
