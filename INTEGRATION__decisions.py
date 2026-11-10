"""
INTEGRATION__decisions.py - the decision seam (RUST PORT stage 0b, INTEGRATION__RUST_PORT.md).

Every choice a BOT makes that the engine then acts on goes through decide():

    foe = decisions.decide("foe", (mover,), lambda: ...compute it...)

Normal play (MODE None): decide() just calls compute() and returns its answer - the seam changes nothing, which
tests/test_port_record.py and the reference logs prove.

RECORD: the answer is also written to RECORDS (with the dice drawn and the log lines printed while computing it),
by tools/port_record.py's codec for that kind. Only the OUTERMOST decision is recorded: a decision computed inside
another one (a bot weighing a target by a dry run of the whole declaration) is part of that bot's thinking, not an
event of the battle.

REPLAY: compute() is NOT called. The recorded answer comes back instead (decoded to live objects by the codec),
and the log lines that computing it printed are printed again, so a replay's log is the original's. With both bots
switched off this way a battle plays from decisions.json + dice.json alone - which proves the list complete and is
what the Rust engine's stage 6 does.

The codecs (encode / decode / name for each kind) live in tools/port_record.py; the engine only knows kinds.
"""

MODE = None            # None | "record" | "replay"
RECORDS = []           # record mode: one dict per outermost decision; replay mode: the list being played back
CODECS = {}            # kind -> object with name(ctx), encode(value, ctx), decode(raw, ctx)
HOOKS = {}             # "dice_count" -> fn() -> dice drawn so far; "phase" -> fn() -> label; set by the recorder
_depth = 0
_cursor = 0
_captured = None       # log lines printed during the outermost decision being computed
_captured_stubs = None # stub warnings [name, message] raised during it (each also counts in stubs._ACTIVE and prints to stderr)


class ReplayMismatch(Exception):
    """The replay was asked for a different decision than the one recorded at this place."""


def reset():
    global MODE, _depth, _cursor, _captured, _captured_stubs
    MODE, _depth, _cursor, _captured, _captured_stubs = None, 0, 0, None, None
    RECORDS.clear()


def decide(kind, ctx, compute):
    """`ctx`: a tuple of the live objects the choice is about (the codec turns them into names)."""
    global _depth, _cursor, _captured, _captured_stubs
    if MODE is None:
        return compute()
    codec = CODECS[kind]
    who = codec.name(ctx)
    if MODE == "replay":
        if _depth:
            return compute()                       # inside a decision that was replayed: cannot happen
        if _cursor >= len(RECORDS):
            raise ReplayMismatch(f"decision {_cursor + 1}: asked for {kind} {who} but the record has ended")
        rec = RECORDS[_cursor]
        if rec["kind"] != kind or rec["who"] != who:
            raise ReplayMismatch(f"decision {_cursor + 1}: asked for {kind} {who}, record has {rec['kind']} "
                                 f"{rec['who']} (phase {rec['phase']})")
        _cursor += 1
        import INTEGRATION__config as config
        HOOKS["skip_dice"](rec["dice_drawn"])      # dice the bot itself drew while computing: not the engine's
        for line in rec["log"]:
            config.log(line)
        import INTEGRATION__stubs as stubs
        for name, msg in rec["stubs"]:
            stubs._warn(name, msg)
        return codec.decode(rec["value"], ctx)
    # record
    if _depth:
        return compute()
    dice_before = HOOKS["dice_count"]()
    _depth, _captured, _captured_stubs = 1, [], []
    try:
        value = compute()
    finally:
        _depth = 0
        lines, _captured = _captured, None
        stub_calls, _captured_stubs = _captured_stubs, None
    RECORDS.append({"n": len(RECORDS) + 1, "kind": kind, "who": who, "phase": HOOKS["phase"](),
                    "dice_before": dice_before, "dice_drawn": HOOKS["dice_count"]() - dice_before,
                    "log": lines, "stubs": stub_calls, "value": codec.encode(value, ctx)})
    return value


def capture_log(msg):
    """Called by the recorder's wrapper of config.log: keeps the lines printed inside a recorded decision."""
    if _captured is not None:
        _captured.append(msg)


def capture_stub(name, msg):
    """Called by the recorder's wrapper of stubs._warn: keeps the stub warnings raised inside a recorded decision."""
    if _captured_stubs is not None:
        _captured_stubs.append([name, msg])
