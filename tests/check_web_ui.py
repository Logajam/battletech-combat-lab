"""
tests/check_web_ui.py - COMBAT LAB IN THE BROWSER, the page as a person uses it (Daniel, 2026-11-17: "If we need a test
suite go ahead and make it"). tests/check_web_lab.py proves the browser plays the same battles as the desktop; this one
clicks through the website itself in headless Chromium (Playwright) and checks what a visitor would see:

    python tests/check_web_ui.py [--battles 12] [--rebuild]

  1. the page loads with no page errors, every tab opens, the status line says the data is loaded;
  2. Units: the Unit Browser lists units and its name search narrows the list; an eye opens a unit sheet, two eyes two;
  3. Map: the preview canvas is drawn; Options: the search narrows the list;
  4. a batch run from the Run button finishes, and the win bar and statistics show it;
  5. CAUSE OF DEATH (Daniel, 2026-11-17): a click on a unit's "How it ended" row shows exactly the battles where that unit
     ended that way (checked battle by battle against the run's own record), the Find battles form holds that condition,
     the "Survived" row does the same for survivors, and Show all brings every battle back;
  6. a click on a battle opens its replay;
  7. CORES (Daniel, 2026-11-17: another program crashed when a run took every cycle): with the threads box at 0 the page
     plays on every core but a quarter of them (at least one left free); a number typed in is used, up to the core count.
     Checked at 1, 2, 4, 8 and 16 reported cores.
Exit code 0 = every check passed; 77 (skipped) when node / Playwright / the web build cannot be had.
"""
import argparse, json, os, shutil, socket, subprocess, sys, tempfile, time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO_ROOT, "web_lab")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


