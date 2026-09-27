"""Headless end-to-end check of the Aquarium prototype (Designer v4 numbers, Art Director landscape layout v4).

Run (dev server must be up on 8767):
  /workspace/tools/venv-aq/bin/python /workspace/aquarium/tests/verify.py            # 844x390 + 1180x820 + portrait
  AQ_VIEWS=844x390 /workspace/tools/venv-aq/bin/python /workspace/aquarium/tests/verify.py   # one size only
The whole suite runs once per landscape size (compact 844x390, large 1180x820); check names carry the size.
Then a portrait pass checks the rotate screen at 390x844 and 820x1180.
Timing rules are checked by stepping the game in the page (AQ.game.tick), so hours-long timers run in
milliseconds; UI checks use real mouse/touch input. Writes screenshots to ../screenshots/v4/<name>_<size>.png.
Resets the save at the end.
"""
import json, os, struct, sys, time, zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("AQ_URL", "http://127.0.0.1:8767/")
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "..", "screenshots", "v4")
# The v4 build is pinned to Designer v4 (design/v4_archive/tuning.json). v5.1 (tank levels 6-10, ten new species) lands after
# the v4 rebuild (bible change 19:48 item 4), so the live design/tuning.json is not compared yet.
TUNING = os.environ.get("AQ_TUNING", "/workspace/studio/briefs/aquarium/design/v4_archive/tuning.json")
os.makedirs(SHOTS, exist_ok=True)

results = []
VIEW = [""]  # current viewport label, prefixed to every check name
def png_rgb(data):
    """Minimal PNG decoder (8-bit RGB/RGBA, non-interlaced) -> (w, h, px(x, y) -> (r, g, b)). No PIL in the test venv."""
    pos, idat, w, h, ct = 8, b"", 0, 0, 6
    while pos < len(data):
        ln, = struct.unpack(">I", data[pos:pos + 4]); typ = data[pos + 4:pos + 8]; body = data[pos + 8:pos + 8 + ln]; pos += 12 + ln
        if typ == b"IHDR": w, h, _bd, ct = struct.unpack(">IIBB", body[:10])
        elif typ == b"IDAT": idat += body
    bpp = 4 if ct == 6 else 3; stride = w * bpp; raw = zlib.decompress(idat); rows, prev, i = [], bytearray(stride), 0
    for _y in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0; b = prev[x]; c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4:
                pp = a + b - c; pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line); prev = line
    return w, h, lambda x, y: tuple(rows[y][x * bpp:x * bpp + 3])


def check(name, cond, detail=""):
    name = f"[{VIEW[0]}] {name}" if VIEW[0] else name
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    return cond

# JS helpers injected into every evaluate that needs them
JS = """const G = AQ.game, T = G.T, H = 3600;
  const clean = () => { const d = G.state.dirt; d.t = 0; d.spots = []; d.spawned = 0; d.grime5 = 0; };
  const toStage = (n) => { clean(); for (let i = 0; i < n; i++) { G.state.dirt.t = T.dirt.stageAtSec[i] - 0.5; G.tick(1); } };
  const feedFull = (f) => { let r, n = 0; do { r = G.feedTap(f.x, f.y); n++; } while (r.ok && !r.full && n < 50); return n; };
  const rubAll = (frac) => { // rub every spot by frac of its starting grime (1 = clean); tank 400 x 560 px
    let res = null; for (const s of G.state.dirt.spots.slice()) { const len = s.grime0 * frac, dx = len / 400 / 2;
      const r = G.rub(s.x - dx, s.y, s.x + dx, s.y, 400, 560, 1); if (r.cleaned) res = r; } return res; };
  // fresh(): a new game with the new-tank extras removed (clean glass, first-clean reward already used), 20 gold, 50 food,
  // so a check can stage exactly what it tests. G.reset() alone = the real v4 new tank (0/0, dirt stage 3).
  const fresh = () => { G.reset(); clean(); G.state.firstCleanPending = false; G.state.gold = 20; G.state.food = 50; };
  const halfGrime = () => { for (const s of G.state.dirt.spots) s.grime = s.grime0 / 2; }; // exact half (rub segments also hit overlapping spots)
"""

