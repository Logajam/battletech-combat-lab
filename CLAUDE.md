# CLAUDE.md

BattleTech Monte Carlo simulator: two mechs (`.mtf`) fight on a hex board under
the Core Rulebook, many times over, and the results are summarized. Daniel owns
the BattleTech rules and scope calls; Claude owns the implementation and the
GitHub logistics.

## Start here

1. Read `INTEGRATION__PROJECT_MAP.md` **Section 0** ("read this first"): what's
   built, how to run and test, and the "Pick up here" list of open work.
2. Section 7 of the same file holds Daniel's standing instructions. Section 5
   holds his decisions (implementation may not override them). Section 6 lists
   every bot decision point and the future-capability Memo. Section 8 is the
   Change Record, newest first.
3. `INTEGRATION__RULES_REVIEW.md` is the Core Rulebook vs code review: fixed
   items, the gap list to build, and open questions for Daniel.
4. `INTEGRATION__CALL_GRAPH.md` shows the import structure, and `README.md` the
   layout and test commands.

## Working rules (details in PROJECT_MAP Section 7)

- **Rules come from the library, never from memory.** Use
  `rules/Battletech_Rule_Reference_Index.zip`, unzipped OUTSIDE the repo. The
  Core Rulebook is in `base/core-rules/*.md`, and a `[p.N]` marker comes before
  page N's text. Cite the page in the code. If the library doesn't settle a
  rule, ask Daniel.
- **Logistics are Claude's** (Daniel: "You're in charge of the logistics").
  Work on the session branch, commit, push, open a PR to `main`, and merge it
  once every test passes. Daniel doesn't use GitHub, so tell him in plain words
  what changed.
- **After every change:**
  - Run `python tests/run_checks.py` (about 12 min since the lifetime default -
    the Asymptote mirror reference battle stalls to 488 turns): every `tests/test_*.py`
    plus every reference battle, side by side, one line each. All must pass.
  - A reference log that differs: if the change was meant to alter results, run
    `python tests/check_reference_logs.py --update` and record that in the
    Change Record.
  - Add `--bench` (the 10-turn benchmark) for anything on the hot path. A
    speed-only change must keep the results identical. It prints where the time
    went (`INTEGRATION__timing`), as every batch does.
- **Show Daniel battles as replays.** Set `REPLAY_BATTLES` in
  `INTEGRATION__config.py`, run, and publish the page from `replays/` with the
  Artifact tool; give him the link (he doesn't run the code himself).
- **Optional rules** (where the rulebook offers a choice, or Daniel's rule
  differs from it) are switches in `INTEGRATION__config.py`'s OPTIONAL RULES
  section, with the rules-as-written version available.
- **Keep going.** Don't pause at natural checkpoints. Stop only for a rules or
  scope call that is Daniel's.
- **Placeholders** are loud, counted stubs in `INTEGRATION__stubs.py`, never
  silent defaults. New bot decisions get a Section 6 row. A decision Daniel
  calls "research" (rate of fire, MASC, ammo kind...) is built as options
  plus a stub that picks.
- **Known issues** Daniel names go in PROJECT_MAP Section 4 ("Known issues to
  fix later").
- **Code style:** Daniel reads the code but doesn't write it. Keep it clean,
  explicit and commented to match the surrounding files, and sign changes in
  the Change Record.
- **File names:** keep the `INTEGRATION__` / `mechsim/` / `pathfinder/` split.
