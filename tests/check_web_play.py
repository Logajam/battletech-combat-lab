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
const [,, base, setupFile, labBase] = process.argv;
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
  // ---- 6: SAVE AND RESUME (P15). Play a dozen answers, read the save the page keeps in this browser, open play.html?resume=1 in a NEW page: the
  // battle is played back to where it stopped and the SAME question is asked again, the units where they were; then the game is played to its
  // end and the save is dropped (a finished game is not resumed).
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + "/index.html");
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SOLO);
  await page.evaluate(() => localStorage.removeItem("bm_save"));
  await page.goto(base + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  const POLICY_SRC = POLICY.toString();
  const stepOnce = async (pg) => {
    await pg.waitForFunction(() => window.__bm.req || window.__bm.over, null, { timeout: 120000 });
    return pg.evaluate((src) => { if (window.__bm.over) return "over"; const P = eval(src); window.send(P(window.__bm.req)); return "sent"; }, POLICY_SRC);
  };
  const seqNow = () => page.evaluate(() => window.__bm.seq);
  for (let i = 0; i < 12; i++) { const before = await seqNow(); await stepOnce(page); await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); }
  const mid = await page.evaluate(() => ({ kind: __bm.req.kind, unit: __bm.req.unit === undefined ? null : __bm.req.unit, hexes: Object.fromEntries(__bm.units.map((u) => [u.id, u.hex])) }));
  await page.waitForTimeout(600);   // the save is written a moment after each answer
  const saved = await page.evaluate(() => { const f = JSON.parse(localStorage.getItem("bm_save") || "null"); return f && { n: f.orders.events.length, fmt: f.orders.order_format, last: f.orders.events[f.orders.events.length - 1] }; });
  const page2 = await ctx.newPage();
  page2.on('pageerror', (e) => errors.push(String(e)));
  await page2.goto(base + "/play.html?resume=1");
  await page2.waitForFunction(() => window.__bm && window.__bm.req, null, { timeout: 120000 });
  const back = await page2.evaluate(() => ({ kind: __bm.req.kind, unit: __bm.req.unit === undefined ? null : __bm.req.unit, hexes: Object.fromEntries(__bm.units.map((u) => [u.id, u.hex])), board: !!(__bm.board && Object.keys(__bm.board.hexes).length) }));
  // coming back with no address but this page (a dropped tab, a phone switched off): the unfinished game is resumed by itself
  const page3 = await ctx.newPage();
  page3.on('pageerror', (e) => errors.push(String(e)));
  await page3.goto(base + "/play.html");
  await page3.waitForFunction(() => window.__bm && window.__bm.req, null, { timeout: 120000 }).catch(() => {});
  const bare = await page3.evaluate(() => ({ kind: __bm.req && __bm.req.kind, unit: __bm.req && __bm.req.unit === undefined ? null : __bm.req && __bm.req.unit }));
  await page3.close();
  let endOver = false;
  for (let i = 0; i < 400 && !endOver; i++) { const before = await page2.evaluate(() => window.__bm.seq); if ((await stepOnce(page2)) === "over") break; await page2.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); endOver = await page2.evaluate(() => !!window.__bm.over); }
  await page2.waitForTimeout(600);
  out.resume = { bare, mid, back, saved, over: endOver, dropped: await page2.evaluate(() => localStorage.getItem("bm_save") === null) };
  // ---- 7: TIME TRAVEL (P4). Play a dozen answers, open the time-travel list, go back to an earlier question: a NEW page resumes with that question
  // asked again, the list before it unchanged, a reseed where the timeline starts, the old game kept as the parent; Back to the earlier timeline
  // returns to the question the first game was waiting on.
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + "/index.html");
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SOLO);
  await page.evaluate(() => localStorage.removeItem("bm_save"));
  await page.goto(base + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  for (let i = 0; i < 14; i++) { const before = await seqNow(); await stepOnce(page); await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); }
  const tt = {};
  tt.waiting = await page.evaluate(() => ({ kind: __bm.req.kind, unit: __bm.req.unit === undefined ? null : __bm.req.unit }));
  tt.before = await page.evaluate(() => ({ events: JSON.parse(JSON.stringify(SAVE.events)), marks: SAVE.marks.length }));
  await page.evaluate(() => timeTravelCard());   // the old card list: kept for this branch test until the REC layer's meddling replaces it
  tt.card = await page.evaluate(() => document.querySelectorAll('#card [data-act="branch"]').length);
  tt.pick = await page.evaluate(() => { const bs = [...document.querySelectorAll('#card [data-act="branch"]')]; const b = bs[Math.floor(bs.length / 2)]; const at = +b.dataset.at; const ev = SAVE.events[at]; b.click(); return { at, post: ev.post }; });
  await page.waitForURL(/resume=1/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && SAVE.parent, null, { timeout: 120000 }).catch(() => {});
  tt.asked = await page.evaluate(() => ({ kind: __bm.req.kind, unit: __bm.req.unit === undefined ? null : __bm.req.unit }));
  tt.file = await page.evaluate((at) => { const f = JSON.parse(localStorage.getItem("bm_save")); return { hasParent: !!f.parent, reseed: f.reseed || null, at: f.orders.events[at] }; }, tt.pick.at);
  tt.past = await page.evaluate((a) => { const f = JSON.parse(localStorage.getItem("bm_save")); return { n: f.orders.events.length, at: a }; }, tt.pick.at);
  // answer something, so the branch has a life of its own, then go back to the parent
  const bseq = await page.evaluate(() => __bm.seq); await stepOnce(page);
  await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, bseq, { timeout: 120000 });
  await page.waitForTimeout(600);
  await page.evaluate(() => backToParent());
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && !SAVE.parent, null, { timeout: 120000 }).catch(() => {});
  tt.parentAsked = await page.evaluate(() => ({ kind: __bm.req.kind, unit: __bm.req.unit === undefined ? null : __bm.req.unit }));
  await page.evaluate(() => forwardToChild());
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && SAVE.parent && SAVE.events.some((e) => e.reseed), null, { timeout: 120000 }).catch(() => {});
  tt.childAsked = await page.evaluate(() => ({ kind: __bm.req.kind, unit: __bm.req.unit === undefined ? null : __bm.req.unit, hasReseed: SAVE.events.some((e) => e.reseed) }));
  out.tt = tt;
  // ---- 8: THE REC LAYER, view part (prompt 2.1-2.4). REC opens the strip and the report panel (the bottom half, with its tabs); the sliders and
  // arrows move the board to the right sub-phase without touching the live game (the live units and question are the same afterwards, nothing is
  // answered); the Report button, on top of the panel, closes it and a slider reopens it; REC again closes the layer.
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + "/index.html");
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SOLO);
  await page.evaluate(() => localStorage.removeItem("bm_save"));
  await page.goto(base + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  for (let i = 0; i < 40; i++) { const before = await seqNow(); await stepOnce(page); await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); }
  if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
  const rec = {};
  rec.liveBefore = await page.evaluate(() => JSON.stringify({ u: __bm.units, r: __bm.req && __bm.req.kind, n: SAVE.events.length }));
  await page.evaluate(() => document.querySelector('[data-act="rec"]').click());
  await page.waitForFunction(() => document.getElementById('tt-strip') && document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 30000 });
  rec.open = await page.evaluate(() => { const r = document.getElementById('report').getBoundingClientRect(), H = window.innerHeight; return { strip: getComputedStyle(document.getElementById('tt-strip')).display !== 'none', report: document.getElementById('report').style.display, bottomHalf: r.top >= H * 0.45 && r.bottom >= H - 2, tabs: [...document.querySelectorAll('#tt-tabs button')].map((b) => b.textContent), repOnTop: document.getElementById('tt-repcopy').classList.contains('on'), steps: TT._st.steps.length, turns: TT._st.turnList.length }; });
  // a past movement step: the sliders, the log, the unit's place in the record
  rec.move = await page.evaluate(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "move" && s.turn >= 2 && s.unit);
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } }
    const s = st.steps[i]; return { i, unit: s.unit, hex: s.state[s.unit].hex, past: TT.past(), log: document.getElementById('tt-pane').innerText, readout: document.getElementById('tt-read').innerText, orders: s.orders }; });
  await page.waitForTimeout(500);
  rec.pastDraw = await page.evaluate(() => ({ path: !!document.querySelector('#map polyline'), ring: !!document.querySelector('#map polygon[stroke="#fff"]') }));
  // a past fire step: an arrow with its result
  rec.fire = await page.evaluate(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "fire" && s.unit && s.target);
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } }
    return { i }; });
  await page.waitForTimeout(500);
  rec.fireDraw = await page.evaluate(() => ({ arrow: [...document.querySelectorAll('#map text')].some((t) => /^\d+\/\d+/.test(t.textContent)), log: document.getElementById('tt-pane').innerText }));
  // taps on the map do nothing at a past step; the live game is untouched
  await page.mouse.click(200, 300); await page.waitForTimeout(300);
  rec.liveAfter = await page.evaluate(() => JSON.stringify({ u: __bm.units, r: __bm.req && __bm.req.kind, n: SAVE.events.length }));
  // the Report button (the copy on top of the panel) closes the panel; a slider reopens it
  await page.evaluate(() => document.getElementById('tt-repcopy').click());
  rec.closed = await page.evaluate(() => document.getElementById('report').style.display);
  await page.evaluate(() => { const a = document.getElementById('tt-b'); a.value = Math.max(0, +a.value - 1); a.dispatchEvent(new Event('input', { bubbles: true })); });
  rec.reopened = await page.evaluate(() => document.getElementById('report').style.display);
  // the arrows step one action: Live is the end
  await page.evaluate(() => document.querySelector('#tt-strip [data-tt="live"]').click());
  rec.live = await page.evaluate(() => ({ past: TT.past(), now: document.querySelector('#tt-strip .tt-live').classList.contains('now') }));
  await page.evaluate(() => document.querySelector('[data-act="rec"]').click());
  rec.shut = await page.evaluate(() => ({ strip: getComputedStyle(document.getElementById('tt-strip')).display, tabs: document.getElementById('tt-tabs').classList.contains('on'), rbody: document.getElementById('rbody').style.display, report: document.getElementById('report').style.display, open: TT.isOpen() }));
  out.rec = rec;
  // ---- 9: MEDDLING (prompt Section 3). Take over the Atlas's (the bot's) move at a past step: the page goes into a candidate timeline, the original save is
  // untouched, the first question is the Atlas's, the commit button reads "Meddle"; Live goes back to the first game exactly where it was; holding the answer
  // writes the branch (a reseed and a meddle in its list, the old game as its parent). Then a team handed to a bot (Teams tab) plays to the end and can be kept.
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + "/index.html");
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SOLO);
  await page.evaluate(() => { localStorage.removeItem("bm_save"); localStorage.removeItem("bm_try"); });
  await page.goto(base + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  for (let i = 0; i < 24; i++) { const before = await seqNow(); await stepOnce(page); await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); }
  if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
  await page.waitForTimeout(600);
  const med = {};
  med.orig = await page.evaluate(() => ({ kind: (__bm.req || {}).kind, unit: (__bm.req || {}).unit === undefined ? null : (__bm.req || {}).unit, n: JSON.parse(localStorage.getItem("bm_save")).orders.events.length }));
  await page.evaluate(() => document.querySelector('[data-act="rec"]').click());
  await page.waitForFunction(() => document.getElementById('tt-strip') && document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 30000 });
  med.step = await page.evaluate(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "move" && s.turn >= 2 && s.unit && /Atlas|Blue/.test(s.unit + (S.units.find((u) => u.name === s.unit) || {}).mech));
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } }
    return { i, unit: st.steps[i].unit, turn: st.steps[i].turn }; });
  await page.evaluate(() => document.querySelector('#tt-tabs [data-tt-tab="log"]').click());
  med.button = await page.evaluate(() => !!document.querySelector('#tt-pane [data-tt-do="meddle"]'));
  await page.evaluate(() => document.querySelector('#tt-pane [data-tt-do="meddle"]').click());
  await page.waitForURL(/resume=try/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && SAVE.candidate, null, { timeout: 120000 }).catch(() => {});
  await page.waitForFunction(() => document.getElementById('tt-strip') && document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 30000 }).catch(() => {});
  med.cand = await page.evaluate(() => ({ kind: (__bm.req || {}).kind, unit: (__bm.req || {}).unit === undefined ? null : (__bm.req || {}).unit, team: __bm.myTeam, who: (__bm.units.find((u) => u.id === ((__bm.req || {}).unit ?? ((__bm.req || {}).candidates || [])[0])) || {}).team, phase: document.getElementById('phase').innerText, url: location.search, label: (document.querySelector('.commit .lab') || {}).textContent, strip: document.getElementById('tt-strip') && document.getElementById('tt-strip').classList.contains('on'), saveN: JSON.parse(localStorage.getItem("bm_save")).orders.events.length, try: !!localStorage.getItem("bm_try"), tryBranch: JSON.parse(localStorage.getItem("bm_try")).orders.events.filter((e) => e.branch).map((e) => e.branch) }));
  // Live before holding Meddle: back to the first game, the save untouched
  await page.evaluate(() => document.querySelector('#tt-strip [data-tt="live"]').click());
  await page.waitForURL(/resume=1/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && !SAVE.candidate, null, { timeout: 120000 }).catch(() => {});
  med.back = await page.evaluate(() => ({ kind: (__bm.req || {}).kind, unit: (__bm.req || {}).unit === undefined ? null : (__bm.req || {}).unit, saveN: JSON.parse(localStorage.getItem("bm_save")).orders.events.length, try: !!localStorage.getItem("bm_try") }));
  // again, and this time hold the answer
  await page.evaluate(() => document.querySelector('[data-act="rec"]').click());
  await page.waitForFunction(() => document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 30000 });
  await page.evaluate(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "move" && s.turn >= 2 && s.unit && /Atlas|Blue/.test(s.unit + (S.units.find((u) => u.name === s.unit) || {}).mech));
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } } });
  await page.evaluate(() => document.querySelector('#tt-tabs [data-tt-tab="log"]').click());
  await page.evaluate(() => document.querySelector('#tt-pane [data-tt-do="meddle"]').click());
  await page.waitForURL(/resume=try/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && SAVE.candidate, null, { timeout: 120000 }).catch(() => {});
  const mseq = await seqNow(); await stepOnce(page);
  await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, mseq, { timeout: 120000 });
  await page.waitForTimeout(700);
  med.kept = await page.evaluate(() => { const f = JSON.parse(localStorage.getItem("bm_save")); return { cand: SAVE.candidate, hasTry: !!localStorage.getItem("bm_try"), parent: !!f.parent, branch: f.orders.events.filter((e) => e.branch).map((e) => e.branch) }; });
  out.med = med;
  // ---- 10: THE TEAMS TAB. Hand the human team (Red) to a bot from a past step of its own: the new timeline plays to the end without asking anything, and
  // "Keep this timeline" writes it (a control entry in its list, the old game as its parent).
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + "/index.html");
  await page.evaluate((s) => localStorage.setItem("bm_play_setup", JSON.stringify(s)), SOLO);
  await page.evaluate(() => { localStorage.removeItem("bm_save"); localStorage.removeItem("bm_try"); });
  await page.goto(base + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  for (let i = 0; i < 24; i++) { const before = await seqNow(); await stepOnce(page); await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); }
  if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
  await page.waitForTimeout(600);
  const tm = {};
  await page.evaluate(() => document.querySelector('[data-act="rec"]').click());
  await page.waitForFunction(() => document.getElementById('tt-strip') && document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 30000 });
  await page.evaluate(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "move" && s.turn >= 2 && s.unit && (S.units.find((u) => u.name === s.unit) || {}).team === "Red");
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } } });
  await page.evaluate(() => document.querySelector('#tt-tabs [data-tt-tab="teams"]').click());
  tm.selects = await page.evaluate(() => [...document.querySelectorAll('#tt-pane select[data-tt-team]')].map((s) => [s.dataset.ttTeam, s.value]));
  await page.evaluate(() => { const s = document.querySelector('#tt-pane select[data-tt-team="Red"]'); s.value = "gladiator"; s.dispatchEvent(new Event('change', { bubbles: true })); });
  await page.evaluate(() => document.querySelector('#tt-pane [data-tt-do="apply"]').click());
  await page.waitForURL(/resume=try/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.over && typeof SAVE !== 'undefined' && SAVE.candidate, null, { timeout: 180000 }).catch(() => {});
  tm.over = await page.evaluate(() => ({ over: __bm.over, cand: SAVE.candidate, keep: !!document.querySelector('[data-tt-keep]'), asked: SAVE.events.filter((e) => e.post).length }));
  await page.evaluate(() => { const k = document.querySelector('[data-tt-keep]'); if (k) k.click(); });
  await page.waitForTimeout(500);
  tm.kept = await page.evaluate(() => { const f = JSON.parse(localStorage.getItem("bm_save") || "null"); return f && { parent: !!f.parent, control: f.orders.events.filter((e) => e.branch && e.branch.control).map((e) => e.branch.control), cand: SAVE.candidate }; });
  out.tm = tm;
  // ---- 11: THE REPLAY TAB = THE REC LAYER (Phase D). (a) A bot battle's record opens in the view-only replay page; Play from here at a move starts a candidate
  // game in which the chosen team is the person's. (b) A played human game: Watch replay opens the Lab's Replay tab with the page inside it, showing the human
  // game's own steps; Play from here there resumes the human's earlier answers and asks the next question.
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + "/index.html");
  await page.waitForFunction(() => window.LAB_WASM && window.crossOriginIsolated, null, { timeout: 60000 });
  const BOTS = JSON.parse(JSON.stringify(SOLO)); BOTS.teams[0].bot = "gladiator"; BOTS.teams[1].bot = "princess"; BOTS.seed = 11;
  const rp = {};
  rp.rec = await page.evaluate(async (st) => { const rec = await LAB_WASM.api("history", { setup: st, seed: 11, sim: 1 }); if (rec.error) return { error: rec.error }; localStorage.setItem("bm_replay", JSON.stringify({ record: rec, setup: st, orders: null, seed: rec.seed })); localStorage.removeItem("bm_save"); localStorage.removeItem("bm_try"); return { steps: rec.steps.length }; }, BOTS);
  await page.goto(base + "/play.html?replay=1");
  await page.waitForFunction(() => typeof TT !== 'undefined' && TT._st.steps.length > 0 && document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 60000 }).catch(() => {});
  rp.a = await page.evaluate(() => ({ strip: document.getElementById('tt-strip').classList.contains('on'), steps: TT._st.steps.length, replay: TT._st.replay, units: __bm.units.map((u) => u.hex).filter(Boolean).length, rec: getComputedStyle(document.querySelector('.tbar .rec')).display }));
  await page.evaluate(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "move" && s.turn >= 2 && s.unit);
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } } });
  rp.btn = await page.evaluate(() => [...document.querySelectorAll('#tt-pane [data-tt-do]')].map((b) => b.textContent));
  await page.evaluate(() => document.querySelector('#tt-pane [data-tt-do="from"]').click());
  await page.waitForURL(/resume=try/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && SAVE.candidate, null, { timeout: 120000 }).catch(() => {});
  rp.cand = await page.evaluate(() => ({ kind: (__bm.req || {}).kind, team: __bm.myTeam, cand: SAVE.candidate, control: JSON.parse(localStorage.getItem("bm_try")).orders.events.filter((e) => e.branch).map((e) => e.branch.control) }));
  // (b) a played human game
  await page.evaluate(() => { localStorage.setItem("bm_play_setup", JSON.stringify(window.__solo)); }).catch(() => {});
  await page.goto(base + "/index.html");
  await page.evaluate((s) => { localStorage.setItem("bm_play_setup", JSON.stringify(s)); localStorage.removeItem("bm_save"); localStorage.removeItem("bm_try"); localStorage.removeItem("bm_replay"); }, SOLO);
  await page.goto(base + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  for (let i = 0; i < 400; i++) { await page.waitForFunction(() => window.__bm.req || window.__bm.over, null, { timeout: 120000 }); if (await page.evaluate(() => window.__bm.over)) break; const before = await seqNow(); await stepOnce(page); await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); }
  await page.waitForFunction(() => document.querySelector('[data-act="watch-replay"]'), null, { timeout: 30000 }).catch(() => {});
  await page.evaluate(() => document.querySelector('[data-act="watch-replay"]').click());
  await page.waitForURL(/index\.html/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => { const f = document.getElementById('replay-frame'); try { return !!(f && f.contentWindow && f.contentWindow.eval('typeof TT !== "undefined" && TT._st.steps.length')); } catch (e) { return false; } }, null, { timeout: 90000 }).catch(() => {});
  rp.b = await page.evaluate(() => { const f = document.getElementById('replay-frame'), w = f.contentWindow; return { tab: !document.getElementById('page-replay').hidden, src: f.getAttribute('src'), steps: w.eval('TT._st.steps.length'), hasOrders: !!(JSON.parse(localStorage.getItem("bm_replay")).orders), setup: !!JSON.parse(localStorage.getItem("bm_replay")).setup }; });
  await page.evaluate(() => { const w = document.getElementById('replay-frame').contentWindow; w.eval(`(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "move" && s.turn >= 3 && s.unit);
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } } })()`); });
  await page.evaluate(() => document.getElementById('replay-frame').contentDocument.querySelector('#tt-pane [data-tt-do="from"]').click());
  await page.waitForURL(/resume=try/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && SAVE.candidate, null, { timeout: 120000 }).catch(() => {});
  rp.bc = await page.evaluate(() => ({ kind: (__bm.req || {}).kind, cand: SAVE.candidate, events: JSON.parse(localStorage.getItem("bm_try")).orders.events.length }));
  out.rp = rp;
  // ---- 12: THE DESKTOP LAB (Phase F). The same page code against the desktop server (no wasm): the Lab leaves the setup, the play page starts the game, saves it,
  // closing and opening the page resumes it, REC reads the record over the server's history query, and Meddle here opens a candidate and holds it.
  await page.close();
  page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(labBase + "/index.html");
  await page.evaluate((s) => { localStorage.setItem("bm_play_setup", JSON.stringify(s)); localStorage.removeItem("bm_save"); localStorage.removeItem("bm_try"); }, SOLO);
  await page.goto(labBase + "/play.html");
  await page.waitForFunction(() => typeof window.send === 'function' && window.__bm);
  for (let i = 0; i < 24; i++) { const before = await seqNow(); await stepOnce(page); await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, before, { timeout: 120000 }); }
  if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) await page.locator('[data-act="report-close"]').first().click();
  await page.waitForTimeout(700);
  const dk = {};
  dk.orig = await page.evaluate(() => ({ kind: __bm.req.kind, n: JSON.parse(localStorage.getItem("bm_save")).orders.events.length }));
  // closing and opening the page: resumed by itself
  await page.goto(labBase + "/play.html");
  await page.waitForFunction(() => window.__bm && window.__bm.req, null, { timeout: 120000 }).catch(() => {});
  dk.resumed = await page.evaluate(() => ({ kind: (__bm.req || {}).kind, n: JSON.parse(localStorage.getItem("bm_save")).orders.events.length }));
  await page.evaluate(() => document.querySelector('[data-act="rec"]').click());
  await page.waitForFunction(() => document.getElementById('tt-strip') && document.getElementById('tt-strip').classList.contains('on'), null, { timeout: 60000 }).catch(() => {});
  dk.rec = await page.evaluate(() => ({ strip: document.getElementById('tt-strip').classList.contains('on'), steps: TT._st.steps.length }));
  await page.evaluate(() => { const st = TT._st, i = st.steps.findIndex((s) => s.k === "move" && s.turn >= 2 && s.unit && (S.units.find((u) => u.name === s.unit) || {}).team === "Blue");
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { const a = document.getElementById('tt-a'), b = document.getElementById('tt-b'); a.value = k; a.dispatchEvent(new Event('input', { bubbles: true })); b.value = j; b.dispatchEvent(new Event('input', { bubbles: true })); break; } } });
  await page.evaluate(() => document.querySelector('#tt-pane [data-tt-do="meddle"]').click());
  await page.waitForURL(/resume=try/, { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => window.__bm && window.__bm.req && typeof SAVE !== 'undefined' && SAVE.candidate, null, { timeout: 120000 }).catch(() => {});
  dk.cand = await page.evaluate(() => ({ team: __bm.myTeam, cand: SAVE.candidate, label: (document.querySelector('.commit .lab') || {}).textContent }));
  const dseq = await seqNow(); await stepOnce(page);
  await page.waitForFunction((b) => (window.__bm.req && window.__bm.seq !== b) || window.__bm.over, dseq, { timeout: 120000 });
  await page.waitForTimeout(700);
  dk.kept = await page.evaluate(() => { const f = JSON.parse(localStorage.getItem("bm_save")); return { cand: SAVE.candidate, parent: !!f.parent, branch: f.orders.events.filter((e) => e.branch).length }; });
  out.dk = dk;
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
            p = subprocess.run(["node", nf, f"http://127.0.0.1:{web_port}", sf, f"http://127.0.0.1:{lab_port}"], capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path}, timeout=1800)
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
        rz = out.get("resume") or {}
        report(rz.get("saved") and rz["saved"]["n"] > 20 and rz["saved"]["fmt"] == 1 and rz["mid"] == {k: v for k, v in rz["back"].items() if k != "board"} and rz["back"].get("board"), f"a game saved part-way comes back, in a new page, at the same question with the units where they were ({rz})")
        report((rz.get("bare") or {}).get("kind") == rz["mid"]["kind"] and rz["bare"]["unit"] == rz["mid"]["unit"], f"opening the play page again with nothing to start goes straight back to the unfinished game's question ({rz.get('bare')})")
        report(rz.get("over") and rz.get("dropped"), "the resumed game plays on to its end, and a finished game leaves no save behind")
        tt = out.get("tt") or {}
        report(tt.get("card", 0) >= 8 and tt.get("asked") == tt["pick"]["post"] and tt["file"]["hasParent"] and bool((tt["file"]["at"] or {}).get("reseed")), f"time travel: the list of questions opens, going back asks the picked question again in a new page, the new seed is written where the timeline starts ({tt})")
        report(tt.get("parentAsked") == tt.get("waiting"), f"Back to the earlier timeline returns to the question the first game was waiting on ({tt.get('parentAsked')} vs {tt.get('waiting')})")
        report((tt.get("childAsked") or {}).get("hasReseed"), f"On to the later timeline comes back to the branch, its new seed still in its list ({tt.get('childAsked')})")
        rc = out.get("rec") or {}
        op = rc.get("open") or {}
        report(op.get("strip") and op.get("report") == "block" and op.get("bottomHalf") and op.get("tabs") == ["Log", "Report", "Teams", "Timelines"] and op.get("steps", 0) > 20 and op.get("repOnTop"), f"REC opens the strip and the report as the bottom half with its tabs, the Report button on top ({op})")
        mv = rc.get("move") or {}
        report(mv.get("past") and any(w in mv.get("log", "") for w in ("ran", "walked", "jumped", "moved", "stood")), f"a slider takes the board to a past movement step and the Log says what it did ({mv.get('readout')!r}: {mv.get('log', '')[:90]!r})")
        pd = rc.get("pastDraw") or {}
        report(pd.get("path") and pd.get("ring"), f"the mover's path and ring are drawn at a past movement step ({pd})")
        fd = rc.get("fireDraw") or {}
        report(fd.get("arrow") and "fired at" in fd.get("log", ""), f"a past fire step draws the attack arrow with its result and the Log tells it ({fd.get('arrow')}, {fd.get('log', '')[:90]!r})")
        report(rc.get("liveBefore") == rc.get("liveAfter"), "looking back and tapping the map changes nothing in the live game (units, question, answers)")
        report(rc.get("closed") == "none" and rc.get("reopened") == "block", f"the Report button closes the panel while REC is open and a slider reopens it ({rc.get('closed')}, {rc.get('reopened')})")
        lv = rc.get("live") or {}
        sh = rc.get("shut") or {}
        report(lv.get("now") and not lv.get("past") and sh.get("strip") == "none" and not sh.get("tabs") and not sh.get("open") and sh.get("report") == "none", f"Live comes back to the present and REC closes the layer ({lv}, {sh})")
        md = out.get("med") or {}
        cd2 = md.get("cand") or {}
        report(md.get("button") and cd2.get("who") and cd2.get("who") == cd2.get("team") and cd2.get("who") != "Red" and cd2.get("label") == "Meddle" and cd2.get("strip") and cd2.get("try") and cd2.get("saveN") == md["orig"]["n"], f"Meddle here at the bot's move opens a candidate timeline: the first question is the bot team's, the commit button reads Meddle, the original save is untouched ({md.get('step')}, {cd2})")
        bk = md.get("back") or {}
        report(bk.get("kind") == md["orig"]["kind"] and bk.get("unit") == md["orig"]["unit"] and bk.get("saveN") == md["orig"]["n"] and not bk.get("try"), f"Live before holding Meddle goes back to the first game exactly where it was ({bk} vs {md.get('orig')})")
        kp = md.get("kept") or {}
        report(not kp.get("cand") and not kp.get("hasTry") and kp.get("parent") and any(b.get("meddle") and b.get("reseed") for b in kp.get("branch", [])), f"holding the answer keeps the new timeline: a reseed and the meddle in its list, the old game as its parent ({kp})")
        tmx = out.get("tm") or {}
        report((tmx.get("over") or {}).get("over") and tmx["over"].get("keep") and (tmx.get("kept") or {}).get("parent") and tmx["kept"].get("control") == [[{"team": "Red", "by": "gladiator"}]] and not tmx["kept"].get("cand"), f"the Teams tab: Red handed to a bot from a past step plays to the end without a question, Keep writes the timeline with its control entry and the old game as parent ({tmx})")
        rpx = out.get("rp") or {}
        ra = rpx.get("a") or {}
        report(ra.get("strip") and ra.get("steps", 0) > 20 and ra.get("replay") and ra.get("units") == 2 and ra.get("rec") == "none" and "Play from here" in rpx.get("btn", []), f"a bot battle's record opens in the view-only replay page with the strip and Play from here ({ra}, {rpx.get('btn')})")
        rc2 = rpx.get("cand") or {}
        report(rc2.get("cand") and rc2.get("kind") and rc2.get("control") == [[{"team": "Red", "by": "human"}]], f"Play from here on a bot battle starts a candidate game with the chosen team as the person ({rc2})")
        rb = rpx.get("b") or {}
        report(rb.get("tab") and "play.html?replay=1" in (rb.get("src") or "") and rb.get("steps", 0) > 30 and rb.get("hasOrders") and rb.get("setup"), f"Watch replay opens the Lab's Replay tab with the REC page inside it, showing the human game with its orders ({rb})")
        rbc = rpx.get("bc") or {}
        report(rbc.get("cand") and rbc.get("kind") and rbc.get("events", 0) > 5, f"Play from here in a human game's replay resumes its earlier answers and asks the next question ({rbc})")
        dkx = out.get("dk") or {}
        report((dkx.get("resumed") or {}).get("kind") == (dkx.get("orig") or {}).get("kind") and dkx["resumed"].get("n") == dkx["orig"].get("n") and (dkx.get("rec") or {}).get("strip") and dkx["rec"].get("steps", 0) > 20, f"the desktop Lab: the play page saves, closing and opening it resumes the game, REC reads the record from the server ({dkx.get('orig')}, {dkx.get('resumed')}, {dkx.get('rec')})")
        report((dkx.get("cand") or {}).get("cand") and dkx["cand"].get("team") == "Blue" and dkx["cand"].get("label") == "Meddle" and (dkx.get("kept") or {}).get("parent") and dkx["kept"].get("branch") == 1 and not dkx["kept"].get("cand"), f"the desktop Lab: Meddle here opens a candidate (the bot team's question, Meddle label) and holding the answer keeps it ({dkx.get('cand')}, {dkx.get('kept')})")
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
