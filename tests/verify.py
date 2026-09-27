"""Headless end-to-end check of the Aquarium prototype.

Run (server must be up on 8766):
  /workspace/tools/venv-aq/bin/python /workspace/aquarium/tests/verify.py
Uses ?speed=60 so timers are repeatable. Writes screenshots to ../screenshots/.
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("AQ_URL", "http://127.0.0.1:8766/")
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "..", "screenshots")
TUNING = "/workspace/studio/briefs/aquarium/design/tuning.json"
os.makedirs(SHOTS, exist_ok=True)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    return cond

def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 420, "height": 860}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(BASE + "?speed=60")
        page.wait_for_function("window.AQ && window.AQ.game")
        page.wait_for_timeout(300)

        S = lambda: page.evaluate("JSON.parse(JSON.stringify(AQ.game.state))")
        stage = lambda: page.evaluate("AQ.game.dirtStage()")
        box = page.locator("#tank").bounding_box()
        def tank_click(x, y):
            page.mouse.click(box["x"] + x, box["y"] + y)
        def fish(fid):
            return next((f for f in S()["fish"] if f["id"] == fid), None)
        def wait_for(pred, timeout=30, step=0.05):
            t0 = time.time()
            while time.time() - t0 < timeout:
                v = pred()
                if v: return v
                time.sleep(step)
            return None
        def tool(name):
            page.click(f'.tool[data-tool="{name}"]')
        def click_fish(fid):
            for _ in range(5):
                pos = page.evaluate(f"AQ.fishScreen({fid})")
                tank_click(pos["x"], pos["y"])
                page.wait_for_timeout(120)
                if page.locator("#panel").is_visible(): return True
            return False
        def feed_tap():
            tool("food"); tank_click(box["width"] * 0.5, box["height"] * 0.3); page.wait_for_timeout(60)
        def clean_then_feed():
            for _ in range(3):
                if stage() >= 1: rub_clean()
                if stage() == 0:
                    feed_tap(); return
        def rub_clean(timeout=40):
            tool("sponge")
            t0 = time.time()
            while stage() >= 1 and time.time() - t0 < timeout:
                for sp in page.evaluate("AQ.spotsScreen()"):
                    x, y, r = sp["x"], sp["y"], sp["r"]
                    page.mouse.move(box["x"] + x - r, box["y"] + y)
                    page.mouse.down()
                    for _ in range(3):
                        page.mouse.move(box["x"] + x + r, box["y"] + y + 4, steps=6)
                        page.mouse.move(box["x"] + x - r, box["y"] + y - 4, steps=6)
                    page.mouse.up()
            return stage() == 0

        # ---- 0. config matches Designer tuning.json
        tj = json.load(open(TUNING))
        check("config.js TUNING == Designer tuning.json", page.evaluate("AQ.game.T") == tj)
        s = S()
        check("URL ?speed=60 applied", s["speed"] == 60, f"speed={s['speed']}")
        check("start state: empty tank, 20 gold, 10 food", s["fish"] == [] and s["gold"] == tj["startGold"] and s["food"] == tj["startFood"], f"gold={s['gold']} food={s['food']}")
        bc = page.evaluate("AQ.game.balanceChecks()")
        check("balance: sell@L4 beats sell@L3 per slot-minute (all species)", bc["sellOk"], json.dumps(bc["sell"]))
        check("balance: clean-often pays more per hour", bc["cleanOk"], str(bc["cleanPerHour"]))

        # ---- 1. shop + buy
        page.click("#btn-shop"); page.wait_for_timeout(300)
        check("shop shows 4 species", page.locator("#shop-list .card").count() == 4)
        check("diamond stub is disabled + labelled", page.locator("button.diamond").is_disabled() and "coming later" in page.locator("button.diamond").inner_text())
        check("unaffordable species are disabled", page.locator('button[data-buy="danio"]').is_disabled())
        page.screenshot(path=os.path.join(SHOTS, "shop.png"))
        page.click('button[data-buy="guppy"]'); page.wait_for_timeout(200)
        s = S(); g = s["fish"][0]; gid = g["id"]
        check("bought Guppy for 20 gold", s["gold"] == 0 and g["sp"] == "guppy" and g["state"] == "WAITING")
        page.click('[data-close="shop"]')
        # unfed fish waits forever: advance and check nothing ticks
        page.wait_for_timeout(1500)  # 90 game-seconds
        g = fish(gid)
        check("never-fed fish stays WAITING (no hunger/death)", g["state"] == "WAITING" and g["deathLeft"] is None and g["progress"] == 0)
        tool("hand"); click_fish(gid)
        check("panel shows 'Not started - feed to start'", "Not started - feed to start" in page.inner_text("#p-growth"), page.inner_text("#p-growth"))
        # the dirt timer runs while a fish is in the tank: clean first if needed
        if stage() >= 1:
            feed_tap()
            check("feeding blocked while dirty (pre-first-feed)", fish(gid)["state"] == "WAITING")
            rub_clean()

        # ---- 2. first feed starts growth
        if stage() >= 1: rub_clean()
        food0, gold0 = S()["food"], S()["gold"]
        feed_tap()
        s = S(); g = fish(gid)
        check("first feed starts growth", g["state"] == "GROWING", g["state"])
        check("feed spends portion (1 food) and pays +1 gold", s["food"] == food0 - 1 and s["gold"] == gold0 + 1, f"food {food0}->{s['food']} gold {gold0}->{s['gold']}")

        # ---- 3. wait until hungry, panel shows paused + death timer
        wait_for(lambda: fish(gid)["state"] == "HUNGRY", timeout=10)
        g = fish(gid)
        check("fish becomes HUNGRY midway through L1", g["state"] == "HUNGRY" and abs(g["progress"] - 120) < 1e-6, f"progress={g['progress']}")
        tool("hand"); click_fish(gid)
        page.wait_for_timeout(250)
        hunger_txt = page.inner_text("#p-hunger"); death_txt = page.inner_text("#p-death")
        check("panel: 'Hungry! Growth paused' + death timer visible", "Hungry" in hunger_txt and page.locator("#p-death-row").is_visible() and "dies in" in death_txt, f"{hunger_txt} | {death_txt}")
        page.screenshot(path=os.path.join(SHOTS, "panel_hungry.png"))
        p1 = fish(gid)["progress"]; page.wait_for_timeout(600); p2 = fish(gid)["progress"]
        check("growth paused while hungry", p1 == p2 == 120, f"{p1} {p2}")
        d_before = fish(gid)["deathLeft"]
        check("death timer runs while hungry", d_before < 360, f"deathLeft={d_before:.1f}")

        # ---- 4. feed again (dirt may already be at stage 1 -> must clean first)
        if stage() >= 1:
            feed_tap()
            check("feeding blocked while dirty (hungry fish)", fish(gid)["state"] == "HUNGRY")
        clean_then_feed()
        g = fish(gid)
        check("feeding hungry fish: death timer cleared, growth resumes", g["state"] == "GROWING" and g["deathLeft"] is None, g["state"])
        pa = g["progress"]; page.wait_for_timeout(400); g = fish(gid)
        check("growth resumed after feed", g["progress"] > pa or g["level"] == 2)

        # ---- 5. reach level 2 (pays level-up gold)
        gold_before_lvl = S()["gold"]
        wait_for(lambda: (fish(gid) or {}).get("level", 0) >= 2, timeout=10)
        s = S(); g = fish(gid)
        check("fish reached level 2 and paid 10 gold", g["level"] == 2 and s["gold"] >= gold_before_lvl + 10, f"gold {gold_before_lvl}->{s['gold']}")

        # ---- 6. let dirt build up, feeding blocked, rub clean
        page.evaluate("() => { const G = AQ.game; G.state.dirt.points = G.T.dirt.stageAtPoints[2] - 0.05; }")  # one L2 fish needs ~27 game-min; jump near stage 3
        wait_for(lambda: stage() >= 3, timeout=10)
        check("dirt reached stage 3", stage() >= 3, f"stage={stage()}")
        n_spots = len(S()["dirt"]["spots"])
        check("dirt spots grow with stage (4 at stage 3)", n_spots == tj["dirt"]["spots"][stage() - 1], f"spots={n_spots}")
        tool("hand"); page.keyboard.press("Escape")
        page.screenshot(path=os.path.join(SHOTS, "dirty_tank.png"))
        food_b = S()["food"]
        feed_tap()
        check("feeding blocked at dirt>=1: food unchanged, callout shown",
              S()["food"] == food_b and page.locator("#dirt-callout").is_visible() and "Clean the tank first" in page.inner_text("#dirt-callout"))
        check("toast says 'Clean the tank first'", "Clean the tank first" in page.inner_text("#toasts"))
        page.screenshot(path=os.path.join(SHOTS, "feed_blocked.png"))
        gold_b = S()["gold"]; st_b = stage()
        ok = rub_clean()
        s = S()
        check("rub-clean with pointer drags -> dirt 0, gold paid", ok and s["gold"] > gold_b, f"stage {st_b}->0, gold {gold_b}->{s['gold']}")
        page.screenshot(path=os.path.join(SHOTS, "after_clean.png"))

        # ---- 7. feed hungry L2 fish, then sell it
        wait_for(lambda: fish(gid)["state"] == "HUNGRY", timeout=10)
        if stage() >= 1: rub_clean()
        f0 = S()["food"]; clean_then_feed()
        check("L2 portion is 2 food", S()["food"] == f0 - 2 and fish(gid)["state"] == "GROWING", f"{f0}->{S()['food']}")
        tool("hand"); click_fish(gid)
        sell_txt = page.inner_text("#p-sell")
        gold_b = S()["gold"]
        page.click("#p-sell"); page.wait_for_timeout(200)
        lvl = 2 if "10" in sell_txt else None
        check("sold L2 Guppy for 10 gold", "Sell for 10 gold" in sell_txt and S()["gold"] == gold_b + 10 and fish(gid) is None, sell_txt)

        # ---- 8. release an L1 for 0 (confirm dialog)
        page.click("#dbg-gold")  # keep gold >= 20 after release so edge case 5 top-up doesn't fire here
        page.click("#btn-shop"); page.click('button[data-buy="guppy"]'); page.click('[data-close="shop"]')
        nid = S()["fish"][-1]["id"]
        page.wait_for_timeout(300)
        tool("hand"); click_fish(nid)
        check("L1 button reads 'Release (0 gold)'", page.inner_text("#p-sell") == "Release (0 gold)", page.inner_text("#p-sell"))
        gold_b = S()["gold"]
        page.click("#p-sell"); page.wait_for_timeout(150)
        check("confirm dialog shown for release", page.locator("#confirm").is_visible())
        page.screenshot(path=os.path.join(SHOTS, "release_confirm.png"))
        page.click("#confirm-yes"); page.wait_for_timeout(150)
        check("released L1 for 0 gold", S()["gold"] == gold_b and fish(nid) is None)

        # ---- 9. a fish left hungry dies
        page.click("#dbg-gold")
        page.click("#btn-shop"); page.click('button[data-buy="guppy"]'); page.click('[data-close="shop"]')
        did = S()["fish"][-1]["id"]
        clean_then_feed()
        check("doomed fish fed once (growing)", fish(did)["state"] == "GROWING")
        wait_for(lambda: (fish(did) or {}).get("state") == "HUNGRY", timeout=10)
        deaths0 = S()["stats"]["deaths"]
        gone = wait_for(lambda: fish(did) is None, timeout=15)  # L1 death timer 360 s = 6 s at x60
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SHOTS, "fish_died.png"))
        check("fish left hungry dies (removed + toast)", gone and S()["stats"]["deaths"] == deaths0 + 1 and "died" in page.inner_text("#toasts"), page.inner_text("#toasts"))

        # ---- 10. full tank screenshot with all 4 species
        for _ in range(3): page.click("#dbg-gold")
        page.click("#btn-shop")
        for sp in ["guppy", "danio", "neon", "platy"]:
            page.click(f'button[data-buy="{sp}"]'); page.wait_for_timeout(80)
        page.click('[data-close="shop"]')
        page.click("#btn-buyfood"); page.click("#btn-buyfood")
        clean_then_feed()
        check("one tap feeds all 4 new fish (1+1+2+2 = 6 food, +4 gold)", all(f["state"] == "GROWING" for f in S()["fish"]))
        page.click('.dbg[data-speed="1"]'); tool("hand")
        page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SHOTS, "tank_with_fish.png"))
        check("fish stay inside the tank", all(0 < f["x"] < 1 and 0 < f["y"] < 1 for f in S()["fish"]))

        # ---- 11. save/reload keeps progress; URL speed overrides saved speed
        page.evaluate("AQ.game.save()")
        before = S()
        page.goto(BASE + "?speed=10"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(200)
        after = S()
        check("reload keeps fish/gold/food", len(after["fish"]) == len(before["fish"]) and after["gold"] >= before["gold"] - 1 and after["food"] == before["food"], f"fish {len(before['fish'])}->{len(after['fish'])} gold {before['gold']}->{after['gold']}")
        check("?speed=10 overrides saved speed (1)", after["speed"] == 10)

        # ---- 12. adult path + starter grant (logic, fast-forwarded via tick in page)
        r = page.evaluate("""() => {
          const G = AQ.game; G.reset(); G.state.gold = 20;
          const f = G.buyFish('guppy');
          const cleanNow = () => { G.state.dirt.points = 0; G.state.dirt.spots = []; G.state.dirt.spawned = 0; };
          cleanNow(); G.feed();
          let guard = 0;
          while (f.level < 4 && guard++ < 10000) { G.tick(1); if (f.state === 'HUNGRY') { cleanNow(); G.feed(); } }
          const adult = f.state; const goldAt4 = G.state.gold;
          const sinceAt4 = f.sinceFed; let hs = 0; while (f.state === 'ADULT' && hs < 5000) { G.tick(1); hs++; }
          const adultHungerAfter = hs; cleanNow(); G.feed();
          const sold = G.sell(f.id);
          // starter grant: no fish, gold < cheapest baby, food left over (Designer's dead-guppy case)
          G.state.gold = 3; G.state.food = 8; G.tick(1);
          const g1 = G.state.gold, used = G.state.starterGrantUsed;
          G.state.gold = 3; G.tick(1);
          return { adult, sold, g1, used, g2: G.state.gold, sinceAt4, adultHungerAfter };
        }""")
        check("guppy reaches Adult (L4) and sells for 90", r["adult"] == "ADULT" and r["sold"] == 90, json.dumps(r))
        check("first adult hunger 16:00 after reaching L4 (Guppy)", r["sinceAt4"] <= 1 and abs(r["adultHungerAfter"] - 960) <= 1, json.dumps(r))
        check("edge case 5: one-time top-up to 20 gold, only once", r["g1"] == 20 and r["used"] and r["g2"] == 3, json.dumps(r))
        # ---- second wipe-out after top-up used -> "Your tank is empty" + Start new tank (Producer ruling)
        page.wait_for_timeout(300)
        over_shown = page.locator("#tankover").is_visible()
        page.click("#btn-newtank"); page.wait_for_timeout(300)
        s2 = S()
        check("2nd wipe-out shows 'Your tank is empty'; Start new tank gives fresh 20g/10 food save", over_shown and not page.locator("#tankover").is_visible() and s2["gold"] == 20 and s2["food"] == 10 and not s2["fish"] and not s2["starterGrantUsed"], json.dumps({"shown": over_shown, "gold": s2["gold"], "food": s2["food"], "fish": len(s2["fish"])}))
        # ---- 13. staged screenshot with mixed levels (levels set via console, visual only)
        page.evaluate("""() => { const G = AQ.game; G.reset(); G.state.gold = 500;
          ['guppy','danio','neon','platy','guppy','danio'].forEach((id, i) => { const f = G.buyFish(id); f.level = [4,3,2,4,1,2][i];
            f.state = f.level === 4 ? 'ADULT' : 'GROWING'; });
          G.state.speed = 1; }""")
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(SHOTS, "tank_mixed_levels_staged.png"))
        page.evaluate("AQ.game.reset(); AQ.game.save()")

        # ---- 13b. dirt load model (Designer v1.2): fish-driven dirt, cap, first-Guppy timing
        d = page.evaluate("""() => {
          const G = AQ.game; const T = G.T; G.reset(); G.state.gold = 1000;
          const f = G.buyFish('guppy');                   // waiting fish counts as L1
          G.tick(719); const waitSt719 = G.dirtStage(); G.tick(2); const waitSt721 = G.dirtStage();
          G.reset(); G.state.gold = 1000; const g = G.buyFish('guppy'); G.feed();
          let t = 0, stAtL2 = null, firstStage1 = null;
          while (t < 1500 && firstStage1 === null) {
            G.tick(1); t++;
            if (g.level >= 2 && stAtL2 === null) stAtL2 = G.dirtStage();
            if (G.dirtStage() >= 1) firstStage1 = t;
            if ((g.state === 'HUNGRY') && G.dirtStage() === 0) G.feed();
          }
          G.reset(); G.state.gold = 10000;
          for (let i = 0; i < 6; i++) { const a = G.buyFish('guppy'); a.level = 4; a.state = 'ADULT'; a.sinceFed = 0; }
          const cap = G.dirtLoadPerMin();
          G.reset(); G.save();
          return { waitSt719, waitSt721, stAtL2, firstStage1, cap, maxLoad: T.dirt.maxLoadPerMin };
        }""")
        check("one waiting baby: dirt still clean at 11:59, stage 1 at 12:00", d["waitSt719"] == 0 and d["waitSt721"] == 1, json.dumps(d))
        check("first Guppy: dirt bar empty through L1, stage 1 at ~9:20 (9-10 min)", d["stAtL2"] == 0 and 540 <= d["firstStage1"] <= 600, json.dumps(d))
        check("full adult tank load capped at maxLoadPerMin (20/min)", d["cap"] == d["maxLoad"] == 20, json.dumps(d))

        # ---- 13c. Art Director look spec (DIRT_AND_FISH_GROWTH.md): per-stage dirt looks, overlap spawning, fish growth look
        a = page.evaluate("""() => {
          const G = AQ.game, T = G.T, V = G.CFG.VISUAL, sz = AQ.size(); G.reset(); G.state.gold = 1000;
          const f = G.buyFish('guppy'); f.level = 4; f.state = 'ADULT';
          let spots = [], counts = [];
          for (let run = 0; run < 40; run++) {
            G.state.dirt.points = 0; G.state.dirt.spots = []; G.state.dirt.spawned = 0;
            for (let i = 0; i < 5; i++) { G.state.dirt.points = T.dirt.stageAtPoints[i] + 0.01; G.tick(0.001); counts.push(G.state.dirt.spots.length === T.dirt.spots[i]); }
            spots = spots.concat(G.state.dirt.spots.map((s) => {
              const o = G.state.dirt.spots.find((x) => x.id === s.over);
              const d = o ? Math.hypot((s.x - o.x) * sz.W, (s.y - o.y) * sz.H) / (o.r * sz.W) : null;
              return { stage: s.stage, r: s.r, over: s.over, d, olderOk: o ? o.id < s.id : true };
            }));
          }
          const looks = V.dirtStages.map((l) => l.look);
          const later = spots.filter((s) => s.stage >= 2), ov = later.filter((s) => s.over != null);
          const k1 = FishArt.growth(1), k4 = FishArt.growth(4);
          // tail pixels of an L1 vs L4 guppy on a transparent canvas: L1 must be clear (low alpha, near-grey)
          const tail = (lv) => { const c = document.createElement('canvas'); c.width = 400; c.height = 300; const x = c.getContext('2d');
            x.translate(260, 150); FishArt.drawFish(x, 'guppy', 200, 0, { level: lv });
            const tl = FishArt.ART.guppy.tailLen * FishArt.growth(lv).tl * 200, cx = 260 - 0.31 * 200 - tl * 0.55;
            const d = x.getImageData(Math.round(cx - 6), 140, 12, 20).data; let al = 0, sat = 0, n = 0;
            for (let i = 0; i < d.length; i += 4) { al += d[i + 3] / 255; if (d[i + 3] > 0) { sat += (Math.max(d[i], d[i+1], d[i+2]) - Math.min(d[i], d[i+1], d[i+2])) / 255; n++; } }
            return { alpha: +(al / (d.length / 4)).toFixed(3), sat: +(sat / Math.max(1, n)).toFixed(3) }; };
          const res = {
            looksDistinct: new Set(looks).size === 5,
            everyStageStyled: spots.every((s) => s.stage >= 1 && s.stage <= 5 && !!looks[s.stage - 1]),
            radiusInRange: spots.every((s) => s.r >= V.dirtStages[s.stage - 1].r[0] - 1e-9 && s.r <= V.dirtStages[s.stage - 1].r[1] + 1e-9),
            stage1Faintest: V.dirtStages.every((l, i) => i === 0 || l.alpha > V.dirtStages[i - 1].alpha) && V.dirtStages[0].alpha === 0.16 && V.dirtStages[4].alpha === 0.34,
            stage5Biggest: V.dirtStages.every((l, i) => i === 4 || l.r[1] <= V.dirtStages[4].r[0]),
            countsOk: counts.every(Boolean), stage1NeverOver: spots.filter((s) => s.stage === 1).every((s) => s.over == null),
            overlapRate: +(ov.length / later.length).toFixed(2),
            overlapDistOk: ov.every((s) => s.d >= 0.4 - 1e-6 && s.d <= 1.6 + 1e-6 && s.olderOk),
            l1Clear: k1.clear && k1.sat === 0.3 && k1.tl === 0.45 && k4.fin === 1 && k4.sat === 1,
            tailL1: tail(1), tailL4: tail(4),
          };
          // AD rulings: danio L1 no stripe (pixel on the stripe line equals plain body, stays tan), neon L2 line 55%,
          // fins keep the species hue unblended (platy L2 dorsal pixel = fin colour at 40% alpha), hair patch 0.28 / strands 0.5
          const px = (sp, lv, fx, fy) => { const c = document.createElement('canvas'); c.width = 400; c.height = 300; const x = c.getContext('2d');
            x.translate(200, 150); FishArt.drawFish(x, sp, 200, 0, { level: lv }); const hh = FishArt.ART[sp].depth * 100;
            const d = x.getImageData(Math.round(200 + fx * 200), Math.round(150 + fy * hh), 1, 1).data; return [d[0], d[1], d[2], +(d[3] / 255).toFixed(2)]; };
          const stripeY = 0.14 * 0.8125, stripeX = -0.015; // danio stripe 2 at mid body
          res.danioL1 = px('danio', 1, stripeX, stripeY); res.danioL1off = px('danio', 1, stripeX, stripeY + 0.12); res.danioL3 = px('danio', 3, stripeX, stripeY);
          res.danioStripes = FishArt.LOOK.danioStripes.map((a) => a.length);
          res.neonL2 = FishArt.LOOK.neonL2LineAlpha;
          res.platyFinL2 = px('platy', 2, -0.04, -1.2); res.platyFinL4 = px('platy', 4, -0.04, -1.2);
          res.hair = [V.dirtStages[3].alpha, V.dirtStages[3].strandAlpha];
          G.reset(); G.save(); return res; }""")
        check("dirt: 5 distinct stage looks, every spot drawn in its own stage's style, radius per stage", a["looksDistinct"] and a["everyStageStyled"] and a["radiusInRange"], json.dumps(a))
        check("dirt: alpha 0.16 -> 0.34 rising, stage 5 biggest, spot counts unchanged", a["stage1Faintest"] and a["stage5Biggest"] and a["countsOk"])
        check("dirt: stage 2+ spots overlap an older spot about half the time, within 0.6 R of its edge", 0.3 <= a["overlapRate"] <= 0.7 and a["overlapDistOk"] and a["stage1NeverOver"], f"rate={a['overlapRate']}")
        dl1, dof, dl3 = a["danioL1"], a["danioL1off"], a["danioL3"]
        check("AD ruling 1: zebra danio L1 has no stripe (stripes from L2)", a["danioStripes"] == [0, 2, 4, 4] and dl1[0] >= dl1[2] and max(abs(dl1[i] - dof[i]) for i in range(3)) < 12 and dl3[2] > dl3[0] + 30, f"L1 {dl1} off {dof} L3 {dl3} stripes {a['danioStripes']}")
        check("AD ruling 6: neon tetra L2 blue line at 55%", a["neonL2"] == 0.55)
        f2, f4 = a["platyFinL2"], a["platyFinL4"]
        check("AD ruling 5: platy L2 fin keeps its own orange hue (not grey-blended), only alpha lower", f2[0] > 230 and f2[0] - f2[2] > 150 and abs(f2[1] - f4[1]) < 25 and 0.2 < f2[3] < 0.5 and f4[3] > 0.75, f"L2 {f2} L4 {f4}")
        check("AD ruling 3: hair-algae patch 0.28, strands 0.5", a["hair"] == [0.28, 0.5], str(a["hair"]))
        check("fish: L1 tail clear/uncoloured, L4 tail full colour (growth table)", a["l1Clear"] and a["tailL1"]["alpha"] < 0.35 and a["tailL1"]["sat"] < 0.15 and a["tailL4"]["alpha"] > 0.6 and a["tailL4"]["sat"] > 0.4, f"L1 {a['tailL1']} L4 {a['tailL4']}")

        # ---- 14. touch: rub-clean with real touch drags (CDP touch events, phone emulation)
        tctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
        tp = tctx.new_page()
        tp.on("pageerror", lambda e: errors.append(f"pageerror(touch): {e}"))
        tp.goto(BASE + "?speed=1"); tp.wait_for_function("window.AQ && window.AQ.game")
        tp.evaluate("() => { const G = AQ.game; G.reset(); G.buyFish('guppy'); G.state.dirt.points = 23.99; G.tick(1); }")
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
                    pts += [(sp["x"] - sp["r"], sp["y"] + lift), (sp["x"] + sp["r"], sp["y"] + lift + 3)]  # finger below; sponge cleans above it
                x0, y0 = pts[0]
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": tb["x"] + x0, "y": tb["y"] + y0}]})
                for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                    for t in range(1, 7):
                        x = ax + (bx - ax) * t / 6; y = ay + (by - ay) * t / 6
                        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": tb["x"] + x, "y": tb["y"] + y}]})
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        check("touch drags rub the tank clean (phone emulation)", st0 >= 1 and tp.evaluate("AQ.game.dirtStage()") == 0 and tp.evaluate("AQ.game.state.gold") == gold0 + tj["dirt"]["cleanGold"][0],
              f"stage {st0}->{tp.evaluate('AQ.game.dirtStage()')}")
        tp.evaluate("AQ.game.reset(); AQ.game.save()")
        tctx.close()

        check("no console errors / page errors", not errors, "; ".join(errors[:5]))
        browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
