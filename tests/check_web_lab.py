"""
tests/check_web_lab.py - COMBAT LAB IN THE BROWSER's check (INTEGRATION__COMBAT_LAB_WEB.md): the WebAssembly build,
running in a real browser (headless Chromium through Playwright), plays exactly the battles the desktop Lab plays.

    python tests/check_web_lab.py [--battles 8] [--rebuild]

  1. builds web_lab/ (tools/build_web_lab.py) when it is missing, or with --rebuild;
  2. starts the desktop Lab and a static web server on free ports;
  3. for four setups (a Gladiator 2 v 2, Princess v Hydra with packed units, two boards stitched, a map list with
     starting zones) plays the batch on both and compares every battle: seed, winner, turns, each team's damage
     dealt and each unit's cause of death. The web build plays unit files with their fluff stripped, so this also proves
     the stripping changes nothing;
  4. plays one battle's replay on the page, and checks a bad setup answers in words.
Exit code 0 = every check passed; 77 (skipped) when node / Playwright / the wasm target are not here.
"""
import argparse, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
LAB = os.path.join(ENGINE, "target", "release", "combatlab")
WEB = os.path.join(REPO_ROOT, "web_lab")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def ask(port, name, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/{name}", data=json.dumps(body or {}).encode(), method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


# the 100-ton Atlas with jump jets (Jump MP 3) and a new name: what the unit editor would send (2026-11-15)
MODIFIED_ATLAS = open(os.path.join(REPO_ROOT, "data", "Atlas AS7-K.mtf"), encoding="utf-8", errors="replace").read().replace("Jump MP:0", "Jump MP:3").replace("chassis:Atlas", "chassis:Atlas Modified")


def setups(n):
    unit = lambda f, g=4, p=5: {"unit": f, "gunnery": g, "piloting": p}
    return {
        "gladiator 2v2": {"teams": [{"name": "Red", "bot": "gladiator", "units": [unit("Atlas AS7-K.mtf"), unit("Griffin GRF-1N.mtf")]},
                                     {"name": "Blue", "bot": "gladiator", "units": [unit("Awesome AWS-8Q.mtf"), unit("Archer ARC-2R.mtf")]}],
                          "board": "16x17_Grassland_1.board", "battles": n, "seed": 7},
        "princess v hydra, packed units": {"teams": [{"name": "Red", "bot": "princess", "units": [unit("meks/3039u/Archer ARC-2K.mtf", 3, 4)]},
                                                      {"name": "Blue", "bot": "hydra", "units": [unit("Jenner JR7-D.mtf"), unit("Locust LCT-1V.mtf")]}],
                                           "board": "16x17_Desert_Hills.board", "battles": n, "seed": 11},
        "stitched boards": {"teams": [{"name": "Red", "bot": "gladiator", "units": [unit("Hunchback HBK-4G.mtf")]},
                                       {"name": "Blue", "bot": "gladiator", "units": [unit("Catapult CPLT-C1.mtf")]}],
                            "board": {"grid": [["16x17_Hilltops_1.board", "16x17_Scattered_Woods.board"]]}, "battles": n, "seed": 3},
        "modified unit (text in the setup)": {"teams": [{"name": "Red", "bot": "gladiator", "units": [{"unit": "Atlas AS7-K.mtf", "mtf_text": MODIFIED_ATLAS, "gunnery": 4, "piloting": 5}]},
                                                         {"name": "Blue", "bot": "gladiator", "units": [unit("Awesome AWS-8Q.mtf")]}],
                                              "board": "16x17_Grassland_1.board", "battles": n, "seed": 9},
        "map list with zones": {"teams": [{"name": "Red", "bot": "gladiator", "units": [unit("Cataphract CTF-3D.mtf")], "zone": {"boxes": [True, False, False, True, False, False, True, False, False], "walk_on": True}},
                                           {"name": "Blue", "bot": "gladiator", "units": [unit("Dervish DV-6M.mtf")]}],
                                "board": {"playlist": ["16x17_Large_Lakes_1.board", "16x17_Military_Base_1.board"], "order": "shuffle"},
                                "zone_mode": "random", "battles": n, "seed": 5},
    }


def key_of(line):
    return {"sim": line["sim"], "seed": line["seed"], "winner": line["winner"], "turns": line["turns"], "board": line["board"],
            "teams": {t: s["damage_dealt"] for t, s in line["teams"].items()},
            "causes": {u: (v["destroyed"], v["cause"]) for u, v in line["units"].items()}}


NODE = r"""
const { chromium } = require('playwright');
(async () => {
  const [url, file] = process.argv.slice(2);
  const all = JSON.parse(require('fs').readFileSync(file, 'utf8'));
  const b = await chromium.launch(); const p = await b.newPage();
  const errors = []; p.on('pageerror', e => errors.push(e.message));
  await p.goto(url);
  const out = await p.evaluate(async (all) => {
    const res = {};
    for (const [name, setup] of Object.entries(all)) {
      const r = await LAB_WASM.api("run", { setup });
      if (r.error) { res[name] = { error: r.error }; continue; }
      let pr;
      do { await new Promise(s => setTimeout(s, 100)); pr = await LAB_WASM.api("progress", { run: r.run }); } while (!pr.finished);
      const full = await LAB_WASM.api("results", { run: r.run, from: 1, to: 100000 });
      // the battle list is slim: ask for each battle's unit detail through the unit statistics call is too coarse; use save_run
      const saved = await LAB_WASM.api("save_run", { run: r.run });
      res[name] = { lines: saved.lines, crashed: saved.crashed };
    }
    const text = (await LAB_WASM.api("unit_text", { id: "Atlas AS7-K.mtf" })).text || "";
    const editor = { text: text.length, base: await LAB_WASM.api("unit_eval", { text }),
      jumped: await LAB_WASM.api("unit_eval", { text: text.replace("Jump MP:0", "Jump MP:3") }),
      broken: await LAB_WASM.api("unit_eval", { text: "this is not a unit" }),
      equipment: ((await LAB_WASM.api("equipment_list", {})).equipment || []).length };
    const bad = await LAB_WASM.api("run", { setup: { teams: [], board: "x" } });
    const html = await LAB_WASM.replayHtml({ setup: all[Object.keys(all)[0]], seed: 7, sim: 1 });
    return { res, editor, bad, replay: typeof html === "string" ? html.length : html };
  }, all);
  out.errors = errors;
  console.log("RESULT " + JSON.stringify(out));
  await b.close();
})();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--battles", type=int, default=8)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if not shutil.which("node") or not shutil.which("cargo"):
        print("SKIP: node and cargo are needed"); return 77
    node_path = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    if not os.path.isdir(os.path.join(node_path, "playwright")):
        print("SKIP: Playwright is not installed"); return 77
    if a.rebuild or not os.path.exists(os.path.join(WEB, "combatlab.wasm")):
        subprocess.check_call([sys.executable, os.path.join(REPO_ROOT, "tools", "build_web_lab.py")])
    all_setups = setups(a.battles)
    lab_port, web_port = free_port(), free_port()
    lab = subprocess.Popen([LAB, "--no-browser", "--port", str(lab_port)], env={**os.environ, "BTSIM_ROOT": REPO_ROOT}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    web = subprocess.Popen([sys.executable, "-m", "http.server", str(web_port), "--bind", "127.0.0.1", "--directory", WEB], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures = 0
    try:
        for _ in range(60):
            try: ask(lab_port, "info"); break
            except Exception: time.sleep(0.5)
        native = {}
        for name, setup in all_setups.items():
            r = ask(lab_port, "run", {"setup": setup})
            if r.get("error"): print("FAIL native", name, r["error"]); return 1
            while not ask(lab_port, "progress", {"run": r["run"]})["finished"]: time.sleep(0.2)
            saved = ask(lab_port, "save_run", {"run": r["run"]})
            native[name] = saved
        with tempfile.TemporaryDirectory() as tmp:
            sf = os.path.join(tmp, "setups.json"); json.dump(all_setups, open(sf, "w"))
            nf = os.path.join(tmp, "probe.js"); open(nf, "w").write(NODE)
            t0 = time.time()
            p = subprocess.run(["node", nf, f"http://127.0.0.1:{web_port}/index.html", sf], capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path}, timeout=1800)
            took = time.time() - t0
        line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
        if not line:
            print("FAIL: the page gave no result\n", p.stdout[-2000:], p.stderr[-2000:]); return 1
        out = json.loads(line[7:])
        for name in all_setups:
            w = out["res"][name]
            if "error" in w: print(f"FAIL {name}: the page said {w['error']}"); failures += 1; continue
            n = native[name]
            nk = sorted((key_of(l) for l in n["lines"]), key=lambda k: k["sim"])
            wk = sorted((key_of(l) for l in w["lines"]), key=lambda k: k["sim"])
            same = nk == wk and not w["crashed"] and not n["crashed"]
            print(f"{'ok  ' if same else 'FAIL'} {name}: {len(wk)} battles in the browser, {len(nk)} on the desktop" + ("" if same else " - DIFFERENT"))
            if not same:
                failures += 1
                for x, y in zip(nk, wk):
                    if x != y: print("   desktop", x, "\n   browser", y); break
        ed = out["editor"]
        for what, good in [("unit_text gives the file", ed["text"] > 1000), ("unit_eval gives the listed BV", ed["base"].get("unit", {}).get("bv") == 2175),
                           ("an edited jump MP changes the BV", ed["jumped"].get("unit", {}).get("bv") not in (None, 2175)),
                           ("a text that is not a unit is refused, not a crash", ed["broken"].get("unit", {}).get("ok") is False or "error" in ed["broken"]),
                           ("equipment_list has the catalogue", ed["equipment"] > 600)]:
            print(f"{'ok  ' if good else 'FAIL'} browser editor: {what}"); failures += 0 if good else 1
        print(f"{'ok  ' if out['bad'].get('error') else 'FAIL'} a bad setup answers in words: {out['bad'].get('error')}")
        failures += 0 if out["bad"].get("error") else 1
        print(f"{'ok  ' if isinstance(out['replay'], int) and out['replay'] > 1000 else 'FAIL'} replay page built ({out['replay']} characters)")
        failures += 0 if isinstance(out["replay"], int) and out["replay"] > 1000 else 1
        if out["errors"]: print("FAIL page errors:", out["errors"]); failures += 1
        print(f"(the browser played {len(all_setups)} batches in {took:.0f} s)")
    finally:
        lab.terminate(); web.terminate()
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