def main(VW, VH):
    errors = []
    tj = json.load(open(TUNING))
    VIEW[0] = f"{VW}x{VH}"; LARGE = VH >= 600
    def shot(name): return os.path.join(SHOTS, f"{name}_{VIEW[0]}.png")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        def boot(q=""):
            page.goto(BASE + q); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(250)
        def ev(body, arg=None):
            return page.evaluate("(arg) => { " + JS + body + " }", arg)
        S = lambda: page.evaluate("JSON.parse(JSON.stringify(AQ.game.state))")
        stage = lambda: page.evaluate("AQ.game.dirtStage()")
        def box(): return page.locator("#tank").bounding_box()
        def tank_click(x, y):
            b = box(); page.mouse.click(b["x"] + x, b["y"] + y)
        def fish(fid): return next((f for f in S()["fish"] if f["id"] == fid), None)
        def tool(name): page.click(f'.tool[data-tool="{name}"]')
        def click_fish(fid, until="#panel"):
            for _ in range(6):
                pos = page.evaluate(f"AQ.fishScreen({fid})")
                if pos: tank_click(pos["x"], pos["y"])
                page.wait_for_timeout(120)
                if page.locator(until).is_visible(): return True
            return False
        def net_text(fid):  # Net tool on a fish -> confirm text (then Cancel)
            tool("net"); ok = click_fish(fid, "#confirm"); t = page.inner_text("#confirm-text") if ok else ""
            return t
        def clear_toasts(): page.evaluate("document.getElementById('toasts').innerHTML = ''")
        def rub_clean(timeout=40):
            tool("sponge"); b = box(); t0 = time.time()
            while stage() >= 1 and time.time() - t0 < timeout:
                for sp in page.evaluate("AQ.spotsScreen()"):
                    x, y, r = sp["x"], sp["y"], sp["r"]
                    page.mouse.move(b["x"] + x - r, b["y"] + y); page.mouse.down()
                    for _ in range(3):
                        page.mouse.move(b["x"] + x + r, b["y"] + y + 4, steps=6)
                        page.mouse.move(b["x"] + x - r, b["y"] + y - 4, steps=6)
                    page.mouse.up()
            return stage() == 0

        # ================================================================ A. rules / config / speed
        boot(); page.evaluate("AQ.game.reset(); AQ.game.save()"); boot()
        check("config.js TUNING == Designer tuning.json (verbatim)", page.evaluate("AQ.game.T") == tj)
        s = S()
        check("page opens at x1 (debugDefaultSpeed)", s["speed"] == 1 == tj["debugDefaultSpeed"], f"speed={s['speed']}")
        btns = page.locator("#speed-btns .dbg").all_inner_texts()
        check("debug speed buttons are exactly x1 x5 x10 x15 x20", btns == ["×1", "×5", "×10", "×15", "×20"] and tj["debugSpeeds"] == [1, 5, 10, 15, 20], str(btns))
        nt = page.evaluate("({ st: AQ.game.dirtStage(), spots: AQ.game.state.dirt.spots.map((s) => s.stage), next: AQ.game.dirtNextIn(), fc: AQ.game.state.firstCleanPending, lvl: AQ.game.tankInfo().level })")
        check("v4 new tank: empty, 0 gold / 0 food / 0 diamonds, dirt stage 3 (clock at 12 h, next stage in 12 h) with its spots, first-clean reward armed, tank Lv1",
              s["fish"] == [] and s["gold"] == tj["startGold"] == 0 and s["food"] == tj["startFood"] == 0 and s["diamonds"] == tj["startDiamonds"] == 0 and nt["st"] == 3
              and len(nt["spots"]) == tj["dirt"]["spots"][2] and 12 * 3600 - 60 < nt["next"] <= 12 * 3600 and nt["fc"] and nt["lvl"] == 1, json.dumps(nt))
        boot("?speed=3600")
        g0 = page.evaluate("AQ.game.state.gameTime"); page.wait_for_timeout(1000); g1 = page.evaluate("AQ.game.state.gameTime")
        check("hidden ?speed=3600 works (about 1 game hour per real second)", S()["speed"] == 3600 and 1800 < g1 - g0 < 7200, f"speed={S()['speed']} dGame={g1 - g0:.0f}s")
        boot("?speed=1")

        d = ev("""const out = {}; const at = T.dirt.stageAtSec;
          const run = (setup) => { fresh(); G.state.gold = 1000; G.state.tank.xp = 5000; setup(); const rows = []; let t = 0;
            for (let i = 0; i < at.length; i++) { G.tick(at[i] - 1 - t); const before = G.dirtStage(); G.tick(2); t = at[i] + 1;
              rows.push([before, G.dirtStage(), G.state.dirt.spots.length]); } return rows; };
          out.empty = run(() => {});
          out.living = run(() => { const f = G.buyFish('guppy'); feedFull(f); clean(); }); // (its meal moved the clock 5 min: reset that)
          out.dead = run(() => { const f = G.buyFish('guppy'); f.state = 'DEAD'; f.diedAt = 0; });
          out.waiting = run(() => { G.buyFish('platy'); });
          out.hours = at.map((s) => s / H); return out;""")
        exp = [[i, i + 1, tj["dirt"]["spots"][i]] for i in range(5)]
        check("dirt stages at 3/6/12/24/48 h with dirt.spots spots per stage (empty tank gets dirty too)", d["hours"] == [3, 6, 12, 24, 48] and d["empty"] == exp and tj["dirt"]["runsWithEmptyTank"] is True, json.dumps(d["empty"]))
        check("dirt timer ignores the fish: empty / living / dead / waiting tanks give identical stages", d["living"] == d["dead"] == d["waiting"] == d["empty"], json.dumps({k: d[k] for k in ("living", "dead", "waiting")}))

        c = ev("""const out = []; for (let n = 1; n <= 5; n++) { fresh(); G.state.gold = 50; toStage(n); const g0 = G.state.gold, x0 = G.state.tank.xp;
            const r = rubAll(1.01); out.push({ n, gold: G.state.gold - g0, xp: G.state.tank.xp - x0, cleaned: !!(r && r.cleaned), t: G.state.dirt.t, st: G.dirtStage() }); }
          fresh(); G.state.gold = 50; toStage(3); const g0 = G.state.gold; rubAll(0.5); const partial = G.state.gold - g0;
          return { out, partial };""")
        cg = tj["dirt"]["cleanGold"]
        check("full clean pays cleanGold by stage (2/3/4/5/6) + 5 XP and restarts the dirt clock (first clean already used)", cg == [2, 3, 4, 5, 6] and all(r["gold"] == cg[r["n"] - 1] and r["xp"] == 5 and r["cleaned"] and r["t"] == 0 and r["st"] == 0 for r in c["out"]), json.dumps(c["out"]))
        c2 = ev("""fresh(); G.state.gold = 50; toStage(3); const g0 = G.state.gold; rubAll(0.3); const partial = G.state.gold - g0, rs = G.state.dirt.rubStage;
          G.state.dirt.t = T.dirt.stageAtSec[3] - 0.5; G.tick(1); const midStage = G.dirtStage(), spots = G.state.dirt.spots.length;
          const r = rubAll(1.01); return { partial, rs, midStage, spots, gold: G.state.gold - g0, payStage: r && r.stage, stageNow: r && r.stageNow, rsAfter: G.state.dirt.rubStage };""")
        check("clean pays by the stage when the rub STARTED (start at 3, tank reaches 4 mid-rub -> pays cleanGold[3] = 4)",
              c2["partial"] == 0 and c2["rs"] == 3 and c2["midStage"] == 4 and c2["spots"] >= 1 and c2["gold"] == cg[2] == 4 and c2["payStage"] == 3 and c2["stageNow"] == 4 and c2["rsAfter"] == 0, json.dumps(c2))
        check("partial rubbing pays nothing", c["partial"] == 0)
        fc = ev("""G.reset(); G.tick(1); const g0 = G.state.gold, f0 = G.state.food, x0 = G.state.tank.xp, grant0 = G.state.starterGrantUsed;
          const r = rubAll(1.01); const first = { gold: G.state.gold - g0, food: G.state.food - f0, xp: G.state.tank.xp - x0, pending: G.state.firstCleanPending, t: G.state.dirt.t, grant0 };
          toStage(3); const g1 = G.state.gold, f1 = G.state.food; rubAll(1.01); return { first, second: { gold: G.state.gold - g1, food: G.state.food - f1 } };""")
        check("first clean of a new tank pays 20 gold + 10 food + 5 XP instead of the stage pay; no starter grant before it; the next clean pays the stage pay again",
              fc["first"] == {"gold": 20, "food": 10, "xp": 5, "pending": False, "t": 0, "grant0": False} and fc["second"] == {"gold": cg[2], "food": 0}
              and tj["newTank"]["firstCleanReward"] == {"gold": 20, "food": 10, "replacesStagePay": True}, json.dumps(fc))

        # ================================================================ B. feeding / growth / hunger / death
        f = ev("""const out = { meal: T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.portion(sp, lv))) };
          // growth: feed the moment it gets hungry -> adult after sum(growSec)
          fresh(); G.state.gold = 1000; let a = G.buyFish('guppy'); feedFull(a); let t = 0, hungerAt = null; const hung = [];
          const a0 = a; G.on((ty, d) => { if (ty === 'hungry' && d.fish === a0) hung.push([t + 1, a0.level, a0.progress === 0 ? 'start' : 'mid']); });
          while (a.level < 4 && t < 100000) { G.tick(1); t++; if (hungerAt === null && a.state === 'HUNGRY') hungerAt = t;
            if (a.state === 'HUNGRY') { clean(); feedFull(a); } }
          out.adultAt = t; out.firstHunger = hungerAt; out.hung = hung; out.adultState = a.state; out.adultDeath = a.deathLeft;
          // a new L1 fish that is never fed just waits: never hungry, never dies
          fresh(); const w = G.buyFish('guppy'); G.tick(24 * H); out.waiting = [w.state, w.deathLeft];
          // death timer by level (3a): a fish hungry at level L dies exactly deathSec[L-1] later (mid meal at L1-L3, adult hunger at L4)
          out.byLevel = [1, 2, 3, 4].map((lv) => { fresh(); G.state.tank.xp = 5000; const f = G.buyFish('guppy'); feedFull(f); f.level = lv;
            f.state = lv === 4 ? 'ADULT' : 'GROWING'; f.progress = 0; f.hungerDone = false; f.sinceFed = 0; let t = 0, h = null, d = null, dl = null;
            while (d === null && t < 20 * H) { G.tick(1); t++; if (h === null && G.needsFood(f)) { h = t; dl = f.deathLeft; } if (f.state === 'DEAD') d = t; }
            return { lv, hungryAt: h, deathLeftAtHunger: dl, diesAfter: d - h }; });
          // just levelled up: hungry for its L2 start meal with the L2 timer (7 h), not L1's 6 h
          fresh(); const u = G.buyFish('guppy'); feedFull(u); u.hungerDone = true; u.progress = G.growSec(G.SPECIES.guppy, 1) - 0.5; G.tick(1);
          const up = { level: u.level, state: u.state, deathLeft: u.deathLeft }; let tt = 0; while (u.state !== 'DEAD' && tt < 20 * H) { G.tick(1); tt++; } up.diesAfter = tt + 0.5;
          out.justUp = up;
          // hunger at half of L1, death exactly deathSec after hunger (fed once, never again)
          fresh(); G.state.gold = 1000; a = G.buyFish('guppy'); feedFull(a); t = 0; let h = null, dead = null;
          while (!dead && t < 200000) { G.tick(1); t++; if (h === null && a.state === 'HUNGRY') { h = t; out.progressAtHunger = a.progress; } if (a.state === 'DEAD') dead = t; }
          out.hungry = h; out.deathAfter = dead - h; out.deadState = a.state; out.deadStays = G.state.fish.includes(a);
          // meals: partial food moves nothing; a completed meal gives feed XP and moves the dirt clock +300 s
          fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; const p = G.buyFish('platy'); const t0 = G.state.dirt.t, x0 = G.state.tank.xp; const steps = [];
          for (let k = 0; k < 3; k++) { const r = G.feedTap(p.x, p.y); steps.push([r.full, G.state.dirt.t - t0, G.state.tank.xp - x0, p.fed, p.state]); }
          out.platyMeal = steps;
          // a meal that pushes the clock over a stage line still counts fully; only the next tap is blocked
          fresh(); const g2 = G.buyFish('guppy'); G.state.dirt.t = T.dirt.stageAtSec[0] - 100; const x1 = G.state.tank.xp;
          const rr = G.feedTap(g2.x, g2.y); G.state.gold = 20; G.buyFish('guppy'); const nx = G.feedTap(0.5, 0.5);
          out.cross = { full: rr.full, state: g2.state, xp: G.state.tank.xp - x1, stage: G.dirtStage(), next: nx.reason, spots: G.state.dirt.spots.length };
          return out;""")
        check("food per meal by species and level = mealFood (Guppy 1/1/1/2, Danio 1/2/2/3, Neon 2/3/3/4, Platy 3/5/6/7), 1 food per tap",
              f["meal"] == [s_["mealFood"] for s_ in tj["species"]] and f["meal"][0] == [1, 1, 1, 2] and f["meal"][3] == [3, 5, 6, 7] and tj["foodPerTap"] == 1, json.dumps(f["meal"]))
        gsum = sum(next(s for s in tj["species"] if s["id"] == "guppy")["growSec"])
        check("every fish timer is v3/20: Guppy grows 3 / 6 / 12 min and reaches adult in 21 min with prompt feeding",
              f["adultAt"] == gsum == 21 * 60 and next(s for s in tj["species"] if s["id"] == "guppy")["growSec"] == [180, 360, 720], f"adultAt={f['adultAt']} sum={gsum}")
        hung = f["hung"]
        check("two meals per level: hungry at 50% of each level and again right at every level-up (L2, L3, L4), 6 hungers on the way to adult",
              [h_[2] for h_ in hung] == ["mid", "start", "mid", "start", "mid", "start"] and [h_[1] for h_ in hung] == [1, 2, 2, 3, 3, 4] and hung[0][0] == 90 and hung[1][0] == 180
              and f["adultState"] == "ADULT_HUNGRY" and f["adultDeath"] == tj["deathSec"][3] and tj["hungerPoints"] == [0.0, 0.5], json.dumps(hung))
        check("hungry at 50% of the level (Guppy L1 at 1 m 30 s)", f["hungry"] == 90 and abs(f["progressAtHunger"] - 90) < 1e-6, f"hungry at {f['hungry']}s")
        check("death exactly deathSec[L1] (6 h) after an L1 fish gets hungry; the dead fish stays in the tank", f["deathAfter"] == tj["deathSec"][0] == 21600 and f["deadState"] == "DEAD" and f["deadStays"], f"deathAfter={f['deathAfter']}")
        bl = f["byLevel"]
        check("death timer by level (NUMBERS 3a): hungry at L1 / L2 / L3 / L4 -> dies 6 h / 7 h / 9 h / 10 h later (tuning deathSec, same for every species)",
              tj["deathSec"] == [21600, 25200, 32400, 36000] and [b_["deathLeftAtHunger"] for b_ in bl] == tj["deathSec"] and [b_["diesAfter"] for b_ in bl] == tj["deathSec"], json.dumps(bl))
        check("just levelled up to L2: hungry for the start meal with the L2 timer (7 h, not L1's 6 h) and dies 7 h later if not fed",
              f["justUp"]["level"] == 2 and f["justUp"]["state"] == "HUNGRY" and abs(f["justUp"]["deathLeft"] - tj["deathSec"][1]) <= 1 and abs(f["justUp"]["diesAfter"] - tj["deathSec"][1]) <= 1, json.dumps(f["justUp"]))
        check("a new L1 fish that is never fed just waits (24 h later: still WAITING, no death timer)", f["waiting"] == ["WAITING", None], str(f["waiting"]))
        pm = f["platyMeal"]
        check("Platy L1 meal = 3 food: taps 1-2 are partial (no XP, dirt clock unchanged); tap 3 completes it: +5 feed XP, dirt clock +300 s, growing",
              [x_[0] for x_ in pm] == [False, False, True] and [x_[1] for x_ in pm] == [0, 0, 300] and [x_[2] for x_ in pm] == [0, 0, 5] and pm[2][4] == "GROWING"
              and tj["dirt"]["mealAddsSec"] == 300, json.dumps(pm))
        check("a meal that pushes the dirt over a stage line still counts (XP, growing); the next tap is blocked as dirty",
              f["cross"] == {"full": True, "state": "GROWING", "xp": 1, "stage": 1, "next": "dirty", "spots": tj["dirt"]["spots"][0]}, json.dumps(f["cross"]))

        # real taps: 1 food per tap, fed meter, v3 feeding pays 0 and shows no gold float (Platy needs 2 taps at L1)
        pid = ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; const f = G.buyFish('platy'); AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(200); tool("food")
        pos = page.evaluate(f"AQ.fishScreen({pid})")
        page.evaluate("AQ.floats(true)"); s0 = S(); tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s1 = S()
        tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s2 = S()
        f1 = next(x for x in s1["fish"] if x["id"] == pid); f2 = next(x for x in s2["fish"] if x["id"] == pid)
        page.wait_for_timeout(900); fl = page.evaluate("AQ.floats(true)")
        tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s2 = S(); f2 = next(x for x in s2["fish"] if x["id"] == pid)
        check("real Food taps: 1 food per tap, Platy fed 1/3, 2/3, then full -> growing, 0 gold (feedGoldPerFish 0)",
              tj["feedGoldPerFish"] == 0 and s1["food"] == s0["food"] - 1 and f1["fed"] == 1 and f1["state"] == "WAITING" and s1["gold"] == s0["gold"]
              and s2["food"] == s0["food"] - 3 and f2["state"] == "GROWING" and s2["gold"] == s0["gold"],
              f"food {s0['food']}->{s1['food']}->{s2['food']} gold {s0['gold']}->{s2['gold']} state {f2['state']}")
        check("full feed shows no gold float at all (no '+0')", not any("gold" in t or "+0" in t for t in fl), str(fl))
        clear_toasts(); tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(150)
        check("tap with nobody hungry: 'Nobody's hungry', no food spent", S()["food"] == s2["food"] and "Nobody's hungry" in page.inner_text("#toasts"), page.inner_text("#toasts"))

        # v1 flake shower on every successful tap (NUMBERS.md 3.4), drifting toward the fed fish; blocked taps show none
        fid = ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; const f = G.buyFish('platy'); AQ.pinFish(f.id, 0.82, 0.55); return f.id;")
        page.wait_for_timeout(200); tool("food"); b_ = box()
        fl0 = page.evaluate("AQ.flakes()"); food0 = S()["food"]
        tank_click(b_["width"] * 0.18, b_["height"] * 0.25); page.wait_for_timeout(60)
        fl1 = page.evaluate("AQ.flakes()"); food1 = S()["food"]; pf = fish(fid)
        n_new = fl1["spawned"] - fl0["spawned"]
        check("feed tap: a shower of >= 8 flakes, still exactly 1 food and one meter step on the nearest hungry fish",
              n_new >= 8 and fl1["showers"] == fl0["showers"] + 1 and food1 == food0 - 1 and pf["fed"] == 1 and all(x["fishId"] == fid for x in fl1["live"]), f"flakes={n_new} food {food0}->{food1} fed={pf['fed']}")
        clear_toasts(); page.wait_for_timeout(350)
        page.screenshot(path=shot("feeding_flakes"))
        live = page.evaluate("AQ.flakes().live")
        sink = [(x["y"] - x["y0"]) / x["t"] for x in live if x["t"] > 0.2]
        fx0 = b_["width"] * 0.82
        eaten_at, trail = None, []
        for k_ in range(40):   # the fed fish rushes over and eats every flake of the tap (none left falling)
            page.wait_for_timeout(200); fl_ = page.evaluate("AQ.flakes()"); pos_ = page.evaluate(f"AQ.fishScreen({fid})"); trail.append(round(pos_["x"]))
            if not [x for x in fl_["live"] if x["fishId"] == fid]: eaten_at = (k_ + 1) * 0.2; break
        fl2 = page.evaluate("AQ.flakes()")
        check("flakes fall slowly (< 25 px/s) and the fed fish rushes to them and eats every one: none left, all counted eaten, within 8 s",
              sink and max(sink) < 25 and eaten_at is not None and fl2["eaten"] - fl0["eaten"] >= n_new and trail[-1] < fx0 - 40,
              f"sink px/s max={max(sink) if sink else None:.1f} eaten after {eaten_at}s; eaten {fl2['eaten'] - fl0['eaten']}/{n_new}; fish x {fx0:.0f} -> {trail[-3:]}")
        blocked = {}
        for why, setup in [("nobody hungry", "fresh(); feedFull(G.buyFish('guppy'));"),
                           ("out of food", "G.buyFish('guppy'); G.state.food = 0;"),
                           ("dirty", "G.state.food = 5; toStage(1);")]:
            ev(setup); page.wait_for_timeout(100); a0 = page.evaluate("AQ.flakes().spawned"); f0 = S()["food"]
            tank_click(b_["width"] * 0.5, b_["height"] * 0.3); page.wait_for_timeout(150)
            blocked[why] = (page.evaluate("AQ.flakes().spawned") - a0, S()["food"] - f0)
        check("blocked taps (nobody hungry, out of food, dirty) spawn zero flakes and spend nothing", all(v == (0, 0) for v in blocked.values()), json.dumps(blocked))
        ev("clean();")

        # hungry panel text
        gid = ev("fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); feedFull(f); G.tick(90); AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(2500); clear_toasts(); tool("hand"); click_fish(gid); page.wait_for_timeout(250)
        ht, gt, mt, wt = page.inner_text("#p-hunger"), page.inner_text("#p-growth"), page.inner_text("#p-meal"), page.inner_text("#p-worth")
        segs = page.evaluate("[...document.querySelectorAll('#p-mealbar i')].map((e) => e.classList.contains('on'))")
        check("fish info: 'Hungry! Growth paused · dies in 6h 00m', 'Meal 2 of 2 · needs 1 food' with a 1-segment bar, 'Worth 0 gold'; no tap counts",
              any(ht.startswith("Hungry! Growth paused · dies in " + t) for t in ("6h 00m", "5h 59m")) and "Growth paused" in gt and mt == "Meal 2 of 2 · needs 1 food"
              and segs == [False] and wt == "Worth 0 gold" and "tap" not in (ht + mt + gt).lower(), f"{ht} | {gt} | {mt} | {segs} | {wt}")
        page.screenshot(path=shot("panel_hungry"))
        page.keyboard.press("Escape")

        # ================================================================ C. tank XP / shop gating
        x = ev("""fresh(); G.state.gold = 1000; const a = G.buyFish('guppy'); feedFull(a); let n = 0;
          while (a.level < 2 && n++ < 10000) { G.tick(1); if (a.state === 'HUNGRY' && a.level < 2) { clean(); feedFull(a); } }
          const afterLvl = G.state.tank.xp, gu = T.species.find((s) => s.id === 'guppy');
          G.sell(a.id); const afterSell = G.state.tank.xp;
          const table = T.species.map((sp) => [2, 3, 4].map((lv) => G.xpFor('fishLevelUp', { sp, level: lv })));
          const sellXp = T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.xpFor('sell', { sp, level: lv }))), feedXp = T.species.map((sp) => G.xpFor('feed', { sp }));
          return { afterLvl, xp2: gu.levelUpXp[0], gold2: gu.levelUpGold[0], afterSell, table, sellXp, feedXp, retired: G.CFG.XP_SOURCE === undefined && G.CFG.XP_PRESETS === undefined,
            rule: T.tank.xp.fishLevelUp, lv: [0, 59, 60, 399, 400, 1200, 3000].map(G.tankLevelFor) };""")
        check("tank XP v4: 2 meals x feed XP 1 + Guppy L2 level-up 10 (pays 1 gold) = 12; selling it at L2 adds sellXp 10; tables = tuning (feed 1/2/3/5, sell up to 80/160/240/400)",
              x["rule"] == "species.levelUpXp" and x["afterLvl"] == 2 * 1 + x["xp2"] == 12 and x["gold2"] == 1 and x["afterSell"] == x["afterLvl"] + 10 and x["retired"]
              and x["table"] == [s_["levelUpXp"] for s_ in tj["species"]] and x["sellXp"] == [s_["sellXp"] for s_ in tj["species"]] and x["feedXp"] == [1, 2, 3, 5], json.dumps(x))
        # level-up floats: "+2 gold" and "+20 XP" for a Guppy reaching L3 (NUMBERS.md 1f)
        lf = ev("""fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); feedFull(f); f.level = 2; f.progress = G.growSec(G.SPECIES.guppy, 2) - 0.5;
          f.hungerDone = true; AQ.pinFish(f.id, 0.5, 0.5); AQ.floats(true); const g0 = G.state.gold, x0 = G.state.tank.xp; G.tick(1);
          return { gold: G.state.gold - g0, xp: G.state.tank.xp - x0, level: f.level };""")
        page.wait_for_timeout(100); fl = page.evaluate("AQ.floats(true)")
        check("level-up pays v3 gold and shows '+2 gold' and '+20 XP' floats (Guppy L3)", lf["gold"] == 2 and lf["xp"] == 20 and lf["level"] == 3 and "+2 gold" in fl and "+20 XP" in fl, f"{lf} {fl}")
        check("tank levels at 60 / 400 / 1200 / 3000 XP", x["lv"] == [1, 1, 2, 2, 3, 4, 5], str(x["lv"]))
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 55; G.state.speed = 1;")
        page.click("#btn-shop"); page.wait_for_timeout(250)
        lock = {sp: (page.locator(f'button[data-buy="{sp}"]').is_disabled(), page.locator(f'button[data-buy="{sp}"]').inner_text()) for sp in ["guppy", "danio", "neon", "platy"]}
        check("shop: locked species disabled with 'Tank level N' even with 1000 gold", not lock["guppy"][0] and all(lock[s][0] and f"Tank level {n}" in lock[s][1] for s, n in [("danio", 2), ("neon", 3), ("platy", 4)]), json.dumps(lock))
        check("buying a locked species is refused", ev("return G.canBuy('neon').locked === true && G.buyFish('neon') === null;"))
        page.click('[data-close="shop"]'); clear_toasts()
        ev("toStage(1); rubAll(1.01);")  # clean gives the last 5 XP -> tank level 2
        page.wait_for_timeout(200)
        tt = page.inner_text("#toasts")
        page.click("#btn-shop"); page.wait_for_timeout(250)
        check("tank level-up toast names the unlock; Danio becomes buyable", "Tank level 2" in tt and "Zebra Danio" in tt and not page.locator('button[data-buy="danio"]').is_disabled(), tt)
        page.click('[data-close="shop"]')
        # shop prices / "sells up to" match tuning.json (all unlocked)
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 5000; G.state.speed = 1;")
        clear_toasts(); page.click("#btn-shop"); page.wait_for_timeout(250)
        shop = {sp["id"]: (page.locator(f'button[data-buy="{sp["id"]}"] .price').inner_text(), page.locator(f'#shop-list .card:has(button[data-buy="{sp["id"]}"])').inner_text()) for sp in tj["species"]}
        check("shop prices 20/50/90/150 and 'sells up to' adult price match tuning.json",
              [int(shop[s_["id"]][0]) for s_ in tj["species"]] == [s_["price"] for s_ in tj["species"]] == [20, 50, 90, 150]
              and all(f'sells up to {s_["sell"][3]}g' in shop[s_["id"]][1] for s_ in tj["species"]), json.dumps({k: v[0] for k, v in shop.items()}))
        page.screenshot(path=shot("shop"))
        page.click('[data-close="shop"]')
        sp_tab = ev("return T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.sellPrice(sp, lv)));")
        lg_tab = ev("return T.species.map((sp) => [2, 3, 4].map((lv) => G.levelUpGold(sp, lv)));")
        check("sell prices at every level (Guppy 0/8/18/40 ...) and level-up gold (Guppy 1/2/4 ...) follow tuning.json v3",
              sp_tab == [s_["sell"] for s_ in tj["species"]] and sp_tab[0] == [0, 8, 18, 40] and lg_tab == [s_["levelUpGold"] for s_ in tj["species"]] and lg_tab[0] == [1, 2, 4], json.dumps([sp_tab, lg_tab]))
        btns, worth, panel_btns = [], [], []
        for lv in (1, 2, 3, 4):
            fid = ev(f"fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); f.level = {lv}; f.state = {lv} === 4 ? 'ADULT' : 'GROWING'; AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
            page.wait_for_timeout(150); tool("hand"); click_fish(fid); page.wait_for_timeout(150)
            worth.append(page.inner_text("#p-worth"))
            panel_btns.append(page.evaluate("[...document.querySelectorAll('#panel button')].filter((b) => !b.classList.contains('close') && b.offsetParent).length"))
            if lv == 4: page.screenshot(path=shot("fish_info"))
            page.keyboard.press("Escape")
            btns.append(net_text(fid))
            if lv == 3: page.screenshot(path=shot("net_sell_confirm"))
            page.click("#confirm-no"); page.wait_for_timeout(80)
        check("fish info has no sell button and shows 'Worth 0 / 8 / 18 / 40 gold' by level", panel_btns == [0, 0, 0, 0] and worth == ["Worth 0 gold", "Worth 8 gold", "Worth 18 gold", "Worth 40 gold"], json.dumps([worth, panel_btns]))
        check("Net confirms: 'Release Guppy? You get nothing.' / 'Sell Guppy (L2) for 8 gold and 10 XP?' / L3 18 + 25 XP / L4 40 + 80 XP",
              btns == ["Release Guppy? You get nothing.", "Sell Guppy (L2) for 8 gold and 10 XP?", "Sell Guppy (L3) for 18 gold and 25 XP?", "Sell Guppy (L4) for 40 gold and 80 XP?"], str(btns))
        tool("hand")

        # debug +50 XP button (NUMBERS.md 9.13): normal XP path, tank level-ups + unlock toasts, no gold, persists
        ev("fresh(); G.state.gold = 1000; G.state.speed = 1;"); page.wait_for_timeout(100)
        check("debug row has '+50 XP' next to the speed buttons, +100g and Reset save",
              page.locator("#debug #dbg-xp").inner_text() == "+50 XP" and page.locator("#debug #dbg-gold").is_visible() and page.locator("#debug #dbg-reset").is_visible())
        page.locator("#debug").screenshot(path=shot("debug_row"))
        seen, clicks, xp_trace = {}, 0, []
        for target, lvl, sp_name in [(60, 2, "Zebra Danio"), (400, 3, "Neon Tetra"), (1200, 4, "Platy")]:
            while page.evaluate("AQ.game.state.tank.xp") < target:
                clear_toasts(); page.click("#dbg-xp"); clicks += 1; page.wait_for_timeout(30)
            page.wait_for_timeout(120)
            seen[lvl] = (page.evaluate("AQ.game.tankInfo().level"), page.evaluate("AQ.game.state.tank.xp"), page.inner_text("#toasts"))
        g_after = S()["gold"]
        check("+50 XP x2 / x8 / x24 reaches tank level 2 / 3 / 4 at 100 / 400 / 1200 XP with the unlock toasts, gold unchanged",
              clicks == 24 and seen[2][:2] == (2, 100) and "Tank level 2! Zebra Danio unlocked" in seen[2][2] and seen[3][:2] == (3, 400) and "Tank level 3! Neon Tetra unlocked" in seen[3][2]
              and seen[4][:2] == (4, 1200) and "Tank level 4! Platy unlocked" in seen[4][2] and g_after == 1000, json.dumps({"clicks": clicks, "seen": seen, "gold": g_after}))
        page.click("#btn-shop"); page.wait_for_timeout(200)
        unl = {sp_["id"]: (page.locator(f'button[data-buy="{sp_["id"]}"]').is_disabled(), page.locator(f'button[data-buy="{sp_["id"]}"]').inner_text()) for sp_ in tj["species"]}
        check("at tank level 4 all four species are unlocked and buyable in the shop", all(not d_ and "Tank level" not in t_ for d_, t_ in unl.values()), json.dumps(unl))
        page.click('[data-close="shop"]')
        boot("?speed=1")
        check("debug XP persists after reload (normal save path)", page.evaluate("AQ.game.state.tank.xp") == 1200 and page.evaluate("AQ.game.tankInfo().level") == 4 and S()["gold"] == 1000)

        # ================================================================ D. offline catch-up (real reload) + dead fish
        ids = ev("""fresh(); G.state.speed = 1; G.state.gold = 100; const a = G.buyFish('guppy'); feedFull(a); const b = G.buyFish('guppy');
          G.save(); G.save = () => {}; // keep this page's periodic/pagehide save from overwriting the edited timestamp
          const k = G.CFG.VISUAL.saveKey, d = JSON.parse(localStorage.getItem(k)); d.lastSeen -= 49 * H * 1000; localStorage.setItem(k, JSON.stringify(d));
          return { a: a.id, b: b.id, t0: G.state.gameTime };""")
        boot(); page.wait_for_timeout(600)
        s = S(); a = fish(ids["a"]); b = fish(ids["b"])
        check("offline 49 h: dirt stage 5, fed guppy died at 1m30 + 6h (L1 timer) and stays DEAD, unfed one still waiting",
              stage() == 5 and a and a["state"] == "DEAD" and abs(a["diedAt"] - ids["t0"] - 21690) <= 5 and b["state"] == "WAITING",
              f"stage={stage()} a={a and a['state']} diedAt-t0={a and a['diedAt'] - ids['t0']:.0f} b={b and b['state']}")
        aw = page.locator("#away").is_visible(); at_ = page.inner_text("#away-time") if aw else ""; al = page.inner_text("#away-list") if aw else ""
        check("'While you were away' summary: 49h, Guppy died, 'Tank is at dirt stage 5'", aw and "49h 00m" in at_ and "Guppy died" in al and "Tank is at dirt stage 5" in al and "clean" not in al.lower(), f"{at_} | {al}")
        page.click("#away-ok")
        r = ev("""const t0 = G.state.gameTime; G.state.lastSeen = Date.now(); const back = G.resume(Date.now() - H * 1000); const d1 = G.state.gameTime - t0;
          const s = G.newState(); return { back, d1 };""")
        check("clock set backwards counts as 0 offline time", r["back"] is None and r["d1"] == 0, json.dumps(r))
        r = ev("""const snap = JSON.stringify(G.state); G.state.lastSeen = Date.now() - 30 * 24 * H * 1000; const t0 = G.state.gameTime;
          const res = G.resume(Date.now()); const d1 = G.state.gameTime - t0; G.load({ getItem: () => snap });
          return { sec: res.sec, d1, cap: G.CFG.OFFLINE_CAP_SEC };""")
        check("offline catch-up capped at 7 days", r["sec"] == r["d1"] == r["cap"] == 7 * 86400, json.dumps(r))

        # dead fish: top band, tappable at the top, panel, slot, feeding, remove
        page.wait_for_timeout(300)
        gm = page.evaluate("AQ.geom()")
        wy = lambda fy: (fy * gm["H"] - gm["surf"]) / gm["waterH"]   # depth below the surface, in water heights
        dy = wy(page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {ids['a']}).y"))
        check("dead fish floats in the dead-fish band (6-10% of the water height below the surface)", 0.055 <= dy <= 0.105, f"depth={dy:.3f}")
        page.keyboard.press("Escape"); tool("hand")
        opened = click_fish(ids["a"]); page.wait_for_timeout(200)
        lvl = page.inner_text("#p-level") if opened else ""
        check("tapping the dead fish at the top opens its info: 'Dead', no buttons (removal is done with the Net)", opened and lvl == "Dead" and page.locator("#p-dead").is_visible()
              and page.evaluate("[...document.querySelectorAll('#panel button')].filter((b) => !b.classList.contains('close') && b.offsetParent).length") == 0, lvl)
        page.keyboard.press("Escape")
        full = ev(f"""clean(); G.state.gold = 1000; for (let i = 0; i < 4; i++) G.buyFish('guppy');
          const n = G.state.fish.length, c = G.canBuy('guppy'); const dead = G.state.fish.find((f) => f.id === {ids['a']});
          const r = G.feedTap(dead.x, dead.y); return {{ n, ok: c.ok, reason: c.reason, fedId: r.ok ? r.fish.id : null, deadFed: dead.fed, living: G.living() }};""")
        check("dead fish takes a tank slot (6/6 incl. dead -> 'Tank full')", full["n"] == 6 and not full["ok"] and full["reason"] == "Tank full", json.dumps(full))
        check("dead fish isn't fed and doesn't block feeding (tap on it feeds a living fish)", full["fedId"] not in (None, ids["a"]) and full["deadFed"] == 0, json.dumps(full))
        page.click("#btn-shop"); page.wait_for_timeout(200)
        check("shop disables buying while the tank is full with a dead fish in it", page.locator('button[data-buy="guppy"]').is_disabled())
        page.click('[data-close="shop"]'); tool("hand")
        gold_b = S()["gold"]; rt = net_text(ids["a"]); page.click("#confirm-yes"); page.wait_for_timeout(200)
        check("Net on a dead fish asks first ('Remove the dead Guppy? You get nothing.'), then pays 0 and frees the slot",
              rt == "Remove the dead Guppy? You get nothing." and fish(ids["a"]) is None and S()["gold"] == gold_b and not page.locator("#confirm").is_visible() and ev("return G.canBuy('guppy').ok;"), rt)
        tool("hand")
        check("dead fish can't be sold", ev("const f = G.buyFish('guppy'); f.state = 'DEAD'; return G.sell(f.id) === null;"))

        # a fish dying now rises to the top over ~20 game-seconds
        did = ev("fresh(); G.state.gold = 100; const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, 0.5, 0.6); f.state = 'HUNGRY'; f.deathLeft = 0.5; G.tick(1); G.state.speed = 20; return f.id;")
        page.wait_for_timeout(300); y_mid = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y")
        page.wait_for_timeout(1700); y_top = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y")
        check("a fish that just died rises to the dead-fish band over ~20 game s", wy(y_mid) > 0.2 and 0.055 <= wy(y_top) <= 0.105, f"depth after ~6 game s {wy(y_mid):.2f}, after ~40 {wy(y_top):.3f}")
        sg = ev("""G.state.speed = 1; const g = G.state.gold; G.state.gold = 0; G.tick(1);
          return { gold: G.state.gold, used: G.state.starterGrantUsed, living: G.living(), n: G.state.fish.length };""")
        check("starter grant counts living fish only (dead fish in tank, 0 gold -> top-up to 20)", sg["gold"] == 20 and sg["used"] and sg["living"] == 0 and sg["n"] == 1, json.dumps(sg))
        ev("G.state.gold = 3; G.tick(1);"); page.wait_for_timeout(300)
        over = page.locator("#tankover").is_visible()
        page.click("#btn-newtank"); page.wait_for_timeout(300); s2 = S()
        check("2nd wipe-out (only a dead fish left) shows 'Your tank is empty'; Start new tank gives the v4 new tank (0/0, dirt stage 3, first-clean reward armed)",
              over and s2["gold"] == 0 and s2["food"] == 0 and not s2["fish"] and not s2["starterGrantUsed"] and s2["firstCleanPending"] and stage() == 3, json.dumps({"shown": over, "gold": s2["gold"], "food": s2["food"], "fish": len(s2["fish"])}))

        # ================================================================ E. UI: dirty feed, rub clean, sell/release, reload
        gid = ev("fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.5, 0.45); toStage(3); return f.id;")
        page.wait_for_timeout(2800); clear_toasts(); tool("food"); page.wait_for_timeout(250)  # let earlier toasts/floats expire
        def ui_state():
            return page.evaluate("""() => ({ toasts: [...document.getElementById('toasts').children].map((e) => ({ text: e.textContent, kind: e.className })),
              hint: document.getElementById('hint').textContent, floats: AQ.floats(true), flakes: AQ.flakes().spawned, food: AQ.game.state.food,
              flash: document.getElementById('dirt-win').classList.contains('flash'), pulse: AQ.pulse(),
              old: !!(document.getElementById('dirt-callout') || document.getElementById('dirt-arrow')) })""")
        pre = ui_state()
        check("dirty tank + Food selected, before tapping: no hint, no toast, no flash; the old callout and arrow are gone from the page",
              stage() == 3 and pre["hint"] == "" and pre["toasts"] == [] and not pre["flash"] and not pre["old"], json.dumps(pre))
        taps = []
        for k, wait_before in enumerate([0, 2800, 1000]):   # tap 2 after the toast expired, tap 3 while it is still up (restart)
            if wait_before: page.wait_for_timeout(wait_before)
            before = ui_state()
            tank_click(box()["width"] * (0.3 + 0.2 * k), box()["height"] * 0.35); page.wait_for_timeout(120)
            after = ui_state()
            taps.append({"toasts": after["toasts"], "count": after["pulse"]["count"] - before["pulse"]["count"], "flash": after["flash"], "pulse": after["pulse"]["p"],
                         "hint": after["hint"], "floats": after["floats"], "food": after["food"] - before["food"], "flakes": after["flakes"] - before["flakes"]})
            if k == 0:
                page.wait_for_timeout(230)   # ~0.35 s after the tap: spots at their most solid, dirt window red
                mid_p = page.evaluate("AQ.pulse()")
                # read the two red peaks (0.25 s and 0.75 s) by seeking the running CSS animation, then put it back
                bgs = page.evaluate("""(() => { const el = document.getElementById('dirt-win'), a = el.getAnimations()[0]; if (!a) return ['none', 'none'];
                    const t = a.currentTime, out = []; for (const ms of [250, 750]) { a.currentTime = ms; out.push(getComputedStyle(el).backgroundColor); } a.currentTime = t; return out; })()""")
                bg = bgs[0]
                page.screenshot(path=shot("dirty_feed_flash"))
                tb_ = page.evaluate("(() => { const t = document.querySelector('#toasts .toast').getBoundingClientRect(), k = document.getElementById('tank-wrap').getBoundingClientRect(); return { cx: (t.left + t.right) / 2 - k.left, top: t.top - k.top, W: k.width }; })()")
                page.wait_for_timeout(750)   # > 1.0 s after the tap: back to normal
                end_p = page.evaluate("AQ.pulse()"); bg_end = page.evaluate("getComputedStyle(document.getElementById('dirt-win')).backgroundColor")
        page.wait_for_timeout(2000); still = [t["text"] for t in ui_state()["toasts"]]   # 2.1 s after tap 3 = 3.1 s after tap 2 -> only up if tap 3 restarted it
        page.wait_for_timeout(700); gone = ui_state()["toasts"]
        check("each blocked feed tap shows 'Clean the tank first' as a red toast at the top middle (one line, restarted, never stacked or counted), ~2.5 s",
              all([t_["text"] for t_ in t["toasts"]] == ["Clean the tank first"] and "bad" in t["toasts"][0]["kind"] for t in taps) and still == ["Clean the tank first"] and gone == []
              and abs(tb_["cx"] - tb_["W"] / 2) < 3 and tb_["top"] < 0.3 * box()["height"], json.dumps({"taps": taps, "still": still, "gone": gone, "toast": tb_}))
        rise = [(q["alpha"] - q["base"]) for q in mid_p["spots"]]
        check("blocked tap: every spot pulses more solid (alpha -> min(a + 0.35, 0.85)) around 0.35 s and is back to normal after 1.0 s; restarts on each tap",
              all(t["count"] == 1 and t["pulse"] > 0 for t in taps) and rise and min(rise) > 0.25 and all(abs(q["alpha"] - q["base"]) < 1e-3 for q in end_p["spots"]) and end_p["p"] == 0
              and abs(page.evaluate("AQ.pulseAt(0.35)") - 1) < 1e-6 and page.evaluate("AQ.pulseAt(0.5)") == 1 and page.evaluate("AQ.pulseAt(1.0)") == 0,
              json.dumps({"mid": mid_p["spots"][:3], "end": end_p["spots"][:2]}))
        red_ = lambda c: [int(v) for v in c[c.index("(") + 1:c.index(")")].split(",")[:3]]
        check("blocked tap: the dirt window flashes red (#c43c3c at the peak) and returns to --panel after 1 s, no shake",
              all(t["flash"] for t in taps) and all(red_(c)[0] > 180 and red_(c)[1] < 80 and red_(c)[2] < 80 for c in bgs) and red_(bg_end) == [15, 45, 68]
              and page.evaluate("getComputedStyle(document.getElementById('dirt-win')).animationName") in ("dirtFlash", "none"), json.dumps({"peaks 0.25 s / 0.75 s": bgs, "end": bg_end}))
        check("blocked taps: no food spent, no flakes, no floats, no bottom hint", all(t["food"] == 0 and t["flakes"] == 0 and t["floats"] == [] and t["hint"] == "" for t in taps))
        gold_b, xp_b = S()["gold"], S()["tank"]["xp"]
        ok = rub_clean(); s = S()
        fl = page.evaluate("AQ.floats(true)")
        check("sponge mouse rub cleans stage 3: +4 gold, +5 XP, 'Sparkling! +4 gold' float", ok and s["gold"] == gold_b + 4 and s["tank"]["xp"] == xp_b + 5 and "Sparkling! +4 gold" in fl, f"gold {gold_b}->{s['gold']} xp {xp_b}->{s['tank']['xp']} {fl}")
        tool("hand"); page.wait_for_timeout(400)
        page.screenshot(path=shot("after_clean"))
        # L1 release and L2 sell with the Net (both confirmed)
        rt = net_text(gid)
        cb_ = page.evaluate("(() => { const b = document.querySelector('#confirm .modal-box').getBoundingClientRect(), k = document.getElementById('tank-wrap').getBoundingClientRect(), n = document.getElementById('confirm-no').getBoundingClientRect(), y = document.getElementById('confirm-yes').getBoundingClientRect(), pc = document.getElementById('confirm-portrait'); return { w: b.width, cx: (b.left + b.right) / 2 - (k.left + k.right) / 2, cy: (b.top + b.bottom) / 2 - (k.top + k.bottom) / 2, cancelLeft: n.right <= y.left, portrait: pc.offsetParent !== null, no: document.getElementById('confirm-no').textContent }; })()")
        page.screenshot(path=shot("release_confirm"))
        check("Net on an L1 fish: centred confirm (320 / 400 wide) with the fish portrait, 'Release Guppy? You get nothing.', Cancel left of Release",
              rt == "Release Guppy? You get nothing." and abs(cb_["w"] - (400 if LARGE else 320)) < 1 and abs(cb_["cx"]) < 2 and abs(cb_["cy"]) < 2 and cb_["cancelLeft"] and cb_["portrait"]
              and page.inner_text("#confirm-yes") == "Release" and cb_["no"] == "Cancel", json.dumps([rt, cb_]))
        gb = S()["gold"]; page.click("#confirm-yes"); page.wait_for_timeout(150)
        check("released L1 for 0 gold", S()["gold"] == gb and fish(gid) is None)
        sid = ev("G.state.gold = 100; const f = G.buyFish('guppy'); f.level = 2; f.state = 'GROWING'; AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(200); st = net_text(sid); gb = S()["gold"]; xb = S()["tank"]["xp"]
        page.click("#confirm-no"); page.wait_for_timeout(100); kept = fish(sid) is not None
        net_text(sid); page.click("#confirm-yes"); page.wait_for_timeout(150)
        l2 = next(s_ for s_ in tj["species"] if s_["id"] == "guppy")["sell"][1]
        check(f"Net sells an L2 Guppy only after confirming: Cancel keeps it, Sell pays {l2} gold + 10 XP", kept and st == f"Sell Guppy (L2) for {l2} gold and 10 XP?" and S()["gold"] == gb + l2 and S()["tank"]["xp"] == xb + 10 and fish(sid) is None, st)
        tool("hand")
        # full tank screenshot + reload keeps state
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; ['guppy','danio','neon','platy'].forEach((id) => { const f = G.buyFish(id); feedFull(f); });")
        tool("hand"); page.wait_for_timeout(2500)
        page.screenshot(path=shot("tank_with_fish"))
        check("fish stay inside the tank", all(0 < f_["x"] < 1 and 0 < f_["y"] < 1 for f_ in S()["fish"]))
        page.evaluate("AQ.game.save()"); before = S()
        boot("?speed=5"); after = S()
        check("reload keeps fish/gold/food/XP; ?speed=5 applied", len(after["fish"]) == 4 and after["gold"] == before["gold"] and after["food"] == before["food"] and after["tank"]["xp"] == before["tank"]["xp"] and after["speed"] == 5,
              f"fish {len(after['fish'])} gold {before['gold']}->{after['gold']} speed {after['speed']}")
        ev("fresh(); G.state.gold = 500; G.state.tank.xp = 1200; ['guppy','danio','neon','platy','guppy','danio'].forEach((id, i) => { const f = G.buyFish(id); f.level = [4,3,2,4,1,2][i]; f.state = f.level === 4 ? 'ADULT' : 'GROWING'; }); G.state.speed = 1;")
        page.wait_for_timeout(2500)
        page.screenshot(path=shot("tank_mixed_levels_staged"))

        # ================================================================ E2. Playtester pass 6 fixes (N1-N3, N6, D1)
        R = lambda sel: page.evaluate(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return {{ l: r.left, t: r.top, r: r.right, b: r.bottom }}; }})()")
        hit = lambda a, b: a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]
        # N2: toasts stay out of the dead-fish band (surface .. 10% of the water height below it)
        did = ev("fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, 0.3, 0.5); f.state = 'HUNGRY'; f.deathLeft = 0.5; G.tick(1); G.state.gameTime += 25; G.debugAddXp(60); return f.id;")
        page.wait_for_timeout(700)
        tk = R("#tank"); gm = page.evaluate("AQ.geom()"); band = {"l": tk["l"], "t": tk["t"], "r": tk["r"], "b": tk["t"] + gm["surf"] + 0.10 * gm["waterH"]}
        toasts = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => { const r = e.getBoundingClientRect(); return { text: e.textContent, l: r.left, t: r.top, r: r.right, b: r.bottom }; })")
        dy = (page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y") * gm["H"] - gm["surf"]) / gm["waterH"]
        page.screenshot(path=shot("dead_fish_with_toast"))
        check("N2: toasts ('Guppy died', tank level-up) never intersect the air gap + dead-fish band; the dead fish stays in its band (6-10% of water below the surface)",
              len(toasts) >= 2 and any("died" in t_["text"] for t_ in toasts) and any("Tank level 2" in t_["text"] for t_ in toasts) and not any(hit(t_, band) for t_ in toasts) and 0.055 <= dy <= 0.105,
              json.dumps({"band": band, "toasts": toasts, "deadY": round(dy, 3)}))
        # N3: only dead fish -> no hint; back once a living fish is there
        page.wait_for_timeout(2800)
        h_dead = page.inner_text("#hint").strip() if page.locator("#hint").is_visible() else ""
        page.screenshot(path=shot("only_dead_fish"))
        ev("const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.5, 0.5);"); page.wait_for_timeout(200); h_wait = page.inner_text("#hint")
        ev("const f = G.state.fish.find((x) => x.state === 'WAITING'); clean(); feedFull(f);"); page.wait_for_timeout(200); h_live = page.inner_text("#hint")
        check("N3: only dead fish -> hint empty; a living fish brings hints back ('Tap a fish to see its details' once fed)",
              h_dead == "" and h_wait.startswith("New fish!") and h_live == "Tap a fish to see its details", json.dumps([h_dead, h_wait, h_live]))
        # D1: Start new tank modal states exactly what resets, and the button does reset exactly that
        ev("fresh(); G.state.speed = 1; G.state.tank.xp = 1500; G.state.food = 3; G.state.starterGrantUsed = true; const f = G.buyFish('guppy') || null; G.state.gold = 3; if (f) { f.state = 'DEAD'; f.diedAt = G.state.gameTime - 30; } G.tick(1);")
        page.wait_for_timeout(400)
        line = page.inner_text("#newtank-reset") if page.locator("#tankover").is_visible() else ""
        page.screenshot(path=shot("start_new_tank_modal"))
        exp_line = "Everything resets: 0 gold, 0 food, 0 diamonds, no fish, tank level 1 (0 XP), Zebra Danio, Neon Tetra and Platy lock again, only the default decorations, and the tank starts dirty (stage 3). The first clean pays 20 gold and 10 food again."
        page.click("#btn-newtank"); page.wait_for_timeout(250)
        after = ev("return { gold: G.state.gold, food: G.state.food, diamonds: G.state.diamonds, fish: G.state.fish.length, xp: G.state.tank.xp, lvl: G.tankInfo().level, locked: ['danio', 'neon', 'platy'].map((id) => !!G.canBuy(id).locked), grant: G.state.starterGrantUsed, speed: G.state.speed, stage: G.dirtStage(), fc: G.state.firstCleanPending };")
        check("D1: 'Your tank is empty' modal has the v4 reset line, and Start new tank resets exactly that (0 gold, 0 food, 0 diamonds, no fish, TL1 / 0 XP, 3 species relocked, dirt stage 3, first clean armed)",
              line == exp_line and after == {"gold": 0, "food": 0, "diamonds": 0, "fish": 0, "xp": 0, "lvl": 1, "locked": [True, True, True], "grant": False, "speed": 1, "stage": 3, "fc": True}, json.dumps({"line": line, "after": after}))
        # N6: every float type stays fully inside the tank with >= 8 px margin, at every edge/corner, also while rising
        sz = page.evaluate("AQ.size()"); Wt, Ht = sz["W"], sz["H"]
        pts = [(2, 2), (Wt - 2, 2), (2, Ht - 2), (Wt - 2, Ht - 2), (Wt / 2, 2), (2, Ht / 2), (Wt - 2, Ht / 2), (Wt / 2, Ht - 2), (-40, -40), (Wt + 40, Ht + 40)]
        bad, n_boxes = [], 0
        page.wait_for_timeout(1900)  # earlier floats gone
        for kind in ("clean", "levelup", "feed"):
            for (px_, py_) in pts:
                page.evaluate(f"AQ.testFloat('{kind}', {px_}, {py_})")
            for wait in (80, 900):   # just spawned, and after rising ~25 px
                page.wait_for_timeout(wait)
                bxs = page.evaluate("AQ.floatBoxes()"); n_boxes += len(bxs)
                for q in bxs:
                    if not (q["x0"] >= 8 - 0.01 and q["y0"] >= 8 - 0.01 and q["x1"] <= Wt - 8 + 0.01 and q["y1"] <= Ht - 8 + 0.01): bad.append({"kind": kind, **q})
                if kind == "levelup":
                    grps = {}
                    for q in bxs: grps.setdefault(q["grp"], []).append(q)
                    for pair in grps.values():
                        if len(pair) == 2:
                            a_, b_ = pair
                            if a_["x0"] < b_["x1"] and b_["x0"] < a_["x1"] and a_["y0"] < b_["y1"] and b_["y0"] < a_["y1"]: bad.append({"overlap": pair})
                        else: bad.append({"pairSize": len(pair)})
            page.wait_for_timeout(1000)
        check("N6: clean / level-up (gold+XP pair) / feed floats spawned at every edge and corner stay >= 8 px inside the tank (measured text box), pair never overlaps",
              not bad and n_boxes >= 2 * len(pts) * 4, f"boxes checked={n_boxes} bad={json.dumps(bad[:3])}")
        # real clean finishing at the far right edge
        ev("fresh(); G.state.gold = 50; G.state.speed = 1; toStage(1); G.state.dirt.spots.forEach((s, i) => { s.x = 0.9; s.y = 0.3 + i * 0.25; });")
        page.wait_for_timeout(200); page.evaluate("AQ.floats(true)"); tool("sponge"); b_ = box()
        for _ in range(12):
            if stage() == 0: break
            for sp in page.evaluate("AQ.spotsScreen()"):
                page.mouse.move(b_["x"] + sp["x"] - sp["r"], b_["y"] + sp["y"]); page.mouse.down()
                for _k in range(3):
                    page.mouse.move(b_["x"] + b_["width"] + 30, b_["y"] + sp["y"] + 4, steps=6)
                    page.mouse.move(b_["x"] + sp["x"] - sp["r"], b_["y"] + sp["y"] - 4, steps=6)
                page.mouse.move(b_["x"] + b_["width"] - 3, b_["y"] + sp["y"], steps=4); page.mouse.up()
        page.wait_for_timeout(250)
        cb = [q for q in page.evaluate("AQ.floatBoxes()") if q["text"].startswith("Sparkling")]
        page.screenshot(path=shot("float_edge_clamp"))
        check("N6: a real clean finished at the far right edge: 'Sparkling! +2 gold' fully inside the tank (>= 8 px)",
              stage() == 0 and len(cb) == 1 and cb[0]["x1"] <= Wt - 8 + 0.01 and cb[0]["x0"] >= 8 and cb[0]["x1"] >= Wt - 8 - 25, json.dumps(cb))
        tool("hand")

        # ================================================================ E3. Playtester pass 7 polish (M2 multi level-up, N4); the M1 callout arrow is gone (v4)
        # M2: 4 Guppies level up in the same tick (3 bunched in the middle, 1 at the right wall): staggered float pairs never
        # overlap, all >= 8px inside the tank; identical toasts merge into one line with a count
        page.wait_for_timeout(1900); clear_toasts(); page.evaluate("AQ.floats(true)")
        ev("""fresh(); G.state.gold = 500; G.state.speed = 1;
              [[0.5, 0.45], [0.52, 0.46], [0.48, 0.44], [0.93, 0.3]].forEach(([x, y]) => { const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, x, y); });""")
        page.wait_for_timeout(300); clear_toasts()
        ev("G.state.fish.forEach((f) => { f.progress = G.growSec(G.SPECIES.guppy, f.level) - 0.5; f.hungerDone = true; }); G.tick(1);")
        m2, snaps = [], []
        for wait in (80, 250, 700, 1100):
            page.wait_for_timeout(wait)
            bxs = page.evaluate("AQ.floatBoxes()"); snaps.append(len(bxs))
            if wait == 250: page.screenshot(path=shot("multi_levelup"))
            for i_, a_ in enumerate(bxs):
                if not (a_["x0"] >= 8 - 0.01 and a_["y0"] >= 8 - 0.01 and a_["x1"] <= Wt - 8 + 0.01 and a_["y1"] <= Ht - 8 + 0.01): m2.append({"out": a_})
                for b_ in bxs[i_ + 1:]:
                    if a_["x0"] < b_["x1"] and b_["x0"] < a_["x1"] and a_["y0"] < b_["y1"] and b_["y0"] < a_["y1"]: m2.append({"overlap": [a_, b_]})
        tl = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        lv = [t_ for t_ in tl if "reached level 2" in t_]
        lvls = ev("return G.state.fish.map((f) => f.level);")
        print("   M2 toasts:", json.dumps(tl))
        check("M2: 4 simultaneous level-ups -> 8 float boxes, none overlapping, all >= 8px inside the tank (checked 4 times while rising)",
              lvls == [2, 2, 2, 2] and snaps[0] == 8 and not m2, json.dumps({"levels": lvls, "boxes": snaps, "bad": m2[:3]}))
        check("M2: identical level-up toasts merge into one line with a count: 'Guppy reached level 2! +1 gold ×4'",
              lv == ["Guppy reached level 2! +1 gold ×4"] and len(tl) == len(set(tl)), json.dumps(tl))
        # the merged toast restarts its timer, and a later identical toast joins it instead of stacking
        # (~2.1 s after the first four: still on screen)
        ev("const f = G.buyFish('guppy'); feedFull(f); f.progress = G.growSec(G.SPECIES.guppy, 1) - 0.5; f.hungerDone = true; AQ.pinFish(f.id, 0.3, 0.7); G.tick(1);"); page.wait_for_timeout(100)
        tl2 = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        check("M2: a 5th identical toast while the merged one is still up joins it ('×5'), no second line",
              [t_ for t_ in tl2 if "reached level 2" in t_] == ["Guppy reached level 2! +1 gold ×5"], json.dumps(tl2))

        # N4: Start new tank clears toasts still showing/fading (e.g. "Guppy died") before "New tank started"
        page.wait_for_timeout(2800); clear_toasts()
        ev("""fresh(); G.state.speed = 1; G.state.starterGrantUsed = true; const f = G.buyFish('guppy'); feedFull(f); G.state.gold = 3;
              f.state = 'HUNGRY'; f.deathLeft = 0.5; G.tick(1); G.state.gameTime += 25;""")
        page.wait_for_timeout(300)
        before_nt = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        over_nt = page.locator("#tankover").is_visible()
        page.click("#btn-newtank"); page.wait_for_timeout(60)
        now_nt = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        page.wait_for_timeout(900)
        later_nt = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        check("N4: Start new tank clears 'Guppy died' (and any other toast) first; only 'New tank started' shows",
              over_nt and any("Guppy died" in t_ for t_ in before_nt) and now_nt == ["New tank started"] and later_nt == ["New tank started"],
              json.dumps({"modal": over_nt, "before": before_nt, "after60ms": now_nt, "after1s": later_nt}))

        # debug row (AD v4 1): under the tank only, one line, 11px (Large 13px), clock right-aligned; Reset save on the same row
        page.wait_for_timeout(300)
        n5 = page.evaluate("""(() => { const r = (id) => document.getElementById(id).getBoundingClientRect(); const e = document.getElementById('dbg-reset');
            const rg = document.createRange(); rg.selectNodeContents(e); const lines = new Set([...rg.getClientRects()].map((q) => Math.round(q.top))).size;
            const x = r('dbg-reset'), xp = r('dbg-xp'), c = r('dbg-clock'), dbg = r('debug'), t = r('tank-wrap');
            return { textLines: lines, sameRow: Math.abs(x.top - xp.top) < 0.5, resetRight: x.right, clockRight: c.right, clockTop: c.top, dbgRight: dbg.right, dbgL: dbg.left, tankL: t.left, tankR: t.right,
                     clockOneLine: c.height < 20, fs: parseFloat(getComputedStyle(document.getElementById('debug')).fontSize), h: dbg.height, overflow: document.getElementById('debug').scrollWidth > document.getElementById('debug').clientWidth + 0.5 }; })()""")
        page.locator("#debug").screenshot(path=shot("debug_row"))
        check("debug row: one line under the tank only, 11px / 13px, h 24 / 32, Reset save on the button row, clock right-aligned, nothing clipped",
              n5["textLines"] == 1 and n5["sameRow"] and abs(n5["clockRight"] - n5["dbgRight"]) < 1 and n5["clockOneLine"] and n5["fs"] == (13 if LARGE else 11) and abs(n5["h"] - (32 if LARGE else 24)) < 0.5
              and abs(n5["dbgL"] - n5["tankL"]) < 0.5 and abs(n5["dbgRight"] - n5["tankR"]) < 0.5 and not n5["overflow"] and n5["resetRight"] < n5["clockRight"], json.dumps(n5))

        # ================================================================ L. landscape layout v4 (Art Director LANDSCAPE_LAYOUT_V4.md)
        boot("?speed=1"); ev("fresh(); G.state.food = 0; G.state.speed = 1;"); tool("hand"); page.wait_for_timeout(300)
        lay = page.evaluate("AQ.layout()")
        spec = {False: {"column": (8, 8, 68, 374), "hud": (84, 8, 752, 36), "tank": (84, 50, 752, 302), "debug": (84, 358, 752, 24)},
                True: {"column": (12, 12, 96, 796), "hud": (120, 12, 1048, 48), "tank": (120, 68, 1048, 700), "debug": (120, 776, 1048, 32)}}[LARGE]
        off = {k: max(abs(lay[k]["x"] - v[0]), abs(lay[k]["y"] - v[1]), abs(lay[k]["w"] - v[2]), abs(lay[k]["h"] - v[3])) for k, v in spec.items()}
        check("AD v4 1: tool column, top bar, tank and debug row match the spec boxes within 4px; nothing scrolls",
              max(off.values()) <= 4 and lay["scrollW"] <= VW and lay["scrollH"] <= VH, json.dumps({"off": off, "got": {k: lay[k] for k in spec}}))
        tl = lay["tools"]; bw, bh, ic, gap = (96, 88, 52, 8) if LARGE else (68, 54, 36, 4)
        check("AD v4 2: tools top-down Look, Food, Clean, Net, Decorate, Shop; buttons 68x54 / 96x88, icons 36 / 52 px, 6px extra gap above Shop, none overlapping the tank",
              [t["label"] for t in tl] == ["Look", "Food", "Clean", "Net", "Decorate", "Shop"] and all(abs(t["w"] - bw) < 0.5 and abs(t["h"] - bh) < 0.5 and abs(t["icon"]["w"] - ic) < 0.5 and abs(t["icon"]["h"] - ic) < 0.5 for t in tl)
              and all(abs(tl[i + 1]["y"] - tl[i]["y"] - bh - gap) < 0.5 for i in range(4)) and abs(tl[5]["y"] - tl[4]["y"] - bh - gap - 6) < 0.5
              and all(t["x"] + t["w"] <= lay["tank"]["x"] - 5 for t in tl), json.dumps([(t["label"], t["y"], t["w"], t["h"], t["icon"]["w"]) for t in tl]))
        sel = page.evaluate("""(() => { const cs = (el) => getComputedStyle(el); const on = document.querySelector('.tool[data-tool="hand"]'), off = document.querySelector('.tool[data-tool="food"]');
            return { onBg: cs(on).backgroundColor, onBorder: cs(on).borderTopColor, onBw: cs(on).borderTopWidth, onLbl: cs(on).color, offBg: cs(off).backgroundColor, offLbl: cs(off).color }; })()""")
        check("AD v4 2: selected tool = --panel2 fill, 2px --accent border, white label; idle = --panel fill, --muted label",
              sel == {"onBg": "rgb(20, 58, 87)", "onBorder": "rgb(55, 195, 255)", "onBw": "2px", "onLbl": "rgb(255, 255, 255)", "offBg": "rgb(15, 45, 68)", "offLbl": "rgb(156, 192, 216)"}, json.dumps(sel))
        def bottle():
            return page.evaluate("""(() => { const b = document.getElementById('food-badge'), cs = getComputedStyle(b), i = document.getElementById('food-icon');
              const br = b.getBoundingClientRect(), ir = i.getBoundingClientRect(), btn = b.closest('.tool').getBoundingClientRect();
              return { text: b.textContent, border: cs.borderTopColor, color: cs.color, fill: +i.dataset.fill, empty: !document.getElementById('food-empty').hasAttribute('hidden'),
                       partial: !document.getElementById('food-partial').hasAttribute('hidden'), clipH: +document.getElementById('food-clip-rect').getAttribute('height'),
                       overlapX: ir.right - br.left, h: br.height, top: br.top - ir.top, inside: br.right <= btn.right + 0.5 && br.left >= btn.left }; })()""")
        b0 = bottle()
        check("AD v4 2: at 0 food the badge reads 0 with --danger border and text, and the bottle is the empty i-food-empty (no orange body)",
              b0["text"] == "0" and b0["border"] == "rgb(255, 90, 90)" and b0["color"] == "rgb(255, 90, 90)" and b0["empty"] and not b0["partial"] and b0["fill"] == 0, json.dumps(b0))
        fills = {}
        for n in (1, 4, 5, 9, 10, 19, 20, 250, 1000):
            ev(f"G.state.food = {n};"); page.wait_for_timeout(60); q = bottle(); fills[n] = (q["fill"], q["text"], q["clipH"], q["border"])
        check("AD v4 2: bottle fill steps 1-4 quarter, 5-9 half, 10-19 three quarters, 20+ full (body clipped from the bottom); badge '999+' above 999, orange border when > 0",
              [fills[n][0] for n in (1, 4, 5, 9, 10, 19, 20, 250)] == [0.25, 0.25, 0.5, 0.5, 0.75, 0.75, 1, 1] and fills[1000][1] == "999+" and fills[250][1] == "250"
              and abs(fills[5][2] - 7.5) < 1e-6 and all(fills[n][3] == "rgb(255, 138, 61)" for n in (1, 250)), json.dumps(fills))
        check("AD v4 2: food badge at the icon's top-right, overlapping it by >= 6px, height 18 / 22, inside the button",
              b0["overlapX"] >= 5.5 and abs(b0["h"] - (22 if LARGE else 18)) < 0.6 and b0["top"] <= 0 and b0["inside"], json.dumps(b0))
        # top bar
        hud = page.evaluate("""(() => { const q = (s) => document.querySelector(s); const r = (s) => q(s).getBoundingClientRect();
            return { order: [...q('#hud').children].map((e) => e.id), food: !!q('#res-food'), gold: r('#res-gold'), gem: r('#res-gem'), lvl: r('#tanklvl'), dirt: r('#dirt-win'), hud: r('#hud'),
                     gems: q('#gems').textContent, label: q('#tank-label').textContent, xp: q('#tank-xp').textContent, pillFs: getComputedStyle(q('#res-gold')).fontSize, tab: getComputedStyle(q('#gold')).fontVariantNumeric }; })()""")
        check("AD v4 3: top bar = gold pill, diamond pill (no food pill; 0 diamonds), 'Tank Lv 1' block with '0 / 60', dirt window 240x36 / 320x48 right-aligned; pills 32 / 42 high",
              hud["order"] == ["res-gold", "res-gem", "tanklvl", "dirt-win"] and not hud["food"] and hud["gems"] == "0" and hud["label"] == "Tank Lv 1" and hud["xp"] == "0 / 60"
              and abs(hud["dirt"]["width"] - (320 if LARGE else 240)) < 0.5 and abs(hud["dirt"]["height"] - (48 if LARGE else 36)) < 0.5 and abs(hud["dirt"]["right"] - hud["hud"]["right"]) < 0.5
              and abs(hud["gold"]["height"] - (42 if LARGE else 32)) < 0.5 and hud["lvl"]["width"] >= 160 and hud["pillFs"] == ("20px" if LARGE else "16px") and "tabular-nums" in hud["tab"], json.dumps(hud))
        def dirt_txt():
            return page.evaluate("""(() => { const l = document.getElementById('dirt-label'), n = document.getElementById('dirt-next'), h = document.getElementById('hud');
              const w = document.getElementById('dirt-win'), a = l.getBoundingClientRect(), b = n.getBoundingClientRect();
              return { label: l.textContent, next: n.textContent, clip: l.scrollWidth > l.clientWidth + 0.5 || n.scrollWidth > n.clientWidth + 0.5 || a.right > b.left || b.right > w.getBoundingClientRect().right,
                       oneLine: Math.abs(a.top - b.top) < 1 && h.scrollHeight <= h.clientHeight + 0.5 }; })()""")
        dt = {}
        for key, js in [("clean", "clean(); G.state.dirt.t = T.dirt.stageAtSec[0] - (2 * H + 12 * 60) - 30;"), ("s4", "toStage(4); G.state.dirt.t = T.dirt.stageAtSec[3] + 30;"),
                        ("m42", "toStage(2); G.state.dirt.t = T.dirt.stageAtSec[2] - 42 * 60 - 10;"), ("lt1", "toStage(2); G.state.dirt.t = T.dirt.stageAtSec[2] - 30;"), ("max", "toStage(5);")]:
            ev(js); page.wait_for_timeout(80); dt[key] = dirt_txt()
        ev("toStage(4); G.state.dirt.t = T.dirt.stageAtSec[3] + 30;"); page.wait_for_timeout(80); page.locator("#hud").screenshot(path=shot("topbar_23h59m"))
        check("AD v4 3: dirt window 'Dirt: clean' / 'Stage 1 in 2h 12m', 'Dirt: stage 4 of 5' / 'Stage 5 in 23h 59m' (one line, no clipping), '42m', '<1m', 'Max dirt'",
              dt["clean"]["label"] == "Dirt: clean" and dt["clean"]["next"] == "Stage 1 in 2h 12m" and dt["s4"]["label"] == "Dirt: stage 4 of 5" and dt["s4"]["next"] == "Stage 5 in 23h 59m"
              and not dt["s4"]["clip"] and dt["s4"]["oneLine"] and dt["m42"]["next"] == "Stage 3 in 42m" and dt["lt1"]["next"] == "Stage 3 in <1m" and dt["max"]["next"] == "Max dirt"
              and dt["max"]["label"] == "Dirt: stage 5 of 5", json.dumps(dt))
        jm = ev("""clean(); G.state.dirt.t = 3600 - 30; G.state.food = 20; const f = G.buyFish('guppy'); return 0;""")
        page.wait_for_timeout(80); t_before = dirt_txt()["next"]
        ev("const f = G.state.fish[G.state.fish.length - 1]; feedFull(f);"); page.wait_for_timeout(80); t_after = dirt_txt()["next"]
        check("AD v4 3: the dirt timer jumps 5 minutes at once when a meal moves the clock", t_before == "Stage 1 in 2h 00m" and t_after == "Stage 1 in 1h 55m", f"{t_before} -> {t_after}")
        # tank drawing geometry + pixels
        ev("fresh(); G.state.speed = 1;"); page.wait_for_timeout(350)
        gm = page.evaluate("AQ.geom()"); tb = box()
        exp_surf = max(16, 0.07 * gm["H"])
        png = page.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); pw, ph, px = png_rgb(png); k_ = pw / tb["width"]
        P = lambda x, y: px(int(x * k_), int(y * k_))
        air = P(gm["W"] * 0.33, gm["surf"] * 0.45); water = P(gm["W"] * 0.33, gm["surf"] + 30)
        xr = gm["W"] - gm["inset"]; yl = (gm["surf"] + gm["sand"]) / 2
        line_px, beside = P(xr, yl), P(xr - 9, yl)
        surf_px = max((P(gm["W"] * 0.66, gm["surf"] + d) for d in (-1, 0, 1)), key=sum)
        check("AD v4 4: air gap = top 7% (min 16px: 21 / 49px) filled darker than the water; sand top at 86%; glass lines inset 3.5% of W",
              abs(gm["surf"] - exp_surf) < 0.01 and round(gm["surf"]) == (49 if LARGE else 21) and abs(gm["sand"] - min(0.86 * gm["H"], gm["H"] - 36)) < 0.01 and abs(gm["inset"] - 0.035 * gm["W"]) < 0.01
              and sum(air) < sum(water) - 150 and air[2] < 110, json.dumps({"geom": gm, "air": air, "water": water}))
        check("AD v4 4: water surface line is visible (lighter than the water under it)", sum(surf_px) > sum(water) + 40, json.dumps({"surface": surf_px, "water": water}))
        # square tank corners (Maksims 19:57, AD v4 4 updated 19:58): radius 0 on frame, canvas, water and sand
        rad = page.evaluate("['tank-wrap', 'tank'].map((id) => { const c = getComputedStyle(document.getElementById(id)); return [c.borderTopLeftRadius, c.borderTopRightRadius, c.borderBottomRightRadius, c.borderBottomLeftRadius]; })")
        dif = lambda p, q: sum(abs(u - v) for u, v in zip(p, q))
        Wt, Ht = gm["W"], gm["H"]
        corners = {"tl": dif(P(0.3, 0.3), P(4, 4)), "tr": dif(P(Wt - 0.7, 0.3), P(Wt - 4, 4)), "bl": dif(P(0.3, Ht - 0.7), P(3, Ht - 3)), "br": dif(P(Wt - 0.7, Ht - 0.7), P(Wt - 3, Ht - 3))}
        check("Maksims / AD v4 4: tank corners are SQUARE: border-radius 0 on the tank frame and canvas, and the very corner pixels are tank (air / sand), not frame",
              all(r == "0px" for rr in rad for r in rr) and all(v < 30 for v in corners.values()), json.dumps({"radius": rad, "cornerDiff": corners}))
        def glass_probe():
            gl = page.evaluate("AQ.glassLine()"); x = gl["x"]; xo = gm["inset"] if gl["side"] == "right" else Wt - gm["inset"]; inward = -1 if gl["side"] == "right" else 1
            top, top_b = P(x, 0.6), P(x + 9 * inward, 0.6)
            bot, bot_b = P(x, gm["sand"] - 1.2), P(x + 9 * inward, gm["sand"] - 1.2)
            below, below_b = P(x + 0.5 * inward, gm["sand"] + 3), P(x + 6 * inward, gm["sand"] + 3)
            oth = P(xo, yl); oth_n = [(a + b) / 2 for a, b in zip(P(xo - 5, yl), P(xo + 5, yl))]
            return gl, {"top": sum(top) - sum(top_b), "bottom": sum(bot) - sum(bot_b), "belowCorner": dif(below, below_b), "otherSide": sum(oth) - sum(oth_n)}
        gl, pr = glass_probe()
        check("AD v4 4: exactly ONE glass back line, on VISUAL.glassLineSide = 'right': it runs from the frame's inner top edge (y 0) straight down to the sand's back corner "
              "(the sand edge is exactly at the corner), visible at both ends, no overshoot into the sand, no line on the left",
              gl["side"] == "right" and abs(gl["x"] - (Wt - gm["inset"])) < 1e-6 and gl["y0"] == 0 and abs(gl["y1"] - gm["sand"]) < 1e-6 and abs(gl["cornerY"] - gm["sand"]) < 1e-6
              and pr["top"] > 20 and pr["bottom"] > 20 and pr["belowCorner"] < 15 and pr["otherSide"] < 20, json.dumps({"line": gl, "px": pr}))
        tbq = box()
        page.screenshot(path=shot("tank_corners_right"), clip={"x": tbq["x"] + tbq["width"] * 0.72, "y": tbq["y"] - 10, "width": tbq["width"] * 0.28 + 10, "height": tbq["height"] + 20})
        ev("window.AQUARIUM_CONFIG.VISUAL.glassLineSide = 'left';"); page.wait_for_timeout(150)
        png = page.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); pw, ph, px = png_rgb(png)
        gl2, pr2 = glass_probe()
        page.screenshot(path=shot("tank_glass_left_setting"))
        ev("window.AQUARIUM_CONFIG.VISUAL.glassLineSide = 'right';"); page.wait_for_timeout(150)
        check("AD v4 4: one setting flips it: glassLineSide = 'left' draws the single line at the left sand corner (frame top to corner) and none on the right",
              gl2["side"] == "left" and abs(gl2["x"] - gm["inset"]) < 1e-6 and gl2["y0"] == 0 and abs(gl2["cornerY"] - gm["sand"]) < 1e-6
              and pr2["top"] > 20 and pr2["bottom"] > 20 and pr2["belowCorner"] < 15 and pr2["otherSide"] < 20, json.dumps({"line": gl2, "px": pr2}))
        page.screenshot(path=shot("main_screen"))
        L4 = page.evaluate("AQ.fishLen('guppy', 4)"); L1n = page.evaluate("AQ.fishLen('neon', 1)")
        tgt = ev("fresh(); G.state.tank.xp = 5000; G.state.gold = 1000; const f = G.buyFish('neon'); AQ.pinFish(f.id, 0.5, 0.5); return f.id;")
        page.wait_for_timeout(200); c_ = page.evaluate(f"AQ.fishScreen({tgt})"); taps_ok = []
        for dx_, dy_ in ((21, 0), (-21, 0), (0, 21), (0, -21)):
            page.keyboard.press("Escape"); page.wait_for_timeout(60); tank_click(c_["x"] + dx_, c_["y"] + dy_); page.wait_for_timeout(120)
            taps_ok.append(page.locator("#panel").is_visible())
        page.keyboard.press("Escape")
        check("AD v4 4: fish length = min(W, waterH*0.8) * 0.30 * species * level (adult guppy ~0.82 x 67px compact); the smallest fish is tappable 21px off-centre in every direction (>= 44x44)",
              abs(L4 - min(gm["W"], gm["waterH"] * 0.8) * 0.30 * 0.82) < 0.01 and all(taps_ok), json.dumps({"L4guppy": L4, "L1neon": L1n, "taps": taps_ok}))
        ic_ = ev("fresh(); const f = G.buyFish('guppy'); feedFull(f); G.tick(90); AQ.pinFish(f.id, 0.5, 0.5); return f.id;"); page.wait_for_timeout(200)
        fi_ = page.evaluate(f"AQ.fishIcon({ic_})"); c2 = page.evaluate(f"AQ.fishScreen({ic_})")
        check("AD v4 5: hunger icon centred at y = -(body half-depth) - 12, x = +0.25 L toward the head (no feed meter, no selection ring)",
              abs(fi_["y"] - (c2["y"] - fi_["halfDepth"] - 12)) < 0.01 and abs(fi_["x"] - (c2["x"] + fi_["face"] * 0.25 * fi_["L"])) < 0.01, json.dumps([fi_, c2]))
        # stage 1 readability (AD v4 21): 3 spots, alpha 0.22, colour #7A8A4A, big enough to see
        ev("fresh(); toStage(1);"); page.wait_for_timeout(300)
        sp1 = page.evaluate("AQ.spotsScreen()"); gm = page.evaluate("AQ.geom()")
        png = page.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); pw, ph, px = png_rgb(png); k_ = pw / tb["width"]
        ev("clean();"); page.wait_for_timeout(250)
        png0 = page.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); _w0, _h0, px0 = png_rgb(png0)
        diffs = [sum(abs(a_ - b_) for a_, b_ in zip(px(int(q["x"] * k_), int(q["y"] * k_)), px0(int(q["x"] * k_), int(q["y"] * k_)))) for q in sp1]
        check("AD v4 21: stage 1 = 3 spots (dirt.spots[0]), radius 0.10-0.14 of the water height, each clearly visible against clean water (colour change > 40 at its centre)",
              len(sp1) == tj["dirt"]["spots"][0] == 3 and all(0.10 * gm["waterH"] - 0.01 <= q["r"] <= 0.14 * gm["waterH"] + 0.01 for q in sp1) and min(diffs) > 40, json.dumps({"r": [round(q["r"], 1) for q in sp1], "diff": diffs}))
        ev("toStage(1);"); page.wait_for_timeout(250); page.screenshot(path=shot("stage1_dirt")); ev("clean();")
        check("AD v4 6: sponge radius = 0.16 x water height clamped 40-72px", abs(gm["spongeR"] - max(40, min(72, 0.16 * gm["waterH"]))) < 0.01, str(gm["spongeR"]))
        # shop: centred panel, tabs, close pill, food packs, decorations
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 5000; G.state.speed = 1;"); page.wait_for_timeout(100)
        page.click("#btn-shop"); page.wait_for_timeout(300)
        sh = page.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const k = r('#tank-wrap'), s = r('#shop'), c = r('#shop-close');
            const cols = getComputedStyle(document.getElementById('shop-list')).gridTemplateColumns.split(' ').length;
            return { w: s.width, h: s.height, cx: (s.left + s.right) / 2 - (k.left + k.right) / 2, top: s.top - k.top, tankW: k.width, tankH: k.height, closeW: c.width, closeH: c.height,
                     closeCx: (c.left + c.right) / 2 - (s.left + s.right) / 2, closeBottom: s.bottom - parseFloat(getComputedStyle(document.getElementById('shop')).borderBottomWidth) - c.bottom, cols, tabs: [...document.querySelectorAll('#shop .tab')].map((t) => t.textContent),
                     title: document.querySelector('#shop h2').textContent, xp: /XP|Tank Lv/.test(document.getElementById('shop').innerText), closeText: document.getElementById('shop-close').textContent,
                     pad: parseFloat(getComputedStyle(document.getElementById('shop-scroll')).paddingBottom) }; })()""")
        check("AD v4 8 / bible 7-8: shop = centred panel min(680, tankW-32) x tankH-16, header 'Shop' + tabs Fish / Food / Decorations, no tank level / XP, 4 / 5 columns",
              abs(sh["w"] - min(680, sh["tankW"] - 32)) < 1 and abs(sh["h"] - (sh["tankH"] - 16)) < 1 and abs(sh["cx"]) < 1 and abs(sh["top"] - 8) < 1 and sh["title"] == "Shop"
              and sh["tabs"] == ["Fish", "Food", "Decorations"] and not sh["xp"] and sh["cols"] == (5 if LARGE else 4), json.dumps(sh))
        page.evaluate("document.getElementById('shop-scroll').scrollTop = 1e6"); page.wait_for_timeout(150)
        vis = page.evaluate("(() => { const c = document.getElementById('shop-close').getBoundingClientRect(), s = document.getElementById('shop').getBoundingClientRect(); const e = document.elementFromPoint((c.left + c.right) / 2, (c.top + c.bottom) / 2); return { onTop: e && e.id === 'shop-close', inside: c.bottom <= s.bottom && c.top >= s.top }; })()")
        page.screenshot(path=shot("shop_scrolled"))
        check("bible 7 / AD v4 8: 'Close' pill fixed at the shop's bottom middle 8px up, 120x36 / 160x44, still on top after scrolling to the end; grid has 52 / 60px bottom padding",
              sh["closeText"] == "Close" and abs(sh["closeW"] - (160 if LARGE else 120)) < 0.5 and abs(sh["closeH"] - (44 if LARGE else 36)) < 0.5 and abs(sh["closeCx"]) < 1 and abs(sh["closeBottom"] - 8) < 1
              and vis["onTop"] and vis["inside"] and sh["pad"] == (60 if LARGE else 52), json.dumps([sh, vis]))
        page.click("#shop-close"); page.wait_for_timeout(150)
        closed = not page.locator("#shop").is_visible()
        page.click("#btn-shop"); page.wait_for_timeout(200); page.click('#shop .tab[data-tab="food"]'); page.wait_for_timeout(150)
        packs = page.evaluate("[...document.querySelectorAll('#shop-food .card')].map((c) => [c.querySelector('.n').textContent, c.querySelector('.price').textContent])")
        g0, f0 = S()["gold"], S()["food"]; page.click('#shop-food button[data-food="0"]'); page.wait_for_timeout(100); g1, f1 = S()["gold"], S()["food"]
        page.click('#shop-food button[data-food="1"]'); page.wait_for_timeout(100); g2, f2 = S()["gold"], S()["food"]
        page.screenshot(path=shot("shop_food"))
        check("bible 9: Food tab sells 10 food for 5 gold and 50 food for 25 gold; the Close pill closes the shop",
              closed and packs == [["10 food", "5"], ["50 food", "25"]] and (g0 - g1, f1 - f0, g1 - g2, f2 - f1) == (5, 10, 25, 50), json.dumps([packs, g0, g1, g2, f0, f1, f2]))
        page.click('#shop .tab[data-tab="decor"]'); page.wait_for_timeout(150)
        dec = page.evaluate("[...document.querySelectorAll('#shop-decor .card')].map((c) => [c.querySelector('.n').textContent, c.querySelector('.price').textContent])")
        page.screenshot(path=shot("shop_decorations"))
        # decorations: defaults, buying opens edit mode on the new one
        d0 = page.evaluate("AQ.decorScreen()")
        check("bible 24 / AD v4 7: default tank = leaves at x 0.16 / 0.24 / 0.82 (colours 25 / 55 / 40) and a stone at 0.60 (colour 50), all 1.0x, inside the glass lines",
              [(q["type"], q["x"], q["color"], q["sh"], q["sw"]) for q in d0] == [("leaf", 0.16, 25, 1, 1), ("leaf", 0.24, 55, 1, 1), ("leaf", 0.82, 40, 1, 1), ("stone", 0.6, 50, 1, 1)]
              and all(q["x0"] >= gm["inset"] and q["x1"] <= gm["W"] - gm["inset"] for q in d0), json.dumps([(q["type"], q["x"], round(q["x0"]), round(q["x1"])) for q in d0]))
        page.click('#shop-decor button[data-buydecor="leaf"]'); page.wait_for_timeout(250)
        ed = page.evaluate("AQ.edit()"); dn = page.evaluate("AQ.decorScreen()")[-1]
        toasts_ = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        check("bible 25 / 27: Decorations tab offers Leaf and Stone for free; buying places it at the floor centre, opens edit mode, selects it and opens its menu",
              dec == [["Leaf", "Free"], ["Stone", "Free"]] and not page.locator("#shop").is_visible() and ed["editing"] and ed["selDecor"] == dn["id"] and ed["menu"] and abs(dn["x"] - 0.5) < 1e-9
              and "Tap a decoration to change it" in toasts_ and page.locator('.tool[data-tool="brush"]').get_attribute("aria-pressed") == "true", json.dumps([dec, ed, dn["x"], toasts_]))
        page.screenshot(path=shot("edit_mode_menu"))
        mr = ed["menu"]; tk_ = ed["tank"]; dnb = ed["done"]
        check("AD v4 7: side menu 296x248 / 392x330 docked 8px from the tank top and side; Done button 72x32 / 96x40 in a top corner 8px in, not covered by the menu",
              abs(mr["w"] - (392 if LARGE else 296)) < 0.5 and abs(mr["h"] - (330 if LARGE else 248)) < 0.5 and abs(mr["y"] - tk_["y"] - 8) < 0.5
              and (abs(mr["x"] - tk_["x"] - 8) < 0.5 or abs(tk_["x"] + tk_["w"] - mr["x"] - mr["w"] - 8) < 0.5) and dnb and abs(dnb["w"] - (96 if LARGE else 72)) < 0.5 and abs(dnb["h"] - (40 if LARGE else 32)) < 0.5
              and abs(dnb["y"] - tk_["y"] - 8) < 0.5 and (dnb["x"] + dnb["w"] <= mr["x"] or dnb["x"] >= mr["x"] + mr["w"]), json.dumps([mr, dnb, tk_]))
        # the menu never covers the decoration it edits: every decoration, at 1.0x and at 2.0 x 2.0
        cover = []
        for scale in (1.0, 2.0):
            for q in page.evaluate("AQ.decorScreen()"):
                ev(f"const d = G.state.decor.find((x) => x.id === '{q['id']}'); d.sh = {scale}; d.sw = {scale}; AQ.selectDecor(d.id);"); page.wait_for_timeout(40)
                e_ = page.evaluate("AQ.edit()"); g_ = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == q["id"]); m_ = e_["menu"]
                mx0, my0 = m_["x"] - e_["tank"]["x"], m_["y"] - e_["tank"]["y"]
                if not (g_["x1"] <= mx0 or g_["x0"] >= mx0 + m_["w"] or g_["y1"] <= my0 or g_["y0"] >= my0 + m_["h"]): cover.append([q["id"], scale])
        ev("G.state.decor.forEach((d) => { d.sh = 1; d.sw = 1; });")
        check("AD v4 7: the side menu docks away from the decoration (centre x > 50% -> left) and never covers it (all decorations at 1.0x and 2.0x)", not cover, json.dumps(cover))
        # move / size / colour / sell
        did_ = dn["id"]; ev(f"AQ.selectDecor('{did_}');"); page.wait_for_timeout(60)
        x_a = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["bx"]
        page.click('#deco-menu [data-move="right"]'); page.wait_for_timeout(60)
        x_b = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["bx"]
        rb = page.locator('#deco-menu [data-move="left"]').bounding_box()
        page.mouse.move(rb["x"] + rb["width"] / 2, rb["y"] + rb["height"] / 2); page.mouse.down(); page.wait_for_timeout(700); page.mouse.up(); page.wait_for_timeout(60)
        x_c = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["bx"]
        steps_held = round((x_b - x_c) / 8)
        check("AD v4 7: a Move tap moves 8px; holding repeats every 80ms after 300ms (0.7 s hold = about 6 steps)", abs(x_b - x_a - 8) < 0.01 and 4 <= steps_held <= 7, f"tap {x_b - x_a:.2f}px, held {steps_held} steps")
        for _ in range(10): page.click('#deco-menu [data-size="taller"]')
        for _ in range(5): page.click('#deco-menu [data-size="narrower"]')
        page.wait_for_timeout(80)
        szs = page.evaluate(f"(() => {{ const d = AQ.game.state.decor.find((x) => x.id === '{did_}'); return {{ sh: d.sh, sw: d.sw, label: document.getElementById('dm-scale').textContent,"
                            " capT: document.querySelector('[data-size=\"taller\"]').classList.contains('capped'), op: getComputedStyle(document.querySelector('[data-size=\"taller\"]')).opacity,"
                            " capN: document.querySelector('[data-size=\"narrower\"]').classList.contains('capped'), capS: document.querySelector('[data-size=\"shorter\"]').classList.contains('capped') }; })()")
        lg_ = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)
        check("v4 7 sizes: 0.1x per tap, capped at 2.0x tall / 0.5x narrow (the capped button drops to 40%), label 'H 2.0x  W 0.5x'; the leaf's top stays >= 4% of the water below the surface",
              szs["sh"] == 2.0 and szs["sw"] == 0.5 and szs["label"] == "H 2.0x  W 0.5x" and szs["capT"] and szs["capN"] and not szs["capS"] and szs["op"] == "0.4"
              and lg_["y0"] >= gm["surf"] + 0.04 * gm["waterH"] - 0.01, json.dumps([szs, lg_["y0"]]))
        page.evaluate("(() => { const c = document.getElementById('dm-color'); c.value = 80; c.dispatchEvent(new Event('input', { bubbles: true })); c.dispatchEvent(new Event('change', { bubbles: true })); })()")
        page.wait_for_timeout(60)
        col = page.evaluate(f"(() => {{ const c = document.getElementById('dm-color'); return {{ color: AQ.game.state.decor.find((x) => x.id === '{did_}').color, track: c.style.getPropertyValue('--track'), thumb: c.style.getPropertyValue('--thumb') }}; }})()")
        check("AD v4 7: colour slider 0-100 updates the decoration live; track = the leaf gradient light hsl(98,68%,65%) -> dark hsl(135,50%,23%), thumb = current colour",
              col["color"] == 80 and "hsl(98.0,68.0%,65.0%)" in col["track"] and "hsl(135.0,50.0%,23.0%)" in col["track"] and col["thumb"].startswith("hsl("), json.dumps(col))
        page.click("#dm-sell"); page.wait_for_timeout(100)
        sell_t = page.inner_text("#confirm-text"); sell_btn = page.inner_text("#dm-sell") if page.locator("#dm-sell").is_visible() else ""
        n_before = len(S()["decor"]); gd = S()["gold"]; page.click("#confirm-yes"); page.wait_for_timeout(100)
        check("AD v4 7: 'Sell · refund 0 gold' asks 'Sell this leaf? You get 0 gold back.', then removes it (refunds the 0 paid)",
              sell_t == "Sell this leaf? You get 0 gold back." and sell_btn == "Sell · refund 0 gold" and len(S()["decor"]) == n_before - 1 and S()["gold"] == gd and not page.locator("#deco-menu").is_visible(), json.dumps([sell_t, sell_btn]))
        # edit mode: fish can't be tapped; Done exits; another tool exits
        fe = ev("const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.45, 0.4); return f.id;"); page.wait_for_timeout(150)
        pos_ = page.evaluate(f"AQ.fishScreen({fe})"); tank_click(pos_["x"], pos_["y"]); page.wait_for_timeout(150)
        no_panel = not page.locator("#panel").is_visible()
        page.click("#deco-done"); page.wait_for_timeout(100); ex1 = page.evaluate("AQ.edit()")
        tool("brush"); page.wait_for_timeout(60); tool("food"); page.wait_for_timeout(60); ex2 = page.evaluate("AQ.edit()")
        check("bible 26 / AD v4 7: in edit mode fish can't be tapped; Done leaves edit mode (back to Look); choosing another tool also leaves it",
              no_panel and not ex1["editing"] and ex1["done"] is None and page.locator('.tool[data-tool="food"]').get_attribute("aria-pressed") == "true" and not ex2["editing"], json.dumps([ex1, ex2]))
        # max 12 decorations, persistence
        ev("while (G.state.decor.length < 12) G.buyDecor('stone'); G.state.decor[0].x = 0.3; G.state.decor[0].sh = 1.4; G.state.decor[0].color = 70; G.save();")
        page.click("#btn-shop"); page.wait_for_timeout(150); page.click('#shop .tab[data-tab="decor"]'); page.wait_for_timeout(120)
        full_d = page.evaluate("[...document.querySelectorAll('#shop-decor button')].map((b) => [b.disabled, b.innerText.trim()])"); refused = ev("return G.buyDecor('leaf') === null && G.state.decor.length === 12;")
        page.click("#shop-close"); snap_d = S()["decor"]
        boot("?speed=1"); after_d = S()["decor"]
        check("v4 7: max 12 decorations (Buy disabled with 'Tank is full of decorations'); decorations keep position, size and colour across a reload",
              all(d_ and t_ == "Tank is full of decorations" for d_, t_ in full_d) and refused and after_d == snap_d and after_d[0]["x"] == 0.3 and after_d[0]["sh"] == 1.4 and after_d[0]["color"] == 70, json.dumps(full_d))
        # fish info side panel geometry + meal bar
        fp = ev("fresh(); G.state.tank.xp = 5000; G.state.gold = 1000; const f = G.buyFish('platy'); AQ.pinFish(f.id, 0.3, 0.5); G.feedTap(f.x, f.y); return f.id;")
        page.wait_for_timeout(150); tool("hand"); click_fish(fp); page.wait_for_timeout(250)
        pn = page.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const k = r('#tank-wrap'), p = r('#panel');
            return { w: p.width, h: p.height, right: k.right - p.right, top: p.top - k.top, tankH: k.height, overflowY: getComputedStyle(document.getElementById('panel')).overflowY,
                     meal: document.getElementById('p-meal').textContent, segs: [...document.querySelectorAll('#p-mealbar i')].map((e) => e.classList.contains('on')),
                     segH: document.querySelector('#p-mealbar i') ? document.querySelector('#p-mealbar i').getBoundingClientRect().height : 0, worth: document.getElementById('p-worth').textContent }; })()""")
        page.screenshot(path=shot("fish_info_meal"))
        check("AD v4 8 / bible 18: fish info docks right (300 / 380 wide, tank height - 16, scrolls); 'Meal 1 of 2 · needs 2 food' with a 3-segment 10px bar (1 filled), 'Worth 0 gold'",
              abs(pn["w"] - (380 if LARGE else 300)) < 0.5 and abs(pn["h"] - (pn["tankH"] - 16)) < 0.5 and abs(pn["right"] - 8) < 0.5 and abs(pn["top"] - 8) < 0.5 and pn["overflowY"] == "auto"
              and pn["meal"] == "Meal 1 of 2 · needs 2 food" and pn["segs"] == [True, False, False] and abs(pn["segH"] - 10) < 0.5 and pn["worth"] == "Worth 0 gold", json.dumps(pn))
        page.keyboard.press("Escape")
        # away window (NUMBERS v4 11.1)
        aw_ = ev("""fresh(); const quiet = G.catchUp(600); const shownQuiet = AQ.showAway(quiet); const vis1 = !document.getElementById('away').hidden;
          G.state.dirt.t = T.dirt.stageAtSec[1] - 100; const dirty = G.catchUp(200); const shown = AQ.showAway(dirty); const txt = document.getElementById('away-list').innerText;
          document.getElementById('away').hidden = true; return { quiet: quiet.lines, shownQuiet, vis1, dirty: dirty.lines, shown, txt };""")
        check("bible 23: the away window never says the tank is clean; it names the dirt stage only when dirty ('Tank is at dirt stage 2') and doesn't open when there's nothing to report",
              aw_["quiet"] == [] and aw_["shownQuiet"] is False and not aw_["vis1"] and aw_["dirty"] == ["tank is at dirt stage 2"] and aw_["shown"] is True and aw_["txt"].strip() == "Tank is at dirt stage 2", json.dumps(aw_))
        # new-tank start screenshot (0 / 0, dirt stage 3, defaults)
        ev("G.reset(); G.state.speed = 1;"); page.wait_for_timeout(400); page.screenshot(path=shot("new_tank_start"))

        # ================================================================ F. balance
        bc = page.evaluate("AQ.game.balanceChecks()")
        # Designer check (a): gold per day if you always clean at stage n = cleanGold[n] * 24 h / stage-n time; stage 1 earns the most
        per_day = [tj["dirt"]["cleanGold"][i] * 86400 / t for i, t in enumerate(tj["dirt"]["stageAtSec"])]
        check("Designer check (a): cleaning at stage 1 earns the most gold per day (16/12/8/5/3), falling every stage",
              per_day == [16, 12, 8, 5, 3] and all(per_day[i] < per_day[i - 1] for i in range(1, 5)) and bc["cleanOk"] and bc["cleanPerDay"] == per_day, str(per_day))
        # Designer check (b): profit(L) = sell[L] + level-up gold up to L - price - food eaten up to L (food 1 gold each, NUMBERS.md 5)
        prof = {}
        for sp in tj["species"]:
            food_val = tj["foodPacks"][0]["gold"] / tj["foodPacks"][0]["food"]
            port = sp["mealFood"]
            rows = []
            for L in range(1, 5):
                food = sum(2 * port[i] for i in range(L - 1))  # v4: start + mid meal of every finished level
                no_food = sp["sell"][L - 1] + sum(sp["levelUpGold"][:L - 1]) - sp["price"]
                rows.append((round(no_food - food * food_val + tj["feedGoldPerFish"] * L, 2), no_food))
            prof[sp["id"]] = rows
        ok_b = all(all(r[0] <= 0 for r in rows[:3]) and rows[3][0] > 0 for rows in prof.values())
        check("Designer check (b, v4 10): selling at L1-L3 is never a profit, L4 always is (L3: Guppy -1, Danio 0, Neon 0, Platy 0; L4: +24/+63/+114/+189)",
              ok_b and [prof[k][2][0] for k in ("guppy", "danio", "neon", "platy")] == [-1, 0, 0, 0] and [prof[k][3][0] for k in ("guppy", "danio", "neon", "platy")] == [24, 63, 114, 189] and bc["sellOk"]
              and [round(r_["l4perHour"]) for r_ in bc["sell"]] == [69, 144, 186, 216],
              json.dumps({k: [r[0] for r in v] for k, v in prof.items()}) + " | without food: " + json.dumps({k: [r[1] for r in v] for k, v in prof.items()}))

        # v4 9 first session: new tank -> first clean -> buy a Guppy -> six meals to adult -> sell (no waiting between actions)
        sl = ev("""G.reset(); const rows = []; const snap = (k) => rows.push([k, G.state.gold, G.state.food, G.state.tank.xp]);
          snap('start'); rubAll(1.01); snap('clean'); const a = G.buyFish('guppy'); snap('buy'); const d0 = G.state.dirt.t; let t = 0, meals = 0;
          if (feedFull(a)) meals++;
          while (a.level < 4 && t < 5000) { G.tick(1); t++; if (a.state === 'HUNGRY') { feedFull(a); meals++; } }
          snap('adult'); const lvl = G.tankInfo().level, dirtMoved = G.state.dirt.t - d0 - t; G.sell(a.id); snap('sold');
          return { rows, meals, lvl, dirtMoved, grow: t };""")
        check("v4 first session: start 0/0/0 -> clean 20/10/5 -> buy Guppy 0/10/5 -> six meals to adult 7/4/81 (tank Lv2) -> sell 47/4/161; meals moved dirt 30 min",
              [r_[1:] for r_ in sl["rows"]] == [[0, 0, 0], [20, 10, 5], [0, 10, 5], [7, 4, 81], [47, 4, 161]] and sl["meals"] == 6 and sl["lvl"] == 2 and sl["dirtMoved"] == 1800 and sl["grow"] == 1260, json.dumps(sl))

        # ================================================================ G. Art Director look spec (v2 dirt + fish growth)
        a = ev("""const V = G.CFG.VISUAL, sz = AQ.size(); fresh(); G.state.gold = 1000;
          let spots = [], counts = [];
          for (let run = 0; run < 40; run++) {
            clean();
            for (let i = 0; i < 5; i++) { G.state.dirt.t = T.dirt.stageAtSec[i] - 0.5; G.tick(1); counts.push(G.state.dirt.spots.length === T.dirt.spots[i]); }
            spots = spots.concat(G.state.dirt.spots.map((s) => {
              const o = G.state.dirt.spots.find((x) => x.id === s.over);
              const d = o ? Math.hypot((s.x - o.x) * sz.W, (s.y - o.y) * sz.H) / (o.r * sz.waterH) : null;
              return { stage: s.stage, r: s.r, over: s.over, d, olderOk: o ? o.id < s.id : true };
            }));
          }
          const looks = V.dirtStages.map((l) => l.look);
          const later = spots.filter((s) => s.stage >= 2), ov = later.filter((s) => s.over != null);
          const k1 = FishArt.growth(1), k4 = FishArt.growth(4);
          const tail = (lv) => { const c = document.createElement('canvas'); c.width = 400; c.height = 300; const x = c.getContext('2d');
            x.translate(260, 150); FishArt.drawFish(x, 'guppy', 200, 0, { level: lv });
            const tl = FishArt.ART.guppy.tailLen * FishArt.growth(lv).tl * 200, cx = 260 - 0.31 * 200 - tl * 0.55;
            const d = x.getImageData(Math.round(cx - 6), 140, 12, 20).data; let al = 0, sat = 0, n = 0;
            for (let i = 0; i < d.length; i += 4) { al += d[i + 3] / 255; if (d[i + 3] > 0) { sat += (Math.max(d[i], d[i+1], d[i+2]) - Math.min(d[i], d[i+1], d[i+2])) / 255; n++; } }
            return { alpha: +(al / (d.length / 4)).toFixed(3), sat: +(sat / Math.max(1, n)).toFixed(3) }; };
          const res = {
            looks, alphas: V.dirtStages.map((l) => l.alpha), radii: V.dirtStages.map((l) => l.r),
            everyStageStyled: spots.every((s) => s.stage >= 1 && s.stage <= 5 && !!looks[s.stage - 1]),
            radiusInRange: spots.every((s) => s.r >= V.dirtStages[s.stage - 1].r[0] - 1e-9 && s.r <= V.dirtStages[s.stage - 1].r[1] + 1e-9),
            countsOk: counts.every(Boolean), stage1NeverOver: spots.filter((s) => s.stage === 1).every((s) => s.over == null),
            overlapRate: +(ov.length / later.length).toFixed(2),
            overlapDistOk: ov.every((s) => s.d >= 0.4 - 1e-6 && s.d <= 1.6 + 1e-6 && s.olderOk),
            l1Clear: k1.clear && k1.sat === 0.3 && k1.tl === 0.45 && k4.fin === 1 && k4.sat === 1,
            tailL1: tail(1), tailL4: tail(4), layer: V.dirtLayer, tint: [V.dirtStages[3].tintHalf, V.dirtStages[3].tintMix],
            film: { rgb: V.dirtFilm.rgb, centre: V.dirtFilm.centre, edge: V.dirtFilm.edge, scum: [V.dirtFilm.scumFrac, V.dirtFilm.scumAlpha] },
          };
          const px = (sp, lv, fx, fy) => { const c = document.createElement('canvas'); c.width = 400; c.height = 300; const x = c.getContext('2d');
            x.translate(200, 150); FishArt.drawFish(x, sp, 200, 0, { level: lv }); const hh = FishArt.ART[sp].depth * 100;
            const d = x.getImageData(Math.round(200 + fx * 200), Math.round(150 + fy * hh), 1, 1).data; return [d[0], d[1], d[2], +(d[3] / 255).toFixed(2)]; };
          const stripeY = 0.14 * 0.8125, stripeX = -0.015;
          res.danioL1 = px('danio', 1, stripeX, stripeY); res.danioL1off = px('danio', 1, stripeX, stripeY + 0.12); res.danioL3 = px('danio', 3, stripeX, stripeY);
          res.danioStripes = FishArt.LOOK.danioStripes.map((a) => a.length);
          res.neonL2 = FishArt.LOOK.neonL2LineAlpha;
          res.platyFinL2 = px('platy', 2, -0.04, -1.2); res.platyFinL4 = px('platy', 4, -0.04, -1.2);
          res.hair = [V.dirtStages[3].alpha, V.dirtStages[3].strandAlpha];
          fresh(); return res;""")
        rr = a["radii"]
        check("dirt v2: 5 distinct looks, spots drawn in their own stage's style and radius", len(set(a["looks"])) == 5 and a["everyStageStyled"] and a["radiusInRange"] and a["countsOk"], json.dumps(rr))
        check("dirt v4: stage 1 alpha 0.22 r 0.10-0.14 (AD v4 21), stages 2-5 keep the v2 table (0.22/0.32/0.40/0.46, 0.11-0.14 ... 0.24-0.30); radii in water heights",
              a["alphas"] == [0.22, 0.22, 0.32, 0.40, 0.46] and rr == [[0.10, 0.14], [0.11, 0.14], [0.16, 0.20], [0.20, 0.25], [0.24, 0.30]], f"{a['alphas']} {rr}")
        check("dirt v4: stage 1 wash 0.03 (new), stage 2-4 wash 0.04/0.08/0.12, stage 5 film rgb(70,110,40) 0.28 -> 0.42, scum top 8% at 0.45, stage 4 brown tint on half",
              a["layer"][0] == {"wash": "rgba(95,110,40,0.03)"} and [l and l.get("wash") for l in a["layer"][1:4]] == ["rgba(95,110,40,0.04)", "rgba(95,110,40,0.08)", "rgba(108,116,38,0.12)"] and a["layer"][4] == {"film": True}
              and a["film"] == {"rgb": [70, 110, 40], "centre": 0.28, "edge": 0.42, "scum": [0.08, 0.45]} and a["tint"] == ["#5A5228", 0.6], json.dumps([a["layer"], a["film"], a["tint"]]))
        check("dirt: stage 2+ spots overlap an older spot about half the time, within 0.6 R of its edge", 0.3 <= a["overlapRate"] <= 0.7 and a["overlapDistOk"] and a["stage1NeverOver"], f"rate={a['overlapRate']}")
        dl1, dof, dl3 = a["danioL1"], a["danioL1off"], a["danioL3"]
        check("AD ruling 1: zebra danio L1 has no stripe (stripes from L2)", a["danioStripes"] == [0, 2, 4, 4] and dl1[0] >= dl1[2] and max(abs(dl1[i] - dof[i]) for i in range(3)) < 12 and dl3[2] > dl3[0] + 30, f"L1 {dl1} off {dof} L3 {dl3}")
        ns = ev("""const V = G.CFG.VISUAL, L = AQ.fishLen('neon', 2), depth = FishArt.ART.neon.depth * L, sc = 4;
          const meas = (lv) => { const c = document.createElement('canvas'); c.width = 600; c.height = 400; const x = c.getContext('2d');
            x.translate(300, 200); x.scale(sc, sc); FishArt.drawFish(x, 'neon', L, 0, { level: lv });
            const d = x.getImageData(300, 0, 1, 400).data; let n = 0, best = null;
            for (let y = 0; y < 400; y++) { const i = y * 4; if (d[i + 3] > 128 && d[i + 2] - d[i] > 90) { n++; if (!best || d[i + 2] - d[i] > best[2] - best[0]) best = [d[i], d[i + 1], d[i + 2]]; } }
            return { px: +(n / sc).toFixed(2), best }; };
          return { L: +L.toFixed(1), depth: +depth.toFixed(2), l1: meas(1), l2: meas(2), look: FishArt.LOOK };""")
        need = max(2, 0.12 * ns["depth"])
        check("AD ruling (neon L2): line 85% in the adult stripe blue, no glow, >= max(2 px, 12% body depth) thick at tank size",
              ns["look"]["neonL2LineAlpha"] == 0.85 and ns["look"]["neonStripe"] == ["#5ff6ff", "#2aa8ff", "#2a6bff"] and ns["l1"]["px"] == 0
              and need <= ns["l2"]["px"] <= need + 2.5 and ns["l2"]["best"][2] > 200, f"tank L={ns['L']}px depth={ns['depth']}px need>={need:.2f}px measured={ns['l2']['px']}px colour={ns['l2']['best']}")
        f2, f4 = a["platyFinL2"], a["platyFinL4"]
        check("AD ruling 5b: platy L2 fin keeps its own orange hue at ~65% opacity", f2[0] > 230 and f2[0] - f2[2] > 150 and abs(f2[1] - f4[1]) < 25 and 0.58 < f2[3] < 0.72 and f4[3] > 0.75, f"L2 {f2} L4 {f4}")
        check("AD ruling 3 + v2: hair-algae patch 0.40, strands 0.5", a["hair"] == [0.40, 0.5], str(a["hair"]))
        check("fish: L1 tail clear/uncoloured, L4 tail full colour (growth table)", a["l1Clear"] and a["tailL1"]["alpha"] < 0.35 and a["tailL1"]["sat"] < 0.15 and a["tailL4"]["alpha"] > 0.6 and a["tailL4"]["sat"] > 0.4, f"L1 {a['tailL1']} L4 {a['tailL4']}")

        # stage 5 film: only at stage 5, fades with the grime, gone after the last spot, guard <= 0.6
        ev("fresh(); G.state.gold = 1000; G.state.speed = 1; toStage(4);"); page.wait_for_timeout(200)
        f4_ = page.evaluate("[AQ.game.dirtFilm(), AQ.filmInfo().max]")
        ev("toStage(5);"); page.wait_for_timeout(250)
        f5 = page.evaluate("({ s: AQ.game.dirtFilm(), fi: AQ.filmInfo(), guard: AQ.guardCheck() })")
        check("film: none at stage 4, full at stage 5 (centre ~0.28, edges up to ~0.42+cloud)", f4_ == [0, 0] and f5["s"] == 1 and 0.2 <= f5["fi"]["midMax"] <= 0.36 and 0.38 <= f5["fi"]["max"] <= 0.52, json.dumps([f4_, f5["fi"]]))
        check("guard: film + one spot <= 0.6 in the middle 60% of the tank", f5["guard"]["worst"] <= 0.6 + 1e-3, json.dumps(f5["guard"]))
        ev("halfGrime();"); page.wait_for_timeout(250)
        mid = page.evaluate("({ s: AQ.game.dirtFilm(), fi: AQ.filmInfo() })")
        check("film fades in proportion to the grime left (half-rubbed -> ~0.5)", 0.4 <= mid["s"] <= 0.6 and abs(mid["fi"]["strength"] - mid["s"]) < 0.05 and mid["fi"]["max"] > 0, json.dumps(mid))
        ev("G.state.dirt.spots = G.state.dirt.spots.slice(0, 1);")  # everything but one half-rubbed spot already cleared
        pre = ev("const s = G.state.dirt.spots; return s.length ? G.dirtFilm() : -1;")
        ev("rubAll(1.01);"); page.wait_for_timeout(250)
        gone = page.evaluate("({ s: AQ.game.dirtFilm(), fi: AQ.filmInfo(), st: AQ.game.dirtStage() })")
        check("film is already faint before the last spot clears and gone right after", 0 <= pre <= 0.3 and gone["s"] == 0 and gone["fi"]["max"] == 0 and gone["st"] == 0, json.dumps({"beforeLast": pre, "after": gone}))

        # ================================================================ H. touch: rub-clean with real touch drags (CDP, phone emulation)
        tctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=2, has_touch=True, is_mobile=True)
        tp = tctx.new_page()
        tp.on("pageerror", lambda e: errors.append(f"pageerror(touch): {e}"))
        tp.goto(BASE + "?speed=1"); tp.wait_for_function("window.AQ && window.AQ.game")
        tp.evaluate("() => { const G = AQ.game; G.reset(); const d = G.state.dirt; d.t = G.T.dirt.stageAtSec[0] - 0.5; d.spots = []; d.spawned = 0; G.state.firstCleanPending = false; G.state.gold = 20; G.buyFish('guppy'); G.tick(1); }")
        tp.wait_for_timeout(200)
        tp.tap('.tool[data-tool="sponge"]')
        cdp = tctx.new_cdp_session(tp)
        tb = tp.locator("#tank").bounding_box()
        st0 = tp.evaluate("AQ.game.dirtStage()"); gold0 = tp.evaluate("AQ.game.state.gold")
        lift = tp.evaluate("AQ.geom().spongeR * AQ.game.CFG.VISUAL.spongeTouchLiftFrac")
        for _ in range(20):
            if tp.evaluate("AQ.game.dirtStage()") == 0: break
            for sp in tp.evaluate("AQ.spotsScreen()"):
                pts = []
                for k in range(4):
                    pts += [(sp["x"] - sp["r"], sp["y"] + lift), (sp["x"] + sp["r"], sp["y"] + lift + 3)]
                x0, y0 = pts[0]
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": tb["x"] + x0, "y": tb["y"] + y0}]})
                for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                    for t in range(1, 7):
                        x_ = ax + (bx - ax) * t / 6; y_ = ay + (by - ay) * t / 6
                        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": tb["x"] + x_, "y": tb["y"] + y_}]})
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        check("touch drags rub the tank clean (touch emulation), stage 1 pays +2 gold", st0 == 1 and tp.evaluate("AQ.game.dirtStage()") == 0 and tp.evaluate("AQ.game.state.gold") == gold0 + tj["dirt"]["cleanGold"][0],
              f"stage {st0}->{tp.evaluate('AQ.game.dirtStage()')}")
        tp.evaluate("AQ.game.reset(); AQ.game.save()")
        tctx.close()

        page.evaluate("AQ.game.reset(); AQ.game.save()")
        check("no console errors / page errors", not errors, "; ".join(errors[:5]))
        browser.close()