# the browser half: drives the page, prints one "RESULT {json}" line of what it saw
NODE = r"""
const { chromium } = require('playwright');
(async () => {
  const [url, battlesArg] = process.argv.slice(2);
  const battles = +battlesArg;
  const out = { checks: [], errors: [] };
  const check = (name, ok, detail) => out.checks.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
  const b = await chromium.launch();
  try {
    // ---- the thread rule, at several core counts (navigator.hardwareConcurrency set before the page's scripts run)
    for (const cores of [1, 2, 4, 8, 16]) {
      const ctx = await b.newContext();
      await ctx.addInitScript((c) => Object.defineProperty(Navigator.prototype, "hardwareConcurrency", { get: () => c }), cores);
      const p = await ctx.newPage();
      await p.goto(url);
      await p.waitForFunction(() => window.LAB_WASM && document.getElementById("status").textContent.length > 0, null, { timeout: 120000 });
      const r = await p.evaluate(async () => {
        const units = (await LAB_WASM.api("list_units", {})).units;
        const id = (n) => units.find((u) => u.id === n) ? n : units[0].id;
        const setup = { teams: [{ name: "Red", bot: "gladiator", units: [{ unit: id("Locust LCT-1V.mtf") }] }, { name: "Blue", bot: "gladiator", units: [{ unit: id("Locust LCT-1V.mtf") }] }],
          board: "16x17_Grassland_1.board", battles: 40, seed: 3, max_turns: 5 };
        const auto = await LAB_WASM.api("estimate", { setup: { ...setup, threads: 0 } });
        const two = await LAB_WASM.api("estimate", { setup: { ...setup, threads: 2 } });
        const many = await LAB_WASM.api("estimate", { setup: { ...setup, threads: 99 } });
        return { auto: auto.threads, two: two.threads, many: many.threads, err: auto.error || two.error || many.error };
      });
      const want = Math.max(1, cores - Math.max(1, Math.floor(cores / 4)));
      check(`${cores} cores: automatic plays on ${want}`, r.auto === want, `got ${r.auto}${r.err ? " / " + r.err : ""}`);
      check(`${cores} cores: 2 typed in plays on ${Math.min(2, cores)}`, r.two === Math.min(2, cores), `got ${r.two}`);
      check(`${cores} cores: 99 typed in is capped at ${cores}`, r.many === cores, `got ${r.many}`);
      await ctx.close();
    }

    // ---- the page as a visitor uses it
    const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => out.errors.push(e.message));
    await p.goto(url);
    await p.waitForFunction(() => window.LAB_WASM && document.querySelectorAll("#ub-list tbody tr").length > 0, null, { timeout: 120000 });
    check("the page loads and the Unit Browser lists units", true, await p.locator("#ub-list tbody tr").count());

    for (const tab of ["map", "options", "results", "replay", "units"]) {
      await p.click(`#tab-${tab}`);
      check(`the ${tab} tab opens`, await p.isVisible(`#page-${tab}`));
    }

    // Unit Browser search and sheets
    const before = await p.locator("#ub-list tbody tr").count();
    await p.fill("#ub-name", "Atlas AS7");
    await p.waitForTimeout(400);
    const rows = await p.locator("#ub-list tbody tr").count();
    check("the name search narrows the Unit Browser", rows > 0 && rows < before, `${before} -> ${rows}`);
    await p.locator("#ub-list tbody tr [data-eye]").nth(0).click();
    await p.waitForSelector(".dialog.sheet", { timeout: 30000 });
    await p.locator("#ub-list tbody tr [data-eye]").nth(1).click();
    await p.waitForTimeout(1500);
    check("two eyes open two unit sheets", await p.locator(".dialog.sheet").count() === 2, await p.locator(".dialog.sheet").count());
    const sheetText = await p.locator(".dialog.sheet").first().innerText();
    check("a unit sheet shows the unit", /Atlas/.test(sheetText), sheetText.slice(0, 80));
    while (await p.locator(".dialog.sheet").count()) await p.locator(".dialog.sheet .closebox").first().click();
    await p.fill("#ub-name", "");

    // Map preview, Options search
    await p.click("#tab-map");
    await p.waitForTimeout(1500);
    const drawn = await p.evaluate(() => { const c = document.getElementById("map-preview"); if (!c || !c.width) return 0;
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data; const seen = new Set(); for (let i = 0; i < d.length; i += 4 * 97) seen.add(d[i] + "," + d[i + 1] + "," + d[i + 2]); return seen.size; });
    check("the map preview is drawn", drawn > 3, `${drawn} colours sampled`);
    await p.click("#tab-options");
    const allOpts = await p.locator("#page-options .opt:visible").count();
    await p.fill("#opt-search", "thread");
    await p.waitForTimeout(300);
    const someOpts = await p.locator("#page-options .opt:visible").count();
    check("the Options search narrows the list", someOpts >= 1 && someOpts < allOpts, `${allOpts} -> ${someOpts}`);
    await p.fill("#opt-search", "");

    // a batch from the Run button (the default setup: Atlas + Griffin v Awesome + Hunchback)
    await p.fill("#seed", "4242");
    await p.fill("#threads", "0");
    await p.click("#tab-units");
    await p.fill("#battles", String(battles));
    await p.click("#run-btn");
    await p.waitForFunction((n) => (document.getElementById("progress-text").textContent || "").startsWith(`${n} / ${n}`), battles, { timeout: 600000 });
    await p.waitForFunction(() => /Batch finished/.test(document.getElementById("status").textContent), null, { timeout: 60000 });
    check("a batch run from the Run button finishes", true, await p.textContent("#progress-text"));
    check("the win bar and statistics show", await p.locator("#winbar div").count() >= 2 && (await p.textContent("#stats")).includes("Wins"));
    const run = await p.evaluate(() => lab.run);
    const record = await p.evaluate(async (run) => (await LAB_WASM.api("save_run", { run })).lines, run);
    check("the run's record holds every battle", record.length === battles, record.length);

    // cause of death -> those battles
    await p.click("#unit-stats-box summary");
    await p.waitForSelector("#unit-stats tr.cause-row", { state: "attached", timeout: 60000 });
    await p.evaluate(() => document.querySelectorAll("#unit-stats details").forEach((d) => { d.open = true; }));
    const causeRows = await p.evaluate(() => [...document.querySelectorAll("#unit-stats tr.cause-row")].map((tr, i) => ({ i, unit: tr.dataset.unit, cause: tr.dataset.cause })));
    const destroyedRow = causeRows.find((r) => r.cause);
    check("the unit statistics list causes of death as links", !!destroyedRow, causeRows.length + " rows");
    const listed = async () => p.evaluate(() => [...document.querySelectorAll("#battle-tree tbody tr")].map((tr) => +tr.dataset.sim).sort((a, b) => a - b));
    const tryRow = async (row, want, what) => {
      await p.evaluate((i) => document.querySelectorAll("#unit-stats tr.cause-row")[i].click(), row.i);
      await p.waitForFunction(() => /battles match/.test(document.getElementById("filter-note").textContent), null, { timeout: 30000 });
      await p.waitForTimeout(500);
      const shown = await listed();
      const expect = want.map((l) => l.sim).sort((a, b) => a - b);
      check(`${what}: the battle list shows exactly those battles`, JSON.stringify(shown) === JSON.stringify(expect), `shown ${JSON.stringify(shown)} want ${JSON.stringify(expect)}`);
      const note = await p.textContent("#filter-note");
      check(`${what}: the note counts them`, note.startsWith(`${expect.length} of ${battles}`), note);
      const cond = await p.evaluate(() => [...document.querySelectorAll("#f-units .cond")].map((r) => ({ unit: r.querySelector(".c-unit").value, state: r.querySelector(".c-state").value, cause: r.querySelector(".c-cause").value })));
      check(`${what}: the Find battles form holds the condition`, cond.length === 1 && cond[0].unit === row.unit && cond[0].cause === (row.cause || ""), JSON.stringify(cond));
    };
    if (destroyedRow) {
      await tryRow(destroyedRow, record.filter((l) => l.units[destroyedRow.unit] && l.units[destroyedRow.unit].destroyed && (l.units[destroyedRow.unit].cause || "unknown") === destroyedRow.cause), `"${destroyedRow.cause}" (${destroyedRow.unit})`);
      // a second cause that shares words with another, if the run has one, must still match only itself
      const others = causeRows.filter((r) => r.cause && r !== destroyedRow);
      if (others.length) {
        const r2 = await p.evaluate((u) => [...document.querySelectorAll("#unit-stats tr.cause-row")].map((tr, i) => ({ i, unit: tr.dataset.unit, cause: tr.dataset.cause })).filter((r) => r.unit === u.unit && r.cause === u.cause)[0], others[0]);
        await p.click("#f-clear"); await p.waitForTimeout(500);
        await p.evaluate(() => document.querySelectorAll("#unit-stats details").forEach((d) => { d.open = true; }));
        const fresh = await p.evaluate((u) => { const all = [...document.querySelectorAll("#unit-stats tr.cause-row")]; const i = all.findIndex((tr) => tr.dataset.unit === u.unit && tr.dataset.cause === u.cause); return i < 0 ? null : { i, unit: u.unit, cause: u.cause }; }, others[0]);
        if (fresh) await tryRow(fresh, record.filter((l) => l.units[fresh.unit] && l.units[fresh.unit].destroyed && (l.units[fresh.unit].cause || "unknown") === fresh.cause), `"${fresh.cause}" (${fresh.unit})`);
      }
    }
    await p.click("#f-clear"); await p.waitForTimeout(500);
    await p.evaluate(() => document.querySelectorAll("#unit-stats details").forEach((d) => { d.open = true; }));
    const survived = await p.evaluate(() => { const all = [...document.querySelectorAll("#unit-stats tr.cause-row")]; const i = all.findIndex((tr) => tr.dataset.cause === ""); return i < 0 ? null : { i, unit: all[i].dataset.unit, cause: "" }; });
    if (survived) await tryRow(survived, record.filter((l) => l.units[survived.unit] && !l.units[survived.unit].destroyed), `"Survived" (${survived.unit})`);
    await p.click("#f-clear");
    await p.waitForTimeout(500);
    check("Show all brings every battle back", (await listed()).length === battles && (await p.textContent("#filter-note")).startsWith(`${battles} battles`), await p.textContent("#filter-note"));

    // a battle's replay
    await p.locator("#battle-tree tbody tr").first().click();
    await p.waitForFunction(() => { const f = document.getElementById("replay-frame"); return f && (f.srcdoc || "").length > 1000; }, null, { timeout: 120000 });
    check("a click on a battle opens its replay", await p.isVisible("#page-replay"));
    await ctx.close();
  } catch (e) {
    check("the page run did not stop early", false, e.message.split("\n").slice(0, 6).join(" | "));
    if (process.env.WEB_UI_SHOT) { try { for (const c of b.contexts()) for (const pg of c.pages()) await pg.screenshot({ path: process.env.WEB_UI_SHOT }); } catch (x) { /* no picture */ } }
  }
  console.log("RESULT " + JSON.stringify(out));
  await b.close();
})();
"""


