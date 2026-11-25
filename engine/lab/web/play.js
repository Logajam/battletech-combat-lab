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
  decl: null, path: null, attackSel: null, pending: false, myTeam: null };
const svg = $("map");
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };

async function api(name, body) {
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
// drag to pan, wheel / pinch to zoom, press and hold for a card. PRESS AND HOLD (bug B13, Daniel 2026-11-22: "Long click to view detailed
// information on the enemy is not working"): on a unit it opens the Inspector, the detail sheet of THAT unit, friend or enemy (Daniel's
// ruling 2026-11-24: the data sheet's job moves to the Inspector on a long press); on a hex, the hex card. It used to open only the hex
// card, and any movement over 2 px cancelled it, which a fingertip always makes: a hold must stay within HOLD_SLOP px of where it began.
const HOLD_SLOP = 10;
(() => {
  const ptrs = new Map(); let moved = false, lastDist = 0, timer = null, start = null;
  const cancel = () => { if (timer) { clearTimeout(timer); timer = null; } };
  svg.addEventListener("pointerdown", (e) => {
    ptrs.set(e.pointerId, [e.clientX, e.clientY]); moved = false; lastDist = 0; cancel(); start = [e.clientX, e.clientY];
    if (ptrs.size === 1) {
      const al = e.target.closest("[data-atk]");
      if (al) { timer = setTimeout(() => { timer = null; moved = true; attackCard(+al.dataset.atk); }, 650); return; }
      const t = e.target.closest("[data-unit],[data-hex],[data-reach]");
      const uid = t && t.dataset.unit != null ? +t.dataset.unit : null;
      const hex = (t && (t.dataset.hex || t.dataset.reach)) || (MV.mode === "3d" && uid == null ? MV.hexAt(e.clientX, e.clientY) : null);   // the 3D view has no hex elements: ask it which hex is there
      if (uid != null && unit(uid)) timer = setTimeout(() => { timer = null; moved = true; inspect(uid); }, 650);
      else if (hex) timer = setTimeout(() => { timer = null; moved = true; showHexCard(hex); }, 650);
    }
  });
  svg.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId)) return;
    const prev = ptrs.get(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    const r = svg.getBoundingClientRect();
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
  const up = (e) => { ptrs.delete(e.pointerId); lastDist = 0; MV.pinchEnd(); cancel(); };
  svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", up);
  svg.addEventListener("click", (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  svg.addEventListener("contextmenu", (e) => { if (MV.mode === "3d") e.preventDefault(); });   // right-drag orbits the 3D view: no browser menu there
  svg.addEventListener("wheel", (e) => { e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
})();
$("zin").onclick = () => zoom(1 / 1.3); $("zout").onclick = () => zoom(1.3); $("zfit").onclick = fit;

// ---------------------------------------------------------------- cards (press and hold)
function showCard(html) { const c = $("card"); c.innerHTML = html + '<div class="row"><button class="sm" data-act="card-close">Close</button></div>'; c.style.display = "block"; }
function showHexCard(label) {
  const h = S.board && S.board.hexes[label]; if (!h) return;
  const f = h.f || {}, feats = Object.entries(f).map(([k, v]) => `${k}${v && v !== true && v !== 0 ? " " + v : ""}`).join(", ") || "clear";
  const here = S.units.filter((u) => u.hex === label && !u.destroyed).map((u) => esc(u.name + " " + (u.mech || "")));
  const ref = unit(S.sel); const d = ref && ref.hex ? dist(ref.hex, label) : null;
  showCard(`<b>Hex ${label}</b> &middot; level ${h.l || 0}${h.b ? " &middot; building" : ""}<div class="msg">Terrain: ${esc(feats)}</div>${here.length ? `<div>${here.join("<br>")}</div>` : ""}${d != null ? `<div class="msg">${d} hex${d === 1 ? "" : "es"} from ${esc(ref.name)}</div>` : ""}`);
}
function showWeaponCard(w) {
  const r = w.ranges ? `min ${w.ranges.min ?? "-"} / short ${w.ranges.short} / medium ${w.ranges.medium} / long ${w.ranges.long}` : "range unknown";
  const bins = (w.bins || []).map((b) => `${esc(b.name)} (${esc(LOCAB[b.loc] || b.loc || "")}) ${b.shots ?? "?"} shots`).join("<br>");
  showCard(`<b>${esc(w.name)}</b> ${w.loc ? "&middot; " + esc([].concat(w.loc).join("/")) : ""}<div class="msg">${r}</div><div class="msg">Heat ${w.heat ?? "?"}${w.mode ? " &middot; mode " + esc(w.mode) : ""}${w.in_range ? "" : " &middot; out of range"}</div>${bins ? `<div class="msg">${bins}</div>` : ""}`);
}

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
    const col = teamColour(A), g = el("g", { "data-atk": i, style: "cursor:pointer" }, layer);
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
    g.addEventListener("click", (e) => { e.stopPropagation(); attackCard(i); });
  });
}
function attackCard(i) {
  const a = (S.atkList || [])[i]; if (!a) return;
  showCard(`<b>${esc(a.a)} &rarr; ${esc(a.t)}</b> <small>turn ${a.turn}, ${a.hits} of ${a.shots} hit</small><div class="cardrep">${reportHtml(a.lines)}</div>`); document.body.classList.toggle("nodice", !O.dice);
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
    if (far) el("line", { x1: x, y1: y, x2: px + W / 2, y2: py + (spot[1] < 0 ? H : 0), stroke: col, "stroke-width": 1.4 * k, "pointer-events": "none" }, g);
    const cardH = small ? 17 * k : H;
    el("rect", { x: px, y: py, width: W, height: cardH, rx: 3 * k, fill: "#0c0f13", "fill-opacity": ".88", stroke: col, "stroke-width": 1.6 * k }, g);
    const t = el("text", { x: px + 5 * k, y: py + 13 * k, "font-size": 11 * k, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, g); t.textContent = short(u) + (u.name ? " " + u.name.replace(/^\D*/, "") : "");
    // LEFT / RIGHT BARS (Section 24 item 24; the mockup's lrBar): armour and structure split at the centre, the unit's left side on the left
    // half and its right on the right, each wearing in from its outer edge, so the damaged side shows; heat stays one bar
    const sa = { l: sideFrac(u, "a", "Left"), r: sideFrac(u, "a", "Right") }, ss = { l: sideFrac(u, "s", "Left"), r: sideFrac(u, "s", "Right") };
    const aCol = (v) => (v > 0.5 ? "#6fbf86" : v > 0.25 ? "#dba94a" : "#e07468"), sCol = (v) => (v > 0.5 ? "#8fb2d4" : "#e07468");
    if (!small) [["A", sa, aCol], ["S", ss, sCol], ["H", fr.h, () => "#ff7a3c"]].forEach(([lab, v, cf], i) => {
      const by = py + (17 + i * 6.8) * k, bx = px + 14 * k, bw = W - 19 * k, bh = 5.4 * k;
      const l = el("text", { x: px + 5 * k, y: by + 5.4 * k, "font-size": 7.5 * k, fill: "#aab", "pointer-events": "none" }, g); l.textContent = lab;
      el("rect", { x: bx, y: by, width: bw, height: bh, fill: "#2b333d" }, g);
      if (typeof v === "number") { el("rect", { x: bx, y: by, width: bw * v, height: bh, fill: cf(v) }, g); return; }
      const hw = bw / 2;
      el("rect", { x: bx + hw * (1 - v.l), y: by, width: hw * v.l, height: bh, fill: cf(v.l) }, g);
      el("rect", { x: bx + hw, y: by, width: hw * v.r, height: bh, fill: cf(v.r) }, g);
      el("line", { x1: bx + hw, y1: by, x2: bx + hw, y2: by + bh, stroke: "#000", "stroke-width": 0.9 * k }, g);
    });
    if (u.prone) { const p = el("text", { x: x + 16 * s, y: y - 18 * s, "font-size": 8 * s, fill: "#ffd400", "font-weight": 700, stroke: "#000", "stroke-width": 2 * s, "paint-order": "stroke" }, g); p.textContent = "PRONE"; }
    if (u.shutdown) { const p = el("text", { x: x + 16 * s, y: y - 8 * s, "font-size": 8 * s, fill: "#e07468", "font-weight": 700, stroke: "#000", "stroke-width": 2 * s, "paint-order": "stroke" }, g); p.textContent = "OFF"; }
  }
}
// armour, structure and heat as fractions (1 = untouched; heat 1 = at the unit's limit)
function fracs(u) {
  const mx = S.maxLoc[u.id] || {}; let a = 0, am = 0, st = 0, sm = 0;
  for (const [loc, v] of Object.entries(u.locs || {})) { const m = mx[loc] || v; a += v[0] + (v[1] || 0); am += m[0] + (m[1] || 0); st += v[2]; sm += m[2]; }
  return { a: am ? Math.max(0, a / am) : 1, s: sm ? Math.max(0, st / sm) : 1, h: Math.min(1, (u.heat || 0) / Math.max(1, u.max_heat || 30)) };
}
// MOVED THIS TURN (Section 24 item 3): during the Movement Phase a unit that has moved carries a check mark (map, placard, strip)
const inMovement = () => !!S.req && ["move_order", "movement", "stand_up", "boost"].includes(S.req.kind);
const movedMark = (u) => inMovement() && !!u.moved && !u.destroyed;
function renderStrip() {
  const mine = S.units.filter((u) => u.team === S.myTeam), foes = S.units.filter((u) => u.team !== S.myTeam);
  $("strip").innerHTML = mine.map((u) => `<div class="chip${u.destroyed ? " dead" : ""}${S.sel === u.id ? " sel" : ""}${movedMark(u) ? " moved" : ""}" data-u="${u.id}"><i style="background:${teamColour(u)}"></i>${movedMark(u) ? "&#10003; " : ""}${esc(u.name)} <span class="msg">${esc(u.mech || "")}</span><span class="bar" title="armour and structure left"><b style="width:${Math.round(fracOf(u) * 100)}%"></b></span>${u.heat ? `<span class="warnt">${u.heat}H</span>` : ""}${u.shutdown ? '<span class="err">OFF</span>' : ""}${u.prone ? "<span>PRONE</span>" : ""}</div>`).join("");
  $("estrip").innerHTML = foes.map((u) => `<div class="echip${u.destroyed ? " dead" : ""}${S.sel === u.id ? " sel" : ""}" data-u="${u.id}" title="${esc(u.name + " " + (u.mech || ""))}">${esc(short(u))}<b>${Math.round(fracOf(u) * 100)}%</b></div>`).join("");
}
function infoBar() {
  const D = S.decl;
  if (D && S.req && (S.req.kind === "declaration" || S.req.kind === "target")) {
    // the fire phase: target, range, heat; then the focused weapon in the order Min/S/M/L, damage, heat, mode, ammunition, number to hit and odds
    const r = D.req, w = D.rows.find((x) => x.id === D.focus), h = heatIfFired();
    let line = `<b>&rarr; ${esc(r.target_name)}</b> &middot; range ${r.distance} &middot; heat ${r.heat}${D.sel.size ? ` (${h} if these fire)` : ""}`;
    if (w) {
      const bin = (w.bins || []).find((b) => b.selected), od = oddsOf(w.tn);
      line += `<br><b>${esc(w.name)}</b> ${esc([].concat(w.loc || []).map((l) => LOCAB[l] || l).join("/"))}${w.rear ? " (rear)" : ""} &middot; dmg ${esc(dmgText(w))} &middot; heat ${w.heat ?? 0} &middot; ${rangeText(w.ranges)}${w.mode ? " &middot; " + esc(w.mode) : ""}${bin ? ` &middot; ${esc(bin.name)} ${bin.shots ?? "?"}` : ""}${w.in_range && w.tn != null ? ` &middot; <b>TN ${w.tn}</b>${od != null ? " (" + Math.round(od * 100) + "%)" : ""}` : w.jammed ? " &middot; JAMMED" : " &middot; out of range"}`;
    }
    $("info").innerHTML = line;
    return;
  }
  const u = unit(S.sel);
  if (!u) { $("info").textContent = "Tap a unit for its details."; return; }
  const f = fracs(u);
  $("info").innerHTML = `<b>${esc(u.name)}</b> ${esc(u.mech || "")} ${u.tons || ""}t &middot; walk ${u.walk} run ${u.run}${u.jump ? " jump " + u.jump : ""} &middot; heat ${u.heat} &middot; armour ${Math.round(f.a * 100)}% structure ${Math.round(f.s * 100)}%${u.prone ? " &middot; PRONE" : ""}${u.shutdown ? " &middot; SHUT DOWN" : ""}`;
}

// ---------------------------------------------------------------- drawing for the question
function redraw() {
  if (!gDyn) return;
  syncTabletop();
  drawMap();
  renderStrip(); infoBar(); dockRender();
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
  if (r && (r.kind === "declaration" || r.kind === "target")) drawRings(gDyn);
  if (moving()) drawReach(gDyn);
  if (r && r.kind === "deploy") drawDeploy(gDyn);
  if (r && r.kind === "target") drawTargets(gDyn);
  if (r && (r.kind === "spot" || r.kind === "tag")) drawPickTargets(gDyn);
  drawAttackLines(gDyn);
  drawUnits(gDyn);
  if (moving()) { drawDestHex(gDyn); drawPath(gDyn); drawWayMarks(gDyn); drawAttackStops(gDyn); drawTurnArrows(gTop); }
  if (r && r.kind === "deploy") { drawDeployMarker(gDyn, false); drawDeployMarker(gTop, true); }
  if (r && r.kind === "stand_up" && S.prone) drawProneArrows(gTop);
  if (r && r.kind === "declaration") { drawAim(gDyn); drawShotLine(gTop, r.unit, r.target, r.distance); }
  if (r && r.kind === "target" && S.fire && S.fire.tcur != null) { drawAim(gDyn); drawShotLine(gTop, r.unit, S.fire.tcur, (r.enemies.find((e) => e.id === S.fire.tcur) || {}).distance); }
}
function setPhase(t) { $("phase").textContent = t; $("phase").title = t; }
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
function sheet(html) { $("sheet").innerHTML = html; }
async function send(answer) {
  const seq = S.seq; S.req = null; S.decl = null; S.pv = null; S.fire = null; $("wpanel").style.display = "none"; sheet('<div class="msg">Working...</div>'); redraw();
  const r = await api("play_answer", { seq, answer });
  if (r.error) sheet(`<div class="err">${esc(r.error)}</div>`);
  loop();
}
async function loop() {
  while (!S.over) {
    let p; try { p = await api("play_poll", { wait_ms: 20000 }); } catch (e) { setPhase("connection lost"); await new Promise((r) => setTimeout(r, 1500)); continue; }
    if (p.error) { setPhase("error"); sheet(`<div class="err">${esc(p.error)}</div>`); return; }
    if (p.state === "waiting") continue;
    if (p.state === "failed") { setPhase("the engine stopped"); sheet(`<div class="err">The engine stopped: ${esc(p.error)}</div>`); S.over = true; return; }
    if (p.state === "done") { finish(p.end); return; }
    if (p.seq === S.seq && S.req) { await new Promise((r) => setTimeout(r, 300)); continue; }
    S.seq = p.seq; take(p.request); return;
  }
}
const HANDLERS = {};
function take(r) {
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
  if (mine && !S.myTeam && r.kind !== "spot") S.myTeam = mine.team;
  if (r.unit != null) S.sel = r.unit;
  S.dest = null; S.facing = null; S.mode = null; S.decl = null; S.pv = null; S.fire = null; S.path = null; S.attackSel = null; S.attackTarget = null; S.attackConfirm = false; S.reachIdx = null; S.mv = null; S.order = false; S.views = {}; S.way = []; S.wrIdx = null; S.prone = null; S.drop = false; clearCluster(); $("wpanel").style.display = "none"; DOCK.tab = "plan"; DOCK.unit = null; if (DOCK.size === 0) dockSize(1);
  const turn = (S.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1];
  const PH = { deploy: "Deployment", move_order: "Movement", movement: "Movement", stand_up: "Movement", boost: "Movement", spot: "Ranged attacks", tag: "TAG", target: "Ranged attacks", declaration: "Ranged attacks", physical: "Physical attacks", end_phase: "Heat" };
  setPhase(r.kind === "deploy" ? "Deployment" : `Turn ${turn || "?"} · ${PH[r.kind] || r.kind}${turnStatus()}`);
  HANDLERS[r.kind](r);
  redraw();
  if (S.needFocus && r.kind !== "deploy") { S.needFocus = false; const mine = S.units.filter((u) => u.team === S.myTeam && u.hex).map((u) => u.hex); if (mine.length) focusOn(mine, 3); }
}
const errLine = (r) => (r.error ? `<div class="err">${esc(r.error)}</div>` : "");
const eq = (u) => (u && u.equipment) || {};

// ---------------------------------------------------------------- the questions
// STANDING UP IS PART OF THE MOVE (bug A2, Daniel 2026-11-22: "I should be able to undo a plan of stand"; "I can not turn after a stand").
// "Stand up" sends nothing: it opens the move as it would be after standing at the first try (2 MP spent; any facing is free, p.51), with
// the turn arrows round the 'Mech itself. Undo goes back to this choice. Holding Move! sends the stand and the planned move together, and
// only then is the piloting roll made. A failed roll leaves the 'Mech prone and the plan is dropped.
HANDLERS.stand_up = (r) => {
  S.mv = null; clearCluster();
  sheet(`<h3>${esc(r.name)} is prone</h3>${errLine(r)}<div class="msg">Standing up costs 2 movement points and needs a piloting roll of <b>${r.tn}</b> or more (2D6); a failed roll is a fall${r.pilot_hits ? `; pilot hits ${r.pilot_hits} are already counted` : ""}. It may then face any way at no cost and move on with the points left (${r.run} running MP to start). Stay prone to keep firing from the ground.</div><div class="msg">Stand up lets you plan the move first; nothing is rolled until you hold <b>Move!</b>, and &times; brings you back here.</div><div class="row"><button class="go" data-act="stand-plan">Stand up</button>${(r.prone_turns || []).length ? '<button data-act="prone-plan">Stay prone</button>' : '<button data-act="stand" data-v="0">Stay prone</button>'}</div>`);
};
// STAYING PRONE, IT MAY TURN (Core p.51: 1 MP a hexside; engine pass 2026-11-24): the arrows ring the 'Mech, each with its cost; holding
// the button stays prone facing the way chosen (or as it lies). x goes back to the stand / stay choice.
function pronePlan() {
  const r = S.req; if (!r || r.kind !== "stand_up") return;
  S.prone = { facing: null }; proneSheet(); redraw();
}
function proneSheet() {
  const r = S.req, P = S.prone, o = P.facing ? (r.prone_turns || []).find((t) => t.facing === P.facing) : null;
  sheet(`<h3>${esc(r.name)} stays prone</h3><div class="msg">It may turn on the ground, 1 MP a hexside (walking or running MP). Tap an arrow round the 'Mech to turn, then hold the button; with no arrow chosen it stays as it lies. &times; goes back.</div>`);
  const c = $("cluster"); c.style.display = "flex";
  c.innerHTML = `<div class="readout"><b>${o ? "MP " + o.mp : "MP 0"}</b> &middot; ${o ? "faces " + o.facing + " (" + o.mode + ")" : "lies as it is"}<br><span>stays prone</span></div><button class="go big" data-act="prone-go" data-hold="1">Stay prone<small>hold</small></button><button class="x" data-act="undo" aria-label="Back (Esc)">&times;</button>`;
}
function drawProneArrows(layer) {
  const r = S.req, u = unit(r.unit); if (!u || !u.hex) return;
  const by = Object.fromEntries((r.prone_turns || []).map((t) => [t.facing, t]));
  arrowRing(layer, u.hex, Object.keys(by), S.prone.facing || u.facing, (f) => modeCol(by[f].mode), (f) => { S.prone.facing = f; proneSheet(); redraw(); });
}
async function standPlan() {
  const r = S.req, seq = S.seq; if (!r || r.kind !== "stand_up") return;
  sheet('<div class="msg">Working out the moves after standing...</div>');
  const v = await query({ q: "reach", unit: r.unit });
  if (seq !== S.seq || !S.req || S.req.kind !== "stand_up") return;
  if (v.error || !v.view) { sheet(`<div class="err">${esc(v.error || "No move can be shown.")}</div><div class="row"><button class="go" data-act="stand" data-v="1">Stand up (no plan)</button><button data-act="stand" data-v="0">Stay prone</button></div>`); return; }
  S.mv = v.view; S.reachIdx = null; S.way = []; S.wrIdx = null; S.dest = null; S.path = null;
  moveIntro(); redraw();
}
HANDLERS.boost = (r) => {
  const u = unit(r.unit), e = eq(u), b = (e.boost || {});
  sheet(`<h3>${esc(r.name)}: ${e.masc && e.supercharger ? "MASC and supercharger" : e.masc ? "MASC" : "supercharger"}</h3>${errLine(r)}<div class="msg">Using it this turn raises the running speed; each use needs a roll of <b>${b.tn}</b> or more, and a failure costs criticals and may force a fall. The roll gets harder each turn in a row. Your choice stays until you change it.</div><div class="row"><button class="${b.on ? "go" : ""}" data-act="boost" data-v="1">Use it</button><button class="${b.on ? "" : "go"}" data-act="boost" data-v="0">Not this turn</button></div>`);
};
HANDLERS.spot = (r) => {
  sheet(`<h3>${esc(r.name)}: spot for indirect fire?</h3>${errLine(r)}<div class="msg">A spotter that sees an enemy lets friends without a line of sight fire at it indirectly. A spotter may still fire its own weapons, at +1 to hit.</div><div class="row">${r.candidates.map((c) => `<button data-act="spot" data-id="${c.id}">${esc(c.name)} &middot; range ${c.distance} &middot; ${c.friends} friend${c.friends === 1 ? "" : "s"} could use it</button>`).join("")}<button class="go" data-act="spot" data-id="">No spotting</button></div>`);
};
HANDLERS.tag = (r) => {
  sheet(`<h3>${esc(r.name)}: TAG designation</h3>${errLine(r)}<div class="msg">TAG is its own short attack before the weapon attacks. Designating the 'Mech helps homing artillery; designating the hex works for the ground under it. Pick a target and what to light up, or skip.</div><table>${r.candidates.map((c) => `<tr><td>${esc(c.name)}</td><td>range ${c.distance}</td><td>${c.tn_mech != null ? `<button class="sm" data-act="tag" data-id="${c.id}" data-aim="mech">'Mech TN ${c.tn_mech}</button>` : ""}</td><td>${c.tn_hex != null ? `<button class="sm" data-act="tag" data-id="${c.id}" data-aim="hex">Hex TN ${c.tn_hex}</button>` : ""}</td></tr>`).join("")}</table><div class="row"><button class="go" data-act="tag" data-id="">Skip TAG</button></div>`);
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
function jumpButton() { const v = S.mv; if (!v || !(v.jump > 0) || standing()) return ""; const on = jumpOn(); return `<button class="sm jt ${on ? "on" : ""}" data-act="jump-toggle" title="Jump on: only jumps are shown">Jump ${on ? "on" : "off"}</button>`; }
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
    S.mv = null; sheet(`<h3>Choose a unit to move</h3><div class="msg">Looking at ${esc((unit(id) || {}).name || "it")}...</div>`); redraw();
    const r = await query({ q: "reach", unit: id });
    if (seq !== S.seq || !S.req || S.req.kind !== "move_order") return;
    v = S.views[id] = { seq, error: r.error, view: r.view };
  }
  if (S.sel !== id) return;
  S.mv = v.view || null; S.reachIdx = null; moveIntro(v.error); redraw();
}
// what the sheet says before a hex is chosen
function moveIntro(unavailable) {
  const u = unit(S.sel) || {}, v = S.mv;
  clearCluster();
  if (S.order) {
    const others = S.cands.filter((c) => c !== S.sel).map((c) => `<button class="sm" data-act="look" data-id="${c}">${esc((unit(c) || {}).name || c)} ${esc((unit(c) || {}).mech || "")}</button>`).join("");
    sheet(`<h3>${esc(u.name || "")} ${esc(u.mech || "")}: choose where it moves</h3>${errLine(S.req)}
      <div class="msg">${v ? "Tap a tinted hex to plan the move: cyan = walk, yellow = run, orange = jump. Nothing is decided until you press Move!" : esc(unavailable || "No move can be shown for this unit.")}</div>
      <div class="msg">Look at your other units first: tap one on the map or in the strip${others ? ", or here" : ""}.</div>
      <div class="row">${others}</div>
      <div class="row"><button data-act="pick-unit" data-id="${S.sel}">${v ? "Choose it, and plan the move in the next step" : "Move this unit"}</button></div>`);
    if (v) stayCluster();
    return;
  }
  if (standing()) {
    sheet(`<h3>Stand up and move ${esc(v.name)}</h3><div class="msg">If the roll (<b>${S.req.tn}</b>+) succeeds it moves on with ${v.run} MP. Tap a tinted hex, or an arrow round the 'Mech to stand facing another way (free). Hold <b>Move!</b> to stand and move; with nothing chosen it stands where it is. &times; goes back.</div>`);
    stayCluster(); return;
  }
  sheet(`<h3>Move ${esc(v.name)}</h3>${errLine(v)}<div class="msg">${v.standup_mp != null ? "It has stood up and moves on with the points left. " : ""}${v.entry ? "Choose where to enter the map. " : ""}Tap a tinted hex. ${v.attacks.length ? "Tap an enemy for a charge or death from above. " : ""}Cyan = walk (${v.walk} MP), yellow = run (${v.run} MP)${v.jump ? ", orange = jump (" + v.jump + " MP)" : ""}.</div>${v.entry ? "" : '<div class="msg">To leave it where it is, hold <b>Move!</b>.</div>'}${dropRow(null)}${v.entry ? "" : '<div class="row"><button class="sm" data-act="eject-ask">Eject...</button></div>'}`);
  stayCluster();
}
// WAYPOINTS: each tap inside the lit range adds a waypoint and the range re-lights from there with the points left; the last tap is the
// destination. The unit WALKS THE ROUTE AS DRAWN (Daniel, 2026-11-24, replacing the 2026-11-22 ruling): the cheapest way to each waypoint
// in turn, then the turns to the chosen facing. The cost, mode, hexes moved, TMM, heat, piloting rolls and terrain damage shown are those
// of that route, and the answer carries the waypoints so the engine walks the same one (`drawn_route.rs`), rolling each piloting skill
// roll and taking each hazard where the route puts it. A route round a hazard therefore avoids it.
const enrich = (o) => { const e = ((S.reachIdx || {})[o.hex] || []).find((x) => x.facing === o.facing && x.mode === o.mode) || ((S.reachIdx || {})[o.hex] || [])[0] || {}; return { tmm: 0, hexes: 0, heat: 0, ...e, ...o }; };
async function setWay(way) {
  const seq = S.seq, r = await query({ q: "way", unit: S.mv.unit, waypoints: way });
  if (seq !== S.seq || !S.req) return false;
  if (r.error) { sheet(`<h3>Waypoint</h3><div class="err">${esc(r.error)}</div><div class="row"><button data-act="undo">Back</button></div>`); return false; }
  S.way = way; S.wrIdx = reachIndex({ options: r.reach.map(enrich) }); S.attackSel = null;
  S.path = r.legs.map((l, i, a) => ({ ...l, k: i && a[i - 1].hex === l.hex ? "turn" : "forward" }));
  S.dest = way[way.length - 1];
  const os = S.wrIdx[S.dest] || [], cheapest = os.reduce((a, b) => (a.mp <= b.mp ? a : b), os[0]);
  if (!cheapest) return false;
  if (!os.some((o) => o.mode === S.mode)) S.mode = cheapest.mode;
  const same = os.filter((o) => o.mode === S.mode), cur = unit(S.mv.unit);
  if (!same.some((o) => o.facing === S.facing)) S.facing = (same.find((o) => cur && o.facing === cur.facing) || same[0]).facing;
  moveSheet(); redraw();
  return true;
}
async function pickDest(h) {
  S.reachIdx = S.reachIdx || reachIndex(S.mv);
  const idx = S.way.length ? S.wrIdx : S.reachIdx, os = idx[h]; if (!os) return;
  const canWay = S.mv.standup_mp == null && !S.mv.entry && os.some((o) => o.mode !== "Jump");
  if (!S.way.length && !canWay) {   // a jump, a stand-up move or an entry: the destination alone
    const cheapest = os.reduce((a, b) => (a.mp <= b.mp ? a : b));
    S.dest = h; S.mode = cheapest.mode; S.attackSel = null;
    const same = os.filter((o) => o.mode === S.mode), cur = unit(S.mv.unit);
    S.facing = (same.find((o) => cur && o.facing === cur.facing) || same[0]).facing;
    moveSheet(); redraw(); loadPath(); return;
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
      if (o) { S.facing = f; S.mode = o.mode; moveSheet(); redraw(); loadPath(); }
    });
    return;
  }
  const os = destOpts(), cheap = {};
  for (const o of os) if (!cheap[o.facing] || o.mp < cheap[o.facing].mp) cheap[o.facing] = o;
  arrowRing(layer, S.dest, Object.keys(cheap), S.facing, (f) => modeCol((os.find((o) => o.facing === f && o.mode === S.mode) || cheap[f]).mode), (f) => {
    const same = os.find((o) => o.facing === f && o.mode === S.mode);
    S.facing = f; if (!same) S.mode = cheap[f].mode;
    moveSheet(); redraw(); loadPath();
  });
}
function drawAttackStops(layer) {
  if (!S.attackSel && !S.attackTarget) return;
  for (const a of S.mv.attacks.filter((x) => x.target === S.attackTarget)) {
    const s = sc(a.hex), [x, y] = at(a.hex), sel = S.attackSel && S.attackSel.hex === a.hex && S.attackSel.facing === a.facing && S.attackSel.kind === a.kind;
    const p = el("polygon", { points: HP(a.hex, 0.92), fill: "#000", "fill-opacity": sel ? ".5" : ".3", stroke: "#fff", "stroke-width": (sel ? 3 : 1.5) * s, style: "cursor:pointer" }, layer);
    const t = el("text", { x, y: y + 4 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, layer); t.textContent = a.kind === "charge" ? "CHG" : "DFA";
    p.addEventListener("click", (e) => { e.stopPropagation(); chooseAttack(a); });
  }
}
// Leaving the 'Mech where it stands needs no button of its own: Move! with no destination chosen is the stay (Daniel, 2026-11-22). Move! is a
// long press (about 0.6 s, with a fill that shows the progress) so a stray tap cannot commit a move.
function stayCluster() {
  const v = S.mv; if (!v || v.entry || S.dest) return;
  const c = $("cluster"); c.style.display = "flex";
  c.innerHTML = `<div class="readout"><b>MP 0</b> &middot; ${standing() ? "stands here" : "stays here"}<br><span>no destination chosen</span>${jumpButton()}</div><button class="go big" data-act="commit" data-hold="1">Move!<small>hold</small></button>${standing() ? '<button class="x" data-act="undo" aria-label="Back (Esc)">&times;</button>' : ""}`;
}
let HOLD = null;
const holdEnd = () => { if (HOLD) { clearTimeout(HOLD.t); HOLD.b.classList.remove("holding"); HOLD = null; } };
document.addEventListener("pointerdown", (e) => {
  const b = e.target.closest("button.go[data-hold]"); if (!b) return; holdEnd();
  b.classList.add("holding");
  HOLD = { b, t: setTimeout(() => { const x = HOLD; HOLD = null; x.b.classList.remove("holding"); if (x.b.dataset.act === "commit") doCommit(); else act(x.b); }, 600) };
});
["pointerup", "pointercancel"].forEach((n) => document.addEventListener(n, holdEnd));
// Hazard confirmation (Daniel, 2026-11-22): a move that calls for piloting rolls or crosses dangerous terrain lists each risk and asks first
function hazardList(o) {
  const out = [];
  if (o.psrs) out.push(`${o.psrs} piloting skill roll${o.psrs > 1 ? "s" : ""} on this path`);
  if (o.hazard) out.push(`about ${(+o.hazard).toFixed(1)} damage from terrain`);
  const seen = new Set();
  for (const p of (S.path || [])) { const h = p.hex; if (!h || seen.has(h)) continue; seen.add(h); const f = ((S.board.hexes[h] || {}).f) || {}; for (const k of Object.keys(f)) if (/lava|rubble|ice|mine|swamp|water|fire|magma|sand/i.test(k)) out.push(`${h}: ${k}${f[k] && f[k] !== true && f[k] !== 0 ? " " + f[k] : ""}`); }
  return out;
}
const doCommit = () => {
  if (!S.dest) { commitMove({ stay: true }); return; }
  const o = optNow(), hz = o ? hazardList(o) : [];
  if (hz.length && !S.hazardOk) { showCard(`<b>Hazards on this move</b><ul>${hz.map((h) => `<li>${esc(h)}</li>`).join("")}</ul><div class="msg">Moving on accepts them.</div><div class="row"><button class="go" data-act="hazard-ok">Move anyway</button></div>`); return; }
  S.hazardOk = false; commitMove({ hex: S.dest, facing: S.facing, mode: S.mode, ...(S.way.length ? { waypoints: S.way.slice() } : {}) });
};
// the action cluster over the map: the move readout, the commit button, undo
function clearCluster() { $("cluster").innerHTML = ""; $("cluster").style.display = "none"; }
function setCluster(o, label, extra) {
  const c = $("cluster"); c.style.display = "flex";
  c.innerHTML = `<div class="readout"><b>MP ${o.mp} / ${mvBudget(o.mode)}</b> &middot; TMM +${o.tmm}${extra || ""}<br><span>${o.mode}${o.psrs ? ` &middot; ${o.psrs} piloting roll${o.psrs > 1 ? "s" : ""}` : ""}</span>${jumpButton()}</div><button class="go big" data-act="commit" data-hold="1">${label}<small>hold</small></button><button class="x" data-act="undo" aria-label="Undo (Esc)">&times;</button>`;
}
function moveSheet() {
  const os = destOpts(), modes = [...new Set(os.map((o) => o.mode))], o = optNow() || os[0], warns = [];
  if (o.psrs) warns.push(`${o.psrs} piloting roll${o.psrs > 1 ? "s" : ""} on this path`);
  if (o.hazard) warns.push(`about ${(+o.hazard).toFixed(1)} damage from terrain`);
  setCluster(o, S.order ? "Move!" : "Move!");
  sheet(`<h3>${esc(S.mv.name)} to ${S.dest}</h3>${errLine(S.req)}
    <div class="row">${modes.map((m) => `<button data-act="mode" data-m="${m}" class="${m === S.mode ? "on" : ""}" style="border-color:${modeCol(m)}">${m === "Stand Still" ? "Stand still" : m + " " + mvBudget(m)}</button>`).join("")}</div>
    <div class="msg">${o.mp} MP (turns included) &middot; ${o.hexes} hex${o.hexes === 1 ? "" : "es"} &middot; target movement modifier +${o.tmm} &middot; movement heat ${o.heat}</div>
    ${warns.length ? `<div class="warnt">&#9888; ${warns.join("; ")}. Moving on accepts the warning.</div>` : ""}
    ${S.way.length > 1 ? `<div class="msg">Waypoints: ${S.way.map((h, i) => i + 1 + " " + h).join(" &rarr; ")}. The unit walks exactly this route, so the cost, hexes moved and piloting rolls shown are those of the route drawn.</div>` : ""}
    ${dropRow(o)}
    <div class="msg">Tap another tinted hex to add a waypoint (the lit range is what is left from here). Tap an arrow around the hex to turn. &times; or Esc removes the last waypoint.</div>
    `);
}
function undo() {
  if (!S.req) return;
  if (moving() && S.way.length > 1) { setWay(S.way.slice(0, -1)); return; }
  if (moving() && standing() && !S.dest && !S.attackTarget) { HANDLERS.stand_up(S.req); redraw(); return; }
  if (S.prone && S.req.kind === "stand_up") { S.prone = null; HANDLERS.stand_up(S.req); redraw(); return; }
  if (moving()) { S.way = []; S.wrIdx = null; S.dest = null; S.path = null; S.attackSel = null; S.attackTarget = null; S.attackConfirm = false; moveIntro(); redraw(); return; }
  if (S.decl && S.req.kind === "declaration") { S.decl.sel.clear(); declSheet(); redraw(); return; }
  if (S.fire && S.req.kind === "target") { S.fire.assign.clear(); S.fire.order = []; S.fire.lastPrimary = null; if (S.decl) S.decl.sel.clear(); fireRebuild(); return; }
  if (S.req.kind === "deploy" && S.dp) { S.dp.hex = null; HANDLERS.deploy(S.req); redraw(); }
}
// Send the move: in the move_order question the move is a plan that goes with the unit chosen; later the movement question uses it.
// DROP TO THE GROUND (Core p.51; engine pass 2026-11-24): after a ground move with 1 MP to spare, not a jump; it ends prone, same facing.
// A toggle in the move sheet (also with nothing chosen: drop where it stands); it goes with the answer as "prone": true.
function dropOk(o) { const v = S.mv; if (!v || standing() || v.standup_mp != null || v.entry) return false; const mode = o ? o.mode : "Stand Still", mp = o ? o.mp : 0; return mode !== "Jump" && mp + 1 <= v.run; }
function dropRow(o) { return dropOk(o) ? `<div class="row"><button class="sm ${S.drop ? "on" : ""}" data-act="drop">${S.drop ? "&#10003; " : ""}Drop prone at the end (+1 MP)</button></div>` : ""; }
function commitMove(answer) { if (S.drop && (answer.stay || answer.hex) && dropOk(answer.stay ? null : optNow())) answer = { ...answer, prone: true }; if (standing()) send({ stand: true, plan: answer }); else if (S.order) send({ unit: S.mv.unit, plan: answer }); else send(answer); }
// charge / death from above: tap an enemy; the stops go black; pick one; a popup explains and asks
function onUnitTap(id) {
  const r = S.req; DOCK.unit = null;
  if (r && r.kind === "move_order" && r.candidates.includes(id)) { if (id !== S.sel) selectMover(id); else { S.sel = id; redraw(); } return; }
  S.sel = id;
  if (moving() && id === S.mv.unit) {                      // its own hex (the token covers it): turn in place
    const u = unit(id); S.reachIdx = S.reachIdx || reachIndex(S.mv);
    if (u && u.hex && !S.way.length && S.reachIdx[u.hex]) { pickDest(u.hex); return; }
  }
  if (moving()) {
    const list = S.mv.attacks.filter((a) => a.target === id);
    if (list.length) { S.attackTarget = id; S.way = []; S.wrIdx = null; S.dest = null; S.path = null; S.attackSel = null; S.attackConfirm = false; clearCluster(); attackSheet(list); redraw(); return; }
  }
  if (r && (r.kind === "spot" || r.kind === "tag")) { const c = r.candidates.find((x) => x.id === id); if (c && r.kind === "spot") { send({ target: id, fires: true }); return; } }
  redraw();
}
function attackSheet(list) {
  const t = list[0];
  sheet(`<h3>${esc(t.target_name)}: charge or death from above</h3><div class="msg">The black hexes are where you can stop to attack. The path turns to colour when you pick one.</div><div class="row">${list.map((a, i) => `<button data-act="atk" data-i="${i}">${a.kind === "charge" ? "Charge" : "Death from above"} from ${a.hex} (${a.mp} MP)</button>`).join("")}<button data-act="undo">Back</button></div>`);
}
async function chooseAttack(a) {
  S.attackSel = a; S.attackConfirm = true;
  clearCluster();
  sheet(`<h3>${a.kind === "charge" ? "Charge" : "Death from above"} on ${esc(a.target_name)}</h3><div class="msg">You end the move at <b>${a.hex}</b> facing ${a.facing}, using ${a.mp} MP (${a.mode}). The attack is made in the Physical Attack Phase: to hit <b>${a.tn}</b> or more, about ${a.hit != null ? Math.round(a.hit * 100) + "%" : "?"}; ${a.damage} damage to the target; <b>you take ${a.self_damage}</b>${a.kind === "dfa" ? " (and a fall if you miss)" : ""}. A charge or death from above cannot be undone once the turn is set.</div><div class="row"><button class="go" data-act="atk-yes">Yes, make the move</button><button data-act="atk-no">No, back up</button></div>`);
  redraw(); loadPath();
}

// ---- deployment: the units that are placed before turn 1 go on free hexes of the player's own deployment area
HANDLERS.deploy = (r) => {
  S.sel = r.unit; S.dp = S.dp && S.dp.seq === S.seq ? S.dp : { seq: S.seq, hex: null, facing: r.facing || "N" };
  const dp = S.dp, u = unit(r.unit) || {};
  clearCluster();
  if (dp.hex) { const c = $("cluster"); c.style.display = "flex"; c.innerHTML = `<div class="readout"><b>${esc(dp.hex)}</b> &middot; facing ${dp.facing}<br><span>${esc(u.name || "")} ${esc(u.mech || "")}</span></div><button class="go big" data-act="place" data-hold="1">Place!<small>hold</small></button><button class="x" data-act="undo" aria-label="Undo (Esc)">&times;</button>`; }
  sheet(`<h3>Place ${esc(r.name)} ${esc(u.mech || "")}</h3>${errLine(r)}<div class="msg">${dp.hex ? `Placing at <b>${dp.hex}</b> facing <b>${dp.facing}</b>. Tap an arrow to turn it, or another hex to move it.` : "Tap one of the green hexes: your deployment area under this game's deployment rules. Units already placed are on the map."}</div>`);
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
  sheet('<div class="msg">Working out the numbers...</div>'); redraw();
  await refreshPreview(true);
};
function ingest(pv) { const F = S.fire; F.pvt = new Map((pv.targets || []).map((t) => [t.id, t])); F.arcs = pv.arcs || F.arcs; }
async function refreshPreview(first) {
  const F = S.fire, seq = S.seq, p = primaryOf();
  const pv = await query({ q: "preview", unit: F.unit, ...(p != null ? { primary: p } : {}) });
  if (seq !== S.seq || S.fire !== F || !S.req || S.req.kind !== "target") return;
  if (pv.error) { sheet(`<div class="err">${esc(pv.error)}</div>`); return; }
  ingest(pv); F.lastPrimary = p;
  if (first) lookAtTarget();
  fireRebuild();
}
function fireRebuild() {
  const F = S.fire, e = F.pvt.get(F.tcur), keep = S.decl;
  if (!e || !e.req) {                                       // nothing can be declared at this one (no line of sight, a secondary target the book refuses)
    S.decl = null; $("wpanel").style.display = "none";
    const tu = unit(F.tcur) || {};
    sheet(`<h3>${esc(tu.name || "")}: no shot</h3><div class="msg">${esc(e && e.why ? e.why : "No weapon can be declared at this target (no line of sight, or out of every weapon's range).")}</div>${fireTargetRow()}`);
    fireCluster(); redraw(); return;
  }
  const rows = e.req.weapons.map((w) => ({ ...w, ...(F.arcs[w.id] || {}) }));
  S.decl = { req: e.req, rows, sel: new Set([...F.assign].filter(([, t]) => t === F.tcur).map(([w]) => w)), aim: keep ? keep.aim : {}, charge: keep ? keep.charge : new Set(rows.filter((w) => w.charge).map((w) => w.name)),
    focus: keep && rows.some((w) => w.id === keep.focus) ? keep.focus : (rows.find((w) => w.in_range) || rows[0] || {}).id, aimFor: null, bin: keep ? keep.bin : null, strike: keep ? keep.strike : 0, groups: [] };
  declSheet(); redraw();
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
function fireLines() {
  const T = fireTotals(), F = S.fire, p = primaryOf();
  const lines = [...T.per].map(([t, v]) => { const req = (F.pvt.get(t) || {}).req || {}; return `<div class="msg"><b>${esc((unit(t) || {}).name || t)}</b> &middot; range ${req.distance ?? "?"} &middot; ${v.n} weapon${v.n === 1 ? "" : "s"} &middot; ~${v.ev.toFixed(1)} dmg${t === p ? " &middot; primary" : " &middot; secondary +1"}</div>`; }).join("");
  return lines + fireTargetRow();
}
function fireTargetRow() {
  const F = S.fire;
  return `<div class="row">${nearestFirst().map((e) => { const t = fireTotals().per.get(e.id); return `<button class="${e.id === F.tcur ? "on" : ""}" data-act="look-target" data-id="${e.id}">${esc((unit(e.id) || {}).name || e.id)} ${esc(short(unit(e.id) || {}))} &middot; ${e.distance ?? "?"}${t ? ` &middot; ${t.n}` : ""}</button>`; }).join("")}<button data-act="hold">Hold fire</button></div>`;
}
function fireCluster() {
  const T = fireTotals(), c = $("cluster"); c.style.display = "flex";
  const heat = S.decl ? heatIfFired() : "";
  c.innerHTML = `<div class="readout"><b>${T.n} weapon${T.n === 1 ? "" : "s"}${T.per.size > 1 ? ` &middot; ${T.per.size} targets` : ""}</b> &middot; ~${T.ev.toFixed(1)} dmg<br><span>${S.decl ? `heat ${S.decl.req.heat} &rarr; <b>${heat}</b>` : ""}</span></div><button class="go big" data-act="fire-go" ${T.n ? "" : "disabled"}>Fire!</button><button class="x" data-act="clear" aria-label="Clear (Esc)">&times;</button>`;
}
function lookAtTarget() { const me = unit(S.req.unit), t = unit(S.fire && S.fire.tcur); if (me && me.hex && t && t.hex) focusOn([me.hex, t.hex], 3); }
function setTcur(id) {
  const F = S.fire; if (!F || !S.req || S.req.kind !== "target" || !S.req.enemies.some((e) => e.id === id)) return false;
  F.tcur = id; fireRebuild(); lookAtTarget(); return true;
}
function cycleTcur(dir) { const o = nearestFirst(); if (!o.length) return; const i = Math.max(0, o.findIndex((e) => e.id === S.fire.tcur)); setTcur(o[(i + dir + o.length) % o.length].id); }
function fireGo() {
  const F = S.fire, D = S.decl; if (!F || !F.assign.size) return;
  const p = primaryOf(), order = [p, ...F.order.filter((t) => t !== p)];
  const entries = order.map((t) => ({ t, ids: [...F.assign].filter(([, x]) => x === t).map(([w]) => w), charge: D ? [...D.charge] : [], aim: D ? { ...D.aim } : {} }));
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
  sc.i++; sc.at = S.seq; send({ weapons: e.ids, charge: e.charge, aim: e.aim }); return true;
}
function drawTargets(layer) {
  const F = S.fire, D = S.decl, w = D && D.rows.find((x) => x.id === D.focus), T = fireTotals();
  for (const t of S.req.enemies) {
    const u = unit(t.id); if (!u || !u.hex) continue;
    const s = sc(u.hex), cur = F && t.id === F.tcur;
    const p = el("polygon", { points: HP(u.hex, 0.95), fill: "#e07468", "fill-opacity": cur ? ".35" : ".18", stroke: "#e07468", "stroke-width": (cur ? 3.5 : 2) * s, style: "cursor:pointer" }, layer);
    p.addEventListener("click", () => setTcur(t.id));
    const e = F && F.pvt.get(t.id), req = e && e.req; let tn = null;
    if (req) tn = w ? (req.weapons.find((q) => q.id === w.id) || {}).tn : req.base_tn;
    if (F) { // the to-hit pill on the enemy's hex: the focused weapon's number against it; tap it for the line items
      const txt = tn == null ? "-" : tn + "+", g = el("g", { style: "cursor:pointer", "data-tn-pill": t.id }, layer), [px, py] = P(u.hex, 0.3, -0.95, MV.unitHeight());
      el("rect", { x: px, y: py, width: 28 * s, height: 15 * s, rx: 3 * s, fill: "#000", stroke: cur ? "#fff" : "#e07468", "stroke-width": 1.2 * s }, g);
      const tx = el("text", { x: px + 14 * s, y: py + 11 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: tn == null ? "#999" : "#fff", "pointer-events": "none" }, g); tx.textContent = txt;
      g.addEventListener("click", (ev) => { ev.stopPropagation(); if (req && w) { const row = req.weapons.find((q) => q.id === w.id); if (row) tnCard(req, row); } });
      const n = T.per.get(t.id);
      if (n) { const [cx, cy] = P(u.hex, -0.55, -0.8, MV.unitHeight()); el("circle", { cx, cy, r: 8 * s, fill: "#e07468", stroke: "#000", "stroke-width": 1 * s, "pointer-events": "none" }, layer); const nt = el("text", { x: cx, y: cy + 3.5 * s, "text-anchor": "middle", "font-size": 10 * s, "font-weight": 700, fill: "#000", "pointer-events": "none" }, layer); nt.textContent = n.n; }
    }
  }
}
// the number to hit, line by line (the pill beside a weapon, a target or in the info bar opens it)
const RANGE_MOD = { short: 0, medium: 2, long: 4 };
function tnCard(req, w) {
  const b = req.breakdown, sgn = (n) => (n > 0 ? "+" : "") + n, line = (label, v) => (v || v === 0 ? `<tr><td>${label}</td><td>${sgn(v)}</td></tr>` : "");
  const band = String(w.range || "").toLowerCase().replace(/[^a-z]/g, ""), bandKey = Object.keys(RANGE_MOD).find((k) => band.startsWith(k.slice(0, 3)));
  const bandMod = bandKey != null ? RANGE_MOD[bandKey] : 0, adj = w.adj || 0, rest = adj - bandMod;
  const mode = b.attacker_mode || "", moved = { "Stand Still": "stood still", Walk: "walked", Run: "ran", Jump: "jumped" }[mode] || mode.toLowerCase();
  const rows = [`<tr><td>${esc(req.name)}'s gunnery</td><td>${b.gunnery}</td></tr>`, line(`${esc(req.name)} ${esc(moved)}`, b.attacker_movement), line(`${esc(req.target_name)}'s movement (the target movement modifier)`, b.target_movement),
    line("terrain between, and in the target's hex (line of sight)", b.line_of_sight), line("partial cover", b.cover), line("heat", b.heat), line("target prone", b.target_prone), line("stealth", b.stealth),
    line(`other${b.note ? " (" + esc(b.note) + ")" : b.secondary ? " (secondary target)" : ""}`, b.other),
    line(`${bandKey || w.range || "range"} range`, bandKey != null ? bandMod : null), line(`${esc(w.name)}'s own modifiers (ammunition, mode, minimum range...)`, bandKey != null ? rest : adj)].filter(Boolean).join("");
  showCard(`<b>${esc(w.name)} &rarr; ${esc(req.target_name)}</b> &middot; range ${req.distance}<table class="tnt">${rows}<tr class="tot"><td>To hit</td><td>${w.tn}+ (${Math.round((oddsOf(w.tn) || 0) * 100)}%)</td></tr></table><div class="msg">Roll ${w.tn} or more on two dice.</div>`);
}
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
  const s = (sc(a.hex) + sc(t.hex)) / 2, uh = MV.unitHeight(), [x1, y1] = at(a.hex, uh), [x2, y2] = at(t.hex, uh);
  el("line", { x1, y1, x2, y2, stroke: "#e07468", "stroke-width": 1.8 * s, "stroke-dasharray": `${5 * s} ${4 * s}`, "pointer-events": "none" }, layer);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, txt = String(range ?? "");
  el("rect", { x: mx - (4 + txt.length * 3.5) * s, y: my - 8 * s, width: (8 + txt.length * 7) * s, height: 16 * s, rx: 8 * s, fill: "#000", stroke: "#e07468", "stroke-width": 1.2 * s, "pointer-events": "none" }, layer);
  const tx = el("text", { x: mx, y: my + 4 * s, "text-anchor": "middle", "font-size": 11 * s, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, layer); tx.textContent = txt + "h";
}
function drawAim(layer) {
  if (!S.decl) return;
  for (const [wid, hex] of Object.entries(S.decl.aim)) { const s = sc(hex), [x, y] = at(hex); el("circle", { cx: x, cy: y, r: R * 0.6 * s, fill: "none", stroke: "#e07468", "stroke-width": 2.5 * s, "stroke-dasharray": `${4 * s} ${3 * s}`, "pointer-events": "none" }, layer); el("circle", { cx: x, cy: y, r: 3 * s, fill: "#e07468", "pointer-events": "none" }, layer); }
  if (S.decl.aimFor) for (const label of MV.order(Object.keys(S.board.hexes))) { const p = el("polygon", { points: HP(label), fill: "transparent", style: "cursor:crosshair" }, layer); p.addEventListener("click", () => setAim(label)); }
}
HANDLERS.declaration = (r) => {
  S.sel = r.unit;
  if (scriptDecl(r)) return;
  S.decl = { req: r, rows: r.weapons, sel: new Set(), aim: {}, charge: new Set(r.weapons.filter((w) => w.charge).map((w) => w.name)), focus: (r.weapons.find((w) => w.in_range) || r.weapons[0] || {}).id, aimFor: null, bin: null, strike: 0, groups: [] };
  declSheet();
  const me = unit(r.unit); if (me && me.hex && r.target_hex) focusOn([me.hex, r.target_hex], 3);
};
const isDistant = (w) => (w.modes || []).some((m) => m.selected && /distant/i.test(m.label)) || /distant/i.test(w.mode || "");
const focusTn = (D) => { const w = D.rows.find((x) => x.id === D.focus); return w && w.tn != null ? `: ${esc(w.name)} needs ${w.tn}+ (${Math.round((oddsOf(w.tn) || 0) * 100)}%)` : ""; };
const focusParts = (D) => { const w = D.rows.find((x) => x.id === D.focus); if (!w || w.tn == null) return ""; const b = D.req.breakdown.base, adj = w.adj || 0; return ` <b>${esc(w.name)}</b>: base ${b} ${w.range ? esc(w.range) + " range and its own modifiers " : "its modifiers "}${adj >= 0 ? "+" : ""}${adj} = <b>${w.tn}</b>.`; };
function breakdownText(r) {
  const b = r.breakdown, parts = [["gunnery", b.gunnery], ["you moved", b.attacker_movement], ["target moved", b.target_movement], ["line of sight", b.line_of_sight], ["cover", b.cover], ["heat", b.heat], ["target prone", b.target_prone], ["stealth", b.stealth], ["other", b.other]].filter((p) => p[1]);
  return `base ${b.base}${b.secondary ? " (includes +1 for a secondary target)" : ""}: ` + parts.map((p) => `${p[0]} ${p[1] > 0 && p[0] !== "gunnery" ? "+" : ""}${p[1]}`).join(", ") + `. Each weapon adds its range band and its own modifiers.${b.note ? " " + esc(b.note) : ""}`;
}
// ---- the weapon panel (the fire phase)
const SORTS = [["mount", "Mount order"], ["range-d", "Range, long to short"], ["range-a", "Range, short to long"], ["dmg-d", "Damage, high to low"], ["dmg-a", "Damage, low to high"], ["heat-d", "Heat, high to low"], ["heat-a", "Heat, low to high"]];
O.sort = pref("sort", "mount"); O.group = pref("group", "1") === "1";
const oddsOf = (tn) => { if (tn == null) return null; let n = 0; for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) if (a + b >= tn) n++; return n / 36; };
const wDamage = (w) => (w.damage || (w.ev != null && oddsOf(w.tn) ? w.ev / oddsOf(w.tn) : 0) || 0);
const AMMO_ICON = '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><rect x="3" y="11" width="4" height="10" rx="1"/><rect x="9" y="8" width="4" height="13" rx="1"/><rect x="15" y="5" width="4" height="16" rx="1"/></svg>';
const FC_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.2" fill="currentColor"/><path d="M12 1v5M12 18v5M1 12h5M18 12h5"/></svg>';
// weapons share a row only when name, place and arc (rear / torso twist), ammunition bin, mode, rate and the number to hit all match
function groupKey(w) { return [w.name, [].concat(w.loc || []).join("/"), w.rear ? "r" : "", w.needs_twist ? "t" : "", ((w.bins || []).find((b) => b.selected) || {}).id ?? "", w.mode, w.shots, w.tn, w.in_range, w.jammed].join("|"); }
function makeGroups(rows) {
  const out = [], seen = new Map();
  rows.forEach((w, i) => {
    const k = O.group ? groupKey(w) : String(w.id);
    if (seen.has(k)) seen.get(k).members.push(w); else { const g = { members: [w], rep: w, order: i }; seen.set(k, g); out.push(g); }
  });
  const by = { "range-d": (g) => -(g.rep.ranges ? g.rep.ranges.long : 0), "range-a": (g) => (g.rep.ranges ? g.rep.ranges.long : 0), "dmg-d": (g) => -wDamage(g.rep), "dmg-a": (g) => wDamage(g.rep), "heat-d": (g) => -(g.rep.heat || 0), "heat-a": (g) => g.rep.heat || 0 }[O.sort];
  if (by) out.sort((a, b) => by(a) - by(b) || a.order - b.order);
  return out;
}
const tnPill = (w) => (w.tn == null ? '<span class="tnp no" title="cannot fire at this target">&ndash;</span>' : `<span class="tnp" data-act="tn" data-w="${w.id}" title="the number to hit with this weapon: ${w.tn} or more on 2d6 (${Math.round((oddsOf(w.tn) || 0) * 100)}%)">${w.tn}+</span>`);
const assignedIn = (g) => g.members.filter((w) => S.decl.sel.has(w.id)).length;
function heatIfFired() { const D = S.decl, r = D.req, h = S.fire ? fireTotals().heat : [...D.sel].reduce((a, id) => a + ((D.rows.find((w) => w.id === id) || {}).heat || 0), 0); return Math.max(0, r.heat + r.move_heat + h - r.dissipation); }
function declSheet() {
  const D = S.decl, r = D.req, rows = D.rows;
  if (S.fire) syncAssign();
  D.groups = makeGroups(rows);
  const sel = rows.filter((w) => D.sel.has(w.id)), wh = sel.reduce((a, w) => a + (w.heat || 0), 0), ev = sel.reduce((a, w) => a + (w.ev || 0), 0);
  const heat = heatIfFired(), heatCls = heat >= 14 ? "err" : heat >= 8 ? "warnt" : "";
  // the panel on the map
  const wp = $("wpanel"); wp.style.display = "block";
  const sortName = (SORTS.find((x) => x[0] === O.sort) || SORTS[0])[1];
  wp.innerHTML = `<div class="wh">${S.fire ? '<button class="sm" data-act="tgt-prev" aria-label="previous target">&#9664;</button>' : ""}<span title="${esc(r.target_name)}">&#9678; ${esc(S.fire ? short(unit(r.target) || {}) : r.target_name)} &middot; ${r.distance}</span>${S.fire ? '<button class="sm" data-act="tgt-next" aria-label="next target">&#9654;</button>' : ""}<button data-act="sort" title="Sort: ${esc(sortName)}">&#8645;</button></div>` + D.groups.map((g, gi) => {
    const w = g.rep, n = g.members.length, k = assignedIn(g), ok = w.in_range && !w.jammed, fired = false;
    const cls = ["wrow", ok ? "" : "out", w.jammed ? "jam" : "", D.focus != null && g.members.some((m) => m.id === D.focus) ? "focus" : ""].join(" ");
    const state = k === 0 ? (g.members.some(assignedElsewhere) ? "else" : "") : k === n ? "all" : "part";
    return `<div class="${cls}" data-g="${gi}"><button class="fc ${state}" data-act="assign" data-g="${gi}" ${ok ? "" : "disabled"} aria-label="assign ${esc(w.name)} to the target">${FC_ICON}</button><span class="wn" data-act="focus" data-g="${gi}">${esc(w.name)}${n > 1 ? ` <small>${k}/${n}</small>` : ""}${w.rear ? " <small>(r)</small>" : ""}${w.needs_twist ? " <small>(twist)</small>" : ""}${w.jammed ? " JAMMED" : ""}${ok ? "" : w.jammed ? "" : " <small>out</small>"}</span>${tnPill(w)}${(w.modes || []).length > 1 ? `<button class="sm" data-act="mode-w" data-g="${gi}" title="ammunition / firing mode">${esc(shortMode(w.mode))}</button>` : ""}${(w.rates || []).length > 1 ? `<button class="sm" data-act="rate-w" data-g="${gi}" title="rate of fire">x${w.shots}</button>` : ""}${w.chargeable ? `<button class="sm ${D.charge.has(w.name) ? "on" : ""}" data-act="charge-w" data-g="${gi}" title="charge the capacitor instead of firing">&#9889;</button>` : ""}${(w.bins || []).length ? `<button class="sm" data-act="bins-w" data-g="${gi}" title="ammunition bin">${AMMO_ICON}${(w.bins.find((b) => b.selected) || {}).shots ?? ""}</button>` : ""}</div>${D.bin === gi ? binRows(g, gi) : ""}`;
  }).join("");
  wp.querySelectorAll(".wn").forEach((node) => holdFor(node, () => { const g = D.groups[+node.dataset.g]; if (g) showWeaponCard(g.rep); }));
  // the plan tab
  const aimW = rows.find((w) => isDistant(w) && D.sel.has(w.id));
  const next = ["Strike", "Alpha Strike"][D.strike % 2];
  sheet(`<h3>${esc(r.name)} fires on ${esc(r.target_name)} &middot; range ${r.distance}${r.indirect ? " &middot; indirect" : ""}</h3>${errLine(r)}
    <div class="msg">Selected: ${D.sel.size} weapon${D.sel.size === 1 ? "" : "s"}, about ${ev.toFixed(1)} damage. Heat at end of turn about <span class="${heatCls}">${heat}</span> (now ${r.heat}, movement ${r.move_heat}, weapons ${wh}, sinks take off ${r.dissipation}).${heat >= 14 ? " Shutdown risk." : ""}</div>
    ${S.fire ? fireLines() : ""}
    <div class="msg">Tap the target symbol to put a weapon on the target shown (a group adds one at a time; tapping a full group clears it). Look at another target with the arrows, its chip or its hex, and assign weapons to it too: the first target is the primary, the rest are secondary targets (+1). <b>Fire!</b> fires them all. Tap a name to see its range bands and arc; tap a number for its line items; press and hold a name for its card.</div>
    <details open><summary class="msg">To-hit number${focusTn(D)}</summary><div class="msg">${breakdownText(r)}${focusParts(D)}</div></details>
    ${aimW ? `<div class="msg warnt">${esc(aimW.name)} is a distant shot: it lands next turn. Aim: <b>${D.aim[aimW.id] || r.target_hex}</b> <button class="sm ${D.aimFor ? "on" : ""}" data-act="aim-w" data-id="${aimW.id}">${D.aimFor ? "tap a hex on the map" : "Change the aim hex"}</button></div>` : ""}
    <div class="row"><button data-act="strike" title="Strike: the weapons worth their heat. Alpha Strike: everything in range.">${next}</button><button data-act="clear">Clear</button><button data-act="hold">Hold fire</button><button data-act="group">${O.group ? "Ungroup identical" : "Group identical"}</button><span class="msg">Sorted: ${esc(sortName)}</span></div>`);
  // the action cluster: what is assigned, and Fire!
  if (S.fire) fireCluster(); else { const c = $("cluster"); c.style.display = "flex";
  c.innerHTML = `<div class="readout"><b>${D.sel.size} weapon${D.sel.size === 1 ? "" : "s"}</b> &middot; ~${ev.toFixed(1)} dmg<br><span>heat ${r.heat} &rarr; <b class="${heatCls}">${heat}</b></span></div><button class="go big" data-act="fire-go">Fire!</button><button class="x" data-act="clear" aria-label="Clear (Esc)">&times;</button>`; }
  infoBar();
  wp.style.top = ($("info").offsetHeight + 12) + "px"; // under the info box
}
const shortMode = (m) => String(m || "mode").replace(/rounds?/i, "").trim().slice(0, 9) || "mode";
function binRows(g, gi) { const w = g.rep; return `<div class="wbins"><span class="msg">${esc(w.name)} draws from:</span>${w.bins.map((b) => `<button class="sm ${b.selected ? "on" : ""}" data-act="bin-pick" data-g="${gi}" data-b="${b.id}">${esc(LOCAB[b.loc] || b.loc || "?")} ${esc(b.name)} &middot; ${b.shots ?? "?"}</button>`).join("")}<button class="sm" data-act="bin-pick" data-g="${gi}" data-b="">Automatic</button></div>`; }
// the Strike button: the weapons worth their heat first (best damage per heat, up to a comfortable end-of-turn heat); pressed again, everything in range
function strikePick(level) {
  const D = S.decl, r = D.req, usable = D.rows.filter((w) => w.in_range && !w.jammed && !D.charge.has(w.name) && !assignedElsewhere(w));
  D.sel.clear();
  if (level === 1) { usable.forEach((w) => D.sel.add(w.id)); return; }
  let h = Math.max(0, r.heat + r.move_heat - r.dissipation);
  for (const w of usable.slice().sort((a, b) => (b.ev || 0) / ((b.heat || 0) + 0.5) - (a.ev || 0) / ((a.heat || 0) + 0.5))) { if ((w.heat || 0) === 0 || h + w.heat <= 8) { D.sel.add(w.id); h += w.heat || 0; } }
}
function holdFor(node, fn) { let t = null; const stop = () => { if (t) { clearTimeout(t); t = null; } }; node.addEventListener("pointerdown", () => { stop(); t = setTimeout(() => { t = null; fn(); }, 650); }); ["pointerup", "pointerleave", "pointercancel", "pointermove"].forEach((e) => node.addEventListener(e, stop)); }
async function setWeapons(extra) {
  const D = S.decl; if (!D) return;
  const aim = {}; for (const [k, v] of Object.entries(D.aim)) aim[k] = v;
  if (S.fire) {   // before the target is chosen: the settings belong to the unit; the answer is the whole preview again
    const F = S.fire, seq = S.seq, p = primaryOf(), keepSel = new Set(D.sel);
    const r = await query({ q: "set", unit: F.unit, target: F.tcur, ...(p != null ? { primary: p } : {}), charge: [...D.charge], aim, ...extra });
    if (seq !== S.seq || S.fire !== F) return;
    if (r.error) { D.req.error = r.error; declSheet(); return; }
    ingest(r); fireRebuild();
    for (const id of keepSel) { const w = S.decl && S.decl.rows.find((x) => x.id === id); if (!w || !w.in_range) S.decl && S.decl.sel.delete(id); else S.decl.sel.add(id); }
    declSheet(); redraw(); return;
  }
  const r = await query({ q: "set", unit: D.req.unit, charge: [...D.charge], aim, ...extra });
  if (r.error) { D.req.error = r.error; declSheet(); return; }
  D.rows = r.weapons; for (const id of [...D.sel]) { const w = D.rows.find((x) => x.id === id); if (!w || !w.in_range) D.sel.delete(id); }
  declSheet(); redraw();
}
function setAim(hex) { const D = S.decl; if (!D || !D.aimFor) return; D.aim[D.aimFor] = hex; D.aimFor = null; setWeapons({}); }

HANDLERS.physical = (r) => {
  S.sel = r.unit;
  sheet(`<h3>${esc(r.name)}: physical attack on ${esc(r.target_name)}</h3>${errLine(r)}<table><tr><th>Attack</th><th>To hit</th><th>Damage</th><th>Heat</th><th></th></tr>${r.kinds.map((k) => k.options.map((o, i) => `<tr><td>${esc(o.name)}</td><td>TN ${o.tn}</td><td>${o.damage}</td><td>${o.heat || ""}</td><td>${i === 0 ? `<button data-act="phys" data-k="${esc(k.kind)}">${esc(k.kind)}</button>` : ""}</td></tr>`).join("")).join("")}</table><div class="row"><button data-act="phys" data-k="">No physical attack</button></div>`);
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
    <div class="row"><button class="go" data-act="end-go">Continue</button><button data-act="detail">All switches...</button></div>`);
};
// VOLUNTARY SHUTDOWN (Core p.105; engine pass 2026-11-24): shut down in this End Phase; a 'Mech shut down by choice stays down until
// its player asks for a restart in a later End Phase (heat checks apply).
function powerRow(e) {
  const p = e.power; if (!p) return "";
  if (p.shutdown && p.by_choice) return `<div class="sw"><label>Shut down by choice</label><button class="sm ${p.request === "on" ? "go" : ""}" data-act="sw-power" data-v="${p.request === "on" ? "" : "on"}">${p.request === "on" ? "&#10003; Restart this End Phase" : "Restart this End Phase"}</button></div>`;
  if (p.shutdown) return "";
  return `<div class="sw"><label>Power plant</label><button class="sm ${p.request === "off" ? "go" : ""}" data-act="sw-power" data-v="${p.request === "off" ? "" : "off"}">${p.request === "off" ? "&#10003; Shut down this End Phase" : "Shut down this End Phase"}</button><span class="msg">it stays down until you restart it</span></div>`;
}

// ---------------------------------------------------------------- the dock: the bottom sheet with the unit's tabs
// Header (unit name, smaller / bigger arrows; a flick up or down does the same), a summary line, and the tabs Plan (what the question
// asks), Weapons, Stats (equipment switches, critical slots) and Armor (the silhouette with a pip for each point, damage turns pips red from
// the outside in). The question's own controls always live in Plan; the other tabs show whichever unit is selected (enemies read-only).
const DOCK = { size: 1, tab: "plan", unit: null };   // unit: the one a long press is inspecting (null: the selected one)
const TABS = [["plan", "Plan"], ["weapons", "Weapons"], ["stats", "Stats"], ["armor", "Armor"]];
function dockSize(n) { DOCK.size = Math.max(0, Math.min(2, n)); $("dock").dataset.size = DOCK.size; setPref("dock", DOCK.size); }
function dockTab(t) { DOCK.tab = t; if (DOCK.size === 0) dockSize(1); dockRender(); }
function dockRender() {
  const u = (DOCK.tab !== "plan" && unit(DOCK.unit)) || unit(S.sel) || S.units.find((x) => x.team === S.myTeam) || S.units[0];
  $("dock").dataset.tab = DOCK.tab;
  if (!u) return;
  const f = fracs(u);
  $("dockname").textContent = `${u.name} ${u.mech || ""}`.trim();
  $("docksum").innerHTML = `Walk ${u.walk} / Run ${u.run}${u.jump ? " / Jump " + u.jump : ""} &nbsp; Heat ${u.heat}${u.max_heat ? "/" + u.max_heat : ""} &nbsp; Armor ${Math.round(f.a * 100)}% &nbsp; Structure ${Math.round(f.s * 100)}%${u.prone ? " &nbsp; <b class='warnt'>PRONE</b>" : ""}${u.shutdown ? " &nbsp; <b class='err'>SHUT DOWN</b>" : ""}`;
  $("docktabs").innerHTML = TABS.map(([k, n]) => `<button class="tab ${k === DOCK.tab ? "on" : ""}" data-act="tab" data-t="${k}">${n}</button>`).join("");
  if (DOCK.tab !== "plan") $("tabbody").innerHTML = tabBody(u);
}
const renderDetail = dockRender;
function openDetail(tab) { DOCK.tab = tab === "equip" ? "stats" : tab || "stats"; dockSize(2); dockRender(); }
function closeDetail() { DOCK.tab = "plan"; DOCK.unit = null; dockSize(1); dockRender(); }
// press and hold on a unit (map token or strip chip): its Inspector
function inspect(id) { DOCK.unit = id; openDetail("stats"); }
function tabBody(u) {
  if (DOCK.tab === "weapons") return weaponsTab(u);
  if (DOCK.tab === "armor") return armorTab(u);
  return statsTab(u);
}
const rangeText = (r) => (r ? `${r.min ?? "-"}/${r.short}/${r.medium}/${r.long}` : "?");
const dmgText = (w) => (w.damage ? w.damage : w.rack ? w.rack + " msl" : "-");
function weaponsTab(u) {
  const list = S.wlist[u.id] || [];
  if (!list.length) return '<div class="msg">No weapons listed.</div>';
  return `<table class="wt"><tr><th>Weapon</th><th>Loc</th><th>Dmg</th><th>Heat</th><th title="minimum / short / medium / long">Min/S/M/L</th></tr>${list.map((w) => `<tr><td>${esc(w.name)}${w.rear ? " (rear)" : ""}</td><td>${esc([].concat(w.loc || []).map((l) => LOCAB[l] || l).join("/"))}</td><td>${esc(dmgText(w))}</td><td>${w.heat ?? ""}</td><td>${rangeText(w.ranges)}</td></tr>`).join("")}</table>${u.team === S.myTeam ? '<div class="msg">Modes and ammunition are set in the weapon panel during the fire phase.</div>' : '<div class="msg">An enemy unit: read only.</div>'}`;
}
function statsTab(u) {
  const names = S.critNames[u.id] || {}, alive = u.crit_alive || {};
  const crits = Object.keys(names).map((loc) => `<div><b>${LOCAB[loc] || loc}</b></div><div class="crit">${names[loc].map((n, i) => `<span class="${alive[loc] && alive[loc][i] === false ? "x" : ""}">${esc(n)}</span>`).join("")}</div>`).join("");
  return `<div class="msg">${u.tons || "?"} tons &middot; gunnery ${u.gunnery} / piloting ${u.piloting} &middot; pilot hits ${u.pilot_hits} &middot; facing ${u.facing} &middot; last move ${esc(u.move_mode || "none")}</div>${equipBody(u)}<h3 style="margin:8px 0 4px;font-size:13px">Critical slots</h3>${crits}`;
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
// flick the header (or a body scrolled to its top) to make the dock bigger or smaller
(() => {
  let y0 = null, top = false;
  const dock = $("dock");
  dock.addEventListener("touchstart", (e) => { const body = e.target.closest("#dockbody"); top = !body || body.scrollTop <= 0; y0 = e.touches[0].clientY; }, { passive: true });
  dock.addEventListener("touchend", (e) => { if (y0 == null) return; const dy = e.changedTouches[0].clientY - y0; y0 = null; if (Math.abs(dy) < 60) return; if (dy < 0) dockSize(DOCK.size + 1); else if (top) dockSize(DOCK.size - 1); }, { passive: true });
  $("dockup").onclick = () => dockSize(DOCK.size + 1); $("dockdn").onclick = () => dockSize(DOCK.size - 1);
})();
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
  if (r.error) { $("tabbody").insertAdjacentHTML("afterbegin", `<div class="err">${esc(r.error)}</div>`); return null; }
  const u = unit(id); if (u) u.equipment = r.equipment;
  if (S.req && S.req.kind === "end_phase") S.req.equipment = r.equipment;
  if (DOCK.tab !== "plan") dockRender();
  if (S.req && S.req.kind === "end_phase") HANDLERS.end_phase(S.req);
  return r.equipment;
}

// ---------------------------------------------------------------- clicks
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-act]");
  if (t && t.dataset.hold && e.detail > 0) return; // Move! is a long press; only a keyboard activation (no click count) commits at once
  if (t && !(t.tagName === "INPUT" && t.type === "checkbox")) { act(t); return; }
  const chip = e.target.closest(".chip,.echip"); if (chip) { const id = +chip.dataset.u; DOCK.unit = null; if (setTcur(id)) return; if (S.req && S.req.kind === "move_order" && S.cands.includes(id)) { selectMover(id); return; } if (moving() && S.mv.attacks.some((a) => a.target === id)) { onUnitTap(id); return; } S.sel = id; redraw(); if (DOCK.tab !== "plan") dockRender(); return; }
  const un = e.target.closest("[data-unit]"); if (un && setTcur(+un.dataset.unit)) return; if (un && !(S.req && S.req.kind === "target" && S.req.enemies.some((x) => x.id === +un.dataset.unit))) { onUnitTap(+un.dataset.unit); return; }
  if (!e.target.closest("#menu") && !e.target.closest("#menu-btn")) $("menu").style.display = "none";
});
// press and hold on a strip chip (your units, the enemy bar): that unit's Inspector; the click that ends the hold does nothing more
(() => {
  let t = null, held = false, at = null;
  document.addEventListener("pointerdown", (e) => {
    const c = e.target.closest(".chip,.echip"); if (!c) return;
    held = false; at = [e.clientX, e.clientY]; clearTimeout(t);
    t = setTimeout(() => { t = null; held = true; inspect(+c.dataset.u); }, 650);
  });
  document.addEventListener("pointermove", (e) => { if (t && at && Math.hypot(e.clientX - at[0], e.clientY - at[1]) > HOLD_SLOP) { clearTimeout(t); t = null; } });
  ["pointerup", "pointercancel"].forEach((n) => document.addEventListener(n, () => { clearTimeout(t); t = null; }));
  document.addEventListener("click", (e) => { if (held && e.target.closest(".chip,.echip")) { held = false; e.stopPropagation(); e.preventDefault(); } }, true);
})();
document.addEventListener("change", (e) => { const t = e.target; if (t.dataset && t.dataset.act === "fire") { t.checked ? S.decl.sel.add(+t.dataset.id) : S.decl.sel.delete(+t.dataset.id); declSheet(); redraw(); } else if (t.dataset && t.dataset.act === "sw-unjam") { sendUnjam(); } });
function sendUnjam() { const names = [...document.querySelectorAll('[data-act="sw-unjam"]')].filter((c) => c.checked).map((c) => c.dataset.name); setSwitch({ unjam: names }, S.req ? S.req.unit : S.sel); }
function refreshPanel() { if (S.decl) declSheet(); }
const tnPill_unused = 0;
function act(t) {
  const d = t.dataset, a = d.act, D = S.decl, r = S.req;
  switch (a) {
    case "report-close": closeReport(); break;
    case "hazard-ok": $("card").style.display = "none"; S.hazardOk = true; doCommit(); break;
    case "card-close": $("card").style.display = "none"; break;
    case "pick-unit": send({ unit: +d.id }); break;
    case "stand": send({ stand: d.v === "1" }); break;
    case "stand-plan": standPlan(); break;
    // EJECT (TO:AR p.164-165; engine pass 2026-11-24): instead of moving; asked again on a card, as it cannot be undone
    case "eject-ask": showCard(`<b>Eject?</b><div class="msg">The MechWarrior ejects instead of moving and lands behind the 'Mech (a piloting roll; a hard landing costs hits). The 'Mech is abandoned and out of the battle. This cannot be undone.</div><div class="row"><button class="go" data-act="eject-go">Eject</button><button data-act="card-close">Stay in the cockpit</button></div>`); break;
    case "eject-go": $("card").style.display = "none"; if (S.req && S.req.kind === "movement") send({ eject: true }); break;
    case "jump-toggle": if (S.mv) { S.jumpPref[S.mv.unit] = !jumpOn(); S.reachIdx = null; S.dest = null; S.way = []; S.wrIdx = null; S.path = null; S.attackSel = null; moveIntro(); redraw(); } break;
    case "drop": S.drop = !S.drop; if (S.dest) moveSheet(); else moveIntro(); break;
    case "prone-plan": pronePlan(); break;
    case "prone-go": if (S.prone) send(S.prone.facing ? { stand: false, facing: S.prone.facing } : { stand: false }); break;
    case "boost": send({ use: d.v === "1" }); break;
    case "spot": send({ target: d.id === "" ? null : +d.id, fires: true }); break;
    case "tag": send(d.id === "" ? { target: null } : { target: +d.id, aim: d.aim }); break;
    case "target": send({ target: d.id === "" ? null : +d.id }); break;
    case "look": selectMover(+d.id); break;
    case "place": if (S.dp && S.dp.hex) send({ hex: S.dp.hex, facing: S.dp.facing }); break;
    case "undo": undo(); break;
    case "mode": S.mode = d.m; { const os = destOpts().filter((x) => x.mode === S.mode); if (!os.some((x) => x.facing === S.facing)) S.facing = os[0].facing; } moveSheet(); redraw(); loadPath(); break;
    case "commit": doCommit(); break;
    case "atk": chooseAttack(S.mv.attacks.filter((x) => x.target === S.attackTarget)[+d.i]); break;
    case "atk-yes": commitMove({ attack: S.attackSel }); break;
    case "atk-no": S.attackSel = null; S.attackConfirm = false; S.path = null; attackSheet(S.mv.attacks.filter((x) => x.target === S.attackTarget)); redraw(); break;
    case "focus": { const g = D.groups[+d.g]; if (g) { D.focus = g.rep.id; refreshPanel(); redraw(); } break; }
    case "tn": { const w = D && D.rows.find((x) => x.id === +d.w); if (w) tnCard(D.req, w); break; }
    case "tgt-prev": cycleTcur(-1); break;
    case "tgt-next": cycleTcur(1); break;
    case "look-target": setTcur(+d.id); break;
    case "mode-w": { const g = D.groups[+d.g], w = g.rep, i = w.modes.findIndex((m) => m.selected), next = w.modes[(i + 1) % w.modes.length]; setWeapons({ modes: Object.fromEntries(g.members.map((m) => [m.id, next.label])) }); break; }
    case "rate-w": { const g = D.groups[+d.g], w = g.rep, i = w.rates.findIndex((m) => m.selected), next = w.rates[(i + 1) % w.rates.length]; setWeapons({ shots: Object.fromEntries(g.members.map((m) => [m.id, next.shots])) }); break; }
    case "charge-w": { const g = D.groups[+d.g], w = g.rep; D.charge.has(w.name) ? D.charge.delete(w.name) : (D.charge.add(w.name), D.rows.filter((x) => x.name === w.name).forEach((x) => D.sel.delete(x.id))); setWeapons({}); break; }
    case "bins-w": D.bin = D.bin === +d.g ? null : +d.g; declSheet(); break;
    case "bin-pick": { const g = D.groups[+d.g]; D.bin = null; setWeapons({ bins: Object.fromEntries(g.members.map((m) => [m.id, d.b === "" ? null : +d.b])) }); break; }
    case "assign": { const g = D.groups[+d.g]; const free = g.members.find((m) => !D.sel.has(m.id)); if (free) D.sel.add(free.id); else g.members.forEach((m) => D.sel.delete(m.id)); declSheet(); redraw(); break; }
    case "strike": strikePick(D.strike % 2); D.strike++; declSheet(); redraw(); break;
    case "sort": { const i = SORTS.findIndex((x) => x[0] === O.sort); O.sort = SORTS[(i + 1) % SORTS.length][0]; setPref("sort", O.sort); refreshPanel(); break; }
    case "group": O.group = !O.group; setPref("group", O.group ? "1" : "0"); declSheet(); break;
    case "aim-w": D.aimFor = D.aimFor ? null : +d.id; declSheet(); redraw(); break;
    case "clear": if (S.fire) { S.fire.assign.clear(); S.fire.order = []; S.fire.lastPrimary = null; D.sel.clear(); fireRebuild(); break; } D.sel.clear(); declSheet(); redraw(); break;
    case "hold": if (S.fire) send({ target: null }); else send({ weapons: [] }); break;
    case "fire-go": if (S.fire) { fireGo(); break; } { const aim = {}; for (const [k, v] of Object.entries(D.aim)) aim[k] = v; send({ weapons: [...D.sel], charge: [...D.charge], aim }); break; }
    case "phys": send({ kind: d.k === "" ? null : d.k }); break;
    case "end-go": send({}); break;
    case "detail": openDetail("stats"); break;
    case "detail-close": closeDetail(); break;
    case "tab": dockTab(d.t); break;
    case "sw-cool": setSwitch({ coolant: d.v }); break;
    case "sw-rad": setSwitch({ radical: d.v === "1" }); break;
    case "sw-boost": setSwitch({ boost: d.v === "1" }); break;
    case "sw-blue": setSwitch({ blue_shield: d.v === "1" }); break;
    case "sw-power": setSwitch({ power: d.v || null }); break;
    case "sw-ams": { const u = unit(S.sel), off = (eq(u).ams || []).filter((x) => (x.id === +d.id ? !x.off : x.off)).map((x) => x.id); setSwitch({ ams_off: off }); break; }
    case "sw-unjam1": { const u = unit(S.sel), names = (eq(u).jammed || []).filter((x) => (x.name === d.name ? !x.unjam : x.unjam)).map((x) => x.name); setSwitch({ unjam: names }); break; }
    case "sw-cap": { const u = unit(S.sel), names = (eq(u).capacitors || []).filter((x) => (x.name === d.name ? !x.charge : x.charge)).map((x) => x.name); setSwitch({ charge: names }); break; }
    case "sw-sinks": { const u = unit(S.sel), e = eq(u); if (d.d === "auto") setSwitch({ sinks_off: null }); else setSwitch({ sinks_off: Math.max(0, Math.min(e.sinks.working, e.sinks.off + +d.d)) }); break; }
    case "menu-folder": { const sub = document.querySelector(`#menu .sub[data-f="${d.f}"]`); if (sub) sub.classList.toggle("open"); break; }
    case "look": O.look = d.v; setPref("look", d.v); applyLook(); buildMenu(); break;
    case "cvd": O.cvd = !O.cvd; setPref("cvd", O.cvd ? "1" : "0"); buildMenu(); redraw(); if (moving()) { if (S.dest) moveSheet(); } if (S.decl) declSheet(); break;
    case "atk": O.atk = !O.atk; setPref("atk", O.atk ? "1" : "0"); buildMenu(); redraw(); break;
    case "dice": O.dice = !O.dice; setPref("dice", O.dice ? "1" : "0"); buildMenu(); if ($("report").firstChild) renderReport(); break;
    case "rings": O.rings = !O.rings; setPref("rings", O.rings ? "1" : "0"); buildMenu(); redraw(); break;
    case "labels": O.labels = !O.labels; setPref("labels", O.labels ? "1" : "0"); buildMenu(); if (S.board) { buildMap(); redraw(); } break;
    case "view3d": { $("menu").style.display = "none"; const want = MV.mode === "3d" ? "top" : "3d";
      MV.setMode(want).then((got) => { setPref("view", got); buildMenu(); if (want === "3d" && got !== "3d") showCard("<b>The tabletop view needs WebGL</b><div class=\"msg\">This browser or device could not start it, so the flat map stays.</div>"); }); break; }
    case "report": toggleReport(); $("menu").style.display = "none"; break;
    case "lab": location.href = "index.html"; break;
    case "get-results": getResults(); break;
  }
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if ($("report").style.display === "block") { closeReport(); return; } if ($("card").style.display === "block") { $("card").style.display = "none"; return; } undo(); } });

