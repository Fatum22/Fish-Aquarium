import json, re, glob, os, sys
SRC = '/workspace/studio/briefs/aquarium/art/fish-v7'
ORDER = ["guppy","danio","neon","ram","platy","rasbora","dwarfgourami","swordtail","cherrybarb","angelfish","pearlgourami","clownloach","rainbowfish","discus"]
num = re.compile(r'-?\d+\.\d+')
def rp(d, nd=1):
    def f(m):
        v = round(float(m.group()), nd)
        s = ('%.*f' % (nd, v)).rstrip('0').rstrip('.')
        if s in ('-0', ''): s = '0'
        return s
    return num.sub(f, d)
def walk(o):
    if isinstance(o, dict):
        return {k: (rp(v) if k in ('d',) or (isinstance(v, str) and k in SHAPEKEYS) else walk(v)) for k, v in o.items()}
    if isinstance(o, list): return [walk(x) for x in o]
    if isinstance(o, float): return round(o, 3)
    return o
SHAPEKEYS = set()
out = {}
for id_ in ORDER:
    d = json.load(open(f'{SRC}/{id_}.json'))
    for st in d['stages']:
        st['shapes'] = {k: rp(v) for k, v in st['shapes'].items()}
        for l in st['layers']:
            if 'd' in l: l['d'] = rp(l['d'])
    out[id_] = walk(d)
js = "/* Aquarium V7 fish art data (Art Director NEW_FISH_V7.md), generated from studio/briefs/aquarium/art/fish-v7/<id>.json\n * by tools/build_fish_v7.py: path numbers rounded to 0.1 unit (adult = 100 units). Do not edit by hand. */\nwindow.FISH_V7 = " + json.dumps(out, separators=(',', ':')) + ";\n"
dst = sys.argv[1] if len(sys.argv) > 1 else 'fishdata.js'
open(dst, 'w').write(js)
print(dst, len(js))