def stale():
    """True when web_lab/ is missing or older than any file it is built from (the engine, the Lab's code and pages, the
    browser glue, the build script), so the check never passes on an old build."""
    built = os.path.join(WEB, "combatlab.wasm")
    if not os.path.exists(built):
        return True
    when = os.path.getmtime(built)
    for d in ("engine/core/src", "engine/lab/src", "engine/lab/web", "engine/wasm", "engine/defaults"):
        for root, _, files in os.walk(os.path.join(REPO_ROOT, d)):
            if any(os.path.getmtime(os.path.join(root, f)) > when for f in files):
                return True
    return os.path.getmtime(os.path.join(REPO_ROOT, "tools", "build_web_lab.py")) > when


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--battles", type=int, default=12)
    ap.add_argument("--rebuild", action="store_true", help="rebuild web_lab/ first (tools/build_web_lab.py)")
    a = ap.parse_args()
    if not shutil.which("node"):
        print("SKIP: node is needed"); return 77
    node_path = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    if not os.path.isdir(os.path.join(node_path, "playwright")):
        print("SKIP: Playwright is not installed"); return 77
    if a.rebuild or stale():
        if not shutil.which("cargo"):
            print("SKIP: no web build and no cargo to make one"); return 77
        r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tools", "build_web_lab.py")], capture_output=True, text=True)
        if r.returncode:
            print("SKIP: the web build could not be made (is the wasm32 target installed?)\n" + r.stdout[-800:] + r.stderr[-800:]); return 77
    port = free_port()
    web = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", WEB], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        with tempfile.TemporaryDirectory() as tmp:
            nf = os.path.join(tmp, "ui.js"); open(nf, "w").write(NODE)
            t0 = time.time()
            p = subprocess.run(["node", nf, f"http://127.0.0.1:{port}/index.html", str(a.battles)], capture_output=True, text=True,
                               env={**os.environ, "NODE_PATH": node_path}, timeout=1800)
            took = time.time() - t0
    finally:
        web.terminate()
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    if not line:
        print("FAIL: the page gave no result\n", p.stdout[-2000:], p.stderr[-2000:]); return 1
    out = json.loads(line[7:])
    failures = 0
    for c in out["checks"]:
        print(f"{'ok  ' if c['ok'] else 'FAIL'} {c['name']}" + (f"  ({c['detail']})" if c["detail"] and not c["ok"] else ""))
        failures += 0 if c["ok"] else 1
    if out["errors"]:
        print("FAIL page errors:", out["errors"]); failures += 1
    print(f"({len(out['checks'])} checks in {took:.0f} s)")
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
