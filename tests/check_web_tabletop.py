"""
tests/check_web_tabletop.py - THE 3D TABLETOP VIEW IN THE BROWSER BUILD (PROJECT_MAP P10, build step 2: the board preview).

    python tests/check_web_tabletop.py [--rebuild]

Needs node + Playwright and a built web_lab/ (built when missing; it needs the wasm32 target). Serves web_lab/ the way a real host does and
drives the real play page (play.html) in headless Chromium with software WebGL:
  1. the flat view is the default and does NOT download three.js (the page that never asks for 3D stays light);
  2. ?view=3d loads three.js and tabletop.js, builds the board from the engine's own board data (one tile for every hex, the terrain art in
     place), and draws it (the canvas is not empty);
  3. the camera answers the page's gestures through the map view: the wheel zooms, one finger pans, a right-drag turns and tilts, two fingers
     twist and tilt, the tilt button cycles, the fit button fits; a long press on a hex opens the hex card (the view finds the hex under the
     finger); the Menu item switches back to the flat view and the flat layers are shown again;
  4. a browser with no WebGL keeps the flat map, says so, and has no page error.
Exit code 0 = every check passed; 77 = skipped (no node / Playwright / wasm32 target).
"""
import argparse, http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO_ROOT, "web_lab")
SETUP = {"teams": [
    {"name": "Red", "colour": "#4b8fd8", "bot": "human", "units": [{"unit": "Atlas AS7-K.mtf", "gunnery": 4, "piloting": 5}]},
    {"name": "Blue", "colour": "#d86a4b", "bot": "gladiator", "units": [{"unit": "Awesome AWS-8Q.mtf", "gunnery": 4, "piloting": 5}]}],
    "board": "16x17_Military_Base_1.board", "battles": 1, "seed": 11, "max_turns": 100}


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Quiet(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):   # a browser closing a connection is not an error here
        pass


class Isolated(http.server.SimpleHTTPRequestHandler):
    """Static files plus the headers that make a page cross-origin isolated (what coi-sw.js adds on a real host)."""
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, *a):
        pass


