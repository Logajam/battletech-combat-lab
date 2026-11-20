"""
tools/unpack_answer_key.py - unpack the frozen answer key into engine/fixtures/ (git-ignored).

    python tools/unpack_answer_key.py            # unpack if engine/fixtures/ is missing or older than the archive
    python tools/unpack_answer_key.py --force    # unpack again whatever is there

The Python engine was the Rust engine's answer key (INTEGRATION__RUST_PORT.md: "exact match or not done"). When it was
removed (Daniel, 2026-11-20: "dead code the python"), its recordings were made one last time and frozen in
engine/answer_key.tar.xz: the 63 fixture battles (config, board, units, dice, decisions, trace, log, replay record), the
units they need (_units), and the stage 1-3 comparison files. The Rust tests read engine/fixtures/ as before;
tests/run_checks.py calls this first. The Python code that made them is in git history (the commit before its removal:
see the 2026-11-20 Change Record entry "PYTHON ENGINE REMOVED").
"""
import os
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, "engine", "answer_key.tar.xz")
OUT = os.path.join(ROOT, "engine", "fixtures")
STAMP = os.path.join(OUT, ".answer_key_unpacked")


def main(argv):
    if not os.path.exists(ARCHIVE):
        print("unpack_answer_key: no", ARCHIVE)
        return 1
    if "--force" not in argv and os.path.exists(STAMP) and os.path.getmtime(STAMP) >= os.path.getmtime(ARCHIVE):
        return 0
    os.makedirs(OUT, exist_ok=True)
    with tarfile.open(ARCHIVE, "r:xz") as t:
        t.extractall(OUT, filter="data")
    open(STAMP, "w").close()
    print("unpack_answer_key: engine/fixtures/ unpacked from engine/answer_key.tar.xz")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
