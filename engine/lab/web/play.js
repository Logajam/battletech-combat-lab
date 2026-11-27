"use strict";
// BATTLEROM play page. Talks to the Combat Lab server: play_poll / play_answer / play_query (engine/core/src/play_session.rs).
// One question at a time: the engine waits. This page shows what it asks (move order, stand up, MASC, move, spot, TAG, target,
// weapons, physical attack, End Phase switches) and sends the answer; while a question waits it can also ask the engine for
// a route, re-price a weapon after a mode / ammunition change, and set equipment switches.
const $ = (id) => document.getElementById(id);
const qs = new URLSearchParams(location.search);
let GAME = +qs.get("game");
let COLOURS = {};
try { COLOURS = JSON.parse(qs.get("colours") || "{}"); } catch (e) { /* default colours */ }
const R = MapView.R, SQ3 = Math.sqrt(3);
const NS = "http://www.w3.org/2000/svg";
const DIR = { N: [0, -1], NE: [SQ3 / 2, -0.5], SE: [SQ3 / 2, 0.5], S: [0, 1], SW: [-SQ3 / 2, 0.5], NW: [-SQ3 / 2, -0.5] };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const LOCAB = { "Head": "H", "Center Torso": "CT", "Left Torso": "LT", "Right Torso": "RT", "Left Arm": "LA", "Right Arm": "RA", "Left Leg": "LL", "Right Leg": "RL" };

// ---------------------------------------------------------------- looks (remembered on this device)
const LOOKS = { slhisd: "SL-HIS Dark", slhis: "SL-HIS Light", w95: "Windows 95", modern: "Modern" };
const pref = (k, d) => { try { const v = localStorage.getItem("bm_" + k); return v == null ? d : v; } catch (e) { return d; } };
const setPref = (k, v) => { try { localStorage.setItem("bm_" + k, v); } catch (e) { /* storage off */ } };
const O = { look: pref("look", "slhisd"), cvd: pref("cvd", "0") === "1", rings: pref("rings", "1") === "1", labels: pref("labels", "1") === "1", dice: pref("dice", "1") === "1", atk: pref("atk", "1") === "1" };
// movement colours follow MegaMek's (walk cyan, run yellow, jump orange; NOT VERIFIED against its source); the colour-blind set
// (Okabe-Ito) also gives each mode its own line pattern
const modeCol = (m) => (O.cvd ? { Walk: "#56B4E9", Run: "#F0E442", Jump: "#CC79A7" } : { Walk: "#00e5ff", Run: "#ffd400", Jump: "#ff7a3c" })[m] || "#99a";
const modeDash = (m, s = 1) => (O.cvd ? { Walk: "", Run: `${7 * s} ${4 * s}`, Jump: `${2 * s} ${4 * s}` }[m] || "" : "");
const BAND = () => (O.cvd ? { short: "#56B4E9", medium: "#F0E442", long: "#CC79A7" } : { short: "#6fbf86", medium: "#dba94a", long: "#e07468" });

const S = { way: [], wrIdx: null, wlist: {}, seq: 0, req: null, board: null, units: [], max: {}, maxLoc: {}, critNames: {}, sel: null, dest: null, facing: null, mode: null, view: null, log: [], over: false,
  decl: null, path: null, attackSel: null, pending: false, myTeam: null, standOn: false, aim: null, phys: null, lastFocus: null };
const svg = $("map");
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };

