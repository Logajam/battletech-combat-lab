// BattleROM play page, VISUAL REGRESSION driver (P10 build steps). NOT part of run_checks.py (needs node + Playwright + the Lab server).
// Start the Lab from the page folder:  BTSIM_ROOT=$PWD engine/target/release/combatlab --no-browser --port 8799 --web engine/lab/web
// Then:  node tests/play_page_visual.js <outdir> [port] [WxH]   (plays a scripted battle, screenshots every distinct state)
// Run it before and after a change meant to leave the picture alone, then:  python tests/compare_shots.py <dirA> <dirB> [tolerance in pixels]
// (Two runs of the SAME code differ by a few edge pixels, so the default tolerance is 8 pixels an image.)
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const OUT = process.argv[2], PORT = +(process.argv[3] || 8799), [VW, VH] = (process.argv[4] || '390x780').split('x').map(Number);
fs.mkdirSync(OUT, { recursive: true });
const setup = { teams: [
  { name: 'Red', colour: '#4b8fd8', bot: 'human', units: [{ unit: 'Atlas AS7-K.mtf', gunnery: 4, piloting: 5 }, { unit: 'Griffin GRF-1N.mtf', gunnery: 4, piloting: 5 }] },
  { name: 'Blue', colour: '#d86a4b', bot: 'gladiator', units: [{ unit: 'Awesome AWS-8Q.mtf', gunnery: 4, piloting: 5 }, { unit: 'Hunchback HBK-4G.mtf', gunnery: 4, piloting: 5 }] }],
  board: '16x17_Hilltops_1.board', battles: 1, seed: 11, max_turns: 100 };
(async () => {
  const r = await (await fetch(`http://127.0.0.1:${PORT}/api/play_start`, { method: 'POST', body: JSON.stringify({ setup }) })).json();
  if (r.error) { console.log('start error', r.error); process.exit(1); }
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: VW, height: VH }, deviceScaleFactor: 1 }); const page = await ctx.newPage();
  const errs = []; page.on('pageerror', (e) => errs.push(String(e))); page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto(`http://127.0.0.1:${PORT}/play.html?game=${r.game}&colours=${encodeURIComponent(JSON.stringify(r.colours))}`);
  let n = 0; const shot = async (tag) => { await page.waitForTimeout(250); await page.screenshot({ path: path.join(OUT, `${String(n++).padStart(3, '0')}_${tag}.png`) }); };
  const tap = (act, extra) => page.locator(`[data-act="${act}"]${extra || ''}`).first().click({ timeout: 4000 });
  const hold = async (act) => { const bb = await page.locator(`[data-act="${act}"]`).first().boundingBox(); await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await page.mouse.down(); await page.waitForTimeout(900); await page.mouse.up(); };
  let did = {};
  for (let step = 0; step < 250; step++) {
    await page.waitForFunction(() => window.__bm && (window.__bm.req || window.__bm.over), null, { timeout: 60000 });
    const st = await page.evaluate(() => ({ kind: window.__bm.req && window.__bm.req.kind, over: window.__bm.over }));
    if (st.over) break;
    if (await page.evaluate(() => document.getElementById('report').style.display === 'block')) { await shot('report'); await tap('report-close'); }
    const first = !did[st.kind]; did[st.kind] = (did[st.kind] || 0) + 1;
    if (first || did[st.kind] <= 2) await shot(st.kind);
    if (st.kind === 'deploy') { await page.locator('[data-deploy]').first().dispatchEvent('click'); await page.waitForSelector('[data-act="place"]'); if (first) await shot('deploy_picked'); await hold('place'); }
    else if (st.kind === 'move_order') await tap('pick-unit');
    else if (st.kind === 'stand_up') { await tap('stand-plan'); await page.waitForFunction(() => !!window.__bm.mv, null, { timeout: 20000 }); await hold('commit'); }
    else if (st.kind === 'boost') await tap('boost', '[data-v="0"]');
    else if (st.kind === 'movement') {
      const hex = await page.evaluate(() => { const r = window.__bm.req; const o = r.options.filter((x) => x.mode === 'Walk').sort((a, b) => b.mp - a.mp)[0] || r.options[0]; return o && o.hex; });
      if (first) {
        const f1 = await page.evaluate(() => { const r = __bm.req; const o = r.options.filter((x) => x.mode === 'Walk' && x.mp >= 1 && x.mp < r.walk).sort((a, b) => a.mp - b.mp)[0]; return o ? o.hex : null; });
        if (f1) { await page.locator(`[data-reach="${f1}"]`).first().dispatchEvent('click'); await page.waitForFunction(() => __bm.way.length === 1); await shot('way1');
          const s2 = await page.evaluate((f) => Object.keys(__bm.wrIdx).find((h) => h !== f), f1);
          if (s2) { await page.locator(`[data-reach="${s2}"]`).first().dispatchEvent('click'); await page.waitForFunction(() => __bm.way.length === 2, null, { timeout: 5000 }).catch(() => {}); await shot('way2'); await tap('undo'); await page.waitForTimeout(200); } }
        // zoom and pan through the page's own buttons and gesture helpers
        await page.locator('#zin').click(); await shot('zoomed'); await page.locator('#zfit').click(); await shot('fit');
      }
      if (hex) { await page.locator(`[data-reach="${hex}"]`).first().dispatchEvent('click'); await page.waitForSelector('[data-act="commit"]'); if (did[st.kind] <= 2) await shot('dest'); }
      await hold('commit');
    }
    else if (st.kind === 'spot') await tap('spot', '[data-id=""]');
    else if (st.kind === 'tag') await page.evaluate(() => send({ target: null }));
    else if (st.kind === 'target') {
      await page.waitForFunction(() => window.__bm.fire && window.__bm.decl, null, { timeout: 20000 }).catch(() => {});
      if (first) { await tap('tgt-next').catch(() => {}); await page.waitForTimeout(200); await shot('tgt_next'); await tap('assign', ':not([disabled])').catch(() => {}); await shot('assigned'); }
      if (await page.evaluate(() => __bm.fire && __bm.fire.assign.size > 0)) await tap('fire-go'); else await tap('hold').catch(() => {});
    }
    else if (st.kind === 'declaration') { await tap('assign').catch(() => {}); await tap('strike'); await tap('strike'); await shot('declared'); await tap('fire-go'); }
    else if (st.kind === 'physical') await tap('phys', '[data-k=""]');
    else if (st.kind === 'end_phase') await tap('end-go');
    await page.waitForTimeout(60);
  }
  console.log('shots', n, 'kinds', JSON.stringify(did), 'errors', JSON.stringify(errs.slice(0, 5)));
  await b.close();
})();
