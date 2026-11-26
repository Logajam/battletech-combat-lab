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
            ans = {"target": None if r.get("secondary") else r["enemies"][0]["id"]}
        elif k == "declaration":
            ans = {"weapons": [w["id"] for w in r["weapons"] if w["in_range"] and not w["needs_twist"]]}
        elif k == "stand_up":
            ans = {"stand": True}
        elif k in ("boost", "jump_boost"):
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
  if (k === "target") return { target: r.secondary ? null : r.enemies[0].id };
  if (k === "declaration") return { weapons: r.weapons.filter((w) => w.in_range && !w.needs_twist).map((w) => w.id) };
  if (k === "stand_up") return { stand: true };
  if (k === "boost" || k === "jump_boost") return { use: false };
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
  // ---- 3: the real play page, started as the Lab page starts it, tapped through. THE OVERLAY UI (INTEGRATION__UI_SYNC.md Section 14): the
  // map fills the screen, the panels lie over it, Commit is held, the inspector opens on a long press.
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base + "/index.html");
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SETUP);
  await page.goto(base + "/play.html");
  const kinds = new Set();
  let over = false;
  const box = async (sel) => { const l = page.locator(sel).first(); if (!(await l.count())) return null; return l.boundingBox(); };
  const tapAt = async (sel) => { const b = await box(sel); if (!b) return false; await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2); return true; };
  const pressAt = async (sel, ms) => { const b = await box(sel); if (!b) return false; await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down(); await page.waitForTimeout(ms); await page.mouse.up(); return true; };
  const hold = () => pressAt('.commit:not([disabled])', 850);
  for (let step = 0; step < 600; step++) {
    await page.waitForFunction(() => window.__bm && (window.__bm.req || window.__bm.over), null, { timeout: 120000 });
    const st = await page.evaluate(() => ({ kind: window.__bm.req && window.__bm.req.kind, over: window.__bm.over, seq: window.__bm.seq }));
    if (st.over) { over = true; break; }
    kinds.add(st.kind);
    // situational awareness (Daniel's session 35 work order): the turn line's count of units to move, the done mark, attack lines, Jump on the MP display
    const aw = await page.evaluate(() => ({ title: /to move: /.test(document.getElementById('phase').innerText), moved: !!document.querySelector('#strip .fchip.done'), atk: document.querySelectorAll('#map [data-atk]').length > 0, jump: /Jump/.test((document.querySelector('.mpw .hint') || {}).textContent || "") }));
    out.aware = out.aware || {}; for (const k of Object.keys(aw)) out.aware[k] = out.aware[k] || aw[k];
    // the combat report opens by itself once the firing phase is over; it is on top of every screen and button until closed
    if (!out.pop && await page.evaluate(() => document.getElementById('report').style.display === 'block')) {
      out.pop = await page.evaluate(() => { const r = document.getElementById('report'), b = document.querySelector('.commit'); const bb = b.getBoundingClientRect(); const top = document.elementFromPoint(bb.x + bb.width / 2, bb.y + bb.height / 2); return { title: document.getElementById('rtitle').textContent, onTop: !!top && r.contains(top), shots: r.querySelectorAll('.rs').length, heads: r.querySelectorAll('.rh').length, fmt: !/\[Ranged\]/.test(r.innerText) }; });
    }
    if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
    if (st.kind === 'deploy') { await page.locator('[data-deploy]').first().dispatchEvent('click'); await page.waitForTimeout(100); await hold(); }
    else if (st.kind === 'stand_up') {
      // standing is planned with the move (bug A2; Section 14 G2): Stand up beside the MP display, nothing is rolled until Commit is held
      await page.waitForFunction(() => !!window.__bm.mv, null, { timeout: 20000 }).catch(() => {});
      await tapAt('[data-act="standup"]'); out.stand = await page.evaluate(() => ({ on: __bm.standOn, label: document.querySelector('.commit .lab').textContent }));
      await hold();
    }
    else if (st.kind === 'boost') await tapAt('[data-act="boost"][data-v="0"]');
    else if (st.kind === 'jump_boost') await tapAt('[data-act="jump-boost"][data-v="0"]');
    else if (st.kind === 'movement' || st.kind === 'move_order') {
      await page.waitForFunction(() => !!window.__bm.mv || (window.__bm.req && window.__bm.req.kind === 'move_order' && window.__bm.views[window.__bm.sel]), null, { timeout: 20000 }).catch(() => {});
      const hex = await page.evaluate(() => { const v = __bm.mv; if (!v) return null; const o = v.options.filter((x) => x.mode === 'Walk').sort((a, b) => b.mp - a.mp)[0] || v.options[0]; return o && o.hex; });
      if (hex && !out.arrow) {
        // the turn arrows still work when another unit stands in the hex they point at: pick the cheapest hex with several facings,
        // put a friend next to it where an arrow points, and tap that arrow with a real mouse click
        const near = await page.evaluate(() => { const r = __bm.mv; const by = {}; r.options.forEach((o) => (by[o.hex] = by[o.hex] || new Set()).add(o.facing)); const hs = Object.keys(by).filter((h) => by[h].size > 1); hs.sort((a, b) => Math.min(...r.options.filter((o) => o.hex === a).map((o) => o.mp)) - Math.min(...r.options.filter((o) => o.hex === b).map((o) => o.mp))); return hs[0] || null; });
        if (near) {
          await page.locator(`[data-reach="${near}"]`).first().dispatchEvent('click');
          await page.waitForSelector('[data-arrow]');
          await page.waitForTimeout(500);   // the 3D view draws the arrows again when its camera or size settles: let it
          const probe = await page.evaluate(() => {
            const f = [...document.querySelectorAll('[data-arrow]')][0]; if (!f) return null;
            const DIRS = { N: 4, NE: 5, SE: 0, S: 1, SW: 2, NW: 3 }; const facing = f.dataset.arrow;
            const target = neighbours(__bm.dest)[DIRS[facing]];
            const friend = __bm.units.find((u) => u.id !== __bm.mv.unit && u.team === __bm.myTeam && !u.destroyed);
            if (friend) { friend.hex = target; redraw(); }
            const g = document.querySelector(`[data-arrow="${facing}"]`).getBoundingClientRect();
            return { facing, x: g.x + g.width / 2, y: g.y + g.height / 2, before: __bm.facing, blocked: !!friend };
          });
          await page.waitForTimeout(400);
          if (probe) { await page.mouse.click(probe.x, probe.y); await page.waitForTimeout(100); out.arrow = { ...probe, after: await page.evaluate(() => __bm.facing) }; }
        }
      }
      if (hex && out.arrow && !out.way) {
        // waypoints: tap a hex, then another hex of the re-lit range: two numbered waypoints, the last is the destination; Undo takes one back
        const first = await page.evaluate(() => { const r = __bm.mv; const o = r.options.filter((x) => x.mode === 'Walk' && x.mp >= 1 && x.mp < r.walk).sort((a, b) => a.mp - b.mp)[0]; return o ? o.hex : null; });
        if (first) {
          await page.evaluate(() => { __bm.way = []; __bm.wrIdx = null; __bm.dest = null; });
          await page.locator(`[data-reach="${first}"]`).first().dispatchEvent('click');
          await page.waitForFunction(() => __bm.way.length === 1);
          const second = await page.evaluate((f) => Object.keys(__bm.wrIdx).find((h) => h !== f), first);
          if (second) {
            await page.locator(`[data-reach="${second}"]`).first().dispatchEvent('click');
            await page.waitForFunction(() => __bm.way.length === 2, null, { timeout: 5000 }).catch(() => {});
            out.way = await page.evaluate(() => ({ n: __bm.way.length, dest: __bm.dest, marks: document.querySelectorAll('#map circle[fill="#fff"][stroke="#000"]').length, label: document.querySelector('.commit .lab').textContent }));
            await tapAt('[data-act="undo"]');
            await page.waitForFunction(() => __bm.way.length === 1, null, { timeout: 5000 }).catch(() => {});
            out.way.afterUndo = await page.evaluate(() => __bm.way.length);
          } else out.way = { n: 1, skipped: true };
        }
      }
      if (hex) { await page.locator(`[data-reach="${hex}"]`).first().dispatchEvent('click'); await page.waitForTimeout(150); }
      // Commit is held: a plain tap must not commit
      if (!out.tapIgnored && await page.evaluate(() => !!window.__bm.mv)) { await tapAt('.commit:not([disabled])'); await page.waitForTimeout(150); out.tapIgnored = await page.evaluate((s) => !!window.__bm.req && window.__bm.seq === s, st.seq); }
      await hold();
    }
    else if (st.kind === 'spot') await tapAt('[data-act="spot"][data-id=""]');
    else if (st.kind === 'tag') await page.evaluate(() => send({ target: null }));
    else if (st.kind === 'target') {
      // the fire screen: weapons in the critical-table layout round the middle, any number of targets, then Fire! (the page plays the
      // engine's questions from the plan)
      await page.waitForFunction(() => window.__bm.fire && window.__bm.decl, null, { timeout: 20000 }).catch(() => {});
      if (!out.target && await page.evaluate(() => !!window.__bm.decl)) {
        if (out.leak === undefined) out.leak = await page.evaluate(() => { const i = __bm.shown.map((l) => /=== TURN/.test(l)).lastIndexOf(true); return __bm.shown.slice(i + 1).filter((l) => /\[Ranged\]|\[Heat\]|rolled|Firing order|Movement select/.test(l) && !/^\s*Initiative/.test(l) && !/\[TAG\]/.test(l)); });   // the Initiative roll opens the turn and TAG is resolved before the ranged phase (p.200): no spoilers
        const before = await page.evaluate(() => __bm.fire.tcur);
        await tapAt('[data-act="step"][data-team="f"][data-d="1"]'); await page.waitForTimeout(250);
        const base = await page.evaluate((b) => ({ rows: document.querySelectorAll('#ring .wb').length, tn: document.querySelectorAll('#ring .wb .tn').length, pills: document.querySelectorAll('#map [data-tn-pill]').length, moved: __bm.fire.tcur !== b || __bm.req.enemies.length === 1, hold: /Hold fire/.test(document.querySelector('.commit .lab').textContent) }), before);
        // a long press on a to-hit number opens the inspector with its line items, on top of everything
        await pressAt('#ring .wb .tn', 700); await page.waitForTimeout(250);
        const card = await page.evaluate(() => { const c = document.getElementById('insp'); const r = c.getBoundingClientRect(); const top = document.elementFromPoint(r.x + 30, r.y + r.height / 2); return { shown: c.classList.contains('open'), rows: c.querySelectorAll('.ib tr').length, total: !!c.querySelector('.ib tr.tot'), onTop: !!top && c.contains(top), tab: (c.querySelector('.it button.on') || {}).textContent }; });
        await page.keyboard.press('Escape');
        // two targets: a weapon at this one, then another weapon at the next
        await tapAt('#ring .wb.rdy'); await page.waitForTimeout(200);
        await tapAt('[data-act="step"][data-team="f"][data-d="1"]'); await page.waitForTimeout(300);
        await tapAt('#ring .wb.rdy'); await page.waitForTimeout(250);
        const plan = await page.evaluate(() => ({ weapons: __bm.fire.assign.size, targets: new Set(__bm.fire.assign.values()).size, lit: document.querySelectorAll('#ring .wb.on, #ring .wb.else').length, label: document.querySelector('.commit .lab').textContent }));
        // a long press on a chip: the inspector on that unit (its weapons, armour pips, rear pips)
        await pressAt('#strip .fchip', 700); await page.waitForTimeout(250);
        const unitPage = await page.evaluate(() => ({ tab: (document.querySelector('#insp .it button.on') || {}).textContent, weapons: document.querySelectorAll('#insp .ib .wt tr').length, pips: document.querySelectorAll('#insp .ib .pips i').length, rear: document.querySelectorAll('#insp .ib .pips.rear i').length }));
        await page.keyboard.press('Escape');
        // a wing opens from its tab and remembers its page
        await tapAt('.edge.R'); await page.waitForTimeout(250);
        const wing = await page.evaluate(() => ({ open: document.getElementById('wingR').classList.contains('open'), tab: (document.querySelector('#wingR .wh button.on') || {}).textContent, body: document.querySelector('#wingR .wbody').innerText.length }));
        await page.keyboard.press('Escape');
        out.panel = { rear: unitPage.rear, report: await page.evaluate(() => !!document.querySelector('#pnF #rep-btn') && !!document.querySelector('#pnE [data-act="rec"]') && !!document.querySelector('#pnE [data-act="menu"]')), line: await page.evaluate(() => document.querySelectorAll('#map line').length), rows: base.rows, assigned: plan.lit, weapons: unitPage.weapons, pips: unitPage.pips, unitTab: unitPage.tab, wing };
        out.target = { ...base, card, plan };
      }
      await hold();
    }
    else if (st.kind === 'declaration') { await tapAt('#ring .wb.rdy'); await hold(); }
    else if (st.kind === 'physical') {
      if (!out.phys) out.phys = await page.evaluate(() => ({ boxes: document.querySelectorAll('#ring .wb').length, blocked: document.querySelectorAll('#ring .wb.blk').length }));
      await tapAt('#ring .wb.rdy'); await hold();
    }
    else if (st.kind === 'end_phase') await hold();
    await page.waitForFunction((s) => !window.__bm.req || window.__bm.seq !== s || window.__bm.over, st.seq, { timeout: 120000 }).catch(() => { errors.push("the page stayed on a " + st.kind + " question"); });
  }
  out.steps = kinds.size; out.lastKind = await page.evaluate(() => ({ kind: window.__bm.req && window.__bm.req.kind, seq: window.__bm.seq, over: window.__bm.over, phase: document.getElementById('phase').innerText }));
  out.page = { lastKind: out.lastKind, aware: out.aware, pop: out.pop, leak: out.leak, over, kinds: [...kinds], arrow: out.arrow, panel: out.panel, way: out.way, target: out.target, tapIgnored: out.tapIgnored, stand: out.stand, phys: out.phys };
  // ---- 5: a Fire! plan never answers a LATER question by itself (Daniel's bugs B10 / B15, 2026-11-22: "skip TAG ended my firing
  // phase"). One Raven (it carries TAG) against one Atlas: each turn the real "Skip TAG" button, then a weapon and the real Fire!
  // button. With one enemy the engine never asks "another target?", so the old page kept the plan and answered the Raven's NEXT
  // target question with "hold fire" by itself. Every answer the page sends is logged with whether a tap made it.
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + "/index.html");
  const SOLO = { teams: [
    { name: "Red", colour: "#4b8fd8", bot: "human", units: [{ unit: "meks/3050U/Raven RVN-3L.mtf", gunnery: 4, piloting: 5 }] },
    { name: "Blue", colour: "#d86a4b", bot: "gladiator", units: [{ unit: "Atlas AS7-K.mtf", gunnery: 4, piloting: 5 }] }],
    board: "16x17_Grassland_1.board", battles: 1, seed: 5, max_turns: 10 };
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SOLO);
  await page.goto(base + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  await page.evaluate(() => { const o = window.send; window.__sent = []; window.__tap = false; window.send = (a) => { __sent.push({ kind: __bm.req && __bm.req.kind, unit: __bm.req && __bm.req.unit, tap: window.__tap }); window.__tap = false; return o(a); }; });
  const tapSel = async (sel) => { await page.evaluate(() => { window.__tap = true; }); const b = await page.locator(sel).first().boundingBox(); await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2); };
  const holdCommit = async () => { await page.evaluate(() => { window.__tap = true; }); const b = await page.locator('.commit:not([disabled])').first().boundingBox(); await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down(); await page.waitForTimeout(850); await page.mouse.up(); };
  const solo = { fired: 0, tags: 0, over: false };
  let last = -1;
  for (let step = 0; step < 400; step++) {
    await page.waitForFunction((l) => window.__bm && ((window.__bm.req && window.__bm.seq !== l) || window.__bm.over), last, { timeout: 120000 });
    const st = await page.evaluate(() => ({ kind: __bm.req && __bm.req.kind, over: __bm.over, seq: __bm.seq }));
    if (st.over) { solo.over = true; break; }
    last = st.seq;
    if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
    if (st.kind === 'tag') {
      // the second time: designate (bug B16: the TAG line, with its number's parts, is in the report before the ranged phase); then skip
      solo.tags++;
      if (solo.tags === 2 && await page.locator('[data-act="tag"][data-aim]').count()) { solo.designated = true; await tapSel('[data-act="tag"][data-aim]'); }
      else await tapSel('[data-act="tag"][data-id=""]');
    }
    else if (st.kind === 'target') {
      if (solo.designated && solo.tagShown === undefined) solo.tagShown = await page.evaluate(() => ({ line: __bm.shown.some((l) => /\[TAG\].*gunnery \d/.test(l)), html: /TAG: .*needs \d+/.test(document.getElementById('rbody') ? document.getElementById('rbody').innerText : "") }));
      if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
      await page.waitForFunction(() => !__bm.req || __bm.req.kind !== 'target' || (__bm.fire && __bm.fire.pvt.size), null, { timeout: 20000 }).catch(() => {});
      const ok = await page.evaluate(() => { const F = __bm.fire; if (!F) return false; for (const [id, t] of F.pvt) { const w = t.req && t.req.weapons.find((x) => x.in_range); if (w) { setTcur(id); __bm.decl.sel.add(w.id); syncAssign(); return true; } } return false; });
      if (ok) { solo.fired++; await page.evaluate(() => redraw()); await holdCommit(); } else if (await page.evaluate(() => !!(__bm.req && __bm.req.kind === 'target'))) await holdCommit();
    }
    else await page.evaluate(() => { window.__tap = true; const r = __bm.req, k = r.kind;
      if (k === "deploy") send({ hex: r.hexes[0], facing: "N" });
      else if (k === "move_order") send({ unit: r.candidates[0] });
      else if (k === "movement") {   // close in on the Atlas (the Raven's own guns reach 9 hexes)
        const foe = __bm.units.find((u) => u.team !== __bm.myTeam && u.hex && !u.destroyed);
        const o = r.options.slice().sort((a, b) => (foe ? dist(a.hex, foe.hex) - dist(b.hex, foe.hex) : 0) || b.mp - a.mp)[0];
        send(o ? { hex: o.hex, facing: o.facing, mode: o.mode } : { stay: true }); }
      else if (k === "stand_up") send({ stand: true });
      else if (k === "physical") send({ kind: null });
      else if (k === "end_phase") send({});
      else if (k === "declaration") send({ weapons: [] });
      else send({ target: null, use: false }); });
  }
  // Initiative shown (Daniel, 2026-11-24): the title-bar chip with the throws, and the report's Initiative lines carry the dice
  solo.init = await page.evaluate(() => ({ lines: __bm.log.filter((l) => /Initiative/.test(l)).length, rolled: __bm.log.filter((l) => /Initiative.*\(rolled [^)]*\d/.test(l)).length }));
  const sent = await page.evaluate(() => __sent);
  // GET RESULTS (bug B21): at the end the commit button becomes Get Results, which opens the Lab's Results tab with this one battle
  if (solo.over) {
    if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
    solo.getResults = await page.evaluate(() => !!document.querySelector('#ask [data-act="get-results"]'));
    if (solo.getResults) {
      await page.locator('[data-act="get-results"]').click();
      await page.waitForURL(/index\.html/, { timeout: 30000 }).catch(() => {});
      await page.waitForFunction(() => document.getElementById('results') && !document.getElementById('results').hidden, null, { timeout: 60000 }).catch(() => {});
      solo.results = await page.evaluate(() => ({ shown: !document.getElementById('results').hidden, battles: document.getElementById('results').innerText.includes('1 battles') }));
    }
  }
  // a target answer nobody tapped is right only as the plan's "no more targets" straight after its own declaration
  solo.auto = sent.filter((x, i) => x.kind === 'target' && !x.tap && !(i > 0 && sent[i - 1].kind === 'declaration' && sent[i - 1].unit === x.unit)).length;
  out.solo = solo;
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
        pn = out["page"].get("panel") or {}
        report(pn.get("rows", 0) > 0 and pn.get("assigned", 0) > 0 and pn.get("weapons", 0) > 1 and pn.get("pips", 0) > 20 and pn.get("unitTab") == "Unit", f"the weapon boxes stand round the middle, a tap turns one on, a long press on a chip opens the inspector on Unit with its weapons and armour ({pn})")
        wg = pn.get("wing") or {}
        report(wg.get("open") and wg.get("tab") == "Weapons" and wg.get("body", 0) > 20, f"a wing opens from its tab on its phase's page (Weapon Attack: right = Weapons) ({wg})")
        tg = out["page"].get("target") or {}
        report(out["page"].get("leak") == [], f"the report holds back the firing, physical and heat phases and the bots' reasoning until the phase is over ({out['page'].get('leak')})")
        report(tg.get("rows", 0) > 0 and tg.get("tn", 0) > 0 and tg.get("pills", 0) > 0 and tg.get("moved") and tg.get("hold"), f"the fire screen shows the weapon boxes with their numbers, the enemy hexes carry a number pill, the strip's arrows step the target, Commit says Hold fire ({tg})")
        cd = tg.get("card") or {}
        report(cd.get("shown") and cd.get("rows", 0) >= 4 and cd.get("total") and cd.get("onTop") and cd.get("tab") == "To-hit", f"a long press on a number opens the inspector's To-hit page, on top of everything ({cd})")
        pp = out["page"].get("pop") or {}
        report(pp.get("title") == "Combat report" and pp.get("onTop") and pp.get("heads", 0) >= 1 and pp.get("fmt"), f"a formatted combat report opens by itself after the firing phase, on top of every button ({pp})")
        pl = tg.get("plan") or {}
        report(pl.get("weapons", 0) >= 1 and pl.get("label") == "Fire!", f"weapons can be assigned to targets, several targets in one plan, Commit says Fire! ({pl})")
        report(bool(out["page"].get("tapIgnored")), "a plain tap on Commit does not commit; holding it does")
        report(pn.get("rear", 0) > 0 and pn.get("report") and pn.get("line", 0) > 0, f"the Unit page shows rear-armour pips, Report sits on the Active line with Menu and REC on the title line, and the fire step draws the attack line ({pn})")
        wy = out["page"].get("way") or {}
        report(wy.get("n") == 2 and wy.get("marks", 0) >= 2 and wy.get("afterUndo") == 1, f"two waypoints can be planned and undone one by one ({wy})")
        so = out.get("solo") or {}
        report(so.get("over") and so.get("fired", 0) >= 2 and so.get("tags", 0) >= 2 and so.get("auto") == 0, f"after Skip TAG and Fire! the page never answers a later fire question by itself (B10 / B15; {so})")
        ts = so.get("tagShown") or {}
        report(not so.get("designated") or (ts.get("line") and ts.get("html")), f"a TAG attack is in the report, its number's parts spelled out, before the ranged phase (B16; {ts})")
        rs = so.get("results") or {}
        report(so.get("getResults") and rs.get("shown") and rs.get("battles"), f"at the end Get Results opens the Lab's Results tab with the played battle (B21; {so.get('getResults')}, {rs})")
        ini = so.get("init") or {}
        report(ini.get("lines", 0) > 0 and ini.get("rolled") == ini.get("lines"), f"every turn's Initiative dice are shown: each report line carries the dice ({ini})")
        aw = out["page"].get("aware") or {}
        report(aw.get("title") and aw.get("moved") and aw.get("atk") and aw.get("jump"), f"the turn line counts the units still to move, moved units carry a check, attack lines are drawn and a jumper's MP display offers Jump ({aw})")
        ph = out["page"].get("phys")
        if ph is not None:
            report(ph.get("boxes", 0) > 0, f"the Physical Attack Phase shows its attacks as boxes in the limbs' places ({ph})")
        pg = out["page"]
        report(pg["over"] and {"deploy", "target"} <= set(pg["kinds"]) and bool({"movement", "move_order"} & set(pg["kinds"])), f"the real play page played a whole battle by taps (questions seen: {sorted(pg['kinds'])}; at the end: {pg.get('lastKind')})")
        report(not out["errors"], "no page error" + (": " + "; ".join(out["errors"][:3]) if out["errors"] else ""))
        print(f"(the browser played two battles in {took:.0f} s)")
    finally:
        lab.terminate(); httpd.shutdown()
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
