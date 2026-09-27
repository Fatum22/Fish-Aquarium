"""Cache busting: stamp one build id on every local <script src> and <link rel=stylesheet> in index.html
(?v=<build>), so phones fetch fresh files after an update instead of running stale cached ones.
Run before committing a release:  python3 tools/bump_build.py [build-id]
Default build id = UTC time YYYYMMDDHHMM (always increases). tests/verify.py checks every tag carries the same id."""
import os, re, sys, time
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")
build = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d%H%M", time.gmtime())
assert re.fullmatch(r"[0-9A-Za-z._-]+", build), "build id: letters, digits, . _ - only"
s = open(HTML).read()
pat = re.compile(r'((?:src|href)=")((?!https?:|//|data:)[^"?#]+\.(?:js|css))(?:\?v=[^"]*)?(")')
s, n = pat.subn(lambda m: f"{m.group(1)}{m.group(2)}?v={build}{m.group(3)}", s)
open(HTML, "w").write(s)
print(f"index.html: {n} script/CSS tags stamped ?v={build}")
