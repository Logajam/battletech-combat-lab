"use strict";
// MAP VIEW: the one place that knows how a board is drawn and how the camera sees it (PROJECT_MAP P10, 3D tabletop, build step 1).
// play.js asks it where a hex is (`centre`), the corners of a hex (`pts`), the layers to draw into (`layers`), how big a screen pixel is
// (`k`), and it moves the camera through `fit`, `focusOn`, `zoom` and `panBy`; it never touches the SVG's viewBox itself.
// This is the flat top-down SVG view the page has always had, moved here unchanged (Daniel's rule for step 1: nothing changes visibly).
// The 3D tabletop view (tabletop.js: WebGL under a transparent SVG) takes the same calls, so the page's drawing code does not care which view it
// was given; the top-down view stays as the Top-down option and the fallback. `setMode("3d")` loads three.js and tabletop.js the first time it is
// asked (a page that never asks never downloads them) and falls back to the flat view when WebGL is not there.
(function () {
  const R = 34, SQ3 = Math.sqrt(3), NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  // hooks.rescale(): called (after a pause) when a zoom has changed the size of a screen pixel enough that screen-constant marks (placards) are redrawn
  // hooks.camera(): called (at most once a frame) when the tabletop camera moved: what the page draws over the 3D board is projected, so it is drawn again
  function create(svg, hooks) {
    hooks = hooks || {};
    const mv = { R, svg, bounds: null, view: null, layers: null, mode: "top" };
    let board = null, tt = null, loading = null, lastD = 0;
    let kLast = 0, kTimer = null;

    // ---- geometry (flat-topped hexes, even columns half a hex lower, N up)
    const parse = (l) => [parseInt(l.slice(0, 2), 10), parseInt(l.slice(2), 10)];
    mv.centre = (l) => { const [c, r] = parse(l); return [R + (c - 1) * 1.5 * R, (SQ3 / 2) * R + (r - 1) * SQ3 * R + (c % 2 === 0 ? (SQ3 / 2) * R : 0)]; };
    mv.pts = (cx, cy, k = 1) => [0, 1, 2, 3, 4, 5].map((i) => `${(cx + R * k * Math.cos(Math.PI / 3 * i)).toFixed(1)},${(cy + R * k * Math.sin(Math.PI / 3 * i)).toFixed(1)}`).join(" ");

    // ---- the board: empty layers, the terrain painted once into an image, one transparent hit polygon (and number) for every hex.
    // board = { width, height, hexes: { label: { l: level, f: features, b: building } } }; opts.labels = print the hex numbers
    mv.setBoard = (brd, opts) => {
      board = brd; svg.innerHTML = "";
      const W = brd.width, H = brd.height;
      mv.bounds = [0, 0, R * 2 + (W - 1) * 1.5 * R, SQ3 * R * H + (SQ3 / 2) * R];
      mv.layers = { map: el("g", {}, svg), dyn: el("g", {}, svg), top: el("g", {}, svg) };
      // the terrain is painted by the same code as the Lab's map preview (boardart.js), into an image under the interactive layer
      const hexes = new Map();
      for (const label of Object.keys(brd.hexes)) {
        const h = brd.hexes[label], f = {};
        for (const [k, v] of Object.entries(h.f || {})) f[k] = [String(v)];
        if (h.b) f.building = [];
        hexes.set(`${+label.slice(0, 2)},${+label.slice(2)}`, { level: h.l || 0, f });
      }
      const SC = 2, cv = document.createElement("canvas");
      cv.width = Math.ceil(mv.bounds[2] * SC); cv.height = Math.ceil(mv.bounds[3] * SC);
      const g2 = cv.getContext("2d"); g2.scale(SC, SC);
      BoardArt.paintHexes(g2, [{ board: { hexes }, ox: 0, oy: 0 }], R);
      el("image", { href: cv.toDataURL("image/png"), x: 0, y: 0, width: mv.bounds[2], height: mv.bounds[3], "pointer-events": "none" }, mv.layers.map);
      for (const label of Object.keys(brd.hexes).sort()) {
        const [x, y] = mv.centre(label), g = el("g", { "data-hex": label }, mv.layers.map);
        el("polygon", { points: mv.pts(x, y), fill: "transparent" }, g);
        if (opts && opts.labels) { const t = el("text", { x, y: y - R * 0.62, "text-anchor": "middle", "font-size": 8, fill: "#000", "fill-opacity": ".55", "font-family": "ui-monospace,monospace", "pointer-events": "none" }, g); t.textContent = label; }
      }
      if (tt) { hideFlat(); tt.setBoard(brd); } else mv.fit();
    };

    // ---- the camera: a viewBox over the board (pan and zoom only)
    mv.k = () => (mv.mode === "3d" && tt ? 1 : (mv.view ? mv.view.w : svg.viewBox.baseVal.width || 1) / (svg.getBoundingClientRect().width || 1));   // view units per screen pixel (1 over the 3D board)
    mv.markScale = () => { kLast = mv.k(); };                                                                          // placards were drawn at this scale
    const applyView = () => {
      const v = mv.view; svg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
      // the placards keep one size on the screen, so they are drawn again (after a pause) when the zoom changes
      const k = v.w / (svg.getBoundingClientRect().width || 1);
      if (kLast && Math.abs(k - kLast) / kLast > 0.08) { clearTimeout(kTimer); kTimer = setTimeout(() => { if (hooks.rescale) hooks.rescale(); }, 120); }
    };
    // zoom in on a set of hexes (labels) with a margin, as the first view of a game: your own units, not the whole board
    mv.focusOn = (labels, marginHexes) => {
      if (!mv.bounds || !labels.length) return mv.fit();
      const r = svg.getBoundingClientRect(), ar = (r.width || 1) / (r.height || 1), m = (marginHexes || 4) * R * 1.5;
      const pts = labels.map(mv.centre), xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      let x0 = Math.min(...xs) - m, x1 = Math.max(...xs) + m, y0 = Math.min(...ys) - m, y1 = Math.max(...ys) + m;
      let w = x1 - x0, h = y1 - y0;
      if (w / h < ar) { const nw = h * ar; x0 -= (nw - w) / 2; w = nw; } else { const nh = w / ar; y0 -= (nh - h) / 2; h = nh; }
      // keep the view on the board where the board is large enough to fill it
      const B = mv.bounds;
      if (w <= B[2] + 8) x0 = Math.max(B[0] - 4, Math.min(x0, B[0] + B[2] + 4 - w));
      if (h <= B[3] + 8) y0 = Math.max(B[1] - 4, Math.min(y0, B[1] + B[3] + 4 - h));
      mv.view = { x: x0, y: y0, w, h }; applyView();
    };
    mv.fit = () => {
      if (!mv.bounds) return;
      const b = mv.bounds, r = svg.getBoundingClientRect(), ar = (r.width || 1) / (r.height || 1);
      let w = b[2] + 8, h = b[3] + 8;
      if (w / h < ar) w = h * ar; else h = w / ar;
      mv.view = { x: b[0] - 4 - (w - b[2] - 8) / 2, y: b[1] - 4 - (h - b[3] - 8) / 2, w, h };
      applyView();
    };
    // zoom by factor f (below 1 zooms in) about a client point (the middle of the map when none is given)
    mv.zoom = (f, cx, cy) => {
      const v = mv.view, r = svg.getBoundingClientRect();
      const px = cx == null ? 0.5 : (cx - r.left) / r.width, py = cy == null ? 0.5 : (cy - r.top) / r.height;
      const nw = Math.max(120, Math.min(mv.bounds[2] * 3, v.w * f)), nh = nw * v.h / v.w;
      mv.view = { x: v.x + (v.w - nw) * px, y: v.y + (v.h - nh) * py, w: nw, h: nh };
      applyView();
    };
    // drag the map by a screen distance (a finger's move)
    mv.panBy = (dx, dy) => {
      const r = svg.getBoundingClientRect();
      mv.view.x -= dx * mv.view.w / r.width; mv.view.y -= dy * mv.view.h / r.height; applyView();
    };

    // ---- the two views behind one set of calls. The flat view's camera is above; the tabletop's is tabletop.js.
    const flat = { fit: mv.fit, focusOn: mv.focusOn, zoom: mv.zoom, panBy: mv.panBy };
    const is3d = () => mv.mode === "3d" && !!tt;
    const hideFlat = () => { if (mv.layers) mv.layers.map.style.display = "none"; };   // the flat terrain image and hex hit polygons; the layers the page draws into stay and are drawn projected
    // ---- geometry for the page's drawing, the same calls in both views. Flat: board units (a hex is R = 34 across the middle). Tabletop: screen
    // pixels of the svg, which is sized to the map there; a hex's points are projected at the top of its tile. Offsets are in hex radii (dx east,
    // dy south) and `up` is world units above the tile top, so a point drawn on the ground follows the ground. `scale(label)` is view units per
    // board unit at that hex (1 in the flat view): lengths that were written in board units (a stroke, a radius, a text size) are multiplied by it.
    // a point behind the camera (or absurdly far off the screen) has no place: it is sent far away, and a polygon with such a corner is left empty
    const OFF = -99999, good = (p) => p && p.ok && Math.abs(p.x) < 50000 && Math.abs(p.y) < 50000;
    mv.at = (l, up) => { if (is3d()) { const p = tt.project(l, 0, 0, up || 0); return good(p) ? [p.x, p.y] : [OFF, OFF]; } return mv.centre(l); };
    mv.pt = (l, dx, dy, up) => { if (is3d()) { const p = tt.project(l, dx, dy, up || 0); return good(p) ? [p.x, p.y] : [OFF, OFF]; } const c = mv.centre(l); return [c[0] + R * dx, c[1] + R * dy]; };
    mv.is3d = is3d;
    mv.dropDepth = (l) => (is3d() ? tt.dropDepth(l) : 0); mv.raised = (l) => (is3d() ? tt.raised(l) : false);
    // the units, the hexes they stand on (woods get a ring of trees round the base) and the points the cut-away keeps in view. Kept here so that
    // entering the 3D view later shows them too; the flat view draws units itself.
    const keep = { units: [], occ: "", focus: [] };
    mv.setUnits = (list) => { keep.units = list; if (tt) tt.setUnits(list); };
    mv.setOccupied = (labels) => { const k = labels.slice().sort().join(","); if (k === keep.occ) return; keep.occ = k; keep.occL = labels; if (tt) tt.setOccupied(labels); };
    mv.setFocus = (list) => { keep.focus = list; if (tt) tt.setFocus(list); };
    mv.keep = keep;
    mv.hexPts = (l, k = 1, up = 0) => {
      if (!is3d()) { const c = mv.centre(l); return mv.pts(c[0], c[1], k); }
      const ps = [0, 1, 2, 3, 4, 5].map((i) => tt.project(l, k * Math.cos(Math.PI / 3 * i), k * Math.sin(Math.PI / 3 * i), up));
      return ps.every(good) ? ps.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") : "0,0 0,0 0,0";
    };
    mv.scale = (l) => { if (!is3d()) return 1; const p = tt.project(l, 0, 0, 0); return p ? p.scale : 1; };
    mv.unitHeight = () => (is3d() ? tt.unitHeight() : 0);                         // the height of a unit's base above its tile (world units)
    // labels far to near (a polygon drawn later is on top, and takes the tap): the flat view keeps the order it was given
    mv.order = (labels) => { if (!is3d()) return labels; return labels.map((l) => { const p = tt.project(l, 0, 0, 0); return [l, p ? p.d : 0]; }).sort((a, b) => b[1] - a[1]).map((a) => a[0]); };
    // the svg over the 3D board has the size of the board's host: one view unit is one pixel
    mv.syncView = () => { if (!is3d()) return; const r = svg.getBoundingClientRect(); svg.setAttribute("viewBox", `0 0 ${Math.max(1, r.width)} ${Math.max(1, r.height)}`); };
    mv.fit = () => (is3d() ? tt.fit() : flat.fit());
    mv.focusOn = (labels, m) => (is3d() ? tt.focusOn(labels, m) : flat.focusOn(labels, m));
    mv.zoom = (f, cx, cy) => (is3d() ? tt.zoom(f, cx, cy) : flat.zoom(f, cx, cy));
    // a finger moved the map by (dx, dy) and is now at client (x, y)
    mv.panBy = (dx, dy, x, y) => (is3d() ? tt.panBy(dx, dy, x, y) : flat.panBy(dx, dy));
    // two fingers at client points a and b, called on every move; flat: a pinch zoom, tabletop: pinch, twist, pan and tilt. pinchEnd when a finger lifts.
    mv.pinch = (a, b) => {
      if (is3d()) return tt.pinch(a, b);
      const d = Math.hypot(a.x - b.x, a.y - b.y); if (lastD) flat.zoom(lastD / d, (a.x + b.x) / 2, (a.y + b.y) / 2); lastD = d;
    };
    mv.pinchEnd = () => { lastD = 0; if (is3d()) tt.pinchEnd(); };
    mv.orbitBy = (dx, dy) => { if (is3d()) tt.orbitBy(dx, dy); };            // right-drag: turn and tilt (tabletop only)
    mv.hexAt = (x, y) => (is3d() ? tt.hexAt(x, y) : null);                    // the hex under a client point (tabletop only; the flat view's hexes are elements)
    mv.project = (label, dx, dy, up) => (is3d() ? tt.project(label, dx, dy, up) : null);
    mv.preset = (n) => { if (is3d()) tt.preset(n); };
    mv.cycleTilt = () => { if (is3d()) tt.cycleTilt(); };
    mv.setting = (patch) => { if (tt) tt.set(patch); };
    mv.tabletop = () => tt;
    // ---- the mode: "top" (the flat SVG view) or "3d" (the tabletop). Resolves to the mode in force: "top" when the 3D view could not start.
    const loadScript = (src) => new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => bad(new Error("could not load " + src)); document.head.appendChild(s); });
    mv.setMode = async (mode, settings) => {
      if (mode === mv.mode) return mv.mode;
      if (mode === "3d") {
        try {
          if (!loading) loading = (async () => { if (!window.THREE) await loadScript("three.min.js"); if (!window.Tabletop) await loadScript("tabletop.js"); if (!window.MECH_SPRITES) await loadScript("mechsprites.js").catch(() => {}); })();
          await loading;
          const host = document.createElement("div"); host.id = "tabletop"; host.style.cssText = "position:absolute;inset:0;overflow:hidden";
          svg.parentElement.insertBefore(host, svg); tt = window.Tabletop.create(host, { settings });
          let sig = ""; tt.onRender = () => { const c = tt.camera, s = [c.tx, c.tz, c.yaw, c.tilt, c.dist, c.persp, host.clientWidth, host.clientHeight].map((v) => Math.round(v * 100) / 100).join(","); if (s === sig) return; sig = s; mv.syncView(); if (hooks.camera) hooks.camera(); };
        } catch (e) { loading = null; if (tt) { tt.dispose(); tt = null; } const h = document.getElementById("tabletop"); if (h) h.remove(); return mv.mode; }
        mv.mode = "3d"; svg.style.background = "transparent"; svg.style.position = "absolute"; svg.style.inset = "0"; svg.parentElement.classList.add("tabletop");
        hideFlat(); mv.syncView(); if (board) tt.setBoard(board); if (board) { tt.setUnits(keep.units); if (keep.occL) tt.setOccupied(keep.occL); tt.setFocus(keep.focus); }
      } else {
        if (tt) { tt.dispose(); const h = document.getElementById("tabletop"); if (h) h.remove(); tt = null; }
        mv.mode = "top"; svg.style.background = ""; svg.style.position = ""; svg.style.inset = ""; svg.parentElement.classList.remove("tabletop");
        if (mv.layers) mv.layers.map.style.display = ""; flat.fit();
      }
      return mv.mode;
    };
    return mv;
  }
  window.MapView = { create, R };
})();
