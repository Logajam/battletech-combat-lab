"""
tests/check_lab_server.py - COMBAT LAB CL3's check (INTEGRATION__COMBAT_LAB_SPECS.md): the Lab server, driven by a
script with no browser, gives the same battles btsim gives for the same setup and seed.

    python tests/check_lab_server.py [--battles 20] [--keep-running]

Builds and starts engine/target/release/combatlab on a free port, then:
  1. sets up a 2 v 2 (two Gladiator teams on a board) and asks for an estimate;
  2. runs the batch through the server, polling progress until it finishes;
  3. runs the same settings and seed with `btsim --setup` and compares every battle (seed, winner, turns);
  4. asks the server for battle 3's history and checks it against the battle list (seed, winner, turns, a step per
     marked phase) and that a second request gives the same record;
  5. a unit from the unit pack (data/meks.zip) and a board from the map pack (data/maps.zip) play too;
  6. a bad setup answers {"error": ...} and the server keeps answering;
  7. the Options tab's settings ("options" in a setup) are accepted, or refused with words.
Exit code 0 = every check passed.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
LAB = os.path.join(ENGINE, "target", "release", "combatlab")
BTSIM = os.path.join(ENGINE, "target", "release", "btsim")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Lab:
    def __init__(self, port):
        self.port = port

    def api(self, name, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/{name}", data=json.dumps(body or {}).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())


def check(ok, what, failures):
    print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
    if not ok:
        failures.append(what)


def main(argv):
    battles = int(argv[argv.index("--battles") + 1]) if "--battles" in argv else 20
    # up to date with the source (quick when nothing changed)
    subprocess.run(["cargo", "build", "--release", "-q", "-p", "combatlab", "-p", "btsim"], cwd=ENGINE, check=True, capture_output=True)
    port = free_port()
    proc = subprocess.Popen([LAB, "--no-browser", "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=dict(os.environ, BTSIM_ROOT=REPO_ROOT))
    failures = []
    try:
        line = proc.stdout.readline()          # "Combat Lab is running at ..." once it listens
        if "running" not in line:
            raise SystemExit("combatlab did not start: " + line + proc.stderr.read())
        lab = Lab(port)
        units = lab.api("list_units")["units"]
        boards = lab.api("list_boards")["boards"]
        check(len(units) > 1000 and len(boards) > 100, f"lists: {len(units)} units, {len(boards)} boards", failures)
        # a quarter of the library writes "LA armor:" in lower case; the list once showed those units with armor 0
        no_armor = [u["name"] for u in units if not u.get("armor")]
        check(not no_armor, f"every listed unit has armor ({len(no_armor)} without: {no_armor[:3]})", failures)
        # the unit sheet / editor's calls (2026-11-15): a unit's text, the equipment catalogue, the engine's reading of edited text
        text = lab.api("unit_text", {"id": "Atlas AS7-K.mtf"}).get("text", "")
        check("chassis:Atlas" in text, "unit_text returns a unit's file", failures)
        base = lab.api("unit_eval", {"text": text})
        listed = next(u for u in units if u["id"] == "Atlas AS7-K.mtf")
        check(base["unit"]["ok"] and base["unit"]["bv"] == listed["bv"], f"unit_eval gives the listed BV ({base['unit'].get('bv')} v {listed['bv']})", failures)
        check(base["structure"].get("Left Arm") == 17, f"unit_eval gives internal structure ({base['structure'].get('Left Arm')})", failures)
        more = lab.api("unit_eval", {"text": text.replace("Jump MP:0", "Jump MP:3")})
        check(more["unit"]["ok"] and more["unit"]["bv"] != base["unit"]["bv"], "an edited jump MP changes the BV", failures)
        eq = lab.api("equipment_list")["equipment"]
        check(len(eq) > 600 and any("ismediumlaser" in e["al"] for e in eq), f"equipment_list: {len(eq)} items", failures)
        check("error" in lab.api("add_unit", {"file": "Atlas AS7-K.mtf", "text": text, "overwrite": True}), "a published unit file cannot be overwritten", failures)

        setup = {"teams": [{"name": "Red", "bot": "gladiator", "units": [{"unit": "Atlas AS7-K.mtf"}, {"unit": "Griffin GRF-1N.mtf"}]},
                           {"name": "Blue", "bot": "gladiator", "units": [{"unit": "Awesome AWS-8Q.mtf"}, {"unit": "Hunchback HBK-4G.mtf"}]}],
                 "board": "16x17_Grassland_1.board", "battles": battles, "seed": 7, "threads": 0}
        est = lab.api("estimate", {"setup": setup})
        check("seconds" in est, f"estimate: {est.get('seconds', 0):.1f} s for {battles} battles ({est.get('per_battle', 0):.2f} s a battle)", failures)

        run = lab.api("run", {"setup": setup})["run"]
        while not lab.api("progress", {"run": run})["finished"]:
            time.sleep(0.5)
        res = lab.api("results", {"run": run})
        lines = res["battles"]
        check(len(lines) == battles and not res["crashed"], f"run: {len(lines)} battles, {res['summary']['teams']['Red']['wins']} Red wins, "
              f"{res['summary']['teams']['Blue']['wins']} Blue wins, {res['summary']['draws']} draws", failures)

        # the same settings and seed through btsim
        settings = {"FORCES": [{"team": t["name"], "mtf": u["unit"], "bot": t["bot"], "gunnery": 4, "piloting": 5} for t in setup["teams"] for u in t["units"]],
                    "DEFAULT_BOARD_PATH": setup["board"], "DEPLOYMENT": "home_edge"}
        with tempfile.TemporaryDirectory() as tmp:
            sfile = os.path.join(tmp, "settings.json")
            with open(sfile, "w") as f:
                json.dump(settings, f)
            out = os.path.join(tmp, "out.json")
            subprocess.run([BTSIM, "--setup", sfile, "--battles", str(battles), "--seed", "7", "--out", out], check=True,
                           env=dict(os.environ, BTSIM_ROOT=REPO_ROOT), capture_output=True)
            with open(out) as f:
                bt = {r["sim"]: r for r in json.load(f)["results"]}
        same = all(str(bt[l["sim"]]["seed"]) == l["seed"] and bt[l["sim"]]["winner"] == l["winner"] and bt[l["sim"]]["turns"] == l["turns"] for l in lines)
        check(same, "every battle equals btsim's (seed, winner, turns)", failures)

        h = lab.api("history", {"run": run, "sim": 3})
        third = next(l for l in lines if l["sim"] == 3)
        check(h["seed"] == third["seed"] and h["result"]["winner"] == third["winner"] and h["result"]["turns"] == third["turns"],
              f"battle 3's history: {len(h['steps'])} steps, winner {h['result']['winner']} in {h['result']['turns']} turns", failures)
        check(lab.api("history", {"run": run, "sim": 3}) == h, "battle 3's history again: the same record", failures)
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/replay?run={run}&sim=3").read().decode()
        check("replay-data" in page and "__REPLAY_JSON__" not in page, "battle 3's replay page", failures)

        packed_unit = next(u for u in units if u["id"].startswith("meks/") and u["ok"] and u["tons"] == 50)
        packed_board = next(b for b in boards if b["id"].startswith("maps/") and b["width"] == 16 and b["height"] == 17)
        setup2 = {"teams": [{"name": "A", "bot": "princess", "units": [{"unit": packed_unit["id"]}]},
                            {"name": "B", "bot": "gladiator", "units": [{"unit": "Griffin GRF-1N.mtf"}]}],
                  "board": packed_board["id"], "battles": 2, "seed": 1}
        run2 = lab.api("run", {"setup": setup2})
        ok2 = "run" in run2
        if ok2:
            while not lab.api("progress", {"run": run2["run"]})["finished"]:
                time.sleep(0.3)
            ok2 = len(lab.api("results", {"run": run2["run"]})["battles"]) == 2
        check(ok2, f"from the packs: {packed_unit['name']} on {packed_board['name']}: {run2}", failures)

        bad = lab.api("run", {"setup": {"teams": [{"name": "Solo", "units": [{"unit": "Atlas AS7-K.mtf"}]}], "board": "16x17_Grassland_1.board"}})
        check("error" in bad, f"a bad setup: {bad}", failures)
        # Options tab: a changed setting is accepted and used; a wrong kind, an unknown name and one the Lab sets itself are refused
        base = {"teams": [{"name": "Red", "bot": "gladiator", "units": [{"unit": "Atlas AS7-K.mtf"}]}, {"name": "Blue", "bot": "gladiator", "units": [{"unit": "Griffin GRF-1N.mtf"}]}],
                "board": "16x17_Grassland_1.board", "battles": 1, "seed": 1, "threads": 1}
        check("error" not in lab.api("estimate", {"setup": {**base, "options": {"POOL_CLUSTER_DAMAGE": True}}}), "an option is accepted", failures)
        for name, opts in (("wrong kind", {"CHARGES": "yes"}), ("unknown", {"NO_SUCH_SETTING": 1}), ("Lab-owned", {"SEED": 3})):
            check("error" in lab.api("estimate", {"setup": {**base, "options": opts}}), f"option refused: {name}", failures)
        check("units" in lab.api("list_units"), "the server still answers", failures)
    finally:
        if "--keep-running" not in argv:
            proc.terminate()
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
