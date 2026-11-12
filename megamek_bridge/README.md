# megamek_bridge - our bots as players in a live MegaMek game

The Java half of the MegaMek bridge. The plan, what MegaMek offers, the wire and every stage's check:
`../INTEGRATION__MEGAMEK_BRIDGE.md`. The Rust half is `engine/core/src/bridge.rs` (`btsim decide`).

**MegaMek is never forked or edited** (Daniel, 2026-11-12). This code compiles against an unchanged MegaMek release
and uses it as a library. It is built on MegaMek, which is GPL v3, so this folder is GPL v3 too.

## Files

| File | What |
|---|---|
| `src/btbridge/HydraBridge.java` | The bot player: Princess with movement, firing and physical attacks (punches, kicks) asked of our engine (as MegaMek's CASPAR is Princess with parts swapped); anything that can't be done that way is a counted FALLBACK to Princess |
| `src/btbridge/GameView.java` | What our engine is told: the game's start as settings, and each unit's state as MegaMek knows it before every question |
| `src/btbridge/DecisionProcess.java` | `btsim decide` as a child process, one JSON line in, one out |
| `src/btbridge/BridgeLauncher.java` | Plays ONE game of a MegaMek scenario (`.mms`) with our bot on the named players and MegaMek's bots on the rest; writes one JSON record line |
| `build.sh` | Builds `build/megamek_bridge.jar` |

## Use

```bash
# once: an unchanged MegaMek release, unpacked (about 580 MB download)
curl -sSL -o mm.tar.gz https://github.com/MegaMek/megamek/releases/download/v0.51.01.7/MegaMek-0.51.01.7.tar.gz
tar xzf mm.tar.gz
```

```bash
MEGAMEK=/path/to/MegaMek-0.51.01.7 megamek_bridge/build.sh
```

```bash
cd /path/to/MegaMek-0.51.01.7 && mkdir -p savegames && java -Djava.awt.headless=true -cp "/path/to/megamek_bridge/build/megamek_bridge.jar:MegaMek.jar:lib/*" btbridge.BridgeLauncher GAME.mms --btsim /path/to/engine/target/release/btsim --bridge Red --rounds 100 --timeout 10 --records records.jsonl --label "my game"
```

Each game appends one line to the records file: who drove whom, the result, each team's standing, and for our bot
the decisions our engine made ("ours") and the ones Princess made instead ("fallbacks", by reason). Every decision is
also logged in MegaMek's `logs/unified_log.log` (`[bridge]` lines). Units must have their `.mtf` in our `data/`
folder ("Chassis Model.mtf"), or the bridge stays off for that game.

Run it once per game (MegaMek's own runner sometimes stalls at the start of a game; one game per run keeps a stall to
that game). The scenario format and an example: `INTEGRATION__MEGAMEK_BRIDGE.md` Section 1b. All bots, ours and
MegaMek's, fight to the end (forced withdrawal and fleeing off), as our engine's battles do.