// THE SAVED GAME (P15, INTEGRATION__ORDER_FORMAT.md): this page writes down, in order, every question it is shown (kind, unit) and every answer or
// query it sends, exactly as the engine's RecordingLink does. That list is the save: played back, the engine reaches the same point; from there
// the person goes on. It is kept in this browser (localStorage "bm_save") after every answer and when the page is hidden or closed, and can be
// written to a file (Menu: Save game to a file) and opened again from the Lab.
const SAVE_KEY = "bm_save";
const phaseKey_ = (k) => (["target", "declaration", "spot", "tag"].includes(k) ? "fire" : k === "physical" ? "phys" : k === "end_phase" ? "end" : "move");
const SAVE = { events: [], seed: null, setup: null, human: [], marks: [], parent: null, child: null };
function saveFile(whenOver) {
  if (!SAVE.setup || SAVE.seed == null || (S.over && !whenOver)) return null;
  return { combatlab_game: 1, marks: SAVE.marks, parent: SAVE.parent, child: SAVE.child, saved: new Date().toISOString(), title: (SAVE.setup.teams || []).map((t) => t.name).join(" vs "), setup: SAVE.setup, seed: String(SAVE.seed),
           orders: { order_format: 1, engine: "browser", seed: String(SAVE.seed), human: SAVE.human, events: SAVE.events } };
}
function saveNow() {
  if (SAVE.frozen || SAVE.candidate) return;   // a candidate timeline (REC layer: Meddle here) is not kept until its first answer is held   // leaving for another timeline: the page's pagehide must not write this game over the one just stored
  const f = saveFile(); if (!f) return;
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(f)); } catch (e) { /* storage full or off: the game goes on, unsaved */ }
}
function saveSoon() { clearTimeout(saveSoon.t); saveSoon.t = setTimeout(saveNow, 250); }
function dropSave() { clearTimeout(saveSoon.t); if (SAVE.candidate) return; try { localStorage.removeItem(SAVE_KEY); } catch (e) { /* storage off */ } }
addEventListener("pagehide", saveNow);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") saveNow(); });
// TIME TRAVEL (P4, P15 step 3; Daniel: "Time to start on the ability to meddle"): the REC button lists every question of this game, newest first; "Go back here" makes a
// NEW TIMELINE: the list cut just before that question, a fresh dice seed written into it ({"reseed": n}, Daniel 2026-11-19: a branch gets its own seed, recorded),
// and the game resumed from there, so the same question is asked again and you can answer it differently. The game you leave is kept as the branch's
// "parent": Menu > "Back to the earlier timeline" returns to it (where it stood when you left).
function timeTravelCard() {
  if (!SAVE.setup) { toast("Time travel needs a game started from this browser's Lab."); return; }
  const rows = SAVE.marks.filter((m) => m.at < SAVE.events.length).slice().reverse().map((m) => `<div class="row"><span class="msg">${esc(m.label)}</span> <button class="sm" data-act="branch" data-at="${m.at}">Go back here</button></div>`).join("");
  showCard(`<b>Time travel</b><div class="msg">Pick a question to answer again. The game from there on is a new timeline with new dice; this one is kept (Menu: Back to the earlier timeline).${SAVE.parent ? " This game is already a branch." : ""}</div><div style="max-height:46vh;overflow:auto">${rows || '<div class="msg">No questions recorded yet.</div>'}</div>`);
}
function branchFrom(at) {
  const f = saveFile(true); if (!f) return;
  const mark = SAVE.marks.find((m) => m.at === at); if (!mark) return;
  const seed = Math.floor(Math.random() * 0xFFFFFFFE) + 1;
  const ev = SAVE.events.slice(0, at); ev.push({ reseed: String(seed) });
  const branch = { ...f, parent: f, marks: SAVE.marks.filter((m) => m.at < at), title: f.title + " (branch)", orders: { ...f.orders, events: ev }, branched_at: mark.label, reseed: String(seed) };
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(branch)); } catch (e) { toast("This browser will not keep the new timeline (storage is full or off): save the game to a file first."); return; }
  SAVE.frozen = true;   // after the write: the page's pagehide must not store this game over the new timeline
  location.href = "play.html?resume=1";
}
function backToParent() {
  if (!SAVE.parent) return;
  saveNow();
  // the timeline left behind stays with the earlier one, so "On to the later timeline" can come back to it
  const later = { ...saveFile(true), parent: null }, earlier = { ...SAVE.parent, child: later };   // no cycles: each file carries the other once
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(earlier)); } catch (e) { toast("This browser will not keep the earlier timeline."); return; }
  SAVE.frozen = true;
  location.href = "play.html?resume=1";
}
function forwardToChild() {
  if (!SAVE.child) return;
  saveNow();
  const earlier = { ...saveFile(true), child: null }, later = { ...SAVE.child, parent: earlier };
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(later)); } catch (e) { toast("This browser will not keep the later timeline."); return; }
  SAVE.frozen = true;
  location.href = "play.html?resume=1";
}
function saveToFile() {
  saveNow(); const f = saveFile(); if (!f) { toast("Nothing to save yet."); return; }
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(f)], { type: "application/json" }));
  a.download = `${(f.title || "game").replace(/[^A-Za-z0-9_.-]+/g, "_")}_turn_save.combatlab-game.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
async function api(name, body) {
  if (name === "play_query" && SAVE.setup && !(body.query && body.query.q === "history")) { SAVE.events.push({ query: body.query }); }   // the REC layer's look at the record is not part of the game
  if (window.LAB_WASM) return window.LAB_WASM.api(name, { game: GAME, ...body });   // the browser build (engine/wasm): this page plays the battle
  const r = await fetch("api/" + name, { method: "POST", body: JSON.stringify({ game: GAME, ...body }) });
  return r.json();
}
const query = (q) => api("play_query", { query: q });

// ---------------------------------------------------------------- geometry (flat-topped hexes, even columns half a hex lower, N up)
const parse = (l) => [parseInt(l.slice(0, 2), 10), parseInt(l.slice(2), 10)];
const MV = MapView.create(svg, { rescale: () => { if (typeof redraw === "function" && S.board) redraw(); }, camera: () => onCamera() });
const centre = MV.centre, pts = MV.pts;
// label-based geometry, the same calls in the flat map and the 3D tabletop (mapview.js): at = a hex's centre (up = height above its tile),
// P = a point of the hex in hex radii from the centre, HP = its outline, sc = view units per board unit there (1 in the flat map: every length
// below is written in board units and multiplied by it, so the flat drawing is unchanged)
// the 3D looks (Menu, View, Tabletop looks), remembered on this device: height of a level, how clear the glass of a raised tile is, the bevel,
// the kind of tree and the table (a holotable or wood)
const T3 = { relief: [["Low", 170], ["Table", 280], ["Tall", 400]], glass: [["Solid", 0], ["Light", 20], ["Glass", 40], ["Clear", 60]], trees: [["Cones", "cone"], ["Balls", "round"], ["Mixed", "mixed"]], skin: [["Holotable", "holo"], ["Wood", "wood"]] };
const t3get = () => ({ relief: +pref("t_relief", 280), glass: +pref("t_glass", 40), bevel: pref("t_bevel", "1") === "1", trees: pref("t_trees", "cone"), skin: pref("t_skin", "holo") });
const t3name = (k) => { const v = t3get()[k]; return (T3[k].find((x) => x[1] === v) || [v])[0]; };
const t3next = (k) => { const v = t3get()[k], i = T3[k].findIndex((x) => x[1] === v); return T3[k][(i + 1) % T3[k].length][1]; };
const at = (l, up) => MV.at(l, up), P = (l, dx, dy, up) => MV.pt(l, dx, dy, up), HP = (l, k, up) => MV.hexPts(l, k, up), sc = (l) => MV.scale(l);   // where a hex is, and its six corners (the map view, mapview.js)
const hexName = (c, r) => String(c).padStart(2, "0") + String(r).padStart(2, "0");
function neighbours(l) { // in the order of polygon edges 0..5 (SE, S, SW, NW, N, NE)
  const [c, r] = parse(l), low = c % 2 === 0;
  return [hexName(c + 1, r + (low ? 1 : 0)), hexName(c, r + 1), hexName(c - 1, r + (low ? 1 : 0)), hexName(c - 1, r + (low ? 0 : -1)), hexName(c, r - 1), hexName(c + 1, r + (low ? 0 : -1))];
}
function dist(a, b) {
  const cube = (l) => { const [c, r] = parse(l), x = c - 1, z = (r - 1) - (x - (x & 1)) / 2; return [x, -x - z, z]; };
  const p = cube(a), q = cube(b);
  return Math.max(Math.abs(p[0] - q[0]), Math.abs(p[1] - q[1]), Math.abs(p[2] - q[2]));
}
const unit = (id) => S.units.find((u) => u.id === id);

// ---------------------------------------------------------------- map
let gDyn, gTop;   // the layers drawn into (the base map layer is the view's own)
function buildMap() {
  MV.setBoard(S.board, { labels: O.labels }); gDyn = MV.layers.dyn; gTop = MV.layers.top;
}
// zoom in on a set of hexes with a margin (the first view of a game), fit the whole board, zoom about a client point
const focusOn = MV.focusOn, fit = MV.fit, zoom = MV.zoom;
// the camera framing that is done again when the clear area changes (S.lastFocus)
function look(labels, m) { S.lastFocus = [labels, m]; focusOn(labels, m); }
// drag to pan, wheel / pinch to zoom, press and hold for the INSPECTOR (Daniel, 2026-11-26; Section 14, L5): a long press on a unit, its placard
// or a hex opens the inspector on that hex; on an attack line's label, on that attack. A hold must stay within HOLD_SLOP px of where it began
// (bug B13: a fingertip always moves a little).
const HOLD_SLOP = 10, LONG_MS = 500;
(() => {
  const ptrs = new Map(); let moved = false, timer = null, start = null;
  const cancel = () => { if (timer) { clearTimeout(timer); timer = null; } };
  svg.addEventListener("pointerdown", (e) => {
    ptrs.set(e.pointerId, [e.clientX, e.clientY]); moved = false; cancel(); start = [e.clientX, e.clientY];
    if (ptrs.size === 1) {
      const al = e.target.closest("[data-atk],[data-mine]");
      if (al) { timer = setTimeout(() => { timer = null; moved = true; UI.atkSel = al.dataset.atk != null ? { kind: "past", i: +al.dataset.atk } : { kind: "mine", i: +al.dataset.mine }; openInsp("Attack", null, null, "an attack line"); }, LONG_MS); return; }
      const t = e.target.closest("[data-unit],[data-hex],[data-reach]");
      const uid = t && t.dataset.unit != null ? +t.dataset.unit : null;
      const hex = (t && (t.dataset.hex || t.dataset.reach)) || (MV.mode === "3d" && uid == null ? MV.hexAt(e.clientX, e.clientY) : null);   // the 3D view has no hex elements: ask it which hex is there
      if (uid != null && unit(uid)) timer = setTimeout(() => { timer = null; moved = true; const u = unit(uid); UI.last = { kind: "unit", id: uid }; openInsp("Hex", u.hex, uid, "a long press on " + u.name); }, LONG_MS);
      else if (hex) timer = setTimeout(() => { timer = null; moved = true; UI.last = { kind: "hex", l: hex }; openInsp("Hex", hex, null, "a long press on the map"); }, LONG_MS);
    }
  });
  svg.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId)) return;
    const prev = ptrs.get(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptrs.size === 1) {
      const dx = e.clientX - prev[0], dy = e.clientY - prev[1];
      // a press still waiting to become a hold does not pan until the finger has clearly left its spot
      if (timer && start && Math.hypot(e.clientX - start[0], e.clientY - start[1]) <= HOLD_SLOP) return;
      if (Math.abs(dx) + Math.abs(dy) > 2) { moved = true; cancel(); }
      if (e.buttons & 2) MV.orbitBy(dx, dy); else MV.panBy(dx, dy, e.clientX, e.clientY);   // right-drag turns and tilts the 3D view
    } else if (ptrs.size === 2) {
      cancel();
      const [a, b] = [...ptrs.values()];
      MV.pinch({ x: a[0], y: a[1] }, { x: b[0], y: b[1] }); moved = true;
    }
  });
  const up = (e) => { ptrs.delete(e.pointerId); MV.pinchEnd(); cancel(); };
  svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", up);
  svg.addEventListener("click", (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  svg.addEventListener("contextmenu", (e) => { if (MV.mode === "3d") e.preventDefault(); });   // right-drag orbits the 3D view: no browser menu there
  svg.addEventListener("wheel", (e) => { e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
  // a tap: a unit (its base, its placard) or a hex; the marks that answer a tap themselves (lit hexes, arrows, deployment hexes, pills) are left alone
  svg.addEventListener("click", (e) => {
    if (e.target.closest("[data-reach],[data-arrow],[data-deploy],[data-tn-pill],[data-atk],[data-mine],[data-stop],[data-aimhex]")) return;
    const un = e.target.closest("[data-unit]"); if (un) { unitTap(+un.dataset.unit); return; }
    const hx = e.target.closest("[data-hex]"), hex = hx ? hx.dataset.hex : MV.is3d() ? MV.hexAt(e.clientX, e.clientY) : null;
    if (hex) hexTap(hex);
  });
})();
$("zin").onclick = () => zoom(1 / 1.3); $("zout").onclick = () => zoom(1.3); $("zfit").onclick = () => { S.lastFocus = null; fit(); };
// a tap on a unit on the map (H1, L2): in the attack phases an enemy is the target (its hex's tap cycle); in Movement the mover's own hex turns
// it in place, a unit to choose from becomes the mover, an enemy goes to the Last line (with Charge / Death from above beside it)
function unitTap(id) {
  const u = unit(id); if (!u) return;
  if (S.fire && S.req.enemies.some((e) => e.id === id)) { hexTap(u.hex); return; }
  if (S.req && S.req.kind === "physical") { if (!physSetTarget(id)) UI.last = { kind: "unit", id }; redraw(); return; }
  if (moving() || standing()) { onUnitTap(id); return; }
  UI.last = { kind: "unit", id }; redraw();
}
// a tap on a hex. THE TAP CYCLE (Daniel, 2026-11-26; Section 14, H2, H3): in the attack phases, taps on one hex step through its enemy units,
// then a building, then the ground; an empty hex needs two taps (the first only selects it, and the weapons step aside)
function hexTap(l) {
  if (S.decl && S.decl.aimFor) { setAim(l); return; }
  if (S.fire) {
    const foes = S.units.filter((u) => u.hex === l && !u.destroyed && S.req.enemies.some((e) => e.id === u.id)).map((u) => u.id), again = UI.cyc && UI.cyc.l === l;
    if (!foes.length) {
      if (again && UI.pickHex === l) { UI.cyc = null; UI.pickHex = null; toast("Attacking a hex or a building is not in the engine yet: only units can be targeted."); }
      else { UI.cyc = { l, i: -1 }; UI.pickHex = l; UI.last = { kind: "hex", l }; toast("Tap again to target the ground"); }
      redraw(); return;
    }
    const i = again ? (UI.cyc.i + 1) % foes.length : 0; UI.cyc = { l, i }; UI.pickHex = null;
    if (foes.length > 1) toast(`Target ${i + 1} of ${foes.length} in ${l}: tap again for the next`);
    setTcur(foes[i]); return;
  }
  if (S.req && S.req.kind === "physical") { const f = S.units.find((u) => u.hex === l && physOpts().some((o) => o.target === u.id)); if (f && physSetTarget(f.id)) { redraw(); return; } }
  UI.last = { kind: "hex", l }; redraw();
}

// ---------------------------------------------------------------- a card: a short message with buttons over the clear area (eject, a battle the
// browser cannot hand over)
function showCard(html) { const c = $("card"); c.innerHTML = html + '<div class="row"><button class="sm" data-act="card-close">Close</button></div>'; c.style.display = "block"; }

// ---------------------------------------------------------------- units on the map
const teamColour = (u) => (O.cvd ? (u.team === S.myTeam ? "#56B4E9" : "#D55E00") : COLOURS[u.team] || (u.team === S.myTeam ? "#4b8fd8" : "#d86a4b"));
const short = (u) => String(u.mech || u.name || "").split(/\s+/)[0].slice(0, 7);
// share of armour ("a": front + rear) or structure ("s") left on one side ("Left" / "Right"); centre locations count half to each side
function sideFrac(u, kind, side) {
  const mx = S.maxLoc[u.id] || {}, locs = u.locs || {};
  let tot = 0, left = 0;
  for (const [loc, v] of Object.entries(locs)) {
    const m = mx[loc] || v, w = loc.includes(side) ? 1 : (loc.includes("Left") || loc.includes("Right")) ? 0 : 0.5;
    if (!w) continue;
    const now = kind === "a" ? (v[0] || 0) + (v[1] || 0) : v[2] || 0, max = kind === "a" ? (m[0] || 0) + (m[1] || 0) : m[2] || 0;
    tot += w * max; left += w * (v[3] ? 0 : now);
  }
  return tot ? Math.max(0, Math.min(1, left / tot)) : 1;
}
function fracOf(u) {
  const m = S.max[u.id] || (S.max[u.id] = { hp: Math.max(1, u.hp) });
  return Math.max(0, Math.min(1, u.hp / m.hp));
}
// A 'Mech sprite (a plain silhouette, not MegaMek's art) on a tinted hex base, a placard (name and the three bars: armour, structure,
// heat) joined to the unit by a leader line. Placards are placed one at a time on the first spot that does not cover another.
const SPOTS = [[0, 0.7], [0, -0.8], [1.15, 0.2], [-1.15, 0.2], [1.1, -0.7], [-1.1, -0.7], [1.1, 1.0], [-1.1, 1.0], [0, 1.5], [0, -1.6], [1.7, 0.2], [-1.7, 0.2], [1.6, -1.1], [-1.6, -1.1], [1.6, 1.3], [-1.6, 1.3]];
// ATTACK LINES, both sides (Daniel, 2026-11-24: "Attack lines drawn for both sides (So you can see what is shooting at you. Long press on the attack
// line to get details of that attack.)"): the latest turn's attacks from the report lines already released (no spoilers), a line from the
// attacker to its target in the attacker's colour with hits / shots; a tap or a long press opens that attack's report.
function attacksOfLatestTurn() {
  const all = []; let turn = 0, cur = null;
  for (const l of S.shown) {
    const t = /=== TURN (\d+)/.exec(l); if (t) { turn = +t[1]; cur = null; continue; }
    let m;
    if ((m = /\[Ranged\] (.+?) -> (.+?): range/.exec(l))) { cur = { turn, a: m[1], t: m[2], kind: "weapons", lines: [l], shots: 0, hits: 0 }; all.push(cur); continue; }
    if ((m = /\[Physical\] (.+?) -> (.+?): (.+?) needs \d+ .* -> (HIT|miss)/.exec(l))) { cur = { turn, a: m[1], t: m[2], kind: m[3], lines: [l], shots: 1, hits: m[4] === "HIT" ? 1 : 0 }; all.push(cur); continue; }
    if (cur && /^\s{2}\[(Movement|Ranged|Physical|Heat|TAG|Spot)\]|-- end of turn/.test(l) && !/\[Resolve\]/.test(l)) { cur = null; continue; }
    if (cur) { cur.lines.push(l); if (cur.kind === "weapons" && /^\s{4}.+?: needs \d+/.test(l)) { cur.shots++; if (/-> HIT/.test(l)) cur.hits++; } }
  }
  const last = Math.max(0, ...all.map((x) => x.turn));
  return all.filter((x) => x.turn === last && x.shots > 0);   // an attacker that fired nothing draws no line
}
function drawAttackLines(layer) {
  if (!O.atk) return;
  S.atkList = attacksOfLatestTurn();
  const byName = (n) => S.units.find((u) => u.name === n), uh = MV.unitHeight();
  S.atkList.forEach((a, i) => {
    const A = byName(a.a), T = byName(a.t); if (!A || !T || !A.hex || !T.hex) return;
    const s = (sc(A.hex) + sc(T.hex)) / 2, [x1, y1] = at(A.hex, uh), [x2, y2] = at(T.hex, uh), len = Math.hypot(x2 - x1, y2 - y1) || 1, nx = -(y2 - y1) / len * 4 * s, ny = (x2 - x1) / len * 4 * s;
    const sel = new Set([(activeUnit() || {}).id, UI.last && UI.last.kind === "unit" ? UI.last.id : -1]), hi = sel.has(A.id) || sel.has(T.id);
    const col = teamColour(A), g = el("g", { "data-atk": i, style: "cursor:pointer", opacity: hi ? "1" : ".35" }, layer);
    const p = [x1 + nx, y1 + ny, x2 + nx - (x2 - x1) / len * R * s * 0.55, y2 + ny - (y2 - y1) / len * R * s * 0.55];
    el("line", { x1: p[0], y1: p[1], x2: p[2], y2: p[3], stroke: "transparent", "stroke-width": 14 * s }, g);
    el("line", { x1: p[0], y1: p[1], x2: p[2], y2: p[3], stroke: "#000", "stroke-width": 5.5 * s, "stroke-opacity": ".55", "pointer-events": "none" }, g);
    el("line", { x1: p[0], y1: p[1], x2: p[2], y2: p[3], stroke: col, "stroke-width": 3.2 * s, "stroke-dasharray": a.kind === "weapons" ? "" : `${2 * s} ${3 * s}`, "pointer-events": "none" }, g);
    const ux = (x2 - x1) / len, uy = (y2 - y1) / len;
    el("polygon", { points: `${p[2] + ux * 7 * s},${p[3] + uy * 7 * s} ${p[2] - uy * 5 * s},${p[3] + ux * 5 * s} ${p[2] + uy * 5 * s},${p[3] - ux * 5 * s}`, fill: col, stroke: "#000", "stroke-width": 1 * s, "pointer-events": "none" }, g);
    const lx = (p[0] + p[2]) / 2, ly = (p[1] + p[3]) / 2;
    el("rect", { x: lx - 13 * s, y: ly - 9 * s, width: 26 * s, height: 15 * s, rx: 3 * s, fill: "#0c0f13", "fill-opacity": ".85", stroke: col, "stroke-width": 1.2 * s, "pointer-events": "none" }, g);
    const tx = el("text", { x: lx, y: ly + 2.5 * s, "text-anchor": "middle", "font-size": 11 * s, "font-weight": 700, fill: "#fff", stroke: "#000", "stroke-width": 2.5 * s, "paint-order": "stroke", "pointer-events": "none" }, g);
    tx.textContent = `${a.hits}/${a.shots}`;

  });
}
// 3D: the placard is a flat card of a fixed size in the world, so it shrinks as the camera pulls back (s = screen pixels per board unit there);
// its text drops to the name alone when it would be too small to read the bars
const cardF = (s) => Math.max(0.45, Math.min(1.1, s / 1.2));
function drawUnits(layer) {
  const placed = [], hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const list = S.units.filter((u) => u.hex && !u.destroyed);
  // a placard is the same size on the screen at any zoom in the flat map: k = map units per screen pixel
  const d3 = MV.is3d(), uh = MV.unitHeight(), k0 = MV.k(); MV.markScale();
  for (const u of list) { const [x, y] = at(u.hex, uh), r = R * sc(u.hex); placed.push({ x: x - r * 0.7, y: y - r * 0.7, w: r * 1.4, h: r * 1.4 }); } // the sprites
  const baseCount = placed.length;
  for (const u of MV.order(list.map((v) => v.hex)).map((h) => list.find((v) => v.hex === h))) {
    const s = sc(u.hex), Rs = R * s, k = d3 ? cardF(s) : k0, W = 92 * k, H = 38 * k, small = d3 && k < 0.6;
    const [x, y] = at(u.hex, uh), col = teamColour(u), mine = u.team === S.myTeam, fr = fracs(u);
    const g = el("g", { "data-unit": u.id, style: "cursor:pointer" }, layer);
    // the hex base: drawn here in the flat map; in 3D the base is a solid piece of the scene and only its outline is drawn
    el("polygon", { points: d3 ? HP(u.hex, 0.8, uh) : pts(x, y, 0.8), fill: d3 ? "transparent" : col, "fill-opacity": ".5", stroke: S.sel === u.id ? "#fff" : col, "stroke-width": (S.sel === u.id ? 3 : 1.8) * s, "stroke-dasharray": mine ? "" : `${5 * s} ${3 * s}` }, g);
    if (!d3) { // sprite: head, torso, arms, legs
      const sp = el("g", { transform: `translate(${x},${y - 1}) scale(${R / 34})`, fill: "#f4f6f8", stroke: "#0c0f13", "stroke-width": 1, "pointer-events": "none" }, g);
      el("circle", { cx: 0, cy: -13, r: 4.2 }, sp); el("rect", { x: -7, y: -8, width: 14, height: 12, rx: 2 }, sp);
      el("rect", { x: -12, y: -7, width: 4.5, height: 12, rx: 1.5 }, sp); el("rect", { x: 7.5, y: -7, width: 4.5, height: 12, rx: 1.5 }, sp);
      el("rect", { x: -6, y: 5, width: 5, height: 10, rx: 1.5 }, sp); el("rect", { x: 1, y: 5, width: 5, height: 10, rx: 1.5 }, sp);
    }
    // a triangle pointing along DIR facing d: tip at tipR radii, base at baseR radii, half width hw board units
    const tri = (d, tipR, baseR, hw, fill, sw) => {
      const q = (a, b) => P(u.hex, d[0] * a + d[1] * b / R * -1, d[1] * a + d[0] * b / R, uh).join(",");
      return el("polygon", { points: `${q(tipR, 0)} ${q(baseR, -hw)} ${q(baseR, hw)}`, fill, stroke: "#000", "stroke-width": sw * s, "pointer-events": "none" }, g);
    };
    const d = DIR[u.facing] || DIR.N;
    tri(d, 0.82, 0.58, 6, "#fff", 1.2);
    // TORSO TWIST, either side (Daniel, 2026-11-24: "a clear signal of torso twists made by both sides"): an amber arrow the way the torso faces
    if (u.twist) { const F = ["N", "NE", "SE", "S", "SW", "NW"], tf = F[(F.indexOf(u.facing) + u.twist + 6) % 6], t = DIR[tf] || DIR.N;
      tri(t, 0.62, 0.36, 5, "#ffb000", 1);
      const tt = el("title", {}, g); tt.textContent = `torso twisted to face ${tf}`; }
    // moved this turn: a check mark on the hex base
    if (movedMark(u)) { const [mx, my] = P(u.hex, -0.55, -0.55, uh); el("circle", { cx: mx, cy: my, r: 7 * s, fill: "#2e7d4f", stroke: "#fff", "stroke-width": 1.2 * s, "pointer-events": "none" }, g); const ck = el("text", { x: mx, y: my + 3.5 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, g); ck.textContent = "\u2713"; }
    // placard: the first spot that does not cover a sprite or another placard
    let spot = SPOTS[0];
    for (const sp of SPOTS) { const r = { x: x + sp[0] * Rs - W / 2, y: y + sp[1] * Rs - (sp[1] < 0 ? H : 0), w: W, h: H }; if (!placed.slice(baseCount).some((p) => hit(p, r)) && !placed.slice(0, baseCount).some((p) => hit(p, r) && !(Math.abs(sp[0]) < 0.01 && Math.abs(sp[1]) < 0.9))) { spot = sp; break; } }
    const px = x + spot[0] * Rs - W / 2, py = y + spot[1] * Rs - (spot[1] < 0 ? H : 0);
    placed.push({ x: px, y: py, w: W, h: H });
    const far = Math.abs(spot[0]) > 0.5 || Math.abs(spot[1]) > 0.8;
    // PLACARDS STEP BACK when they are not the centre of attention (Daniel, 2026-11-26; Section 14, L1): the active unit, the target and the last
    // clicked at full strength, the rest at half; all faint while the weapons (or physical attacks) are up
    const foc = placardFocus(), boxesUp = attackBoxes().length > 0 && UI.wl === "ring", pop = boxesUp ? (foc.has(u.id) ? 0.5 : 0.2) : foc.has(u.id) ? 1 : 0.5;
    const gp = el("g", { opacity: pop }, g);
    if (far) el("line", { x1: x, y1: y, x2: px + W / 2, y2: py + (spot[1] < 0 ? H : 0), stroke: col, "stroke-width": 1.4 * k, "pointer-events": "none" }, gp);
    const cardH = small ? 17 * k : H;
    el("rect", { x: px, y: py, width: W, height: cardH, rx: 3 * k, fill: "#0c0f13", "fill-opacity": ".88", stroke: col, "stroke-width": 1.6 * k }, gp);
    const t = el("text", { x: px + 5 * k, y: py + 13 * k, "font-size": 11 * k, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, gp); t.textContent = short(u) + (u.name ? " " + u.name.replace(/^\D*/, "") : "");
    // LEFT / RIGHT BARS (Section 24 item 24; the mockup's lrBar): armour and structure split at the centre, the unit's left side on the left
    // half and its right on the right, each wearing in from its outer edge, so the damaged side shows; heat stays one bar
    const sa = { l: sideFrac(u, "a", "Left"), r: sideFrac(u, "a", "Right") }, ss = { l: sideFrac(u, "s", "Left"), r: sideFrac(u, "s", "Right") };
    const aCol = (v) => (v > 0.5 ? "#6fbf86" : v > 0.25 ? "#dba94a" : "#e07468"), sCol = (v) => (v > 0.5 ? "#8fb2d4" : "#e07468");
    if (!small) [["A", sa, aCol], ["S", ss, sCol], ["H", fr.h, () => "#ff7a3c"]].forEach(([lab, v, cf], i) => {
      const by = py + (17 + i * 6.8) * k, bx = px + 14 * k, bw = W - 19 * k, bh = 5.4 * k;
      const l = el("text", { x: px + 5 * k, y: by + 5.4 * k, "font-size": 7.5 * k, fill: "#aab", "pointer-events": "none" }, gp); l.textContent = lab;
      el("rect", { x: bx, y: by, width: bw, height: bh, fill: "#2b333d" }, gp);
      if (typeof v === "number") { el("rect", { x: bx, y: by, width: bw * v, height: bh, fill: cf(v) }, gp); return; }
      const hw = bw / 2;
      el("rect", { x: bx + hw * (1 - v.l), y: by, width: hw * v.l, height: bh, fill: cf(v.l) }, gp);
      el("rect", { x: bx + hw, y: by, width: hw * v.r, height: bh, fill: cf(v.r) }, gp);
      el("line", { x1: bx + hw, y1: by, x2: bx + hw, y2: by + bh, stroke: "#000", "stroke-width": 0.9 * k }, gp);
    });
    if (u.prone) { const p = el("text", { x: x + 16 * s, y: y - 18 * s, "font-size": 8 * s, fill: "#ffd400", "font-weight": 700, stroke: "#000", "stroke-width": 2 * s, "paint-order": "stroke" }, g); p.textContent = "PRONE"; }
    if (u.shutdown) { const p = el("text", { x: x + 16 * s, y: y - 8 * s, "font-size": 8 * s, fill: "#e07468", "font-weight": 700, stroke: "#000", "stroke-width": 2 * s, "paint-order": "stroke" }, g); p.textContent = "OFF"; }
  }
}
// the units at the centre of attention: the active one, the target, the last clicked
function placardFocus() { return new Set([(activeUnit() || {}).id, S.fire ? S.fire.tcur : S.req && S.req.kind === "physical" ? physTarget() : -1, UI.last && UI.last.kind === "unit" ? UI.last.id : -1]); }
// L6 for the Physical Attack Phase: each enemy within reach shows its best to-hit number over it; a tap makes it the target
function drawPhysTargets(layer) {
  const by = new Map(); for (const o of physOpts()) if (!o.blocked) by.set(o.target, Math.min(by.get(o.target) ?? 99, o.tn));
  for (const [id, tn] of by) { const u = unit(id); if (!u || !u.hex) continue; const s = sc(u.hex), cur = id === physTarget(), [px, py] = P(u.hex, 0.3, -0.95, MV.unitHeight());
    el("polygon", { points: HP(u.hex, 0.95), fill: "#e07468", "fill-opacity": cur ? ".35" : ".18", stroke: "#e07468", "stroke-width": (cur ? 3.5 : 2) * s, "pointer-events": "none" }, layer);
    const g = el("g", { style: "cursor:pointer", "data-tn-pill": id }, layer);
    el("rect", { x: px, y: py, width: 28 * s, height: 15 * s, rx: 3 * s, fill: "#000", stroke: cur ? "#fff" : "#e07468", "stroke-width": 1.2 * s }, g);
    const tx = el("text", { x: px + 14 * s, y: py + 11 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, g); tx.textContent = tnText(tn) + "+";
    g.addEventListener("click", (ev) => { ev.stopPropagation(); physSetTarget(id); redraw(); }); }
}
// armour, structure and heat as fractions (1 = untouched; heat 1 = at the unit's limit)
function fracs(u) {
  const mx = S.maxLoc[u.id] || {}; let a = 0, am = 0, st = 0, sm = 0;
  for (const [loc, v] of Object.entries(u.locs || {})) { const m = mx[loc] || v; a += v[0] + (v[1] || 0); am += m[0] + (m[1] || 0); st += v[2]; sm += m[2]; }
  return { a: am ? Math.max(0, a / am) : 1, s: sm ? Math.max(0, st / sm) : 1, h: Math.min(1, (u.heat || 0) / Math.max(1, u.max_heat || 30)) };
}
// MOVED THIS TURN (Section 24 item 3): during the Movement Phase a unit that has moved carries a check mark (map, placard, strip)
const inMovement = () => !!S.req && ["move_order", "movement", "stand_up", "boost", "jump_boost"].includes(S.req.kind);
const movedMark = (u) => inMovement() && !!u.moved && !u.destroyed;
// ---------------------------------------------------------------- THE OVERLAY UI (Daniel, 2026-11-26; INTEGRATION__UI_SYNC.md Section 14)
// The map fills the screen. Two panels lie over it: sideways, your enemy's side on the LEFT and yours on the RIGHT; upright, a band above (the
// enemy's side) and one below (yours). The square between them is the clear area: the camera frames it, the weapons stand round its middle.
// There is no unit sheet: its jobs are in the inspector (top half, opened by a long press) and the two wings (side drawers). Built from the
// frame mockup version 2.5 (reference_art/battlerom_ui/battlerom_frame_mockup.html); every number here is the engine's.
const TABS = ["Hex", "Unit", "Target", "Move", "Weapons", "To-hit", "Attack", "Heat", "Options"];
const UI = { wing: { L: 0, R: 0 }, wtab: { move: { L: "Move", R: "Unit" }, fire: { L: "Target", R: "Weapons" }, phys: { L: "Target", R: "Attack" }, end: { L: "Heat", R: "Unit" } },
  insp: { open: 0, tab: "Hex", hex: null, uid: null, why: "" }, menu: false, last: null, wl: pref("wl", "ring"), ins: { l: 0, r: 0, t: 0, b: 0 }, wide: false,
  cyc: null, pickHex: null, atkSel: null, lim: {}, aimOpen: false, focusW: null, done: new Set(), aord: [], mine: [] };
// which phase the question belongs to: "move" (deployment and movement), "fire" (spotting, TAG, weapons), "phys" (physical attacks), "end"
const phaseKey = () => { const k = S.req && S.req.kind; return ["target", "declaration", "spot", "tag"].includes(k) ? "fire" : k === "physical" ? "phys" : k === "end_phase" ? "end" : "move"; };
const PHASE_LABEL = { move: "Movement", fire: "Weapon Attack", phys: "Physical Attack", end: "End Phase" };
const activeUnit = () => unit(S.req && S.req.unit != null ? S.req.unit : S.sel);
// the to-hit number the engine gives for a unit as a target of the active unit right now (the weapon attack's base, or the physical attack's)
function targetTn(id) {
  if (S.fire) { const e = S.fire.pvt.get(id); return e && e.req ? e.req.base_tn : null; }
  if (S.req && S.req.kind === "physical") { const p = physOpts().find((o) => o.target === id && !o.blocked); return p ? p.tn : null; }
  return null;
}
const tnText = (n) => (n == null ? "—" : n > 12 ? "×" : String(Math.max(2, n)));

// ---- the panels
function lastText() {
  const L = UI.last, a = activeUnit(); if (!L) return '<span class="msg">tap a hex or an enemy</span>';
  if (L.kind === "unit") { const u = unit(L.id); if (!u) return ""; const d = a && a.hex && u.hex ? dist(a.hex, u.hex) : null, tn = u.team !== S.myTeam ? targetTn(u.id) : null;
    return `<b>${esc(u.name)}</b> ${esc(u.mech || "")}${tn != null ? ` &middot; TN <b>${tnText(tn)}</b>` : ""}${d != null && u.team !== S.myTeam ? ` &middot; ${d} hex${d === 1 ? "" : "es"}` : ""}${u.shutdown ? " &middot; shut down" : ""}${u.prone ? " &middot; prone" : ""}${u.destroyed ? " &middot; destroyed" : ""}`; }
  const h = S.board && S.board.hexes[L.l]; if (!h) return "";
  return `<b>Hex ${L.l}</b> &middot; level ${h.l || 0}${terrainText(h) !== "clear" ? " &middot; " + esc(terrainText(h)) : ""}`;
}
function terrainText(h) { const f = h.f || {}; return Object.entries(f).filter(([k]) => !/^bldg_|^road_|elev/.test(k)).map(([k, v]) => `${k.replace(/_/g, " ")}${v && v !== true && v !== 0 ? " " + v : ""}`).join(", ") + (h.b ? (Object.keys(f).length ? ", " : "") + "building" : "") || "clear"; }
function echip(u) {
  const sel = UI.last && UI.last.kind === "unit" && UI.last.id === u.id, tg = (S.fire && S.fire.tcur === u.id) || (S.req && S.req.kind === "physical" && physTarget() === u.id);
  return `<div class="echip${sel ? " sel" : ""}${tg ? " tgt" : ""}${u.destroyed ? " dead" : ""}" data-act="chip" data-u="${u.id}" title="${esc(u.name + " " + (u.mech || ""))}">${esc(short(u))}${u.shutdown ? " &#9211;" : ""}<b>${Math.round(fracOf(u) * 100)}%</b></div>`;
}
const doneNow = (u) => (phaseKey() === "move" ? movedMark(u) : UI.done.has(u.id));
function fchip(u) {
  return `<div class="fchip${u.id === (activeUnit() || {}).id ? " sel" : ""}${doneNow(u) ? " done" : ""}${u.destroyed ? " dead" : ""}" data-act="chip" data-u="${u.id}"><b>${doneNow(u) ? "&#10003; " : ""}${esc(u.name)}</b><span class="msg">${esc(short(u))}${u.prone ? " &middot; prone" : ""}${u.shutdown ? " &middot; off" : ""}</span><span class="bar"><i style="width:${Math.round(fracOf(u) * 100)}%"></i></span></div>`;
}
// heat (Daniel, 2026-11-26): "current heat count (total heat dissipation): end of heat phase total"
const heatLine = (cur, diss, end) => `${cur} (${diss}): ${end}`;
function moveHeatParts() {
  const u = activeUnit() || {}, o = S.mv && S.dest ? optNow() : null, mh = o ? o.heat || 0 : 0, diss = u.sinks ?? 0, cur = u.heat || 0;
  return { cur, diss, mh, end: Math.max(0, cur + mh - diss) };
}
function fireHeatParts() {
  const D = S.decl; if (!D) { const u = activeUnit() || {}; return { cur: u.heat || 0, diss: u.sinks ?? 0, end: Math.max(0, (u.heat || 0) - (u.sinks ?? 0)), gen: 0 }; }
  const r = D.req, w = S.fire ? fireTotals().heat : [...D.sel].reduce((a, id) => a + ((D.rows.find((x) => x.id === id) || {}).heat || 0), 0);
  return { cur: r.heat, diss: r.dissipation, gen: r.move_heat + w, end: heatIfFired() };
}
const heatLimit = (u) => (u && UI.lim[u.id] != null ? UI.lim[u.id] : 4);   // Fire! shows a warning above this end-of-turn heat (the Heat tab sets it; 5 is the scale's first step, Core p.103)
function mpwHtml() {
  const u = activeUnit(), k = phaseKey();
  if (!u || !S.req) return `<button class="mpw" data-act="mpw" disabled><span class="big">${u ? "Heat " + (u.heat || 0) : "&nbsp;"}</span></button>`;
  if (k === "fire" || k === "phys" || k === "end") {
    const h = k === "fire" ? fireHeatParts() : { cur: u.heat || 0, diss: u.sinks ?? 0, end: k === "end" ? S.req.heat.projected : Math.max(0, (u.heat || 0) - (u.sinks ?? 0)), gen: 0 };
    const hot = k === "fire" && h.gen > h.diss, pods = (eq(u).coolant || {}).pods, now = (eq(u).coolant || {}).mode === "now";
    return `<button class="mpw${hot && !now ? " hot" : ""}" data-act="mpw"><span class="big">Heat ${heatLine(h.cur, h.diss, h.end)}</span>${hot && pods ? `<span class="hint on">${now ? "coolant pod: will use" : "tap: use a coolant pod?"}</span>` : ""}</button>`;
  }
  const v = S.mv;
  if (!v) return `<button class="mpw" data-act="mpw"><span class="big">${u.moved ? "Moved" : `MP ${u.run}`}</span><span class="sm">walk ${u.walk}${u.jump ? " · jump " + u.jump : ""}</span><span class="hint">hold: more</span></button>`;
  const o = S.dest ? optNow() : null, j = jumpOn(), max = S.attackSel ? mvBudget(S.attackSel.mode) : o ? mvBudget(o.mode) : j ? v.jump : v.run, used = S.attackSel ? S.attackSel.mp : o ? o.mp : 0, h = moveHeatParts();
  const canJump = v.jump > 0 && !standing() && !(u.prone && !S.standOn);
  return `<button class="mpw" data-act="mpw"><span class="big">MP ${Math.max(0, max - used)}<small>/${max}</small></span><span class="ht${h.end > heatLimit(u) ? " over" : ""}">Heat<br>${heatLine(h.cur, h.diss, h.end)}</span><span class="sm">TMM +${S.attackSel ? S.attackSel.tmm ?? 0 : o ? o.tmm : 0}</span><span class="hint">${canJump ? (j ? "tap: back to ground" : "tap: Jump") : "hold: more moves"}</span></button>`;
}
function moreHtml() {
  if (S.req && S.req.kind === "stand_up") return `<button class="more ctx${S.standOn ? " on" : ""}" data-act="standup">Stand up</button>`;
  return `<button class="more" data-act="more" aria-label="More actions" title="More actions (the inspector)">&#8943;</button>`;
}
// COMMIT: hold to commit (650 ms); the label follows the plan (F3), its colour the move or the attack (F4), a warning for a known chance (F5)
function commitState() {
  const r = S.req, k = phaseKey(), u = activeUnit();
  if (!r) return S.over ? { lab: "Battle over", col: "#8795a5", dis: true } : { lab: "Working", sub: "the engine", col: "#8795a5", dis: true };
  if (r.kind === "deploy") return S.dp && S.dp.hex ? { lab: "Place", sub: `${S.dp.hex} facing ${S.dp.facing}`, col: "#00e5ff" } : { lab: "Place", sub: "tap a green hex", col: "#8795a5", dis: true };
  if (k === "end") return { lab: "Continue", sub: "hold to commit", col: "#8795a5" };
  if (["boost", "jump_boost", "spot", "tag"].includes(r.kind)) return { lab: "Answer", sub: "the question above", col: "#8795a5", dis: true };
  if (k === "fire") {
    if (!S.decl && !S.fire) return { lab: "Hold fire", sub: "hold to commit", col: "#8795a5" };
    const n = S.fire ? S.fire.assign.size : S.decl.sel.size, t = S.fire ? fireTotals().per.size : 1, hp = fireHeatParts();
    return n ? { lab: "Fire!", sub: `${n} weapon${n > 1 ? "s" : ""}${t > 1 ? ` · ${t} targets` : ""}${S.aim && S.aim.loc ? " · aimed " + LOCAB[S.aim.loc] : ""}`, col: "#e0503c", warn: hp.end > heatLimit(u) } : { lab: "Hold fire", sub: "hold to commit", col: "#8795a5" };
  }
  if (k === "phys") { const n = physOn().length; return n ? { lab: "Attack!", sub: `${n} attack${n > 1 ? "s" : ""}`, col: "#e0503c" } : { lab: "No attack", sub: "hold to commit", col: "#8795a5" }; }
  // movement
  if (r.kind === "move_order" && !S.mv) { const v = S.views[S.sel]; return v && v.seq === S.seq ? { lab: "Move", sub: (unit(S.sel) || {}).prone ? "stand up next" : "plan next", col: "#00e5ff" } : { lab: "Move", sub: "looking...", col: "#8795a5", dis: true }; }
  if (S.attackSel) return { lab: S.attackSel.kind === "charge" ? "Charge" : "Death from above", sub: `${S.attackSel.mp} MP`, col: S.attackSel.kind === "charge" ? "#ffd400" : "#ff7a3c", warn: true };
  const o = S.dest ? optNow() : null, stand = standing() && S.standOn;
  if (standing() && !S.standOn) return { lab: "Stay prone", sub: S.prone && S.prone.facing ? "turn to " + S.prone.facing : "hold to commit", col: "#8795a5" };
  if (!o) return { lab: stand ? "Stand up" : "Stand still", sub: S.drop ? "then drop prone" : "hold to commit", col: stand ? "#00e5ff" : "#8795a5", warn: stand };
  const col = { Walk: "#00e5ff", Run: "#ffd400", Jump: "#ff7a3c" }[o.mode] || "#8795a5";
  return { lab: stand ? "Stand + " + o.mode : o.mode === "Stand Still" ? "Stand still" : o.mode, sub: `${o.mp} MP${S.drop ? " · drop prone" : ""}`, col, warn: stand || hazardList(o).length > 0 };
}
function commitHtml() {
  const c = commitState(); if (SAVE.candidate) c.lab = "Meddle";   // the first answer held in a candidate timeline creates it (REC layer)
  const light = ["#00e5ff", "#ffd400", "#8795a5"].includes(c.col);
  return `<button class="commit ${light ? "lt" : "dk"}" data-act="commit" data-hold="1" style="background-color:${c.col}" ${c.dis ? "disabled" : ""}><span class="fill"></span><span class="warn">${c.warn ? "&#9888;" : ""}</span><span class="lab">${esc(c.lab)}</span><span class="sub">${esc(c.sub || "")}</span></button>`;
}
function canUndo() { const k = phaseKey(); if (!S.req) return false; if (k === "fire") return !!(S.fire ? S.fire.assign.size : S.decl && S.decl.sel.size); if (k === "phys") return physOn().length > 0;
  return !!(S.way.length || S.dest || S.attackSel || S.standOn || (S.prone && S.prone.facing) || S.drop || (S.dp && S.dp.hex) || (S.mv && jumpOn())); }
