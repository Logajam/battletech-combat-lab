"""
tools/publish_public.py - update the PUBLIC copy of this project (github.com/Logajam/battletech-combat-lab) from this
private repository (Daniel, 2026-11-13: "we'll let this be the public facing version. I think our actual work should stay
in the private repo").

    python tools/publish_public.py [--push]

Takes this repository's full `main` history (fetched from origin, all of it), rewrites it with git filter-repo and, with
--push, pushes it to the public repository's `main`. Without --push it only builds and checks the rewritten copy (in
a scratch folder it prints). What the rewrite removes, from EVERY version:
  - the paths in PRIVATE_PATHS (the rulebook text that once lived in `rules/`: never public, CLAUDE.md);
  - any author or committer email that is not a public no-reply address (replaced by Daniel's GitHub no-reply address,
    name "Logajam"), so no personal email is published.
filter-repo is deterministic: the same history always gives the same rewritten commits, so each publish adds the new
commits on top of the last one (a plain push, never a forced one). The check refuses to push if anything in
PRIVATE_PATHS or a non-public email survives, or if the rewritten tip's files differ from private main's.
Needs `pip install git-filter-repo`.
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_URL = "https://github.com/Logajam/battletech-combat-lab"
# rules/ = the rulebook text that once lived here; reference_art/ = the TRO drawings and the low-poly models redrawn from them
# (Daniel, 2026-11-16: redrawn images and models stay in the private repo)
# BTTT (Daniel, 2026-11-25: not in public builds; removed from main 2026-11-25, `archive/bttt_restore.patch` puts it back): kept out of the
# public copy's whole history too, in case it is ever in the private history under these names
PRIVATE_PATHS = ["rules/", "reference_art/", "engine/core/src/bttt.rs", "engine/core/tests/bttt.rs", "engine/reference/logs/bttt_", "trial_records/2026-11-25_round_robin_bttt", "archive/"]
DANIEL_PUBLIC = b"56737113+Logajam@users.noreply.github.com"
PUBLIC_EMAILS = [b"noreply@anthropic.com", b"users.noreply.github.com", b"noreply@github.com"]

# filter-repo's commit callback (Python, run on each commit): a non-public email becomes Daniel's public address.
CALLBACK = """
PUBLIC = %r
for who in ("author", "committer"):
    email = getattr(commit, who + "_email")
    if not any(email.endswith(p) for p in PUBLIC):
        setattr(commit, who + "_email", %r)
        setattr(commit, who + "_name", b"Logajam")
""" % (PUBLIC_EMAILS, DANIEL_PUBLIC)


def git(args, cwd, **kw):
    return subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True, text=True, **kw).stdout


def public_files(cwd, rev):
    """{path: blob id} of every file at `rev` outside PRIVATE_PATHS. The rewritten copy must equal private main on exactly
    this set (a private folder kept in main, like reference_art/, is not in the copy, so whole-tree hashes can never match)."""
    files = {}
    for line in git(["ls-tree", "-r", rev], cwd).splitlines():
        meta, path = line.split("\t", 1)
        if not any(path.startswith(p) for p in PRIVATE_PATHS):
            files[path] = meta.split()[2]
    return files


HOLD = ("HELD (Daniel, 2026-11-25): the BTTT bot (engine/core/src/bttt.rs) is not to be in any public copy or website build. "
        "It was removed from main; if it is back (archive/bttt_restore.patch applied), this refuses until Daniel says BTTT may go public.")
if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine", "core", "src", "bttt.rs")):
    sys.exit(HOLD)

def main(argv):
    push = "--push" in argv
    if git(["rev-parse", "--is-shallow-repository"], REPO_ROOT).strip() == "true":
        git(["fetch", "--unshallow", "origin", "main"], REPO_ROOT)
    git(["fetch", "origin", "main"], REPO_ROOT)
    work = tempfile.mkdtemp(prefix="publish_public_")
    git(["init", "-q", "-b", "scratch"], work)
    git(["fetch", "-q", REPO_ROOT, "refs/remotes/origin/main:refs/heads/main"], work)
    git(["checkout", "-q", "main"], work)
    cmd = ["git", "filter-repo", "--force", "--invert-paths"] + sum([["--path", p] for p in PRIVATE_PATHS], []) + ["--commit-callback", CALLBACK]
    subprocess.run(cmd, cwd=work, check=True, capture_output=True)

    # the checks
    objects = git(["rev-list", "--all", "--objects"], work)
    leaked = [l for l in objects.splitlines() if any(f" {p}" in l for p in PRIVATE_PATHS)]
    emails = set(git(["log", "--all", "--format=%ae%n%ce"], work).split())
    private_emails = [e for e in emails if not any(e.encode().endswith(p) for p in PUBLIC_EMAILS)]
    same_tree = public_files(work, "HEAD") == public_files(REPO_ROOT, "origin/main")
    count = git(["rev-list", "--count", "HEAD"], work).strip()
    print(f"rewritten copy: {work}\n  {count} commits; private paths left: {len(leaked)}; non-public emails left: {len(private_emails)}; "
          f"latest files identical to private main (private paths aside): {same_tree}")
    if leaked or private_emails or not same_tree:
        raise SystemExit("NOT PUBLISHED: a check failed (see above)")
    if push:
        git(["remote", "add", "public", PUBLIC_URL], work)
        out = subprocess.run(["git", "push", "public", "main:main"], cwd=work, capture_output=True, text=True)
        print(out.stdout + out.stderr)
        if out.returncode:
            raise SystemExit("push failed")
        shutil.rmtree(work)
        print(f"published to {PUBLIC_URL}")


if __name__ == "__main__":
    main(sys.argv[1:])
