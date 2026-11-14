#!/usr/bin/env python3
"""Builds COMBAT LAB IN THE BROWSER: a folder of static files (`web_lab/`) any web host can serve, where the visitor's
own computer plays the battles (engine/wasm; INTEGRATION__COMBAT_LAB_WEB.md).

    python tools/build_web_lab.py [--out web_lab] [--skip-wasm]

What it does:
  1. builds the engine as WebAssembly (cargo, target wasm32-unknown-unknown) unless --skip-wasm;
  2. asks the desktop Lab (engine/target/release/combatlab, started on a spare port) for its unit and board lists, so the
     web lists are the very ones the desktop shows;
  3. keeps only boards that are 16x17 (the standard map sheet; Daniel, 2026-11-14: "prune out all the maps that aren't
     standard 16x17") and only units the engine can play;
  4. strips the fluff from unit files (history, overview, capabilities, deployment, manufacturers: lines the engine
     never reads; tests/check_web_lab.py plays the same battles with and without to prove it);
  5. writes data.pack.gz (every unit and board in one gzip block: per file name length, name, content length, content,
     4 + 4 bytes little-endian, as the desktop's unit pack), catalog.json (the lists), the pages and the module.
"""
import argparse, gzip, json, os, re, shutil, struct, subprocess, sys, time, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# lines of a unit file that are only fluff: no engine code reads them (checked by tests/check_web_lab.py)
FLUFF = ("history", "overview", "capabilities", "deployment", "manufacturer", "primaryfactory", "systemmanufacturer", "systemmode", "notes", "imagefile", "fluffimage")
FLUFF_RE = re.compile(r"^(" + "|".join(FLUFF) + r"):", re.I)


def strip_fluff(text):
    return "".join(l for l in text.splitlines(True) if not FLUFF_RE.match(l))


def ask(port, name, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/{name}", data=json.dumps(body or {}).encode(), method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web_lab"))
    ap.add_argument("--skip-wasm", action="store_true")
    ap.add_argument("--b64", action="store_true", help="also write data.pack.b64.txt (for a host that will not serve .gz files; engine.js falls back to it)")
    ap.add_argument("--port", type=int, default=8797)
    a = ap.parse_args()
    engine = os.path.join(ROOT, "engine")
    wasm = os.path.join(engine, "target", "wasm32-unknown-unknown", "release", "combatlab_wasm.wasm")
    if not a.skip_wasm:
        subprocess.check_call(["cargo", "build", "--release", "--target", "wasm32-unknown-unknown", "-p", "combatlab_wasm"], cwd=engine)
        subprocess.check_call(["cargo", "build", "--release", "-p", "combatlab"], cwd=engine)
    lab = os.path.join(engine, "target", "release", "combatlab")
    server = subprocess.Popen([lab, "--no-browser", "--port", str(a.port)], env={**os.environ, "BTSIM_ROOT": ROOT}, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                info = ask(a.port, "info")
                break
            except Exception:
                time.sleep(0.5)
        else:
            sys.exit("the desktop Lab did not start")
        units = ask(a.port, "list_units")["units"]
        boards = ask(a.port, "list_boards")["boards"]
    finally:
        server.terminate()
    # the files
    data = os.path.join(ROOT, "data")
    meks = zipfile.ZipFile(os.path.join(data, "meks.zip"))
    maps = zipfile.ZipFile(os.path.join(data, "maps.zip"))

    def unit_text(i):
        if i.startswith("meks/"):
            return meks.read(i).decode("utf-8", "replace")
        return open(os.path.join(data, i), encoding="utf-8", errors="replace").read()

    def board_text(i):
        if i.startswith("maps/"):
            return maps.read(i[len("maps/"):]).decode("utf-8", "replace")
        return open(os.path.join(data, i), encoding="utf-8", errors="replace").read()

    kept_units = [u for u in units if u.get("ok")]
    kept_boards = [b for b in boards if (b["width"], b["height"]) == (16, 17)]
    print(f"units {len(kept_units)} of {len(units)} (the rest the engine cannot play); boards {len(kept_boards)} of {len(boards)} (16x17 only)")
    files, raw, stripped = [], 0, 0
    for u in kept_units:
        t = unit_text(u["id"])
        s = strip_fluff(t)
        raw += len(t); stripped += len(s)
        files.append((u["id"], s))
    for b in kept_boards:
        files.append((b["id"], board_text(b["id"])))
    print(f"unit files {raw/1e6:.1f} MB -> {stripped/1e6:.1f} MB after the fluff")
    block = bytearray()
    for name, text in files:
        n, t = name.encode(), text.encode()
        block += struct.pack("<I", len(n)) + n + struct.pack("<I", len(t)) + t
    out = a.out
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    packed = gzip.compress(bytes(block), 9, mtime=0)
    with open(os.path.join(out, "data.pack.gz"), "wb") as f:
        f.write(packed)
    if a.b64:
        import base64
        open(os.path.join(out, "data.pack.b64.txt"), "w").write(base64.b64encode(packed).decode())
    # a unit's list entry without what only the desktop's own pages use is the same; keep the entry whole
    catalog = {"units": kept_units, "boards": kept_boards,
               "info": {"bots": info["bots"], "default_board": info["default_board"], "skill_table": info["skill_table"]}}
    json.dump(catalog, open(os.path.join(out, "catalog.json"), "w"), separators=(",", ":"))
    shutil.copy(os.path.join(engine, "defaults", "config.json"), os.path.join(out, "defaults.json"))
    for n in ("index.html", "lab.css", "lab.js", "options.json", "availability.json"):
        shutil.copy(os.path.join(engine, "lab", "web", n), os.path.join(out, n))
    for n in ("wasmio.js", "engine.js", "worker.js"):
        shutil.copy(os.path.join(engine, "wasm", "web", n), os.path.join(out, n))
    shutil.copy(wasm, os.path.join(out, "combatlab.wasm"))
    # the page loads the glue before lab.js
    html = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    html = html.replace('<script src="lab.js"></script>', '<script src="wasmio.js"></script>\n<script src="engine.js"></script>\n<script src="lab.js"></script>')
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
    for n in sorted(os.listdir(out)):
        print(f"  {n:20} {os.path.getsize(os.path.join(out, n))/1e6:7.2f} MB")


if __name__ == "__main__":
    main()
