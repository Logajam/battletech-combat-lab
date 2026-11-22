// BattleROM play page: a 6 v 3 game with MASC, TAG, Arrow IV, coolant pods and AMS on the person's side, played by tapping every sheet
// (path preview, charge confirm, weapon modes, ammo bins, detail tabs, switches, End Phase, menu, looks, colour-blind mode). NOT in run_checks.py.
// Start the Lab first (see play_page_e2e.js), then:  node tests/play_page_kitchen_e2e.js /some/folder 7
const { chromium } = require('playwright');
const SP = process.argv[2], SEED = +process.argv[3] || 7;
const U = (n) => ({ unit: n, gunnery: 4, piloting: 5 });
(async () => {
  const setup = { teams: [
    { name: "Red", colour: "#4b8fd8", bot: "human", units: [U("meks/3050U/Caesar CES-4R.mtf"), U("meks/3055U/Stealth STH-2D2.mtf"), U("meks/3075/Gladiator GLD-1R (Keller).mtf"), U("meks/Golden Century/Minsk 2.mtf"), U("meks/3050U/Hatchetman HCT-5DD.mtf"), U("meks/3058Uu/Spartan SPT-N1.mtf")] },
    { name: "Blue", colour: "#d86a4b", bot: "gladiator", units: [U("Atlas AS7-K.mtf"), U("Awesome AWS-8Q.mtf"), U("Hunchback HBK-4G.mtf")] }],
    board: "16x17_Grassland_1.board", battles: 1, seed: SEED, max_turns: 100 };
  const r = await (await fetch("http://127.0.0.1:8799/api/play_start", { method: "POST", body: JSON.stringify({ setup, seed: SEED }) })).json();
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 800 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e))); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto(`http://127.0.0.1:8799/play.html?game=${r.game}&colours=${encodeURIComponent(JSON.stringify(r.colours))}`);
  const seen = {}, shots = new Set(); const shot = async (n) => { if (shots.has(n)) return; shots.add(n); await page.screenshot({ path: `${SP}/k_${n}.png` }); };
  const click = async (sel) => { await page.locator(sel).first().click({ timeout: 5000 }); };
  for (let step = 0; step < 900; step++) {
    await page.waitForFunction(() => window.__bm && (window.__bm.req || window.__bm.over), null, { timeout: 90000 });
    const st = await page.evaluate(() => ({ kind: window.__bm.req && window.__bm.req.kind, over: window.__bm.over, nat: window.__bm.req && window.__bm.req.attacks ? window.__bm.req.attacks.length : 0 }));
    if (st.over) break;
    seen[st.kind] = (seen[st.kind] || 0) + 1;
    switch (st.kind) {
      case 'move_order': await click('[data-act=pick-unit]'); break;
      case 'stand_up': await shot('stand_up'); await click('[data-act=stand][data-v="1"]'); break;
      case 'boost': await shot('boost'); await click('[data-act=boost][data-v="1"]'); break;
      case 'movement': {
        if (st.nat && !seen._atk) {
          seen._atk = 1;
          const tid = await page.evaluate(() => window.__bm.req.attacks[0].target);
          await page.locator(`[data-unit="${tid}"]`).first().dispatchEvent('click');
          await shot('attack_stops');
          await click('[data-act=atk]'); await page.waitForTimeout(600); await shot('attack_confirm');
          await click('[data-act=atk-yes]'); break;
        }
        const hex = await page.evaluate(() => { const o = window.__bm.req.options.filter(x => x.mode === 'Run').sort((a, b) => b.mp - a.mp)[0] || window.__bm.req.options[0]; return o && o.hex; });
        if (!hex) { await click('[data-act=stay]'); break; }
        await page.locator(`[data-reach="${hex}"]`).first().dispatchEvent('click');
        await page.waitForTimeout(500); await shot('move_path');
        await click('[data-act=commit]'); break;
      }
      case 'spot': await shot('spot'); await click('[data-act=spot][data-id=""]'); break;
      case 'tag': await shot('tag'); await click('[data-act=tag][data-aim]'); break;
      case 'target': await click('[data-act=target]:not([data-id=""])'); break;
      case 'declaration': {
        await page.waitForTimeout(150);
        const modeBtn = page.locator('[data-act=mode-w]'); 
        if (await modeBtn.count()) { await modeBtn.first().click(); await page.waitForTimeout(500); await shot('decl_mode'); }
        const rate = page.locator('[data-act=rate-w]'); if (await rate.count()) { await rate.first().click(); await page.waitForTimeout(400); await shot('decl_rate'); }
        const bins = page.locator('[data-act=bins-w]'); if (await bins.count() && !seen._bins) { seen._bins = 1; await bins.first().click(); await shot('decl_bins'); await page.locator('[data-act=bin-pick]').first().click(); await page.waitForTimeout(400); }
        await click('[data-act=alpha]'); await shot('decl_alpha');
        if (!seen._detail) { seen._detail = 1; await click('#det-btn'); await shot('detail_summary'); for (const t of ['armor', 'crits', 'equip']) { await click(`[data-act=tab][data-t=${t}]`); await shot('detail_' + t); } 
          // flip a switch while a question waits
          const sink = page.locator('[data-act=sw-sinks][data-d="1"]'); if (await sink.count()) { await sink.click(); await page.waitForTimeout(400); await shot('detail_sinks'); }
          await click('[data-act=detail-close]'); }
        await click('[data-act=fire-go]'); break; }
      case 'physical': await shot('physical'); { const k = page.locator('[data-act=phys]:not([data-k=""])'); if (await k.count()) await k.first().click(); else await click('[data-act=phys][data-k=""]'); } break;
      case 'end_phase': await shot('end_phase'); await click('[data-act=sw-cool][data-v=now]'); await page.waitForTimeout(300); await click('[data-act=end-go]'); break;
      default: throw new Error('kind ' + st.kind);
    }
    await page.waitForTimeout(60);
  }
  // menu, colour-blind, long-press card at the end
  await click('#menu-btn'); await shot('menu'); await click('[data-act=cvd]'); await page.waitForTimeout(200); await click('[data-act=look][data-v=w95]'); await shot('w95_cvd');
  await click('[data-act=look][data-v=slhis]'); await shot('slhis'); await click('[data-act=look][data-v=slhisd]');
  await page.mouse.click(5, 300);
  console.log('kinds', JSON.stringify(seen), 'over', await page.evaluate(() => window.__bm.over), 'errors', errs.slice(0, 6));
  await b.close();
})();
