#!/usr/bin/env python3
"""Publishes COMBAT LAB IN THE BROWSER as a public website (GitHub Pages) from this private repository (Daniel,
2026-11-14: "push the website based version of the simulator onto it, and have it be accessible as a public website").

    python tools/publish_web_lab.py [--push] [--skip-build]

The site is the build tools/build_web_lab.py makes (`web_lab/`: static files). It goes to the `gh-pages` branch of the
PUBLIC repository (github.com/Logajam/battletech-combat-lab), which GitHub Pages serves at
https://logajam.github.io/battletech-combat-lab/ (Settings > Pages > Deploy from a branch: gh-pages, / (root), once).
The branch holds ONLY generated files, one commit per publish, replaced each time (force-pushed): the 7 MB module
changes with every build, so keeping every version would only grow the repository. The source of the site is `main`,
published by tools/publish_public.py: publish that FIRST so the site's code is public too.
Checks before pushing: the build holds no `rules/` text, no unit or board outside the packs, and no email address.
Without --push it builds and checks only.
"""
import os, re, shutil, subprocess, sys, tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_URL = "https://github.com/Logajam/battletech-combat-lab"
WEB = os.path.join(REPO_ROOT, "web_lab")
AUTHOR = ["-c", "user.name=Logajam", "-c", "user.email=56737113+Logajam@users.noreply.github.com"]


def run(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, **kw)


# (The BTTT hold was lifted 2026-11-25: Daniel, "We have permission to use BTTT live now." BTTT ships in public builds.)

def main(argv):
    if "--skip-build" not in argv:
        subprocess.check_call([sys.executable, os.path.join(REPO_ROOT, "tools", "build_web_lab.py")])
    if not os.path.exists(os.path.join(WEB, "combatlab.wasm")):
        raise SystemExit("no build: run tools/build_web_lab.py")
    # the checks: text files carry no email address; nothing but the expected files
    expected = {"index.html", "play.html", "play.js", "tt_layer.js", "boardart.js", "mapview.js", "tabletop.js", "mechsprites.js", "spritemap.js", "sprites", "three.min.js", "playworker.js", "coi.js", "coi-sw.js", "lab.css", "lab.js", "engine.js", "wasmio.js", "worker.js", "combatlab.wasm", "catalog.json", "data.pack.gz",
                "data.pack.b64.txt", "defaults.json", "options.json", "availability.json"}
    names = set(os.listdir(WEB))
    if names - expected:
        raise SystemExit(f"NOT PUBLISHED: unexpected files in web_lab/: {sorted(names - expected)}")
    for n in sorted(names):
        if n.endswith((".html", ".js", ".json", ".css")):
            text = open(os.path.join(WEB, n), encoding="utf-8", errors="replace").read()
            found = [m for m in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text) if not m.endswith(("users.noreply.github.com", "noreply@anthropic.com"))]
            if found:
                raise SystemExit(f"NOT PUBLISHED: {n} holds an email address: {found[:3]}")
    work = tempfile.mkdtemp(prefix="publish_web_")
    shutil.copytree(WEB, work, dirs_exist_ok=True)
    os.remove(os.path.join(work, "data.pack.b64.txt")) if os.path.exists(os.path.join(work, "data.pack.b64.txt")) else None
    if not os.path.exists(os.path.join(work, "data.pack.gz")):
        raise SystemExit("NOT PUBLISHED: no data.pack.gz (build without --b64 only, or restore it)")
    open(os.path.join(work, ".nojekyll"), "w").close()          # no Jekyll processing: serve the files as they are
    run(["git", "init", "-q", "-b", "gh-pages"], work)
    run(["git", "add", "-A"], work)
    stamp = run(["git", "rev-parse", "--short", "HEAD"], REPO_ROOT).stdout.strip()
    run(["git"] + AUTHOR + ["commit", "-q", "-m", f"Combat Lab web build (alpha), from main {stamp}"], work)
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(work) if ".git" not in dp for f in fs) / 1e6
    print(f"site ready in {work}: {len(os.listdir(work))} files, {size:.1f} MB")
    if "--push" in argv:
        run(["git", "remote", "add", "public", PUBLIC_URL], work)
        out = subprocess.run(["git", "push", "--force", "public", "gh-pages:gh-pages"], cwd=work, capture_output=True, text=True)
        print(out.stdout + out.stderr)
        if out.returncode:
            raise SystemExit("push failed")
        shutil.rmtree(work)
        print("published: https://logajam.github.io/battletech-combat-lab/ (once Pages is switched on for the gh-pages branch)")


if __name__ == "__main__":
    main(sys.argv[1:])
