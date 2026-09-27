"""Headless end-to-end check of the Aquarium prototype (Designer v2 "slow game").

Run (server must be up on 8766):
  /workspace/tools/venv-aq/bin/python /workspace/aquarium/tests/verify.py
Timing rules are checked by stepping the game in the page (AQ.game.tick), so hours-long timers run in
milliseconds; UI checks use real mouse/touch input. Writes a few screenshots to ../screenshots/
(the art/look screenshots come from tests/art_shots.py). Resets the save at the end.
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

# JS helpers injected into every evaluate that needs them
JS = """const G = AQ.game, T = G.T, H = 3600;
  const clean = () => { const d = G.state.dirt; d.t = 0; d.spots = []; d.spawned = 0; d.grime5 = 0; };
  const toStage = (n) => { clean(); for (let i = 0; i < n; i++) { G.state.dirt.t = T.dirt.stageAtSec[i] - 0.5; G.tick(1); } };
  const feedFull = (f) => { let r, n = 0; do { r = G.feedTap(f.x, f.y); n++; } while (r.ok && !r.full && n < 50); return n; };
  const rubAll = (frac) => { // rub every spot by frac of its starting grime (1 = clean); tank 400 x 560 px
    let res = null; for (const s of G.state.dirt.spots.slice()) { const len = s.grime0 * frac, dx = len / 400 / 2;
      const r = G.rub(s.x - dx, s.y, s.x + dx, s.y, 400, 560, 1); if (r.cleaned) res = r; } return res; };
  const halfGrime = () => { for (const s of G.state.dirt.spots) s.grime = s.grime0 / 2; }; // exact half (rub segments also hit overlapping spots)
