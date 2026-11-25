"use strict";
// MAP VIEW: the one place that knows how a board is drawn and how the camera sees it (PROJECT_MAP P10, 3D tabletop, build step 1).
// play.js asks it where a hex is (`centre`), the corners of a hex (`pts`), the layers to draw into (`layers`), how big a screen pixel is
// (`k`), and it moves the camera through `fit`, `focusOn`, `zoom` and `panBy`; it never touches the SVG's viewBox itself.
// This is the flat top-down SVG view the page has always had, moved here unchanged (Daniel's rule for step 1: nothing changes visibly).
// The 3D tabletop view (WebGL under a transparent SVG) will implement the same calls, so the page's drawing code does not care which view it
// was given; the top-down view stays as the Top-down option and the fallback.
(function () {
  const R = 34, SQ3 = Math.sqrt(3), NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  // hooks.rescale(): called (after a pause) when a zoom has changed the size of a screen pixel enough that screen-constant marks (placards) are redrawn
  function create(svg, hooks) {
    hooks = hooks || {};
    const mv = { R, svg, bounds: null, view: null, layers: null };
    let kLast = 0, kTimer = null;

    // ---- geometry (flat-topped hexes, even columns half a hex lower, N up)
    const parse = (l) => [parseInt(l.slice(0, 2), 10), parseInt(l.slice(2), 10)];
    mv.centre = (l) => { const [c, r] = parse(l); return [R + (c - 1) * 1.5 * R, (SQ3 / 2) * R + (r - 1) * SQ3 * R + (c % 2 === 0 ? (SQ3 / 2) * R : 0)]; };
    mv.pts = (cx, cy, k = 1) => [0, 1, 2, 3, 4, 5].map((i) => `${(cx + R * k * Math.cos(Math.PI / 3 * i)).toFixed(1)},${(cy + R * k * Math.sin(Math.PI / 3 * i)).toFixed(1)}`).join(" ");

    // ---- the board: empty layers, the terrain painted once into an image, one transparent hit polygon (and number) for every hex.
    // board = { width, height, hexes: { label: { l: level, f: features, b: building } } }; opts.labels = print the hex numbers
    mv.setBoard = (board, opts) => {
      svg.innerHTML = "";
      const W = board.width, H = board.height;
      mv.bounds = [0, 0, R * 2 + (W - 1) * 1.5 * R, SQ3 * R * H + (SQ3 / 2) * R];
      mv.layers = { map: el("g", {}, svg), dyn: el("g", {}, svg), top: el("g", {}, svg) };
      // the terrain is painted by the same code as the Lab's map preview (boardart.js), into an image under the interactive layer
      const hexes = new Map();
      for (const label of Object.keys(board.hexes)) {
        const h = board.hexes[label], f = {};
        for (const [k, v] of Object.entries(h.f || {})) f[k] = [String(v)];
        if (h.b) f.building = [];
        hexes.set(`${+label.slice(0, 2)},${+label.slice(2)}`, { level: h.l || 0, f });
      }
      const SC = 2, cv = document.createElement("canvas");
      cv.width = Math.ceil(mv.bounds[2] * SC); cv.height = Math.ceil(mv.bounds[3] * SC);
      const g2 = cv.getContext("2d"); g2.scale(SC, SC);
      BoardArt.paintHexes(g2, [{ board: { hexes }, ox: 0, oy: 0 }], R);
      el("image", { href: cv.toDataURL("image/png"), x: 0, y: 0, width: mv.bounds[2], height: mv.bounds[3], "pointer-events": "none" }, mv.layers.map);
      for (const label of Object.keys(board.hexes).sort()) {
        const [x, y] = mv.centre(label), g = el("g", { "data-hex": label }, mv.layers.map);
        el("polygon", { points: mv.pts(x, y), fill: "transparent" }, g);
        if (opts && opts.labels) { const t = el("text", { x, y: y - R * 0.62, "text-anchor": "middle", "font-size": 8, fill: "#000", "fill-opacity": ".55", "font-family": "ui-monospace,monospace", "pointer-events": "none" }, g); t.textContent = label; }
      }
      mv.fit();
    };

    // ---- the camera: a viewBox over the board (pan and zoom only)
    mv.k = () => (mv.view ? mv.view.w : svg.viewBox.baseVal.width || 1) / (svg.getBoundingClientRect().width || 1);   // map units per screen pixel
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
    return mv;
  }
  window.MapView = { create, R };
})();
