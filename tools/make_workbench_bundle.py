"""Build the Combat Lab Workbench bundle for a Windows desktop (2026-11-05, Claude): a zip with the workbench, the builder modules it
imports, the data they read, the unit library and a double-click starter (tools/workbench_windows/).

    python -I tools/make_workbench_bundle.py <out.zip>
"""
import os
import sys
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FILES = ["INTEGRATION__tokens.py", "INTEGRATION__token_mesh.py", "INTEGRATION__shell.py", "INTEGRATION__shell_items.py",
         "INTEGRATION__shell_facet.py", "INTEGRATION__structure_table.py", "mechsim/equipment.json",
         "tools/token_workbench.py", "tools/token_workbench.html", "tools/token_audit.py", "tools/token_sheet.py",
         "data/token_densities.json", "data/token_reference_tags.json", "data/token_overrides.json", "data/token_dictionary.json",
         "data/meks.zip"]
TOP = {"tools/workbench_windows/start_workbench.bat": "start_workbench.bat", "tools/workbench_windows/README.txt": "README.txt"}


def main(out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(os.path.join(ROOT, f), "Combat Lab Workbench/" + f)
        for f, name in TOP.items():
            z.write(os.path.join(ROOT, f), "Combat Lab Workbench/" + name)
    print(out, os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1])
