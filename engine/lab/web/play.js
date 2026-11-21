"use strict";
// BATTLEROM play page (first playable slice). Talks to the Combat Lab server: play_poll / play_answer (engine/core/src/play_session.rs).
// One question at a time: the engine waits; this page shows what it asks (move order, move, target, weapons, physical) and sends the answer.
const $ = (id) => document.getElementById(id);
const qs = new URLSearchParams(location.search);
const GAME = +qs.get("game");
let COLOURS = {};
try { COLOURS = JSON.parse(qs.get("colours") || "{}"); } catch (e) { /* default colours */ }
const R = 34, SQ3 = Math.sqrt(3);
const NS = "http://www.w3.org/2000/svg";
const FACINGS = ["N", "NE", "SE", "S", "SW", "NW"];
const DIR = { N: [0, -1], NE: [SQ3 / 2, -0.5], SE: [SQ3 / 2, 0.5], S: [0, 1], SW: [-SQ3 / 2, 0.5], NW: [-SQ3 / 2, -0.5] };
const MODE_COL = { Walk: "#00e5ff", Run: "#ffd400", Jump: "#ff7a3c", "Stand Still": "#9aa" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const S = { seq: 0, req: null, board: null, units: [], max: {}, sel: null, dest: null, facing: null, mode: null, view: { x: 0, y: 0, k: 1 }, log: [], weapons: new Set(), target: null, over: false };
const svg = $("map");
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };

async function api(name, body) {
  const r = await fetch("api/" + name, { method: "POST", body: JSON.stringify({ game: GAME, ...body }) });
  return r.json();
}

// ---------------------------------------------------------------- geometry (flat-topped hexes, even columns half a hex lower, N up)
const parse = (l) => [parseInt(l.slice(0, 2), 10), parseInt(l.slice(2), 10)];
const centre = (l) => { const [c, r] = parse(l); return [R + (c - 1) * 1.5 * R, (SQ3 / 2) * R + (r - 1) * SQ3 * R + (c % 2 === 0 ? (SQ3 / 2) * R : 0)]; };
const pts = (cx, cy, k = 1) => [0, 1, 2, 3, 4, 5].map((i) => `${(cx + R * k * Math.cos(Math.PI / 3 * i)).toFixed(1)},${(cy + R * k * Math.sin(Math.PI / 3 * i)).toFixed(1)}`).join(" ");
const hexName = (c, r) => String(c).padStart(2, "0") + String(r).padStart(2, "0");
// neighbours in the order of polygon edges 0..5 (SE, S, SW, NW, N, NE)
function neighbours(l) {
  const [c, r] = parse(l), low = c % 2 === 0;
  return [hexName(c + 1, r + (low ? 1 : 0)), hexName(c, r + 1), hexName(c - 1, r + (low ? 1 : 0)), hexName(c - 1, r + (low ? 0 : -1)), hexName(c, r - 1), hexName(c + 1, r + (low ? 0 : -1))];
}

