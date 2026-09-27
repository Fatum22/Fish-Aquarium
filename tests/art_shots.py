"""Review screenshots for Art Director's DIRT_AND_FISH_GROWTH.md (phone 390x844 @2x).
Run (server on 8766): /workspace/tools/venv-aq/bin/python tests/art_shots.py
Writes screenshots/dirt_stage1..5.png, dirt_stage_looks.png, fish_{guppy,neon,danio,platy}_L1-L4.png, fish_all_L1-L4.png, tank_{guppy,neon}_L1-L4.png.
"""
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get("AQ_URL", "http://127.0.0.1:8766/")
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshots")
SPECIES = ["guppy", "neon", "danio", "platy"]

SETUP = """(n) => { const G = AQ.game, T = G.T; G.reset(); G.state.gold = 1000; G.state.speed = 1;
  const f = G.buyFish('guppy'); f.level = 4; f.state = 'ADULT'; f.sinceFed = 0;
  for (let i = 0; i < n; i++) { G.state.dirt.points = T.dirt.stageAtPoints[i] + 0.1; G.tick(0.01); }
  return G.state.dirt.spots.map((s) => ({ stage: s.stage, over: s.over })); }"""

# draws a labelled sheet of fish on a water-coloured overlay canvas; returns nothing
SHEET = """([species, cols, cellW, cellH]) => {
  let c = document.getElementById('artsheet'); if (c) c.remove();
  const rows = cols === 4 ? species.length : 4, W = cols * cellW, H = rows * cellH + 10, dpr = 2;
  c = document.createElement('canvas'); c.id = 'artsheet'; c.width = W * dpr; c.height = H * dpr;
  c.style.cssText = `position:fixed;left:0;top:0;width:${W}px;height:${H}px;z-index:9999`;
  document.body.appendChild(c);
  const x = c.getContext('2d'); x.scale(dpr, dpr);
  const g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#3fc0e8'); g.addColorStop(1, '#0a4c78');
  x.fillStyle = g; x.fillRect(0, 0, W, H);
  const V = AQ.game.CFG.VISUAL, names = { guppy: 'Guppy', neon: 'Neon tetra', danio: 'Zebra danio', platy: 'Platy' };
  species.forEach((sp, r) => {
    for (let lv = 1; lv <= 4; lv++) {
      const col = cols === 4 ? lv - 1 : 0, row = cols === 4 ? r : lv - 1;
      const cx = col * cellW, cy = row * cellH;
      x.fillStyle = '#fff'; x.font = '700 13px sans-serif'; x.textAlign = 'left'; x.textBaseline = 'top';
      x.fillText(`${names[sp]} L${lv}`, cx + 8, cy + 6);
      const L = Math.min(cellW * 0.55, cellH * 1.2) * V.speciesSize[sp] * V.levelSizeScale[lv - 1];
      x.save(); x.translate(cx + cellW * 0.58, cy + cellH * 0.56); FishArt.drawFish(x, sp, L, 0.6, { level: lv }); x.restore();
    }
  });
  return { W, H };
}"""

def main():
    os.makedirs(SHOTS, exist_ok=True)
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(BASE + "?speed=1&debug=0"); page.wait_for_function("window.AQ && window.AQ.game")
        page.wait_for_timeout(300)
        # dirt stages 1..5 (spots accumulate stage by stage; stage 5 retried until at least one overlap)
        for n in range(1, 6):
            for _ in range(12):
                spots = page.evaluate(SETUP, n)
                if n < 3 or any(s["over"] for s in spots): break
            page.wait_for_timeout(1500)
            path = os.path.join(SHOTS, f"dirt_stage{n}.png"); page.screenshot(path=path); out.append(path)
            print(n, spots)
        # each stage look in isolation, same tank (one spot per stage, left->right, top->bottom) + two forced overlaps
        page.evaluate("""() => { const G = AQ.game; G.reset(); G.state.speed = 1; G.state.gold = 1000;
          const f = G.buyFish('guppy'); f.level = 4; f.state = 'ADULT';
          const V = G.CFG.VISUAL, T = G.T, pos = [[0.25,0.16],[0.72,0.17],[0.25,0.43],[0.72,0.45],[0.33,0.72],[0.66,0.72]];
          G.state.dirt.points = T.dirt.stageAtPoints[4] + 1; G.state.dirt.spawned = 6;
          G.state.dirt.spots = pos.map(([x, y], i) => { const st = [1,2,3,4,5,1][i]; const r = V.dirtStages[st-1].r;
            return { id: 900 + i, x, y, r: (r[0] + r[1]) / 2, stage: st, seed: 17 + i * 101, grime: 150, grime0: 150, over: null }; });
          // overlap demo at the bottom: stage 1 smudge crossed by stage 5 crust
          G.state.dirt.spots[5].x = 0.52; G.state.dirt.spots[5].y = 0.74; G.state.dirt.spots.unshift(G.state.dirt.spots.pop());
        }""")
        page.wait_for_timeout(1200)
        path = os.path.join(SHOTS, "dirt_stage_looks.png"); page.screenshot(path=path); out.append(path)
        # fish sheets
        for sp in SPECIES:
            wh = page.evaluate(SHEET, [[sp], 1, 390, 205])
            path = os.path.join(SHOTS, f"fish_{sp}_L1-L4.png"); page.screenshot(path=path, clip={"x": 0, "y": 0, "width": wh["W"], "height": wh["H"]}); out.append(path)
        page.evaluate("document.getElementById('artsheet').remove()")
        big = b.new_context(viewport={"width": 1000, "height": 760}, device_scale_factor=2).new_page()
        big.goto(BASE + "?speed=1&debug=0"); big.wait_for_function("window.AQ && window.AQ.game")
        wh = big.evaluate(SHEET, [SPECIES, 4, 250, 185])
        path = os.path.join(SHOTS, "fish_all_L1-L4.png"); big.screenshot(path=path, clip={"x": 0, "y": 0, "width": wh["W"], "height": wh["H"]}); out.append(path)
        # in-tank: guppy / neon L1..L4 swimming (real game rendering), clean glass
        for sp in ["guppy", "neon"]:
            page.evaluate("""(sp) => { const G = AQ.game; G.reset(); G.state.speed = 1; G.state.gold = 1000;
              [1,2,3,4].forEach((lv) => { const f = G.buyFish(sp); f.level = lv; f.state = lv === 4 ? 'ADULT' : 'GROWING';
                f.x = [0.25, 0.7, 0.3, 0.68][lv - 1]; f.y = [0.25, 0.3, 0.55, 0.6][lv - 1]; }); }""", sp)
            page.wait_for_timeout(1200)
            path = os.path.join(SHOTS, f"tank_{sp}_L1-L4.png"); page.screenshot(path=path); out.append(path)
        page.evaluate("AQ.game.reset(); AQ.game.save()")
        big.evaluate("AQ.game.reset(); AQ.game.save()")
        b.close()
    print("\n".join(out))

if __name__ == "__main__":
    main()
