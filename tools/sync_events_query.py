"""
tools/sync_events_query.py - puts engine/lab/web/events_query.js and events_examples.json INSIDE INTEGRATION__replay_viewer.html.

    python tools/sync_events_query.py          # rewrite the viewer's copy
    python tools/sync_events_query.py --check  # exit 1 if the viewer's copy differs from the files (tests/check_events.py runs this)

Why: a replay page must work opened straight from disk (it is a single file, the replay record inside it), so the search
engine cannot be a separate file it loads. events_query.js is the ONE source: tools/search_events.py runs it under node, and
this copy runs in the browser, so a query gives the same answer in both places.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(ROOT, "INTEGRATION__replay_viewer.html")
JS = os.path.join(ROOT, "engine", "lab", "web", "events_query.js")
EXAMPLES = os.path.join(ROOT, "engine", "lab", "web", "events_examples.json")


def synced(html):
    js = open(JS, encoding="utf-8").read().rstrip("\n")
    ex = open(EXAMPLES, encoding="utf-8").read().strip()
    html, n1 = re.subn(r"(// BEGIN events_query\.js\n).*?(\n// END events_query\.js)", lambda m: m.group(1) + js + m.group(2), html, flags=re.S)
    html, n2 = re.subn(r'(<script id="events-examples" type="application/json">).*?(</script>)', lambda m: m.group(1) + ex.replace("\\", "\\\\") + m.group(2), html, flags=re.S)
    if n1 != 1 or n2 != 1:
        raise SystemExit("the viewer is missing its events_query.js / events-examples markers")
    return html


def main(argv):
    html = open(VIEWER, encoding="utf-8").read()
    new = synced(html)
    if "--check" in argv:
        if new != html:
            print("INTEGRATION__replay_viewer.html is out of date: run python tools/sync_events_query.py")
            return 1
        print("the viewer's event search is in sync with events_query.js")
        return 0
    open(VIEWER, "w", encoding="utf-8", newline="\n").write(new)
    print("viewer updated" if new != html else "viewer already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
