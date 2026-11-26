// BattleROM play page, end to end in a browser (Playwright), THE OVERLAY UI (INTEGRATION__UI_SYNC.md Section 14). NOT part of run_checks.py
// (check_web_play.py plays the page as part of the website checks); this one is for looking: it plays a battle by tapping the real controls
// and takes a screenshot of each new kind of question upright (390x844), sideways (844x390) and on a desktop (1280x800).
// Start the Lab first:  BTSIM_ROOT=$PWD engine/target/release/combatlab --no-browser --port 8799 --web engine/lab/web
// then:  node tests/play_page_e2e.js /some/folder [view=top|3d] [max steps]
const { chromium } = require('playwright');
const SP = process.argv[2], VIEW = process.argv[3] || "3d", MAX = +(process.argv[4] || 600);
const SIZES = [["up", 390, 844], ["side", 844, 390], ["desk", 1280, 800]];
(async () => {
  const setup = { teams: [
    { name: "Red", colour: "#4b8fd8", bot: "human", units: [{ unit: "Atlas AS7-K.mtf", gunnery: 4, piloting: 5 }, { unit: "Griffin GRF-1N.mtf", gunnery: 4, piloting: 5 }] },
    { name: "Blue", colour: "#d86a4b", bot: "gladiator", units: [{ unit: "Awesome AWS-8Q.mtf", gunnery: 4, piloting: 5 }, { unit: "Hunchback HBK-4G.mtf", gunnery: 4, piloting: 5 }] }],
    board: "16x17_Grassland_1.board", battles: 1, seed: 11, max_turns: 100 };
  const r = await (await fetch("http://127.0.0.1:8799/api/play_start", { method: "POST", body: JSON.stringify({ setup }) })).json();
  if (r.error) { console.log("start", r.error); process.exit(1); }
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: false });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', (e) => errs.push(String(e.stack || e))); page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto(`http://127.0.0.1:8799/play.html?game=${r.game}&view=${VIEW}&colours=${encodeURIComponent(JSON.stringify(r.colours))}`);
  const seen = new Set(), log = [];
  const shoot = async (name) => { for (const [n, w, h] of SIZES) { await page.setViewportSize({ width: w, height: h }); await page.waitForTimeout(450); await page.screenshot({ path: `${SP}/${name}_${n}.png` }); } await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300); };
  const hold = async () => { const c = page.locator('.commit:not([disabled])').first(); if (!(await c.count())) return false; const bb = await c.boundingBox(); if (!bb) return false;
    await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await page.mouse.down(); await page.waitForTimeout(800); await page.mouse.up(); return true; };
  const tap = async (sel) => { const l = page.locator(sel).first(); if (!(await l.count())) return false; const bb = await l.boundingBox(); if (!bb) return false; await page.mouse.click(bb.x + bb.width / 2, bb.y + bb.height / 2); return true; };
  for (let step = 0; step < MAX; step++) {
    await page.waitForFunction(() => window.__bm && (window.__bm.req || window.__bm.over), null, { timeout: 120000 });
    if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) { if (!seen.has("report")) { seen.add("report"); await shoot("report"); } await tap('[data-act="report-close"]'); }
    const st = await page.evaluate(() => ({ kind: window.__bm.req && window.__bm.req.kind, over: window.__bm.over, seq: window.__bm.seq }));
    if (st.over) break;
    const k = st.kind, first = !seen.has(k); seen.add(k); log.push(k);
    if (k === 'move_order' || k === 'movement' || k === 'stand_up') {
      await page.waitForFunction(() => !!window.__bm.mv, null, { timeout: 30000 }).catch(() => {});
      const hex = await page.evaluate(() => { const v = __bm.mv; if (!v) return null; const o = v.options.filter((x) => x.mode === 'Walk' && x.hex !== (window.__bm.units.find((u) => u.id === v.unit) || {}).hex).sort((a, b) => b.mp - a.mp)[0] || v.options[0]; return o && o.hex; });
      if (first) await shoot(`${k}_0`);
      if (hex) { await page.locator(`[data-reach="${hex}"]`).first().dispatchEvent('click'); await page.waitForTimeout(400); }
      if (first) await shoot(`${k}_1`);
      await hold();
    } else if (k === 'target' || k === 'declaration') {
      await page.waitForFunction(() => !!window.__bm.decl || (window.__bm.fire && window.__bm.fire.pvt.size), null, { timeout: 30000 }).catch(() => {});
      await page.waitForTimeout(300);
      if (first) await shoot(`${k}_0`);
      for (let i = 0; i < 3; i++) if (!(await tap('#ring .wb.rdy'))) break; else await page.waitForTimeout(150);
      if (first) { await shoot(`${k}_1`); await page.locator('#ring .wb .tn').first().dispatchEvent('pointerdown').catch(() => {}); }
      if (first) { const tn = page.locator('#ring .wb .tn').first(); if (await tn.count()) { const bb = await tn.boundingBox(); await page.mouse.move(bb.x + 4, bb.y + 4); await page.mouse.down(); await page.waitForTimeout(700); await page.mouse.up(); await page.waitForTimeout(300); await shoot(`${k}_tohit`); await page.keyboard.press('Escape'); } }
      await hold();
    } else if (k === 'physical') {
      if (first) await shoot(`${k}_0`);
      await tap('#ring .wb.rdy'); await page.waitForTimeout(200);
      if (first) await shoot(`${k}_1`);
      await hold();
    } else if (k === 'end_phase') { if (first) await shoot(k); await hold(); }
    else if (k === 'deploy') { await page.locator('[data-deploy]').first().dispatchEvent('click'); await page.waitForTimeout(200); if (first) await shoot(k); await hold(); }
    else if (k === 'spot') await tap('[data-act="spot"][data-id=""]');
    else if (k === 'tag') await tap('[data-act="tag"][data-id=""]');
    else if (k === 'boost' || k === 'jump_boost') { if (first) await shoot(k); await tap(`[data-act="${k === 'boost' ? 'boost' : 'jump-boost'}"][data-v="0"]`); }
    await page.waitForFunction((s) => !window.__bm.req || window.__bm.seq !== s || window.__bm.over, st.seq, { timeout: 120000 }).catch(() => { errs.push("stuck at " + k); });
    if (errs.some((e) => e.startsWith("stuck"))) { await page.screenshot({ path: `${SP}/stuck.png` }); break; }
  }
  const over = await page.evaluate(() => window.__bm.over);
  await shoot("end");
  console.log(JSON.stringify({ kinds: [...seen], steps: log.length, over, errors: errs.slice(0, 8) }));
  await b.close();
})();
