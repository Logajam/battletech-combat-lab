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
PRIVATE_PATHS = ["rules/", "reference_art/"]
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


# (The BTTT hold was lifted 2026-11-25: Daniel, "We have permission to use BTTT live now." BTTT ships in public builds.)

def main(argv):
    push = "--push" in argv
    if git(["rev-parse", "--is-shallow-repository"], REPO_ROOT).strip() == "true":
        git(["fetch", "--unshallow", "origin", "main"], REPO_ROOT)
    git(["fetch", "origin", "main"], REPO_ROOT)
    work = tempfile.mkdtemp(prefix="publish_public_")
    git(["init", "-q", "-b", "scratch"], work)
    git(["fetch", "-q", REPO_ROOT, "refs/remotes/origin/main:refs/heads/main"], work)
    git(["checkout", "-q", "main"], work)
    cmd = ["git", "filter-repo", "--force", "--invert-paths"] + sum([["--path-glob", p + "*"] if not p.endswith("/") and not p.endswith(".rs") else ["--path", p] for p in PRIVATE_PATHS], []) + ["--commit-callback", CALLBACK]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if r.returncode: sys.exit('filter-repo failed: ' + r.stderr[-600:])

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
        # THE PUBLIC HISTORY IS NEVER REWRITTEN. The rewrite is deterministic only while PRIVATE_PATHS stays the same: when a path leaves
        # the list (the BTTT hold, lifted 2026-11-25), the rewritten history no longer extends what was published. Then the files of the
        # rewritten tip go on top of the public main as ONE ordinary commit (a sync), never a forced push.
        git(["fetch", "-q", "public", "main"], work)
        public_tip = git(["rev-parse", "FETCH_HEAD"], work).strip()
        if subprocess.run(["git", "merge-base", "--is-ancestor", public_tip, "main"], cwd=work).returncode != 0:
            tree, src = git(["rev-parse", "main^{tree}"], work).strip(), git(["rev-parse", "origin/main"], REPO_ROOT).strip()[:10]
            msg = f"Sync with the private repository (its main at {src}): the files as they are now, on top of the history already published"
            env = {**os.environ, "GIT_AUTHOR_NAME": "Logajam", "GIT_AUTHOR_EMAIL": "56737113+Logajam@users.noreply.github.com", "GIT_COMMITTER_NAME": "Logajam", "GIT_COMMITTER_EMAIL": "56737113+Logajam@users.noreply.github.com"}
            sync = subprocess.run(["git", "commit-tree", tree, "-p", public_tip, "-m", msg], cwd=work, capture_output=True, text=True, env=env, check=True).stdout.strip()
            git(["update-ref", "refs/heads/main", sync], work)
            print(f"  the rewritten history does not extend the published one: one sync commit {sync[:10]} on top of {public_tip[:10]}")
        out = subprocess.run(["git", "push", "public", "main:main"], cwd=work, capture_output=True, text=True)
        print(out.stdout + out.stderr)
        if out.returncode:
            raise SystemExit("push failed")
        shutil.rmtree(work)
        print(f"published to {PUBLIC_URL}")


if __name__ == "__main__":
    main(sys.argv[1:])
