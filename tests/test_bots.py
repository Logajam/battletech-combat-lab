"""
tests/test_bots.py - checks the per-unit bot choice (INTEGRATION__bots, added
2026-10-27): each side's MECH_*_CONFIG["bot"] (else config.BOT) names its bot,
"gladiator" is the default, and an unknown or unbuilt bot is refused at load
time instead of silently falling back.

    python tests/test_bots.py
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
import INTEGRATION__bots as bots  # noqa: E402


def _refused(cfg, error):
    try:
        bots.bot_for(cfg)
    except error:
        return True
    return False


def main():
    failures = []
    if config.BOT != bots.GLADIATOR:
        failures.append(f"config.BOT is {config.BOT!r}, expected the Gladiator default")
    if bots.bot_for({}) != bots.GLADIATOR:
        failures.append("a side with no 'bot' key should get config.BOT")
    if bots.bot_for({"bot": "Gladiator"}) != bots.GLADIATOR:
        failures.append("bot names should be case-insensitive")
    if not _refused({"bot": "princess"}, NotImplementedError):
        failures.append("Princess isn't built yet and should be refused")
    if not _refused({"bot": "nobody"}, ValueError):
        failures.append("an unknown bot name should be refused")
    for f in failures:
        print("FAIL:", f)
    print("test_bots:", "OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
