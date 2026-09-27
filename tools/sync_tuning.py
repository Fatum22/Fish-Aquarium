"""Paste Designer's tuning.json verbatim over config.js TUNING (keys/order unchanged).
Run: python3 tools/sync_tuning.py [path/to/tuning.json]
The v4 build is pinned to design/v4_archive/tuning.json (v5.1 = tank levels 6-10 lands after the v4 rebuild,
bible change 19:48 item 4). Pass the live design/tuning.json explicitly when that work starts."""
import json, os, sys
SRC = sys.argv[1] if len(sys.argv) > 1 else "/workspace/studio/briefs/aquarium/design/v4_archive/tuning.json"
CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.js")
tj = open(SRC).read().strip(); json.loads(tj)
s = open(CFG).read()
a = s.index("  TUNING: ") + len("  TUNING: ")
b = s.index(",\n  // ---- END VERBATIM tuning.json")
s = s[:a] + "\n".join(("  " + l if i else l) for i, l in enumerate(tj.splitlines())) + s[b:]
open(CFG, "w").write(s)
print("config.js TUNING synced from", SRC)