const udHtml = () => `<button class="ic" aria-label="Undo" title="Undo (Esc)" data-act="undo" ${canUndo() ? "" : "disabled"}>&#8630;</button><button class="ic" aria-label="Clear" title="Clear" data-act="clear" ${canUndo() ? "" : "disabled"}>&#10005;</button>`;
function turnText() {
  if (!S.req) return S.over ? "Battle over" : S.phaseText || "Working...";
  if (S.req.kind === "deploy") return "<b>Deployment</b>";
  const turn = (S.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1];
  const k = phaseKey(), left = k === "fire" || k === "phys" ? S.units.filter((u) => u.team === S.myTeam && u.hex && !u.destroyed && !u.shutdown && !UI.done.has(u.id)).length : null;
  return `Turn ${turn || "?"} &middot; <b>${PHASE_LABEL[k]}</b>${esc(turnStatus())}${left != null ? ` &middot; ${left} to ${k === "fire" ? "fire" : "attack"}` : ""}`;
}
function chrome() {
  const app = $("app"), W = app.clientWidth, H = app.clientHeight, wide = W >= H, k = phaseKey(), u = activeUnit();
  UI.wide = wide; app.classList.toggle("wide", wide); app.classList.toggle("tall", !wide); app.classList.toggle("d3", MV.is3d());
  const mine = S.units.filter((x) => x.team === S.myTeam), foes = S.units.filter((x) => x.team !== S.myTeam && S.myTeam != null);
  const tline = `<div class="tbar c3"><button data-act="menu">Menu</button><b>BattleROM</b><button class="rec" data-act="rec" title="Time travel: go back to an earlier question and play it again">&#9679; REC</button></div>`;
  const estrip = `<div class="srow"><button class="arr" data-act="step" data-team="f" data-d="-1" aria-label="Previous enemy">&lsaquo;</button><div class="chips" id="estrip">${foes.map(echip).join("")}</div><button class="arr" data-act="step" data-team="f" data-d="1" aria-label="Next enemy">&rsaquo;</button></div>`;
  const lastL = `<div class="line last"><span class="k">Last</span><span class="t">${lastText()}</span><button data-act="inspect" ${UI.last ? "" : "disabled"}>Inspect</button></div>`;
  const actL = `<div class="line act"><span class="k">Active</span><span class="t">${u ? `<b>${esc(u.name)}</b> ${esc(u.mech || "")}${u.prone ? " &middot; prone" : ""}` : '<span class="msg">waiting</span>'}</span><button data-act="report" id="rep-btn">Report</button></div>`;
  const fstrip = `<div class="srow"><button class="arr" data-act="step" data-team="m" data-d="-1" aria-label="Previous unit">&lsaquo;</button><div class="chips" id="strip">${mine.map(fchip).join("")}</div><button class="arr" data-act="step" data-team="m" data-d="1" aria-label="Next unit">&rsaquo;</button></div>`;
  const boxes = attackBoxes(), list = UI.wl === "list" && boxes.length ? `<div class="wlist">${boxes.join("")}</div>` : "";
  if (wide) {
    $("pnE").innerHTML = tline + estrip + lastL + (list || '<div class="grow"></div>') + `<div class="bl">${mpwHtml()}${moreHtml()}</div>`;
    $("pnF").innerHTML = actL + fstrip + '<div class="grow"></div>' + `<div class="br"><div class="ud">${udHtml()}</div>${commitHtml()}</div>`;
    $("afloat").innerHTML = "";
  } else {
    $("pnE").innerHTML = tline + estrip + lastL;
    $("pnF").innerHTML = (list ? list.replace('class="wlist"', 'class="wlist" style="max-height:150px"') : "") + actL + fstrip;
    $("afloat").innerHTML = `<div class="l">${mpwHtml()}${moreHtml()}</div>${commitHtml()}<div class="r">${udHtml()}</div>`;
  }
  $("ring").innerHTML = (UI.wl === "ring" && !UI.pickHex ? boxes.join("") : "") + ctxHtml();
  $("phase").innerHTML = turnText();
  drawWings(); drawInsp(); drawMenu();
  layoutPanels(); placeOverlay();
  if (typeof TT !== "undefined") TT.sync();   // REC layer: its strip, the report's tabs, the Report / Inspect buttons kept on top of their panels
}
// the clear area: what the panels leave of the map (the camera frames it; the weapons stay inside it)
function layoutPanels() {
  const app = $("app"), W = app.clientWidth, H = app.clientHeight, wide = W >= H;
  if (wide) { const side = Math.max(168, Math.floor((W - H) / 2)); app.style.setProperty("--side", side + "px"); UI.ins = { l: side, r: side, t: 0, b: 0 }; }
  else { const fb = $("pnF").offsetHeight, af = $("afloat"); af.style.bottom = (fb + 6) + "px"; UI.ins = { l: 0, r: 0, t: $("pnE").offsetHeight, b: fb + af.offsetHeight + 12 }; }
  const I = UI.ins, cw = W - I.l - I.r;
  const m = $("menu"), mb = document.querySelector('#pnE [data-act="menu"]'); if (m && mb) { const r = mb.getBoundingClientRect(); m.style.left = Math.max(6, r.left) + "px"; m.style.top = (r.bottom + 4) + "px"; }
  const t = $("toast"); t.style.left = (I.l + cw / 2) + "px"; t.style.top = (I.t + 8) + "px";
  const a = $("ask"); a.style.left = (I.l + 6) + "px"; a.style.top = (I.t + 44) + "px"; a.style.maxWidth = Math.min(440, cw - 12) + "px";
  const c = $("card"); c.style.left = (I.l + 8) + "px"; c.style.top = (I.t + 44) + "px";
  const z = $("topline"); z.style.left = (I.l + 6) + "px"; z.style.right = (I.r + 6) + "px"; z.style.top = (I.t + 6) + "px";
  document.querySelector(".edge.L").style.left = I.l + "px"; document.querySelector(".edge.R").style.right = I.r + "px";
  if (MV.setInsets(I) && S.board) refocus();
}
// the camera's last framing, done again when the clear area changes (a turn of the phone, a panel that grew)
function refocus() { if (S.lastFocus) MV.focusOn(S.lastFocus[0], S.lastFocus[1]); else MV.fit(); }
const COLX = { LA: -2, LT: -1, HD: 0, CT: 0, RT: 1, RA: 2, LL: -1, RL: 1 };
// every frame: the weapons (or physical attacks) at FIXED places round the middle of the clear area (Daniel, 2026-11-26: "Fixed placement on
// screen regardless of where the map is currently looking"), in the active unit's critical-table layout: LA, LT, head above / centre torso
// below, RT, RA; the legs under the side torsos. No location text on them: the place says it.
function placeOverlay() {
  const ring = $("ring"), W = ring.clientWidth, H = ring.clientHeight, I = UI.ins, cx = I.l + (W - I.l - I.r) / 2, cy = I.t + (H - I.t - I.b) / 2;
  const clampX = (x, w) => Math.max(I.l + 4, Math.min(W - I.r - w - 4, x)), clampY = (y, hh) => Math.max(I.t + 40, Math.min(H - I.b - hh - 4, y));
  const boxes = [...ring.querySelectorAll(".wb")], CW = Math.min(78, (W - I.l - I.r) / 5.4), RH = 30;
  const groups = {}; boxes.forEach((b) => { (groups[b.dataset.loc] = groups[b.dataset.loc] || []).push(b); });
  const count = (l) => (groups[l] || []).length;
  for (const [l, list] of Object.entries(groups)) list.forEach((b, j) => {
    const w = b.offsetWidth; let x, y;
    if (l === "HD") { x = cx; y = cy - 40 - (j + 1) * RH; }
    else if (l === "CT") { x = cx; y = cy + 28 + j * RH; }
    else if (l === "LL" || l === "RL") { x = cx + (l === "LL" ? -1 : 1) * CW; y = cy + Math.max(40, count(l === "LL" ? "LT" : "RT") * RH / 2 + 8) + j * RH; }
    else { x = cx + (COLX[l] ?? 0) * CW; y = cy - (list.length * RH) / 2 + j * RH; }
    b.style.transform = `translate(${clampX(x - w / 2, w).toFixed(1)}px,${clampY(y, RH).toFixed(1)}px)`;
  });
  const cb = ring.querySelector(".ctxbox");
  if (cb) { const w = cb.offsetWidth;
    if (phaseKey() !== "move") { const nCT = count("CT"); cb.style.transform = `translate(${clampX(cx - w / 2, w).toFixed(1)}px,${clampY(cy + 28 + nCT * RH + 40, 34).toFixed(1)}px)`; }
    else if (UI.last && UI.last.kind === "unit" && unit(UI.last.id) && unit(UI.last.id).hex) { const [x, y] = at(unit(UI.last.id).hex); const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal, sx = r.width / (vb.width || 1), px = (x - vb.x) * sx, py = (y - vb.y) * sx;
      cb.style.transform = `translate(${clampX(px - w / 2, w).toFixed(1)}px,${clampY(py + 36, 34).toFixed(1)}px)`; } }
}
// context actions ABOUT a unit live by that unit (Daniel, 2026-11-26): Aimed shot at an immobile target; Charge / Death from above in reach
function ctxHtml() {
  const b = [];
  if (S.fire && S.decl && S.fire.tcur != null) { const t = unit(S.fire.tcur);
    if (t && aimable(t)) { if (!UI.aimOpen) b.push(`<button data-act="ctx" data-do="aimed">Aimed shot</button>`); else for (const l of AIM_LOCS) if (t.locs && t.locs[l] && !t.locs[l][3]) b.push(`<button data-act="ctx" data-do="aimloc" data-loc="${esc(l)}" class="${S.aim && S.aim.loc === l ? "on" : ""}">${LOCAB[l]}</button>`); } }
  if (moving() && !standing() && UI.last && UI.last.kind === "unit" && S.mv && S.mv.attacks) { const id = UI.last.id, list = S.mv.attacks.filter((a) => a.target === id);
    if (list.some((a) => a.kind === "charge")) b.push(`<button data-act="ctx" data-do="charge" data-u="${id}" class="${S.attackSel && S.attackSel.kind === "charge" ? "on" : ""}">Charge</button>`);
    if (list.some((a) => a.kind === "dfa")) b.push(`<button data-act="ctx" data-do="dfa" data-u="${id}" class="${S.attackSel && S.attackSel.kind === "dfa" ? "on" : ""}">Death from above</button>`); }
  return b.length ? `<div class="ctxbox">${b.join("")}</div>` : "";
}
const AIM_LOCS = ["Head", "Center Torso", "Left Torso", "Right Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg"];
// an aimed shot needs an immobile target (Core p.70): shut down or its MechWarrior out; the engine says so in the preview (aimable)
const aimable = (t) => { const e = S.fire && S.fire.pvt.get(t.id); return !!(e && e.req && e.req.aimable); };

// ---- the attack boxes: weapons in the Weapon Attack Phase, physical attacks in the Physical Attack Phase
const LOC2 = { "Head": "HD", "Center Torso": "CT", "Left Torso": "LT", "Right Torso": "RT", "Left Arm": "LA", "Right Arm": "RA", "Left Leg": "LL", "Right Leg": "RL",
  "Front Left Leg": "LA", "Front Right Leg": "RA", "Rear Left Leg": "LL", "Rear Right Leg": "RL", "Center Leg": "CT" };
const locOf = (w) => LOC2[[].concat(w.loc || [])[0]] || "CT";
// a weapon's short name, five characters at most (Daniel, 2026-11-26: "a 5 letter cap works for now"): known names, else the initials and the number
const SHORT = { "machine gun": "MG", "flamer": "Flmr", "gauss rifle": "Gauss", "ppc": "PPC", "er ppc": "ERPPC", "tag": "TAG", "narc": "Narc", "anti-missile system": "AMS", "plasma rifle": "Plsma", "arrow iv": "ArwIV" };
function shortName(n) {
  const s = String(n || "").replace(/\s*\((?:R|Rear|OS|I-OS)\)\s*/gi, "").replace(/^(IS|CL|Clan|Inner Sphere)\s+/i, "").trim(), k = s.toLowerCase();
  if (SHORT[k]) return SHORT[k];
  const num = (s.match(/(\d+)(?!.*\d)/) || [""])[0], words = s.replace(/[\/\-]/g, " ").replace(/\d+/g, " ").split(/\s+/).filter(Boolean);
  if (words.length === 1 && !num) return words[0].slice(0, 5);
  const ini = words.map((w) => (/^(ER|LB|AC|SRM|LRM|MRM|ATM|MML|UAC|RAC|LAC|HAG|MG|X)$/i.test(w) ? w.toUpperCase() : w[0].toUpperCase())).join("");
  return (ini + num).slice(0, 5);
}
// the weapon rows shown: the declaration's (the target in view); each weapon keeps ITS target (split fire)
function weaponState(w) {
  const F = S.fire, D = S.decl, t = F ? F.assign.get(w.id) : D && D.sel.has(w.id) ? D.req.target : undefined, cur = F ? F.tcur : D && D.req.target;
  if (t != null && t !== cur) return "else";
  if (t === cur && t != null) return "on";
  if (!w.in_range || w.jammed || w.tn == null) return "out";
  return "rdy";
}
function attackBoxes() {
  const k = phaseKey();
  if (k === "fire" && S.decl && !(S.fire && S.fire.tcur == null)) return S.decl.rows.map((w) => {
    const st = weaponState(w), band = String(w.range || "").toLowerCase(), tint = st === "rdy" || st === "on" ? (band.startsWith("med") ? " med" : band.startsWith("lon") ? " lng" : "") : "";
    const to = st === "else" ? unit(S.fire.assign.get(w.id)) : null;
    return `<div class="wb ${st}${tint}${S.decl.focus === w.id ? " foc" : ""}" data-act="wb" data-w="${w.id}" data-loc="${locOf(w)}" title="${esc(w.name)}${w.rear ? " (rear)" : ""} &middot; ${esc(w.range || "out of range")}">${esc(shortName(w.name))}${w.rear ? '<span class="n2">r</span>' : ""}${to ? `<span class="to">&rarr; ${esc(short(to))}</span>` : ""}<span class="tn" data-act="tn" data-w="${w.id}">${tnText(w.tn)}</span></div>`;
  });
  if (k === "phys") return physBoxesFor().map((b) => physBox(b.o, b.loc));
  return [];
}
function drawWings() {
  for (const s of ["L", "R"]) {
    const w = $("wing" + s), st = UI.wing[s], tab = (UI.wtab[phaseKey()] || UI.wtab.move)[s];
    w.classList.toggle("open", st > 0); w.classList.toggle("full", st === 2); document.querySelector(".edge." + s).hidden = st > 0;
    w.querySelector(".wh").innerHTML = TABS.map((t) => `<button data-act="wtab" data-side="${s}" data-tab="${t}" class="${t === tab ? "on" : ""}">${t}</button>`).join("");
    if (st) w.querySelector(".wbody").innerHTML = pageHtml(tab, { uid: (activeUnit() || {}).id });
  }
}
function openInsp(tab, hex, uid, why) { UI.insp = { open: 1, tab, hex: hex || null, uid: uid ?? null, why: why || "" }; UI.wing = { L: 0, R: 0 }; UI.menu = false; chrome(); }
function drawInsp() {
  const I = UI.insp, box = $("insp"); box.classList.toggle("open", I.open > 0); box.classList.toggle("full", I.open === 2); $("icatch").classList.toggle("on", I.open === 1);
  if (!I.open) return;
  const a = activeUnit(), tid = S.fire ? S.fire.tcur : S.req && S.req.kind === "physical" ? physTarget() : null, T = unit(tid);
  box.querySelector(".t1").innerHTML = T && a && a.hex && T.hex ? `Target: ${esc(T.name)} ${esc(T.mech || "")} &middot; TN ${tnText(targetTn(T.id))} &middot; ${dist(a.hex, T.hex)} hex${dist(a.hex, T.hex) === 1 ? "" : "es"}` : UI.last ? lastText().replace(/<[^>]+>/g, "") : "Nothing selected";
  box.querySelector(".t2").textContent = `${I.tab}${I.hex ? " · hex " + I.hex : ""}${I.uid != null && unit(I.uid) ? " · " + unit(I.uid).name : ""}${I.why ? " · opened from " + I.why : ""}`;
  box.querySelector(".it").innerHTML = TABS.map((t) => `<button data-act="itab" data-tab="${t}" class="${t === I.tab ? "on" : ""}">${t}</button>`).join("");
  box.querySelector(".ib").innerHTML = pageHtml(I.tab, { uid: I.uid, hex: I.hex });
}
function drawMenu() {
  const m = $("menu"); m.hidden = !UI.menu; if (!UI.menu) return;
  const it = (label, act, extra, on) => `<div class="item ${on ? "on" : ""}" data-act="${act}" ${extra || ""}>${label}</div>`;
  m.innerHTML = `<div class="f">Weapons in the fire phase</div>${it("Around the target", "wl", 'data-v="ring"', UI.wl === "ring")}${it("List", "wl", 'data-v="list"', UI.wl === "list")}
    <div class="f">Look</div>${Object.entries(LOOKS).map(([k, n]) => it(n, "look", `data-v="${k}"`, O.look === k)).join("")}
    <div class="f">View</div>${it("Tabletop view (3D)", "view3d", "", MV.mode === "3d")}${it("Colour-blind mode", "cvd", "", O.cvd)}${it("Range bands for the weapon", "rings", "", O.rings)}${it("Hex numbers", "labels", "", O.labels)}${it("Attack lines (the latest turn)", "atk", "", O.atk)}
    <div class="f">Game</div>${it("Report", "report")}${it("Save game to a file", "save-file")}${SAVE.parent ? it("Back to the earlier timeline", "back-parent") : ""}${SAVE.child ? it("On to the later timeline", "fwd-child") : ""}${it("Game options (also: long press Menu)", "options")}${it("Back to the Lab", "lab")}`;
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), msg.length > 60 ? 4200 : 2600); }

