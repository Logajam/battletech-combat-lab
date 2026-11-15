"""
tools/make_lab_demo.py - the Combat Lab pages as ONE self-contained page with canned answers, so Daniel can look at them
without running the program (CLAUDE.md: he does not run the code himself; INTEGRATION__COMBAT_LAB_SPECS.md CL4 "Done
when").

    python tools/make_lab_demo.py OUT.html [--battles 20] [--replays 3]

Starts engine/target/release/combatlab, runs a sample batch through it (the same requests the pages make), keeps every
answer - the unit and board lists, an estimate, the results, and the full histories of the first --replays battles -
and writes the pages (engine/lab/web) with those answers inside (`window.LAB_DEMO`, read by lab.js). The output is
written without <html>/<head>/<body> (the Artifact tool adds them). The numbers in it are real: a real batch.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO_ROOT, "engine", "lab", "web")
LAB = os.path.join(REPO_ROOT, "engine", "target", "release", "combatlab")
VIEWER = os.path.join(REPO_ROOT, "INTEGRATION__replay_viewer.html")

SETUP = {"teams": [{"name": "Red", "bot": "gladiator", "units": [{"unit": "Atlas AS7-K.mtf"}, {"unit": "Griffin GRF-1N.mtf"}]},
                   {"name": "Blue", "bot": "princess", "units": [{"unit": "Awesome AWS-8Q.mtf"}, {"unit": "Hunchback HBK-4G.mtf"}]}],
         "board": "16x17_Grassland_1.board", "battles": 20, "seed": 1, "threads": 0, "max_turns": 100}


def main(argv):
    out = argv[0]
    SETUP["battles"] = int(argv[argv.index("--battles") + 1]) if "--battles" in argv else 20
    replays = int(argv[argv.index("--replays") + 1]) if "--replays" in argv else 3
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([LAB, "--no-browser", "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=dict(os.environ, BTSIM_ROOT=REPO_ROOT))

    def api(name, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/{name}", data=json.dumps(body or {}).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())
    try:
        proc.stdout.readline()
        info = api("info")
        info["project"] = "(your project folder)"
        keep = ("id", "name", "source", "tons", "bv", "tech", "era", "ok", "why", "walk", "jump", "armor", "sinks", "sink_kind", "role", "config", "rules", "book", "armor_type", "structure", "weapons")
        units = [{k: u[k] for k in keep if k in u} for u in api("list_units")["units"]]
        boards = api("list_boards")["boards"]
        estimate = api("estimate", {"setup": SETUP})
        # every board's text, so the Map page's previews work (about 4 MB; the real Lab asks the program for each one)
        board_texts = {}
        for b in boards:
            r = api("board", {"id": b["id"] if isinstance(b, dict) else b})
            if "text" in r:
                board_texts[r["id"]] = r["text"]
        run = api("run", {"setup": SETUP})["run"]
        while not api("progress", {"run": run})["finished"]:
            time.sleep(0.5)
        results = api("results", {"run": run, "from": 1, "to": SETUP["battles"]})
        histories = {sim: api("history", {"run": run, "sim": sim}) for sim in range(1, replays + 1)}
    finally:
        proc.terminate()
    with open(VIEWER, encoding="utf-8") as f:
        viewer = f.read()
    s = results["summary"]
    banner = (f"<b>Demo.</b> Combat Lab's pages with answers recorded from a real run of the program: "
              f"{SETUP['battles']} battles of Atlas + Griffin (Gladiator) against Awesome + Hunchback (Princess). "
              f"Run Simulation replays those results whatever is set up; battles 1 to {replays} can be watched. "
              f"Find battles works on them (try: Red 1 was destroyed).")
    demo = {"info": info, "units": units, "boards": boards, "board_texts": board_texts, "estimate": estimate, "lines": results["battles"], "unitLabels": results["units"],
            "seconds": results["progress"]["seconds"], "histories": histories,
            "setup": SETUP, "viewer": viewer, "banner": banner, "autorun": True}
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        page = f.read()
    body = page.split("<!--LAB-BODY-->")[1].split("<!--LAB-SCRIPT-->")[0]
    with open(os.path.join(WEB, "lab.css"), encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(WEB, "lab.js"), encoding="utf-8") as f:
        js = f.read()
    data = json.dumps(demo, separators=(",", ":")).replace("</", "<\\/")
    html = ("<title>Combat Lab</title>\n<meta name=\"claude:viewport-fit-sides\" content=\"cover\">\n"
            f"<style>\n{css}</style>\n{body}<script>window.LAB_DEMO = {data};</script>\n<script>\n{js}</script>\n")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"{out}: {len(html) / 1e6:.1f} MB; {s['battles']} battles, " +
          ", ".join(f"{t} {v['wins']} wins" for t, v in s["teams"].items()) + f", {s['draws']} draws")


if __name__ == "__main__":
    main(sys.argv[1:])