NODE = r"""
const { chromium } = require('playwright');
(async () => {
  const [base, setupFile] = process.argv.slice(2); const setup = JSON.parse(require('fs').readFileSync(setupFile));
  const out = { errors: [] };
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'] });
  const open = async (query, noWebgl) => {
    const ctx = await b.newContext({ viewport: { width: 1000, height: 760 } });
    if (noWebgl) await ctx.addInitScript(() => { const g = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/i.test(t) ? null : g.call(this, t, ...a); }; });
    const page = await ctx.newPage(); page.on('pageerror', (e) => out.errors.push(String(e))); page.on('console', (m) => { if (m.type() === 'error' && !/WebGL|GPU/i.test(m.text())) out.errors.push(m.text().slice(0, 160)); });
    await page.goto(base + '/index.html'); await page.evaluate((s) => localStorage.setItem('bm_play_setup', JSON.stringify(s)), setup);
    await page.goto(base + '/play.html' + query);
    await page.waitForFunction(() => window.__bm && (window.__bm.req || window.__bm.over), null, { timeout: 120000 });
    return page;
  };
  // ---- 1: the flat view is the default and loads no three.js
  let page = await open('');
  out.flat = await page.evaluate(() => ({ mode: MV.mode, three: typeof THREE !== 'undefined', tabletop: !!document.getElementById('tabletop'), hexes: document.querySelectorAll('#map [data-hex]').length }));
  await page.close();
  // ---- 2 and 3: ?view=3d
  page = await open('?view=3d');
  await page.waitForFunction(() => document.querySelector('#tabletop canvas'), null, { timeout: 30000 }); await page.waitForTimeout(1500);
  out.t3d = await page.evaluate(() => { const V = MV.tabletop().three, c = document.querySelector('#tabletop canvas'); return { mode: MV.mode, hexes: V.M.list.length, tiles: V.tilesS.count + V.tilesG.count, caps: Object.keys(V.caps).length, props: (V.propSets || []).length, canvas: [c.width, c.height], flatHidden: MV.layers.map.style.display === 'none' }; });
  // the picture is not empty: count the pixels that differ from the corner's background
  out.pixels = await page.evaluate(async () => { const c = document.querySelector('#tabletop canvas'); MV.tabletop().render(); const t = document.createElement('canvas'); t.width = 64; t.height = 32; const g = t.getContext('2d'); g.drawImage(c, 0, 0, 64, 32); const d = g.getImageData(0, 0, 64, 32).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 20 && (d[i] > 40 || d[i + 1] > 40 || d[i + 2] > 40)) n++; return n; });
  const cam = () => page.evaluate(() => { const c = MV.tabletop().camera; return { yaw: c.yaw, tilt: c.tilt, dist: c.dist, tx: c.tx, tz: c.tz }; });
  const box = await page.locator('#map').boundingBox(), cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  const c0 = await cam(); await page.mouse.move(cx, cy); await page.mouse.wheel(0, -300); await page.waitForTimeout(250); const c1 = await cam(); out.wheel = [c0.dist, c1.dist];
  await page.mouse.down(); await page.mouse.move(cx + 80, cy + 40, { steps: 6 }); await page.mouse.up(); await page.waitForTimeout(200); const c2 = await cam(); out.pan = [c1.tx, c1.tz, c2.tx, c2.tz];
  await page.mouse.move(cx, cy); await page.mouse.down({ button: 'right' }); await page.mouse.move(cx + 100, cy - 40, { steps: 6 }); await page.mouse.up({ button: 'right' }); await page.waitForTimeout(200); const c3 = await cam(); out.orbit = [c2.yaw, c2.tilt, c3.yaw, c3.tilt];
  const two = (kind) => page.evaluate(async (kind) => {
    const el = document.getElementById('map'), r = el.getBoundingClientRect(), mk = (type, id, x, y) => el.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch', clientX: r.left + x, clientY: r.top + y, bubbles: true, button: 0, buttons: 1 }));
    const cx = r.width / 2, cy = r.height / 2, A = [cx - 80, cy], B = [cx + 80, cy]; mk('pointerdown', 11, ...A); mk('pointerdown', 12, ...B);
    for (let i = 1; i <= 14; i++) { const f = i / 14; let a, b; if (kind === 'twist') { const th = 35 * f * Math.PI / 180; a = [cx - 80 * Math.cos(th), cy - 80 * Math.sin(th)]; b = [cx + 80 * Math.cos(th), cy + 80 * Math.sin(th)]; } else { a = [A[0], A[1] + 60 * f]; b = [B[0], B[1] + 60 * f]; }
      mk('pointermove', 11, ...a); mk('pointermove', 12, ...b); await new Promise((r) => setTimeout(r, 10)); }
    mk('pointerup', 11, 0, 0); mk('pointerup', 12, 0, 0); }, kind);
  await two('twist'); await page.waitForTimeout(200); const c4 = await cam(); out.twist = [c3.yaw, c4.yaw];
  await two('tilt'); await page.waitForTimeout(200); const c5 = await cam(); out.tilt = [c4.tilt, c5.tilt];
  await page.locator('#ztilt').click(); await page.waitForTimeout(150); const c6 = await cam(); out.tiltBtn = [c5.tilt, c6.tilt];
  await page.locator('#zfit').click(); await page.waitForTimeout(300); out.fit = await cam();
  out.hexAt = await page.evaluate(([x, y]) => MV.hexAt(x, y), [cx, cy]);
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.waitForTimeout(900); await page.mouse.up(); await page.waitForTimeout(200);
  out.card = await page.evaluate(() => { const c = document.getElementById('card'); return c.style.display === 'block' ? c.textContent.slice(0, 30) : null; });
  // units: pieces in the scene, the page's marks projected over them, and redrawn when the camera moves
  out.units = await page.evaluate(async () => {
    MV.setUnits([{ id: 1, hex: '0909', facing: 'SE', tons: 100, colour: '#4b8fd8', mech: 'Atlas AS7-K', sel: true }, { id: 2, hex: '0910', facing: 'N', tons: 35, colour: '#d86a4b', mech: 'Nobody X' }]);
    await new Promise((r) => setTimeout(r, 300)); const V = MV.tabletop().three, n0 = V.units ? V.units.children.length : 0;
    const poly = () => document.querySelector('#map polygon[points]'); const at = MV.at('0909'), p = MV.pt('0909', 1, 0);
    return { pieces: n0, sprites: Object.keys(window.MECH_SPRITES || {}).length, at, east: p[0] - at[0], scale: MV.scale('0909'), k: MV.k(), hexPts: MV.hexPts('0909').split(' ').length };
  });
  await page.click('#menu-btn'); await page.locator('#menu [data-act="view3d"]').click(); await page.waitForTimeout(600);
  out.back = await page.evaluate(() => ({ mode: MV.mode, canvas: !!document.getElementById('tabletop'), flatShown: MV.layers.map.style.display !== 'none', pref: localStorage.getItem('bm_view') }));
  await page.close();
  // ---- 4: no WebGL
  page = await open('?view=3d', true); await page.waitForTimeout(1500);
  out.nowebgl = await page.evaluate(() => ({ mode: MV.mode, canvas: !!document.getElementById('tabletop'), card: /needs WebGL/.test(document.getElementById('card').textContent), hexes: document.querySelectorAll('#map [data-hex]').length }));
  await page.close(); await b.close();
  console.log('RESULT ' + JSON.stringify(out));
})();
"""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--rebuild", action="store_true"); a = ap.parse_args()
    if not shutil.which("node"):
        print("SKIP: node is needed"); return 77
    node_path = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    if not os.path.isdir(os.path.join(node_path, "playwright")):
        print("SKIP: Playwright is not installed"); return 77
    stale = os.path.exists(os.path.join(WEB, "combatlab.wasm")) and any(
        os.path.getmtime(os.path.join(REPO_ROOT, "engine", "lab", "web", n)) > os.path.getmtime(os.path.join(WEB, "combatlab.wasm")) for n in ("tabletop.js", "mapview.js", "play.js", "play.html"))
    if a.rebuild or stale or not os.path.exists(os.path.join(WEB, "combatlab.wasm")):
        r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tools", "build_web_lab.py")], capture_output=True, text=True)
        if r.returncode != 0:
            print("SKIP: the web build failed here (no wasm32 target?)\n", r.stderr[-400:]); return 77
    port = free_port()
    httpd = Quiet(("127.0.0.1", port), lambda *args, **kw: Isolated(*args, directory=WEB, **kw))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        sf = os.path.join(tmp, "setup.json"); json.dump(SETUP, open(sf, "w")); nf = os.path.join(tmp, "probe.js"); open(nf, "w").write(NODE)
        p = subprocess.run(["node", nf, f"http://127.0.0.1:{port}", sf], capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path}, timeout=900)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    if not line:
        print("FAIL: the browser gave no result\n", p.stdout[-1500:], p.stderr[-1500:]); return 1
    o = json.loads(line[7:]); failures = 0

    def ck(ok, text):
        nonlocal failures
        print(f"{'ok  ' if ok else 'FAIL'} {text}"); failures += 0 if ok else 1

    ck(o["flat"]["mode"] == "top" and not o["flat"]["three"] and not o["flat"]["tabletop"] and o["flat"]["hexes"] > 200, f"the flat view is the default and loads no three.js ({o['flat']})")
    t = o["t3d"]
    ck(t["mode"] == "3d" and t["hexes"] == 272 and t["tiles"] == 272 and t["caps"] > 3 and t["props"] > 3, f"?view=3d builds the board from the engine's data ({t})")
    ck(t["flatHidden"] and o["pixels"] > 150, f"the flat layers step aside and the picture is not empty ({o['pixels']} lit pixels of 2048)")
    ck(o["wheel"][1] < o["wheel"][0], f"the wheel zooms {o['wheel']}")
    ck(abs(o["pan"][2] - o["pan"][0]) + abs(o["pan"][3] - o["pan"][1]) > 20, f"one finger pans {o['pan']}")
    ck(o["orbit"][2] != o["orbit"][0] and o["orbit"][3] != o["orbit"][1], f"a right-drag turns and tilts {o['orbit']}")
    ck(abs(o["twist"][1] - o["twist"][0]) > 5, f"two fingers twist {o['twist']}")
    ck(o["tilt"][1] != o["tilt"][0], f"two fingers together tilt {o['tilt']}")
    ck(o["tiltBtn"][1] != o["tiltBtn"][0], f"the tilt button cycles {o['tiltBtn']}")
    ck(o["fit"]["dist"] > 100, f"the fit button fits ({o['fit']['dist']:.0f})")
    ck(o["hexAt"] is not None and o["card"] and o["card"].startswith("Hex "), f"the view finds the hex under a point and a long press opens its card ({o['hexAt']}, {o['card']})")
    u = o["units"]
    ck(u["pieces"] >= 5 and u["sprites"] > 30 and u["hexPts"] == 6 and u["east"] > 5 and u["scale"] > 0.05 and u["k"] == 1, f"units stand on the table (bases and pictures) and the page's geometry is projected ({u})")
    ck(o["back"]["mode"] == "top" and not o["back"]["canvas"] and o["back"]["flatShown"] and o["back"]["pref"] == "top", f"the Menu item switches back to the flat view ({o['back']})")
    ck(o["nowebgl"]["mode"] == "top" and not o["nowebgl"]["canvas"] and o["nowebgl"]["card"] and o["nowebgl"]["hexes"] > 200, f"with no WebGL the flat map stays and says so ({o['nowebgl']})")
    ck(not o["errors"], f"no page error ({o['errors'][:2]})")
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