// ---------------------------------------------------------------- the end, the menu, the look
function finish(end) {
  S.over = true; S.units = end.units; S.req = null; S.decl = null;
  if (end.log) feedLog(end.log);
  releaseLog("over");
  setPhase("Battle over");
  redraw();
  sheet(`<h3>Battle over</h3><div class="msg">${end.winner === "Draw" ? "A draw" : esc(end.winner) + " wins"} after ${end.turns} turns. ${end.decisions} decisions recorded.</div><div class="row"><button data-act="report">Show the report</button><button data-act="lab">Back to the Lab</button></div>`);
  // GET RESULTS (bug B21): the commit button becomes Get Results, which opens the Lab's Results tab with this battle's statistics
  S.end = end;
  const c = $("cluster"); c.style.display = "flex";
  c.innerHTML = `<div class="readout"><b>Battle over</b><br><span>${end.winner === "Draw" ? "a draw" : esc(end.winner) + " wins"}</span></div><button class="go big" data-act="get-results">Get Results</button>`;
}
// the finished game as a one-battle run file for the Lab (lab.js openPlayedGame); the setup is the one the Lab handed over
function getResults() {
  const end = S.end; if (!end || !end.line) return;
  let setup = S.setup || null; if (!setup) try { setup = JSON.parse(localStorage.getItem("bm_play_setup") || "null"); } catch (e) { setup = null; }
  if (!setup) { showCard('<b>Get Results</b><div class="msg">This game was not started from this browser\'s Lab, so its setup is not here to open the results with.</div>'); return; }
  // a run's setup names bots only: the person's team is filed under the default bot (the statistics come from the battle line; a replay
  // opened from the Results tab would be the bots' battle, not this game: recording the person's game is the saved-game work, P2 / P11)
  const teams = (setup.teams || []).map((t) => (t.bot === "human" ? { ...t, bot: "gladiator" } : t));
  const file = { combatlab_run: 1, played: true, setup: { ...setup, teams, battles: 1, seed: +end.seed || setup.seed || 1 }, lines: [end.line], crashed: [], seconds: 0, unit_files: {} };
  try { localStorage.setItem("bm_play_result", JSON.stringify(file)); } catch (e) { showCard('<b>Get Results</b><div class="msg">This browser will not let the page hand the results over (storage is off).</div>'); return; }
  location.href = "index.html";
}
// ---------------------------------------------------------------- the report (Daniel, 2026-11-22)
// It must not give anything away early: bot reasoning is never shown; a movement line appears once that unit has moved; everything about the
// firing, physical and heat phases waits until that phase is over (the first question of a later phase). The report is a pop-up over every
// screen and button until it is closed; after the firing phase a combat report opens by itself.
// "tag" (bug B16, Daniel 2026-11-22: "since TAG is used in its own sub phase it would be reported before the ranged attack phase
// begins"): a TAG attack is resolved before any weapon is declared (Core p.200), so its lines are shown as soon as they come.
const SEC = { move: 0, ranged: 1, phys: 2, heat: 3, tag: -1 };
const GROUP = { deploy: 0, move_order: 0, movement: 0, stand_up: 0, boost: 0, spot: 1, tag: 1, target: 1, declaration: 1, physical: 2, end_phase: 3, over: 9 };
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
}
function closeReport() { $("report").style.display = "none"; }
function toggleReport() { const r = $("report"); if (r.style.display === "block") closeReport(); else openReport(false); }
function applyLook() { document.documentElement.setAttribute("data-theme", O.look); document.body.setAttribute("data-theme", O.look); }
function buildMenu() {
  const m = $("menu");
  const item = (label, act, extra, on) => `<div class="item ${on ? "on" : ""}" data-act="${act}" ${extra || ""}>${label}</div>`;
  m.innerHTML = `<div class="f" data-act="menu-folder" data-f="look">Look &#9656;</div><div class="sub open" data-f="look">${Object.entries(LOOKS).map(([k, n]) => item(n, "look", `data-v="${k}"`, O.look === k)).join("")}</div>
    <div class="f" data-act="menu-folder" data-f="view">View &#9656;</div><div class="sub open" data-f="view">${item("Colour-blind mode", "cvd", "", O.cvd)}${item("Range bands for the weapon", "rings", "", O.rings)}${item("Hex numbers", "labels", "", O.labels)}${item("Dice details in the report", "dice", "", O.dice)}${item("Attack lines (the latest turn)", "atk", "", O.atk)}${item("Tabletop view (preview)", "view3d", "", MV.mode === "3d")}</div>
    <div class="f" data-act="menu-folder" data-f="game">Game &#9656;</div><div class="sub open" data-f="game">${item("Report", "report")}${item("Back to the Lab", "lab")}</div>`;
}
$("menu-btn").onclick = () => { buildMenu(); const m = $("menu"); m.style.display = m.style.display === "block" ? "none" : "block"; };
$("rep-btn").onclick = toggleReport;
$("rec-btn").onclick = () => showCard("<b>REC: timeline and branching</b><div class=\"msg\">Not built yet. It will record the battle so you can step back to an earlier phase and branch from it.</div>");
$("det-btn").onclick = () => { if (DOCK.size === 2) closeDetail(); else openDetail("stats"); };
window.addEventListener("resize", () => { if (S.board) fit(); });
applyLook(); dockSize(+pref("dock", "1")); dockRender();
// THE TABLETOP VIEW (P10, build step 2: a board preview, no units yet): chosen in the Menu, remembered on this device, or forced with ?view=3d / ?view=top
$("ztilt").onclick = () => MV.cycleTilt();
{ const want = qs.get("view") || pref("view", "top"); if (want === "3d") MV.setMode("3d").then((got) => { if (got !== "3d") { setPref("view", "top"); showCard("<b>The tabletop view needs WebGL</b><div class=\"msg\">This browser or device could not start it, so the flat map stays.</div>"); } buildMenu(); }); }
// The browser build has no server to start the game: the Lab page left the setup for this page (localStorage), which
// starts the battle in its own worker. The desktop Lab starts it itself and passes ?game=N.
async function boot() {
  if (!GAME && window.LAB_WASM) {
    let setup = null;
    try { setup = JSON.parse(localStorage.getItem("bm_play_setup") || "null"); localStorage.removeItem("bm_play_setup"); } catch (e) { /* storage off */ }
    if (setup) {
      S.setup = setup;   // kept for Get Results (the stored copy is used up here so a reload does not start a second battle)
      $("info").textContent = "Starting the battle...";
      const r = await api("play_start", { setup });
      if (r.error) { setPhase("could not start"); $("info").textContent = r.error; return; }
      GAME = r.game; COLOURS = r.colours || {};
    }
  }
  if (!GAME) { $("info").textContent = "No game: start one from the Lab (set a team to Human, then Play)."; } else { loop(); }
}
boot();
window.__bm = S;
