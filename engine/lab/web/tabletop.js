"use strict";
// TABLETOP: the 3D board view (PROJECT_MAP P10, build step 2): the board, its terrain and the camera, drawn with WebGL (three.js, vendored:
// three.min.js). Perspective camera over a table (holotable or wood), hexes that rise by level with a bevel toward lower hexes, water as an
// anti-hill under a translucent surface, roads that run through hexes, pavement, woods and jungle, rocks, rubble, magma, hazardous liquid,
// buildings with windows and a band at every internal level. The code is the mockup of reference_art/battlerom_ui/battlerom_holotable_mockup.html
// (the tested, approved look), taking the engine's board JSON ({width, height, hexes: {label: {l, f, b}}}) and moved into a module.
// This step draws the board only: no units, routes or placards yet (step 3), so the page shows it as a PREVIEW. mapview.js loads this lazily, so
// the page that never asks for the 3D view never downloads three.js.
// Heights: one level is `relief` percent of 0.17 of a hex radius (280% = 0.34 inch for a 1.25 inch hex; Daniel's table terrain: 0.5 to 0.75 inch).
(function () {
  const R = 34, SQ3 = Math.sqrt(3), D2R = Math.PI / 180;
  const tmpV = new THREE.Vector3(), tmpW = new THREE.Vector3();
  const spriteTex = {};   // textures that outlive a rebuild (none yet: unit sprites come in step 3); disposeGroup keeps these
  const name = (c, r) => String(c).padStart(2, "0") + String(r).padStart(2, "0");
  const parse = (l) => [parseInt(l.slice(0, 2), 10), parseInt(l.slice(2), 10)];
  const centre = (c, r) => [R + (c - 1) * 1.5 * R, (SQ3 / 2) * R + (r - 1) * SQ3 * R + (c % 2 === 0 ? (SQ3 / 2) * R : 0)];
  const nbrs = (l) => { const [c, r] = parse(l), lo = c % 2 === 0; return [name(c + 1, r + (lo ? 1 : 0)), name(c, r + 1), name(c - 1, r + (lo ? 1 : 0)), name(c - 1, r + (lo ? 0 : -1)), name(c, r - 1), name(c + 1, r + (lo ? 0 : -1))]; };
  const RAMP = ["#2f4d2c", "#3e6335", "#55803f", "#76a35a", "#98b865", "#bfc86e", "#dbc77a", "#d2ad6a", "#c4915c", "#b07a52", "#9c6a4b", "#8a5c46", "#c9b6ab", "#e6ddd8"];
  const lvCol = (l) => RAMP[Math.max(-3, Math.min(10, l)) + 3];
  const hash = (a, b) => { let h = (a * 374761393 + b * 668265263) | 0; h = (h ^ (h >>> 13)) * 1274126177; return ((h ^ (h >>> 16)) >>> 0) / 4294967295; };

  // ---- the engine's board JSON into the hexes this view draws. A feature's value is its first parameter; a water hex's `l` is its SURFACE and
  // `water` its depth; `b` marks a building (its height in levels is `bldg_elev`). Road exits are not sent yet, so a road joins the roads and
  // pavement next to it (the exit mask of the board file, `road:1:36`, is a later addition to the board export).
  const num = (v) => (v === undefined || v === null ? 0 : (isNaN(+v) ? 1 : +v));
  const has = (f, k) => f[k] !== undefined && f[k] !== null;
  function normalise(board) {
    const W = board.width, H = board.height, hexes = new Map(), list = [];
    for (const label of Object.keys(board.hexes).sort()) {
      const b = board.hexes[label], f = b.f || {}, [c, r] = parse(label), [x, z] = centre(c, r);
      const h = { c, r, l: label, lev: b.l || 0, x, z, i: list.length, woods: num(f.woods), foliage: 0, water: num(f.water), road: has(f, "road") ? { mask: null } : null, pav: has(f, "pavement"),
        magma: num(f.magma), rough: has(f, "rough"), haz: has(f, "hazardous_liquid"), jungle: num(f.jungle), sand: has(f, "sand"), swamp: has(f, "swamp"), mud: has(f, "mud"),
        rubble: has(f, "rubble"), ice: has(f, "ice"), snow: has(f, "snow"), fire: num(f.fire), smoke: 0, mines: false, limb: false, bldcf: has(f, "bldg_cf") ? num(f.bldg_cf) : 90,
        bld: b.b ? { h: has(f, "bldg_elev") ? num(f.bldg_elev) : 2 } : null, tag: null };
      hexes.set(label, h); list.push(h);
    }
    return { W, H, hexes, list, BW: R * 2 + (W - 1) * 1.5 * R, BH: SQ3 * R * H + (SQ3 / 2) * R };
  }

  const DEFAULTS = { relief: 280, glass: 40, bevel: true, trees: "cone", skin: "holo", props: true, fx: true, cut: true };
  const PRESETS = { top: { tilt: 0, yaw: 0, persp: 20 }, seat: { tilt: 56, yaw: 0, persp: 72 }, corner: { tilt: 54, yaw: 35, persp: 72 }, para: { tilt: 55, yaw: 45, persp: 0 } };

  // host: the element the canvas goes into (it fills it); opts.settings: any of DEFAULTS
  function create(host, opts) {
    opts = opts || {};
    const ST = Object.assign({}, DEFAULTS, opts.settings || {});
    const V = { host, w: 1, h: 1, cam: Object.assign({ tx: 0, tz: 0, yaw: 0, dist: 1000 }, PRESETS.seat), pending: false, ghostKey: "", disposed: false, occupied: null, focus: null };
    V.canvas = document.createElement("canvas"); V.canvas.className = "tabletop-gl"; V.canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block;pointer-events:none"; host.appendChild(V.canvas);
    V.renderer = new THREE.WebGLRenderer({ canvas: V.canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
    V.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); V.renderer.setClearColor(0x000000, 0);
    V.scene = new THREE.Scene(); V.camera = new THREE.PerspectiveCamera(40, 1, 1, 100000); V.ray = new THREE.Raycaster(); V.plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    V.scene.add(new THREE.AmbientLight(0xffffff, 0.62)); const dl = new THREE.DirectionalLight(0xffffff, 0.55); dl.position.set(-300, 600, -200); V.scene.add(dl);
    V.request = () => { if (V.pending || V.disposed) return; V.pending = true; requestAnimationFrame(() => { V.pending = false; if (!V.disposed) V.render(); }); };
    const fovOf = (p) => 6 + p * 0.5;
    // a point of the table (x, z board units, y up) on the screen, in host pixels; ok = in front of the camera
    V.P = (x, y, z, out) => { const o = out || {}; tmpW.set(x, y, z); o.ok = tmpW.clone().applyMatrix4(V.camera.matrixWorldInverse).z < -V.camera.near; tmpV.set(x, y, z).project(V.camera); o.x = (tmpV.x * 0.5 + 0.5) * V.w; o.y = (1 - (tmpV.y * 0.5 + 0.5)) * V.h; o.d = V.camera.position.distanceTo(tmpW); return o; };
    // the point of the ground plane under a host pixel
    V.groundAt = (px, py) => { V.ray.setFromCamera({ x: (px / V.w) * 2 - 1, y: -(py / V.h) * 2 + 1 }, V.camera); const o = new THREE.Vector3(); return V.ray.ray.intersectPlane(V.plane, o) ? o : null; };
    V.applyCam = () => { const c = V.cam, th = c.tilt * D2R, ps = c.yaw * D2R, cam = V.camera; cam.fov = fovOf(c.persp);
      cam.position.set(c.tx + Math.sin(th) * Math.sin(ps) * c.dist, Math.cos(th) * c.dist, c.tz + Math.sin(th) * Math.cos(ps) * c.dist);
      cam.up.set(-Math.sin(ps), 0, -Math.cos(ps)); cam.lookAt(c.tx, 0, c.tz); cam.near = Math.max(1, c.dist * 0.04); cam.far = c.dist * 10 + (V.M ? Math.max(V.M.BW, V.M.BH) * 2 : 0); cam.aspect = V.w / V.h; cam.updateProjectionMatrix(); cam.updateMatrixWorld(); };
    V.fxTick = (tm) => { for (const f of V.fx || []) f(tm); };
    // lava, magma cracks and hazardous liquid move slowly: a light loop at 30 frames a second, only while there is something to move
    V.startAnim = () => { if (V.animOn || V.disposed) return; V.animOn = true; let last = 0; const loop = (now) => { if (V.disposed || !ST.fx || !(V.fx && V.fx.length)) { V.animOn = false; return; } if (now - last > 33 && !V.gesture && !V.pending && !document.hidden) { last = now; V.fxTick(now / 1000); V.renderer.render(V.scene, V.camera); } requestAnimationFrame(loop); }; requestAnimationFrame(loop); };
    V.size = () => { const r = host.getBoundingClientRect(); V.w = Math.max(10, r.width); V.h = Math.max(10, r.height); V.renderer.setSize(V.w, V.h, false); V.canvas.style.width = V.w + "px"; V.canvas.style.height = V.h + "px"; };
    const clampT = () => { const c = V.cam; if (!V.M) return; c.tx = Math.max(-R, Math.min(V.M.BW + R, c.tx)); c.tz = Math.max(-R, Math.min(V.M.BH + R, c.tz)); c.tilt = Math.max(0, Math.min(70, c.tilt)); c.dist = Math.max(R * 5, Math.min(Math.max(V.M.BW, V.M.BH) * 4, c.dist)); };

    // ---- fit the camera to a rectangle of the board (world units), leaving room for the info bar and the action cluster
  V.fitRegion = (x0, z0, x1, z1) => { const c = V.cam, padT = Math.min(44, V.h * 0.1), padB = Math.min(70, V.h * 0.2), top = V.maxTop + R * 2.2, pts = [];
    for (const x of [x0, x1]) for (const z of [z0, z1]) for (const y of [V.bot, top]) pts.push([x, y, z]);
    c.tx = (x0 + x1) / 2; c.tz = (z0 + z1) / 2; let d = 200; const o = {};
    const fits = () => { V.cam.dist = d; V.applyCam(); return pts.every((p) => { V.P(p[0], p[1], p[2], o); return o.ok && o.x > 6 && o.x < V.w - 6 && o.y > padT && o.y < V.h - padB; }); };
    while (!fits() && d < 1e7) d *= 1.1; V.dist0 = d; };

    V.fitAll = () => V.fitRegion(-R, -R, V.M.BW + R, V.M.BH + R);

    // ---- the board and everything that stays still while the camera moves
  V.disposeGroup = (g) => { if (!g) return; g.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => { if (m.map && m.map !== null && !Object.values(spriteTex).includes(m.map)) m.map.dispose(); m.dispose(); }); }); V.scene.remove(g); };
  V.buildStatic = () => {
    V.disposeGroup(V.stat); const g = (V.stat = new THREE.Group()); V.scene.add(g); const holo = ST.skin === "holo", HZh = R * 0.17 * ST.relief / 100, list = V.M.list; let bot = -R * 0.6;
    // water is an anti-hill: the ground lies below the level by the depth, the surface sits at the level
    const minT = Math.min(0, ...list.map((h) => (h.lev - h.water) * HZh)); bot = Math.min(bot, minT - R * 0.3);
    V.bot = bot; V.maxTop = 0; for (const h of list) { h.ground = (h.lev - h.water) * HZh; h.surf = h.lev * HZh; h.top = Math.max(bot + R * 0.2, h.ground); h.ov = h.water ? Math.max(h.surf, h.top) : h.top; if (h.top > V.maxTop) V.maxTop = h.top; if (h.bld) { const bh = Math.max(R * 0.4, Math.max(1, h.bld.h) * Math.max(R * 0.12, HZh)); if (h.top + bh > V.maxTop) V.maxTop = h.top + bh; } }
    const apoR = R * SQ3 / 2, ramps = [], rampAt = new Map(), rampH = new Map();
    for (const h of list) { h.exits = []; if (!h.road) continue; if (h.road.mask != null) { for (let d = 0; d < 6; d++) if ((h.road.mask >> d) & 1) h.exits.push((d + 4) % 6); } else nbrs(h.l).forEach((n, i) => { const o = V.M.hexes.get(n); if (o && (o.road || o.pav)) h.exits.push(i); }); }
    for (const h of list) { if (!h.road) continue; nbrs(h.l).forEach((n, i) => { const o = V.M.hexes.get(n); if (!o || !o.road || o.top <= h.top + 0.5) return; const step = o.top - h.top; if (step > HZh * 1.35 + 1) return; if (!(h.exits.includes(i) || o.exits.includes((i + 3) % 6))) return;
        const drop = ST.bevel ? R * 0.13 : 0, rise = step - drop, r = { L: h, H: o, i, step, rise, drop, len: Math.min(apoR * 0.9, Math.max(R * 0.3, rise)) }; ramps.push(r); rampAt.set(h.i + ":" + i, r); rampH.set(o.i + ":" + ((i + 3) % 6), r); }); }
    const D0 = R * 0.13, DI = R * 0.17; V.D0 = D0;
    for (const h of list) { h.mask = 0; if (ST.bevel) nbrs(h.l).forEach((n, i) => { const o = V.M.hexes.get(n); if (!o || o.top < h.top - 1) h.mask |= 1 << i; }); h.mask &= ~(h.noBevel || 0); }
    const cg = new THREE.CylinderGeometry(R, R, 1, 6, 1); cg.rotateY(Math.PI / 2); cg.clearGroups(); cg.addGroup(36, 18, 0); cg.addGroup(0, 36, 1);
    const gl = holo ? ST.glass / 100 : 0, solidMats = [new THREE.MeshLambertMaterial({ transparent: gl > 0, opacity: 1 - gl * 0.15 }), new THREE.MeshLambertMaterial({ transparent: gl > 0, opacity: 1 - gl * 0.7, depthWrite: gl < 0.45 })];
    const ghostMats = [new THREE.MeshLambertMaterial({ transparent: true, opacity: 0.26, depthWrite: false }), new THREE.MeshLambertMaterial({ transparent: true, opacity: 0.1, depthWrite: false })];
    V.tilesS = new THREE.InstancedMesh(cg, solidMats, list.length); V.tilesG = new THREE.InstancedMesh(cg, ghostMats, list.length); V.tilesG.renderOrder = 3; V.tilesS.frustumCulled = V.tilesG.frustumCulled = false;
    const tcol = (h) => { const L = (x) => new THREE.Color(x), c = L(lvCol(h.lev - h.water)); if (h.water) c.lerp(L(0x1d4f78), 0.55); if (h.sand) c.lerp(L(0xe4cd86), 0.8); if (h.swamp) c.lerp(L(0x4f6b4a), 0.65); if (h.mud) c.lerp(L(0x6b4a2f), 0.75); if (h.rubble) c.lerp(L(0x8d8a84), 0.6); if (h.rough) c.lerp(L(0x8a6f4d), 0.45); if (h.ice) c.lerp(L(0xcfeaf5), 0.8); if (h.snow) c.lerp(L(0xf2f6fa), 0.85); if (h.magma) c.lerp(L(h.magma >= 2 ? 0xc8420f : 0x3b2118), 0.85); if (h.haz) c.lerp(L(0x4a2a5e), 0.5); if (h.jungle) c.lerp(L(0x2f7a45), 0.4); if (holo) c.lerp(L(0x7fb5c8), 0.18); return c; };
    V.tileCol = list.map(tcol); g.add(V.tilesS, V.tilesG);
    V.tall = list.filter((h) => h.top > R * 0.3);
    // the cap of each tile: a thin slab whose top edge slopes down (a bevel) toward every lower neighbour; one shape per pattern of lower edges
    const capGeo = (mask) => { const a = R * SQ3 / 2, nrm = [], P = [], V0 = []; for (let i = 0; i < 6; i++) { const th = (60 * i + 30) * D2R; nrm.push([Math.cos(th), Math.sin(th)]); const tv = 60 * i * D2R; V0.push([R * Math.cos(tv), R * Math.sin(tv)]); }
      const off = (i) => ((mask >> i) & 1 ? DI : 0); for (let i = 0; i < 6; i++) { const j = (i + 5) % 6, a1 = nrm[j][0], b1 = nrm[j][1], c1 = a - off(j), a2 = nrm[i][0], b2 = nrm[i][1], c2 = a - off(i), det = a1 * b2 - a2 * b1; P.push([(c1 * b2 - c2 * b1) / det, (a1 * c2 - a2 * c1) / det]); }
      const g0 = [], g1 = [], nr0 = [], nr1 = []; const tri = (A, B, C, ex, pos, nor) => { let ux = B[0] - A[0], uy = B[1] - A[1], uz = B[2] - A[2], vx = C[0] - A[0], vy = C[1] - A[1], vz = C[2] - A[2], nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx; if (nx * ex[0] + ny * ex[1] + nz * ex[2] < 0) { [B, C] = [C, B]; nx = -nx; ny = -ny; nz = -nz; } const L = Math.hypot(nx, ny, nz) || 1; for (const p of [A, B, C]) { pos.push(p[0], p[1], p[2]); nor.push(nx / L, ny / L, nz / L); } };
      for (let i = 0; i < 6; i++) { const k = (i + 1) % 6; tri([0, 0, 0], [P[i][0], 0, P[i][1]], [P[k][0], 0, P[k][1]], [0, 1, 0], g0, nr0);
        const fl = (mask >> i) & 1, tgt = fl ? [g0, nr0] : [g1, nr1], ex = fl ? [nrm[i][0] * D0, DI, nrm[i][1] * D0] : [nrm[i][0], 0, nrm[i][1]], Pi = [P[i][0], 0, P[i][1]], Pk = [P[k][0], 0, P[k][1]], Vk = [V0[k][0], -D0, V0[k][1]], Vi = [V0[i][0], -D0, V0[i][1]];
        tri(Pi, Pk, Vk, ex, tgt[0], tgt[1]); tri(Pi, Vk, Vi, ex, tgt[0], tgt[1]); }
      const bgm = new THREE.BufferGeometry(), pos = g0.concat(g1), nor = nr0.concat(nr1); bgm.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); bgm.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3)); bgm.addGroup(0, g0.length / 3, 0); if (g1.length) bgm.addGroup(g0.length / 3, g1.length / 3, 1); return bgm; };
    V.caps = {}; const byMask = {}; for (const h of list) (byMask[h.mask] = byMask[h.mask] || []).push(h.i);
    for (const m in byMask) { const mesh = new THREE.InstancedMesh(capGeo(+m), solidMats, byMask[m].length); mesh.frustumCulled = false; mesh.userData.all = byMask[m]; g.add(mesh); V.caps[m] = mesh; }
    // terrain decals, merged by kind
    const dec = {}; const addFan = (k, h, s, off) => { s = Math.min(s, 0.84); const a = (dec[k] = dec[k] || []); const y = h.top + (off || 0.45); for (let i = 0; i < 6; i++) { const t0 = Math.PI / 3 * i, t1 = Math.PI / 3 * (i + 1); a.push(h.x, y, h.z, h.x + R * s * Math.cos(t0), y, h.z + R * s * Math.sin(t0), h.x + R * s * Math.cos(t1), y, h.z + R * s * Math.sin(t1)); } };
    for (const h of list) { if (h.woods) addFan("woods" + Math.min(3, h.woods), h, 0.82); if (h.jungle) addFan("jungle", h, 0.82); }
    const DM = { water1: [0x1e5ac8, 0.5], water2: [0x1e5ac8, 0.72], road: [0x6e6e6e, 0.7], pav: [0x6e6e6e, 0.55], rough: [0x5a3c1e, 0.4], magma: [0xe0480f, 0.85], haz: [0x8228aa, 0.7], jungle: [0x1f8a3d, 0.5], woods1: [0x3aa04a, 0.38], woods2: [0x0f5019, 0.55], woods3: [0x06300d, 0.72], bld: [0x3c3c46, 0.7] };
    for (const k in dec) { const bg = new THREE.BufferGeometry(); bg.setAttribute("position", new THREE.Float32BufferAttribute(dec[k], 3)); const m = new THREE.Mesh(bg, new THREE.MeshBasicMaterial({ color: DM[k][0], transparent: true, opacity: DM[k][1], depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 })); m.frustumCulled = false; m.renderOrder = 1; g.add(m); }
    // --- roads run through the hex to the edges they connect to; pavement is a slab with a curb where it ends
    const flat = (pos, ax, az, bx, bz, w, y, y1) => { if (y1 === undefined) y1 = y; let dx = bx - ax, dz = bz - az; const L = Math.hypot(dx, dz) || 1; dx /= L; dz /= L; const nx = -dz * w / 2, nz = dx * w / 2; pos.push(ax + nx, y, az + nz, ax - nx, y, az - nz, bx + nx, y1, bz + nz, ax - nx, y, az - nz, bx - nx, y1, bz - nz, bx + nx, y1, bz + nz); };
    const mkFlat = (pos, col, op, ro, extra) => { if (!pos.length) return null; const bg2 = new THREE.BufferGeometry(); bg2.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); const m = new THREE.Mesh(bg2, new THREE.MeshBasicMaterial(Object.assign({ color: col, transparent: op < 1, opacity: op, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }, extra || {}))); m.frustumCulled = false; m.renderOrder = ro; g.add(m); return m; };
    const fanAt = (pos, h, k, y) => { for (let i = 0; i < 6; i++) { const t0 = Math.PI / 3 * i, t1 = Math.PI / 3 * (i + 1); pos.push(h.x, y, h.z, h.x + R * k * Math.cos(t0), y, h.z + R * k * Math.sin(t0), h.x + R * k * Math.cos(t1), y, h.z + R * k * Math.sin(t1)); } };
    const roadP = [], roadC = [], pavP = [], curbP = [], apo = R * SQ3 / 2, edgeMid = (h, i) => { const th = Math.PI / 3 * i + Math.PI / 6; return [h.x + Math.cos(th) * apo, h.z + Math.sin(th) * apo]; };
    for (const h of list) {
      if (h.pav) { const y = h.top + 0.7; fanAt(pavP, h, 0.96, y); nbrs(h.l).forEach((n, i) => { const o = V.M.hexes.get(n); if (o && o.pav) return; const t0 = Math.PI / 3 * i, t1 = Math.PI / 3 * (i + 1); flat(curbP, h.x + R * 0.9 * Math.cos(t0), h.z + R * 0.9 * Math.sin(t0), h.x + R * 0.9 * Math.cos(t1), h.z + R * 0.9 * Math.sin(t1), R * 0.07, y + 0.3); }); }
      if (h.road) { const y = h.top + 1.1, ex = []; if (h.road.mask != null) { for (let d = 0; d < 6; d++) if ((h.road.mask >> d) & 1) ex.push((d + 4) % 6); } else nbrs(h.l).forEach((n, i) => { const o = V.M.hexes.get(n); if (o && (o.road || o.pav)) ex.push(i); });
        for (const i of ex) { const m = edgeMid(h, i), rp = rampAt.get(h.i + ":" + i);
          if (rp) { const th = Math.PI / 3 * i + Math.PI / 6, sx = m[0] - Math.cos(th) * rp.len, sz = m[1] - Math.sin(th) * rp.len, yh = rp.H.top - rp.drop + 1.1; flat(roadP, h.x, h.z, sx, sz, R * 0.34, y); flat(roadP, sx, sz, m[0], m[1], R * 0.34, y, yh); flat(roadC, h.x, h.z, sx, sz, R * 0.045, y + 0.25); flat(roadC, sx, sz, m[0], m[1], R * 0.045, y + 0.25, yh + 0.25); }
          else if (rampH.get(h.i + ":" + i)) { const rh = rampH.get(h.i + ":" + i), th = Math.PI / 3 * i + Math.PI / 6, sx = m[0] - Math.cos(th) * R * 0.17, sz = m[1] - Math.sin(th) * R * 0.17; flat(roadP, h.x, h.z, sx, sz, R * 0.34, y); flat(roadP, sx, sz, m[0], m[1], R * 0.34, y, y - rh.drop); flat(roadC, h.x, h.z, sx, sz, R * 0.045, y + 0.25); flat(roadC, sx, sz, m[0], m[1], R * 0.045, y + 0.25, y - rh.drop + 0.25); }
          else { flat(roadP, h.x, h.z, m[0], m[1], R * 0.34, y); flat(roadC, h.x, h.z, m[0], m[1], R * 0.045, y + 0.25); } } fanAt(roadP, h, 0.2, y); } }
    if (ramps.length) { const pos = [], nor = [], col = [], tri3 = (A, B, C, ex, c) => { let ux = B[0] - A[0], uy = B[1] - A[1], uz = B[2] - A[2], vx = C[0] - A[0], vy = C[1] - A[1], vz = C[2] - A[2], nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx; if (nx * ex[0] + ny * ex[1] + nz * ex[2] < 0) { [B, C] = [C, B]; nx = -nx; ny = -ny; nz = -nz; } const L2 = Math.hypot(nx, ny, nz) || 1; for (const q of [A, B, C]) { pos.push(q[0], q[1], q[2]); nor.push(nx / L2, ny / L2, nz / L2); col.push(c.r, c.g, c.b); } };
      for (const r of ramps) { const th = Math.PI / 3 * r.i + Math.PI / 6, nx = Math.cos(th), nz = Math.sin(th), tx = -nz, tz = nx, Mx = r.L.x + nx * apo, Mz = r.L.z + nz * apo, W = R * 0.55, yb = r.H.top - r.drop, ys = r.L.top + 0.2, c = V.tileCol[r.L.i], dk = c.clone().multiplyScalar(0.72);
        const A1 = [Mx + tx * W / 2, yb, Mz + tz * W / 2], A2 = [Mx - tx * W / 2, yb, Mz - tz * W / 2], S1 = [Mx - nx * r.len + tx * W / 2, ys, Mz - nz * r.len + tz * W / 2], S2 = [Mx - nx * r.len - tx * W / 2, ys, Mz - nz * r.len - tz * W / 2];
        tri3(A1, A2, S2, [0, 1, 0], c); tri3(A1, S2, S1, [0, 1, 0], c); tri3(A1, S1, [A1[0], ys, A1[2]], [tx, 0, tz], dk); tri3(A2, S2, [A2[0], ys, A2[2]], [-tx, 0, -tz], dk); }
      const rg = new THREE.BufferGeometry(); rg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); rg.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3)); rg.setAttribute("color", new THREE.Float32BufferAttribute(col, 3)); const rm = new THREE.Mesh(rg, new THREE.MeshLambertMaterial({ vertexColors: true })); rm.frustumCulled = false; g.add(rm); }
    mkFlat(pavP, 0x6d7179, 0.92, 1); mkFlat(curbP, 0xb3b8c0, 0.95, 1); mkFlat(roadP, 0x4d5057, 0.96, 1); mkFlat(roadC, 0xd9c36a, 0.85, 1);
    // --- water: the ground sits below by the depth, a translucent surface at the level, light lines tying surface to ground
    const wP = { 1: [], 2: [], 3: [] }, tether = [], hazP = [], lavaP = [], crustP = [], crackP = [], hazRing = [];
    const postSeen = new Set(); const isW = (l) => { const o = V.M.hexes.get(l); return !!(o && o.water); };
    for (const h of list) { if (h.water) { const k = Math.min(3, h.water), y = h.surf, nb = nbrs(h.l); fanAt(wP[k], h, 0.995, y);
        for (let i = 0; i < 6; i++) { const t0 = Math.PI / 3 * i, t1 = Math.PI / 3 * (i + 1), x0 = h.x + R * Math.cos(t0), z0 = h.z + R * Math.sin(t0), x1 = h.x + R * Math.cos(t1), z1 = h.z + R * Math.sin(t1);
          if (!isW(nb[i])) tether.push(x0, y, z0, x1, y, z1);                                   // the shoreline, once
          if (!isW(nb[(i + 5) % 6]) || !isW(nb[i])) { const key = x0.toFixed(1) + "," + z0.toFixed(1); if (!postSeen.has(key)) { postSeen.add(key); tether.push(x0, h.top + 0.5, z0, x0, y, z0); } } } }
      if (h.magma >= 2) fanAt(lavaP, h, 0.97, h.top + 0.8); else if (h.magma === 1) { fanAt(crustP, h, 0.97, h.top + 0.8); for (let k = 0; k < 5; k++) { const an = hash(h.c * 3 + k, h.r) * 6.28, an2 = an + (hash(h.c, h.r * 3 + k) - 0.5) * 1.6; flat(crackP, h.x + Math.cos(an) * R * 0.1, h.z + Math.sin(an) * R * 0.1, h.x + Math.cos(an2) * R * 0.78, h.z + Math.sin(an2) * R * 0.78, R * 0.05, h.top + 1.2); } }
      if (h.haz) { const y = h.top + R * 0.07; fanAt(hazP, h, 0.97, y); for (let i = 0; i < 6; i++) { const t0 = Math.PI / 3 * i, t1 = Math.PI / 3 * (i + 1); hazRing.push(h.x + R * 0.97 * Math.cos(t0), y + 0.4, h.z + R * 0.97 * Math.sin(t0), h.x + R * 0.97 * Math.cos(t1), y + 0.4, h.z + R * 0.97 * Math.sin(t1)); } } }
    [1, 2, 3].forEach((k) => mkFlat(wP[k], 0x2c78dc, [0, 0.36, 0.5, 0.64][k], 2.4));
    const lineMesh = (pos, col, op, add = true) => { if (!pos.length) return null; const lg2 = new THREE.BufferGeometry(); lg2.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); const m = new THREE.LineSegments(lg2, new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: op, blending: add ? THREE.AdditiveBlending : THREE.NormalBlending, depthWrite: false })); m.frustumCulled = false; m.renderOrder = 2.6; g.add(m); return m; };
    lineMesh(tether, 0xe4f1ff, 0.3, false); lineMesh(hazRing, 0xe3a8ff, 0.8);
    V.fx = []; const lavaM = mkFlat(lavaP, 0xff6a1a, 0.92, 1), crustM = mkFlat(crustP, 0x2a1610, 0.93, 1), crackM = mkFlat(crackP, 0xff7a22, 0.9, 1), hazM = mkFlat(hazP, 0xa545d8, 0.62, 2.4);
    if (lavaM) V.fx.push((tm) => { const k = 0.5 + 0.5 * Math.sin(tm * 1.6); lavaM.material.color.setRGB(1, 0.32 + 0.28 * k, 0.06); });
    if (crackM) V.fx.push((tm) => { crackM.material.opacity = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(tm * 2.1)); });
    if (hazM) V.fx.push((tm) => { hazM.material.opacity = 0.55 + 0.12 * Math.sin(tm * 1.3); });
    // hex grid lines on the tile tops
    const lp = [], lpw = []; for (const h of list) for (let i = 0; i < 6; i++) { const a = Math.PI / 3 * i, b = Math.PI / 3 * (i + 1); const yy = (h.water ? h.surf : h.top) + 0.3 - (!h.water && (h.mask >> i) & 1 ? D0 : 0); (h.water ? lpw : lp).push(h.x + R * Math.cos(a), yy, h.z + R * Math.sin(a), h.x + R * Math.cos(b), yy, h.z + R * Math.sin(b)); }
    const lg = new THREE.BufferGeometry(); lg.setAttribute("position", new THREE.Float32BufferAttribute(lp, 3)); const lines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial(holo ? { color: 0xa8cfdc, transparent: true, opacity: 0.34, blending: THREE.AdditiveBlending, depthWrite: false } : { color: 0x000000, transparent: true, opacity: 0.3, depthWrite: false })); lines.frustumCulled = false; lines.renderOrder = 2; g.add(lines); lineMesh(lpw, 0xcfe6ff, 0.07, false);
    // standing props, instanced; each knows its hex so a tile that fades to glass takes them with it
    V.propSets = []; const addProps = (geo, mat, items) => { if (!items.length) return; const mesh = new THREE.InstancedMesh(geo, mat, items.length); mesh.frustumCulled = false; g.add(mesh); V.propSets.push({ mesh, items }); return mesh; };
    const occ = (V.occupied || new Set()), HZt = Math.max(R * 0.12, HZh), Cc = (x) => new THREE.Color(x);
    if (ST.props) {
      const coneG = new THREE.ConeGeometry(1, 1, 7); coneG.translate(0, 0.5, 0); const domeG = new THREE.SphereGeometry(1, 9, 7), rockG = new THREE.DodecahedronGeometry(1, 0), prismG = new THREE.CylinderGeometry(R * 0.995, R * 0.995, 1, 6); prismG.rotateY(Math.PI / 2); prismG.translate(0, 0.5, 0); const plateG = new THREE.CylinderGeometry(R * 0.88, R * 0.88, 1, 6); plateG.rotateY(Math.PI / 2); plateG.translate(0, 0.5, 0);
      const trunkG = new THREE.CylinderGeometry(1, 1, 1, 6); trunkG.translate(0, 0.5, 0); const vineG = new THREE.CylinderGeometry(1, 1, 1, 4); vineG.translate(0, -0.5, 0); const boxG = new THREE.BoxGeometry(1, 1, 1), trunkC = Cc(0x5a3f28), vineC = Cc(0x1f6a33), girderC = [0x6e4b3a, 0x7d5642, 0x5c4538].map(Cc), jungP2 = [0x4fc765, 0x62d977, 0x3fb950].map(Cc);
      const treeP = [null, [0x56ad63, 0x6cc07a, 0x48985a], [0x1f5a2b, 0x2c7a3b, 0x17481f], [0x0f3a16, 0x16521f, 0x0b2c11]].map((q) => q && q.map(Cc)), jungP = [0x2f9e44, 0x3fb950, 0x1f8a3d].map(Cc), rockP = [0x8b7d6b, 0x7a6e5f, 0x9a8f80].map(Cc), rubP = [0x9a9892, 0x85837e, 0xaaa8a2].map(Cc), duneP = [0xdcc27a, 0xcfb56c].map(Cc);
      const trees = [], domes = [], rocks = [], blds = [], plates = [], wins = [], bands = [], trunks = [], vines = [], slabs = [], girders = [], ringAt = (h, n, k, rad) => { const an = k * (2 * Math.PI / n) + 0.5 + hash(h.c, k) * 0.2; return [h.x + Math.cos(an) * R * rad, h.z + Math.sin(an) * R * rad]; };
      const addTree = (h, x, z, rr, hh, wl, shade, k) => { const col = treeP[wl][Math.floor(shade * 3)], round = ST.trees === "round" || (ST.trees === "mixed" && hash(h.c * 5 + k, h.r + 2) > 0.5);
        if (!round) { trees.push({ h, x, y: h.top, z, sx: rr, sy: hh, sz: rr, col }); return; }
        const tr = hh * 0.42, br = rr * 1.2; trunks.push({ h, x, y: h.top, z, sx: R * 0.04, sy: tr, sz: R * 0.04, col: trunkC }); domes.push({ h, x, y: h.top + tr + br * 0.85, z, sx: br, sy: br * 1.05, sz: br, col }); };
      for (const h of list) { const isOcc = occ.has(h.l);
        if (h.woods) { const lv = Math.max(1, h.foliage || 2), th = Math.max(R * 0.4, lv * HZt), wl = Math.min(3, h.woods), nT = [0, 2, 3, 4][wl];
          if (isOcc) { const nr = [0, 4, 6, 7][wl]; for (let k = 0; k < nr; k++) { const sm = wl === 1 && k % 2 ? 0.72 : 1, p = ringAt(h, nr, k, 0.84), rr = R * 0.17 * sm; addTree(h, p[0], p[1], rr, th * sm * (0.9 + 0.2 * hash(h.r, k)), wl, hash(h.c + k, h.r * 3), k); } }
          else for (let k = 0; k < nT; k++) { const base = wl === 1 ? [[-0.24, 0.06], [0.28, -0.1]][k] : [Math.cos(k * 2.1 + h.c) * 0.38, Math.sin(k * 1.7 + h.r) * 0.34], sm = wl === 1 && k === 1 ? 0.68 : 1, rr = R * (wl === 1 ? 0.2 : 0.21 + 0.03 * wl) * sm; addTree(h, h.x + base[0] * R, h.z + base[1] * R, rr, th * sm * (wl === 1 ? 1 : 0.85 + 0.3 * hash(h.c * 7 + k, h.r)), wl, hash(h.c + k, h.r * 3), k); } }
        if (h.jungle) { const wl = Math.min(3, h.jungle), n = [0, 3, 4, 5][wl], th = Math.max(R * 0.45, Math.max(1, h.foliage || 2) * HZt) * 0.85;
          for (let k = 0; k < n; k++) { const p = isOcc ? ringAt(h, n + 1, k, 0.84) : [h.x + Math.cos(k * 2.3 + h.c) * R * 0.4, h.z + Math.sin(k * 1.9 + h.r) * R * 0.36], rr = R * (isOcc ? 0.15 : 0.25 + 0.03 * wl), tr = th * 0.5, tw = R * (isOcc ? 0.03 : 0.045);
            trunks.push({ h, x: p[0], y: h.top, z: p[1], sx: tw, sy: tr, sz: tw, col: trunkC });
            domes.push({ h, x: p[0], y: h.top + tr, z: p[1], sx: rr, sy: rr * 0.55, sz: rr, col: jungP[k % 3] });                       // the lower canopy
            domes.push({ h, x: p[0] + rr * 0.1, y: h.top + tr + rr * 0.5, z: p[1], sx: rr * 0.66, sy: rr * 0.5, sz: rr * 0.66, col: jungP2[k % 3] }); // the upper canopy
            if (!isOcc) for (let v = 0; v < 4; v++) { const an = v * 1.57 + k; vines.push({ h, x: p[0] + Math.cos(an) * rr * 0.88, y: h.top + tr - rr * 0.05, z: p[1] + Math.sin(an) * rr * 0.88, sx: R * 0.012, sy: tr * (0.5 + 0.3 * hash(k, v)), sz: R * 0.012, col: vineC }); } } }
        if (h.rough) { const n = isOcc ? 5 : 4;
          for (let k = 0; k < n; k++) { const p = isOcc ? ringAt(h, n, k, 0.84) : [h.x + Math.cos(k * 2.4 + h.c) * R * (0.2 + 0.4 * hash(h.c, k)), h.z + Math.sin(k * 1.7 + h.r) * R * (0.2 + 0.4 * hash(h.r, k + 3))], rr = R * (isOcc ? 0.07 : 0.085 + 0.05 * hash(h.c + k, h.r)); rocks.push({ h, x: p[0], y: h.top + rr * 0.25, z: p[1], sx: rr * 1.15, sy: rr * 0.85, sz: rr, ry: hash(k, h.c) * 6.28, col: rockP[k % 3] }); } }
        if (h.rubble) { const n = isOcc ? 5 : 6;
          for (let k = 0; k < n; k++) { const p = isOcc ? ringAt(h, n, k, 0.84) : [h.x + Math.cos(k * 2.4 + h.c) * R * (0.15 + 0.42 * hash(h.c, k)), h.z + Math.sin(k * 1.7 + h.r) * R * (0.15 + 0.4 * hash(h.r, k + 3))], rr = R * (isOcc ? 0.09 : 0.13 + 0.07 * hash(h.c + k, h.r));
            if (k % 2 === 0 || isOcc) rocks.push({ h, x: p[0], y: h.top + rr * 0.35, z: p[1], sx: rr * 1.2, sy: rr * 0.8, sz: rr, ry: hash(k, h.c) * 6.28, col: rubP[k % 3] });
            else slabs.push({ h, x: p[0], y: h.top + rr * 0.4, z: p[1], sx: rr * 2.0, sy: rr * 0.38, sz: rr * 1.5, ry: hash(h.r, k) * 6.28, rz: (hash(k, h.r) - 0.5) * 0.7, col: rubP[(k + 1) % 3] }); }
          if (!isOcc && hash(h.c * 3, h.r * 7) > 0.45) { const gl = R * (0.55 + 0.25 * hash(h.r, h.c)); girders.push({ h, x: h.x + R * 0.05, y: h.top + R * 0.2, z: h.z - R * 0.05, sx: gl, sy: R * 0.045, sz: R * 0.06, ry: hash(h.c, h.r) * 6.28, rz: 0.3 + 0.3 * hash(h.r, h.c + 1), col: girderC[(h.c + h.r) % 3] }); } }
        if (h.sand && !isOcc) for (let k = 0; k < 2; k++) rocks.push({ h, x: h.x + (k ? 0.26 : -0.22) * R, y: h.top, z: h.z + (k ? -0.12 : 0.14) * R, sx: R * 0.36, sy: R * 0.1, sz: R * 0.2, ry: 0.5 + k, col: duneP[k] });
        if (h.bld) { const bh = Math.max(R * 0.4, Math.max(1, h.bld.h) * HZt), cf = Math.min(1, h.bldcf / 120); const bc = Cc(0xb8bcc4).lerp(Cc(0x777c87), cf); blds.push({ h, x: h.x, y: h.top, z: h.z, sx: 1, sy: bh, sz: 1, col: bc }); plates.push({ h, x: h.x, y: h.top + bh, z: h.z, sx: 1, sy: R * 0.06, sz: 1, col: bc.clone().lerp(Cc(0xffffff), 0.3) });
          const rows = Math.max(1, Math.floor(bh / HZt)), nbb = nbrs(h.l); for (let i = 0; i < 6; i++) { const nb2 = V.M.hexes.get(nbb[i]); if (nb2 && nb2.bld) continue; const th = Math.PI / 3 * i + Math.PI / 6, nx = Math.cos(th), nz = Math.sin(th), tx = -nz, tz = nx, rr0 = R * SQ3 / 2 * 0.995 + 0.3;
            for (let rw = 0; rw < rows; rw++) for (let cl = -1; cl <= 1; cl += 2) { const lit = hash(h.c * 13 + i * 5 + rw, h.r * 7 + cl) > 0.82; wins.push({ h, x: h.x + nx * rr0 + tx * cl * R * 0.24, y: h.top + (rw + 0.25) * HZt, z: h.z + nz * rr0 + tz * cl * R * 0.24, sx: R * 0.2, sy: HZt * 0.5, sz: 0.9, ry: -(th + Math.PI / 2), col: lit ? Cc(0xf2d27a) : Cc(0x1c2a3a) }); }
            for (let k = 1; k < rows; k++) bands.push({ h, x: h.x + nx * rr0, y: h.top + k * HZt - R * 0.02, z: h.z + nz * rr0, sx: R * 0.99, sy: R * 0.04, sz: 1.3, ry: -(th + Math.PI / 2), col: Cc(0x3d424b) }); } } }
      addProps(coneG, new THREE.MeshLambertMaterial({}), trees); addProps(trunkG, new THREE.MeshLambertMaterial({}), trunks); addProps(vineG, new THREE.MeshLambertMaterial({}), vines); addProps(boxG, new THREE.MeshLambertMaterial({ flatShading: true }), slabs); addProps(boxG, new THREE.MeshLambertMaterial({ flatShading: true }), girders); addProps(domeG, new THREE.MeshLambertMaterial({}), domes); addProps(rockG, new THREE.MeshLambertMaterial({ flatShading: true }), rocks);
      addProps(prismG, new THREE.MeshLambertMaterial({ transparent: gl > 0, opacity: 1 - gl * 0.25 }), blds);
      addProps(plateG, new THREE.MeshLambertMaterial({}), plates); addProps(boxG, new THREE.MeshBasicMaterial({}), wins); addProps(boxG, new THREE.MeshLambertMaterial({}), bands);
      const be = []; for (const b of blds) { const y = b.y + b.sy + 0.4, h = b.h; for (let i = 0; i < 6; i++) { const t0 = Math.PI / 3 * i, t1 = Math.PI / 3 * (i + 1); be.push(h.x + R * 0.995 * Math.cos(t0), y, h.z + R * 0.995 * Math.sin(t0), h.x + R * 0.995 * Math.cos(t1), y, h.z + R * 0.995 * Math.sin(t1)); } }
      if (be.length) { const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.Float32BufferAttribute(be, 3)); const ln = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0xe3e8ef, transparent: true, opacity: 0.8 })); ln.frustumCulled = false; g.add(ln); } }
    // effects: fire and smoke move slowly (a low-poly flicker, a drifting fade); mines and a lost limb are flat symbols laid on the hex
    const symTex = (draw) => { const cv2 = document.createElement("canvas"); cv2.width = cv2.height = 128; draw(cv2.getContext("2d")); const tx = new THREE.CanvasTexture(cv2); return tx; };
    const mineTex = symTex((c2) => { c2.fillStyle = "rgba(200,40,40,.22)"; c2.beginPath(); c2.arc(64, 64, 60, 0, 7); c2.fill(); c2.strokeStyle = "#ff5a4a"; c2.lineWidth = 6; c2.setLineDash([14, 9]); c2.beginPath(); c2.arc(64, 64, 58, 0, 7); c2.stroke(); c2.setLineDash([]); for (const [x, y] of [[44, 50], [84, 48], [64, 84]]) { c2.fillStyle = "#15171b"; c2.beginPath(); c2.arc(x, y, 15, 0, 7); c2.fill(); c2.strokeStyle = "#15171b"; c2.lineWidth = 4; for (let k = 0; k < 8; k++) { const a2 = k * Math.PI / 4; c2.beginPath(); c2.moveTo(x + Math.cos(a2) * 15, y + Math.sin(a2) * 15); c2.lineTo(x + Math.cos(a2) * 22, y + Math.sin(a2) * 22); c2.stroke(); } c2.fillStyle = "#ff4b3a"; c2.beginPath(); c2.arc(x, y, 6, 0, 7); c2.fill(); } });
    const limbTex = symTex((c2) => { c2.fillStyle = "rgba(16,18,22,.9)"; c2.beginPath(); c2.arc(64, 64, 58, 0, 7); c2.fill(); c2.strokeStyle = "#ffb000"; c2.lineWidth = 7; c2.stroke(); c2.fillStyle = "#ffb000"; c2.beginPath(); c2.moveTo(34, 86); c2.lineTo(62, 58); c2.lineTo(74, 70); c2.lineTo(46, 98); c2.closePath(); c2.fill(); c2.beginPath(); c2.moveTo(70, 52); c2.lineTo(96, 40); c2.lineTo(100, 52); c2.lineTo(80, 66); c2.closePath(); c2.fill(); c2.strokeStyle = "#ffe08a"; c2.lineWidth = 4; c2.beginPath(); c2.moveTo(58, 42); c2.lineTo(66, 54); c2.lineTo(58, 60); c2.lineTo(66, 70); c2.stroke(); });
    const flameG = new THREE.ConeGeometry(1, 1, 5); flameG.translate(0, 0.5, 0); const puffG = new THREE.IcosahedronGeometry(1, 1);
    for (const h of list) {
      if (h.fire) { const glow = []; fanAt(glow, h, 0.8, h.top + 0.9); mkFlat(glow, 0xff5a14, 0.4, 5);
        [[0, 0.24, 0xe8420e, 0.17, 0.9], [2.1, 0.24, 0xf0560f, 0.15, 0.8], [4.2, 0.22, 0xf26a14, 0.14, 0.75], [1, 0, 0xffa11e, 0.12, 0.6], [3.4, 0.12, 0xffd23a, 0.09, 0.45]].forEach(([an, rad, col, rr, hh], k) => { const m = new THREE.Mesh(flameG, new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.92, depthWrite: false })); m.renderOrder = 6; g.add(m); const ph = hash(h.c + k, h.r) * 6.28;
          V.fx.push((tm) => { m.position.set(h.x + Math.cos(an) * R * rad, h.top, h.z + Math.sin(an) * R * rad); const f = 0.78 + 0.3 * Math.sin(tm * 6.5 + ph) + 0.1 * Math.sin(tm * 11 + ph * 2); m.scale.set(R * rr * (1.05 - 0.15 * f), HZt * (hh / 0.9) * 1.15 * f, R * rr * (1.05 - 0.15 * f)); m.rotation.z = 0.14 * Math.sin(tm * 3 + ph); m.rotation.y = tm * 1.2 + ph; }); }); }
      if (h.smoke) { const heavy = h.smoke >= 2, n = heavy ? 8 : 4, cap = 2 * HZt; for (let k = 0; k < n; k++) { const m = new THREE.Mesh(puffG, new THREE.MeshBasicMaterial({ color: heavy ? 0x6f747c : 0x9ea4ac, transparent: true, opacity: 0, depthWrite: false })); m.renderOrder = 7; g.add(m); const ph = k / n + hash(h.c, k) * 0.1;
          V.fx.push((tm) => { const f = (tm * 0.1 + ph) % 1, s2 = R * (0.3 + 0.2 * f) * (heavy ? 1.2 : 1); m.position.set(h.x + Math.sin(tm * 0.5 + ph * 9) * R * 0.2 + f * R * 0.25 + (k % 2 ? 0.2 : -0.15) * R, h.top + s2 * 0.45 + f * Math.max(0, cap - s2 * 1.3), h.z + Math.cos(tm * 0.4 + ph * 7) * R * 0.18); m.scale.set(s2, s2 * 0.7, s2); m.material.opacity = (heavy ? 0.82 : 0.55) * Math.min(1, 3.2 * Math.sin(Math.PI * f)) * (0.8 + 0.2 * Math.sin(tm * 1.7 + ph * 11)); }); } }
      if (h.haz) for (let k = 0; k < 3; k++) { const m = new THREE.Mesh(puffG, new THREE.MeshBasicMaterial({ color: 0xe1a6ff, transparent: true, opacity: 0.7, depthWrite: false })); m.renderOrder = 7; g.add(m); const ph = hash(h.c + k, h.r) * 6.28; V.fx.push((tm) => { const f = (tm * 0.35 + ph) % 1; m.position.set(h.x + Math.cos(ph * 3 + k * 2) * R * 0.45, h.top + R * 0.07 + f * R * 0.35, h.z + Math.sin(ph * 5 + k) * R * 0.4); const s2 = R * 0.07 * (1 - 0.4 * f); m.scale.set(s2, s2, s2); m.material.opacity = 0.75 * (1 - f); }); }
      if (h.mines) { const m = new THREE.Mesh(new THREE.PlaneGeometry(R * 1.6, R * 1.6), new THREE.MeshBasicMaterial({ map: mineTex, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 })); m.rotation.x = -Math.PI / 2; m.position.set(h.x, h.top + 1.4, h.z); m.renderOrder = 6; g.add(m); }
      if (h.limb) { const m = new THREE.Mesh(new THREE.PlaneGeometry(R * 0.55, R * 0.55), new THREE.MeshBasicMaterial({ map: limbTex, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 })); m.rotation.x = -Math.PI / 2; m.position.set(h.x + R * 0.52, h.top + 1.6, h.z - R * 0.42); m.renderOrder = 6; g.add(m); } }
    // the floor
    const ext = Math.max(V.M.BW, V.M.BH), fl = document.createElement("canvas"); fl.width = fl.height = 256; const f2 = fl.getContext("2d");
    if (holo) { f2.fillStyle = "rgba(0,0,0,0)"; f2.clearRect(0, 0, 256, 256); f2.strokeStyle = "rgba(120,200,230,.28)"; f2.lineWidth = 2; f2.strokeRect(1, 1, 254, 254); f2.strokeStyle = "rgba(120,200,230,.1)"; f2.lineWidth = 1; for (let i = 64; i < 256; i += 64) { f2.beginPath(); f2.moveTo(i, 0); f2.lineTo(i, 256); f2.moveTo(0, i); f2.lineTo(256, i); f2.stroke(); } }
    else { for (let y = 0; y < 256; y += 32) { f2.fillStyle = ["#6b4a30", "#5a3d27", "#74533a", "#62432b"][(y / 32) % 4]; f2.fillRect(0, y, 256, 32); f2.fillStyle = "rgba(0,0,0,.45)"; f2.fillRect(0, y, 256, 2); for (let k = 0; k < 40; k++) { f2.fillStyle = `rgba(0,0,0,${0.03 + 0.05 * Math.random()})`; f2.fillRect(Math.random() * 256, y + 3 + Math.random() * 27, 20 + Math.random() * 60, 1); } } }
    const ft = new THREE.CanvasTexture(fl); ft.wrapS = ft.wrapT = THREE.RepeatWrapping; const fs = ext * 5, rep = fs / (holo ? 190 : 260); ft.repeat.set(rep, rep);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(fs, fs), holo ? new THREE.MeshBasicMaterial({ map: ft, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }) : new THREE.MeshLambertMaterial({ map: ft })); floor.rotation.x = -Math.PI / 2; floor.position.set(V.M.BW / 2, bot - R * 0.35, V.M.BH / 2); floor.renderOrder = 0; g.add(floor);
    if (holo) { const rim = [[-R, -R], [V.M.BW + R, -R], [V.M.BW + R, V.M.BH + R], [-R, V.M.BH + R]], rp = []; for (let i = 0; i < 4; i++) { const a = rim[i], b = rim[(i + 1) % 4]; rp.push(a[0], bot - R * 0.3, a[1], b[0], bot - R * 0.3, b[1]); } const rg = new THREE.BufferGeometry(); rg.setAttribute("position", new THREE.Float32BufferAttribute(rp, 3)); g.add(new THREE.LineSegments(rg, new THREE.LineBasicMaterial({ color: 0x8fe0ff, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending }))); }
    else { const sl = new THREE.Mesh(new THREE.BoxGeometry(V.M.BW + 2 * R * 0.55, R * 0.3, V.M.BH + 2 * R * 0.55), new THREE.MeshLambertMaterial({ color: 0x3b4a3a })); sl.position.set(V.M.BW / 2, bot - R * 0.15, V.M.BH / 2); g.add(sl); }
    V.ghostKey = "#"; V.applyGhost(new Set()); V.fxTick(1.3); if (ST.fx) V.startAnim();
  };
  // tiles: solid, or glass where they hide a unit, the route or the target
  V.applyGhost = (ghost) => {
    const key = [...ghost].sort((a, b) => a - b).join(","); if (key === V.ghostKey) return; V.ghostKey = key; const list = V.M.list, m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new THREE.Vector3(), s = new THREE.Vector3(); let ns = 0, ng = 0;
    const sIds = []; for (const h of list) { if (ghost.has(h.i)) { p.set(h.x, (h.top + V.bot) / 2, h.z); s.set(1, h.top - V.bot, 1); m4.compose(p, q, s); V.tilesG.setMatrixAt(ng, m4); V.tilesG.setColorAt(ng++, V.tileCol[h.i]); } else { const tp = h.top - V.D0; p.set(h.x, (tp + V.bot) / 2, h.z); s.set(1, tp - V.bot, 1); m4.compose(p, q, s); V.tilesS.setMatrixAt(ns, m4); V.tilesS.setColorAt(ns, V.tileCol[h.i]); sIds[ns++] = h.i; } }
    V.tilesS.userData.ids = sIds; s.set(1, 1, 1);
    for (const m in V.caps) { const mesh = V.caps[m], ids = []; let n = 0; for (const i of mesh.userData.all) { if (ghost.has(i)) continue; const h = list[i]; p.set(h.x, h.top, h.z); m4.compose(p, q, s); mesh.setMatrixAt(n, m4); mesh.setColorAt(n, V.tileCol[i]); ids[n++] = i; } mesh.count = n; mesh.userData.ids = ids; mesh.instanceMatrix.needsUpdate = true; if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true; }
    V.tilesS.count = ns; V.tilesG.count = ng; V.tilesS.instanceMatrix.needsUpdate = V.tilesG.instanceMatrix.needsUpdate = true; if (V.tilesS.instanceColor) V.tilesS.instanceColor.needsUpdate = true; if (V.tilesG.instanceColor) V.tilesG.instanceColor.needsUpdate = true;
    { const q2 = new THREE.Quaternion(), eul = new THREE.Euler(0, 0, 0, "YXZ"); for (const ps of V.propSets || []) { ps.items.forEach((it, i) => { if (ghost.has(it.h.i)) s.set(0, 0, 0); else s.set(it.sx, it.sy, it.sz); q2.setFromEuler(eul.set(0, it.ry || 0, it.rz || 0)); p.set(it.x, it.y, it.z); m4.compose(p, q2, s); ps.mesh.setMatrixAt(i, m4); ps.mesh.setColorAt(i, it.col); }); ps.mesh.instanceMatrix.needsUpdate = true; if (ps.mesh.instanceColor) ps.mesh.instanceColor.needsUpdate = true; } }
  };
  const holo2 = () => ST.skin === "holo";
  V.computeGhost = () => { const ghost = new Set(); if (!ST.cut || !V.focus || !V.tall.length) return ghost; const a = {}, b = {}, o = {}, cp = V.camera.position;
    for (const f of V.focus) { V.P(f.x, f.y, f.z, a);
      for (const h of V.tall) { if (h.l === f.hex || h.top <= f.y + R * 0.15) continue; V.P(h.x, h.top, h.z, b); if (b.d >= a.d - R * 0.3) continue; if (Math.abs(a.x - b.x) > 140) continue; V.P(h.x + R, h.top, h.z, o); const rp = Math.hypot(o.x - b.x, o.y - b.y); V.P(h.x, V.bot, h.z, o);
        if (Math.abs(a.x - b.x) < rp * 1.08 && a.y > b.y - rp * 0.9 && a.y < o.y + rp * 0.5) ghost.add(h.i); } }
    return ghost; };

    V.render = () => { V.applyCam(); const gk = V.computeGhost(); V.applyGhost(gk); V.renderer.render(V.scene, V.camera); V.lastInfo = V.renderer.info.render; if (tt.onRender) tt.onRender(); };

    // ---- the public calls (the map view, mapview.js, forwards to these). Client coordinates in, host pixels inside.
    const local = (x, y) => { const r = host.getBoundingClientRect(); return { x: x - r.left, y: y - r.top }; };
    let two = null;
    const ro = new ResizeObserver(() => { if (V.disposed) return; V.size(); V.request(); }); ro.observe(host);
    const tt = {
      settings: ST, onRender: null,
      // the board: build it and look at all of it
      setBoard(board) { V.M = normalise(board); V.size(); V.buildStatic(); tt.fit(); },
      // set a setting (relief, glass, bevel, trees, skin, props, fx, cut) and rebuild what depends on it
      set(patch) { Object.assign(ST, patch); if (V.M) { V.size(); V.buildStatic(); V.request(); } },
      // hexes (labels) with a unit on them: a woods hex then gets a ring of small trees round the base (step 3 fills this)
      setOccupied(labels) { V.occupied = new Set(labels); if (V.M) { V.buildStatic(); V.request(); } },
      // points the cut-away keeps visible: tiles in front of them fade to glass (step 3 fills this)
      setFocus(list) { V.focus = (list || []).map((f) => { const h = V.M.hexes.get(f.label); return h ? { x: h.x, y: h.top + (f.up || 0), z: h.z, hex: f.label } : null; }).filter(Boolean); V.request(); },
      fit() { if (!V.M) return; V.size(); V.fitAll(); V.request(); },
      // fit the hexes (labels) with a margin of marginHexes, never closer than about twelve hexes across
      focusOn(labels, marginHexes) {
        if (!V.M || !labels.length) return tt.fit();
        const hs = labels.map((l) => V.M.hexes.get(l)).filter(Boolean); if (!hs.length) return tt.fit();
        const m = (marginHexes || 4) * 1.5 * R, xs = hs.map((h) => h.x), zs = hs.map((h) => h.z); let x0 = Math.min(...xs) - m, x1 = Math.max(...xs) + m, z0 = Math.min(...zs) - m, z1 = Math.max(...zs) + m;
        const minW = 12 * 1.5 * R; if (x1 - x0 < minW) { const c = (x0 + x1) / 2; x0 = c - minW / 2; x1 = c + minW / 2; } if (z1 - z0 < minW * 0.7) { const c = (z0 + z1) / 2; z0 = c - minW * 0.35; z1 = c + minW * 0.35; }
        V.size(); V.fitRegion(Math.max(-R, x0), Math.max(-R, z0), Math.min(V.M.BW + R, x1), Math.min(V.M.BH + R, z1)); V.request();
      },
      preset(nameKey) { const p = PRESETS[nameKey]; if (!p) return; Object.assign(V.cam, p); clampT(); V.request(); },
      cycleTilt() { const a = [0, 34, 56], n = a.find((x) => x > V.cam.tilt + 3); V.cam.tilt = n === undefined ? a[0] : n; V.request(); },
      // zoom by f (below 1 zooms in) about a client point, keeping the ground under it
      zoom(f, cx, cy) { V.applyCam(); const p = cx == null ? { x: V.w / 2, y: V.h / 2 } : local(cx, cy), g0 = V.groundAt(p.x, p.y); V.cam.dist *= f; clampT(); V.applyCam(); const g1 = V.groundAt(p.x, p.y); if (g0 && g1) { V.cam.tx += g0.x - g1.x; V.cam.tz += g0.z - g1.z; } clampT(); V.request(); },
      // a finger (or the mouse) at client (x, y) has moved by (dx, dy): the ground follows it
      panBy(dx, dy, x, y) { V.applyCam(); const p = local(x, y), g0 = V.groundAt(p.x - dx, p.y - dy), g1 = V.groundAt(p.x, p.y); if (g0 && g1) { V.cam.tx += g0.x - g1.x; V.cam.tz += g0.z - g1.z; clampT(); } V.request(); },
      // right-drag: turn and tilt
      orbitBy(dx, dy) { V.cam.yaw -= dx * 0.4; V.cam.tilt -= dy * 0.3; clampT(); V.request(); },
      // two fingers at client points a and b (called on every move): pinch, twist and pan together with the ground held under the fingers; two
      // fingers moving up or down together tilt. The first call pins the ground under the fingers; the kind of gesture is decided once both have moved.
      pinch(a, b) {
        const A = local(a.x, a.y), B = local(b.x, b.y);
        if (!two) { V.applyCam(); two = { lock: null, A0: A, B0: B, gA: V.groundAt(A.x, A.y), gB: V.groundAt(B.x, B.y), tilt0: V.cam.tilt }; V.gesture = true; return; }
        const g = two, d = Math.hypot(A.x - B.x, A.y - B.y), d0 = Math.hypot(g.A0.x - g.B0.x, g.A0.y - g.B0.y);
        if (!g.lock) { const v1 = { x: A.x - g.A0.x, y: A.y - g.A0.y }, v2 = { x: B.x - g.B0.x, y: B.y - g.B0.y }, m1 = Math.hypot(v1.x, v1.y), m2 = Math.hypot(v2.x, v2.y);
          let tw = Math.atan2(B.y - A.y, B.x - A.x) - Math.atan2(g.B0.y - g.A0.y, g.B0.x - g.A0.x); tw = Math.atan2(Math.sin(tw), Math.cos(tw)); const pinchAmt = Math.abs(d - d0);
          if (m1 > 8 && m2 > 8) g.lock = (v1.x * v2.x + v1.y * v2.y) / (m1 * m2) > 0.85 && Math.abs(v1.y + v2.y) > 1.4 * Math.abs(v1.x + v2.x) && pinchAmt < 14 && Math.abs(tw) < 0.2 ? "tilt" : "free";
          else if (pinchAmt > 16 || Math.abs(tw) > 0.25 || Math.max(m1, m2) > 40) g.lock = "free"; }
        if (g.lock === "tilt") { V.cam.tilt = g.tilt0 - ((A.y + B.y) / 2 - (g.A0.y + g.B0.y) / 2) * 0.3; clampT(); }
        else if (g.lock === "free" && g.gA && g.gB) { V.applyCam();
          for (let it = 0; it < 4; it++) { const A1 = V.groundAt(A.x, A.y), B1 = V.groundAt(B.x, B.y); if (!A1 || !B1) break;
            const v0 = { x: g.gB.x - g.gA.x, z: g.gB.z - g.gA.z }, v1 = { x: B1.x - A1.x, z: B1.z - A1.z }, da = Math.atan2(v0.x * v1.z - v0.z * v1.x, v0.x * v1.x + v0.z * v1.z), l0 = Math.hypot(v0.x, v0.z), l1 = Math.hypot(v1.x, v1.z);
            V.cam.yaw += da / D2R; if (l1 > 1) V.cam.dist *= l0 / l1; clampT(); V.applyCam(); const cn = V.groundAt((A.x + B.x) / 2, (A.y + B.y) / 2); if (cn) { V.cam.tx += (g.gA.x + g.gB.x) / 2 - cn.x; V.cam.tz += (g.gA.z + g.gB.z) / 2 - cn.z; } clampT(); V.applyCam(); } }
        V.request();
      },
      pinchEnd() { two = null; V.gesture = false; V.request(); },
      // the hex under a client point, or null
      hexAt(cx, cy) { if (!V.M || !V.tilesS) return null; const p = local(cx, cy); V.applyCam(); const meshes = [V.tilesS, ...Object.values(V.caps)];
        // a ray through the exact centre of a hex can slip between the six triangles that meet there: try a fraction of a pixel to each side too
        for (const [ox, oy] of [[0, 0], [0.7, 0], [-0.7, 0], [0, 0.7], [0, -0.7]]) { V.ray.setFromCamera({ x: ((p.x + ox) / V.w) * 2 - 1, y: -((p.y + oy) / V.h) * 2 + 1 }, V.camera);
          const hit = V.ray.intersectObjects(meshes, false); if (hit.length) { const i = hit[0].object.userData.ids[hit[0].instanceId]; if (i !== undefined) return V.M.list[i].l; } }
        return null; },
      // a point of a hex on the screen: dx, dy in hex radii from its centre (east, south), up in world units above the tile top. Host pixels, the scale of the hex there (pixels per board unit).
      project(label, dx, dy, up) { const h = V.M && V.M.hexes.get(label); if (!h) return null; V.applyCam(); const o = V.P(h.x + (dx || 0) * R, h.top + (up || 0), h.z + (dy || 0) * R), e = V.P(h.x + (dx || 0) * R + R, h.top + (up || 0), h.z + (dy || 0) * R); o.scale = Math.hypot(e.x - o.x, e.y - o.y) / R; return o; },
      // the hex's centre on the screen relative to the page (for DOM marks laid over the map)
      render() { V.render(); }, resize() { V.size(); V.request(); }, info() { return V.lastInfo; },
      camera: V.cam, three: V,
      dispose() { V.disposed = true; V.animOn = false; ro.disconnect(); V.disposeGroup(V.stat); V.renderer.dispose(); try { V.renderer.forceContextLoss(); } catch (e) { /* already lost */ } V.canvas.remove(); },
    };
    return tt;
  }
  window.Tabletop = { create, PRESETS, DEFAULTS };
})();