def portrait():
    """AD v4 1: held upright the rotate screen covers everything; the game clock keeps running; turning back resumes with no reload."""
    VIEW[0] = "portrait"
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (w, h, icon) in ((390, 844, 120), (820, 1180, 160)):
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(400)
            page.evaluate("window.__boot = Math.random()")
            info = page.evaluate("""(() => { const r = document.getElementById('rotate'), i = document.getElementById('rotate-icon').getBoundingClientRect(), t = document.getElementById('rotate-text');
                const e = document.elementFromPoint(innerWidth / 2, innerHeight * 0.9), app = getComputedStyle(document.getElementById('app')).display;
                return { shown: !r.hidden && getComputedStyle(r).display !== 'none', bg: getComputedStyle(r).backgroundColor, iw: i.width, cx: (i.left + i.right) / 2 - innerWidth / 2,
                         text: t.textContent, fs: getComputedStyle(t).fontSize, fw: getComputedStyle(t).fontWeight, top: e && e.closest('#rotate') !== null, app,
                         anim: getComputedStyle(document.querySelector('#rotate-icon .phone')).animationDuration }; })()""")
            vis = page.evaluate("""(() => { const out = {}; for (const id of ['tank', 'tools', 'hud', 'debug']) { const el = document.getElementById(id), cs = getComputedStyle(el);
                out[id] = { rects: el.getClientRects().length, vis: cs.visibility, hidden: el.getClientRects().length === 0 || cs.visibility === 'hidden' || !el.checkVisibility({ visibilityProperty: true }) }; }
                out.rotateVisible = document.getElementById('rotate').checkVisibility({ visibilityProperty: true }); return out; })()""")
            check(f"{w}x{h} upright: ONLY the rotate screen is visible; tank canvas, tool column, top bar and debug row are hidden (display none / no boxes), not just covered",
                  vis["rotateVisible"] and all(vis[k]["hidden"] and vis[k]["rects"] == 0 for k in ("tank", "tools", "hud", "debug")), json.dumps(vis))
            g0 = page.evaluate("AQ.game.state.gameTime"); f0 = page.evaluate("AQ.frames()")
            page.wait_for_timeout(1200)
            g1 = page.evaluate("AQ.game.state.gameTime"); f1 = page.evaluate("AQ.frames()")
            page.screenshot(path=os.path.join(SHOTS, f"portrait_rotate_{w}x{h}.png"))
            check(f"{w}x{h} upright: rotate screen covers everything (#07192a), {icon}px icon centred, 'Turn your device sideways' 18px/800, animation 1.0 s turn + 0.8 s hold",
                  info["shown"] and info["bg"] == "rgb(7, 25, 42)" and abs(info["iw"] - icon) < 0.5 and abs(info["cx"]) < 1 and info["text"] == "Turn your device sideways"
                  and info["fs"] == "18px" and info["fw"] == "800" and info["top"] and info["app"] == "none" and info["anim"] == "1.8s", json.dumps(info))
            check(f"{w}x{h} upright: the game clock keeps running while drawing pauses", 0.8 < g1 - g0 < 2.5 and f1 == f0, f"game +{g1 - g0:.2f}s, frames {f0}->{f1}")
            page.set_viewport_size({"width": h, "height": w}); page.wait_for_timeout(500)
            back = page.evaluate("({ rot: document.getElementById('rotate').hidden, boot: window.__boot !== undefined, frames: AQ.frames(), tank: document.getElementById('tank-wrap').getBoundingClientRect().width })")
            page.wait_for_timeout(300)
            check(f"{w}x{h}: turning sideways hides the rotate screen and resumes drawing with no reload", back["rot"] and back["boot"] and page.evaluate("AQ.frames()") > f1 and back["tank"] > 300, json.dumps(back))
            ctx.close()
        # AD addition: open shop + confirm dialog + toast in landscape, then turn upright -> none of them shows; background fully opaque
        ctx = browser.new_context(viewport={"width": 844, "height": 390}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(400)
        page.evaluate("AQ.openShop(); document.getElementById('dbg-reset').click(); AQ.toast('Guppy is hungry!', '', { ms: 60000 })")
        page.wait_for_timeout(300)
        ids = ("shop", "confirm", "toasts", "tank", "tools", "hud", "debug")
        before = page.evaluate("(ids) => Object.fromEntries(ids.map((id) => [id, document.getElementById(id).checkVisibility({ visibilityProperty: true })]))", list(ids))
        page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(1400)
        after = page.evaluate("""(ids) => { const o = {}; for (const id of ids) { const el = document.getElementById(id);
            o[id] = { visible: el.checkVisibility({ visibilityProperty: true }), rects: el.getClientRects().length }; }
            const t = document.querySelector('#toasts .toast'); o.toastInDom = !!t; o.toastVisible = t ? t.checkVisibility({ visibilityProperty: true }) : false;
            const hits = []; for (let y = 10; y < innerHeight; y += 60) for (let x = 10; x < innerWidth; x += 60) { const e = document.elementFromPoint(x, y); hits.push(!!(e && e.closest('#rotate'))); }
            o.allHitsRotate = hits.every(Boolean); return o; }""", list(ids))
        path = os.path.join(SHOTS, "portrait_rotate_over_open_ui_390x844.png"); page.screenshot(path=path)
        w_, h_, px = png_rgb(open(path, "rb").read())
        bad, n = [], 0
        for y in range(0, h_, 6):
            for x in range(0, w_, 6):
                if abs(x - w_ / 2) < 145 and -75 < y - h_ / 2 < 95: continue  # centred icon + text block (text is ~230 px wide)
                n += 1; c = px(x, y)
                if max(abs(c[0] - 7), abs(c[1] - 25), abs(c[2] - 42)) > 1: bad.append((x, y, c))
        check("390x844 upright over an open shop + confirm dialog + toast: none of them (nor tank, tool column, top bar, debug row) is visible; every tap point hits the rotate screen",
              all(before[k] for k in ("shop", "confirm", "toasts")) and not any(after[k]["visible"] for k in ids) and not after["toastVisible"] and after["allHitsRotate"],
              json.dumps({"before": before, "after": after}))
        check(f"390x844 rotate screen background fully opaque: {n} sampled pixels outside the icon/text block are exactly #07192a (no tank colours through)",
              not bad and n > 5000, f"{len(bad)} off-colour, e.g. {bad[:4]}")
        info = page.evaluate("""(() => { const i = document.getElementById('rotate-icon'), svg = i.querySelector('svg') || i;
            return { phone: !!i.querySelector('.phone'), arrow: !!i.querySelector('.arrow, [class*=arrow]'), text: document.getElementById('rotate-text').textContent, w: i.getBoundingClientRect().width }; })()""")
        check("390x844 rotate screen per AD: 120px phone icon with curved arrow, 'Turn your device sideways'",
              info["phone"] and info["arrow"] and info["text"] == "Turn your device sideways" and abs(info["w"] - 120) < 0.5, json.dumps(info))
        page.set_viewport_size({"width": 844, "height": 390}); page.wait_for_timeout(500)
        back = page.evaluate("(ids) => Object.fromEntries(ids.map((id) => [id, document.getElementById(id).checkVisibility({ visibilityProperty: true })]))", ["shop", "confirm", "tank", "tools", "hud", "debug"])
        check("turning back sideways: the shop and confirm dialog are still open where they were (nothing lost)", all(back.values()), json.dumps(back))
        page.evaluate("document.querySelector('#confirm button').click()")
        ctx.close()
        browser.close()
    check("portrait pass: no page errors", not errors, "; ".join(errors[:3]))

def cache_bust():
    """Producer: every local script/CSS tag carries the same ?v=<build> so phones never run stale files after an update."""
    import re
    html = open(os.path.join(HERE, "..", "index.html")).read()
    tags = re.findall(r'(?:src|href)="((?!https?:|//)[^"]+\.(?:js|css)(?:\?[^"]*)?)"', html)
    vers = {re.search(r"\?v=([0-9A-Za-z._-]+)$", t).group(1) if re.search(r"\?v=([0-9A-Za-z._-]+)$", t) else None for t in tags}
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page(viewport={"width": 844, "height": 390})
        page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game")
        loaded = page.evaluate("performance.getEntriesByType('resource').map((e) => e.name).filter((n) => /\\.(js|css)(\\?|$)/.test(n))")
        browser.close()
    v = next(iter(vers)) if len(vers) == 1 else None
    check(f"cache busting: all {len(tags)} script/CSS tags in index.html carry the same ?v= build id and the page loads them with it",
          len(tags) == 5 and v is not None and len(loaded) >= 5 and all(f"?v={v}" in n for n in loaded), json.dumps({"tags": tags, "loaded": loaded}))

if __name__ == "__main__":
    views = [tuple(int(v) for v in x.split("x")) for x in os.environ.get("AQ_VIEWS", "844x390,1180x820").split(",")]
    for vw, vh in views:
        print(f"\n======== {vw}x{vh}", flush=True)
        main(vw, vh)
    if os.environ.get("AQ_PORTRAIT", "1") == "1":
        print("\n======== portrait", flush=True)
        portrait()
    cache_bust()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)