"""

def main():
    errors = []
    tj = json.load(open(TUNING))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 420, "height": 860}, device_scale_factor=2)
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
        check("start state: empty tank, start gold/food, tank level 1", s["fish"] == [] and s["gold"] == tj["startGold"] and s["food"] == tj["startFood"] and page.evaluate("AQ.game.tankInfo().level") == 1)
        boot("?speed=3600")
        g0 = page.evaluate("AQ.game.state.gameTime"); page.wait_for_timeout(1000); g1 = page.evaluate("AQ.game.state.gameTime")
        check("hidden ?speed=3600 works (about 1 game hour per real second)", S()["speed"] == 3600 and 1800 < g1 - g0 < 7200, f"speed={S()['speed']} dGame={g1 - g0:.0f}s")
        boot("?speed=1")

        d = ev("""const out = {}; const at = T.dirt.stageAtSec;
          const run = (setup) => { G.reset(); G.state.gold = 1000; G.state.tank.xp = 5000; setup(); const rows = []; let t = 0;
            for (let i = 0; i < at.length; i++) { G.tick(at[i] - 1 - t); const before = G.dirtStage(); G.tick(2); t = at[i] + 1;
              rows.push([before, G.dirtStage(), G.state.dirt.spots.length]); } return rows; };
          out.empty = run(() => {});
          out.living = run(() => { const f = G.buyFish('guppy'); feedFull(f); });
          out.dead = run(() => { const f = G.buyFish('guppy'); f.state = 'DEAD'; f.diedAt = 0; });
          out.waiting = run(() => { G.buyFish('platy'); });
          out.hours = at.map((s) => s / H); return out;""")
        exp = [[i, i + 1, tj["dirt"]["spots"][i]] for i in range(5)]
        check("dirt stages at 3/6/12/24/48 h with 2-6 spots (empty tank gets dirty too)", d["hours"] == [3, 6, 12, 24, 48] and d["empty"] == exp and tj["dirt"]["runsWithEmptyTank"] is True, json.dumps(d["empty"]))
        check("dirt timer ignores the fish: empty / living / dead / waiting tanks give identical stages", d["living"] == d["dead"] == d["waiting"] == d["empty"], json.dumps({k: d[k] for k in ("living", "dead", "waiting")}))

        c = ev("""const out = []; for (let n = 1; n <= 5; n++) { G.reset(); G.state.gold = 50; toStage(n); const g0 = G.state.gold, x0 = G.state.tank.xp;
            const r = rubAll(1.01); out.push({ n, gold: G.state.gold - g0, xp: G.state.tank.xp - x0, cleaned: !!(r && r.cleaned), t: G.state.dirt.t, st: G.dirtStage() }); }
          G.reset(); G.state.gold = 50; toStage(3); const g0 = G.state.gold; rubAll(0.5); const partial = G.state.gold - g0;
          return { out, partial };""")
        check("every full clean pays 10 gold + 5 XP at any stage and restarts the dirt clock", all(r["gold"] == 10 and r["xp"] == 5 and r["cleaned"] and r["t"] == 0 and r["st"] == 0 for r in c["out"]) and tj["dirt"]["cleanGold"] == 10, json.dumps(c["out"]))
        check("partial rubbing pays nothing", c["partial"] == 0)

        # ================================================================ B. feeding / growth / hunger / death
        f = ev("""const sp = (id) => [1, 2, 3, 4].map((lv) => G.tapsFor(G.portion(G.SPECIES[id], lv)));
          const out = { guppyTaps: sp('guppy'), platyTaps: sp('platy'), platyFood: [1, 2, 3, 4].map((lv) => G.portion(G.SPECIES.platy, lv)) };
          // growth: feed the moment it gets hungry -> adult after sum(growSec)
          G.reset(); G.state.gold = 1000; let a = G.buyFish('guppy'); feedFull(a); let t = 0, hungerAt = null;
          while (a.level < 4 && t < 100000) { G.tick(1); t++; if (hungerAt === null && a.state === 'HUNGRY') hungerAt = t;
            if (a.state === 'HUNGRY') { clean(); feedFull(a); } }
          out.adultAt = t; out.firstHunger = hungerAt;
          // hunger at half of L1, death exactly deathSec after hunger (fed once, never again)
          G.reset(); G.state.gold = 1000; a = G.buyFish('guppy'); feedFull(a); t = 0; let h = null, dead = null;
          while (!dead && t < 200000) { G.tick(1); t++; if (h === null && a.state === 'HUNGRY') { h = t; out.progressAtHunger = a.progress; } if (a.state === 'DEAD') dead = t; }
          out.hungry = h; out.deathAfter = dead - h; out.deadState = a.state; out.deadStays = G.state.fish.includes(a);
          // 8 h night right after a feed never kills (L1 baby and an adult platy)
          G.reset(); G.state.gold = 1000; G.state.tank.xp = 5000; a = G.buyFish('guppy'); feedFull(a);
          const pl = G.buyFish('platy'); pl.level = 4; pl.state = 'ADULT_HUNGRY'; pl.deathLeft = T.deathSec; clean(); feedFull(pl);
          G.tick(8 * H); out.night = [a.state, pl.state];
          return out;""")
        check("taps per portion: Guppy 1-4, Platy 2-8 (1 food per tap)", f["guppyTaps"] == [1, 2, 3, 4] and f["platyTaps"] == [2, 4, 6, 8] and tj["foodPerTap"] == 1, json.dumps(f))
        gsum = sum(next(s for s in tj["species"] if s["id"] == "guppy")["growSec"])
        check("Guppy reaches adult in 7 h with prompt feeding", f["adultAt"] == gsum == 7 * 3600, f"adultAt={f['adultAt']} sum={gsum}")
        check("hungry at 50% of the level (Guppy L1 at 30 min)", f["hungry"] == 1800 and abs(f["progressAtHunger"] - 1800) < 1e-6 and tj["hungerPoint"] == 0.5, f"hungry at {f['hungry']}s")
        check("death exactly 16 h after getting hungry; the dead fish stays in the tank", f["deathAfter"] == tj["deathSec"] == 57600 and f["deadState"] == "DEAD" and f["deadStays"], f"deathAfter={f['deathAfter']}")
        check("an 8 h night right after a feed kills nobody", "DEAD" not in f["night"], str(f["night"]))

        # real taps: 1 food per tap, fed meter, +1 gold when full (Platy needs 2 taps at L1)
        pid = ev("G.reset(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; const f = G.buyFish('platy'); AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(200); tool("food")
        pos = page.evaluate(f"AQ.fishScreen({pid})")
        s0 = S(); tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s1 = S()
        tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s2 = S()
        f1 = next(x for x in s1["fish"] if x["id"] == pid); f2 = next(x for x in s2["fish"] if x["id"] == pid)
        check("real Food taps: 1 food per tap, Platy fed 1/2 then full -> growing, +1 gold",
              s1["food"] == s0["food"] - 1 and f1["fed"] == 1 and f1["state"] == "WAITING" and s1["gold"] == s0["gold"]
              and s2["food"] == s0["food"] - 2 and f2["state"] == "GROWING" and s2["gold"] == s0["gold"] + 1,
              f"food {s0['food']}->{s1['food']}->{s2['food']} gold {s0['gold']}->{s2['gold']} state {f2['state']}")
        clear_toasts(); tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(150)
        check("tap with nobody hungry: 'Nobody's hungry', no food spent", S()["food"] == s2["food"] and "Nobody's hungry" in page.inner_text("#toasts"), page.inner_text("#toasts"))

        # hungry panel text
        gid = ev("G.reset(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); feedFull(f); G.tick(1800); AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(2500); clear_toasts(); tool("hand"); click_fish(gid); page.wait_for_timeout(250)
        ht, gt = page.inner_text("#p-hunger"), page.inner_text("#p-growth")
        check("panel: 'Hungry! 0/1 fed · Growth paused · dies in 16h 00m'", any(ht.startswith("Hungry! 0/1 fed · Growth paused · dies in " + t) for t in ("16h 00m", "15h 59m")) and "Growth paused" in gt, f"{ht} | {gt}")
        page.screenshot(path=os.path.join(SHOTS, "panel_hungry.png"))
        page.keyboard.press("Escape")

        # ================================================================ C. tank XP / shop gating
        x = ev("""G.reset(); G.state.gold = 1000; const a = G.buyFish('guppy'); feedFull(a); let n = 0;
          while (a.level < 2 && n++ < 10000) { G.tick(1); if (a.state === 'HUNGRY') { clean(); feedFull(a); } }
          const afterLvl = G.state.tank.xp, gold2 = T.species.find((s) => s.id === 'guppy').levelUpGold[0];
          G.sell(a.id); const afterSell = G.state.tank.xp;
          return { afterLvl, gold2, afterSell, src: G.CFG.XP_SOURCE, lv: [0, 59, 60, 399, 400, 1200, 3000].map(G.tankLevelFor) };""")
        check("tank XP: level-up XP = level-up gold; selling gives 0 XP", x["afterLvl"] == x["gold2"] and x["afterSell"] == x["afterLvl"] and x["src"] == "designer", json.dumps(x))
        check("tank levels at 60 / 400 / 1200 / 3000 XP", x["lv"] == [1, 1, 2, 2, 3, 4, 5], str(x["lv"]))
        ev("G.reset(); G.state.gold = 1000; G.state.tank.xp = 55; G.state.speed = 1;")
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

        # ================================================================ D. offline catch-up (real reload) + dead fish
        ids = ev("""G.reset(); G.state.speed = 1; G.state.gold = 100; const a = G.buyFish('guppy'); feedFull(a); const b = G.buyFish('guppy');
          G.save(); G.save = () => {}; // keep this page's periodic/pagehide save from overwriting the edited timestamp
          const k = G.CFG.VISUAL.saveKey, d = JSON.parse(localStorage.getItem(k)); d.lastSeen -= 49 * H * 1000; localStorage.setItem(k, JSON.stringify(d));
          return { a: a.id, b: b.id, t0: G.state.gameTime };""")
        boot(); page.wait_for_timeout(600)
        s = S(); a = fish(ids["a"]); b = fish(ids["b"])
        check("offline 49 h: dirt stage 5, fed guppy died at 16h30 and stays DEAD, unfed one still waiting",
              stage() == 5 and a and a["state"] == "DEAD" and abs(a["diedAt"] - ids["t0"] - 59400) <= 5 and b["state"] == "WAITING",
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
        did = ev("G.reset(); G.state.gold = 100; const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, 0.5, 0.6); f.state = 'HUNGRY'; f.deathLeft = 0.5; G.tick(1); G.state.speed = 20; return f.id;")
        page.wait_for_timeout(300); y_mid = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y")
        page.wait_for_timeout(1700); y_top = page.evaluate(f"AQ.game.state.fish.find((f) => f.id === {did}).y")
        check("a fish that just died rises to the top band over ~20 game s", y_mid > 0.2 and 0.05 <= y_top <= 0.11, f"y after ~6 game s {y_mid:.2f}, after ~40 {y_top:.3f}")
        sg = ev("""G.state.speed = 1; const g = G.state.gold; G.state.gold = 0; G.tick(1);
          return { gold: G.state.gold, used: G.state.starterGrantUsed, living: G.living(), n: G.state.fish.length };""")
        check("starter grant counts living fish only (dead fish in tank, 0 gold -> top-up to 20)", sg["gold"] == 20 and sg["used"] and sg["living"] == 0 and sg["n"] == 1, json.dumps(sg))
        ev("G.state.gold = 3; G.tick(1);"); page.wait_for_timeout(300)
        over = page.locator("#tankover").is_visible()
        page.click("#btn-newtank"); page.wait_for_timeout(300); s2 = S()
        check("2nd wipe-out (only a dead fish left) shows 'Your tank is empty'; Start new tank gives a fresh save", over and s2["gold"] == 20 and s2["food"] == 10 and not s2["fish"] and not s2["starterGrantUsed"], json.dumps({"shown": over, "gold": s2["gold"], "fish": len(s2["fish"])}))

        # ================================================================ E. UI: dirty feed, rub clean, sell/release, reload
        gid = ev("G.reset(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.5, 0.45); toStage(3); return f.id;")
        page.wait_for_timeout(200); tool("food"); clear_toasts(); food_b = S()["food"]
        tank_click(box()["width"] * 0.5, box()["height"] * 0.3); page.wait_for_timeout(200)
        n_toasts = page.locator("#toasts > *").count(); hint_vis = page.locator("#hint").is_visible() and page.inner_text("#hint").strip() != ""
        check("dirty tank: feeding blocked with ONE message by the dirt bar (no toast, no hint)",
              S()["food"] == food_b and page.locator("#dirt-callout").is_visible() and "Clean the tank first" in page.inner_text("#dirt-callout") and n_toasts == 0 and not hint_vis,
              f"toasts={n_toasts} hint={hint_vis}")
        gold_b, xp_b = S()["gold"], S()["tank"]["xp"]
        ok = rub_clean(); s = S()
        check("sponge mouse rub cleans stage 3: +10 gold, +5 XP", ok and s["gold"] == gold_b + 10 and s["tank"]["xp"] == xp_b + 5, f"gold {gold_b}->{s['gold']} xp {xp_b}->{s['tank']['xp']}")
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
        ev("G.reset(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; ['guppy','danio','neon','platy'].forEach((id) => { const f = G.buyFish(id); feedFull(f); });")
        tool("hand"); page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SHOTS, "tank_with_fish.png"))
        check("fish stay inside the tank", all(0 < f_["x"] < 1 and 0 < f_["y"] < 1 for f_ in S()["fish"]))
        page.evaluate("AQ.game.save()"); before = S()
        boot("?speed=5"); after = S()
        check("reload keeps fish/gold/food/XP; ?speed=5 applied", len(after["fish"]) == 4 and after["gold"] == before["gold"] and after["food"] == before["food"] and after["tank"]["xp"] == before["tank"]["xp"] and after["speed"] == 5,
              f"fish {len(after['fish'])} gold {before['gold']}->{after['gold']} speed {after['speed']}")
        ev("G.reset(); G.state.gold = 500; G.state.tank.xp = 1200; ['guppy','danio','neon','platy','guppy','danio'].forEach((id, i) => { const f = G.buyFish(id); f.level = [4,3,2,4,1,2][i]; f.state = f.level === 4 ? 'ADULT' : 'GROWING'; }); G.state.speed = 1;")
        page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SHOTS, "tank_mixed_levels_staged.png"))

        # ================================================================ F. balance
        bc = page.evaluate("AQ.game.balanceChecks()")
        check("balance: selling at L4 beats L3 per hour (all species)", bc["sellOk"], json.dumps(bc["sell"]))
        check("balance: clean often pays most: 80/40/20/10/5 gold per day, 16x", bc["cleanOk"] and bc["cleanPerDay"] == [80, 40, 20, 10, 5] and bc["cleanRatio"] == 16, str(bc["cleanPerDay"]))

        # ================================================================ G. Art Director look spec (v2 dirt + fish growth)
        a = ev("""const V = G.CFG.VISUAL, sz = AQ.size(); G.reset(); G.state.gold = 1000;
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
          G.reset(); return res;""")
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
        check("AD ruling 6b: neon tetra L2 blue line at 70%", a["neonL2"] == 0.70)
        f2, f4 = a["platyFinL2"], a["platyFinL4"]
        check("AD ruling 5b: platy L2 fin keeps its own orange hue at ~65% opacity", f2[0] > 230 and f2[0] - f2[2] > 150 and abs(f2[1] - f4[1]) < 25 and 0.58 < f2[3] < 0.72 and f4[3] > 0.75, f"L2 {f2} L4 {f4}")
        check("AD ruling 3 + v2: hair-algae patch 0.40, strands 0.5", a["hair"] == [0.40, 0.5], str(a["hair"]))
        check("fish: L1 tail clear/uncoloured, L4 tail full colour (growth table)", a["l1Clear"] and a["tailL1"]["alpha"] < 0.35 and a["tailL1"]["sat"] < 0.15 and a["tailL4"]["alpha"] > 0.6 and a["tailL4"]["sat"] > 0.4, f"L1 {a['tailL1']} L4 {a['tailL4']}")

        # stage 5 film: only at stage 5, fades with the grime, gone after the last spot, guard <= 0.6
        ev("G.reset(); G.state.gold = 1000; G.state.speed = 1; toStage(4);"); page.wait_for_timeout(200)
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
        tp.evaluate("() => { const G = AQ.game; G.reset(); G.buyFish('guppy'); G.state.dirt.t = G.T.dirt.stageAtSec[0] - 0.5; G.tick(1); }")
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
        check("touch drags rub the tank clean (phone emulation), +10 gold", st0 >= 1 and tp.evaluate("AQ.game.dirtStage()") == 0 and tp.evaluate("AQ.game.state.gold") == gold0 + tj["dirt"]["cleanGold"],
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