// ---------------------------------------------------------------- map
let gMap, gDyn;
function buildMap() {
  svg.innerHTML = "";
  const W = S.board.width, H = S.board.height;
  S.bounds = [0, 0, R * 2 + (W - 1) * 1.5 * R, SQ3 * R * H + (SQ3 / 2) * R];
  gMap = el("g", {}, svg); gDyn = el("g", {}, svg);
  for (const label of Object.keys(S.board.hexes).sort()) {
    const h = S.board.hexes[label], f = h.f || {}, [x, y] = centre(label);
    let fill = "#39402f";
    const trees = f.woods || f.jungle;
    if (f.road || f.pavement) fill = "#3a3b35";
    if (f.rough || f.rubble) fill = "#4b4535";
    if (trees) fill = String(trees) === "1" ? "#2f4a2b" : "#26402a";
    if (f.water && String(f.water) !== "0") fill = "#2a4a66";
    if (h.b) fill = "#55504a";
    const g = el("g", { "data-hex": label }, gMap);
    el("polygon", { points: pts(x, y), fill, stroke: "#1b2117", "stroke-width": h.l ? 1.8 : 0.8 }, g);
    const t = el("text", { x, y: y - R * 0.55, "text-anchor": "middle", "font-size": 8, fill: "#cfd8c4", "fill-opacity": ".55", "font-family": "ui-monospace,monospace" }, g); t.textContent = label;
    if (h.l) { const lv = el("text", { x, y: y + R * 0.72, "text-anchor": "middle", "font-size": 9, fill: "#e0e6d8", "font-weight": 600 }, g); lv.textContent = "L" + h.l; }
    if (trees) { const w = el("text", { x, y: y + 3, "text-anchor": "middle", "font-size": 14, fill: "#7fb27f", "fill-opacity": ".7" }, g); w.textContent = "♣"; }
  }
  fit();
}
function applyView() { svg.setAttribute("viewBox", `${S.view.x} ${S.view.y} ${S.view.w} ${S.view.h}`); }
function fit() {
  const b = S.bounds, r = svg.getBoundingClientRect(), ar = (r.width || 1) / (r.height || 1);
  let w = b[2] + 8, h = b[3] + 8;
  if (w / h < ar) w = h * ar; else h = w / ar;
  S.view = { x: b[0] - 4 - (w - b[2] - 8) / 2, y: b[1] - 4 - (h - b[3] - 8) / 2, w, h };
  applyView();
}
function zoom(f, cx, cy) {
  const v = S.view, r = svg.getBoundingClientRect();
  const px = cx == null ? 0.5 : (cx - r.left) / r.width, py = cy == null ? 0.5 : (cy - r.top) / r.height;
  const nw = Math.max(120, Math.min(S.bounds[2] * 3, v.w * f)), nh = nw * v.h / v.w;
  S.view = { x: v.x + (v.w - nw) * px, y: v.y + (v.h - nh) * py, w: nw, h: nh };
  applyView();
}
// drag to pan, wheel / pinch to zoom
(() => {
  const ptrs = new Map(); let moved = false, lastDist = 0;
  svg.addEventListener("pointerdown", (e) => { ptrs.set(e.pointerId, [e.clientX, e.clientY]); moved = false; lastDist = 0; });
  svg.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId)) return;
    const prev = ptrs.get(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    const r = svg.getBoundingClientRect();
    if (ptrs.size === 1) {
      const dx = e.clientX - prev[0], dy = e.clientY - prev[1];
      if (Math.abs(dx) + Math.abs(dy) > 0) moved = moved || Math.abs(dx) + Math.abs(dy) > 2;
      S.view.x -= dx * S.view.w / r.width; S.view.y -= dy * S.view.h / r.height; applyView();
    } else if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      if (lastDist) zoom(lastDist / d, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      lastDist = d; moved = true;
    }
  });
  const up = (e) => { ptrs.delete(e.pointerId); lastDist = 0; };
  svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", up);
  svg.addEventListener("click", (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  svg.addEventListener("wheel", (e) => { e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, { passive: false });
})();
$("zin").onclick = () => zoom(1 / 1.3); $("zout").onclick = () => zoom(1.3); $("zfit").onclick = fit;

// ---------------------------------------------------------------- units
const teamColour = (u) => COLOURS[u.team] || (u.team === S.myTeam ? "#4b8fd8" : "#d86a4b");
const short = (u) => String(u.mech || u.name || "").split(/\s+/)[0].slice(0, 7);
function fracOf(u) {
  const m = S.max[u.id] || (S.max[u.id] = { hp: Math.max(1, u.hp) });
  return Math.max(0, Math.min(1, u.hp / m.hp));
}
function drawUnits(layer) {
  for (const u of S.units) {
    if (!u.hex || u.destroyed) continue;
    const [x, y] = centre(u.hex), col = teamColour(u);
    const g = el("g", { "data-unit": u.id, style: "cursor:pointer" }, layer);
    el("polygon", { points: pts(x, y, 0.8), fill: col, "fill-opacity": ".55", stroke: S.sel === u.id ? "#fff" : col, "stroke-width": S.sel === u.id ? 2.5 : 1.5 }, g);
    const d = DIR[u.facing] || DIR.N;
    el("polygon", { points: `${x + d[0] * R * 0.78},${y + d[1] * R * 0.78} ${x + d[0] * R * 0.5 - d[1] * 5},${y + d[1] * R * 0.5 + d[0] * 5} ${x + d[0] * R * 0.5 + d[1] * 5},${y + d[1] * R * 0.5 - d[0] * 5}`, fill: "#fff" }, g);
    const t = el("text", { x, y: y + 4, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: "#fff", stroke: "#000", "stroke-width": 0.4 }, g); t.textContent = short(u);
    // armour + structure bar and heat bar (below the token)
    const f = fracOf(u);
    el("rect", { x: x - 18, y: y + R * 0.52, width: 36, height: 4, fill: "#0c0f13" }, g);
    el("rect", { x: x - 18, y: y + R * 0.52, width: 36 * f, height: 4, fill: f > 0.5 ? "#6fbf86" : f > 0.25 ? "#dba94a" : "#e07468" }, g);
    el("rect", { x: x - 18, y: y + R * 0.52 + 5, width: 36, height: 3, fill: "#0c0f13" }, g);
    el("rect", { x: x - 18, y: y + R * 0.52 + 5, width: 36 * Math.min(1, u.heat / 30), height: 3, fill: "#ff7a3c" }, g);
    if (u.prone) { const p = el("text", { x: x + 20, y: y - 14, "font-size": 9, fill: "#ffd400", "font-weight": 700 }, g); p.textContent = "PRONE"; }
    if (u.shutdown) { const p = el("text", { x: x + 20, y: y - 4, "font-size": 9, fill: "#e07468", "font-weight": 700 }, g); p.textContent = "OFF"; }
  }
}
function renderStrip() {
  $("strip").innerHTML = S.units.map((u) => `<div class="chip${u.destroyed ? " dead" : ""}${S.sel === u.id ? " sel" : ""}" data-u="${u.id}"><i style="background:${teamColour(u)}"></i>${esc(u.name)} <span class="msg">${esc(u.mech || "")}</span><span class="bar" title="armour and structure left"><b style="width:${Math.round(fracOf(u) * 100)}%"></b></span>${u.heat ? `<span class="warnt">${u.heat}H</span>` : ""}${u.shutdown ? '<span class="err">OFF</span>' : ""}${u.prone ? "<span>PRONE</span>" : ""}</div>`).join("");
}
function infoBar() {
  const u = S.units.find((x) => x.id === S.sel);
  if (!u) { $("info").textContent = "Tap a unit for its details."; return; }
  const AB = { "Head": "H", "Center Torso": "CT", "Left Torso": "LT", "Right Torso": "RT", "Left Arm": "LA", "Right Arm": "RA", "Left Leg": "LL", "Right Leg": "RL" };
  const locs = Object.entries(u.locs || {}).map(([k, v]) => `${AB[k] || k} ${v[3] ? "gone" : v[0] + (v[1] ? "(" + v[1] + ")" : "") + "/" + v[2]}`).join(" \u00b7 ");
  $("info").innerHTML = `<b>${esc(u.name)}</b> ${esc(u.mech || "")} ${u.tons || ""}t &middot; walk ${u.walk} run ${u.run}${u.jump ? " jump " + u.jump : ""} &middot; heat ${u.heat} &middot; facing ${u.facing} &middot; pilot hits ${u.pilot_hits}<br><span style="font-size:11px" title="armour (rear) / structure">${esc(locs)}</span>`;
}
document.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip"); if (chip) { S.sel = +chip.dataset.u; redraw(); return; }
  const un = e.target.closest("[data-unit]"); if (un && !(S.req && S.req.kind === "target" && S.req.enemies.some((x) => x.id === +un.dataset.unit))) { onUnitTap(+un.dataset.unit); return; }
});

