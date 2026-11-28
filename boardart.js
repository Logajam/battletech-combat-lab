// BOARD ART: the one way a map's hexes are painted, shared by the Lab's map preview (lab.js) and the play page (play.js), so a
// map looks the same in the map browser and in a game. Heights are shown the way MegaMek's board view does: a colour ramp from
// the low ground (dark green) up through yellow and brown to white, so a ridge or a pit reads at a glance; terrain is laid
// over the height colour.
"use strict";
(function () {
  const SQ = Math.sqrt(3);
  const LEVEL_RAMP = { "-3": "#2f4d2c", "-2": "#3e6335", "-1": "#55803f", 0: "#76a35a", 1: "#98b865", 2: "#bfc86e", 3: "#dbc77a", 4: "#d2ad6a", 5: "#c4915c", 6: "#b07a52", 7: "#9c6a4b", 8: "#8a5c46", 9: "#c9b6ab", 10: "#e6ddd8", 11: "#ffffff" };
  const levelColour = (l) => LEVEL_RAMP[Math.max(-3, Math.min(11, l))];
  // paint the hexes of `cells` ([{board: {hexes: Map "col,row" -> {level, f}}, ox, oy}]) into the 2D context g, hexes of radius R
  function paintHexes(g, cells, R) {
    const centre = (c, r) => [R + (c - 1) * 1.5 * R, (SQ / 2) * R + (r - 1) * SQ * R + (c % 2 === 0 ? (SQ / 2) * R : 0)];
    const path = (x, y, k) => { g.beginPath(); for (let i = 0; i < 6; i++) { const a = Math.PI / 3 * i; g.lineTo(x + k * R * Math.cos(a), y + k * R * Math.sin(a)); } g.closePath(); };
    const showLevels = R >= 11;
    for (const { board, ox, oy } of cells) {
      for (const [key, hex] of board.hexes) {
        const [c0, r0] = key.split(",").map(Number), c = c0 + ox, r = r0 + oy, [x, y] = centre(c, r), f = hex.f;
        path(x, y, 1); g.fillStyle = levelColour(hex.level); g.fill();
        const wood = f.woods || f.jungle, water = f.water && f.water[0] !== "0";
        if (water) { g.fillStyle = `rgba(30,90,200,${Math.min(0.85, 0.45 + 0.15 * (+f.water[0] || 1))})`; path(x, y, 1); g.fill(); }
        if (f.magma) { g.fillStyle = "rgba(220,60,10,.7)"; path(x, y, 1); g.fill(); }
        if (f.hazardous_liquid) { g.fillStyle = "rgba(130,40,170,.6)"; path(x, y, 1); g.fill(); }
        if (f.pavement || f.road) { g.fillStyle = "rgba(110,110,110,.55)"; path(x, y, f.pavement ? 1 : 0.45); g.fill(); }
        if (f.rough || f.rubble) { g.fillStyle = "rgba(90,60,30,.45)"; for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(x + (i - 1) * R * 0.4, y + (i % 2 ? 0.25 : -0.25) * R, R * 0.15, 0, 7); g.fill(); } }
        if (f.sand) { g.fillStyle = "rgba(240,215,110,.5)"; path(x, y, 1); g.fill(); }
        if (f.ice) { g.fillStyle = "rgba(220,245,255,.65)"; path(x, y, 1); g.fill(); }
        if (wood) { g.fillStyle = `rgba(15,80,25,${String(wood[0]) === "1" ? 0.5 : 0.75})`; path(x, y, 0.72); g.fill(); }
        if (f.building) { g.fillStyle = "rgba(60,60,70,.85)"; g.fillRect(x - R * 0.45, y - R * 0.4, R * 0.9, R * 0.8); }
        path(x, y, 1); g.strokeStyle = "rgba(0,0,0,.28)"; g.lineWidth = 0.6; g.stroke();
        if (showLevels && hex.level !== 0) { g.fillStyle = hex.level > 8 || hex.level < -1 ? "#fff" : "#222"; g.font = `${Math.round(R * 0.5)}px sans-serif`; g.textAlign = "center"; g.fillText(hex.level, x, y + R * 0.7); }
      }
    }
  }
  window.BoardArt = { levelColour, paintHexes };
})();
