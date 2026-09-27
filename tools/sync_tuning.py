"""Paste Designer's tuning.json verbatim over config.js TUNING (keys/order unchanged).
Run: python3 tools/sync_tuning.py"""
import json, os
SRC = "/workspace/studio/briefs/aquarium/design/tuning.json"
CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.js")
tj = open(SRC).read().strip(); json.loads(tj)
s = open(CFG).read()
a = s.index("  TUNING: ") + len("  TUNING: ")
b = s.index(",\n\n  // ---- Tank XP source switch")
s = s[:a] + "\n".join(("  " + l if i else l) for i, l in enumerate(tj.splitlines())) + s[b:]
open(CFG, "w").write(s)
print("config.js TUNING synced from", SRC)
