# Trial records

One file per trial run, one JSON line per batch, every battle's result: its number in the set (`sim`), its own dice
seed, winner, turns, whether it reached the turn cap, each team's armor + structure left. Written by
`tools/hydra_trial.py` and `tools/round_robin.py` (format: `tools/trial_records.py`); `tools/replay_undecided.py`
plays a file's undecided battles on with a higher turn cap (Daniel, 2026-11-12).

`megamek_bridge.jsonl`: games played in MegaMek through the bridge (`tools/megamek_bridge_games.py`,
INTEGRATION__MEGAMEK_BRIDGE.md), one JSON line per game: the scenario, who drove each player (our "bridge" or
MegaMek's PRINCESS / CASPAR), finished, rounds, the winning team (by Battle Value left), each team's units and BV,
and for our bot the decisions our engine made ("ours") and those Princess made instead ("fallbacks", by reason).
