"""INTEGRATION__main.py - thin entry point, no logic of its own.

    python INTEGRATION__main.py

Runs a full batch: INTEGRATION__orchestrator.run_batch() (settings in
INTEGRATION__config.py - mech files, board, seed, batch size, stub knobs).

CHANGED 2026-10-18 (Claude): used to `import config; config.run()`, which
(a) imported a bare `config` module that doesn't exist under the
INTEGRATION__ naming and (b) only loaded two mechs. Now calls the
orchestrator.
"""

import INTEGRATION__orchestrator as orchestrator

if __name__ == "__main__":
    orchestrator.run_batch()
