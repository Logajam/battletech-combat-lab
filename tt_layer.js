// REC LAYER, view part (INTEGRATION__TIMELINE_SYNC.md Section 4; the build prompt SONNET_PROMPT_REC_TIMELINE.md Sections 2.1-2.4).
//
// RULE 0: with REC closed the play page is exactly what it was. This file adds one NEW layer on top of play.js and touches it in a few named
// hooks only (`TT.enter` in redraw, `TT.draw` in drawMap, `TT.sync` at the end of chrome / openReport / closeReport, the REC button). Everything it
// adds has an id or class starting "tt-". It never writes into the live state `S` except through `TT.enter`, which swaps `S.units`, `S.log` and
// `S.req` for the length of ONE draw and puts them back (try / finally), so no past state is ever left in the live game.
//
// What it shows: the strip under the top bar (turn readout, two sliders: turn and sub-phase, arrows, Live), the report panel's tabs (Log, Report,
// Timelines), and on the board the battle as it stood at the chosen sub-phase, the mover's path and the attack arrows with their results, the
// camera on the event. The data is the replay record the engine keeps (history.rs: steps with the state of every unit, event slices; the
// {"q": "history"} query while a question waits, or `end.replay` once the game is over).
"use strict";
const TT = (() => {
  const KIND = { init: "Initiative", deploy: "Deployment", move: "Movement", fire: "Fire", fire_end: "Fire", phys: "Physical", phys_end: "Physical", heat: "Heat", over: "End", other: "" };
  const st = { open: false, rec: null, steps: [], byTurn: [], turnList: [], ti: 0, si: 0, tab: "log", seq: -1, over: false, openedReport: false, logs: [], err: "" };

  // ---------------------------------------------------------------- CSS (all tt- names)
  const css = document.createElement("style");
  css.textContent = `
#tt-strip{position:absolute;z-index:11;display:none;grid-template-columns:minmax(120px,200px) minmax(120px,1fr) auto auto;gap:6px;align-items:center;padding:4px 6px;background:var(--panel);border:1px solid var(--bd);box-shadow:0 2px 10px rgba(0,0,0,.45)}
#tt-strip.on{display:grid}
#tt-strip .tt-read{font-size:11px;line-height:1.25;min-width:0;grid-area:rd}
#tt-strip.nar{grid-template-columns:1fr auto;grid-template-areas:"rd lv" "sl ar"}
#tt-strip .tt-sl{grid-area:sl}#tt-strip .tt-ar{grid-area:ar}#tt-strip .tt-live{grid-area:lv}
#tt-strip:not(.nar){grid-template-areas:"rd sl ar lv"}
#tt-strip .tt-read b{display:block;font-size:12px}
#tt-strip .tt-sl{display:flex;flex-direction:column;gap:2px;min-width:0}
#tt-strip input[type=range]{width:100%;margin:0;height:18px;accent-color:var(--link,#4b8fd8)}
#tt-strip .tt-ar{display:flex;gap:2px}
#tt-strip button{min-height:30px;min-width:28px;padding:0 5px;font-size:14px}
#tt-strip .tt-small{font-size:12px;font-weight:700;letter-spacing:.04em}
#tt-strip button.tt-live{font-size:12px;font-weight:700;padding:0 8px}
#tt-strip button.tt-live.now{background:var(--go);border-color:var(--ok);color:#fff}
#tt-tabs{display:none;gap:4px;padding:4px 8px;background:var(--panel);border-bottom:1px solid var(--sh);flex:none}
#tt-tabs.on{display:flex}
#tt-tabs button{min-height:28px;padding:0 10px;font-size:12px}
#tt-tabs button.on{outline:2px solid var(--link,#4b8fd8)}
#tt-pane{display:none;flex:1;overflow:auto;padding:8px 10px;font-size:13px;line-height:1.45}
#tt-pane.on{display:block}
#tt-pane .tt-h{font-weight:700;margin:0 0 4px}
#tt-pane .tt-l{margin:2px 0}
#tt-pane .tt-l.hit{color:#ff9b8f}#tt-pane .tt-l.miss{color:var(--muted)}#tt-pane .tt-l.crit{color:#ffd24a;font-weight:600}
#tt-pane .tt-ctx{margin-top:10px;border-top:1px solid var(--bd);padding-top:6px;font-size:12px;color:var(--muted)}
#tt-pane .tt-ctx div{padding:1px 4px;cursor:pointer}#tt-pane .tt-ctx div.cur{color:var(--tx);font-weight:700;background:var(--face)}
#tt-pane .tt-raw{margin-top:8px;font-size:11px;color:var(--muted);white-space:pre-wrap}
#tt-pane .tt-do{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}
body.tt-replay .tbar .rec{display:none}body.tt-replay #tt-tabs [data-tt-tab="timelines"]{display:none}
#tt-repcopy,#tt-inspcopy{position:fixed;z-index:1100;display:none}
#tt-repcopy.on,#tt-inspcopy.on{display:block}
`;
  document.head.appendChild(css);

  // ---------------------------------------------------------------- the record
  const turnOf = (s) => s.turn || 0;
  function index(rec) {
    st.rec = rec; st.steps = rec.steps || []; st.byTurn = []; st.turnList = []; st.logs = [];
    let acc = [];
    st.steps.forEach((s, i) => {
      const t = turnOf(s); let k = st.turnList.indexOf(t);
      if (k < 0) { st.turnList.push(t); st.byTurn.push([]); k = st.turnList.length - 1; }
      st.byTurn[k].push(i);
      acc = acc.concat(s.log || []); st.logs.push(acc);
    });
  }
  async function load() {
    let rec = null;
    try {
      if (S.over && S.end && S.end.replay) rec = S.end.replay;
      else {
        // the engine answers one query at a time (the page's own look at the move's reach may be in flight): try again a few times
        for (let n = 0; n < 14 && !rec; n++) {
          const r = await api("play_query", { query: { q: "history" } });
          if (r && r.history) rec = r.history; else { st.err = (r && r.error) || "the engine did not answer"; if (!/no question is waiting/.test(st.err)) break; await new Promise((ok) => setTimeout(ok, 350)); }
        }
      }
    } catch (e) { st.err = String(e); }
    if (rec) { st.err = ""; index(rec); st.seq = S.seq; st.over = !!S.over; }
    return !!rec;
  }
  const stale = () => st.seq !== S.seq || st.over !== !!S.over;
  // the live game moved on while REC was open: read the record again, keep the place if it still exists
  async function refresh() {
    const at = pastIndex();
    if (!(await load())) return;
    if (at != null && at < st.steps.length) select(at, true); else live(true);
  }

  // ---------------------------------------------------------------- the place in the record
  const liveIdx = () => st.turnList.length;               // the slider's last stop
  function pastIndex() {
    if (!st.open || st.ti >= st.turnList.length) return null;
    const list = st.byTurn[st.ti]; return list ? list[Math.min(st.si, list.length - 1)] : null;
  }
  function select(i, quiet) {
    for (let k = 0; k < st.byTurn.length; k++) { const j = st.byTurn[k].indexOf(i); if (j >= 0) { st.ti = k; st.si = j; break; } }
    afterMove(quiet);
  }
  function live(quiet) { st.ti = liveIdx(); st.si = 0; afterMove(quiet); }
  function afterMove(quiet) {
    if (!quiet) reopenReport();
    redraw(); focusNow();
  }
  function step(d) {                                     // one sub-phase, across turn borders
    const flat = st.byTurn.flat(), cur = pastIndex();
    let i = cur == null ? flat.length : flat.indexOf(cur);
    i += d; if (i >= flat.length) return live(); if (i < 0) i = 0;
    select(flat[i]);
  }
  function turnJump(d) {
    let k = st.ti + d; if (k < 0) k = 0; if (k > liveIdx()) k = liveIdx();
    if (k >= liveIdx()) return live();
    st.ti = k; st.si = 0; afterMove();
  }

  // ---------------------------------------------------------------- the board at a past step (one draw at a time)
  function enter() {
    const i = pastIndex(); if (i == null) return null;
    const stp = st.steps[i], saved = { units: S.units, log: S.log, req: S.req };
    S.units = S.units.map((u) => { const p = stp.state && stp.state[u.name]; if (!p) return u;
      // what the wings and the inspector read must be the unit as it was at this step, not as it is now: the slots destroyed then, the sinks working then
      const q = { ...u, ...p, moved: false, move_heat: 0 };
      if (p.crit_dead && u.crit_alive) { q.crit_alive = {}; for (const loc of Object.keys(u.crit_alive)) q.crit_alive[loc] = u.crit_alive[loc].map((_, i) => !(p.crit_dead[loc] || []).includes(i)); }
      return q; });
    S.log = st.logs[i] || [];
    S.req = null;                                        // the live question's controls are not shown over a past board
    return () => { S.units = saved.units; S.log = saved.log; S.req = saved.req; };
  }
  const hexesOf = (w) => String(w || "").split(/\s+/).filter(Boolean).map((e) => e.split("/")[0]);
  const evs = () => (st.rec && st.rec.events) || [];
  function stepEvents(stp) { const r = stp.ev; return r ? evs().slice(r[0], r[1]) : []; }
  function moveInfo(i) {
    const stp = st.steps[i], me = stp.unit, es = stepEvents(stp).filter((e) => e.u === me);
    const path = es.find((e) => e.k === "MOVE_PATH"), mv = es.find((e) => e.k === "MOVE");
    const prev = i > 0 ? st.steps[i - 1].state[me] : null, now = stp.state[me];
    const start = prev && prev.hex, end = (mv && mv.w) || (now && now.hex);
    let hexes = path ? [start, ...hexesOf(path.w)].filter(Boolean) : (start && end ? [start, end] : []);
    return { hexes, mode: mv && mv.s, mp: mv && mv.n, jump: !path, es };
  }
  function attackInfo(i) {
    const stp = st.steps[i], a = stp.unit, t = stp.target, turn = turnOf(stp);
    const all = evs().filter((e) => e.t === turn && e.u === a && e.o === t);
    const shots = stp.k === "fire" ? all.filter((e) => e.k === "ATTACK") : all.filter((e) => /^PHYS_/.test(e.k));
    const lands = stepEvents(stp).filter((e) => e.k === "HIT" && e.o === a && e.u === t);
    const dmg = lands.reduce((s, e) => s + (e.d || 0), 0);
    return { a, t, shots, lands, dmg, hits: shots.filter((e) => e.ok).length };
  }
  function draw(layerDyn, layerTop) {
    const i = pastIndex(); if (i == null) return;
    const stp = st.steps[i], uh = MV.unitHeight(), ringOf = (hex, col) => hex && el("polygon", { points: HP(hex, 0.96, uh), fill: "none", stroke: col, "stroke-width": 3 * sc(hex), "pointer-events": "none" }, layerDyn);
    const unitHex = (label) => { const u = S.units.find((x) => x.name === label); return u && u.hex; };
    if (stp.k === "move" && stp.unit) {
      const m = moveInfo(i), col = "#00e5ff";
      const pts = m.hexes.map((h) => at(h, uh));
      if (pts.length > 1) {
        const s = sc(m.hexes[0]);
        el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: "#000", "stroke-opacity": ".55", "stroke-width": 7 * s, "stroke-linejoin": "round", "pointer-events": "none" }, layerDyn);
        el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: col, "stroke-width": 4 * s, "stroke-dasharray": m.jump ? `${3 * s} ${4 * s}` : "", "stroke-linejoin": "round", "pointer-events": "none" }, layerDyn);
        pts.forEach((p, k) => el("circle", { cx: p[0], cy: p[1], r: (k === 0 || k === pts.length - 1 ? 5 : 2.5) * s, fill: k === 0 ? "#fff" : col, stroke: "#000", "stroke-width": 1 * s, "pointer-events": "none" }, layerDyn));
      }
      ringOf(unitHex(stp.unit), "#fff");
    } else if ((stp.k === "fire" || stp.k === "phys") && stp.unit && stp.target) {
      const A = unitHex(stp.unit), T = unitHex(stp.target); if (!A || !T) return;
      const info = attackInfo(i), col = stp.k === "fire" ? "#ff5a4a" : "#ffb000", s = (sc(A) + sc(T)) / 2;
      const [x1, y1] = at(A, uh), [x2, y2] = at(T, uh), len = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / len, uy = (y2 - y1) / len, R0 = 34 * s;
      const ex = x2 - ux * R0 * 0.7, ey = y2 - uy * R0 * 0.7;
      el("line", { x1, y1, x2: ex, y2: ey, stroke: "#000", "stroke-opacity": ".6", "stroke-width": 8 * s, "pointer-events": "none" }, layerTop);
      el("line", { x1, y1, x2: ex, y2: ey, stroke: col, "stroke-width": 4.5 * s, "stroke-dasharray": stp.k === "fire" ? "" : `${3 * s} ${3 * s}`, "pointer-events": "none" }, layerTop);
      el("polygon", { points: `${ex + ux * 9 * s},${ey + uy * 9 * s} ${ex - uy * 7 * s},${ey + ux * 7 * s} ${ex + uy * 7 * s},${ey - ux * 7 * s}`, fill: col, stroke: "#000", "stroke-width": 1.2 * s, "pointer-events": "none" }, layerTop);
      const lx = (x1 + ex) / 2, ly = (y1 + ey) / 2, label = `${info.hits}/${info.shots.length}${info.dmg ? " · " + info.dmg : ""}`;
      el("rect", { x: lx - 24 * s, y: ly - 11 * s, width: 48 * s, height: 18 * s, rx: 4 * s, fill: "#0c0f13", "fill-opacity": ".92", stroke: col, "stroke-width": 1.4 * s, "pointer-events": "none" }, layerTop);
      const tx = el("text", { x: lx, y: ly + 3 * s, "text-anchor": "middle", "font-size": 12 * s, "font-weight": 700, fill: "#fff", "pointer-events": "none" }, layerTop); tx.textContent = label;
      ringOf(A, "#fff"); ringOf(T, col);
    }
  }
  function focusNow() {
    const i = pastIndex(); if (i == null) return;
    const stp = st.steps[i]; let labels = [];
    const unitHex = (l) => { const u = S.units.find((x) => x.name === l); return u && u.hex; };
    if (stp.k === "move" && stp.unit) { const m = moveInfo(i); labels = [m.hexes[0], m.hexes[m.hexes.length - 1]]; }
    else if (stp.unit && stp.target) { const p = st.steps[i].state; labels = [p[stp.unit] && p[stp.unit].hex, p[stp.target] && p[stp.target].hex]; }
    labels = labels.filter(Boolean);
    if (labels.length) { try { MV.focusOn(labels, 2); } catch (e) { /* the view may not be built yet */ } }
  }

  // ---------------------------------------------------------------- words (the Log tab)
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const nm = (label) => { const u = S.units.find((x) => x.name === label); return u ? (u.mech || label) : label; };
  const VERB = { walk: "walked", run: "ran", jump: "jumped", "stand still": "stood still" };
  function describe(i) {
    const stp = st.steps[i], L = [];
    const add = (cls, t) => L.push(`<div class="tt-l ${cls || ""}">${t}</div>`);
    if (stp.k === "deploy") add("", "The units are placed on the board.");
    else if (stp.k === "init") add("", "The Initiative is thrown for the turn.");
    else if (stp.k === "move") {
      const m = moveInfo(i), mode = String(m.mode || "").toLowerCase(), hexes = Math.max(0, m.hexes.length - 1);
      add("", `<b>${esc(nm(stp.unit))}</b> ${VERB[mode] || "moved"}${hexes ? ` ${hexes} hex${hexes > 1 ? "es" : ""}` : ""}${m.mp != null ? ` (${m.mp} MP)` : ""} to ${esc(m.hexes[m.hexes.length - 1] || "")}${stp.state[stp.unit] ? `, facing ${esc(stp.state[stp.unit].facing)}` : ""}.`);
      m.es.filter((e) => e.k === "FALL" || e.k === "STAND_ATTEMPT" || e.k === "HAZARD").forEach((e) => add("crit", e.k === "FALL" ? `It fell (${esc(e.s)}), ${e.n} damage.` : e.k === "STAND_ATTEMPT" ? `Stand attempt: needed ${e.tn}, rolled ${e.r}: ${e.ok ? "stood up" : "stayed down"}.` : `Hazard: ${esc(e.s)}.`));
    } else if (stp.k === "fire" || stp.k === "phys") {
      const a = attackInfo(i);
      add("", `<b>${esc(nm(a.a))}</b> ${stp.k === "fire" ? "fired at" : "attacked"} <b>${esc(nm(a.t))}</b>.`);
      a.shots.forEach((e) => add(e.ok ? "hit" : "miss", `${esc(e.w || e.k.replace("PHYS_", "").toLowerCase())}: needed ${e.tn}, rolled ${e.r}: ${e.ok ? "hit" : "miss"}${e.n > 1 ? ` (${e.n} shots)` : ""}.`));
      if (!a.shots.length) add("miss", "Nothing was fired.");
      a.lands.forEach((e) => add("hit", `${esc(e.w || "hit")}: ${e.d} damage to the ${esc(e.l)}.`));
      stepEvents(stp).filter((e) => ["CRIT", "LOCATION_DESTROYED", "UNIT_DESTROYED", "AMMO_EXPLOSION", "PILOT_HIT", "SHUTDOWN"].includes(e.k)).forEach((e) => add("crit", `${esc(e.k.replace(/_/g, " ").toLowerCase())}: ${esc(nm(e.u || ""))}${e.l ? " " + esc(e.l) : ""}${e.w ? " (" + esc(e.w) + ")" : ""}${e.s ? " " + esc(e.s) : ""}.`));
    } else if (stp.k === "fire_end" || stp.k === "phys_end") add("", `End of the ${stp.k === "fire_end" ? "Fire" : "Physical Attack"} phase.`);
    else if (stp.k === "heat") add("", "Heat and end phase: " + stepEvents(stp).filter((e) => e.k === "HEAT_LEVEL").map((e) => `${esc(nm(e.u || ""))} heat ${e.n}`).join(", ") + ".");
    else if (stp.k === "over") add("", "The battle is over.");
    const raw = (stp.log || []).filter((l) => l.trim()).join("\n");
    return { html: L.join(""), raw };
  }
  const readout = () => {
    const i = pastIndex();
    if (SAVE.candidate && i == null) return "<b>New timeline</b>not kept yet";
    if (i == null && st.replay) return "<b>End</b>of the battle";
    if (i == null) { const turn = (S.log.map((l) => /=== TURN (\d+)/.exec(l)).filter(Boolean).pop() || [])[1]; return `<b>Live</b>${turn ? "Turn " + turn : ""}`; }
    const s = st.steps[i];
    return `<b>${s.turn ? "Turn " + s.turn : "Start"} · ${KIND[s.k] || ""}</b>${s.unit ? esc(nm(s.unit)) : ""}${s.target ? " → " + esc(nm(s.target)) : ""}`;
  };

  // ---------------------------------------------------------------- the DOM: strip, report tabs, the two punch-through buttons
  const $ = (id) => document.getElementById(id);
  function strip() {
    let s = $("tt-strip"); if (s) return s;
    s = document.createElement("div"); s.id = "tt-strip";
    s.innerHTML = `<div class="tt-read" id="tt-read"></div>
      <div class="tt-sl"><input type="range" id="tt-a" min="0" max="0" step="1" aria-label="Turn"><input type="range" id="tt-b" min="0" max="0" step="1" aria-label="Sub-phase"></div>
      <div class="tt-ar"><button data-tt="bigback" aria-label="Previous turn" title="Previous turn">&laquo;</button><button data-tt="back" aria-label="Back one action" title="Back one action">&lsaquo;</button><button data-tt="fwd" aria-label="Forward one action" title="Forward one action">&rsaquo;</button><button data-tt="bigfwd" aria-label="Next turn" title="Next turn">&raquo;</button></div>
      <button class="tt-live" data-tt="live">Live</button>`;
    $("app").appendChild(s);
    s.addEventListener("click", (e) => { const b = e.target.closest("[data-tt]"); if (!b) return; e.stopPropagation(); ({ bigback: () => turnJump(-1), back: () => step(-1), fwd: () => step(1), bigfwd: () => turnJump(1), live: () => (SAVE.candidate ? abandon() : live()) })[b.dataset.tt](); });
    $("tt-a").addEventListener("input", (e) => { st.ti = +e.target.value; st.si = 0; afterMove(); });
    $("tt-b").addEventListener("input", (e) => { st.si = +e.target.value; afterMove(); });
    return s;
  }
  function paintStrip() {
    const s = strip(); s.classList.toggle("on", st.open);
    if (!st.open) return;
    const a = $("tt-a"), b = $("tt-b"), atLive = st.ti >= liveIdx();
    a.max = liveIdx(); a.value = st.ti;
    const cnt = atLive ? 0 : (st.byTurn[st.ti] || []).length;
    b.max = Math.max(0, cnt - 1); b.value = st.si; b.disabled = atLive || cnt < 2;
    s.querySelector(".tt-live").classList.toggle("now", atLive); s.querySelector(".tt-live").textContent = st.replay ? "End" : "Live";
    { const A = $("app"), I0 = UI.ins || { l: 0, r: 0 }; s.classList.toggle("nar", (UI.wide ? A.clientWidth - I0.l - I0.r : A.clientWidth) < 600); }
    $("tt-read").innerHTML = readout();
    // place it: under the top bar (upright) or over the clear middle (sideways); the page's own panels are not moved
    const app = $("app"), wide = UI.wide, I = UI.ins || { l: 0, r: 0 };
    if (wide) { s.style.left = I.l + 6 + "px"; s.style.right = I.r + 6 + "px"; s.style.top = "6px"; }
    else { const tb = document.querySelector("#pnE .tbar"); s.style.left = "6px"; s.style.right = "6px"; s.style.top = (tb ? tb.offsetHeight + 4 : 38) + "px"; }
  }
  function decorate() {
    const rep = $("report"); if (!rep || !rep.firstChild) return;
    const box = $("rbox"); let tabs = $("tt-tabs"), pane = $("tt-pane");
    if (!tabs) {
      tabs = document.createElement("div"); tabs.id = "tt-tabs";
      tabs.innerHTML = '<button data-tt-tab="log">Log</button><button data-tt-tab="report">Report</button><button data-tt-tab="teams">Teams</button><button data-tt-tab="timelines">Timelines</button>';
      box.insertBefore(tabs, $("rbody"));
      pane = document.createElement("div"); pane.id = "tt-pane"; box.appendChild(pane);
      tabs.addEventListener("click", (e) => { const b = e.target.closest("[data-tt-tab]"); if (b) { st.tab = b.dataset.ttTab; paintPane(); } });
      pane.addEventListener("click", (e) => { const r = e.target.closest("[data-tt-go]"); if (r) { select(+r.dataset.ttGo); } const d = e.target.closest("[data-tt-do]"); if (d) doAction(d.dataset.ttDo); });
      pane.addEventListener("change", (e) => { if (e.target.dataset && e.target.dataset.ttTeam) st.teamPick = { ...(st.teamPick || {}), [e.target.dataset.ttTeam]: e.target.value }; });
    }
    tabs.classList.toggle("on", st.open);
    paintPane();
  }
  function paintPane() {
    const pane = $("tt-pane"), tabs = $("tt-tabs"); if (!pane) return;
    const show = st.open && st.tab !== "report";
    pane.classList.toggle("on", show); $("rbody").style.display = st.open && st.tab !== "report" ? "none" : "";
    [...tabs.querySelectorAll("button")].forEach((b) => b.classList.toggle("on", b.dataset.ttTab === st.tab));
    if (!st.open) return;
    if (st.tab === "log") pane.innerHTML = logHtml();
    else if (st.tab === "timelines") pane.innerHTML = timelinesHtml();
    else if (st.tab === "teams") pane.innerHTML = teamsHtml();
  }
  function logHtml() {
    if (st.err) return `<div class="tt-l miss">The game's record could not be read: ${esc(st.err)}</div>`;
    if (!st.steps.length) return '<div class="tt-l miss">Nothing has happened yet.</div>';
    const i = pastIndex(), shown = i == null ? st.steps.length - 1 : i, d = describe(shown), s = st.steps[shown];
    const turnIdx = st.turnList.indexOf(turnOf(s)), list = st.byTurn[turnIdx] || [];
    const ctx = list.map((j) => `<div class="${j === shown ? "cur" : ""}" data-tt-go="${j}">${esc(st.steps[j].phase)}</div>`).join("");
    const can = i != null && meddleSpec(i);
    const banner = SAVE.candidate ? '<div class="tt-l crit">A NEW TIMELINE, not kept yet. Hold Meddle on your first answer to keep it. Live, or closing REC, goes back to the game you left.</div>' : "";
    return nameHtml(`${banner}<div class="tt-h">${i == null ? "Live: the latest action was" : esc(KIND[s.k] || "")}</div>${d.html}
      <div class="tt-do"><button data-tt-do="live" class="${i == null ? "on" : ""}">${st.replay ? "End" : "Live"}</button>${st.replay && i != null ? '<button data-tt-do="from" class="go">Play from here</button>' : ""}${can ? '<button data-tt-do="meddle">Meddle here</button>' : ""}</div>
      ${i != null && !can ? '<div class="tt-l miss">Meddle is for a unit\'s move, shot or physical attack.</div>' : ""}${i == null && !SAVE.candidate ? '<div class="tt-l miss">Move a slider back to an action, then press Meddle here to take it over.</div>' : ""}
      <div class="tt-ctx"><b>This turn</b>${ctx}</div>${d.raw ? `<div class="tt-raw">${esc(d.raw)}</div>` : ""}`);
  }
  function timelinesHtml() {
    return `<div class="tt-l">Games you can switch between in this browser.</div><div class="tt-do">
      ${SAVE.parent ? '<button data-tt-do="parent">Back to the earlier timeline</button>' : ""}${SAVE.child ? '<button data-tt-do="child">On to the later timeline</button>' : ""}
      <button data-tt-do="file">Save game to a file</button></div>${SAVE.parent || SAVE.child ? "" : '<div class="tt-l miss">This game has no other timeline yet.</div>'}`;
  }
  function doAction(a) {
    if (a === "live") { if (SAVE.candidate) return abandon(); live(); }
    else if (a === "meddle") meddleHere();
    else if (a === "apply") { if (st.replay) playFromHere(true); else applyTeams(); }
    else if (a === "from") playFromHere(false);
    else if (a === "keep") { commitCandidate(); toast("Kept: this is the game now."); }
    else if (a === "discard") abandon();
    else if (a === "parent") backToParent();
    else if (a === "child") forwardToChild();
    else if (a === "file") saveToFile();
  }
  function reopenReport() { const r = $("report"); if (r && r.style.display !== "block") { openReport(false); st.openedReport = true; } decorate(); }

  // the two deliberate exceptions to rule 0 (prompt 2.1, 2.2): the Report button and the Inspect button stay on top of their panels. A copy of
  // the button, fixed over the original's place, with the same data-act so the page's own handler does the work.
  function copyOf(id, on, original, act, label) {
    let c = $(id);
    if (!c) { c = document.createElement("button"); c.id = id; c.dataset.act = act; c.textContent = label; $("app").appendChild(c); }
    if (!on || !original) { c.classList.remove("on"); return; }
    const r = original.getBoundingClientRect();
    // only when something lies over the real button (the report and the inspector now keep clear of the side panels and bands, so usually nothing
    // does and the real button is all there is: no copy sitting on the text under it, Daniel 2026-11-27)
    c.classList.remove("on"); const over = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!over || over === original || original.contains(over)) return; c.style.left = r.left + "px"; c.style.top = r.top + "px"; c.style.width = r.width + "px"; c.style.height = r.height + "px";
    c.classList.add("on");
  }
  // THE REPORT sits in the bottom half of the clear area between the panels: it no longer covers the side panels (landscape, desktop) or the bottom
  // band (upright), so the commit button, the heat display and the Report button stay in reach under it; on a short landscape screen it takes more
  // of the height. (The layout numbers are the page's own, UI.ins.)
  function fitReport() {
    const rep = $("report"); if (!rep || rep.style.display !== "block") return;
    const I = UI.ins || { l: 0, r: 0, t: 0, b: 0 }, short = window.innerHeight < 500;
    rep.style.left = (I.l || 0) + "px"; rep.style.right = (I.r || 0) + "px"; rep.style.bottom = (I.b || 0) + "px"; rep.style.top = short ? "34%" : "50%";
  }
  function punch() {
    fitReport();
    const rep = $("report");
    copyOf("tt-repcopy", !!(rep && rep.style.display === "block"), $("rep-btn"), "report", "Report");
    copyOf("tt-inspcopy", !!(UI.insp && UI.insp.open), document.querySelector('#pnE [data-act="inspect"]'), "inspect", "Inspect");
  }

  // ---------------------------------------------------------------- meddling: a candidate timeline (prompt Section 3)
  // The step the person looks at, as a cut in the order list. A move is one decision, so the cut is just before it. All fire declarations (and all
  // physical ones) are made before any is resolved, so the cut for a fire / physical step is at the start of that phase and the person takes over
  // THAT unit's decisions. `flow` = how many list events (not branch events) had been written when the step before the cut was marked.
  const teamOf = (label) => { const u = S.units.find((x) => x.name === label); return u && u.team; };
  function cutFor(i) {
    const s = st.steps[i]; let j = i;
    if (s.k === "fire" || s.k === "phys") { const f = st.steps.findIndex((x) => turnOf(x) === turnOf(s) && x.k === s.k); if (f >= 0) j = f; }
    return { after: j, flow: j === 0 ? 0 : st.steps[j - 1].orders };
  }
  function meddleSpec(i) {
    const s = st.steps[i]; if (!s || !s.unit || !["move", "fire", "phys"].includes(s.k)) return null;
    const team = teamOf(s.unit); if (!team) return null;
    return s.k === "move" ? { team, phase: "move" } : { team, phase: s.k, unit: s.unit };
  }
  // The original game is stored as it stands, the branch is written to "bm_try" and the page reloads into it (play.html?resume=try). Nothing of the
  // game being left is overwritten: bm_save stays as it was until the first answer of the new timeline is held.
  function makeBranch(body, cut, label, src) {
    // src: where the game being branched comes from: the live game (default) or a replay's own record and order list (replay mode: Play from here)
    if (!src) saveNow();
    const f = src ? src.file : saveFile(true); if (!f) { toast("There is nothing to branch from."); return; }
    const events = src ? src.events : SAVE.events, marks = src ? [] : SAVE.marks;
    let n = 0; const prefix = [];
    for (const e of events) { if (e.branch) { if (e.branch.after_step <= cut.after) prefix.push(e); continue; } if (n >= cut.flow) break; prefix.push(e); n++; }
    const seed = Math.floor(Math.random() * 0xFFFFFFFE) + 1;
    prefix.push({ branch: { after_step: cut.after, reseed: String(seed), ...body } });
    const file = { ...f, parent: src ? null : { ...f, child: null }, child: null, marks: marks.filter((m) => m.at < prefix.length), title: (f.title || "game").replace(/ \(.*\)$/, "") + " (" + label + ")", orders: { ...f.orders, events: prefix }, branched_at: label, reseed: String(seed) };
    try { localStorage.setItem("bm_try", JSON.stringify(file)); } catch (e) { toast("This browser will not keep the new timeline (storage is full or off): save the game to a file first."); return; }
    SAVE.frozen = true;
    (window.top || window).location.href = "play.html?resume=try";
  }
  // REPLAY MODE (play.html?replay=1, shown in the Lab's Replay tab): the record of a finished battle (a bot battle or a human game) is the whole page.
  // Play from here = a candidate timeline from the step being looked at, built from the record's own setup, seed and order list.
  function playFromHere(useTeams) {
    const i = pastIndex(); if (i == null) { toast("Move a slider to the action you want to play from."); return; }
    const meta = st.meta, rec = st.rec; if (!meta || !meta.setup) { toast("This replay has no setup to play from."); return; }
    const setup = meta.setup, humanNow = (setup.teams || []).filter((t) => t.bot === "human").map((t) => t.name);
    const file = { combatlab_game: 1, saved: new Date().toISOString(), title: (setup.teams || []).map((t) => t.name).join(" vs "), setup, seed: String(rec.seed), sim: rec.sim || 1,
      orders: { order_format: 1, engine: "browser", seed: String(rec.seed), human: humanNow, events: [] }, marks: [], parent: null, child: null };
    const ch = []; const want = useTeams ? st.teamPick || {} : {};
    for (const t of (setup.teams || []).map((x) => x.name)) { const w = want[t]; if (w && w !== currentByMeta(t)) ch.push({ team: t, by: w }); }
    let body = {};
    if (ch.length) body = { control: ch };
    else if (!humanNow.length) { const team = teamOf(st.steps[i].unit || st.steps[i].target) || (setup.teams[0] || {}).name; body = { control: [{ team, by: "human" }] }; }   // a bot battle: the person takes the team of the action
    makeBranch(body, cutFor(i), "play from here", { file, events: (meta.orders && meta.orders.events) || [] });
  }
  function currentByMeta(team) {
    let by = null; for (const e of (st.meta.orders && st.meta.orders.events) || []) if (e.branch && e.branch.control) for (const c of e.branch.control) if (c.team === team) by = c.by;
    if (by) return by;
    const t = ((st.meta.setup || {}).teams || []).find((x) => x.name === team); return (t && t.bot) || "gladiator";
  }
  async function replayBoot() {
    let meta = null; try { meta = JSON.parse(localStorage.getItem("bm_replay") || "null"); } catch (e) { meta = null; }
    if (!meta || !meta.record || !meta.record.steps) { setPhase("no replay"); ask('<h3>No replay</h3><div class="msg">Open a battle from the Lab\'s Results page.</div>'); return; }
    const rec = meta.record; st.meta = meta; st.replay = true; document.body.classList.add("tt-replay");
    S.setup = meta.setup || null; COLOURS = rec.colours || {};
    const last = rec.steps[rec.steps.length - 1].state, labels = Object.keys(rec.mechs);
    S.units = labels.map((label, i) => { const m = rec.mechs[label];
      return { id: i, name: label, mech: m.name, team: rec.teams[label], tons: m.tons, walk: 0, run: 0, jump: 0, max_heat: 30, sinks: 0, moved: false, crit_alive: {}, equipment: {}, weapons: [], ...last[label] }; });
    S.board = rec.board; S.myTeam = (rec.team_order || [])[0]; S.over = true; S.end = { replay: rec };
    for (const u of S.units) { S.maxLoc[u.id] = JSON.parse(JSON.stringify(rec.mechs[u.name].max || {})); }
    buildMap(); S.needFocus = false;
    await load(); st.open = true; st.tab = "log";
    setPhase("Replay: " + ((S.setup && S.setup.teams) ? S.setup.teams.map((t) => t.name).join(" vs ") : "battle"));
    live(true); reopenReport(); chrome(); redraw(); MV.fit();
  }
  function meddleHere() {
    const i = pastIndex(); if (i == null) return;
    const m = meddleSpec(i); if (!m) return;
    if (st.replay) { const meta = st.meta, setup = meta.setup, rec = st.rec;
      const file = { combatlab_game: 1, saved: new Date().toISOString(), title: (setup.teams || []).map((t) => t.name).join(" vs "), setup, seed: String(rec.seed), sim: rec.sim || 1, orders: { order_format: 1, engine: "browser", seed: String(rec.seed), human: (setup.teams || []).filter((t) => t.bot === "human").map((t) => t.name), events: [] }, marks: [], parent: null, child: null };
      return makeBranch({ meddle: m }, cutFor(i), "meddle", { file, events: (meta.orders && meta.orders.events) || [] }); }
    makeBranch({ meddle: m }, cutFor(i), "meddle");
  }
  const BOTS = [["human", "Human"], ["gladiator", "Gladiator"], ["princess", "Princess"]];
  function currentBy(team) {
    if (st.replay) return currentByMeta(team);
    let by = null; for (const e of SAVE.events) if (e.branch && e.branch.control) for (const c of e.branch.control) if (c.team === team) by = c.by;
    if (by) return by;
    const t = ((S.setup || {}).teams || []).find((x) => x.name === team); return (t && t.bot) || "gladiator";
  }
  function teamsHtml() {
    const teams = ((S.setup || {}).teams || []).map((t) => t.name), i = pastIndex();
    const rows = teams.map((t) => { const cur = (st.teamPick && st.teamPick[t]) || currentBy(t); const known = BOTS.some((b) => b[0] === cur);
      return `<div class="tt-l"><b>${esc(t)}</b> <select data-tt-team="${esc(t)}">${known ? "" : `<option value="${esc(cur)}" selected>${esc(cur)} (now)</option>`}${BOTS.map((b) => `<option value="${b[0]}" ${b[0] === cur ? "selected" : ""}>${b[1]}</option>`).join("")}</select></div>`; }).join("");
    return `<div class="tt-l">Who plays each team from the action you are looking at to the end of the game. A change takes effect in a NEW timeline; Human means you answer for that team.</div>${rows}
      <div class="tt-do"><button data-tt-do="apply" class="go" ${i == null ? "disabled" : ""}>${st.replay ? "Play from here" : "Apply from here"}</button></div>${i == null ? '<div class="tt-l miss">Move a slider back to the action to change from.</div>' : ""}`;
  }
  function applyTeams() {
    const i = pastIndex(); if (i == null) return;
    const ch = []; for (const t of ((S.setup || {}).teams || []).map((x) => x.name)) { const want = (st.teamPick && st.teamPick[t]) || currentBy(t); if (want !== currentBy(t)) ch.push({ team: t, by: want }); }
    if (!ch.length) { toast("No team has a different setting."); return; }
    makeBranch({ control: ch }, cutFor(i), "new teams");
  }
  function abandon() { try { localStorage.removeItem("bm_try"); } catch (e) { /* storage off */ } SAVE.frozen = true; location.href = "play.html?resume=1"; }
  function commitCandidate() {
    if (!SAVE.candidate) return;
    SAVE.candidate = false;
    { const f = saveFile(true); if (f) { try { localStorage.setItem("bm_save", JSON.stringify(f)); } catch (e) { toast("This browser will not keep the new timeline."); } } }   // bm_save is the new timeline now (its parent is the game left behind); a game already over is kept too
    try { localStorage.removeItem("bm_try"); } catch (e) { /* storage off */ }
    SAVE.child = null; paintStrip(); paintPane();
  }
  // a candidate whose game ends without asking anything (a team handed to a bot): keep it or discard it
  function candidateOver() {
    if (!SAVE.candidate || !S.over) return;
    const a = $("ask"); if (!a) return;
    a.insertAdjacentHTML("beforeend", '<div class="row"><b>A new timeline.</b> It ends without asking you anything.</div><div class="row"><button class="go" data-tt-keep="1">Keep this timeline</button><button data-tt-discard="1">Back to the earlier one</button></div>');
    a.querySelector("[data-tt-keep]").addEventListener("click", () => { commitCandidate(); toast("Kept: this is the game now."); });
    a.querySelector("[data-tt-discard]").addEventListener("click", abandon);
  }
  let cStarted = false;
  function afterTake() { if (SAVE.candidate && !cStarted && !st.open) { cStarted = true; toggle(); } }
  const followTeam = () => !!SAVE.candidate || SAVE.events.some((e) => e.branch);

  // ---------------------------------------------------------------- called from the page
  function sync() {
    punch();
    if (!st.open) { const t = $("tt-tabs"); if (t) { t.classList.remove("on"); paintPane(); } paintStrip(); const ask = $("ask"); if (ask) ask.style.visibility = ""; return; }
    paintStrip(); decorate();
    { const ask = $("ask"); if (ask) ask.style.visibility = pastIndex() != null ? "hidden" : ""; }   // the live question's words are not shown over a past board
    // the map frames what the panels leave: the top half while the report is up, below the strip
    const rep = $("report"), I = UI.ins; if (I) {
      const strip_ = $("tt-strip"), H = $("app").clientHeight;
      if (strip_ && !UI.wide) I.t = Math.max(I.t, strip_.offsetTop + strip_.offsetHeight + 4);
      if (rep && rep.style.display === "block") I.b = Math.max(I.b, Math.round(H / 2));
      if (MV.setInsets(I) && S.board) { if (S.lastFocus) MV.focusOn(S.lastFocus[0], S.lastFocus[1]); }
    }
  }
  async function toggle() {
    if (st.replay) return;                               // the replay page is always open
    if (st.open) {
      if (SAVE.candidate) return abandon();   // REC closed before Meddle was held: nothing is written, back to the game you left
      st.open = false; live(true);
      if (st.openedReport) { closeReport(); st.openedReport = false; }
      sync(); redraw(); return;
    }
    if (!S.board) return;
    st.open = true; st.tab = "log";
    if (!(await load())) { st.open = false; toast("Time travel could not read the game: " + (st.err || "no record")); sync(); return; }
    live(true); reopenReport(); sync(); redraw();
  }
  // taps on the board do nothing at a past step (the live controls are not drawn there)
  document.addEventListener("click", (e) => { if (pastIndex() != null && e.target.closest && e.target.closest("#map")) { e.stopPropagation(); e.preventDefault(); } }, true);
  window.addEventListener("resize", () => { if (st.open) sync(); });

  return { toggle, enter, draw, sync, replayBoot, commitCandidate, candidateOver, afterTake, followTeam, isOpen: () => st.open, past: () => pastIndex() != null, refreshIfStale: () => { if (st.open && stale()) refresh(); }, _st: st };
})();
