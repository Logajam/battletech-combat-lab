"""
tools/port_coverage.py - RUST PORT stage 0: which engine functions do the fixture battles never reach?

    python tools/port_coverage.py                     # all scenarios of tools/port_scenarios.py
    python tools/port_coverage.py NAME [NAME ...]     # only these
    python tools/port_coverage.py --report FILE       # write the list to FILE (default: coverage_report.txt in the scratch dir)

Runs each scenario's recording under coverage.py (one process per scenario, side by side), combines the data, and
lists, per engine module, every function whose body never ran. A function the fixtures never reach is a function
whose translation is unchecked (INTEGRATION__RUST_PORT.md, stage 0): the list is kept in that file, each entry
either covered by a new scenario or explained ("a test builds it by hand", "an error branch", ...).

Engine modules = the rules and bot modules of the port (the table in INTEGRATION__RUST_PORT.md): not output, art,
pickers, tests or tools.
"""
import ast
import glob
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import port_scenarios  # noqa: E402

# Not translated (RUST_PORT "What gets translated"): output pages, the pickers, the Combat Lab art, the stat viewers.
NOT_ENGINE = {"replay", "results", "stats", "stats_report", "saved_state", "timing", "main", "file_picker",
              "map_picker", "tokens", "shell", "shell_facet", "shell_items", "token_mesh", "decisions"}


def engine_files():
    files = []
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "INTEGRATION__*.py"))):
        name = os.path.basename(path)[len("INTEGRATION__"):-3]
        if name not in NOT_ENGINE:
            files.append(path)
    files += sorted(glob.glob(os.path.join(REPO_ROOT, "mechsim", "*.py")))
    files += sorted(glob.glob(os.path.join(REPO_ROOT, "pathfinder", "*.py")))
    return files


def run(name, data_file, out_dir):
    env = dict(os.environ, INTEGRATION_DATA_DIR="./data", PYTHONIOENCODING="utf-8", COVERAGE_FILE=data_file)
    proc = subprocess.run([sys.executable, "-m", "coverage", "run", "--parallel-mode",
                           "tools/port_record.py", "--scenario", name, os.path.join(out_dir, name)],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return name, proc.returncode, proc.stderr[-800:]


def functions(path):
    """[(qualified name, first body line, last line)] of every def in the file."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # the first statement that EXECUTES: not the docstring, not `global` / `nonlocal` (no line event)
                body = [st for st in child.body if not isinstance(st, (ast.Global, ast.Nonlocal))
                        and not (isinstance(st, ast.Expr) and isinstance(getattr(st, "value", None), ast.Constant))]
                first = body[0].lineno if body else child.lineno
                out.append((prefix + child.name, first, child.end_lineno))
                walk(child, prefix + child.name + ".")
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix + child.name + ".")
    walk(tree, "")
    return out


def main(argv):
    report_path = None
    if "--report" in argv:
        report_path = argv[argv.index("--report") + 1]
    names = [a for a in argv if a in port_scenarios.SCENARIOS] or list(port_scenarios.SCENARIOS)
    # One data file per scenario, kept in engine/fixtures/_coverage (git-ignored): only scenarios without one are run,
    # so adding a scenario costs one run. --rerun redoes all (after the engine changes).
    store = os.path.join(REPO_ROOT, "engine", "fixtures", "_coverage")
    os.makedirs(store, exist_ok=True)
    work = tempfile.mkdtemp(prefix="port_coverage_")
    todo = [n for n in names if "--rerun" in argv or not os.path.exists(os.path.join(store, n + ".cov"))]
    todo.sort(key=lambda n: -port_scenarios.SCENARIOS[n][1])
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        jobs = [pool.submit(run, n, os.path.join(work, f".coverage.{n}"), os.path.join(work, "out")) for n in todo]
        for job in jobs:
            name, code, err = job.result()
            print(("ok   " if code == 0 else "FAIL ") + name + ("" if code == 0 else "\n" + err), flush=True)
            for f in os.listdir(work):
                if f.startswith(f".coverage.{name}."):          # coverage's parallel-mode suffix
                    os.replace(os.path.join(work, f), os.path.join(store, name + ".cov"))
    import coverage
    combined = os.path.join(work, ".coverage")
    cov = coverage.Coverage(data_file=combined)
    cov.combine([os.path.join(store, n + ".cov") for n in names if os.path.exists(os.path.join(store, n + ".cov"))],
                keep=True)
    cov.save()
    data = coverage.CoverageData(basename=combined)
    data.read()
    lines_out, total, missed = [], 0, 0
    for path in engine_files():
        executed = set(data.lines(path) or [])
        if not executed and not data.measured_files():
            continue
        funcs = functions(path)
        total += len(funcs)
        never = [f for f in funcs if not any(f[1] <= ln <= f[2] for ln in executed if ln >= f[1]) or f[1] not in executed]
        # a function is reached when its first body statement ran
        never = [f for f in funcs if f[1] not in executed]
        missed += len(never)
        if never:
            rel = os.path.relpath(path, REPO_ROOT)
            lines_out.append(f"{rel}  ({len(never)} of {len(funcs)} functions never reached)")
            lines_out += [f"    {f[0]}  (line {f[1]})" for f in never]
    summary = f"{missed} of {total} engine functions never reached by {len(names)} scenario(s)."
    text = summary + "\n" + "\n".join(lines_out) + "\n"
    report_path = report_path or os.path.join(work, "coverage_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(summary + f"\nFull list: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
