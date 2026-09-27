"""Paste Designer's tuning.json over config.js TUNING (keys/order unchanged, text verbatim).
Run: python3 tools/sync_tuning.py [path/to/tuning.json]
The v4 build is pinned to design/v4_archive/tuning.json (v5.1 = tank levels 6-10 and new fish land after the v4 rebuild,
bible change 19:48 item 4). Only the v4-relevant live changes are taken from the live design/tuning.json on top of it:
  - decorations.move (Maksims 20:34: stepPxPerTap split into stepPxPerTapX 8 / stepPxPerTapY 4)
Pass a path to paste that file verbatim instead (e.g. the live tuning.json when the v5.1 work starts).
tests/verify.py builds the same merge (merged_tuning) and asserts TUNING equals it."""
import json, os, re, sys
V4 = "/workspace/studio/briefs/aquarium/design/v4_archive/tuning.json"
LIVE = "/workspace/studio/briefs/aquarium/design/tuning.json"
CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.js")
MOVE = re.compile(r'( *)"move": \{[^{}]*\}')

def merged_text():
    """v4 archive text with its decorations.move block replaced by the live file's block (re-indented)."""
    base, live = open(V4).read().strip(), open(LIVE).read()
    m_live = MOVE.search(live[live.index('"decorations"'):])
    i = base.index('"decorations"'); m_base = MOVE.search(base, i)
    ind_b, ind_l = len(m_base.group(1)), len(m_live.group(1))
    blk = "\n".join((" " * ind_b + l[ind_l:]) if l.startswith(" " * ind_l) else l for l in m_live.group(0).splitlines())
    out = base[:m_base.start()] + blk + base[m_base.end():]
    json.loads(out)
    return out

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else None
    tj = open(src).read().strip() if src else merged_text(); json.loads(tj)
    s = open(CFG).read()
    a = s.index("  TUNING: ") + len("  TUNING: ")
    b = s.index(",\n  // ---- END VERBATIM tuning.json")
    s = s[:a] + "\n".join(("  " + l if i else l) for i, l in enumerate(tj.splitlines())) + s[b:]
    open(CFG, "w").write(s)
    print("config.js TUNING synced from", src or f"{V4} + live decorations.move")
