"""
INTEGRATION__file_picker.py

THE single file-picker module for the integration project. Consolidates
MECHSIM__file_picker.py and PATHFINDER__file_picker.py (2026-08-28,
Daniel) - one shared tkinter dialog core and one shared last-used-path
store instead of two near-duplicate implementations. The two source
projects' single-file UX flows (choose_mtf_file's ask-to-reuse vs
choose_board_file's dialog-first-then-silent-fallback) behave differently
on purpose, so they're kept as separate functions rather than merged.
"""

import json
import os

_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".file_picker_state.json")

MTF_FILETYPES = [("MegaMek unit files", "*.mtf"), ("All files", "*.*")]
BOARD_FILETYPES = [(".board files", "*.board"), ("All files", "*.*")]

# =============================================================================
# ==========================  SHARED STATE  ===================================
# =============================================================================
# One JSON file, one {purpose: last_path} dict, shared by everything below -
# replaces MECHSIM's sim_last_unit.json + .last_dirs.json and PATHFINDER's
# .last_map_path.json (three separate stores for the same "remember where
# to open the dialog next time" idea).


def _load_state() -> dict:
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(data: dict) -> None:
    try:
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        print(f"WARNING: could not save file-picker state ({e}) - remembered paths won't persist.")


def _remembered_path(purpose: str) -> str:
    """Returns the last path saved under this purpose, or None."""
    return _load_state().get(purpose)


def _remembered_dir(purpose: str) -> str:
    """Returns the directory of the last path saved under this purpose,
    if that directory still exists - otherwise None."""
    path = _remembered_path(purpose)
    if path and os.path.isdir(os.path.dirname(path)):
        return os.path.dirname(path)
    return None


def _remember(purpose: str, path: str) -> None:
    data = _load_state()
    data[purpose] = path
    _save_state(data)


# =============================================================================
# ==========================  DIALOG CORE  =====================================
# =============================================================================
def _browse_for_files(title: str, filetypes: list, initial_dir: str = None) -> list:
    """Native OS multi-select 'Open File' dialog via tkinter. Returns a
    list of selected paths - empty if cancelled or if tkinter isn't
    available (callers decide how to fall back)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as e:
        print(f"WARNING: couldn't open a native file picker ({e}).")
        return []

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    kwargs = {"title": title, "filetypes": filetypes}
    if initial_dir:
        kwargs["initialdir"] = initial_dir
    paths = filedialog.askopenfilenames(**kwargs)
    root.destroy()
    return list(paths)


# =============================================================================
# ==========================  GENERIC MULTI-PICKER (WIRED)  ===================
# =============================================================================
# Already in production use - INTEGRATION__config.py's load_two_mechs()
# calls this for both mechs, and MECHSIM__compare_runs.py calls it for
# run-stats JSON selection.
def pick_files(purpose: str, title: str, filetypes: list, count: int) -> list:
    """Opens a multi-select dialog at the directory last used for this
    purpose, remembers whichever directory was actually used, and HARD
    FAILS (ValueError) if the user selects anything other than exactly
    `count` files."""
    paths = _browse_for_files(title, filetypes, initial_dir=_remembered_dir(purpose))

    if len(paths) != count:
        raise ValueError(f"Expected exactly {count} file(s) to be selected for '{purpose}', "
                          f"but {len(paths)} were selected. Try again and select exactly {count}.")

    _remember(purpose, paths[0])
    return paths


# =============================================================================
# ==========================  SINGLE-FILE CONVENIENCE PICKERS (NOT WIRED)  ====
# =============================================================================
# Neither is called from the current integration path - load_two_mechs()
# uses pick_files() directly. choose_board_file() is a slot for
# INTEGRATION__config.py's not-yet-wired map-loading section.

def choose_mtf_file(purpose: str = "mtf") -> str:
    """Asks whether to reuse the last-picked file (if any) before opening
    a dialog; falls back to typed input if no dialog is available.
    Returns None if the user leaves everything blank."""
    last_path = _remembered_path(purpose)
    if last_path:
        choice = input(f"Last unit used: {last_path}\nPick a new unit? [y/N]: ").strip().lower()
        if choice not in ("y", "yes"):
            return last_path

    picked_list = _browse_for_files("Select a .mtf unit file", MTF_FILETYPES)
    picked = picked_list[0] if picked_list else None
    if not picked:
        typed = input("Enter path to a .mtf file (blank = use the built-in fixture mech): ").strip()
        picked = typed or None

    if picked:
        _remember(purpose, picked)
    return picked


def choose_board_file(purpose: str = "board") -> str:
    """Opens a dialog defaulting to the last-used directory; silently
    reuses the remembered path if the dialog is cancelled. Raises
    ValueError if there's neither a new selection nor a remembered path."""
    last_path = _remembered_path(purpose)
    picked_list = _browse_for_files("Select a MegaMek .board map file", BOARD_FILETYPES,
                                     initial_dir=_remembered_dir(purpose))
    picked = picked_list[0] if picked_list else None

    if picked:
        _remember(purpose, picked)
        return picked

    if last_path:
        print(f"No file selected - reusing last map: {last_path}")
        return last_path

    raise ValueError("No map file selected and no previously remembered map path exists - "
                      "can't proceed without a board file.")
