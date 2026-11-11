"""Hydra v the house bot, same seeds, sides swapped (INTEGRATION__HYDRA.md, Section 4).

    python tools/hydra_trial.py SCENARIO_DIR [SCENARIO_DIR ...] [--battles 20] [--seed 1] [--threads N]

For each scenario folder (config.json, units.json, board.json; e.g. engine/fixtures/<name>) it runs three batches with
the release btsim: nobody is Hydra (the baseline), the first team is Hydra, the second team is Hydra. One line each:
wins per team, draws, mean turns, seconds per battle. Two measures of Hydra against the house bot, each averaged over the two sides so the
'Mechs and the starting edge cancel out: win share (Hydra's wins minus the same team's baseline wins) and the
strength-left margin (my team's surviving armor + structure share minus the enemy's; a draw that saves the 'Mech counts).
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")


def option(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def run(folder, battles, seed, threads, hydra):
    cmd = [BTSIM, folder, "--battles", str(battles), "--seed", str(seed)]
    if threads:
        cmd += ["--threads", threads]
    if hydra:
        cmd += ["--hydra", hydra]
    out = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    return out


def main(argv):
    battles = int(option(argv, "--battles", "20"))
    seed = int(option(argv, "--seed", "1"))
    threads = option(argv, "--threads", None)
    folders = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--"))]
    edges = []
    for folder in folders:
        units = json.load(open(os.path.join(folder, "units.json")))
        teams = []
        for u in units.values():
            if u["team"] not in teams:
                teams.append(u["team"])
        house = sorted({u["bot"] for u in units.values()})
        print(f"{os.path.basename(folder.rstrip('/'))}: {len(units)} units, teams {teams}, house bot {house}, {battles} battles")
        share, margin = {}, {}
        for label, hydra in [("baseline", None)] + [(f"Hydra={t}", t) for t in teams]:
            out = run(folder, battles, seed, threads, hydra)
            wins = out["wins"]
            line = ", ".join(f"{t} {wins.get(t, 0)}" for t in teams)
            other = sum(v for k, v in wins.items() if k not in teams)
            print(f"  {label:14s} {line}, other {other}; mean turns {out['mean_turns']:.1f}; {out['seconds'] / battles:.2f} s/battle (wall, all threads)")
            share[label] = {t: wins.get(t, 0) / battles for t in teams}
            # strength left: a team's final armor + structure as a share of what it began with, minus the other team's
            left = {t: sum(r["teams"][t]["final_hp"] / max(r["teams"][t]["max_hp"], 1) for r in out["results"]) / battles for t in teams}
            margin[label] = {t: left[t] - sum(left[o] for o in teams if o != t) / max(len(teams) - 1, 1) for t in teams}
        edge = sum(share[f"Hydra={t}"][t] - share["baseline"][t] for t in teams) / len(teams)
        gain = sum(margin[f"Hydra={t}"][t] - margin["baseline"][t] for t in teams) / len(teams)
        print(f"  Hydra over the house bot: win share {edge:+.2f}, strength-left margin {gain:+.3f} (0 = no better)")
        edges.append((edge, gain))
    if len(edges) > 1:
        print(f"ALL {len(edges)} scenarios: mean win-share edge {sum(e for e, _ in edges) / len(edges):+.3f}, mean margin gain {sum(g for _, g in edges) / len(edges):+.3f}")


if __name__ == "__main__":
    main(sys.argv[1:])
