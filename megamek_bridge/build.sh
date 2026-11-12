#!/bin/sh
# Builds megamek_bridge.jar against an unchanged MegaMek release (INTEGRATION__MEGAMEK_BRIDGE.md).
#   MEGAMEK=/path/to/MegaMek-0.51.01.7 megamek_bridge/build.sh
set -e
: "${MEGAMEK:?set MEGAMEK to the unpacked MegaMek release folder}"
here=$(cd "$(dirname "$0")" && pwd)
rm -rf "$here/build" && mkdir -p "$here/build/classes"
javac -proc:none -encoding UTF-8 --release 21 -cp "$MEGAMEK/MegaMek.jar:$MEGAMEK/lib/*" -d "$here/build/classes" "$here"/src/btbridge/*.java
jar cf "$here/build/megamek_bridge.jar" -C "$here/build/classes" .
echo "built $here/build/megamek_bridge.jar"