// ---- the pages (one set of tabs, shared by the wings and the inspector)
function armorBars(u) {
  const row = (lab, l, r, cf) => `<span>${lab}</span><i><b style="width:${Math.round(l * 100)}%;background:${cf(l)};margin-left:auto"></b></i><i><b style="width:${Math.round(r * 100)}%;background:${cf(r)}"></b></i>`;
  return `<div class="bars"><span></span><span class="msg">left side</span><span class="msg">right side</span>${row("Armor", sideFrac(u, "a", "Left"), sideFrac(u, "a", "Right"), (v) => (v > 0.5 ? "#6fbf86" : v > 0.25 ? "#dba94a" : "#e07468"))}${row("Structure", sideFrac(u, "s", "Left"), sideFrac(u, "s", "Right"), (v) => (v > 0.5 ? "#8fb2d4" : "#e07468"))}</div>`;
}
function pageHtml(tab, ctx) {
  const a = activeUnit(), k = phaseKey(), u = (ctx.uid != null && unit(ctx.uid)) || a;
  if (!u && tab !== "Options" && tab !== "Hex") return '<p class="msg">Nothing to show yet.</p>';
  if (tab === "Hex") {
    const l = ctx.hex || (UI.last && UI.last.kind === "hex" ? UI.last.l : u && u.hex), h = l && S.board && S.board.hexes[l]; if (!h) return '<p class="msg">No hex.</p>';
    const here = S.units.filter((x) => x.hex === l && !x.destroyed), acts = [];
    if (S.fire) { here.filter((x) => S.req.enemies.some((e) => e.id === x.id)).forEach((x) => acts.push(`<button data-act="opt" data-k="tgtunit" data-u="${x.id}">Target ${esc(x.name)}</button>`));
      acts.push(`<button data-act="opt" data-k="tgthex" data-l="${l}">Target this hex</button>`); if (h.b) acts.push(`<button data-act="opt" data-k="tgthex" data-l="${l}">Target the building</button>`); }
    if (moving() && !here.length && reachHas(l)) acts.push(`<button data-act="opt" data-k="moveto" data-l="${l}">Plan a move here</button>`);
    return `<h4>Hex ${l}</h4><div class="kv"><span>Level</span><span>${h.l || 0}</span><span>Terrain</span><span>${esc(terrainText(h))}</span>${a && a.hex ? `<span>Range</span><span>${dist(a.hex, l)} hex${dist(a.hex, l) === 1 ? "" : "es"} from ${esc(a.name)}</span>` : ""}</div>
      <h4>In this hex</h4>${here.length ? here.map((x) => `<div>${esc(x.name)} ${esc(x.mech || "")}${x.shutdown ? " (shut down)" : ""}${x.prone ? " (prone)" : ""}</div>`).join("") : '<p class="msg">Nothing.</p>'}
      ${acts.length ? `<h4>Special actions</h4><div class="acts">${acts.join("")}</div>` : ""}`;
  }
  if (tab === "Unit" || tab === "Target") {
    let v = u; if (tab === "Target") { v = unit(S.fire ? S.fire.tcur : S.req && S.req.kind === "physical" ? physTarget() : UI.last && UI.last.kind === "unit" ? UI.last.id : null); if (!v) return '<p class="msg">No target.</p>'; }
    const f = fracs(v), mine = v.team === S.myTeam;
    return `<h4>${esc(v.name)} ${esc(v.mech || "")}${mine ? "" : " (enemy)"}</h4><div class="kv"><span>Tons</span><span>${v.tons || "?"}</span><span>MP</span><span>walk ${v.walk} / run ${v.run}${v.jump ? " / jump " + v.jump : ""}</span><span>Heat</span><span>${v.heat}${v.sinks != null ? ` (sinks ${v.sinks})` : ""}</span><span>Pilot</span><span>gunnery ${v.gunnery} / piloting ${v.piloting}${v.pilot_hits ? ` &middot; ${v.pilot_hits} hit${v.pilot_hits > 1 ? "s" : ""}` : ""}</span><span>State</span><span>${[v.destroyed ? "destroyed" : "", v.shutdown ? "shut down" : "", v.prone ? "prone" : "", v.moved ? "moved" : ""].filter(Boolean).join(", ") || "ready"} &middot; faces ${v.facing}</span><span>Armor</span><span>${Math.round(f.a * 100)}% &middot; structure ${Math.round(f.s * 100)}%</span></div>
      <h4>Armor and structure</h4>${armorBars(v)}${armorTab(v)}
      <h4>Weapons</h4>${weaponsTab(v)}
      ${tab === "Unit" ? `<h4>Equipment</h4>${equipBody(v)}` : ""}
      <h4>Critical slots</h4>${critsHtml(v)}`;
  }
  if (tab === "Move") {
    if (!u || u.team !== S.myTeam) return '<p class="msg">Movement options are for your units.</p>';
    if (!moving() || (S.mv && S.mv.unit !== u.id && !(standing() && S.req.unit === u.id))) return `<h4>${esc(u.name)}</h4><p class="msg">${moving() ? "Another unit is moving now." : "Not the Movement Phase."}</p>`;
    const v = S.mv, o = S.dest ? optNow() : null, os = S.dest ? destOpts() : [], modes = [...new Set(os.map((x) => x.mode))], acts = [];
    if (v && v.jump > 0 && !standing()) acts.push(`<button data-act="opt" data-k="jump" class="${jumpOn() ? "on" : ""}">Jump</button>`);
    for (const m of modes) acts.push(`<button data-act="opt" data-k="mode" data-m="${m}" class="${m === S.mode ? "on" : ""}">${m === "Stand Still" ? "Stand still" : m + " " + mvBudget(m)}</button>`);
    if (dropOk(o)) acts.push(`<button data-act="opt" data-k="drop" class="${S.drop ? "on" : ""}">Go prone at the end (+1 MP)</button>`);
    if (standing()) { acts.push(`<button data-act="standup" class="${S.standOn ? "on" : ""}">Stand up (needs ${S.req.tn}+)</button>`); if (S.req.careful && S.req.careful.available) acts.push(`<button data-act="opt" data-k="careful">Careful stand (needs ${S.req.careful.tn}+, the whole move)</button>`); }
    if (S.req.kind === "movement" && !v.entry) acts.push(`<button data-act="opt" data-k="eject">Eject...</button>`);
    const hz = o ? hazardList(o) : [];
    return `<h4>${esc(u.name)} movement</h4><div class="acts">${acts.join("")}</div>
      ${o ? `<div class="kv" style="margin-top:8px"><span>Plan</span><span>${o.mode} to ${S.dest} facing ${S.facing}</span><span>Cost</span><span>${o.mp} MP (turns included), ${o.hexes} hex${o.hexes === 1 ? "" : "es"}</span><span>TMM</span><span>+${o.tmm}</span><span>Heat</span><span>${o.heat}</span></div>` : '<p class="note">Tap a lit hex for a waypoint: cyan = walk, yellow = run, orange = jump.</p>'}
      ${S.way.length > 1 ? `<p class="note">Waypoints: ${S.way.map((h, i) => i + 1 + " " + h).join(" &rarr; ")}. The unit walks exactly this route.</p>` : ""}
      ${hz.length ? `<h4>Chances on this move</h4><ul>${hz.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}
      ${standing() ? `<p class="note">Standing up costs 2 MP and needs a Piloting roll of ${S.req.tn}+ (2D6); a failed roll is a fall, and you decide again from where the 'Mech lies.</p>` : ""}
      <p class="note">Lateral shift, hull down and climbing are offered here when the engine allows them for this unit.</p>`;
  }
  if (tab === "Weapons") {
    if (S.decl && u.id === activeUnit().id) return weaponModesHtml();
    return `<h4>${esc(u.name)} weapons</h4>${weaponsTab(u)}`;
  }
  if (tab === "To-hit") {
    const D = S.decl, w = D && D.rows.find((x) => x.id === (UI.focusW ?? D.focus));
    if (S.req && S.req.kind === "physical") return physTnHtml();
    if (!D || !w) return '<p class="msg">No weapon is being aimed now.</p>';
    return tnTableHtml(D.req, w);
  }
  if (tab === "Attack") {
    const sel = UI.atkSel;
    if (sel && sel.kind === "past") { const x = (S.atkList || [])[sel.i]; if (x) return `<h4>${esc(x.a)} &rarr; ${esc(x.t)}</h4><p class="msg">turn ${x.turn}, ${x.hits} of ${x.shots} hit</p><div class="cardrep">${reportHtml(x.lines)}</div>`; }
    if (sel && sel.kind === "mine") { const x = UI.mine[sel.i]; if (x) return `<h4>${esc(x.a)} &rarr; ${esc(x.t)} (committed)</h4><table><tr><th>Weapon</th><th>TN</th></tr>${x.w.map((y) => `<tr><td>${esc(y.n)}</td><td class="n">${tnText(y.tn)}</td></tr>`).join("")}</table>`; }
    if (S.fire && S.decl) { const T = fireTotals(), F = S.fire;
      if (!T.n) return '<p class="msg">No weapon is on yet.</p>';
      return [...T.per].map(([t, v]) => { const req = (F.pvt.get(t) || {}).req || { weapons: [] }; return `<h4>${esc((unit(t) || {}).name || t)} &middot; range ${req.distance ?? "?"}${t === primaryOf() ? " &middot; primary" : " &middot; secondary (+1)"}</h4><table><tr><th>Weapon</th><th>TN</th><th>Heat</th></tr>${[...F.assign].filter(([, x]) => x === t).map(([wid]) => { const w = req.weapons.find((x) => x.id === wid) || {}; return `<tr><td>${esc(w.name || wid)}</td><td class="n">${tnText(w.tn)}</td><td class="n">${w.heat ?? ""}</td></tr>`; }).join("")}</table><p class="note">about ${v.ev.toFixed(1)} damage</p>`; }).join("");
    }
    if (S.req && S.req.kind === "physical") { const on = physOn(); return on.length ? `<table><tr><th>Attack</th><th>Target</th><th>TN</th><th>Damage</th></tr>${on.map((o) => `<tr><td>${esc(o.name)}</td><td>${esc((unit(o.target) || {}).name || "")}</td><td class="n">${tnText(o.tn)}</td><td class="n">${o.damage}</td></tr>`).join("")}</table>` : '<p class="msg">No attack is on yet.</p>'; }
    return '<p class="msg">No attack.</p>';
  }
  if (tab === "Heat") {
    const e = eq(u), mine = u.team === S.myTeam, h = phaseKey() === "fire" && u.id === (a || {}).id ? fireHeatParts() : phaseKey() === "move" && u.id === (a || {}).id ? moveHeatParts() : { cur: u.heat, diss: u.sinks ?? 0, end: Math.max(0, u.heat - (u.sinks ?? 0)) };
    return `<h4>${esc(u.name)} heat</h4><div class="kv"><span>Now</span><span>${h.cur}</span><span>Dissipation</span><span>${h.diss}</span><span>End of this turn</span><span>${h.end}${S.req && S.req.kind === "end_phase" ? ` (now ${S.req.heat.now}, movement ${S.req.heat.movement}, weapons ${S.req.heat.weapons}, sinks ${S.req.heat.sinks})` : ""}</span></div>
      <p class="note">The heat scale (Core p.103): 5 &minus;1 MP, 8 +1 to hit, 14 a shutdown roll, 19 an ammunition roll, 30 shut down.</p>
      ${mine ? `<h4>Heat limit for Fire!</h4><div class="acts"><button data-act="opt" data-k="lim" data-d="-1">&minus;</button><b style="align-self:center">${heatLimit(u)}</b><button data-act="opt" data-k="lim" data-d="1">+</button></div><p class="note">Fire! shows &#9888; when the plan ends the turn above this heat.</p>` : ""}
      ${mine && e.coolant && e.coolant.pods ? `<h4>Coolant pods (${e.coolant.pods})</h4><div class="acts">${["auto", "hold", "now"].map((m) => `<button class="${e.coolant.mode === m ? "on" : ""}" data-act="sw-cool" data-u="${u.id}" data-v="${m}">${m === "auto" ? "Automatic" : m === "hold" ? "Hold" : "Use one this turn"}</button>`).join("")}</div>` : ""}
      ${mine && e.radical && e.radical.has ? `<h4>Radical heat sinks</h4><div class="acts"><button data-act="sw-rad" data-u="${u.id}" data-v="${e.radical.on ? 0 : 1}" class="${e.radical.on ? "on" : ""}">${e.radical.on ? "On" : "Off"}</button></div>` : ""}`;
  }
  if (tab === "Options") {
    const b = (act, v, l, on) => `<button data-act="${act}" ${v != null ? `data-v="${v}"` : ""} class="${on ? "on" : ""}">${l}</button>`;
    return `<h4>Weapons in the fire phase</h4><div class="acts">${b("wl", "ring", "Around the target", UI.wl === "ring")}${b("wl", "list", "List", UI.wl === "list")}</div>
      <h4>Look</h4><div class="acts">${Object.entries(LOOKS).map(([k2, n]) => b("look", k2, n, O.look === k2)).join("")}</div>
      <h4>View</h4><div class="acts">${b("view3d", null, "Tabletop view (3D)", MV.mode === "3d")}${b("cvd", null, "Colour-blind mode", O.cvd)}${b("rings", null, "Range bands", O.rings)}${b("labels", null, "Hex numbers", O.labels)}${b("atk", null, "Attack lines", O.atk)}${b("dice", null, "Dice details in the report", O.dice)}</div>
      <h4>Tabletop looks</h4><div class="acts">${["relief", "glass", "trees", "skin"].map((k2) => `<button data-act="t3" data-k="${k2}">${{ relief: "Height of a level", glass: "Glass of raised tiles", trees: "Trees", skin: "Table" }[k2]}: ${t3name(k2)}</button>`).join("")}${b("t3", null, "Bevel toward lower hexes", t3get().bevel).replace('data-act="t3"', 'data-act="t3" data-k="bevel"')}</div>
      <h4>Game</h4><div class="acts">${b("report", null, "Report", false)}${b("lab", null, "Back to the Lab", false)}</div>`;
  }
  return "";
}
function reachHas(l) { if (!S.mv) return false; const idx = S.way.length ? S.wrIdx : (S.reachIdx = S.reachIdx || reachIndex(S.mv)); return !!(idx && idx[l]); }
function critsHtml(u) {
  const names = S.critNames[u.id] || {}, alive = u.crit_alive || {};
  return Object.keys(names).map((loc) => `<div><b>${LOCAB[loc] || loc}</b></div><div class="crit">${names[loc].map((n, i) => `<span class="${alive[loc] && alive[loc][i] === false ? "x" : ""}">${esc(n)}</span>`).join("")}</div>`).join("") || '<p class="msg">Not known.</p>';
}
// the weapon modes, rates, ammunition feeds and capacitors of the active unit's weapons (long press a weapon box: Section 14, I4)
function weaponModesHtml() {
  const D = S.decl, rows = D.rows, f = UI.focusW ?? D.focus;
  const aimW = rows.find((w) => isDistant(w) && (S.fire ? S.fire.assign.has(w.id) : D.sel.has(w.id)));
  return `<h4>${esc(D.req.name)}: weapons</h4><table><tr><th>Weapon</th><th>Loc</th><th>Mode</th><th>Ammo</th></tr>${rows.map((w) => `<tr${w.id === f ? ' style="background:color-mix(in srgb,var(--link) 18%,transparent)"' : ""}><td>${esc(w.name)}${w.rear ? " (r)" : ""}${w.jammed ? " <b class=\"err\">JAMMED</b>" : ""}</td><td>${esc(locOf(w))}</td>
    <td>${(w.modes || []).length > 1 ? `<button class="sm" data-act="mode-w" data-w="${w.id}">${esc(w.mode || "mode")}</button>` : esc(w.mode || "—")}${(w.rates || []).length > 1 ? ` <button class="sm" data-act="rate-w" data-w="${w.id}">x${w.shots}</button>` : ""}${w.chargeable ? ` <button class="sm ${D.charge.has(w.name) ? "on" : ""}" data-act="charge-w" data-w="${w.id}">&#9889; charge</button>` : ""}</td>
    <td>${(w.bins || []).length ? w.bins.map((b) => `<button class="sm ${b.selected ? "on" : ""}" data-act="bin-pick" data-w="${w.id}" data-b="${b.id}">${esc(LOCAB[b.loc] || b.loc || "?")} ${esc(b.name)} ${b.shots ?? "?"}${b.selected ? " &middot; feeds first" : ""}</button>`).join(" ") + ` <button class="sm" data-act="bin-pick" data-w="${w.id}" data-b="">Automatic</button>` : "—"}</td></tr>`).join("")}</table>
    ${aimW ? `<p class="note warnt">${esc(aimW.name)} is a distant shot: it lands next turn. Aim: <b>${D.aim[aimW.id] || D.req.target_hex}</b> <button class="sm ${D.aimFor ? "on" : ""}" data-act="aim-w" data-id="${aimW.id}">${D.aimFor ? "tap a hex on the map" : "Change the aim hex"}</button></p>` : ""}
    <div class="acts"><button data-act="strike">${["Strike (the weapons worth their heat)", "Alpha strike (everything in range)"][D.strike % 2]}</button></div>`;
}
// the number to hit, line by line (long press a to-hit number: Section 14, I4): the engine's own list
function tnTableHtml(req, w) {
  const b = req.breakdown, sgn = (n) => (n > 0 ? "+" : "") + n, line = (label, v) => (v || v === 0 ? `<tr><td>${label}</td><td class="n">${sgn(v)}</td></tr>` : "");
  const band = String(w.range || "").toLowerCase().replace(/[^a-z]/g, ""), bandKey = Object.keys(RANGE_MOD).find((k) => band.startsWith(k.slice(0, 3)));
  const bandMod = bandKey != null ? RANGE_MOD[bandKey] : 0, adj = w.adj || 0, rest = adj - bandMod;
  const mode = b.attacker_mode || "", moved = { "Stand Still": "stood still", Walk: "walked", Run: "ran", Jump: "jumped" }[mode] || mode.toLowerCase();
  const rows = [`<tr><td>${esc(req.name)}'s gunnery</td><td class="n">${b.gunnery}</td></tr>`, line(`${esc(req.name)} ${esc(moved)}`, b.attacker_movement), line(`${esc(req.target_name)}'s movement (TMM)`, b.target_movement),
    line("terrain between, and in the target's hex", b.line_of_sight), line("partial cover", b.cover), line("heat", b.heat), line("target prone", b.target_prone), line("stealth", b.stealth),
    line(`other${b.note ? " (" + esc(b.note) + ")" : b.secondary ? " (secondary target)" : ""}`, b.other),
    line(`${bandKey || w.range || "range"} range`, bandKey != null ? bandMod : null), line(`${esc(w.name)}'s own modifiers (ammunition, mode, minimum range...)`, bandKey != null ? rest : adj)].filter(Boolean).join("");
  return `<h4>${esc(w.name)} &rarr; ${esc(req.target_name)} &middot; range ${req.distance}</h4><table class="tnt">${rows}<tr class="tot"><td>To hit</td><td class="n">${w.tn != null ? `${w.tn}+ (${Math.round((oddsOf(w.tn) || 0) * 100)}%)` : "no shot"}</td></tr></table>`;
}

// ---- PHYSICAL ATTACKS work the same way as weapons (Daniel, 2026-11-26; Section 14, J): punches in each arm section, push in BOTH arm sections,
// a kick in each leg place. The engine lists every attack the active unit could make on each adjacent enemy (`attacks`: kind, name, limbs,
// target, to-hit, damage) and the ones it cannot make with the reason (`blocked`: Core pp.77, 81-83). One TYPE a turn (p.77); selecting one
// punch activates both arms; a punch may go at a SECONDARY target (turn it off, pick the other target, turn it on again; p.82 lets each arm
// punch a target in its own side arc).
const PH_LOCS = { "Left Arm": "LA", "Right Arm": "RA", "Left Leg": "LL", "Right Leg": "RL", "Front Left Leg": "LA", "Front Right Leg": "RA", "Rear Left Leg": "LL", "Rear Right Leg": "RL" };
const PH_SHORT = { punch: "Punch", kick: "Kick", push: "Push", club: "Club", claw: "Claw" };
function physOpts() {
  const r = S.req; if (!r || r.kind !== "physical") return [];
  if (S.phys && S.phys.seq === S.seq) return S.phys.list;
  let list = [];
  if (r.attacks) list = r.attacks.map((a) => ({ ...a, key: `${a.kind}|${a.name}|${a.target}` }));
  else for (const k of r.kinds || []) for (const o of k.options) { const m = /\(([^)]+)\)/.exec(o.name); list.push({ kind: k.kind, name: o.name, limb: m ? [m[1]] : k.kind === "push" ? ["Left Arm", "Right Arm"] : [], target: r.target, tn: o.tn, damage: o.damage, heat: o.heat, key: `${k.kind}|${o.name}|${r.target}` }); }
  for (const b of r.blocked || []) list.push({ ...b, blocked: true, key: `${b.kind}|${b.name}|${b.target}|x` });
  S.phys = { seq: S.seq, list, on: new Set(), target: r.target };
  return list;
}
const physTarget = () => (S.phys && S.phys.seq === S.seq ? S.phys.target : S.req && S.req.target);
const physOn = () => { physOpts(); return S.phys ? S.phys.list.filter((o) => S.phys.on.has(o.key)) : []; };
const limbsOf = (o) => (o.limb && o.limb.length ? o.limb : ["Center Torso"]);
// the boxes: each attack at the place of each limb it uses (a push: both arm sections); for the target in view, plus any that is on elsewhere
function physBoxesFor() {
  const t = physTarget(), out = [];
  for (const o of physOpts()) { const on = S.phys.on.has(o.key); if (o.target !== t && !on) continue; for (const l of limbsOf(o)) out.push({ o, loc: PH_LOCS[l] || "CT" }); }
  // an attack on at another target takes its limb's place: the same limb's attack at this target steps aside
  const busy = new Set(out.filter((b) => b.o.target !== t).map((b) => b.loc + b.o.kind));
  return out.filter((b) => b.o.target !== t || !busy.has(b.loc + b.o.kind));
}
function physBox(o, loc) {
  const on = S.phys.on.has(o.key), t = physTarget(), away = on && o.target !== t, anyOn = physOn();
  let st = o.blocked ? "blk" : away ? "else" : on ? "on" : anyOn.some((x) => x.kind !== o.kind || o.kind === "kick") ? "gry" : "rdy";
  return `<div class="wb ${st}" data-act="pb" data-key="${esc(o.key)}" data-loc="${loc}" title="${esc(o.name)}${o.blocked ? ": " + esc(o.why) : ` · ${o.damage} damage`}">${esc(PH_SHORT[o.kind] || shortName(o.name))}${away ? `<span class="to">&rarr; ${esc(short(unit(o.target) || {}))}</span>` : ""}<span class="tn" data-act="ptn" data-key="${esc(o.key)}">${o.blocked ? "×" : tnText(o.tn)}</span></div>`;
}
function togglePhys(key) {
  physOpts(); const P = S.phys, o = P.list.find((x) => x.key === key); if (!o) return;
  if (o.blocked) { toast(`${PH_SHORT[o.kind] || o.name}: ${o.why}`); return; }
  if (P.on.has(key)) { if (o.kind === "push") P.list.filter((x) => x.kind === "push").forEach((x) => P.on.delete(x.key)); else P.on.delete(key); return; }
  // one TYPE a turn (Core p.77): another type clears the rest; a kick is one leg
  for (const k of [...P.on]) { const x = P.list.find((y) => y.key === k); if (!x || x.kind !== o.kind || o.kind === "kick" || o.kind === "push") P.on.delete(k); }
  // one attack per limb: this limb's attack at another target goes
  for (const k of [...P.on]) { const x = P.list.find((y) => y.key === k); if (x && limbsOf(x).some((l) => limbsOf(o).includes(l))) P.on.delete(k); }
  P.on.add(key);
  // selecting one punch activates both (Daniel, 2026-11-26), unless the other arm is busy elsewhere, blocked or cannot reach
  if (o.kind === "punch") { const other = P.list.find((x) => x.kind === "punch" && x.target === o.target && !x.blocked && x.key !== key && !limbsOf(x).some((l) => limbsOf(o).includes(l)));
    if (other && ![...P.on].some((k) => { const x = P.list.find((y) => y.key === k); return x && limbsOf(x).some((l) => limbsOf(other).includes(l)); })) P.on.add(other.key); }
  const tu = unit(o.target); if (tu && tu.hex) MV.centreOn(tu.hex);
}
function physSetTarget(id) { physOpts(); if (!S.phys || !physOpts().some((o) => o.target === id)) return false; S.phys.target = id; UI.last = { kind: "unit", id }; const tu = unit(id), me = activeUnit(); if (tu && me && tu.hex && me.hex) look([me.hex, tu.hex], 3); return true; }
function physTnHtml() {
  const on = physOn(), list = on.length ? on : physOpts().filter((o) => o.target === physTarget());
  return `<h4>${esc((activeUnit() || {}).name || "")}: physical attacks</h4><table><tr><th>Attack</th><th>Target</th><th>TN</th><th>Damage</th></tr>${list.map((o) => `<tr><td>${esc(o.name)}</td><td>${esc((unit(o.target) || {}).name || "")}</td><td class="n">${o.blocked ? "—" : tnText(o.tn)}</td><td class="n">${o.blocked ? esc(o.why) : o.damage}</td></tr>`).join("")}</table><p class="note">Base to-hit ${S.req.base_tn} (Piloting, movement, the target's movement, terrain); each attack adds its own modifier (Core pp.81-83).</p>`;
}
function physCommit() {
  const on = physOn(), r = S.req;
  if (!on.length) { send({ kind: null }); return; }
  if (r.attacks) { send({ attacks: on.map((o) => ({ kind: o.kind, name: o.name, target: o.target })) }); return; }
  send({ kind: on[0].kind });
}

// ---------------------------------------------------------------- drawing for the question
function redraw() {
  if (!gDyn) return;
  // REC layer: at a past step the board is drawn from the replay's state for this one draw (tt_layer.js); with REC closed this does nothing
  const back = typeof TT !== "undefined" ? TT.enter() : null;
  try {
    syncTabletop();
    drawMap();
    chrome();
  } finally { if (back) back(); }
}
// 3D only. Hex numbers: small on the tile, only where the hex is big enough to read and on the screen (a 4x4 splice has over a thousand).
function drawHexNumbers(layer) {
  if (!O.labels || !S.board) return;
  const vb = svg.viewBox.baseVal, W = vb.width, H = vb.height;
  for (const label of Object.keys(S.board.hexes)) {
    const s = sc(label); if (s < 0.75) return;
    const [x, y] = P(label, 0, -0.62); if (x < -20 || y < -20 || x > W + 20 || y > H + 20) continue;
    const t = el("text", { x, y, "text-anchor": "middle", "font-size": 8 * s, fill: "#000", "fill-opacity": ".55", "font-family": "ui-monospace,monospace", "pointer-events": "none" }, layer); t.textContent = label;
  }
}
// 3D only. DROP-LINES: a thin line from a unit's base down to the table under a raised hex, so its place on the ground stays clear when the tiles
// in front are glass (Daniel: "light outlines to keep track of surface to ground tethering").
function drawDropLines(layer) {
  for (const u of S.units) {
    if (!u.hex || u.destroyed || !MV.raised(u.hex)) continue;
    const [x1, y1] = at(u.hex, MV.unitHeight()), [x2, y2] = at(u.hex, -MV.dropDepth(u.hex));
    el("line", { x1, y1, x2, y2, stroke: teamColour(u), "stroke-width": 1.2, "stroke-opacity": ".55", "stroke-dasharray": "3 3", "pointer-events": "none" }, layer);
  }
}
// what the 3D tabletop shows besides the board: the unit pieces (hex bases with their pictures), the woods they stand in, and the points the
// cut-away keeps in view (the units and the route being planned). Harmless in the flat view (mapview.js keeps it for when the 3D view opens).
function syncTabletop() {
  const live = S.units.filter((u) => u.hex && !u.destroyed);
  MV.setUnits(live.map((u) => ({ id: u.id, hex: u.hex, facing: u.facing, tons: u.tons, colour: teamColour(u), mech: u.mech, prone: !!u.prone, sel: S.sel === u.id })));
  MV.setOccupied(live.map((u) => u.hex));
  const f = live.map((u) => ({ label: u.hex, up: 24 })); if (S.path) for (const st of S.path) f.push({ label: st.hex, up: 12 }); if (S.dest) f.push({ label: S.dest, up: 12 });
  MV.setFocus(f);
}
// the marks over the map; in the 3D tabletop they are projected, so a camera move draws them again (a frame at most)
let camQueued = false;
function onCamera() { if (camQueued || !gDyn) return; camQueued = true; requestAnimationFrame(() => { camQueued = false; if (MV.is3d()) drawMap(); }); }
function drawMap() {
  gDyn.innerHTML = ""; gTop.innerHTML = "";
  const r = S.req;
  if (MV.is3d()) { drawHexNumbers(gDyn); drawDropLines(gDyn); }
  if (r && (r.kind === "declaration" || r.kind === "target")) drawRings(gDyn);
  if (moving()) drawReach(gDyn);
  if (r && r.kind === "deploy") drawDeploy(gDyn);
  if (r && r.kind === "target") drawTargets(gDyn);
  if (r && (r.kind === "spot" || r.kind === "tag")) drawPickTargets(gDyn);
  drawAttackLines(gDyn);
  drawUnits(gDyn);
  if (moving()) { drawDestHex(gDyn); drawPath(gDyn); drawWayMarks(gDyn); drawAttackStops(gDyn); if (!standing() || S.standOn) drawTurnArrows(gTop); }
  if (r && r.kind === "deploy") { drawDeployMarker(gDyn, false); drawDeployMarker(gTop, true); }
  if (r && r.kind === "stand_up" && S.prone && !S.standOn) drawProneArrows(gTop);
  if (UI.mine.length) drawMyAttacks(gDyn);
  if (r && r.kind === "physical") drawPhysTargets(gDyn);
  if (r && r.kind === "declaration") { drawAim(gDyn); drawShotLine(gTop, r.unit, r.target, r.distance); }
  if (r && r.kind === "target" && S.fire && S.fire.tcur != null) { drawAim(gDyn); drawShotLine(gTop, r.unit, S.fire.tcur, (r.enemies.find((e) => e.id === S.fire.tcur) || {}).distance); }
  if (typeof TT !== "undefined") TT.draw(gDyn, gTop);   // REC layer: the mover's path and the attack arrows of the step being looked at
  if (r && r.kind === "physical" && physTarget() != null) { const t = unit(physTarget()), me = unit(r.unit); if (t && me && t.hex && me.hex) drawShotLine(gTop, r.unit, t.id, dist(me.hex, t.hex)); }
}
function setPhase(t) { S.phaseText = t; $("phase").innerHTML = esc(t); }
// WHOSE TURN (Section 24 item 4, Daniel: "Who won initiative, how many units need to be activated, and where we're at in whose turn to activate
// should probably be displayed in the Title bar"): who has the Initiative this turn and, while moving, each side's units still to move
function turnStatus() {
  const il = S.log.slice().reverse().find((l) => /^\s*Initiative/.test(l)) || "";
  const loser = (/Initiative: (.+?) lost the roll/.exec(il) || [])[1];
  const teams = [...new Set(S.units.map((u) => u.team))];
  const winner = loser && teams.length === 2 ? teams.find((t) => t !== loser) : null;
  let txt = winner ? ` · ${winner === S.myTeam ? "you have" : winner + " has"} the initiative` : "";
  if (inMovement()) {
    const left = teams.map((t) => [t, S.units.filter((u) => u.team === t && u.hex && !u.destroyed && !u.shutdown && !u.moved).length]);
    txt += " · to move: " + left.map(([t, n]) => `${t === S.myTeam ? "you" : t} ${n}`).join(", ");
  }
  return txt;
}
// THE QUESTION BOX: a question that needs words and has no place on the map or the action buttons (MASC, jump boosters, spotting, TAG, the End
// Phase switches, deployment, the end of the battle) at the top of the clear area; "sheet" is the old name, kept for the handlers
function ask(html) { $("ask").innerHTML = html; }
const sheet = ask;
async function send(answer) {
  if (SAVE.candidate && typeof TT !== "undefined") TT.commitCandidate();   // holding Meddle: the new timeline is written now
  const seq = S.seq; if (S.req && S.req.unit != null && phaseKey() !== "move") UI.done.add(S.req.unit);
  S.req = null; S.decl = null; S.pv = null; S.fire = null; S.phys = null; ask(""); redraw();
  if (SAVE.setup) SAVE.events.push({ answer });
  const r = await api("play_answer", { seq, answer });
  if (r.error) { toast(r.error); if (SAVE.setup) SAVE.events.pop(); } else saveSoon();
  loop();
}
async function loop() {
  while (!S.over) {
    let p; try { p = await api("play_poll", { wait_ms: 20000 }); } catch (e) { setPhase("connection lost"); await new Promise((r) => setTimeout(r, 1500)); continue; }
    if (p.error) { setPhase("error"); ask(`<div class="err">${esc(p.error)}</div>`); return; }
    if (p.state === "waiting") continue;
    if (p.state === "failed") { setPhase("the engine stopped"); ask(`<div class="err">The engine stopped: ${esc(p.error)}</div>`); S.over = true; return; }
    if (p.state === "done") { finish(p.end); return; }
    if (p.seq === S.seq && S.req) { await new Promise((r) => setTimeout(r, 300)); continue; }
    S.seq = p.seq; take(p.request); return;
  }
}
const HANDLERS = {};
function take(r) {
  if (typeof TT !== "undefined") TT.refreshIfStale();
  if (SAVE.setup) {
    // a MARK for time travel: this question's place in the list, and where the game was (turn, phase, unit)
    const tn = (S.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1];
    const ph = { move: "Move", fire: "Fire", phys: "Physical", end: "Heat" }[phaseKey_(r.kind)];
    SAVE.marks.push({ at: SAVE.events.length, turn: tn ? +tn : 0, label: `${tn ? "Turn " + tn + " \u00b7 " : ""}${ph} \u00b7 ${r.name || (r.kind === "move_order" ? "who moves next" : r.kind)}${r.name ? " (" + r.kind + ")" : ""}` });
    SAVE.events.push({ post: { kind: r.kind, unit: r.unit === undefined ? null : r.unit } }); saveSoon();
  }
  S.req = r; S.units = r.units;
  if (r.kind !== "target" && r.kind !== "declaration") S.script = null;   // a plan never reaches past its own unit's fire questions
  for (const u of S.units) { // first sight of a unit: its full armour, structure and slot names (for the bars and the criticals tab)
    if (!S.maxLoc[u.id]) S.maxLoc[u.id] = JSON.parse(JSON.stringify(u.locs || {}));
    if (u.crit_names) S.critNames[u.id] = u.crit_names;
    if (u.weapons) S.wlist[u.id] = u.weapons;
  }
  if (r.board && !S.board) { S.board = r.board; buildMap(); S.needFocus = true; }
  if (r.log && r.log.length) feedLog(r.log);
  releaseLog(r.kind);
  const mine = unit(r.unit ?? (r.candidates || [])[0]);
  if (mine && r.kind !== "spot" && (!S.myTeam || (typeof TT !== "undefined" && TT.followTeam()))) S.myTeam = mine.team;   // after a meddle or a change of control the question may be another team's
  if (r.unit != null) S.sel = r.unit;
  S.dest = null; S.facing = null; S.mode = null; S.decl = null; S.pv = null; S.fire = null; S.path = null; S.attackSel = null; S.attackTarget = null; S.attackConfirm = false; S.reachIdx = null; S.mv = null; S.order = false; S.views = {}; S.way = []; S.wrIdx = null; S.prone = null; S.drop = false;
  S.standOn = false; S.aim = null; S.phys = null; UI.aimOpen = false; UI.cyc = null; UI.pickHex = null; UI.aord = []; UI.atkSel = null; ask("");
  // a new phase: its done marks and its committed attacks start again
  const pk = phaseKey(); if (pk !== UI.phase) { UI.phase = pk; UI.done.clear(); UI.mine = []; UI.wing = { L: 0, R: 0 }; }
  if (r.error) toast(r.error);
  const turn = (S.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1];
  const PH = { deploy: "Deployment", move_order: "Movement", movement: "Movement", stand_up: "Movement", boost: "Movement", jump_boost: "Movement", spot: "Ranged attacks", tag: "TAG", target: "Ranged attacks", declaration: "Ranged attacks", physical: "Physical attacks", end_phase: "Heat" };
  setPhase(r.kind === "deploy" ? "Deployment" : `Turn ${turn || "?"} · ${PH[r.kind] || r.kind}${turnStatus()}`);
  HANDLERS[r.kind](r);
  redraw();
  if (typeof TT !== "undefined") TT.afterTake();
  if (S.needFocus && r.kind !== "deploy") { S.needFocus = false; const mine = S.units.filter((u) => u.team === S.myTeam && u.hex).map((u) => u.hex); if (mine.length) look(mine, 3); }
}
const errLine = (r) => (r.error ? `<div class="err">${esc(r.error)}</div>` : "");
const eq = (u) => (u && u.equipment) || {};

// ---------------------------------------------------------------- the questions
// STANDING UP IS PART OF THE MOVE (bug A2, Daniel 2026-11-22; the overlay UI, Daniel 2026-11-26, Section 14 G2). A prone 'Mech's move is shown
// as it would be after standing at the first try (2 MP spent; any facing is free, p.51); tapping a lit hex adds Stand up first (and says so), and
// the extra button beside the MP display is Stand up (a toggle). With Stand up off, Commit says Stay prone: the arrows round the 'Mech turn it on
// the ground, 1 MP a hexside (p.51). Nothing is rolled until Commit is held; a failed roll is reported and the player decides again (G3).
HANDLERS.stand_up = (r) => {
  S.mv = null; S.prone = { facing: null }; S.standOn = false;
  UI.last = null; standPlan();
  // ASKED AGAIN (G3, Daniel 2026-11-26): a stand failed, or the 'Mech fell partway through its move; say what happened and what is left
  if (r.again) {
    const tail = S.log.slice(-40), roll = tail.map((l) => /Stand attempt \d+: needs (\d+).*Rolled (\d+)/.exec(l)).filter(Boolean).pop(), fell = tail.map((l) => /fell at (\d{4})/.exec(l)).filter(Boolean).pop();
    const what = roll && tail.some((l) => /Failed to stand/.test(l)) ? `did not stand (rolled ${roll[2]}, needed ${roll[1]}) and fell` : fell ? `fell at ${fell[1]}` : "fell";
    toast(`${r.name} ${what}: the fall's damage is in the report. ${r.run} MP left: stand again and plan the rest, or stay prone.`);
  }
};
function drawProneArrows(layer) {
  const r = S.req, u = unit(r.unit); if (!u || !u.hex) return;
  const by = Object.fromEntries((r.prone_turns || []).map((t) => [t.facing, t]));
  arrowRing(layer, u.hex, Object.keys(by), S.prone.facing || u.facing, (f) => modeCol(by[f].mode), (f) => { S.prone.facing = S.prone.facing === f ? null : f; redraw(); });
}
async function standPlan() {
  const r = S.req, seq = S.seq; if (!r || r.kind !== "stand_up") return;
  const v = await query({ q: "reach", unit: r.unit });
  if (seq !== S.seq || !S.req || S.req.kind !== "stand_up") return;
  if (v.error || !v.view) { toast(v.error || "No move after standing can be shown: Commit stands up or stays prone."); redraw(); return; }
  S.mv = v.view; S.reachIdx = null; S.way = []; S.wrIdx = null; S.dest = null; S.path = null;
  redraw();
}
HANDLERS.boost = (r) => {
  const u = unit(r.unit), e = eq(u), b = (e.boost || {});
  ask(`<h3>${esc(r.name)}: ${e.masc && e.supercharger ? "MASC and supercharger" : e.masc ? "MASC" : "supercharger"}</h3>${errLine(r)}<div class="msg">Using it this turn raises the running speed; each use needs a roll of <b>${b.tn}</b> or more, and a failure costs criticals and may force a fall. The roll gets harder each turn in a row. Your choice stays until you change it.</div><div class="row"><button class="${b.on ? "go" : ""}" data-act="boost" data-v="1">Use it</button><button class="${b.on ? "" : "go"}" data-act="boost" data-v="0">Not this turn</button></div>`);
};
// MECHANICAL JUMP BOOSTERS (TO:AUE p.105; engine pass 2026-11-25): jump on them this turn instead of the jets. No heat, may be used under
// water, but the 'Mech lands facing the way it took off, cannot make a Death From Above, and cannot use boosters and jets in the same turn.
HANDLERS.jump_boost = (r) => {
  const e = eq(unit(r.unit)), j = e.jump_boosters || {};
  ask(`<h3>${esc(r.name)}: mechanical jump boosters</h3>${errLine(r)}<div class="msg">Jumping on the boosters gives <b>${j.mp}</b> jump MP${j.jets ? ` (the jets give ${j.jets})` : ""}, makes no heat and works under water. The 'Mech lands facing the way it took off, cannot make a Death From Above, and cannot use boosters and jets in the same turn.</div><div class="row"><button class="${j.on ? "go" : ""}" data-act="jump-boost" data-v="1">Jump on the boosters</button><button class="${j.on ? "" : "go"}" data-act="jump-boost" data-v="0">${j.jets ? "Jets / ground move" : "Not this turn"}</button></div>`);
};
HANDLERS.spot = (r) => {
  ask(`<h3>${esc(r.name)}: spot for indirect fire?</h3>${errLine(r)}<div class="msg">A spotter that sees an enemy lets friends without a line of sight fire at it indirectly. A spotter may still fire its own weapons, at +1 to hit.</div><div class="row">${r.candidates.map((c) => `<button data-act="spot" data-id="${c.id}">${esc(c.name)} &middot; range ${c.distance} &middot; ${c.friends} friend${c.friends === 1 ? "" : "s"} could use it</button>`).join("")}<button class="go" data-act="spot" data-id="">No spotting</button></div>`);
};
HANDLERS.tag = (r) => {
  ask(`<h3>${esc(r.name)}: TAG designation</h3>${errLine(r)}<div class="msg">TAG is its own short attack before the weapon attacks. Designating the 'Mech helps homing artillery; designating the hex works for the ground under it. Pick a target and what to light up, or skip.</div><table>${r.candidates.map((c) => `<tr><td>${esc(c.name)}</td><td>range ${c.distance}</td><td>${c.tn_mech != null ? `<button class="sm" data-act="tag" data-id="${c.id}" data-aim="mech">'Mech TN ${c.tn_mech}</button>` : ""}</td><td>${c.tn_hex != null ? `<button class="sm" data-act="tag" data-id="${c.id}" data-aim="hex">Hex TN ${c.tn_hex}</button>` : ""}</td></tr>`).join("")}</table><div class="row"><button class="go" data-act="tag" data-id="">Skip TAG</button></div>`);
};
function drawPickTargets(layer) {
  for (const c of (S.req.candidates || [])) { const u = unit(c.id); if (!u || !u.hex) continue; el("polygon", { points: HP(u.hex, 0.95), fill: "#dba94a", "fill-opacity": ".2", stroke: "#dba94a", "stroke-width": 2.5 * sc(u.hex), "pointer-events": "none" }, layer); }
}

// ---- movement (also the planning done while choosing which unit moves, and placing units before turn 1)
// S.mv is the movement view being shown: the movement question itself, or, in the move_order question, the view of whichever
// candidate is selected (fetched with the "reach" query), so the player can look over every unit before moving one.
// JUMP TOGGLE (Section 24 item 1, Daniel 2026-11-24: "Jump toggle in the movement tracker in the lower left of the screen"; "The chosen option
// is remembered from one turn to the next"): for a unit with jump MP, on = only the jumps are lit, off = only walking and running.
S.jumpPref = {};
const jumpOn = () => !!(S.mv && S.mv.jump > 0 && S.jumpPref[S.mv.unit]);
function reachIndex(r) {
  const filter = r === S.mv && S.mv.jump > 0 && !standing(), j = jumpOn();
  const byHex = {}; for (const o of r.options) { if (filter && (o.mode === "Jump") !== j) continue; (byHex[o.hex] = byHex[o.hex] || []).push(o); } return byHex;
}
const moving = () => !!S.mv && !!S.req && (S.req.kind === "movement" || S.req.kind === "move_order" || S.req.kind === "stand_up");
const standing = () => !!S.req && S.req.kind === "stand_up";
function drawReach(layer) {
  S.reachIdx = S.reachIdx || reachIndex(S.mv);
  const idx = S.way.length ? S.wrIdx : S.reachIdx;
  const sets = { Walk: new Set(), Run: new Set(), Jump: new Set() };
  for (const [h, os] of Object.entries(idx)) for (const o of os) if (sets[o.mode]) sets[o.mode].add(h);
  for (const mode of ["Jump", "Run", "Walk"]) {
    const col = modeCol(mode);
    for (const h of sets[mode]) el("polygon", { points: HP(h, 0.96), fill: col, "fill-opacity": mode === "Walk" ? ".22" : ".14", "pointer-events": "none" }, layer);
    for (const h of sets[mode]) { // only the outer border of each mode's reach (MegaMek's look)
      const s = sc(h);
      neighbours(h).forEach((n, i) => {
        if (sets[mode].has(n)) return;
        const a = Math.PI / 3 * i, b2 = Math.PI / 3 * (i + 1), [x1, y1] = P(h, Math.cos(a), Math.sin(a)), [x2, y2] = P(h, Math.cos(b2), Math.sin(b2));
        el("line", { x1, y1, x2, y2, stroke: col, "stroke-width": 2.4 * s, "stroke-dasharray": modeDash(mode, s), "pointer-events": "none" }, layer);
      });
    }
  }
  for (const h of MV.order(Object.keys(idx))) { const p = el("polygon", { points: HP(h), fill: "transparent", "data-reach": h, style: "cursor:pointer" }, layer); p.addEventListener("click", () => pickDest(h)); }
}
// the unit being moved: its walking / running / jumping MP
const mvBudget = (mode) => (mode === "Jump" ? S.mv.jump : mode === "Run" ? S.mv.run : S.mv.walk);
// the question's own movement view; in move_order, the view of the unit chosen from the candidates
HANDLERS.movement = (r) => {
  S.sel = r.unit; S.mv = r; S.order = false; S.reachIdx = null;
  moveIntro();
};
HANDLERS.move_order = (r) => {
  S.order = true; S.cands = r.candidates; S.views = S.views || {};
  if (!r.candidates.includes(S.sel)) S.sel = r.candidates[0];
  selectMover(S.sel);
};
async function selectMover(id) {
  S.sel = id; S.dest = null; S.path = null; S.attackSel = null; S.attackTarget = null; S.attackConfirm = false; S.reachIdx = null; S.way = []; S.wrIdx = null;
  const seq = S.seq;
  let v = S.views[id];
  if (!v || v.seq !== seq) {
    S.mv = null; redraw();
    const r = await query({ q: "reach", unit: id });
    if (seq !== S.seq || !S.req || S.req.kind !== "move_order") return;
    v = S.views[id] = { seq, error: r.error, view: r.view };
  }
  if (S.sel !== id) return;
  S.mv = v.view || null; S.reachIdx = null; moveIntro(v.error); redraw();
}
// the plan starts empty: the lit hexes and the arrows are the choices, the action buttons say what holding Commit does (Section 14, F)
function moveIntro(unavailable) { if (unavailable) toast(unavailable); }
// WAYPOINTS: each tap inside the lit range adds a waypoint and the range re-lights from there with the points left; the last tap is the
// destination. The unit WALKS THE ROUTE AS DRAWN (Daniel, 2026-11-24, replacing the 2026-11-22 ruling): the cheapest way to each waypoint
// in turn, then the turns to the chosen facing. The cost, mode, hexes moved, TMM, heat, piloting rolls and terrain damage shown are those
// of that route, and the answer carries the waypoints so the engine walks the same one (`drawn_route.rs`), rolling each piloting skill
// roll and taking each hazard where the route puts it. A route round a hazard therefore avoids it.
const enrich = (o) => { const e = ((S.reachIdx || {})[o.hex] || []).find((x) => x.facing === o.facing && x.mode === o.mode) || ((S.reachIdx || {})[o.hex] || [])[0] || {}; return { tmm: 0, hexes: 0, heat: 0, ...e, ...o }; };
async function setWay(way) {
  const seq = S.seq, r = await query({ q: "way", unit: S.mv.unit, waypoints: way });
  if (seq !== S.seq || !S.req) return false;
  if (r.error) { toast(r.error); return false; }
  S.way = way; S.wrIdx = reachIndex({ options: r.reach.map(enrich) }); S.attackSel = null;
  S.path = r.legs.map((l, i, a) => ({ ...l, k: i && a[i - 1].hex === l.hex ? "turn" : "forward" }));
  S.dest = way[way.length - 1];
  const os = S.wrIdx[S.dest] || [], cheapest = os.reduce((a, b) => (a.mp <= b.mp ? a : b), os[0]);
  if (!cheapest) return false;
  if (!os.some((o) => o.mode === S.mode)) S.mode = cheapest.mode;
  const same = os.filter((o) => o.mode === S.mode), cur = unit(S.mv.unit);
  if (!same.some((o) => o.facing === S.facing)) S.facing = (same.find((o) => cur && o.facing === cur.facing) || same[0]).facing;
  redraw();
  return true;
}
async function pickDest(h) {
  if (!S.mv) return;
  if (standing() && !S.standOn) { S.standOn = true; toast(`Stand up added: a Piloting roll of ${S.req.tn}+ first`); }
  S.reachIdx = S.reachIdx || reachIndex(S.mv);
  const idx = S.way.length ? S.wrIdx : S.reachIdx, os = idx[h]; if (!os) return;
  const canWay = S.mv.standup_mp == null && !S.mv.entry && os.some((o) => o.mode !== "Jump");
  if (!S.way.length && !canWay) {   // a jump, a stand-up move or an entry: the destination alone
    const cheapest = os.reduce((a, b) => (a.mp <= b.mp ? a : b));
    S.dest = h; S.mode = cheapest.mode; S.attackSel = null;
    const same = os.filter((o) => o.mode === S.mode), cur = unit(S.mv.unit);
    S.facing = (same.find((o) => cur && o.facing === cur.facing) || same[0]).facing;
    redraw(); loadPath(); return;
  }
  if (S.way.length && S.way[S.way.length - 1] === h) return;
  await setWay([...S.way, h]);
}
const destOpts = () => (S.way.length ? (S.wrIdx || {})[S.dest] : (S.reachIdx || {})[S.dest]) || [];
const optNow = () => destOpts().find((o) => o.mode === S.mode && o.facing === S.facing);
async function loadPath() {
  if (S.way.length && !S.attackSel) return;      // the route through the waypoints is already drawn
  const seq = S.seq; let q;
  if (S.attackSel) q = { q: "path", unit: S.mv.unit, attack: S.attackSel };
  else if (S.dest) q = { q: "path", unit: S.mv.unit, hex: S.dest, facing: S.facing, mode: S.mode };
  else { S.path = null; return; }
  const r = await query(q);
  if (seq !== S.seq || !S.req) return;
  S.path = r.path || null; redraw();
}
function drawPath(layer) {
  if (!S.path || !S.path.length) return;
  const u = unit(S.mv.unit), black = !!S.attackSel && !S.attackConfirm, col = black ? "#000" : modeCol(S.attackSel ? S.attackSel.mode : S.mode);
  const pt = [u && u.hex ? at(u.hex) : null, ...S.path.map((s) => at(s.hex))].filter(Boolean), s0 = u && u.hex ? sc(u.hex) : 1;
  el("polyline", { points: pt.map((p) => p.join(",")).join(" "), fill: "none", stroke: black ? "#fff" : "#000", "stroke-width": 7 * s0, "stroke-opacity": ".55", "pointer-events": "none" }, layer);
  el("polyline", { points: pt.map((p) => p.join(",")).join(" "), fill: "none", stroke: col, "stroke-width": 3.5 * s0, "stroke-dasharray": modeDash(S.mode, s0), "pointer-events": "none" }, layer);
  S.path.forEach((st, i) => { if (st.k === "turn") return; const s = sc(st.hex), [x, y] = at(st.hex); const t = el("text", { x, y: y - 10 * s, "text-anchor": "middle", "font-size": 9 * s, "font-weight": 700, fill: "#fff", stroke: "#000", "stroke-width": 2.5 * s, "paint-order": "stroke", "pointer-events": "none" }, layer); t.textContent = st.mp; });
}
function drawWayMarks(layer) {
  S.way.forEach((h, i) => { const s = sc(h), [x, y] = P(h, -0.5, -0.5); el("circle", { cx: x, cy: y, r: 9 * s, fill: "#fff", stroke: "#000", "stroke-width": 1.5 * s, "pointer-events": "none" }, layer); const t = el("text", { x, y: y + 3.5 * s, "text-anchor": "middle", "font-size": 11 * s, "font-weight": 700, fill: "#000", "pointer-events": "none" }, layer); t.textContent = i + 1; });
}
function drawDestHex(layer) {
  if (!S.dest) return;
  el("polygon", { points: HP(S.dest, 0.98), fill: "none", stroke: modeCol(S.mode), "stroke-width": 3 * sc(S.dest), "pointer-events": "none" }, layer);
}
// The turn arrows: a ring of triangles hugging the hex, one for each facing the unit could end in, none on the side it already faces,
// each coloured by the movement mode that facing needs. Drawn on the TOP layer with a generous tap area so that a unit standing in
// the hex a turn points at can never take the tap.
function arrowRing(layer, hex, facings, current, colourOf, onPick) {
  const s = sc(hex);
  for (const f of facings) {
    if (f === current) continue;
    const d = DIR[f], n = [-d[1], d[0]], col = colourOf(f);
    const tip = P(hex, d[0] * 1.1, d[1] * 1.1), c1 = P(hex, d[0] * 0.78 + n[0] * 0.26, d[1] * 0.78 + n[1] * 0.26), c2 = P(hex, d[0] * 0.78 - n[0] * 0.26, d[1] * 0.78 - n[1] * 0.26), tap = P(hex, d[0] * 0.95, d[1] * 0.95);
    const g = el("g", { "data-arrow": f, style: "cursor:pointer" }, layer);
    el("circle", { cx: tap[0], cy: tap[1], r: R * 0.5 * s, fill: "transparent" }, g);
    el("polygon", { points: `${tip} ${c1} ${c2}`, fill: col, stroke: "#000", "stroke-width": 1.4 * s, "stroke-linejoin": "round" }, g);
    g.addEventListener("click", (e) => { e.stopPropagation(); onPick(f); });
  }
}
function drawTurnArrows(layer) {
  if (!S.dest) {                                          // nothing chosen: the facings it can end in without leaving its hex
    const u = unit(S.mv.unit); if (!u || !u.hex || S.attackTarget) return;
    S.reachIdx = S.reachIdx || reachIndex(S.mv);
    const here = S.reachIdx[u.hex] || [], cheap = {};
    for (const o of here) if (!cheap[o.facing] || o.mp < cheap[o.facing].mp) cheap[o.facing] = o;
    arrowRing(layer, u.hex, Object.keys(cheap), u.facing, (f) => modeCol(cheap[f].mode), async (f) => {
      await pickDest(u.hex);
      const os = destOpts(), o = os.find((x) => x.facing === f && x.mode === S.mode) || os.filter((x) => x.facing === f).sort((a, b) => a.mp - b.mp)[0];
      if (o) { S.facing = f; S.mode = o.mode; redraw(); loadPath(); }
    });
    return;
  }
  const os = destOpts(), cheap = {};
  for (const o of os) if (!cheap[o.facing] || o.mp < cheap[o.facing].mp) cheap[o.facing] = o;
  arrowRing(layer, S.dest, Object.keys(cheap), S.facing, (f) => modeCol((os.find((o) => o.facing === f && o.mode === S.mode) || cheap[f]).mode), (f) => {
    const same = os.find((o) => o.facing === f && o.mode === S.mode);
    S.facing = f; if (!same) S.mode = cheap[f].mode;
    redraw(); loadPath();
  });
}
function drawAttackStops(layer) {
  if (!S.attackSel && !S.attackTarget) return;
  for (const a of S.mv.attacks.filter((x) => x.target === S.attackTarget)) {
    const s = sc(a.hex), [x, y] = at(a.hex), sel = S.attackSel && S.attackSel.hex === a.hex && S.attackSel.facing === a.facing && S.attackSel.kind === a.kind;
    const p = el("polygon", { points: HP(a.hex, 0.92), fill: "#000", "fill-opacity": sel ? ".5" : ".3", stroke: "#fff", "stroke-width": (sel ? 3 : 1.5) * s, style: "cursor:pointer", "data-stop": a.hex }, layer);
    const t = el("text", { x, y: y + 4 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, layer); t.textContent = a.kind === "charge" ? "CHG" : "DFA";
    p.addEventListener("click", (e) => { e.stopPropagation(); chooseAttack(a); });
  }
}
// Leaving the 'Mech where it stands needs no button of its own: Commit with no destination chosen is the stay (Daniel, 2026-11-22).
// Hazard confirmation (Daniel, 2026-11-22): a move that calls for piloting rolls or crosses dangerous terrain lists each risk and asks first
function hazardList(o) {
  const out = [];
  if (o.psrs) out.push(`${o.psrs} piloting skill roll${o.psrs > 1 ? "s" : ""} on this path`);
  if (o.hazard) out.push(`about ${(+o.hazard).toFixed(1)} damage from terrain`);
  const seen = new Set();
  for (const p of (S.path || [])) { const h = p.hex; if (!h || seen.has(h)) continue; seen.add(h); const f = ((S.board.hexes[h] || {}).f) || {}; for (const k of Object.keys(f)) if (/lava|rubble|ice|mine|swamp|water|fire|magma|sand/i.test(k)) out.push(`${h}: ${k}${f[k] && f[k] !== true && f[k] !== 0 ? " " + f[k] : ""}`); }
  return out;
}
// UNDO (Section 14, F9): one step back: the last waypoint, the stand, the jump; the last weapon or attack turned on. CLEAR: the whole plan.
function undo() {
  if (!S.req) return;
  const k = phaseKey();
  if (k === "fire") { const id = UI.aord.pop(); const D = S.decl; if (id == null) { clearAll(); return; } if (D) D.sel.delete(id); if (S.fire) S.fire.assign.delete(id); afterAssign(); return; }
  if (k === "phys") { if (S.phys && S.phys.on.size) { const last = [...S.phys.on].pop(); S.phys.on.delete(last); } redraw(); return; }
  if (S.req.kind === "deploy" && S.dp) { S.dp.hex = null; HANDLERS.deploy(S.req); redraw(); return; }
  if (S.attackSel) { S.attackSel = null; S.attackTarget = null; S.attackConfirm = false; S.path = null; redraw(); return; }
  if (moving() && S.way.length > 1) { setWay(S.way.slice(0, -1)); return; }
  if (moving() && (S.way.length || S.dest)) { S.way = []; S.wrIdx = null; S.dest = null; S.path = null; redraw(); return; }
  if (S.drop) { S.drop = false; redraw(); return; }
  if (standing() && S.standOn) { S.standOn = false; redraw(); return; }
  if (standing() && S.prone && S.prone.facing) { S.prone.facing = null; redraw(); return; }
  if (S.mv && jumpOn()) { S.jumpPref[S.mv.unit] = false; clearPlan(); redraw(); }
}
// Send the move: in the move_order question the move is a plan that goes with the unit chosen; later the movement question uses it.
// DROP TO THE GROUND (Core p.51; engine pass 2026-11-24): after a ground move with 1 MP to spare, not a jump; it ends prone, same facing.
// A toggle in the move sheet (also with nothing chosen: drop where it stands); it goes with the answer as "prone": true.
function dropOk(o) { const v = S.mv; if (!v || standing() || v.standup_mp != null || v.entry) return false; const mode = o ? o.mode : "Stand Still", mp = o ? o.mp : 0; return mode !== "Jump" && mp + 1 <= v.run; }
function commitMove(answer) { if (S.mv) UI.done.add(S.mv.unit); if (S.drop && (answer.stay || answer.hex) && dropOk(answer.stay ? null : optNow())) answer = { ...answer, prone: true }; if (standing()) send({ stand: true, plan: answer }); else if (S.order) send({ unit: S.mv.unit, plan: answer }); else send(answer); }
// a tap on a unit while moving: the mover's own hex turns it in place; another unit to choose from becomes the mover; an enemy goes to the Last
// line, and when a charge or death from above can reach it the buttons for them stand beside it (Section 14, G4)
function onUnitTap(id) {
  const r = S.req;
  if (r && r.kind === "move_order" && r.candidates.includes(id)) { if (id !== S.sel) selectMover(id); else redraw(); return; }
  if (moving() && S.mv && id === S.mv.unit) {                      // its own hex (the token covers it): turn in place
    const u = unit(id); S.reachIdx = S.reachIdx || reachIndex(S.mv);
    if (u && u.hex && !S.way.length && S.reachIdx[u.hex]) { pickDest(u.hex); return; }
  }
  UI.last = { kind: "unit", id };
  redraw();
}
// a charge or a death from above, planned: the path to the stop, Commit says Charge (the stops to choose from are the black hexes)
async function chooseAttack(a) {
  if (!a) return;
  S.attackTarget = a.target; S.attackSel = a; S.attackConfirm = true; S.way = []; S.wrIdx = null; S.dest = null;
  redraw(); loadPath();
}
// ---- deployment: the units that are placed before turn 1 go on free hexes of the player's own deployment area
HANDLERS.deploy = (r) => {
  S.sel = r.unit; S.dp = S.dp && S.dp.seq === S.seq ? S.dp : { seq: S.seq, hex: null, facing: r.facing || "N" };
  const dp = S.dp, u = unit(r.unit) || {};
  ask(`<h3>Place ${esc(r.name)} ${esc(u.mech || "")}</h3>${errLine(r)}<div class="msg">${dp.hex ? `Placing at <b>${dp.hex}</b> facing <b>${dp.facing}</b>. Tap an arrow to turn it, or another hex to move it.` : "Tap one of the green hexes: your deployment area under this game's deployment rules. Units already placed are on the map."}</div>`);
};
function drawDeploy(layer) {
  const r = S.req, dp = S.dp; if (!r || r.kind !== "deploy") return;
  for (const h of MV.order(r.hexes)) {
    const on = dp && dp.hex === h, s = sc(h);
    const p = el("polygon", { points: HP(h, 0.96), fill: "#3ddc84", "fill-opacity": on ? ".6" : ".38", stroke: "#eaffef", "stroke-width": (on ? 3 : 1.6) * s, "stroke-dasharray": on ? "" : `${4 * s} ${3 * s}`, "data-deploy": h, style: "cursor:pointer" }, layer);
    p.addEventListener("click", () => { S.dp.hex = h; HANDLERS.deploy(S.req); redraw(); });
  }
}
function drawDeployMarker(layer, top) {
  const dp = S.dp, r = S.req; if (!dp || !dp.hex || !r || r.kind !== "deploy") return;
  const col = teamColour({ team: S.myTeam }) || "#4b8fd8", s = sc(dp.hex);
  if (!top) {
    el("polygon", { points: HP(dp.hex, 0.8), fill: col, "fill-opacity": ".6", stroke: "#fff", "stroke-width": 2.5 * s, "pointer-events": "none" }, layer);
    const d = DIR[dp.facing] || DIR.N, n = [-d[1], d[0]], w = 5 / R;
    el("polygon", { points: `${P(dp.hex, d[0] * 0.78, d[1] * 0.78)} ${P(dp.hex, d[0] * 0.5 + n[0] * w, d[1] * 0.5 + n[1] * w)} ${P(dp.hex, d[0] * 0.5 - n[0] * w, d[1] * 0.5 - n[1] * w)}`, fill: "#fff", "pointer-events": "none" }, layer);
    return;
  }
  arrowRing(layer, dp.hex, Object.keys(DIR), dp.facing, () => "#6fbf86", (f) => { dp.facing = f; HANDLERS.deploy(S.req); redraw(); });
}

// ---- target, weapons
// THE FIRE SCREEN (the target question). Daniel, 2026-11-22: "Select weapon. Click on a target. Push the fire button. Click on another target,
// fire on a secondary target. That's how it works in the demo." The engine asks for a target, then the weapons; the page asks the engine for a
// `preview` (every enemy's declaration as it would be asked, numbers included), lets the person assign weapons to any number of targets, and on
// Fire! plays the engine's questions itself in order: the primary target and its weapons, then each secondary target (split fire, p.64) and
// its weapons. `S.fire` holds the plan (weapon -> target); `S.decl` is the declaration view of the target being looked at, so the weapon panel,
// arcs, Strike, modes and ammunition all work as they do in the declaration.
const nearestFirst = () => S.req.enemies.slice().sort((a, b) => (a.distance ?? 99) - (b.distance ?? 99));
const primaryOf = () => { const F = S.fire; return F.order.find((id) => (F.pvt.get(id) || {}).forward) ?? F.order[0] ?? null; };
HANDLERS.target = async (r) => {
  S.sel = r.unit; S.decl = null;
  const sc = S.script;
  if (scriptLive(r)) {                                   // Fire! is playing the plan: the next target, or no more
    sc.at = S.seq;
    const e = sc.entries[sc.i];
    if (sc.i > 0 && e && r.enemies.some((x) => x.id === e.t)) { send({ target: e.t }); return; }
    S.script = null; send({ target: null }); return;
  }
  S.script = null;
  S.fire = { unit: r.unit, pvt: new Map(), arcs: {}, assign: new Map(), order: [], tcur: (nearestFirst()[0] || {}).id ?? null, secondary: !!r.secondary, primary: r.primary ?? null, lastPrimary: null };
  if (S.fire.tcur != null) UI.last = { kind: "unit", id: S.fire.tcur };
  redraw();
  await refreshPreview(true);
};
function ingest(pv) { const F = S.fire; F.pvt = new Map((pv.targets || []).map((t) => [t.id, t])); F.arcs = pv.arcs || F.arcs; }
async function refreshPreview(first) {
  const F = S.fire, seq = S.seq, p = primaryOf();
  const pv = await query({ q: "preview", unit: F.unit, ...(p != null ? { primary: p } : {}), ...(S.aim ? { aimed: { [F.tcur]: S.aim.loc } } : {}) });
  if (seq !== S.seq || S.fire !== F || !S.req || S.req.kind !== "target") return;
  if (pv.error) { toast(pv.error); return; }
  ingest(pv); F.lastPrimary = p;
  if (first) lookAtTarget();
  fireRebuild();
}
function fireRebuild() {
  const F = S.fire, e = F.pvt.get(F.tcur), keep = S.decl;
  if (!e || !e.req) {                                       // nothing can be declared at this one (no line of sight, a secondary target the book refuses)
    S.decl = null;
    const tu = unit(F.tcur) || {};
    toast(`${tu.name || ""}: no shot. ${e && e.why ? e.why : "No weapon can be declared at this target (no line of sight, or out of every weapon's range)."}`);
    redraw(); return;
  }
  const rows = e.req.weapons.map((w) => ({ ...w, ...(F.arcs[w.id] || {}) }));
  S.decl = { req: e.req, rows, sel: new Set([...F.assign].filter(([, t]) => t === F.tcur).map(([w]) => w)), aim: keep ? keep.aim : {}, charge: keep ? keep.charge : new Set(rows.filter((w) => w.charge).map((w) => w.name)),
    focus: keep && rows.some((w) => w.id === keep.focus) ? keep.focus : (rows.find((w) => w.in_range) || rows[0] || {}).id, aimFor: null, bin: keep ? keep.bin : null, strike: keep ? keep.strike : 0, groups: [] };
  redraw();
}
// the plan -> S.decl.sel of the target in view, and back: assigning a weapon here takes it off any other target
function syncAssign() {
  const F = S.fire, D = S.decl; if (!F || !D) return;
  for (const w of D.rows) {
    if (D.sel.has(w.id)) { if (F.assign.get(w.id) !== F.tcur) F.assign.set(w.id, F.tcur); } else if (F.assign.get(w.id) === F.tcur) F.assign.delete(w.id);
  }
  const used = new Set(F.assign.values());
  F.order = F.order.filter((t) => used.has(t)); for (const t of used) if (!F.order.includes(t)) F.order.push(t);
  if (primaryOf() !== F.lastPrimary) { F.lastPrimary = primaryOf(); setTimeout(() => { if (S.fire === F) refreshPreview(false); }, 0); }  // the others are secondary targets now (+1)
}
const assignedElsewhere = (w) => S.fire && S.fire.assign.has(w.id) && S.fire.assign.get(w.id) !== S.fire.tcur;
function fireTotals() {
  const F = S.fire, per = new Map();
  for (const [wid, t] of F.assign) { const row = ((F.pvt.get(t) || {}).req || { weapons: [] }).weapons.find((x) => x.id === wid) || {}; const p = per.get(t) || { n: 0, ev: 0, heat: 0 }; p.n++; p.ev += row.ev || 0; p.heat += row.heat || 0; per.set(t, p); }
  let n = 0, ev = 0, heat = 0; for (const p of per.values()) { n += p.n; ev += p.ev; heat += p.heat; }
  return { per, n, ev, heat };
}
function lookAtTarget() { const me = unit(S.req.unit), t = unit(S.fire && S.fire.tcur); if (me && me.hex && t && t.hex) look([me.hex, t.hex], 3); }
function setTcur(id) {
  const F = S.fire; if (!F || !S.req || S.req.kind !== "target" || !S.req.enemies.some((e) => e.id === id)) return false;
  const was = F.tcur; F.tcur = id; UI.last = { kind: "unit", id }; UI.pickHex = null;
  if (was !== id) { UI.aimOpen = false; if (S.aim) { S.aim = null; refreshPreview(false); } }
  fireRebuild(); lookAtTarget(); return true;
}
function cycleTcur(dir) { const o = nearestFirst(); if (!o.length) return; const i = Math.max(0, o.findIndex((e) => e.id === S.fire.tcur)); setTcur(o[(i + dir + o.length) % o.length].id); }
function fireGo() {
  const F = S.fire, D = S.decl; if (!F || !F.assign.size) return;
  const p = primaryOf(), order = [p, ...F.order.filter((t) => t !== p)];
  const entries = order.map((t) => ({ t, ids: [...F.assign].filter(([, x]) => x === t).map(([w]) => w), charge: D ? [...D.charge] : [], aim: D ? { ...D.aim } : {}, aimed: S.aim && t === F.tcur ? S.aim.loc : null }));
  // the committed attacks stay on the field (Section 14, K2): one per target (I8)
  const me = unit(F.unit); for (const e of entries) { const req = (F.pvt.get(e.t) || {}).req || { weapons: [] }; UI.mine.push({ a: me ? me.name : "", aid: F.unit, t: (unit(e.t) || {}).name || "", tid: e.t, w: e.ids.map((id) => { const w = req.weapons.find((x) => x.id === id) || {}; return { n: w.name || id, tn: w.tn }; }) }); }
  S.script = { unit: F.unit, entries, i: 0, at: S.seq };
  send({ target: entries[0].t });
}
// The plan answers ONLY the questions that follow straight on from its own answers (`at` = the last question it answered; the engine numbers
// every question it asks). The engine asks "another target?" only while the unit has weapons left to split, so a plan that used every weapon
// gets no such question: without this check the plan stayed behind and answered that unit's NEXT target question, a turn later, with "hold
// fire" on its own (Daniel's bugs B10 and B15, 2026-11-22: "skip TAG ended my firing phase"; fixed 2026-11-24).
function scriptLive(r) {
  const sc = S.script;
  if (sc && sc.unit === r.unit && !r.error && S.seq === sc.at + 1) return true;
  S.script = null; return false;
}
// when the engine asks the declaration while Fire! is playing the plan, the page answers it from the plan
function scriptDecl(r) {
  const sc = S.script; if (!sc || !scriptLive(r)) return false;
  const e = sc.entries[sc.i];
  if (!e || e.t !== r.target) { S.script = null; return false; }
  sc.i++; sc.at = S.seq; send({ weapons: e.ids, charge: e.charge, aim: e.aim, ...(e.aimed ? { aimed: e.aimed } : {}) }); return true;
}
function drawTargets(layer) {
  const F = S.fire, D = S.decl, w = D && D.rows.find((x) => x.id === D.focus), T = fireTotals();
  for (const t of S.req.enemies) {
    const u = unit(t.id); if (!u || !u.hex) continue;
    const s = sc(u.hex), cur = F && t.id === F.tcur;
    el("polygon", { points: HP(u.hex, 0.95), fill: "#e07468", "fill-opacity": cur ? ".35" : ".18", stroke: "#e07468", "stroke-width": (cur ? 3.5 : 2) * s, "pointer-events": "none" }, layer);
    const e = F && F.pvt.get(t.id), req = e && e.req; let tn = null;
    if (req) tn = w ? (req.weapons.find((q) => q.id === w.id) || {}).tn : req.base_tn;
    if (F) { // the to-hit pill on the enemy's hex: the focused weapon's number against it; tap it for the line items
      const txt = tn == null ? "-" : tn + "+", g = el("g", { style: "cursor:pointer", "data-tn-pill": t.id }, layer), [px, py] = P(u.hex, 0.3, -0.95, MV.unitHeight());
      el("rect", { x: px, y: py, width: 28 * s, height: 15 * s, rx: 3 * s, fill: "#000", stroke: cur ? "#fff" : "#e07468", "stroke-width": 1.2 * s }, g);
      const tx = el("text", { x: px + 14 * s, y: py + 11 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: tn == null ? "#999" : "#fff", "pointer-events": "none" }, g); tx.textContent = txt;
      g.addEventListener("click", (ev) => { ev.stopPropagation(); if (t.id !== F.tcur) setTcur(t.id); else openInsp("To-hit", null, null, "a to-hit number"); });
      const n = T.per.get(t.id);
      if (n) { const [cx, cy] = P(u.hex, -0.55, -0.8, MV.unitHeight()); el("circle", { cx, cy, r: 8 * s, fill: "#e07468", stroke: "#000", "stroke-width": 1 * s, "pointer-events": "none" }, layer); const nt = el("text", { x: cx, y: cy + 3.5 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: "#000", "pointer-events": "none" }, layer); nt.textContent = n.n; }
    }
  }
}
// the number to hit, line by line (the pill beside a weapon, a target or in the info bar opens it)
const RANGE_MOD = { short: 0, medium: 2, long: 4 };
// range bands and firing arc for the weapon in focus: shaded = outside its arc, dashed = in its arc only after a torso twist / arm flip
// the weapon view in use: the declaration's, or the target question's preview (weapons first, so the arcs and bands can guide the pick)
function drawRings(layer) {
  const FV = S.decl;
  if (!O.rings || !FV) return;
  const me = unit(S.req.unit), w = FV.rows.find((x) => x.id === FV.focus);
  if (!me || !me.hex || !w || !w.ranges) return;
  const rg = w.ranges, col = BAND(), L = { short: "S", medium: "M", long: "L" };
  const inNow = new Set(w.arc || []), inTwist = new Set(w.arc_twist || []);
  for (const label of MV.order(Object.keys(S.board.hexes))) {
    const d = dist(me.hex, label); if (d === 0 || d > rg.long) continue;
    const s = sc(label);
    if (!inTwist.has(label)) { el("polygon", { points: HP(label, 0.98), fill: "#000", "fill-opacity": ".45", "pointer-events": "none" }, layer); continue; } // outside the weapon's arc
    if (!inNow.has(label)) el("polygon", { points: HP(label, 0.9), fill: "none", stroke: "#fff", "stroke-width": 1.2 * s, "stroke-dasharray": `${3 * s} ${3 * s}`, "pointer-events": "none" }, layer); // in arc only after a torso twist / arm flip
    const band = d <= rg.short ? "short" : d <= rg.medium ? "medium" : "long";
    const tooClose = rg.min && d < rg.min;
    el("polygon", { points: HP(label, 0.96), fill: tooClose ? "#888" : col[band], "fill-opacity": tooClose ? ".12" : band === "short" ? ".2" : band === "medium" ? ".14" : ".09", "pointer-events": "none" }, layer);
    if (O.cvd && (d === rg.short || d === rg.medium || d === rg.long)) { const [x, y] = at(label); const t = el("text", { x, y: y + 3 * s, "text-anchor": "middle", "font-size": 9 * s, "font-weight": 700, fill: col[band], "pointer-events": "none" }, layer); t.textContent = L[band]; }
  }
}
// the line from the attacker to the target with the range on it
function drawShotLine(layer, from, to, range) {
  const a = unit(from), t = unit(to); if (!a || !t || !a.hex || !t.hex) return;
  const on = S.fire ? [...S.fire.assign.values()].includes(to) : S.decl && S.decl.sel.size > 0;
  const s = (sc(a.hex) + sc(t.hex)) / 2, uh = MV.unitHeight(), [x1, y1] = at(a.hex, uh), [x2, y2] = at(t.hex, uh);
  el("line", { x1, y1, x2, y2, stroke: "#e07468", "stroke-width": (on ? 2.6 : 1.8) * s, "stroke-opacity": on ? "1" : ".6", "stroke-dasharray": on ? "" : `${5 * s} ${4 * s}`, "pointer-events": "none" }, layer);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, txt = String(range ?? "") + "h", g = el("g", { "data-mine": -1, style: "cursor:pointer" }, layer);
  el("rect", { x: mx - (4 + txt.length * 3.5) * s, y: my - 8 * s, width: (8 + txt.length * 7) * s, height: 16 * s, rx: 8 * s, fill: "#000", stroke: "#e07468", "stroke-width": 1.2 * s }, g);
  const tx = el("text", { x: mx, y: my + 4 * s, "text-anchor": "middle", "font-size": 11 * s, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, g); tx.textContent = txt;
}
// the attacks committed in this phase stay on the field (Section 14, K2): muted, unless the attacker or the target is the one selected
function drawMyAttacks(layer) {
  const focus = new Set([(activeUnit() || {}).id, UI.last && UI.last.kind === "unit" ? UI.last.id : -1, S.fire ? S.fire.tcur : -1]);
  UI.mine.forEach((m, i) => {
    const A = unit(m.aid), T = unit(m.tid); if (!A || !T || !A.hex || !T.hex) return;
    const hi = focus.has(m.aid) || focus.has(m.tid), s = (sc(A.hex) + sc(T.hex)) / 2, uh = MV.unitHeight(), [x1, y1] = at(A.hex, uh), [x2, y2] = at(T.hex, uh), col = hi ? "#ffd400" : "#ffffff";
    const g = el("g", { "data-mine": i, style: "cursor:pointer" }, layer);
    el("line", { x1, y1, x2, y2, stroke: col, "stroke-width": 2.2 * s, "stroke-opacity": hi ? ".85" : ".25", "pointer-events": "none" }, g);
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, txt = `\u25b8 ${m.w.length}`;
    el("rect", { x: mx - 14 * s, y: my - 8 * s, width: 28 * s, height: 16 * s, rx: 8 * s, fill: "#000", "fill-opacity": hi ? ".85" : ".4", stroke: col, "stroke-opacity": hi ? "1" : ".4", "stroke-width": 1.2 * s }, g);
    const tx = el("text", { x: mx, y: my + 4 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: "#fff", "fill-opacity": hi ? "1" : ".5", "pointer-events": "none" }, g); tx.textContent = txt;
  });
}
function drawAim(layer) {
  if (!S.decl) return;
  for (const [wid, hex] of Object.entries(S.decl.aim)) { const s = sc(hex), [x, y] = at(hex); el("circle", { cx: x, cy: y, r: R * 0.6 * s, fill: "none", stroke: "#e07468", "stroke-width": 2.5 * s, "stroke-dasharray": `${4 * s} ${3 * s}`, "pointer-events": "none" }, layer); el("circle", { cx: x, cy: y, r: 3 * s, fill: "#e07468", "pointer-events": "none" }, layer); }
  if (S.decl.aimFor) for (const label of MV.order(Object.keys(S.board.hexes))) { const p = el("polygon", { points: HP(label), fill: "transparent", style: "cursor:crosshair", "data-aimhex": label }, layer); p.addEventListener("click", () => setAim(label)); }
}
HANDLERS.declaration = (r) => {
  S.sel = r.unit;
  if (scriptDecl(r)) return;
  S.decl = { req: r, rows: r.weapons, sel: new Set(), aim: {}, charge: new Set(r.weapons.filter((w) => w.charge).map((w) => w.name)), focus: (r.weapons.find((w) => w.in_range) || r.weapons[0] || {}).id, aimFor: null, bin: null, strike: 0, groups: [] };
  UI.last = { kind: "unit", id: r.target };
  const me = unit(r.unit); if (me && me.hex && r.target_hex) look([me.hex, r.target_hex], 3);
};
const isDistant = (w) => (w.modes || []).some((m) => m.selected && /distant/i.test(m.label)) || /distant/i.test(w.mode || "");
// ---- the numbers of the fire phase
const oddsOf = (tn) => { if (tn == null) return null; let n = 0; for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) if (a + b >= tn) n++; return n / 36; };
const wDamage = (w) => (w.damage || (w.ev != null && oddsOf(w.tn) ? w.ev / oddsOf(w.tn) : 0) || 0);
function heatIfFired() { const D = S.decl, r = D.req, h = S.fire ? fireTotals().heat : [...D.sel].reduce((a, id) => a + ((D.rows.find((w) => w.id === id) || {}).heat || 0), 0); return Math.max(0, r.heat + r.move_heat + h - r.dissipation); }
function declSheet() { if (S.fire) syncAssign(); redraw(); }
// the Strike button: the weapons worth their heat first (best damage per heat, up to a comfortable end-of-turn heat); pressed again, everything in range
function strikePick(level) {
  const D = S.decl, r = D.req, usable = D.rows.filter((w) => w.in_range && !w.jammed && !D.charge.has(w.name) && !assignedElsewhere(w));
  D.sel.clear();
  if (level === 1) { usable.forEach((w) => D.sel.add(w.id)); return; }
  let h = Math.max(0, r.heat + r.move_heat - r.dissipation);
  for (const w of usable.slice().sort((a, b) => (b.ev || 0) / ((b.heat || 0) + 0.5) - (a.ev || 0) / ((a.heat || 0) + 0.5))) { if ((w.heat || 0) === 0 || h + w.heat <= 8) { D.sel.add(w.id); h += w.heat || 0; } }
}
async function setWeapons(extra) {
  const D = S.decl; if (!D) return;
  const aim = {}; for (const [k, v] of Object.entries(D.aim)) aim[k] = v;
  if (S.fire) {   // before the target is chosen: the settings belong to the unit; the answer is the whole preview again
    const F = S.fire, seq = S.seq, p = primaryOf(), keepSel = new Set(D.sel);
    const r = await query({ q: "set", unit: F.unit, target: F.tcur, ...(p != null ? { primary: p } : {}), charge: [...D.charge], aim, ...(S.aim ? { aimed: { [F.tcur]: S.aim.loc } } : {}), ...extra });
    if (seq !== S.seq || S.fire !== F) return;
    if (r.error) { D.req.error = r.error; declSheet(); return; }
    ingest(r); fireRebuild();
    for (const id of keepSel) { const w = S.decl && S.decl.rows.find((x) => x.id === id); if (!w || !w.in_range) S.decl && S.decl.sel.delete(id); else S.decl.sel.add(id); }
    declSheet(); return;
  }
  const r = await query({ q: "set", unit: D.req.unit, charge: [...D.charge], aim, ...extra });
  if (r.error) { D.req.error = r.error; declSheet(); return; }
  D.rows = r.weapons; for (const id of [...D.sel]) { const w = D.rows.find((x) => x.id === id); if (!w || !w.in_range) D.sel.delete(id); }
  declSheet();
}
function setAim(hex) { const D = S.decl; if (!D || !D.aimFor) return; D.aim[D.aimFor] = hex; D.aimFor = null; setWeapons({}); }

HANDLERS.physical = (r) => {
  S.sel = r.unit; physOpts(); UI.last = { kind: "unit", id: r.target };
  const me = unit(r.unit), t = unit(r.target); if (me && t && me.hex && t.hex) look([me.hex, t.hex], 3);
};

// ---- end phase (switches that matter for the expected heat)
HANDLERS.end_phase = (r) => {
  S.sel = r.unit;
  const e = r.equipment, h = r.heat;
  const jam = (e.jammed || []).map((j) => `<label class="sw"><input type="checkbox" data-act="sw-unjam" data-name="${esc(j.name)}" ${j.unjam ? "checked" : ""}> Try to clear the jam on ${esc(j.name)} next turn (it does not fire that turn)</label>`).join("");
  sheet(`<h3>${esc(r.name)}: before the Heat Phase</h3>${errLine(r)}<div class="msg">Expected heat at the end of the turn: <b class="${h.projected >= 14 ? "err" : h.projected >= 8 ? "warnt" : ""}">${h.projected}</b> (now ${h.now}, movement ${h.movement}, weapons ${h.weapons}, heat sinks take off ${h.sinks}).</div>
    ${e.coolant.pods ? `<div class="sw"><label>Coolant pods (${e.coolant.pods})</label><button class="sm" data-act="sw-cool" data-v="now">Use a pod now</button><button class="sm" data-act="sw-cool" data-v="hold">Hold them</button><button class="sm" data-act="sw-cool" data-v="auto">Automatic</button><span class="msg">now: ${e.coolant.mode}</span></div>` : ""}
    ${e.radical.live ? `<div class="sw"><label>Radical heat sinks</label><button class="sm ${e.radical.on ? "go" : ""}" data-act="sw-rad" data-v="1">On (needs ${e.radical.tn}+)</button><button class="sm ${e.radical.on ? "" : "go"}" data-act="sw-rad" data-v="0">Off</button></div>` : ""}
    ${jam}
    ${powerRow(e)}
    <div class="row"><button class="go" data-act="end-go">Continue</button></div>`);
};
// VOLUNTARY SHUTDOWN (Core p.105; engine pass 2026-11-24): shut down in this End Phase; a 'Mech shut down by choice stays down until
// its player asks for a restart in a later End Phase (heat checks apply).
function powerRow(e) {
  const p = e.power; if (!p) return "";
  if (p.shutdown && p.by_choice) return `<div class="sw"><label>Shut down by choice</label><button class="sm ${p.request === "on" ? "go" : ""}" data-act="sw-power" data-v="${p.request === "on" ? "" : "on"}">${p.request === "on" ? "&#10003; Restart this End Phase" : "Restart this End Phase"}</button></div>`;
  if (p.shutdown) return "";
  return `<div class="sw"><label>Power plant</label><button class="sm ${p.request === "off" ? "go" : ""}" data-act="sw-power" data-v="${p.request === "off" ? "" : "off"}">${p.request === "off" ? "&#10003; Shut down this End Phase" : "Shut down this End Phase"}</button><span class="msg">it stays down until you restart it</span></div>`;
}

// ---------------------------------------------------------------- what the pages show of a unit (the old dock's tabs, now in the inspector and the
// wings): its weapons, its armour as pips, its equipment switches
const rangeText = (r) => (r ? `${r.min ?? "-"}/${r.short}/${r.medium}/${r.long}` : "?");
const dmgText = (w) => (w.damage ? w.damage : w.rack ? w.rack + " msl" : "-");
function weaponsTab(u) {
  const list = S.wlist[u.id] || [];
  if (!list.length) return '<div class="msg">No weapons listed.</div>';
  return `<table class="wt"><tr><th>Weapon</th><th>Loc</th><th>Dmg</th><th>Heat</th><th title="minimum / short / medium / long">Min/S/M/L</th></tr>${list.map((w) => `<tr><td>${esc(w.name)}${w.rear ? " (rear)" : ""}</td><td>${esc([].concat(w.loc || []).map((l) => LOCAB[l] || l).join("/"))}</td><td>${esc(dmgText(w))}</td><td>${w.heat ?? ""}</td><td>${rangeText(w.ranges)}</td></tr>`).join("")}</table>${u.team === S.myTeam ? '<div class="msg">Modes and ammunition: long press a weapon in the Weapon Attack Phase.</div>' : '<div class="msg">An enemy unit: read only.</div>'}`;
}
// the armour silhouette: each location a box of pips, armour outside (white), structure inside (grey); lost points are red from the outside in
function armorTab(u) {
  const mx = S.maxLoc[u.id] || {}, locs = u.locs || {};
  const box = (loc) => {
    const v = locs[loc]; if (!v) return "<div></div>";
    const m = mx[loc] || v, per = Math.max(1, Math.ceil(Math.max(m[0], m[1] || 0, m[2]) / 14));
    const pips = (now, max, cls) => { const n = Math.ceil(max / per), have = Math.ceil(now / per); return Array.from({ length: n }, (_, i) => `<i class="${i < n - have ? "r" : cls}"></i>`).join(""); };
    return `<div class="loc ${v[3] ? "dead" : ""}"><b>${LOCAB[loc] || loc}</b><div class="pips" title="armour ${v[0]}/${m[0]}">${pips(v[0], m[0], "")}</div><div class="pips" title="structure ${v[2]}/${m[2]}">${pips(v[2], m[2], "s")}</div>${m[1] > 0 ? `<div class="pips rear" title="rear armour ${v[1]}/${m[1]}">${pips(v[1], m[1], "")}</div>` : ""}<span>${v[3] ? "gone" : v[0] + "/" + v[2]}${v[1] ? ` (r ${v[1]})` : ""}</span></div>`;
  };
  const per = Math.max(1, Math.ceil(Math.max(...Object.values(mx).map((m) => Math.max(m[0], m[1] || 0, m[2])), 1) / 14));
  return `<div class="sil"><div></div><div></div>${box("Head")}<div></div><div></div>${box("Left Arm")}${box("Left Torso")}${box("Center Torso")}${box("Right Torso")}${box("Right Arm")}<div></div>${box("Left Leg")}<div></div>${box("Right Leg")}<div></div></div><div class="msg">Top row = front armour, middle = structure, bottom (torsos) = rear armour; red = lost; one pip is up to ${per} point${per > 1 ? "s" : ""} (hover for the numbers). Numbers: armour / structure, rear armour in brackets.</div>`;
}
function equipBody(u) {
  const e = eq(u), mine = u.team === S.myTeam; if (!mine) return '<div class="msg">The switches of an enemy unit are not yours to set.</div>';
  const headAmmo = ((S.critNames[u.id] || {}).Head || []).some((n) => /ammo/i.test(n));
  const rows = [];
  rows.push(`<div class="sw"><label>Heat sinks off</label><button class="sm" data-act="sw-sinks" data-d="-1">&minus;</button><b>${e.sinks.off}</b> of ${e.sinks.working}<button class="sm" data-act="sw-sinks" data-d="1">+</button><button class="sm" data-act="sw-sinks" data-d="auto">Automatic</button><span class="msg">${e.sinks.chosen ? "set by you" : "automatic"}</span></div>`);
  if (e.coolant.pods) rows.push(`<div class="sw"><label>Coolant pods (${e.coolant.pods})</label>${["auto", "hold", "now"].map((m) => `<button class="sm ${e.coolant.mode === m ? "on" : ""}" data-act="sw-cool" data-v="${m}">${m === "auto" ? "Automatic" : m === "hold" ? "Hold" : "Use when heat is expected"}</button>`).join("")}</div>`);
  if (e.radical.has) rows.push(`<div class="sw"><label>Radical heat sinks</label><button class="sm ${e.radical.on ? "on" : ""}" data-act="sw-rad" data-v="${e.radical.on ? 0 : 1}">${e.radical.on ? "On" : "Off"}</button><span class="msg">${e.radical.live ? "works on " + e.radical.tn + "+" : "destroyed"}</span></div>`);
  if (e.boost.has) rows.push(`<div class="sw"><label>MASC / supercharger</label><button class="sm ${e.boost.on ? "on" : ""}" data-act="sw-boost" data-v="${e.boost.on ? 0 : 1}">${e.boost.on ? "On" : "Off"}</button><span class="msg">works on ${e.boost.tn}+; asked at the start of each move</span></div>`);
  for (const a of e.ams || []) rows.push(`<div class="sw"><label>${esc(a.name)}</label><button class="sm ${a.off ? "" : "on"}" data-act="sw-ams" data-id="${a.id}">${a.off ? "Off" : "On"}</button></div>`);
  { const pr = powerRow(e); if (pr) rows.push(pr); }   // voluntary shutdown: set any time, done in the next End Phase (p.105)
  if (e.blue_shield.has) rows.push(`<div class="sw"><label>Blue Shield</label><button class="sm ${e.blue_shield.on ? "on" : ""}" data-act="sw-blue" data-v="${e.blue_shield.on ? 0 : 1}">${e.blue_shield.on ? "On" : "Off"}</button></div>`);
  for (const j of e.jammed || []) rows.push(`<div class="sw"><label>${esc(j.name)} jammed</label><button class="sm ${j.unjam ? "on" : ""}" data-act="sw-unjam1" data-name="${esc(j.name)}">${j.unjam ? "Clear it next turn" : "Leave it"}</button></div>`);
  for (const c of e.capacitors || []) rows.push(`<div class="sw"><label>${esc(c.name)} capacitor</label><button class="sm ${c.charge ? "on" : ""}" data-act="sw-cap" data-name="${esc(c.name)}">&#9889; ${c.charge ? "Charge" : "Fire normally"}</button></div>`);
  rows.push(`<div class="sw"><label>Auto eject</label><span class="msg">Ejection is not built yet. ${headAmmo ? '<b class="warnt">&#9888; This unit carries ammunition in the head and auto eject is off.</b>' : ""}</span></div>`);
  return rows.join("") + '<div class="msg">A switch stays as you set it and counts from the next Heat Phase. Switches can be set while a question is waiting.</div>';
}
async function setSwitch(sw, uid) {
  const id = uid ?? S.sel, r = await query({ q: "switches", unit: id, switches: sw });
  if (r.error) { toast(r.error); return null; }
  const u = unit(id); if (u) u.equipment = r.equipment;
  if (S.req && S.req.kind === "end_phase") S.req.equipment = r.equipment;
  if (S.req && S.req.kind === "end_phase") HANDLERS.end_phase(S.req);
  chrome();
  return r.equipment;
}

// ---------------------------------------------------------------- ONE PRESS SYSTEM for every control: tap, long press (500 ms), hold (Commit,
// 650 ms with a fill that shows the progress), flick (a quick drag on a wing tab, a wing's grip or the inspector's header)
let press = null;
const HOLD_MS = 650;
document.addEventListener("pointerdown", (e) => {
  const t = e.target.closest("[data-act]");
  if (UI.menu && !e.target.closest("#menu") && !(t && t.dataset.act === "menu")) { UI.menu = false; drawMenu(); }
  if (!t || t.closest("svg")) return;
  press = { el: t, x: e.clientX, y: e.clientY, t0: performance.now(), long: false, moved: false, id: e.pointerId };
  if (t.dataset.hold) { if (t.disabled) { press = null; return; } const f = t.querySelector(".fill"), T0 = performance.now();
    const step = () => { if (!press || press.el !== t) { if (f) f.style.width = "0"; return; } const p = Math.min(1, (performance.now() - T0) / HOLD_MS); if (f) f.style.width = p * 100 + "%";
      if (p >= 1) { press.long = true; if (f) f.style.width = "0"; press = null; act(t, "hold"); return; } requestAnimationFrame(step); };
    requestAnimationFrame(step); return; }
  press.timer = setTimeout(() => { if (press && !press.moved && press.el === t) { press.long = true; act(t, "long"); } }, LONG_MS);
});
document.addEventListener("pointermove", (e) => { if (!press || e.pointerId !== press.id) return; if (!press.moved && Math.hypot(e.clientX - press.x, e.clientY - press.y) > HOLD_SLOP) { press.moved = true; clearTimeout(press.timer); } });
document.addEventListener("pointerup", (e) => {
  if (!press || e.pointerId !== press.id) return; const p = press; press = null; clearTimeout(p.timer);
  if (p.el.dataset.hold) { if (!p.long) act(p.el, "tap"); return; }
  if (p.long) return;
  const dx = e.clientX - p.x, dy = e.clientY - p.y, dt = performance.now() - p.t0;
  if (p.moved) { const fl = p.el.dataset.flick ? p.el : p.el.parentElement && p.el.parentElement.closest("[data-flick]"); if (fl && dt < 700) act(fl, "flick", { dx, dy }); return; }
  act(p.el, "tap");
});
document.addEventListener("pointercancel", () => { if (press) { clearTimeout(press.timer); press = null; } });
// a keyboard activation (Enter, Space: a click with no pointer) is a tap, or the hold for Commit
document.addEventListener("click", (e) => { if (e.detail !== 0) return; const t = e.target.closest("[data-act]"); if (t && !t.closest("svg")) act(t, t.dataset.hold ? "hold" : "tap"); });
document.addEventListener("contextmenu", (e) => { if (e.target.closest("#app")) e.preventDefault(); });
document.addEventListener("change", (e) => { const t = e.target; if (t.dataset && t.dataset.act === "sw-unjam") sendUnjam(); });
function sendUnjam() { const names = [...document.querySelectorAll('[data-act="sw-unjam"]')].filter((c) => c.checked).map((c) => c.dataset.name); setSwitch({ unjam: names }, S.req ? S.req.unit : S.sel); }
// a touch on the uncovered map while the inspector is open ONLY closes it (no move, no target)
$("icatch").addEventListener("pointerdown", (e) => { e.preventDefault(); e.stopPropagation(); UI.insp.open = 0; chrome(); });
function act(t, kind, info = {}) {
  const d = t.dataset, a = d.act, D = S.decl, k = phaseKey(), side = d.side;
  switch (a) {
    // ---- the title line and the panels
    case "menu": if (kind === "long") openInsp("Options", null, null, "a long press on Menu"); else { UI.menu = !UI.menu; drawMenu(); layoutPanels(); } return;
    case "rec": TT.toggle(); return;   // the REC layer (tt_layer.js); the old card list (timeTravelCard) is kept for the branch test until meddling replaces it
    case "branch": $("card").style.display = "none"; branchFrom(+d.at); return;
    case "fwd-child": UI.menu = false; drawMenu(); forwardToChild(); return;
    case "back-parent": UI.menu = false; drawMenu(); backToParent(); return;
    case "step": stepStrip(d.team, +d.d); break;
    case "chip": { const id = +d.u, u = unit(id); if (!u) return; if (kind === "long") { openInsp("Unit", u.hex, id, `${u.name} in the strip`); return; } chipTap(id); return; }
    case "inspect": if (UI.insp && UI.insp.open) { UI.insp.open = 0; chrome(); return; }   // a second press closes it (prompt 2.2)
      if (UI.last) { const L = UI.last; openInsp(L.kind === "unit" ? "Unit" : "Hex", L.kind === "unit" ? (unit(L.id) || {}).hex : L.l, L.kind === "unit" ? L.id : null, "the Last line"); } return;
    case "report": UI.menu = false; toggleReport(); return;
    case "report-close": closeReport(); return;
    case "card-close": $("card").style.display = "none"; return;
    // ---- the action buttons
    case "mpw": {
      const u = activeUnit(); if (!u || !S.req) return;
      if (kind === "long") { openInsp(k === "move" ? "Move" : "Heat", null, u.id, "the MP / heat display"); return; }
      if (k === "fire") { const e = eq(u), h = fireHeatParts(); if (h.gen > h.diss && e.coolant && e.coolant.pods) setSwitch({ coolant: e.coolant.mode === "now" ? "auto" : "now" }, u.id).then(() => chrome()); else toast("Hold for the Heat tab"); return; }
      if (k !== "move") { toast("Hold for the Heat tab"); return; }
      if (S.mv && S.mv.jump > 0 && !standing()) { S.jumpPref[S.mv.unit] = !jumpOn(); clearPlan(); moveIntro(); redraw(); toast(jumpOn() ? "Jump: only the jumps are lit" : "Back on the ground: walking and running"); return; }
      toast(S.mv && S.mv.jump > 0 ? "Stand up first to jump" : "Hold for more moves"); return; }
    case "more": openInsp(k === "fire" ? "Weapons" : k === "phys" ? "Attack" : k === "end" ? "Heat" : "Move", null, (activeUnit() || {}).id, "the ⋯ button"); return;
    case "standup": if (standing()) { S.standOn = !S.standOn; if (!S.standOn) { clearPlan(); } toast(S.standOn ? `Stand up: a Piloting roll of ${S.req.tn}+ first` : "Stays prone"); redraw(); } return;
    case "commit": if (kind === "hold") commitNow(); else { const c = commitState(); toast(c.warn ? `Hold to commit. ⚠ ${warnText()}` : "Hold to commit"); } return;
    case "undo": undo(); return;
    case "clear": clearAll(); return;
    // ---- the attack boxes
    case "wb": case "tn": { const w = D && D.rows.find((x) => x.id === +d.w); if (!w) return;
      if (kind === "long") { UI.focusW = w.id; D.focus = w.id; openInsp(a === "tn" ? "To-hit" : "Weapons", null, (activeUnit() || {}).id, a === "tn" ? "a to-hit number" : "a weapon"); redraw(); return; }
      toggleWeapon(w); return; }
    case "pb": case "ptn": if (kind === "long") { openInsp(a === "ptn" ? "To-hit" : "Attack", null, (activeUnit() || {}).id, a === "ptn" ? "a to-hit number" : "an attack"); return; } togglePhys(d.key); redraw(); return;
    case "ctx": ctxAct(d); return;
    // ---- wings and the inspector
    case "edge": if (kind === "tap" || (kind === "flick" && (side === "L" ? info.dx > 20 : info.dx < -20))) { UI.wing[side] = 1; UI.insp.open = 0; } break;
    case "wclose": UI.wing[side] = kind === "tap" && UI.wing[side] === 2 ? 1 : 0; if (kind === "flick" && (side === "L" ? info.dx > 30 : info.dx < -30)) UI.wing[side] = 2; break;
    case "wmore": if (kind === "tap" || (kind === "flick" && (side === "L" ? info.dx > 20 : info.dx < -20))) UI.wing[side] = 2; else if (kind === "flick") UI.wing[side] = 0; break;
    case "wtab": (UI.wtab[k] || UI.wtab.move)[side] = d.tab; break;
    case "whead": if (kind === "flick" && Math.abs(info.dy) > 30 && Math.abs(info.dy) > Math.abs(info.dx)) { const w = UI.wtab[k] || UI.wtab.move, i = TABS.indexOf(w[side]); w[side] = TABS[(i + (info.dy > 0 ? -1 : 1) + TABS.length) % TABS.length]; } break;
    case "itab": UI.insp.tab = d.tab; break;
    case "iclose": UI.insp.open = 0; break;
    case "ihead": if (kind === "flick") { if (info.dy > 30) UI.insp.open = 2; else if (info.dy < -30) UI.insp.open = 0; } break;
    // ---- page actions
    case "opt": optAct(d); break;
    case "wl": UI.wl = d.v; setPref("wl", d.v); UI.menu = false; break;
    case "options": UI.menu = false; openInsp("Options", null, null, "the menu"); return;
    // ---- the questions' own buttons (the question box, cards)
    case "stand": send({ stand: d.v === "1" }); return;
    case "boost": send({ use: d.v === "1" }); return;
    case "jump-boost": send({ use: d.v === "1" }); return;
    case "spot": send({ target: d.id === "" ? null : +d.id, fires: true }); return;
    case "tag": send(d.id === "" ? { target: null } : { target: +d.id, aim: d.aim }); return;
    case "eject-go": $("card").style.display = "none"; if (S.req && S.req.kind === "movement") send({ eject: true }); return;
    case "end-go": send({}); return;
    case "atk-pick": { const list = S.mv.attacks.filter((x) => x.target === S.attackTarget); chooseAttack(list[+d.i]); return; }
    // weapons: modes, rates, capacitors, ammunition feeds, the distant aim, Strike
    case "mode-w": { const w = D.rows.find((x) => x.id === +d.w), i = w.modes.findIndex((m) => m.selected), next = w.modes[(i + 1) % w.modes.length]; setWeapons({ modes: { [w.id]: next.label } }); return; }
    case "rate-w": { const w = D.rows.find((x) => x.id === +d.w), i = w.rates.findIndex((m) => m.selected), next = w.rates[(i + 1) % w.rates.length]; setWeapons({ shots: { [w.id]: next.shots } }); return; }
    case "charge-w": { const w = D.rows.find((x) => x.id === +d.w); D.charge.has(w.name) ? D.charge.delete(w.name) : (D.charge.add(w.name), D.rows.filter((x) => x.name === w.name).forEach((x) => unassign(x))); setWeapons({}); return; }
    case "bin-pick": setWeapons({ bins: { [+d.w]: d.b === "" ? null : +d.b } }); return;
    case "aim-w": D.aimFor = D.aimFor ? null : +d.id; redraw(); return;
    case "strike": strikePick(D.strike % 2); D.strike++; afterAssign(); return;
    // the equipment switches
    case "sw-cool": setSwitch({ coolant: d.v }, d.u != null ? +d.u : undefined); return;
    case "sw-rad": setSwitch({ radical: d.v === "1" }, d.u != null ? +d.u : undefined); return;
    case "sw-boost": setSwitch({ boost: d.v === "1" }); return;
    case "sw-blue": setSwitch({ blue_shield: d.v === "1" }); return;
    case "sw-power": setSwitch({ power: d.v || null }); return;
    case "sw-ams": { const u = unit(S.sel), off = (eq(u).ams || []).filter((x) => (x.id === +d.id ? !x.off : x.off)).map((x) => x.id); setSwitch({ ams_off: off }); return; }
    case "sw-unjam1": { const u = unit(S.sel), names = (eq(u).jammed || []).filter((x) => (x.name === d.name ? !x.unjam : x.unjam)).map((x) => x.name); setSwitch({ unjam: names }); return; }
    case "sw-cap": { const u = unit(S.sel), names = (eq(u).capacitors || []).filter((x) => (x.name === d.name ? !x.charge : x.charge)).map((x) => x.name); setSwitch({ charge: names }); return; }
    case "sw-sinks": { const u = unit(S.sel), e = eq(u); if (d.d === "auto") setSwitch({ sinks_off: null }); else setSwitch({ sinks_off: Math.max(0, Math.min(e.sinks.working, e.sinks.off + +d.d)) }); return; }
    // the menu and the options
    case "look": O.look = d.v; setPref("look", d.v); applyLook(); break;
    case "cvd": O.cvd = !O.cvd; setPref("cvd", O.cvd ? "1" : "0"); break;
    case "atk": O.atk = !O.atk; setPref("atk", O.atk ? "1" : "0"); break;
    case "dice": O.dice = !O.dice; setPref("dice", O.dice ? "1" : "0"); if ($("report").firstChild) renderReport(); break;
    case "rings": O.rings = !O.rings; setPref("rings", O.rings ? "1" : "0"); break;
    case "labels": O.labels = !O.labels; setPref("labels", O.labels ? "1" : "0"); if (S.board) buildMap(); break;
    case "t3": { const k2 = d.k; if (k2 === "bevel") setPref("t_bevel", t3get().bevel ? "0" : "1"); else setPref("t_" + k2, String(t3next(k2))); MV.setting(t3get()); break; }
    case "view3d": { UI.menu = false; const want = MV.mode === "3d" ? "top" : "3d";
      MV.setMode(want, t3get()).then((got) => { setPref("view", got); if (want === "3d" && got !== "3d") showCard("<b>The tabletop view needs WebGL</b><div class=\"msg\">This browser or device could not start it, so the flat map stays.</div>"); redraw(); refocus(); }); return; }
    case "lab": location.href = "index.html"; return;
    case "save-file": UI.menu = false; drawMenu(); saveToFile(); return;
    case "get-results": getResults(); return;
    case "watch-replay": watchReplay(); return;
    default: return;
  }
  redraw();
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if ($("report").style.display === "block") { closeReport(); return; }
  if ($("card").style.display === "block") { $("card").style.display = "none"; return; }
  if (UI.menu) { UI.menu = false; drawMenu(); return; }
  if (UI.insp.open) { UI.insp.open = 0; chrome(); return; }
  if (UI.wing.L || UI.wing.R) { UI.wing = { L: 0, R: 0 }; chrome(); return; }
  undo();
});
// the strips' arrows (C1, E2): the enemy's step the target in the attack phases and the Last line in Movement; yours step through the units
// not yet done (the movers to choose from; in the other phases the engine asks each unit in turn, so they step the Last line)
function stepStrip(team, dir) {
  const k = phaseKey();
  if (team === "f") {
    const list = S.units.filter((u) => u.team !== S.myTeam && !u.destroyed && u.hex); if (!list.length) return;
    if (S.fire) { cycleTcur(dir); return; }
    if (k === "phys") { const ids = [...new Set(physOpts().map((o) => o.target))]; if (ids.length) { const i = Math.max(0, ids.indexOf(physTarget())); physSetTarget(ids[(i + dir + ids.length) % ids.length]); } return; }
    const cur = UI.last && UI.last.kind === "unit" ? UI.last.id : null, i = list.findIndex((u) => u.id === cur), n = list[(i + dir + list.length) % list.length];
    UI.last = { kind: "unit", id: n.id }; if (n.hex) MV.centreOn(n.hex); return;
  }
  if (S.req && S.req.kind === "move_order") { const c = S.cands, i = Math.max(0, c.indexOf(S.sel)); selectMover(c[(i + dir + c.length) % c.length]); return; }
  const list = S.units.filter((u) => u.team === S.myTeam && !u.destroyed && !doneNow(u)); if (!list.length) return;
  const cur = UI.last && UI.last.kind === "unit" ? UI.last.id : (activeUnit() || {}).id, i = list.findIndex((u) => u.id === cur), n = list[(i + dir + list.length) % list.length];
  UI.last = { kind: "unit", id: n.id }; if (n.hex) MV.centreOn(n.hex);
}
// a tap on a chip (either strip), a placard or a unit on the map (H1, L2)
function chipTap(id) {
  const u = unit(id); if (!u) return;
  if (S.fire && S.req.enemies.some((e) => e.id === id)) { UI.cyc = null; UI.pickHex = null; setTcur(id); return; }
  if (S.req && S.req.kind === "physical" && physSetTarget(id)) { redraw(); return; }
  if (S.req && S.req.kind === "move_order" && S.cands.includes(id)) { UI.last = { kind: "unit", id }; selectMover(id); return; }
  UI.last = { kind: "unit", id };
  if (u.team !== S.myTeam && u.hex) MV.centreOn(u.hex);
  redraw();
}
function ctxAct(d) {
  if (d.do === "aimed") { UI.aimOpen = true; redraw(); return; }
  if (d.do === "aimloc") { S.aim = S.aim && S.aim.loc === d.loc ? null : { loc: d.loc }; setWeapons({}); return; }
  if (d.do === "charge" || d.do === "dfa") {
    const id = +d.u, kind = d.do, list = S.mv.attacks.filter((a) => a.target === id && a.kind === kind);
    if (S.attackSel && S.attackSel.kind === kind && S.attackSel.target === id) { S.attackSel = null; S.attackTarget = null; S.path = null; redraw(); return; }
    S.attackTarget = id; S.way = []; S.wrIdx = null; S.dest = null;
    const best = list.reduce((x, y) => (y.mp < x.mp ? y : x), list[0]); chooseAttack(best);
    toast(`${kind === "charge" ? "Charge" : "Death from above"} on ${unit(id).name}: to hit ${best.tn}+, ${best.damage} damage, you take ${best.self_damage}. The black hexes are the other places to stop. Hold Commit.`);
  }
}
function optAct(d) {
  const k = d.k;
  if (k === "jump") { S.jumpPref[S.mv.unit] = !jumpOn(); clearPlan(); moveIntro(); return; }
  if (k === "mode") { S.mode = d.m; const os = destOpts().filter((x) => x.mode === S.mode); if (!os.some((x) => x.facing === S.facing)) S.facing = os[0].facing; loadPath(); return; }
  if (k === "drop") { S.drop = !S.drop; return; }
  if (k === "careful") { send({ stand: true, careful: true }); return; }
  if (k === "eject") { showCard(`<b>Eject?</b><div class="msg">The MechWarrior ejects instead of moving and lands behind the 'Mech (a piloting roll; a hard landing costs hits). The 'Mech is abandoned and out of the battle. This cannot be undone.</div><div class="row"><button class="go" data-act="eject-go">Eject</button><button data-act="card-close">Stay in the cockpit</button></div>`); return; }
  if (k === "lim") { const u = activeUnit(); UI.lim[u.id] = Math.max(0, heatLimit(u) + +d.d); return; }
  if (k === "tgtunit") { UI.insp.open = 0; chipTap(+d.u); return; }
  if (k === "tgthex") { UI.insp.open = 0; toast("Attacking a hex or a building is not in the engine yet: only units can be targeted."); return; }
  if (k === "moveto") { UI.insp.open = 0; pickDest(d.l); return; }
}
function warnText() { const k = phaseKey(); if (k === "fire") return `the plan ends the turn at heat ${fireHeatParts().end}, above the limit ${heatLimit(activeUnit())}`; if (S.attackSel) return "a charge or death from above cannot be taken back"; const o = S.dest ? optNow() : null; return [standing() && S.standOn ? `standing needs ${S.req.tn}+` : "", ...(o ? hazardList(o) : [])].filter(Boolean).join("; "); }
function commitNow() {
  const r = S.req; if (!r) return; const k = phaseKey();
  if (r.kind === "deploy") { if (S.dp && S.dp.hex) send({ hex: S.dp.hex, facing: S.dp.facing }); return; }
  if (k === "end") { send({}); return; }
  if (k === "fire") { if (S.fire) { if (S.fire.assign.size) fireGo(); else send({ target: null }); return; } if (S.decl) { if (S.decl.sel.size) send({ weapons: [...S.decl.sel], charge: [...S.decl.charge], aim: { ...S.decl.aim } }); else send({ weapons: [] }); } return; }
  if (k === "phys") { UI.done.add(r.unit); physCommit(); return; }
  if (r.kind === "move_order" && !S.mv) { send({ unit: S.sel }); return; }   // a unit with no move to show here (prone): choose it, and its own questions follow
  if (!moving() && !standing()) return;
  if (standing() && !S.standOn) { send(S.prone && S.prone.facing ? { stand: false, facing: S.prone.facing } : { stand: false }); return; }
  if (S.attackSel) { commitMove({ attack: S.attackSel }); return; }
  if (!S.dest) { commitMove({ stay: true }); return; }
  commitMove({ hex: S.dest, facing: S.facing, mode: S.mode, ...(S.way.length ? { waypoints: S.way.slice() } : {}) });
}
function clearPlan() { S.way = []; S.wrIdx = null; S.dest = null; S.path = null; S.attackSel = null; S.attackTarget = null; S.attackConfirm = false; S.reachIdx = null; }
function clearAll() {
  const k = phaseKey();
  if (k === "fire") { if (S.fire) { S.fire.assign.clear(); S.fire.order = []; S.fire.lastPrimary = null; } if (S.decl) S.decl.sel.clear(); UI.aord = []; afterAssign(); return; }
  if (k === "phys") { if (S.phys) S.phys.on.clear(); redraw(); return; }
  if (S.req && S.req.kind === "deploy" && S.dp) { S.dp.hex = null; redraw(); return; }
  clearPlan(); S.drop = false; if (standing()) { S.standOn = false; if (S.prone) S.prone.facing = null; } else if (S.mv) S.jumpPref[S.mv.unit] = false;
  moveIntro(); redraw();
}
// weapons: on / off at the target in view (I3, I5): a weapon aimed elsewhere comes to this target
function toggleWeapon(w) {
  const D = S.decl, F = S.fire; D.focus = w.id;
  const st = weaponState(w);
  if (st === "on") { unassign(w); afterAssign(); return; }
  if (!w.in_range || w.tn == null || w.jammed) { toast(`${shortName(w.name)}: ${w.jammed ? "jammed" : "cannot fire at " + D.req.target_name + (w.range ? "" : " (out of range or arc)")}`); redraw(); return; }
  if (D.charge.has(w.name)) { toast(`${shortName(w.name)} is charging its capacitor this turn`); return; }
  D.sel.add(w.id); if (F) F.assign.set(w.id, F.tcur);
  UI.aord = UI.aord.filter((x) => x !== w.id); UI.aord.push(w.id);
  afterAssign();
  const t = unit(F ? F.tcur : D.req.target); if (t && t.hex) MV.centreOn(t.hex);
}
function unassign(w) { const D = S.decl, F = S.fire; D.sel.delete(w.id); if (F) F.assign.delete(w.id); UI.aord = UI.aord.filter((x) => x !== w.id); }
function afterAssign() { if (S.fire) syncAssign(); redraw(); }

// ---------------------------------------------------------------- the end, the menu, the look
function finish(end) {
  S.over = true; S.units = end.units; S.req = null; S.decl = null;
  if (end.log) feedLog(end.log);
  releaseLog("over");
  setPhase("Battle over");
  // GET RESULTS (bug B21): opens the Lab's Results tab with this battle's statistics
  S.end = end; dropSave();
  redraw();
  if (typeof TT !== "undefined") setTimeout(() => TT.candidateOver(), 0);
  ask(`<h3>Battle over</h3><div class="msg">${end.winner === "Draw" ? "A draw" : esc(end.winner) + " wins"} after ${end.turns} turns. ${end.decisions} decisions recorded.</div><div class="row"><button class="go" data-act="get-results">Get Results</button>${end.replay_html ? '<button class="go" data-act="watch-replay">Watch replay</button>' : ""}<button data-act="rec">Go back in time</button><button data-act="report">Show the report</button><button data-act="lab">Back to the Lab</button></div>`);
}
// WATCH REPLAY (Daniel, 2026-11-27, P15 step 1): the game just played, in the Lab's replay viewer. The engine recorded it as it was
// played (play_session.rs, "replay_html"), YOUR moves included; the viewer page is shown over the game in a frame, with a way back.
function watchReplay() {
  const end = S.end; if (!end || !end.replay) return;
  // the Lab's Replay tab shows it (play.html?replay=1 inside it): the record of THIS game, your moves included, with the setup and the order list so
  // that "Play from here" can start a game from any action
  try { localStorage.setItem("bm_replay", JSON.stringify({ record: end.replay, setup: S.setup || null, orders: end.orders || null, seed: end.seed })); }
  catch (e) { showCard('<b>Watch replay</b><div class="msg">This browser will not hand the replay over (storage is full or off).</div>'); return; }
  location.href = "index.html?replay=1";
}
// the finished game as a one-battle run file for the Lab (lab.js openPlayedGame); the setup is the one the Lab handed over
function getResults() {
  const end = S.end; if (!end || !end.line) return;
  let setup = S.setup || null; if (!setup) try { setup = JSON.parse(localStorage.getItem("bm_play_setup") || "null"); } catch (e) { setup = null; }
  if (!setup) { showCard('<b>Get Results</b><div class="msg">This game was not started from this browser\'s Lab, so its setup is not here to open the results with.</div>'); return; }
  // a run's setup names bots only: the person's team is filed under the default bot (the statistics come from the battle line; a replay
  // opened from the Results tab would be the bots' battle, not this game: recording the person's game is the saved-game work, P2 / P11)
  const teams = (setup.teams || []).map((t) => (t.bot === "human" ? { ...t, bot: "gladiator" } : t));
  const file = { replay: end.replay, played_orders: end.orders, played_setup: setup, combatlab_run: 1, played: true, setup: { ...setup, teams, battles: 1, seed: +end.seed || setup.seed || 1 }, lines: [end.line], crashed: [], seconds: 0, unit_files: {} };
  // the replay record rides along so the Replay tab can show YOUR moves; a very long game may not fit in the browser's storage: then the results go without it
  try { localStorage.setItem("bm_play_result", JSON.stringify(file)); } catch (e0) { try { localStorage.setItem("bm_play_result", JSON.stringify({ ...file, replay: null, played_orders: null, played_setup: null })); } catch (e) { showCard('<b>Get Results</b><div class="msg">This browser will not let the page hand the results over (storage is off).</div>'); return; } }
  location.href = "index.html";
}
// ---------------------------------------------------------------- the report (Daniel, 2026-11-22)
// It must not give anything away early: bot reasoning is never shown; a movement line appears once that unit has moved; everything about the
// firing, physical and heat phases waits until that phase is over (the first question of a later phase). The report is a pop-up over every
// screen and button until it is closed; after the firing phase a combat report opens by itself.
// "tag" (bug B16, Daniel 2026-11-22: "since TAG is used in its own sub phase it would be reported before the ranged attack phase
// begins"): a TAG attack is resolved before any weapon is declared (Core p.200), so its lines are shown as soon as they come.
const SEC = { move: 0, ranged: 1, phys: 2, heat: 3, tag: -1 };
const GROUP = { deploy: 0, move_order: 0, movement: 0, stand_up: 0, boost: 0, jump_boost: 0, spot: 1, tag: 1, target: 1, declaration: 1, physical: 2, end_phase: 3, over: 9 };
S.queue = []; S.shown = []; S.fresh = []; S.lastSec = "move";
function secOf(l) {
  if (/\[Movement select\]|Firing order/.test(l)) return "hide";
  if (/\[Movement\]|=== TURN|Initiative|Deployment/.test(l)) return "move";
  if (/\[Physical\]/.test(l)) return "phys";
  if (/\[Heat\]|-- end of turn/.test(l)) return "heat";
  if (/\[TAG\]/.test(l)) return "tag";
  if (/\[Resolve\]/.test(l)) return "ranged";
  if (/\[Ranged\]|\[Spot|\bAMS\b/i.test(l)) return "ranged";
  return S.lastSec;                                         // an indented result line belongs to the line above it
}
function feedLog(lines) { for (const l of lines) { S.log.push(l); const s = secOf(l); if (s !== "hide") { S.lastSec = s; S.queue.push({ l, s }); } } }
function releaseLog(kind) {
  const g = GROUP[kind] ?? 0; let fired = false, any = false;
  while (S.queue.length) {
    const q = S.queue[0], o = SEC[q.s];
    if (o !== 0 && g === o) break;                        // that phase is still going on: hold it (and everything after it)
    S.queue.shift(); S.shown.push(q.l); any = true;
    if (q.s === "ranged" || q.s === "phys" || q.s === "tag") { S.fresh.push(q.l); fired = true; }
  }
  if (any) renderReport();
  if (fired) openReport(true);
}
const esc2 = (s) => esc(s).replace(/AMM/g, "attacker movement").replace(/TMM/g, "target movement").replace(/LOS/g, "line of sight");
const RAN = { Run: "ran", Walk: "walked", Jump: "jumped", "Stand Still": "stood still" };
function fmtLine(l) {
  let m;
  if ((m = /\[Movement\] (.+?): (\S+) (\S+) -> (\S+) (\S+), (Run|Walk|Jump|Stand Still) \((\d+) MP, (\d+) hex(?:es)?, (\d+) heat; budget walk (\d+) \/ run (\d+) \/ jump (\d+)\)/.exec(l)))
    return `<div class="rm"><b>${esc(m[1])}</b> ${RAN[m[6]]}${m[6] === "Stand Still" ? "" : ` to ${m[4]} (facing ${m[5]})`} &middot; ${m[7]} movement points (of ${m[6] === "Run" ? m[11] : m[6] === "Jump" ? m[12] : m[10]}), ${m[8]} hex${m[8] === "1" ? "" : "es"} moved &middot; movement heat ${m[9]}</div>`;
  if ((m = /\[Movement\] (.+)/.exec(l))) return `<div class="rm">${esc(m[1])}</div>`;
  if ((m = /\[Ranged\] (.+?) -> (.+?): range (\d+), base TN (\d+) \((.*?)\); (firing nothing|firing (\[.*?\]))/.exec(l)))
    return `<div class="rh"><b>${esc(m[1])} &rarr; ${esc(m[2])}</b> &middot; range ${m[3]} &middot; base to-hit ${m[4]} <small>(${esc2(m[5])})</small><br>${m[7] ? "firing " + esc(m[7].replace(/[\[\]']/g, "")) : "fires nothing"}</div>`;
  if ((m = /^\s{4}(.+?): needs (\d+)(.*?), rolled (\d+) -> (.+)$/.exec(l))) {
    const hit = /\bhit\b/i.test(m[5]) && !/miss/i.test(m[5]);
    return `<div class="rs ${hit ? "hit" : "miss"}"><b>${esc(m[1])}</b> needs ${m[2]}${esc(m[3])}, rolled ${m[4]}: ${hit ? "HIT" : "miss"} <small>${hit ? esc(m[5].replace(/^hit\W*/i, "")) : ""}</small></div>`;
  }
  if ((m = /\[TAG\] (.+?)'s (.+?) -> (.+?): needs (\d+) \((.*?)\), rolled (\d+) -> (.+)$/.exec(l))) {
    const hit = /DESIGNATED/.test(m[7]);
    return `<div class="rs ${hit ? "hit" : "miss"}"><b>TAG: ${esc(m[1])} &rarr; ${esc(m[3])}</b> needs ${m[4]} <small>(${esc2(m[5])})</small>, rolled ${m[6]}: ${hit ? "DESIGNATED for this turn" : "miss"}</div>`;
  }
  if ((m = /\[Heat\] (.+?): (\d+) \+ movement (\d+) \+ weapons (\d+) \+ engine (\d+) - sinks (\d+) -> (\d+)/.exec(l)))
    return `<div class="rm"><b>${esc(m[1])}</b> heat ${m[2]} &rarr; ${m[7]} (movement +${m[3]}, weapons +${m[4]}, engine +${m[5]}, sinks &minus;${m[6]})</div>`;
  if (/=== TURN/.test(l)) return `<div class="rt">${esc(l.trim().replace(/=+/g, "").trim())}</div>`;
  if (/^\s{4}/.test(l)) return `<div class="rs">${esc(l.trim())}</div>`;
  return `<div class="rd">${esc(l.trim().replace(/^\[[^\]]+\]\s*/, ""))}</div>`;
}
// THE REPORT, ATTACK BY ATTACK (bugs B17-B20, Daniel 2026-11-22). The engine rolls every attack as it is declared and applies the damage
// later (declaration and resolution are separate in the game); each resolved attack's lines start with "[Resolve] A -> T: weapon". The
// report puts those lines straight under that attack's roll, so a hit shows where it landed and what it did before the next attack (B17);
// the damage lines are boiled down to "-> Blue 3 Right Torso: armour 11 -> 6" (B18); a critical hit shows only the slot hit, highlighted,
// without the pool or the slot lists (B19); each phase gets a heading and the report opens at the start of the latest one (B20).
const PHASE_NAME = { move: "Movement", tag: "TAG", ranged: "Weapon attacks", phys: "Physical attacks", heat: "Heat and End Phase" };
const RESOLVE_END = /^\s*\[(Ranged|Heat|Physical|Movement|End|TAG|Spot|Resolve)\]|^\s*-- end of turn|=== TURN|^PSR trigger|^Attack Phase PSR|^\s*Initiative/;
function reportHtml(lines) {
  // 1. take each resolution block out, queued by (attacker, target, weapon)
  const blocks = new Map(), keep = [];
  for (let i = 0; i < lines.length; i++) {
    const m = /^\s*\[Resolve\] (.+?) -> (.+?): (.+)$/.exec(lines[i]);
    if (!m) { keep.push(lines[i]); continue; }
    const body = [];
    while (i + 1 < lines.length && !RESOLVE_END.test(lines[i + 1])) body.push(lines[++i]);
    const k = `${m[1]}|${m[2]}|${m[3]}`;
    (blocks.get(k) || blocks.set(k, []).get(k)).push({ target: m[2], body });
  }
  // 2. the lines in order, each attack's roll followed by what it did
  let out = "", who = null, sec = null;
  for (const l of keep) {
    // a heading where a line names its phase itself (an indented result line belongs to the phase above it)
    const s = /\[(Movement|Ranged|Physical|Heat|TAG|Spot)\]|^\s*Initiative|\bAMS\b|-- end of turn/.test(l) ? secOf(l) : null;
    if (s && s !== "hide" && s !== sec && PHASE_NAME[s]) { out += `<div class="rp" data-ph="${s}">${PHASE_NAME[s]}</div>`; sec = s; }
    if (/=== TURN/.test(l)) sec = null;
    const h = /\[Ranged\] (.+?) -> (.+?): range/.exec(l); if (h) who = [h[1], h[2]];
    out += fmtLine(l);
    const roll = /^\s{4}(.+?)(?: x\d+)?: needs \d+/.exec(l);
    if (roll && who) {
      // a hit takes the next block for that weapon; a miss only one that tells of the miss (a homing or artillery round striking the hex)
      const q = blocks.get(`${who[0]}|${who[1]}|${roll[1]}`), hit = /-> HIT/.test(l);
      const blk = q && q.length && (hit || /miss/i.test(q[0].body.join(" "))) ? q.shift() : null;
      if (blk) out += `<div class="rr">${((st) => blk.body.map((b) => fmtDamage(b, blk.target, st)).join(""))({})}</div>`;
    }
  }
  // resolution blocks no roll claimed (should not happen): shown at the end rather than lost
  for (const [k, q] of blocks) for (const blk of q) out += `<div class="rh">${esc(k.replace(/\|/g, " &rarr; "))}</div><div class="rr">${((st) => blk.body.map((b) => fmtDamage(b, blk.target, st)).join(""))({})}</div>`;
  return out;
}
// one line of a hit's resolution, boiled down (B18, B19): '' = not shown
function fmtDamage(l, target, st) {
  const t = l.trim(); let m;
  if ((m = /^Critical hit pool at (.+):$/.exec(t))) { if (st) st.loc = m[1]; return ""; }
  // the critical check's roll is always shown (Daniel, 2026-11-24: "The dice rolls for critical hits should be shown"); the slot roll, like the
  // other detail dice (hit location, cluster), only with "Dice details" on (Daniel: "Showing dice rolls may need to be an optional setting")
  if ((m = /^Check for possible critical\. Roll a (\d+)\.$/.exec(t))) { if (st) st.check = m[1]; return ""; }
  if ((m = /^(\d+) critical hit\(s\)\.$/.exec(t))) return `<div class="rl ck">critical check: rolled ${st && st.check || "?"} &rarr; <b>${m[1]} critical hit${m[1] === "1" ? "" : "s"}</b></div>`;
  if (/^No critical hit\.$/.test(t)) return `<div class="rl dm">critical check: rolled ${st && st.check || "?"} &rarr; none</div>`;
  if ((m = /^Slot roll: (\d+) on 1D(\d+)/.exec(t))) return `<div class="rl dm dice">slot roll ${m[1]} on 1D${m[2]}</div>`;
  if (/^(Critical hit pool at|Current crit slots in)/.test(t) || /^\d+: .+ \(slot \d+\)$/.test(t)) return "";
  if (/^\d+ damage \(\w+\) incoming to /.test(t) || /hit for \d+:$/.test(t)) return "";
  if ((m = /^(?:Group (\d+)\/(\d+): )?Hit location roll (\d+) \((\w+) table\): (.+)\.$/.exec(t)))
    return `<div class="rl">${m[1] ? `<small>${m[1]}/${m[2]}</small> ` : ""}&rarr; <b>${esc(target)}</b> ${esc(m[5])} <small class="dice">(roll ${m[3]}, ${esc(m[4])})</small></div>`;
  if ((m = /^\[[^\]]+\] (\d+) armor pts destroyed at (.+?) \((\d+) -> (\d+) remaining\)\.(?: (\d+) damage applied to structure \[[^\]]+\] \((\d+) -> (\d+)\/\d+ remaining\)\.)?/.exec(t)))
    return `<div class="rl dm">${/rear/.test(m[2]) ? "rear " : ""}armour ${m[3]} &rarr; ${m[4]}${m[5] ? `, <b>structure ${m[6]} &rarr; ${m[7]}</b>` : ""}</div>`;
  if ((m = /^\d+\/\d+ Criticals: (.+) hit\.$/.exec(t))) return `<div class="rl crit">CRITICAL HIT: ${st && st.loc ? esc(target) + " " + esc(st.loc) + " &mdash; " : ""}${esc(m[1])}</div>`;
  if ((m = /^(.+?) hit: cluster roll (\d+)(?: \((.+?)\))? on the (\d+)-column table -> (\d+) connect \((\d+) dmg\)\.$/.exec(t)))
    return `<div class="rl"><b>${m[5]}</b> of ${m[4]} hit${m[3] ? ` (${esc(m[3])})` : ""}, ${m[6]} damage <small class="dice">(cluster roll ${m[2]})</small></div>`;
  const big = /destroy|DESTROYED|explo|pilot|Head hit|engine hit|gyro|critical|falls|Through-Armor|cockpit|unconscious/i.test(t);
  return `<div class="rl${big ? " big" : ""}">${esc(t)}</div>`;
}
function renderReport() {
  const r = $("report"); if (!r.firstChild) r.innerHTML = '<div id="rbox"><div id="rhead"><b id="rtitle">Report</b><button data-act="report-close">Close</button></div><div id="rbody"></div></div>';
  const fresh = r.dataset.mode === "fire";
  $("rtitle").textContent = fresh ? "Combat report" : "Report";
  r.classList.toggle("nodice", !O.dice);
  $("rbody").innerHTML = reportHtml(fresh ? S.fresh : S.shown) || '<div class="rd">Nothing to report yet.</div>';
  // the report opens at the start of the latest phase it has (B20)
  const heads = $("rbody").querySelectorAll(".rp, .rt"), last = heads[heads.length - 1];
  $("rbody").scrollTop = fresh || !last ? 0 : last.offsetTop - $("rbody").offsetTop;
}
function openReport(fire) {
  const r = $("report"); r.dataset.mode = fire ? "fire" : "all"; renderReport(); r.style.display = "block";
  if (fire) S.fresh = [];
  if (typeof TT !== "undefined") TT.sync();
}
function closeReport() { $("report").style.display = "none"; if (typeof TT !== "undefined") TT.sync(); }
function toggleReport() { const r = $("report"); if (r.style.display === "block") closeReport(); else openReport(false); }
function applyLook() { document.documentElement.setAttribute("data-theme", O.look); document.body.setAttribute("data-theme", O.look); }
window.addEventListener("resize", () => { if (S.board) { chrome(); refocus(); } else chrome(); });
applyLook();
// THE TABLETOP VIEW (P10, build step 2: a board preview, no units yet): chosen in the Menu, remembered on this device, or forced with ?view=3d / ?view=top
$("ztilt").onclick = () => MV.cycleTilt();
// 3D is the default (Daniel, 2026-11-25: "3D is the way to go. 2D is the fallback"); a device without WebGL keeps the flat map and says so only when 3D was asked for
{ const asked = qs.get("view") || pref("view", ""), want = asked || "3d"; if (want === "3d") MV.setMode("3d", t3get()).then((got) => { if (got !== "3d" && asked) { setPref("view", "top"); showCard("<b>The tabletop view needs WebGL</b><div class=\"msg\">This browser or device could not start it, so the flat map stays.</div>"); } chrome(); refocus(); }); }
// The browser build has no server to start the game: the Lab page left the setup for this page (localStorage), which
// starts the battle in its own worker. The desktop Lab starts it itself and passes ?game=N.
async function boot() {
  // REPLAY MODE (play.html?replay=1: the Lab's Replay tab): no game is started; tt_layer.js shows the record left in localStorage "bm_replay"
  if (new URLSearchParams(location.search).get("replay")) { addEventListener("load", () => TT.replayBoot()); return; }
  let resume = new URLSearchParams(location.search).get("resume");
  // COMING BACK (a phone that was switched off, a tab the browser dropped): this page is opened again with nothing to start. If a game was
  // left unfinished it is resumed here, straight to the question, not through the Lab's front page.
  if (!GAME && !resume && window.LAB_WASM) { try { if (!localStorage.getItem("bm_play_setup") && localStorage.getItem(SAVE_KEY)) resume = "1"; } catch (e) { /* storage off */ } }
  if (!GAME && (window.LAB_WASM || resume)) {
    let setup = null, seed, orders = null, savedFile = null, sim = 1;
    if (resume) {
      // RESUME BATTLE: the saved game (this browser's, or a file the Lab opened), played back to where it stopped
      let f = null; try { f = JSON.parse(localStorage.getItem(resume === "try" ? "bm_try" : SAVE_KEY) || "null"); } catch (e) { f = null; }
      if (!f || !f.combatlab_game || !f.orders) { setPhase("no saved game"); ask('<h3>No saved game</h3><div class="msg">This browser holds no game to resume.</div><div class="row"><button data-act="lab">Back to the Lab</button></div>'); return; }
      setup = f.setup; seed = f.seed; orders = f.orders; S.setup = setup; savedFile = f; sim = f.sim || 1;   // the seed stays text: a battle's seed passes JavaScript's exact-integer limit
      setPhase("Resuming the battle...");
    } else {
      try { setup = JSON.parse(localStorage.getItem("bm_play_setup") || "null"); localStorage.removeItem("bm_play_setup"); } catch (e) { /* storage off */ }
      if (setup) { S.setup = setup; setPhase("Starting the battle..."); }   // kept for Get Results (the stored copy is used up here so a reload does not start a second battle)
    }
    if (setup) {
      const r = await api("play_start", { setup, seed, resume: orders, sim });
      if (r.error) { setPhase("could not start"); ask(`<div class="err">${esc(r.error)}</div>`); return; }
      GAME = r.game; COLOURS = r.colours || {};
      // from here the page writes the save: a resumed game carries on the list it was resumed from
      SAVE.setup = setup; SAVE.seed = seed != null ? seed : r.seed; SAVE.human = (setup.teams || []).filter((t) => t.bot === "human").map((t) => t.name);
      SAVE.events = orders ? orders.events.slice() : [];
      if (resume === "try") SAVE.candidate = true;   // a new timeline on trial: nothing is written to the save until the first answer is held (tt_layer.js)
      if (orders) { SAVE.marks = (savedFile.marks || []).slice(); SAVE.parent = savedFile.parent || null; SAVE.child = savedFile.child || null; }
      if (orders) { while (SAVE.events.length && SAVE.events[SAVE.events.length - 1].query) SAVE.events.pop(); if (SAVE.events.length && SAVE.events[SAVE.events.length - 1].post) SAVE.events.pop(); SAVE.marks = SAVE.marks.filter((m) => m.at < SAVE.events.length); }   // as the engine does: the waiting question comes again
    }
  }
  if (!GAME) { setPhase("No game"); ask('<h3>No game</h3><div class="msg">Start one from the Lab (set a team to Human, then Play).</div><div class="row"><button data-act="lab">Back to the Lab</button></div>'); } else { loop(); }
}
chrome();
boot();
window.__bm = S; window.__ui = UI;
