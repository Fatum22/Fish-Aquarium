"""Headless end-to-end check of the Aquarium prototype (Designer v4 numbers).

Run (server must be up on 8766):
  /workspace/tools/venv-aq/bin/python /workspace/aquarium/tests/verify.py
Timing rules are checked by stepping the game in the page (AQ.game.tick), so hours-long timers run in
milliseconds; UI checks use real mouse/touch input. Writes a few screenshots to ../screenshots/
(the art/look screenshots come from tests/art_shots.py). Resets the save at the end.
"""
import json, os, struct, sys, time, zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("AQ_URL", "http://127.0.0.1:8766/")
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "..", "screenshots")
TUNING = "/workspace/studio/briefs/aquarium/design/tuning.json"
os.makedirs(SHOTS, exist_ok=True)

results = []
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

def main():
    errors = []
    tj = json.load(open(TUNING))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
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
        def click_fish(fid):
            for _ in range(6):
                pos = page.evaluate(f"AQ.fishScreen({fid})")
                if pos: tank_click(pos["x"], pos["y"])
                page.wait_for_timeout(120)
                if page.locator("#panel").is_visible(): return True
            return False
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
        clear_toasts(); page.wait_for_timeout(450)
        page.screenshot(path=os.path.join(SHOTS, "feeding_flakes.png"))
        page.wait_for_timeout(250)
        live = page.evaluate("AQ.flakes().live")
        dr = sum(x["x"] - x["x0"] for x in live) / max(1, len(live))
        ev(f"AQ.pinFish({fid}, 0.15, 0.55);"); page.wait_for_timeout(1500)   # let the first shower finish / be eaten
        fl2 = page.evaluate("AQ.flakes()")
        tank_click(b_["width"] * 0.85, b_["height"] * 0.25); page.wait_for_timeout(700)
        fl3 = page.evaluate("AQ.flakes()"); live2 = [x for x in fl3["live"] if x["t"] < 1.0]
        dl = sum(x["x"] - x["x0"] for x in live2) / max(1, len(live2))
        check("flakes drift sideways toward the fed fish (fish right -> drift right, fish left -> drift left)",
              len(live) >= 4 and dr > 15 and fl3["spawned"] - fl2["spawned"] >= 8 and len(live2) >= 4 and dl < -15, f"right: {len(live)} flakes mean dx={dr:.1f}px; left: {len(live2)} flakes mean dx={dl:.1f}px")
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
        ht, gt = page.inner_text("#p-hunger"), page.inner_text("#p-growth")
        check("panel: 'Hungry! 0/1 fed · Growth paused · dies in 6h 00m'", any(ht.startswith("Hungry! 0/1 fed · Growth paused · dies in " + t) for t in ("6h 00m", "5h 59m")) and "Growth paused" in gt, f"{ht} | {gt}")
        page.screenshot(path=os.path.join(SHOTS, "panel_hungry.png"))
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
        page.screenshot(path=os.path.join(SHOTS, "shop.png"))
        page.click('[data-close="shop"]')
        sp_tab = ev("return T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.sellPrice(sp, lv)));")
        lg_tab = ev("return T.species.map((sp) => [2, 3, 4].map((lv) => G.levelUpGold(sp, lv)));")
        check("sell prices at every level (Guppy 0/8/18/40 ...) and level-up gold (Guppy 1/2/4 ...) follow tuning.json v3",
              sp_tab == [s_["sell"] for s_ in tj["species"]] and sp_tab[0] == [0, 8, 18, 40] and lg_tab == [s_["levelUpGold"] for s_ in tj["species"]] and lg_tab[0] == [1, 2, 4], json.dumps([sp_tab, lg_tab]))
        btns = []
        for lv in (1, 2, 3, 4):
            fid = ev(f"fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); f.level = {lv}; f.state = {lv} === 4 ? 'ADULT' : 'GROWING'; AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
            page.wait_for_timeout(150); tool("hand"); click_fish(fid); page.wait_for_timeout(150)
            btns.append(page.inner_text("#p-sell"))
            if lv == 4: page.screenshot(path=os.path.join(SHOTS, "panel_adult_sell.png"))
            page.keyboard.press("Escape")
        check("fish panel sell button per level: Release (0 gold) / Sell for 8 / 18 / 40 gold", btns == ["Release (0 gold)", "Sell for 8 gold", "Sell for 18 gold", "Sell for 40 gold"], str(btns))

        # debug +50 XP button (NUMBERS.md 9.13): normal XP path, tank level-ups + unlock toasts, no gold, persists
        ev("fresh(); G.state.gold = 1000; G.state.speed = 1;"); page.wait_for_timeout(100)
        check("debug row has '+50 XP' next to the speed buttons, +100g and Reset save",
              page.locator("#debug #dbg-xp").inner_text() == "+50 XP" and page.locator("#debug #dbg-gold").is_visible() and page.locator("#debug #dbg-reset").is_visible())
        page.locator("#debug").screenshot(path=os.path.join(SHOTS, "debug_row.png"))
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
        check("'While you were away' summary: 49h, Guppy died, dirt stage 5", aw and "49h 00m" in at_ and "Guppy died" in al and "dirt stage 5" in al, f"{at_} | {al}")
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
        dy = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {ids['a']}).y")
        check("dead fish floats in the top band (y about 6-10% of the tank)", 0.05 <= dy <= 0.11, f"y={dy:.3f}")
        page.keyboard.press("Escape"); tool("hand")
        opened = click_fish(ids["a"]); page.wait_for_timeout(200)
        lvl, btn = page.inner_text("#p-level") if opened else "", page.inner_text("#p-sell") if opened else ""
        check("tapping the dead fish at the top opens its panel: 'Dead' + 'Remove (0 gold)'", opened and lvl == "Dead" and btn == "Remove (0 gold)" and page.locator("#p-dead").is_visible(), f"{lvl} | {btn}")
        page.keyboard.press("Escape")
        full = ev(f"""clean(); G.state.gold = 1000; for (let i = 0; i < 4; i++) G.buyFish('guppy');
          const n = G.state.fish.length, c = G.canBuy('guppy'); const dead = G.state.fish.find((f) => f.id === {ids['a']});
          const r = G.feedTap(dead.x, dead.y); return {{ n, ok: c.ok, reason: c.reason, fedId: r.ok ? r.fish.id : null, deadFed: dead.fed, living: G.living() }};""")
        check("dead fish takes a tank slot (6/6 incl. dead -> 'Tank full')", full["n"] == 6 and not full["ok"] and full["reason"] == "Tank full", json.dumps(full))
        check("dead fish isn't fed and doesn't block feeding (tap on it feeds a living fish)", full["fedId"] not in (None, ids["a"]) and full["deadFed"] == 0, json.dumps(full))
        page.click("#btn-shop"); page.wait_for_timeout(200)
        check("shop disables buying while the tank is full with a dead fish in it", page.locator('button[data-buy="guppy"]').is_disabled())
        page.click('[data-close="shop"]'); tool("hand")
        gold_b = S()["gold"]; click_fish(ids["a"]); page.click("#p-sell"); page.wait_for_timeout(200)
        check("Remove (0 gold): no confirm, pays 0, frees the slot", fish(ids["a"]) is None and S()["gold"] == gold_b and not page.locator("#confirm").is_visible() and ev("return G.canBuy('guppy').ok;"))
        check("dead fish can't be sold", ev("const f = G.buyFish('guppy'); f.state = 'DEAD'; return G.sell(f.id) === null;"))

        # a fish dying now rises to the top over ~20 game-seconds
        did = ev("fresh(); G.state.gold = 100; const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, 0.5, 0.6); f.state = 'HUNGRY'; f.deathLeft = 0.5; G.tick(1); G.state.speed = 20; return f.id;")
        page.wait_for_timeout(300); y_mid = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y")
        page.wait_for_timeout(1700); y_top = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y")
        check("a fish that just died rises to the top band over ~20 game s", y_mid > 0.2 and 0.05 <= y_top <= 0.11, f"y after ~6 game s {y_mid:.2f}, after ~40 {y_top:.3f}")
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
        page.wait_for_timeout(2800); clear_toasts(); tool("food"); page.wait_for_timeout(250)  # let earlier toasts/floats/callouts expire
        # visible text outside the dirt bar (#dirt-wrap) must carry no dirt message (NUMBERS.md 3 rule 1)
        DIRT_TXT = """() => { const out = []; const walk = (el) => { if (el.id === 'dirt-wrap' || el.id === 'dirt-callout' || el.id === 'debug') return;
            const cs = getComputedStyle(el); if (el.hidden || cs.display === 'none' || cs.visibility === 'hidden') return;
            for (const n of el.childNodes) { if (n.nodeType === 3 && /dirt|dirty|clean the tank|pick the sponge|rub the/i.test(n.textContent)) out.push(n.textContent.trim()); else if (n.nodeType === 1) walk(n); } };
          walk(document.getElementById('app')); return out; }"""
        def ui_state():
            return page.evaluate("""() => ({ callout: !document.getElementById('dirt-callout').hidden, calloutText: document.getElementById('dirt-callout').textContent,
              count: +(document.getElementById('dirt-callout').dataset.count || 0), toasts: document.getElementById('toasts').children.length,
              hint: document.getElementById('hint').textContent, floats: AQ.floats(true), flakes: AQ.flakes().spawned, food: AQ.game.state.food })""")
        pre = ui_state(); pre_txt = page.evaluate(DIRT_TXT)
        check("dirty tank + Food selected, before tapping: no dirt hint anywhere except the dirt bar (hint empty, no callout, no toast)",
              stage() == 3 and pre["hint"] == "" and not pre["callout"] and pre["toasts"] == 0 and pre_txt == [], json.dumps({"state": pre, "dirtText": pre_txt}))
        taps = []
        for k, wait_before in enumerate([0, 2800, 1000]):   # tap 2 after the callout expired (re-show), tap 3 while still up (restart)
            if wait_before: page.wait_for_timeout(wait_before)
            before = ui_state()
            tank_click(box()["width"] * (0.3 + 0.2 * k), box()["height"] * 0.35); page.wait_for_timeout(250)
            after = ui_state(); txt = page.evaluate(DIRT_TXT)
            taps.append({"hiddenBefore": not before["callout"], "shown": after["callout"], "text": after["calloutText"], "count": after["count"] - before["count"],
                         "toasts": after["toasts"], "hint": after["hint"], "floats": after["floats"], "food": after["food"] - before["food"], "flakes": after["flakes"] - before["flakes"], "otherDirtText": txt})
        page.wait_for_timeout(2000); still = ui_state()["callout"]   # 2.25 s after tap 3 = 3.25 s after tap 2 -> only up if tap 3 restarted it
        page.wait_for_timeout(700); gone = not ui_state()["callout"]
        check("each of 3 blocked feed taps shows the dirt-bar callout 'Clean the tank first' (re-shown after expiring, restarted while up, ~2.5 s)",
              all(t["shown"] and t["text"] == "Clean the tank first" and t["count"] == 1 for t in taps) and taps[1]["hiddenBefore"] and not taps[2]["hiddenBefore"] and still and gone, json.dumps(taps))
        check("blocked taps: no toast, no bottom hint, no centre message, no other dirt text", all(t["toasts"] == 0 and t["hint"] == "" and t["floats"] == [] and t["otherDirtText"] == [] for t in taps))
        check("blocked taps: no food spent, no flakes", all(t["food"] == 0 and t["flakes"] == 0 for t in taps))
        gold_b, xp_b = S()["gold"], S()["tank"]["xp"]
        ok = rub_clean(); s = S()
        fl = page.evaluate("AQ.floats(true)")
        check("sponge mouse rub cleans stage 3: +4 gold, +5 XP, 'Sparkling! +4 gold' float", ok and s["gold"] == gold_b + 4 and s["tank"]["xp"] == xp_b + 5 and "Sparkling! +4 gold" in fl, f"gold {gold_b}->{s['gold']} xp {xp_b}->{s['tank']['xp']} {fl}")
        tool("hand"); page.wait_for_timeout(400)
        page.screenshot(path=os.path.join(SHOTS, "after_clean.png"))
        # L1 release (confirm) and L2 sell
        tool("hand"); click_fish(gid)
        check("L1 button reads 'Release (0 gold)'", page.inner_text("#p-sell") == "Release (0 gold)", page.inner_text("#p-sell"))
        page.click("#p-sell"); page.wait_for_timeout(150)
        check("confirm dialog shown for release", page.locator("#confirm").is_visible())
        page.screenshot(path=os.path.join(SHOTS, "release_confirm.png"))
        gb = S()["gold"]; page.click("#confirm-yes"); page.wait_for_timeout(150)
        check("released L1 for 0 gold", S()["gold"] == gb and fish(gid) is None)
        sid = ev("G.state.gold = 100; const f = G.buyFish('guppy'); f.level = 2; f.state = 'GROWING'; AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(200); click_fish(sid); st = page.inner_text("#p-sell"); gb = S()["gold"]
        page.click("#p-sell"); page.wait_for_timeout(150)
        l2 = next(s_ for s_ in tj["species"] if s_["id"] == "guppy")["sell"][1]
        check(f"sold L2 Guppy for {l2} gold (no confirm)", st == f"Sell for {l2} gold" and S()["gold"] == gb + l2 and fish(sid) is None, st)
        # full tank screenshot + reload keeps state
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; ['guppy','danio','neon','platy'].forEach((id) => { const f = G.buyFish(id); feedFull(f); });")
        tool("hand"); page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SHOTS, "tank_with_fish.png"))
        check("fish stay inside the tank", all(0 < f_["x"] < 1 and 0 < f_["y"] < 1 for f_ in S()["fish"]))
        page.evaluate("AQ.game.save()"); before = S()
        boot("?speed=5"); after = S()
        check("reload keeps fish/gold/food/XP; ?speed=5 applied", len(after["fish"]) == 4 and after["gold"] == before["gold"] and after["food"] == before["food"] and after["tank"]["xp"] == before["tank"]["xp"] and after["speed"] == 5,
              f"fish {len(after['fish'])} gold {before['gold']}->{after['gold']} speed {after['speed']}")
        ev("fresh(); G.state.gold = 500; G.state.tank.xp = 1200; ['guppy','danio','neon','platy','guppy','danio'].forEach((id, i) => { const f = G.buyFish(id); f.level = [4,3,2,4,1,2][i]; f.state = f.level === 4 ? 'ADULT' : 'GROWING'; }); G.state.speed = 1;")
        page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SHOTS, "tank_mixed_levels_staged.png"))

        # ================================================================ E2. Playtester pass 6 fixes (N1-N3, N6, D1)
        R = lambda sel: page.evaluate(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return {{ l: r.left, t: r.top, r: r.right, b: r.bottom }}; }})()")
        hit = lambda a, b: a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]
        # N1: dirt-bar callout never covers the tank XP bar, still under / pointing at the dirt bar
        ev("fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.4, 0.5); toStage(2);")
        page.wait_for_timeout(200); tool("food"); tank_click(box()["width"] * 0.4, box()["height"] * 0.6); page.wait_for_timeout(300)
        co, xpb, xprow, tk, db = R("#dirt-callout"), R("#tank-xpbar"), R("#tankbar"), R("#tank"), R("#dirt-bar")
        check("N1: dirt callout visible, doesn't intersect the tank XP bar/row, sits in the tank's top corner under the dirt bar",
              page.locator("#dirt-callout").is_visible() and not hit(co, xpb) and not hit(co, xprow) and co["t"] >= xprow["b"] and co["l"] < db["r"] and co["r"] > db["l"]
              and co["t"] >= tk["t"] and co["b"] - tk["t"] <= 0.08 * (tk["b"] - tk["t"]), json.dumps({"callout": co, "xpRow": xprow, "tank": tk, "dirtBar": db}))
        page.wait_for_timeout(2700); tool("hand"); ev("clean();")
        # N2: toasts stay out of the top 12% of the tank, where dead fish float
        did = ev("fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, 0.3, 0.5); f.state = 'HUNGRY'; f.deathLeft = 0.5; G.tick(1); G.state.gameTime += 25; G.debugAddXp(60); return f.id;")
        page.wait_for_timeout(700)
        tk = R("#tank"); band = {"l": tk["l"], "t": tk["t"], "r": tk["r"], "b": tk["t"] + 0.12 * (tk["b"] - tk["t"])}
        toasts = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => { const r = e.getBoundingClientRect(); return { text: e.textContent, l: r.left, t: r.top, r: r.right, b: r.bottom }; })")
        dy = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y")
        page.screenshot(path=os.path.join(SHOTS, "dead_fish_with_toast.png"))
        check("N2: toasts ('Guppy died', tank level-up) never intersect the top 12% of the tank; dead fish stays in its 6-10% band",
              len(toasts) >= 2 and any("died" in t_["text"] for t_ in toasts) and any("Tank level 2" in t_["text"] for t_ in toasts) and not any(hit(t_, band) for t_ in toasts) and 0.05 <= dy <= 0.11,
              json.dumps({"band": band, "toasts": toasts, "deadY": round(dy, 3)}))
        # N3: only dead fish -> no hint; back once a living fish is there
        page.wait_for_timeout(2800)
        h_dead = page.inner_text("#hint").strip() if page.locator("#hint").is_visible() else ""
        page.screenshot(path=os.path.join(SHOTS, "only_dead_fish.png"))
        ev("const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.5, 0.5);"); page.wait_for_timeout(200); h_wait = page.inner_text("#hint")
        ev("const f = G.state.fish.find((x) => x.state === 'WAITING'); clean(); feedFull(f);"); page.wait_for_timeout(200); h_live = page.inner_text("#hint")
        check("N3: only dead fish -> hint empty; a living fish brings hints back ('Tap a fish to see its details' once fed)",
              h_dead == "" and h_wait.startswith("New fish!") and h_live == "Tap a fish to see its details", json.dumps([h_dead, h_wait, h_live]))
        # D1: Start new tank modal states exactly what resets, and the button does reset exactly that
        ev("fresh(); G.state.speed = 1; G.state.tank.xp = 1500; G.state.food = 3; G.state.starterGrantUsed = true; const f = G.buyFish('guppy') || null; G.state.gold = 3; if (f) { f.state = 'DEAD'; f.diedAt = G.state.gameTime - 30; } G.tick(1);")
        page.wait_for_timeout(400)
        line = page.inner_text("#newtank-reset") if page.locator("#tankover").is_visible() else ""
        page.screenshot(path=os.path.join(SHOTS, "start_new_tank_modal.png"))
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
        page.screenshot(path=os.path.join(SHOTS, "float_edge_clamp.png"))
        check("N6: a real clean finished at the far right edge: 'Sparkling! +2 gold' fully inside the tank (>= 8 px)",
              stage() == 0 and len(cb) == 1 and cb[0]["x1"] <= Wt - 8 + 0.01 and cb[0]["x0"] >= 8 and cb[0]["x1"] >= Wt - 8 - 25, json.dumps(cb))
        tool("hand")

        # ================================================================ E3. Playtester pass 7 polish (M1 arrow, M2 multi level-up, N4, N5)
        # M1 (Art Director spec): callout box unchanged; 12px-wide red triangle from its top edge, tip 4px under the dirt bar's
        # bottom, centred on the dirt bar; may cross the XP row, drawn above it (not clipped by the tank or the HUD)
        ev("fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.4, 0.5); toStage(3);")
        page.wait_for_timeout(2800); clear_toasts(); tool("food"); page.wait_for_timeout(200)
        tank_click(box()["width"] * 0.4, box()["height"] * 0.6); page.wait_for_timeout(500)   # after the pop and the dirt-bar shake
        co, ar, db, xprow, tkw = R("#dirt-callout"), R("#dirt-arrow"), R("#dirt-bar"), R("#tankbar"), R("#tank-wrap")
        tip_x, tip_y, base_w = (ar["l"] + ar["r"]) / 2, ar["t"], ar["r"] - ar["l"]
        base_y = ar["b"] - 2   # 2px strip under the base overlaps the box (no seam)
        dbc = (db["l"] + db["r"]) / 2
        # pixels down the arrow's centre line: between tip and dirt bar (no arrow), just under the tip, across the XP row,
        # in the gap between XP row and tank, and just above the box: arrow red wherever it should be
        page.screenshot(path=os.path.join(SHOTS, "dirty_feed.png"))
        cx0 = int(round(tip_x)) - 4
        png = page.screenshot(clip={"x": cx0, "y": 0, "width": 8, "height": int(co["t"]) + 2})
        _w, _h, px = png_rgb(png); dpr = _w / 8
        red = lambda c: c[0] > 200 and c[1] < 140 and c[2] < 140
        at = lambda y: px(int((tip_x - cx0) * dpr), int(y * dpr))
        samples = {"aboveTip": at(tip_y - 2), "underTip": at(tip_y + 9), "xpRowMid": at((xprow["t"] + xprow["b"]) / 2),
                   "gapXpTank": at((xprow["b"] + tkw["t"]) / 2), "aboveBox": at(co["t"] - 3)}
        arrow_pos = page.evaluate("(() => { const a = document.getElementById('dirt-arrow'); return { inTank: !!a.closest('#tank-wrap'), inHud: !!a.closest('#hud'), z: +getComputedStyle(a).zIndex, pos: getComputedStyle(a).position, hudZ: +getComputedStyle(document.getElementById('hud')).zIndex }; })()")
        geo = {"tipX": round(tip_x, 2), "dirtBarCentreX": round(dbc, 2), "tipY": round(tip_y, 2), "dirtBarBottom": round(db["b"], 2), "tipGap": round(tip_y - db["b"], 2),
               "baseW": round(base_w, 2), "baseY": round(base_y, 2), "box": co, "xpRow": xprow, "dirtBar": db, "arrow": ar, "pixels": samples, "el": arrow_pos}
        print("   M1 geometry:", json.dumps(geo))
        check("M1: callout arrow tip at the dirt bar's centre x (<= 2px) and 4px (+-1) below its bottom; 12px base on the box's top edge",
              page.locator("#dirt-arrow").is_visible() and abs(tip_x - dbc) <= 2 and 3 <= tip_y - db["b"] <= 5 and abs(base_w - 12) <= 0.5 and abs(base_y - co["t"]) <= 1, json.dumps(geo))
        check("M1: callout box stays clear of the XP row, in the tank's top-right corner (unchanged); arrow drawn above the XP row, not clipped (red pixels along its length)",
              not hit(co, xprow) and co["t"] >= xprow["b"] and co["t"] >= tkw["t"] and abs(co["r"] - (tkw["r"] - 10)) <= 1 and abs(co["t"] - (tkw["t"] + 10)) <= 1
              and not red(samples["aboveTip"]) and all(red(samples[k_]) for k_ in ("underTip", "xpRowMid", "gapXpTank", "aboveBox"))
              and not arrow_pos["inTank"] and not arrow_pos["inHud"] and arrow_pos["z"] > arrow_pos["hudZ"], json.dumps({"pixels": samples, "el": arrow_pos}))
        page.wait_for_timeout(2600)
        check("M1: arrow hides together with the callout (2.5 s)", not page.locator("#dirt-callout").is_visible() and not page.locator("#dirt-arrow").is_visible())
        tool("hand"); ev("clean();")

        # M2: 4 Guppies level up in the same tick (3 bunched in the middle, 1 at the right wall): staggered float pairs never
        # overlap, all >= 8px inside the tank; identical toasts merge into one line with a count
        page.wait_for_timeout(1900); clear_toasts(); page.evaluate("AQ.floats(true)")
        ev("""fresh(); G.state.gold = 500; G.state.speed = 1;
              [[0.5, 0.45], [0.52, 0.46], [0.48, 0.44], [0.97, 0.3]].forEach(([x, y]) => { const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, x, y); });""")
        page.wait_for_timeout(300); clear_toasts()
        ev("G.state.fish.forEach((f) => { f.progress = G.growSec(G.SPECIES.guppy, f.level) - 0.5; f.hungerDone = true; }); G.tick(1);")
        m2, snaps = [], []
        for wait in (80, 250, 700, 1100):
            page.wait_for_timeout(wait)
            bxs = page.evaluate("AQ.floatBoxes()"); snaps.append(len(bxs))
            if wait == 250: page.screenshot(path=os.path.join(SHOTS, "multi_levelup.png"))
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

        # N5: "Reset save" fits on one line at 390x844, on the same row as the other debug buttons, fully on screen
        page.wait_for_timeout(2800)
        n5 = page.evaluate("""(() => { const r = (id) => document.getElementById(id).getBoundingClientRect(); const e = document.getElementById('dbg-reset');
            const rg = document.createRange(); rg.selectNodeContents(e); const lines = new Set([...rg.getClientRects()].map((q) => Math.round(q.top))).size;
            const x = r('dbg-reset'), xp = r('dbg-xp'), g = r('dbg-gold'), dbg = r('debug');
            return { text: e.textContent, visible: e.offsetParent !== null, textLines: lines, h: x.height, xpH: xp.height, top: x.top, xpTop: xp.top, goldTop: g.top,
                     left: x.left, right: x.right, footerRight: dbg.right, vw: innerWidth, lh: parseFloat(getComputedStyle(e).fontSize) }; })()""")
        page.screenshot(path=os.path.join(SHOTS, "footer_reset_save.png"))
        print("   N5 geometry:", json.dumps(n5))
        check("N5: 'Reset save' visible on one line (1 text line, same height as '+50 XP'), same row as +100g/+50 XP, inside the footer",
              n5["visible"] and n5["text"] == "Reset save" and n5["textLines"] == 1 and abs(n5["h"] - n5["xpH"]) < 0.5 and abs(n5["top"] - n5["xpTop"]) < 0.5
              and abs(n5["top"] - n5["goldTop"]) < 0.5 and n5["right"] <= n5["footerRight"] and n5["right"] <= n5["vw"], json.dumps(n5))

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
              const d = o ? Math.hypot((s.x - o.x) * sz.W, (s.y - o.y) * sz.H) / (o.r * sz.W) : null;
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
        check("dirt v2: alphas 0.14/0.22/0.32/0.40/0.46, radii 0.075-0.11 ... 0.24-0.30 (AD v2 table)",
              a["alphas"] == [0.14, 0.22, 0.32, 0.40, 0.46] and rr == [[0.075, 0.11], [0.11, 0.14], [0.16, 0.20], [0.20, 0.25], [0.24, 0.30]], f"{a['alphas']} {rr}")
        check("dirt v2: stage 2-4 wash 0.04/0.08/0.12, stage 5 film rgb(70,110,40) 0.28 -> 0.42, scum top 8% at 0.45, stage 4 brown tint on half",
              a["layer"][0] is None and [l and l.get("wash") for l in a["layer"][1:4]] == ["rgba(95,110,40,0.04)", "rgba(95,110,40,0.08)", "rgba(108,116,38,0.12)"] and a["layer"][4] == {"film": True}
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
        tctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
        tp = tctx.new_page()
        tp.on("pageerror", lambda e: errors.append(f"pageerror(touch): {e}"))
        tp.goto(BASE + "?speed=1"); tp.wait_for_function("window.AQ && window.AQ.game")
        tp.evaluate("() => { const G = AQ.game; G.reset(); const d = G.state.dirt; d.t = G.T.dirt.stageAtSec[0] - 0.5; d.spots = []; d.spawned = 0; G.state.firstCleanPending = false; G.state.gold = 20; G.buyFish('guppy'); G.tick(1); }")
        tp.wait_for_timeout(200)
        tp.tap('.tool[data-tool="sponge"]')
        cdp = tctx.new_cdp_session(tp)
        tb = tp.locator("#tank").bounding_box()
        st0 = tp.evaluate("AQ.game.dirtStage()"); gold0 = tp.evaluate("AQ.game.state.gold")
        lift = tp.evaluate("(() => { const c = document.querySelector('#tank canvas') || document.querySelector('canvas'); return c.getBoundingClientRect().width * AQ.game.CFG.VISUAL.spongeRadiusFrac * AQ.game.CFG.VISUAL.spongeTouchLiftFrac; })()")
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
        check("touch drags rub the tank clean (phone emulation), stage 1 pays +2 gold", st0 == 1 and tp.evaluate("AQ.game.dirtStage()") == 0 and tp.evaluate("AQ.game.state.gold") == gold0 + tj["dirt"]["cleanGold"][0],
              f"stage {st0}->{tp.evaluate('AQ.game.dirtStage()')}")
        tp.evaluate("AQ.game.reset(); AQ.game.save()")
        tctx.close()

        page.evaluate("AQ.game.reset(); AQ.game.save()")
        check("no console errors / page errors", not errors, "; ".join(errors[:5]))
        browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
