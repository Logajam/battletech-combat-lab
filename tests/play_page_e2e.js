// BattleROM play page, end to end in a phone-sized browser (Playwright). NOT part of run_checks.py (needs node + playwright).
// Start the Lab first:  BTSIM_ROOT=$PWD engine/target/release/combatlab --no-browser --port 8799
// then:  node tests/play_page_e2e.js /some/folder   (screenshots go to that folder). Plays a whole battle by tapping the real controls.
const { chromium } = require('playwright');
const SP = process.argv[2];
(async () => {
  const setup = { teams: [
    { name: "Red", colour: "#4b8fd8", bot: "human", units: [{ unit: "Atlas AS7-K.mtf", gunnery: 4, piloting: 5 }, { unit: "Griffin GRF-1N.mtf", gunnery: 4, piloting: 5 }] },
    { name: "Blue", colour: "#d86a4b", bot: "gladiator", units: [{ unit: "Awesome AWS-8Q.mtf", gunnery: 4, piloting: 5 }, { unit: "Hunchback HBK-4G.mtf", gunnery: 4, piloting: 5 }] }],
    board: "16x17_Grassland_1.board", battles: 1, seed: 11, max_turns: 100 };
  const r = await (await fetch("http://127.0.0.1:8799/api/play_start", { method: "POST", body: JSON.stringify({ setup }) })).json();
  console.log("start", JSON.stringify(r).slice(0, 120));
  if (r.error) process.exit(1);
  const b = await chromium.launch(); 
  const ctx = await b.newContext({ viewport: { width: 390, height: 780 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e))); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto(`http://127.0.0.1:8799/play.html?game=${r.game}&colours=${encodeURIComponent(JSON.stringify(r.colours))}`);
  const kindsSeen = new Set();
  let shots = 0;
  for (let step = 0; step < 400; step++) {
    await page.waitForFunction(() => window.__bm && (window.__bm.req || window.__bm.over), null, { timeout: 60000 });
    const st = await page.evaluate(() => ({ kind: window.__bm.req && window.__bm.req.kind, over: window.__bm.over, phase: document.getElementById('phase').textContent }));
    if (st.over) break;
    kindsSeen.add(st.kind);
    if (!shots || (st.kind === 'declaration' && shots < 3) || (st.kind === 'physical' && shots < 4) || (st.kind === 'movement' && shots < 2)) {
      if (st.kind === 'movement') {
        // tap a reachable hex far from the unit, to show the tint, arrows and the sheet
        const hex = await page.evaluate(() => { const r = window.__bm.req; const o = r.options.filter(x => x.mode === 'Run').sort((a, b) => b.mp - a.mp)[0] || r.options[0]; return o.hex; });
        await page.locator(`[data-reach="${hex}"]`).first().dispatchEvent('click');
        await page.waitForTimeout(200);
      }
      await page.screenshot({ path: `${SP}/shot_${shots}_${st.kind}.png` }); shots++;
    }
    // answer by tapping the real controls
    if (st.kind === 'move_order') await page.locator('[data-pick]').first().click();
    else if (st.kind === 'movement') {
      const hex = await page.evaluate(() => { const r = window.__bm.req; const o = r.options.filter(x => x.mode === 'Walk').sort((a, b) => b.mp - a.mp)[0] || r.options[0]; return o.hex; });
      await page.locator(`[data-reach="${hex}"]`).first().dispatchEvent('click');
      await page.locator('#commit').click();
    }
    else if (st.kind === 'target') await page.locator('[data-t]').first().click();
    else if (st.kind === 'declaration') { await page.locator('#alpha').click(); await page.locator('#fire').click(); }
    else if (st.kind === 'physical') { const k = page.locator('[data-k]').first(); if (await k.count()) await k.click(); else await page.locator('#skip').click(); }
    await page.waitForTimeout(80);
  }
  const over = await page.evaluate(() => window.__bm.over);
  await page.screenshot({ path: `${SP}/shot_end.png` });
  console.log("kinds", [...kindsSeen], "over", over, "errors", errs.slice(0, 5));
  await b.close();
})();