// ---------------------------------------------------------------- the questions
function redraw() {
  gDyn.innerHTML = "";
  const r = S.req;
  if (r && r.kind === "movement") drawReach(gDyn);
  if (r && r.kind === "target") drawTargets(gDyn);
  drawUnits(gDyn);
  if (r && r.kind === "movement") drawDest(gDyn);
  renderStrip(); infoBar();
}
function setPhase(t) { $("phase").textContent = t; }
function sheet(html) { $("sheet").innerHTML = html; }
async function send(answer) {
  const seq = S.seq; S.req = null; sheet('<div class="msg">Working...</div>');
  const r = await api("play_answer", { seq, answer });
  if (r.error) { sheet(`<div class="err">${esc(r.error)}</div>`); }
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
function take(r) {
  S.req = r; S.units = r.units;
  if (r.board && !S.board) { S.board = r.board; buildMap(); }
  if (r.log && r.log.length) { S.log.push(...r.log); $("report").textContent = S.log.join("\n"); }
  const mine = S.units.find((u) => u.id === (r.unit ?? (r.candidates || [])[0]));
  if (mine && !S.myTeam) S.myTeam = mine.team;
  if (r.unit != null) S.sel = r.unit;
  S.dest = null; S.facing = null; S.mode = null; S.weapons = new Set(); S.target = null;
  const turn = (S.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1];
  const phase = { move_order: "Movement", movement: "Movement", target: "Ranged attacks", declaration: "Ranged attacks", physical: "Physical attacks" }[r.kind];
  setPhase(`Turn ${turn || "?"} · ${phase}`);
  ({ move_order: askOrder, movement: askMove, target: askTarget, declaration: askDecl, physical: askPhys }[r.kind])(r);
  redraw();
}
function errLine(r) { return r.error ? `<div class="err">${esc(r.error)}</div>` : ""; }

// movement order: pick a unit
function askOrder(r) {
  sheet(`<h3>Choose a unit to move</h3><div class="msg">Tap one of your units that has not moved yet.</div><div class="row">${r.candidates.map((id) => { const u = S.units.find((x) => x.id === id); return `<button data-pick="${id}">${esc(u.name)}</button>`; }).join("")}</div>`);
  S.sel = r.candidates[0];
}
function onUnitTap(id) {
  S.sel = id;
  if (S.req && S.req.kind === "move_order" && S.req.candidates.includes(id)) { send({ unit: id }); return; }
  redraw();
}
$("sheet").addEventListener("click", (e) => { const b = e.target.closest("[data-pick]"); if (b) send({ unit: +b.dataset.pick }); });

// movement
function reachIndex(r) {
  const byHex = {};
  for (const o of r.options) (byHex[o.hex] = byHex[o.hex] || []).push(o);
  return byHex;
}
function drawReach(layer) {
  const idx = S.reachIdx || (S.reachIdx = reachIndex(S.req));
  const sets = { Walk: new Set(), Run: new Set(), Jump: new Set() };
  for (const [h, os] of Object.entries(idx)) for (const o of os) if (sets[o.mode]) sets[o.mode].add(h);
  for (const mode of ["Jump", "Run", "Walk"]) {
    const col = MODE_COL[mode];
    for (const h of sets[mode]) { const [x, y] = centre(h); el("polygon", { points: pts(x, y, 0.96), fill: col, "fill-opacity": mode === "Walk" ? ".22" : ".14", "pointer-events": "none" }, layer); }
    // only the outer border of each mode's reach (MegaMek's look)
    for (const h of sets[mode]) {
      const [x, y] = centre(h), nb = neighbours(h);
      nb.forEach((n, i) => {
        if (sets[mode].has(n)) return;
        const a = Math.PI / 3 * i, b = Math.PI / 3 * (i + 1);
        el("line", { x1: x + R * Math.cos(a), y1: y + R * Math.sin(a), x2: x + R * Math.cos(b), y2: y + R * Math.sin(b), stroke: col, "stroke-width": 2.4, "pointer-events": "none" }, layer);
      });
    }
  }
  // clickable hexes
  for (const h of Object.keys(idx)) { const [x, y] = centre(h); const p = el("polygon", { points: pts(x, y), fill: "transparent", "data-reach": h, style: "cursor:pointer" }, layer); p.addEventListener("click", () => pickDest(h)); }
}
function pickDest(h) {
  const os = S.reachIdx[h]; if (!os) return;
  const cheapest = os.reduce((a, b) => (a.mp <= b.mp ? a : b));
  S.dest = h; S.mode = cheapest.mode; S.facing = null;
  const same = os.filter((o) => o.mode === S.mode);
  const cur = S.units.find((u) => u.id === S.req.unit);
  S.facing = (same.find((o) => cur && o.facing === cur.facing) || same[0]).facing;
  moveSheet(); redraw();
}
function optNow() { const os = (S.reachIdx || {})[S.dest] || []; return os.find((o) => o.mode === S.mode && o.facing === S.facing); }
function drawDest(layer) {
  if (!S.dest) return;
  const os = S.reachIdx[S.dest].filter((o) => o.mode === S.mode), [x, y] = centre(S.dest);
  el("polygon", { points: pts(x, y, 0.98), fill: "none", stroke: MODE_COL[S.mode], "stroke-width": 3, "pointer-events": "none" }, layer);
  for (const o of os) {
    const d = DIR[o.facing], sel = o.facing === S.facing;
    const ax = x + d[0] * R * 1.12, ay = y + d[1] * R * 1.12;
    const g = el("g", { style: "cursor:pointer" }, layer);
    el("circle", { cx: ax, cy: ay, r: 11, fill: sel ? MODE_COL[S.mode] : "#252c35", stroke: MODE_COL[S.mode], "stroke-width": 1.5, "fill-opacity": sel ? 1 : .85 }, g);
    el("polygon", { points: `${ax + d[0] * 7},${ay + d[1] * 7} ${ax - d[0] * 4 - d[1] * 5},${ay - d[1] * 4 + d[0] * 5} ${ax - d[0] * 4 + d[1] * 5},${ay - d[1] * 4 - d[0] * 5}`, fill: sel ? "#101418" : MODE_COL[S.mode] }, g);
    g.addEventListener("click", (e) => { e.stopPropagation(); S.facing = o.facing; moveSheet(); redraw(); });
  }
}
function askMove(r) {
  S.reachIdx = null;
  const u = S.units.find((x) => x.id === r.unit);
  sheet(`<h3>Move ${esc(r.name)}</h3>${errLine(r)}<div class="msg">${r.standup_mp != null ? "Prone: moving means standing up first (a piloting roll). " : ""}${r.entry ? "Choose where to enter the map. " : ""}Tap a tinted hex on the map. Cyan = walk (${r.walk} MP), yellow = run (${r.run} MP)${r.jump ? ", orange = jump (" + r.jump + " MP)" : ""}.</div><div class="row"><button id="stay">Stay here</button></div>`);
  $("stay").onclick = () => send({ stay: true });
  S.sel = r.unit;
}
function moveSheet() {
  const os = S.reachIdx[S.dest], modes = [...new Set(os.map((o) => o.mode))];
  const o = optNow() || os[0];
  const warns = [];
  if (o.psrs) warns.push(`${o.psrs} piloting roll${o.psrs > 1 ? "s" : ""} on this path`);
  if (o.hazard) warns.push(`about ${(+o.hazard).toFixed(1)} damage from terrain`);
  if (S.mode === "Run" || S.mode === "Jump") { /* running / jumping adds heat and TMM; the numbers are shown */ }
  sheet(`<h3>${esc(S.req.name)} to ${S.dest}</h3>${errLine(S.req)}
    <div class="row">${modes.map((m) => `<button data-mode="${m}" class="${m === S.mode ? "on" : ""}" style="border-color:${MODE_COL[m]}">${m}</button>`).join("")}</div>
    <div class="msg">${o.mp} MP (turns included) &middot; ${o.hexes} hex${o.hexes === 1 ? "" : "es"} &middot; target movement modifier +${o.tmm} &middot; movement heat ${o.heat}</div>
    ${warns.length ? `<div class="warnt">&#9888; ${warns.join("; ")}</div>` : ""}
    <div class="msg">Tap an arrow around the hex to choose the facing. Esc or Undo clears the choice.</div>
    <div class="row"><button class="go" id="commit">Move</button><button id="undo">Undo</button><button id="stay">Stay here</button></div>`);
  $("sheet").querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => { S.mode = b.dataset.mode; const same = os.filter((x) => x.mode === S.mode); if (!same.some((x) => x.facing === S.facing)) S.facing = same[0].facing; moveSheet(); redraw(); }));
  $("commit").onclick = () => send({ hex: S.dest, facing: S.facing, mode: S.mode });
  $("undo").onclick = undo; $("stay").onclick = () => send({ stay: true });
}
function undo() { if (S.req && S.req.kind === "movement") { S.dest = null; askMove(S.req); redraw(); } }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") undo(); });

// target
function drawTargets(layer) {
  const me = S.units.find((u) => u.id === S.req.unit);
  for (const t of S.req.enemies) {
    const u = S.units.find((x) => x.id === t.id); if (!u || !u.hex) continue;
    const [x, y] = centre(u.hex);
    const p = el("polygon", { points: pts(x, y, 0.95), fill: "#e07468", "fill-opacity": ".22", stroke: "#e07468", "stroke-width": 2.5, style: "cursor:pointer" }, layer);
    p.addEventListener("click", () => send({ target: t.id }));
    if (me && me.hex) { const [mx, my] = centre(me.hex); el("line", { x1: mx, y1: my, x2: x, y2: y, stroke: "#e07468", "stroke-width": 1.5, "stroke-dasharray": "5 4", "pointer-events": "none" }, layer); }
  }
}
function askTarget(r) {
  sheet(`<h3>${esc(r.name)}: choose a target</h3>${errLine(r)}<div class="msg">Tap a red hex, or pick from the list.</div><div class="row">${r.enemies.map((t) => `<button data-t="${t.id}">${esc(t.name)} &middot; range ${t.distance ?? "?"}</button>`).join("")}<button id="hold">Hold fire</button></div>`);
  $("sheet").querySelectorAll("[data-t]").forEach((b) => (b.onclick = () => send({ target: +b.dataset.t })));
  $("hold").onclick = () => send({ target: null });
}

// weapons
function askDecl(r) {
  S.sel = r.unit; S.weapons = new Set();
  declSheet(r);
}
function declSheet(r) {
  const proj = (() => { const sel = r.weapons.filter((w) => S.weapons.has(w.id)); const wh = sel.reduce((a, w) => a + (w.heat || 0), 0), ev = sel.reduce((a, w) => a + (w.ev || 0), 0); return { wh, ev, heat: Math.max(0, r.heat + r.move_heat + wh - r.dissipation) }; })();
  const rows = r.weapons.map((w) => {
    const ok = w.in_range;
    const on = S.weapons.has(w.id);
    return `<tr class="${ok ? (on ? "pick" : "") : "out"}"><td><input type="checkbox" data-w="${w.id}" ${on ? "checked" : ""} ${ok ? "" : "disabled"} aria-label="fire ${esc(w.name)}"></td><td class="w">${esc(w.name)}${w.loc ? ' <span class="msg">' + esc([].concat(w.loc).join("/")) + "</span>" : ""}${w.needs_twist ? ' <span class="msg">(torso twist)</span>' : ""}</td><td>${ok ? "TN " + w.tn : "out of range"}</td><td>${ok ? (+w.ev).toFixed(1) + " dmg" : ""}</td><td>${w.heat ?? ""}${w.heat != null ? "H" : ""}</td><td>${w.range || ""}</td></tr>`;
  }).join("");
  const heatCls = proj.heat >= 14 ? "err" : proj.heat >= 8 ? "warnt" : "";
  sheet(`<h3>${esc(r.name)} fires on ${esc(r.target_name)} &middot; range ${r.distance}</h3>${errLine(r)}
    <table><tr><th></th><th>Weapon</th><th>To hit</th><th>Expected</th><th>Heat</th><th>Band</th></tr>${rows}</table>
    <div class="msg">Selected: ${S.weapons.size} weapon${S.weapons.size === 1 ? "" : "s"}, about ${proj.ev.toFixed(1)} damage. Heat at end of turn about <span class="${heatCls}">${proj.heat}</span> (now ${r.heat}, movement ${r.move_heat}, weapons ${proj.wh}, sinks take off ${r.dissipation}).${proj.heat >= 14 ? " Shutdown risk." : ""}</div>
    <div class="row"><button class="go" id="fire">Fire!</button><button id="alpha">Alpha strike</button><button id="none">Clear</button><button id="holdf">Hold fire</button></div>`);
  $("sheet").querySelectorAll("[data-w]").forEach((c) => (c.onchange = () => { c.checked ? S.weapons.add(+c.dataset.w) : S.weapons.delete(+c.dataset.w); declSheet(r); }));
  $("fire").onclick = () => send({ weapons: [...S.weapons] });
  $("alpha").onclick = () => { r.weapons.forEach((w) => { if (w.in_range) S.weapons.add(w.id); }); declSheet(r); };
  $("none").onclick = () => { S.weapons.clear(); declSheet(r); };
  $("holdf").onclick = () => send({ weapons: [] });
}

// physical
function askPhys(r) {
  S.sel = r.unit;
  sheet(`<h3>${esc(r.name)}: physical attack on ${esc(r.target_name)}</h3>${errLine(r)}<table><tr><th>Attack</th><th>To hit</th><th>Damage</th><th>Heat</th><th></th></tr>${r.kinds.map((k) => k.options.map((o, i) => `<tr><td>${esc(o.name)}</td><td>TN ${o.tn}</td><td>${o.damage}</td><td>${o.heat || ""}</td><td>${i === 0 ? `<button data-k="${esc(k.kind)}">${esc(k.kind)}</button>` : ""}</td></tr>`).join("")).join("")}</table><div class="row"><button id="skip">No physical attack</button></div>`);
  $("sheet").querySelectorAll("[data-k]").forEach((b) => (b.onclick = () => send({ kind: b.dataset.k })));
  $("skip").onclick = () => send({ kind: null });
}

// the end
function finish(end) {
  S.over = true; S.units = end.units; S.req = null;
  if (end.log) { S.log.push(...end.log); $("report").textContent = S.log.join("\n"); }
  setPhase("Battle over");
  if (gDyn) redraw();
  sheet(`<h3>Battle over</h3><div class="msg">${end.winner === "Draw" ? "A draw" : esc(end.winner) + " wins"} after ${end.turns} turns. ${end.decisions} decisions recorded.</div><div class="row"><button id="show-rep">Show the report</button><a href="index.html"><button>Back to the Lab</button></a></div>`);
  $("show-rep").onclick = () => { $("report").style.display = "block"; $("report").scrollTop = $("report").scrollHeight; };
}
$("rep-btn").onclick = () => { const r = $("report"); r.style.display = r.style.display === "block" ? "none" : "block"; r.scrollTop = r.scrollHeight; };
$("menu-btn").onclick = () => { location.href = "index.html"; };
window.addEventListener("resize", () => { if (S.board) fit(); });
if (!GAME) { $("info").textContent = "No game: start one from the Lab (set a team to Human, then Play)."; } else { loop(); }
window.__bm = S;
