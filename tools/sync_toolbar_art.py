#!/usr/bin/env python3
"""Put the Art Director's left toolbar icons V1 (art/toolbar-v1/TOOLBAR_V1.md) into the game. Repeatable: re-run whenever
art/toolbar-v1 changes, then bump the ?v= build id in index.html and commit index.html.
  tools/sync_toolbar_art.py [SRC]   (default SRC = /workspace/studio/briefs/aquarium/art/toolbar-v1)
- Each <name>.svg is INLINED inside its button's .ico span in index.html (TOOLBAR_V1.md note 1: no <symbol>/<use>, so
  the inner groups stay addressable), between <!--tb:<name>--> ... <!--/tb:<name>--> markers.
- food.svg (the approved Food button pot, note 2) keeps the Job 5 level logic: its ids are prefixed 'fb-' (a document-wide
  #body / #fill / #rim would be ambiguous), #fb-fill is wrapped in <g id="food-level"> clipped by #food-level-clip
  (rect #food-level-rect, set by main.js setFoodLevel: visible from y = -84 x level down to y = 0; hidden at level 0),
  and the root gets id="food-icon" data-art="toolbar-v1".
- NO button animations (Maksims 2026-09-29 01:36, overrides TOOLBAR_V1.md notes 3-5): toolbar.css is NOT shipped and the
  animation-only parts (.flakes on Food, .bubbles on Clean, .stroke on Decorate, all hidden at rest in the AD art) are
  removed from the inlined markup, so every button is the static rest art; pressed = only the existing blue selected border.
  The only dynamic part is the Food pot fill level."""
import pathlib, re, sys

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/studio/briefs/aquarium/art/toolbar-v1")
GAME = pathlib.Path(__file__).resolve().parent.parent
NAMES = ["hand", "food", "sponge", "net", "brush", "shop"]

def load(name):
    s = (SRC / f"{name}.svg").read_text().strip()
    if 'viewBox="0 0 120 120"' not in s or f'class="tb tb-{name}"' not in s:
        sys.exit(f"{name}.svg: expected viewBox 0 0 120 120 and class 'tb tb-{name}'")
    if "<use" in s or "<symbol" in s:
        sys.exit(f"{name}.svg: contains <use>/<symbol>")
    return s

ANIM_ONLY = [re.compile(r'<g class="flakes">.*?</g>\n?', re.S),                                   # Food: falling flakes
             re.compile(r'<g class="bubbles">(?:<g class="bub[^"]*">.*?</g>)*</g>\n?', re.S),    # Clean: popping bubbles
             re.compile(r'<path class="stroke[^"]*"[^>]*/>\n?')]                                  # Decorate: paint stroke
def strip_anim(s):
    for pat in ANIM_ONLY: s = pat.sub("", s)
    for part in ('class="flake', 'class="bub', 'class="stroke'):
        if part in s: sys.exit(f"animation-only part {part} left in the markup")
    return s

def food_markup(s):
    for i in ("body", "fill", "rim", "fill-clip", "fill-clip-path"):
        if f'id="{i}"' not in s: sys.exit(f"food.svg: no #{i}")
    for part in ('class="pot"',):
        if part not in s: sys.exit(f"food.svg: no {part}")
    ids = re.findall(r'\bid="([^"]+)"', s)
    for i in ids:
        s = s.replace(f'id="{i}"', f'id="fb-{i}"').replace(f"url(#{i})", f"url(#fb-{i})").replace(f'href="#{i}"', f'href="#fb-{i}"')
    # level clip (Job 5 logic): #fb-fill inside #food-level, hidden until main.js sets the level
    m = re.search(r'<g id="fb-fill".*?</g>(?=\s*<g id="fb-rim")', s, re.S)
    if not m: sys.exit("food.svg: #fill is not directly followed by #rim")
    s = s[:m.start()] + '<g id="food-level" clip-path="url(#food-level-clip)" style="display:none">' + m.group(0) + '</g>' + s[m.end():]
    lvl = '<clipPath id="food-level-clip" clipPathUnits="userSpaceOnUse"><rect id="food-level-rect" x="-60" y="0" width="120" height="0"/></clipPath>'
    s = s.replace("</defs>", lvl + "</defs>", 1)
    return s.replace("<svg ", '<svg id="food-icon" data-art="toolbar-v1" ', 1)

html_p = GAME / "index.html"
html = html_p.read_text()
for name in NAMES:
    svg = strip_anim(load(name))
    if name == "food": svg = food_markup(svg)
    pat = re.compile(r"<!--tb:%s-->.*?<!--/tb:%s-->" % (name, name), re.S)
    if not pat.search(html): sys.exit(f"index.html: no <!--tb:{name}--> marker")
    html = pat.sub(lambda _m: f"<!--tb:{name}-->{svg}<!--/tb:{name}-->", html, count=1)
ids = re.findall(r'\bid="([^"]+)"', html)
dup = sorted({i for i in ids if ids.count(i) > 1})
if dup: sys.exit(f"index.html: duplicate ids {dup}")
html_p.write_text(html)
print(f"synced toolbar V1 from {SRC}: {', '.join(n + '.svg' for n in NAMES)} inlined into index.html (static, no animation parts; toolbar.css not shipped)")
