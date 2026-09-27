"""Review screenshots (phone 390x844 @2x) for Art Director's DIRT_AND_FISH_GROWTH.md and the v2 rules UI.
Run (server on 8766): /workspace/tools/venv-aq/bin/python tests/art_shots.py
Writes screenshots/: dirt_stage1..5.png (adult neon mid-tank), dirt_stage5_midrub.png, dead_fish_panel.png,
dead_fish_stage5.png, fish_{guppy,neon,danio,platy}_L1-L4.png, tank_neon_L2_closeup.png, fish_all_L1-L4.png, tank_{guppy,neon}_L1-L4.png,
shop_locked.png, feeding_meter.png, dirty_feed.png, away_summary.png. Resets the save at the end.
"""
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get("AQ_URL", "http://127.0.0.1:8766/")
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshots")
SPECIES = ["guppy", "neon", "danio", "platy"]

# dirt up to stage n (spots spawn stage by stage), one adult neon parked mid-tank (tank level 3 for neon)
SETUP = """(n) => { const G = AQ.game, T = G.T; G.reset(); G.state.gold = 1000; G.state.speed = 1; G.state.tank.xp = 400;
  const f = G.buyFish('neon'); f.level = 4; f.state = 'ADULT'; f.sinceFed = 0; AQ.pinFish(f.id, 0.5, 0.45);
  for (let i = 0; i < n; i++) { G.state.dirt.t = T.dirt.stageAtSec[i] - 0.5; G.tick(1); }
  return G.state.dirt.spots.map((s) => ({ stage: s.stage, over: s.over })); }"""

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
    def shot(page, name, **kw):
        path = os.path.join(SHOTS, name); page.screenshot(path=path, **kw); out.append(path)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(BASE + "?debug=0"); page.wait_for_function("window.AQ && window.AQ.game")
        page.wait_for_timeout(300)
        # ---- dirt stages 1..5
        for n in range(1, 6):
            for _ in range(12):
                spots = page.evaluate(SETUP, n)
                if n < 3 or any(s["over"] for s in spots): break
            page.wait_for_timeout(1200)
            shot(page, f"dirt_stage{n}.png")
        # stage 5 mid-rub: half of every spot's grime gone, sponge over the glass
        page.evaluate("() => AQ.game.state.dirt.spots.forEach((s) => { s.grime = s.grime0 * 0.5; })")
        page.click('.tool[data-tool="sponge"]')
        box = page.locator("#tank").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.35, box["y"] + box["height"] * 0.35)
        page.wait_for_timeout(600)
        shot(page, "dirt_stage5_midrub.png")
        page.click('.tool[data-tool="hand"]')
        # ---- dead fish: rises to the waterline, panel with Remove (0 gold); also behind the stage 5 film
        page.evaluate("""() => { const G = AQ.game; G.reset(); G.state.speed = 1; G.state.gold = 200; G.state.tank.xp = 400;
          const a = G.buyFish('guppy'); a.level = 3; a.state = 'ADULT'; const n = G.buyFish('neon'); n.level = 3; n.state = 'GROWING'; n.hungerDone = true;
          a.state = 'ADULT_HUNGRY'; a.level = 4; a.deathLeft = 1; AQ.pinFish(n.id, 0.5, 0.55); G.tick(2); }""")
        page.wait_for_timeout(1800)
        page.evaluate("() => { AQ.game.state.gameTime += 25; }")  # skip the 20 s rise
        page.wait_for_timeout(800)
        dead = page.evaluate("AQ.game.state.fish.find((f) => f.state === 'DEAD').id")
        pos = page.evaluate(f"AQ.fishScreen({dead})")
        page.mouse.click(box["x"] + pos["x"], box["y"] + pos["y"]); page.wait_for_timeout(400)
        shot(page, "dead_fish_panel.png")
        page.keyboard.press("Escape"); page.click('[data-close="panel"]')
        page.evaluate("""() => { const G = AQ.game, T = G.T; for (let i = 0; i < 5; i++) { G.state.dirt.t = T.dirt.stageAtSec[i] - 0.5; G.tick(1); } }""")
        page.wait_for_timeout(1200)
        shot(page, "dead_fish_stage5.png")
        # ---- shop with locked species + tank level bar (spec example: Tank Lv 2 · 130 / 400 XP)
        page.evaluate("() => { const G = AQ.game; G.reset(); G.state.gold = 120; G.state.tank.xp = 130; G.buyFish('guppy'); }")
        page.click("#btn-shop"); page.wait_for_timeout(400)
        shot(page, "shop_locked.png")
        page.click('[data-close="shop"]')
        # ---- feeding meter: hungry L3 guppy (3 taps, 1 given) + waiting neon (2 taps)
        page.evaluate("""() => { const G = AQ.game; G.reset(); G.state.gold = 200; G.state.tank.xp = 400;
          const g = G.buyFish('guppy'); g.level = 3; g.state = 'HUNGRY'; g.hungerDone = true; g.progress = 7200; g.deathLeft = 50000; g.fed = 1;
          const n = G.buyFish('neon'); AQ.pinFish(g.id, 0.35, 0.4); AQ.pinFish(n.id, 0.65, 0.5); }""")
        page.click('.tool[data-tool="food"]'); page.wait_for_timeout(800)
        shot(page, "feeding_meter.png")
        # ---- dirty-feed: exactly one message, by the dirt bar
        page.evaluate("() => { const G = AQ.game; G.state.dirt.t = G.T.dirt.stageAtSec[0] - 0.5; G.tick(1); }")
        page.wait_for_timeout(300)
        page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5); page.wait_for_timeout(300)
        shot(page, "dirty_feed.png")
        page.click('.tool[data-tool="hand"]')
        # ---- fish sheets
        for sp in SPECIES:
            wh = page.evaluate(SHEET, [[sp], 1, 390, 205])
            shot(page, f"fish_{sp}_L1-L4.png", clip={"x": 0, "y": 0, "width": wh["W"], "height": wh["H"]})
        page.evaluate("document.getElementById('artsheet').remove()")
        big = b.new_context(viewport={"width": 1000, "height": 760}, device_scale_factor=2).new_page()
        big.goto(BASE + "?debug=0"); big.wait_for_function("window.AQ && window.AQ.game")
        wh = big.evaluate(SHEET, [SPECIES, 4, 250, 185])
        shot(big, "fish_all_L1-L4.png", clip={"x": 0, "y": 0, "width": wh["W"], "height": wh["H"]})
        big.evaluate("AQ.game.reset(); AQ.game.save()")
        # ---- in-tank: guppy / neon L1..L4 swimming (real game rendering), clean glass
        for sp in ["guppy", "neon"]:
            page.evaluate("""(sp) => { const G = AQ.game; G.reset(); G.state.speed = 1; G.state.gold = 1000; G.state.tank.xp = 400;
              [1,2,3,4].forEach((lv) => { const f = G.buyFish(sp); f.level = lv; f.state = lv === 4 ? 'ADULT' : 'GROWING'; f.hungerDone = true;
                f.x = [0.25, 0.7, 0.3, 0.68][lv - 1]; f.y = [0.25, 0.3, 0.55, 0.6][lv - 1]; }); }""", sp)
            page.wait_for_timeout(1200)
            shot(page, f"tank_{sp}_L1-L4.png")
            if sp == "neon":  # AD ruling check: the L2 line at real tank size (native pixels, no upscaling)
                ids = page.evaluate("AQ.game.state.fish.map((f) => f.id)")
                page.evaluate(f"AQ.pinFish({ids[1]}, 0.5, 0.4)"); page.wait_for_timeout(400)
                pos = page.evaluate(f"AQ.fishScreen({ids[1]})")
                shot(page, "tank_neon_L2_closeup.png", clip={"x": box["x"] + pos["x"] - 70, "y": box["y"] + pos["y"] - 35, "width": 140, "height": 70})
        # ---- away summary: real reload 49 h after the save (one fed guppy, one waiting guppy)
        page.evaluate("""() => { const G = AQ.game; G.reset(); G.state.speed = 1; G.state.gold = 100;
          const a = G.buyFish('guppy'); G.feedTap(a.x, a.y); G.buyFish('guppy'); G.save();
          G.save = () => {}; // keep this page's periodic/pagehide save from overwriting the edited timestamp
          const k = G.CFG.VISUAL.saveKey, d = JSON.parse(localStorage.getItem(k)); d.lastSeen -= 49 * 3600 * 1000; localStorage.setItem(k, JSON.stringify(d)); }""")
        page.goto(BASE + "?debug=0"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(1500)
        shot(page, "away_summary.png")
        page.evaluate("AQ.game.reset(); AQ.game.save()")
        b.close()
    print("\n".join(out))

if __name__ == "__main__":
    main()
