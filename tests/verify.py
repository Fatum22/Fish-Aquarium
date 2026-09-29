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
# v6: config.js TUNING must equal the live design/tuning.json verbatim (tools/sync_tuning.py default).
TUNING = os.environ.get("AQ_TUNING", "/workspace/studio/briefs/aquarium/design/tuning.json")
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


def merged_tuning():
    """what config.js TUNING must equal: the live design/tuning.json (v6) verbatim, or AQ_TUNING if set"""
    return json.load(open(TUNING))

def ver_at_least(tj, v):
    """tuning.json version >= v (e.g. '6.8' >= '6.5'): a rule introduced at v stays checked in every later approved version
    unless that version changes the numbers (the number checks themselves still read tuning.json)."""
    return tuple(int(x) for x in str(tj["version"]).split(".")) >= tuple(int(x) for x in v.split("."))

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
    tj = merged_tuning()
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
        def open_debug(pw="123456"):
            """Unlock the debug panel through the password popup (Maksims 2026-09-28)."""
            if page.evaluate("AQ.debugOpen()"): return True
            page.click("#dbg-toggle"); page.wait_for_timeout(80)
            page.fill("#dbg-pass-input", pw); page.click("#dbg-pass-yes"); page.wait_for_timeout(80)
            return page.evaluate("AQ.debugOpen()")
        def close_debug():
            if page.evaluate("AQ.debugOpen()"): page.click("#dbg-toggle"); page.wait_for_timeout(60)
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
        check("config.js TUNING == Designer tuning.json v6 (verbatim)", page.evaluate("AQ.game.T") == tj)
        s = S()
        check("page opens at x1 (debugDefaultSpeed)", s["speed"] == 1 == tj["debugDefaultSpeed"], f"speed={s['speed']}")
        btns = page.locator("#speed-btns .dbg").all_inner_texts()
        check("debug speed buttons are exactly x1 x5 x10 x15 x20", btns == ["×1", "×5", "×10", "×15", "×20"] and tj["debugSpeeds"] == [1, 5, 10, 15, 20], str(btns))
        # Maksims 2026-09-28: DEBUG is a password toggle; buttons start hidden; wrong password / cancel stay closed; right password opens; one tap closes
        gate0 = page.evaluate("""(() => { const d = document.getElementById('debug'), p = document.getElementById('dbg-panel'), m = document.getElementById('dbg-pass');
          const vis = (el) => !!(el && el.checkVisibility({ visibilityProperty: true, contentVisibilityAuto: true }));
          return { open: AQ.debugOpen(), cls: d.classList.contains('open'), pressed: document.getElementById('dbg-toggle').getAttribute('aria-pressed'),
                   panel: vis(p), gold: vis(document.getElementById('dbg-gold')), xp: vis(document.getElementById('dbg-xp')), reset: vis(document.getElementById('dbg-reset')),
                   speeds: [...document.querySelectorAll('#speed-btns .dbg')].map((b) => vis(b)), modal: vis(m), clock: vis(document.getElementById('dbg-clock')) }; })()""")
        check("debug starts closed: DEBUG toggle visible, speed/+100g/+50 XP/Reset hidden, clock still shown, no password modal, not in save",
              not gate0["open"] and not gate0["cls"] and gate0["pressed"] == "false" and not gate0["panel"] and not gate0["gold"] and not gate0["xp"] and not gate0["reset"]
              and gate0["speeds"] == [False] * 5 and not gate0["modal"] and gate0["clock"], json.dumps(gate0))
        page.click("#dbg-toggle"); page.wait_for_timeout(100)
        box_pw = page.evaluate("""(() => { const b = document.querySelector('#dbg-pass .modal-box').getBoundingClientRect(), k = document.getElementById('tank-wrap').getBoundingClientRect();
          return { w: b.width, h: b.height, cx: (b.left + b.right) / 2 - (k.left + k.right) / 2, cy: (b.top + b.bottom) / 2 - (k.top + k.bottom) / 2,
                   title: document.getElementById('dbg-pass-title').textContent, yes: document.getElementById('dbg-pass-yes').textContent, no: document.getElementById('dbg-pass-no').textContent,
                   tankW: k.width, tankH: k.height }; })()""")
        page.screenshot(path=shot("debug_password"))
        check("tapping DEBUG opens a centred password popup (fits the tank: <= 280 / 340 wide) matching the confirm style: 'Developer password', Cancel + Unlock",
              not page.evaluate("AQ.debugOpen()") and page.locator("#dbg-pass").is_visible() and box_pw["title"] == "Developer password" and box_pw["yes"] == "Unlock" and box_pw["no"] == "Cancel"
              and abs(box_pw["cx"]) < 3 and abs(box_pw["cy"]) < 3 and box_pw["w"] <= (340 if LARGE else 280) + 1 and box_pw["h"] < box_pw["tankH"] - 8, json.dumps(box_pw))
        page.fill("#dbg-pass-input", "000000"); page.click("#dbg-pass-yes"); page.wait_for_timeout(80)
        wrong = page.evaluate("""(() => ({ open: AQ.debugOpen(), err: !document.getElementById('dbg-pass-err').hidden, modal: !document.getElementById('dbg-pass').hidden,
          panel: document.getElementById('debug').classList.contains('open') }))()""")
        check("wrong password: stays closed, shows 'Wrong password', modal still up, debug buttons still hidden",
              not wrong["open"] and wrong["err"] and wrong["modal"] and not wrong["panel"] and page.inner_text("#dbg-pass-err") == "Wrong password", json.dumps(wrong))
        page.click("#dbg-pass-no"); page.wait_for_timeout(80)
        cancelled = page.evaluate("({ open: AQ.debugOpen(), modal: !document.getElementById('dbg-pass').hidden, panel: document.getElementById('debug').classList.contains('open') })")
        check("Cancel on the password popup leaves debug closed (no buttons)", not cancelled["open"] and not cancelled["modal"] and not cancelled["panel"], json.dumps(cancelled))
        page.click("#dbg-toggle"); page.wait_for_timeout(80)
        page.fill("#dbg-pass-input", "123456"); page.click("#dbg-pass-yes"); page.wait_for_timeout(100)
        unlocked = page.evaluate("""(() => { const vis = (id) => document.getElementById(id).checkVisibility({ visibilityProperty: true });
          return { open: AQ.debugOpen(), cls: document.getElementById('debug').classList.contains('open'), pressed: document.getElementById('dbg-toggle').getAttribute('aria-pressed'),
                   modal: !document.getElementById('dbg-pass').hidden, gold: vis('dbg-gold'), xp: vis('dbg-xp'), reset: vis('dbg-reset'),
                   speeds: [...document.querySelectorAll('#speed-btns .dbg')].map((b) => b.checkVisibility({ visibilityProperty: true })) }; })()""")
        page.locator("#debug").screenshot(path=shot("debug_row_open"))
        check("password 123456 unlocks: DEBUG pressed, modal gone, speed/+100g/+50 XP/Reset visible",
              unlocked["open"] and unlocked["cls"] and unlocked["pressed"] == "true" and not unlocked["modal"] and unlocked["gold"] and unlocked["xp"] and unlocked["reset"]
              and unlocked["speeds"] == [True] * 5, json.dumps(unlocked))
        page.click("#dbg-toggle"); page.wait_for_timeout(80)
        closed = page.evaluate("({ open: AQ.debugOpen(), cls: document.getElementById('debug').classList.contains('open'), gold: document.getElementById('dbg-gold').checkVisibility({ visibilityProperty: true }), modal: !document.getElementById('dbg-pass').hidden })")
        check("one tap on DEBUG closes the panel with no password prompt", not closed["open"] and not closed["cls"] and not closed["gold"] and not closed["modal"], json.dumps(closed))
        # reopen for any later checks that need the buttons (and prove every open asks again)
        page.click("#dbg-toggle"); page.wait_for_timeout(60)
        again = page.locator("#dbg-pass").is_visible()
        page.fill("#dbg-pass-input", "123456"); page.click("#dbg-pass-yes"); page.wait_for_timeout(80)
        check("opening again always asks for the password (not remembered across closes)", again and page.evaluate("AQ.debugOpen()"), f"asked={again}")
        page.evaluate("AQ.game.save()"); boot("?speed=1")
        check("reload always starts with debug closed (open state is not saved)", not page.evaluate("AQ.debugOpen()") and not page.locator("#dbg-gold").is_visible())
        nt = page.evaluate("({ st: AQ.game.dirtStage(), spots: AQ.game.state.dirt.spots.map((s) => s.stage), next: AQ.game.dirtNextIn(), fc: AQ.game.state.firstCleanPending, lvl: AQ.game.tankInfo().level })")
        check("v6.1 new tank: empty, 0 gold / 0 food / 0 diamonds, dirt stage 3 (clock at newTank.dirtClockStartSec 6 h, stage 4 due at 12 h, i.e. 6 h away) with its spots, first-clean reward armed, tank Lv1",
              s["fish"] == [] and s["gold"] == tj["startGold"] == 0 and s["food"] == tj["startFood"] == 0 and s["diamonds"] == tj["startDiamonds"] == 0 and nt["st"] == 3
              and tj["newTank"]["dirtClockStartSec"] == 21600 and len(nt["spots"]) == tj["dirt"]["spots"][2] and 6 * 3600 - 60 < nt["next"] <= 6 * 3600 and nt["fc"] and nt["lvl"] == 1, json.dumps(nt))
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
        check("v6.1 dirt stages at 1.5/3/6/12/24 h with dirt.spots spots per stage (empty tank gets dirty too)", d["hours"] == [1.5, 3, 6, 12, 24] and tj["dirt"]["stageAtSec"] == [5400, 10800, 21600, 43200, 86400] and d["empty"] == exp and tj["dirt"]["runsWithEmptyTank"] is True, json.dumps(d["empty"]))
        check("dirt timer ignores the fish: empty / living / dead / waiting tanks give identical stages", d["living"] == d["dead"] == d["waiting"] == d["empty"], json.dumps({k: d[k] for k in ("living", "dead", "waiting")}))

        c = ev("""const out = []; for (let n = 1; n <= 5; n++) { fresh(); G.state.gold = 50; toStage(n); const g0 = G.state.gold, x0 = G.state.tank.xp;
            const r = rubAll(1.01); out.push({ n, gold: G.state.gold - g0, xp: G.state.tank.xp - x0, cleaned: !!(r && r.cleaned), t: G.state.dirt.t, st: G.dirtStage() }); }
          fresh(); G.state.gold = 50; toStage(3); const g0 = G.state.gold; rubAll(0.5); const partial = G.state.gold - g0;
          return { out, partial };""")
        cg = tj["dirt"]["cleanGold"]
        check("v6.5 full clean pays cleanGold by stage (4/7/12/20/32) + 5 XP and restarts the dirt clock (first clean already used)", cg == [4, 7, 12, 20, 32] and ver_at_least(tj, "6.5") and all(r["gold"] == cg[r["n"] - 1] and r["xp"] == 5 and r["cleaned"] and r["t"] == 0 and r["st"] == 0 for r in c["out"]), json.dumps(c["out"]))
        c2 = ev("""fresh(); G.state.gold = 50; toStage(3); const g0 = G.state.gold; rubAll(0.3); const partial = G.state.gold - g0, rs = G.state.dirt.rubStage;
          G.state.dirt.t = T.dirt.stageAtSec[3] - 0.5; G.tick(1); const midStage = G.dirtStage(), spots = G.state.dirt.spots.length;
          const r = rubAll(1.01); return { partial, rs, midStage, spots, gold: G.state.gold - g0, payStage: r && r.stage, stageNow: r && r.stageNow, rsAfter: G.state.dirt.rubStage };""")
        check("clean pays by the stage when the rub STARTED (start at 3, tank reaches 4 mid-rub -> pays cleanGold[2] = 12, not 20)",
              c2["partial"] == 0 and c2["rs"] == 3 and c2["midStage"] == 4 and c2["spots"] >= 1 and c2["gold"] == cg[2] == 12 and c2["payStage"] == 3 and c2["stageNow"] == 4 and c2["rsAfter"] == 0, json.dumps(c2))
        check("partial rubbing pays nothing", c["partial"] == 0)
        fc = ev("""G.reset(); G.tick(1); const g0 = G.state.gold, f0 = G.state.food, x0 = G.state.tank.xp, grant0 = G.state.starterGrantUsed;
          const r = rubAll(1.01); const first = { gold: G.state.gold - g0, food: G.state.food - f0, xp: G.state.tank.xp - x0, pending: G.state.firstCleanPending, t: G.state.dirt.t, grant0 };
          toStage(3); const g1 = G.state.gold, f1 = G.state.food; rubAll(1.01); return { first, second: { gold: G.state.gold - g1, food: G.state.food - f1 } };""")
        check("first clean of a new tank pays 20 gold + 50 food + 5 XP instead of the stage pay; no starter grant before it; the next clean pays the stage pay again",
              fc["first"] == {"gold": 20, "food": 50, "xp": 5, "pending": False, "t": 0, "grant0": False} and fc["second"] == {"gold": cg[2], "food": 0}
              and tj["newTank"]["firstCleanReward"] == {"gold": 20, "food": 50, "replacesStagePay": True}, json.dumps(fc))

        # ================================================================ B. feeding / growth / hunger / death
        f = ev("""const out = { meal: T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.portion(sp, lv))), split: T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.mealsOf(sp, lv))) };
          // growth (v6): bought baby grows at once; feed the moment it gets hungry -> adult after sum(growSec); L4 not hungry
          fresh(); G.state.gold = 1000; let a = G.buyFish('guppy'); let t = 0, hungerAt = null; const hung = [];
          const a0 = a; G.on((ty, d) => { if (ty === 'hungry' && d.fish === a0) hung.push([t + 1, a0.level, d.end ? 'end' : 'mid', a0.progress / G.growSec(G.SPECIES.guppy, a0.level)]); });
          out.bought = { state: a.state, deathLeft: a.deathLeft, progress: a.progress };
          while (a.level < 4 && t < 100000) { G.tick(1); t++; if (hungerAt === null && a.state === 'HUNGRY') hungerAt = t;
            if (a.state === 'HUNGRY') { clean(); feedFull(a); } }
          out.adultAt = t; out.firstHunger = hungerAt; out.hung = hung; out.adultState = a.state; out.adultDeath = a.deathLeft; out.adultHunger = G.adultHungerSec(G.SPECIES.guppy);
          // a new L1 fish that is never fed: grows to mid hunger, then dies on the L1 death timer (no start meal / WAITING)
          fresh(); const w = G.buyFish('guppy'); const w0 = [w.state, w.deathLeft]; G.tick(24 * H); out.waiting = { atBuy: w0, after24h: [w.state, w.deathLeft] };
          // death timer by rarity+level (v6 3a): common L1-L4 = deathSecByRarity.common; rare longer
          out.byLevel = [1, 2, 3, 4].map((lv) => { fresh(); G.state.tank.xp = 5000; const f = G.buyFish('guppy'); f.level = lv;
            f.state = lv === 4 ? 'ADULT' : 'GROWING'; f.progress = 0; f.hungerDone = false; f.sinceFed = 0; let t = 0, h = null, d = null, dl = null;
            while (d === null && t < 40 * H) { G.tick(1); t++; if (h === null && G.needsFood(f)) { h = t; dl = f.deathLeft; } if (f.state === 'DEAD') d = t; }
            return { lv, hungryAt: h, deathLeftAtHunger: dl, diesAfter: d - h }; });
          out.rareDeath = (() => { fresh(); G.state.tank.xp = 5000; G.state.gold = 1000; const f = G.buyFish('ram'); f.level = 4; f.state = 'ADULT_HUNGRY'; f.fed = 0; f.deathLeft = G.deathSecFor(G.SPECIES.ram, 4); let t = 0; while (f.state !== 'DEAD' && t < 40 * H) { G.tick(1); t++; } return { diesAfter: t, expected: G.deathSecFor(G.SPECIES.ram, 4) }; })();
          // v6.3: at 100% of L1 the fish is hungry for its end meal and stays L1 (L1 death timer) until fed; the end meal levels
          // it up to L2, GROWING from 0% and NOT hungry (no death timer), next hunger at 50% of L2
          fresh(); const u = G.buyFish('guppy'); u.hungerDone = true; u.progress = G.growSec(G.SPECIES.guppy, 1) - 0.5; G.tick(1);
          const up = { atEnd: { level: u.level, state: u.state, endMeal: !!u.endMeal, deathLeft: u.deathLeft, progress: u.progress } };
          G.tick(600); up.after10m = { level: u.level, state: u.state, progress: u.progress, info: G.fishInfo(u).level };
          const r1 = G.feedTap(u.x, u.y);
          up.afterEnd = { full: r1.full, levelUp: r1.levelUp, level: u.level, state: u.state, deathLeft: u.deathLeft, progress: u.progress, needs: G.needsFood(u), fed: u.fed };
          let tt = 0; while (u.state === 'GROWING' && tt < 40 * H) { G.tick(1); tt++; } up.nextHunger = { after: tt, level: u.level, state: u.state, endMeal: !!u.endMeal };
          // an unfed fish waiting at 100% dies on its level's death timer (L1 12 h)
          fresh(); const u2 = G.buyFish('guppy'); u2.hungerDone = true; u2.progress = G.growSec(G.SPECIES.guppy, 1) - 0.5; G.tick(1); tt = 0;
          while (u2.state !== 'DEAD' && tt < 40 * H) { G.tick(1); tt++; } up.diesAfter = tt + 0.5; up.diedLevel = u2.level;
          out.justUp = up;
          fresh(); const u4 = G.buyFish('guppy'); u4.level = 3; u4.state = 'GROWING'; u4.hungerDone = true; u4.progress = G.growSec(G.SPECIES.guppy, 3) - 0.5; G.tick(1);
          const pre4 = { level: u4.level, state: u4.state, endMeal: !!u4.endMeal, need: G.mealFor(u4) }; const taps4 = feedFull(u4);
          out.justL4 = { pre: pre4, taps: taps4, level: u4.level, state: u4.state, deathLeft: u4.deathLeft, sinceFed: u4.sinceFed };
          // hunger at half of L1, death exactly deathSec after hunger (never fed after buy)
          fresh(); G.state.gold = 1000; a = G.buyFish('guppy'); t = 0; let h = null, dead = null;
          while (!dead && t < 200000) { G.tick(1); t++; if (h === null && a.state === 'HUNGRY') { h = t; out.progressAtHunger = a.progress; } if (a.state === 'DEAD') dead = t; }
          out.hungry = h; out.deathAfter = dead - h; out.deadState = a.state; out.deadStays = G.state.fish.includes(a);
          // meals: make Rasbora hungry (L3 mid = floor(7 / 2) = 3 food), then partial food moves nothing; a completed meal gives feed XP and moves dirt +300 s
          fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; const p = G.buyFish('rasbora'); p.level = 3; p.state = 'HUNGRY'; p.fed = 0; p.deathLeft = G.deathSecFor(G.SPECIES.rasbora, 3); p.hungerDone = true; p.progress = G.growSec(G.SPECIES.rasbora, 3) * 0.5;
          const t0 = G.state.dirt.t, x0 = G.state.tank.xp; const steps = [];
          for (let k = 0; k < 3; k++) { const r = G.feedTap(p.x, p.y); steps.push([r.full, G.state.dirt.t - t0, G.state.tank.xp - x0, p.fed, p.state]); }
          out.platyMeal = steps;
          // a meal that pushes the clock over a stage line still counts fully; only the next tap is blocked
          fresh(); const g2 = G.buyFish('guppy'); g2.state = 'HUNGRY'; g2.fed = 0; g2.deathLeft = G.deathSecFor(G.SPECIES.guppy, 1); g2.hungerDone = true; g2.progress = 90;
          G.state.dirt.t = T.dirt.stageAtSec[0] - 100; const x1 = G.state.tank.xp;
          const rr = G.feedTap(g2.x, g2.y); G.state.gold = 20; G.buyFish('guppy'); const nx = G.feedTap(0.5, 0.5);
          out.cross = { full: rr.full, state: g2.state, xp: G.state.tank.xp - x1, stage: G.dirtStage(), next: nx.reason, spots: G.state.dirt.spots.length };
          // sell formula + adultHungerMult + deathSecByRarity tables
          out.sellFormula = T.species.every((sp) => [1,2,3,4].every((lv) => G.sellPrice(sp, lv) === Math.floor(sp.price * lv / 2) && sp.sell[lv-1] === Math.floor(sp.price * lv / 2)));
          out.adultMult = T.adultHungerMultOfL3Grow; out.adultOk = T.species.every((sp) => G.adultHungerSec(sp) === sp.growSec[2] * T.adultHungerMultOfL3Grow && sp.adultHungerSec === sp.growSec[2] * 4);
          out.deathTables = T.deathSecByRarity;
          // v6.3 per-level meal walk (guppy + the rare Ram): taps for each mid / end meal, level only changes after the end meal
          out.walk = ['guppy', 'ram'].map((id) => { fresh(); G.state.gold = 5000; G.state.tank.xp = 5000; G.state.food = 500; const f = G.buyFish(id); const sp = G.SPECIES[id];
            const res = { id, bought: [f.state, G.needsFood(f)], meals: [] }; let t = 0;
            while (f.level < 4 && t < 100000) { G.tick(1); t++; if (f.state === 'HUNGRY') { clean();
              const m = { level: f.level, end: !!f.endMeal, pct: f.progress / G.growSec(sp, f.level), need: G.mealFor(f), panel: G.fishInfo(f).portion, taps: 0, levelDuring: [] };
              let r; do { r = G.feedTap(f.x, f.y); m.taps++; if (!r.full) m.levelDuring.push(f.level); } while (r.ok && !r.full && m.taps < 50);
              m.levelAfter = f.level; m.stateAfter = f.state; m.hungryAfter = G.needsFood(f); m.deathAfter = f.deathLeft; m.progressAfter = f.progress; res.meals.push(m); } }
            res.adult = [f.level, f.state, f.deathLeft, t]; return res; });
          // adults unchanged: L4 needs one meal of mealFood[3] after the 4 x L3 wait, stays L4
          out.adult = ['guppy', 'ram'].map((id) => { fresh(); G.state.tank.xp = 5000; G.state.gold = 5000; G.state.food = 500; const f = G.buyFish(id); f.level = 4; f.state = 'ADULT'; f.progress = 0; f.sinceFed = 0;
            let t = 0; while (f.state === 'ADULT' && t < 40 * H) { G.tick(1); t++; } clean(); const at = t, need = G.mealFor(f), taps = feedFull(f);
            return { id, hungryAt: at, wait: G.adultHungerSec(G.SPECIES[id]), need, taps, meal3: G.SPECIES[id].mealFood[3], after: [f.level, f.state, f.deathLeft] }; });
          return out;""")
        check("v6.3 food per level = mealFood (Guppy 2/3/4/5, Danio 2/3/4/5, Discus 2/7/11/16), 1 food per tap",
              f["meal"] == [s_["mealFood"] for s_ in tj["species"]] and f["meal"][0] == [2, 3, 4, 5] and f["meal"][1] == [2, 3, 4, 5] and f["meal"][-1] == [2, 7, 11, 16] and tj["foodPerTap"] == 1
              and ver_at_least(tj, "6.3"), json.dumps(f["meal"]))
        split_ok = all(sp_[lv] == [s_["mealFood"][lv] // 2, s_["mealFood"][lv] - s_["mealFood"][lv] // 2] and min(sp_[lv]) >= 1 for sp_, s_ in zip(f["split"], tj["species"]) for lv in range(3))
        check("v6.3 mealSplit: L1-L3 mid = floor(total / 2), end = the rest (Guppy L3 4 -> 2+2, Ram L3 5 -> 2+3), every meal >= 1, every L1 = 1+1; L4 one meal of mealFood[3]",
              split_ok and all(sp_[0] == [1, 1] for sp_ in f["split"]) and all(sp_[3] == [s_["mealFood"][3]] for sp_, s_ in zip(f["split"], tj["species"]))
              and f["split"][3][2] == [2, 3] and "mealSplit" in tj, json.dumps(f["split"][:4]))
        gsum = sum(next(s for s in tj["species"] if s["id"] == "guppy")["growSec"])
        check("Guppy grows 3 / 6 / 12 min and reaches adult in 21 min with prompt feeding; just-bought is GROWING with no death timer",
              f["adultAt"] == gsum == 21 * 60 and f["bought"] == {"state": "GROWING", "deathLeft": None, "progress": 0}
              and next(s for s in tj["species"] if s["id"] == "guppy")["growSec"] == [180, 360, 720], f"adultAt={f['adultAt']} bought={f['bought']}")
        hung = f["hung"]
        check("v6.3 hunger path: L1, L2, L3 each hungry at exactly 50% (mid) and 100% (end) of grow time (6 hungers, Guppy at 1m30 / 3m / 6m / 9m / 15m / 21m); reaching L4 is ADULT not hungry; adult wait = 4 x L3 grow (48 m)",
              [h_[2] for h_ in hung] == ["mid", "end"] * 3 and [h_[1] for h_ in hung] == [1, 1, 2, 2, 3, 3] and [h_[0] for h_ in hung] == [90, 180, 360, 540, 900, 1260]
              and [h_[3] for h_ in hung] == [0.5, 1.0] * 3
              and f["adultState"] == "ADULT" and f["adultDeath"] is None and f["adultHunger"] == 2880 == tj["species"][0]["adultHungerSec"]
              and f["adultMult"] == 4 and f["adultOk"] and tj["hungerPoints"] == [0.5, 1.0], json.dumps({"hung": hung, "adult": f["adultState"]}))
        check("hungry at 50% of L1 (Guppy at 1 m 30 s); sell formula (price/2)*level holds for every species",
              f["hungry"] == 90 and abs(f["progressAtHunger"] - 90) < 1e-6 and f["sellFormula"], f"hungry at {f['hungry']}s sell={f['sellFormula']}")
        common = tj["deathSecByRarity"]["common"]
        check("death exactly deathSecByRarity.common[L1] (12 h) after an L1 fish gets hungry; the dead fish stays in the tank",
              f["deathAfter"] == common[0] == 43200 and f["deadState"] == "DEAD" and f["deadStays"], f"deathAfter={f['deathAfter']}")
        bl = f["byLevel"]
        check("death timer by rarity+level (v6 3a): common/uncommon 12/14/18/20 h, rare 18/21/27/30 h; Guppy uses common",
              tj["deathSecByRarity"] == {"common": [43200, 50400, 64800, 72000], "uncommon": [43200, 50400, 64800, 72000], "rare": [64800, 75600, 97200, 108000]}
              and [b_["deathLeftAtHunger"] for b_ in bl] == common and [b_["diesAfter"] for b_ in bl] == common
              and f["rareDeath"]["diesAfter"] == f["rareDeath"]["expected"] == 108000, json.dumps({"bl": bl, "rare": f["rareDeath"]}))
        ju = f["justUp"]
        check("v6.3 at 100% of L1: hungry for the end meal, stays L1 (also 10 min later, info says L1) with the L1 timer (12 h); dies 12 h later at L1 if never fed",
              ju["atEnd"]["level"] == 1 and ju["atEnd"]["state"] == "HUNGRY" and ju["atEnd"]["endMeal"] and abs(ju["atEnd"]["deathLeft"] - common[0]) <= 1 and ju["atEnd"]["progress"] == 180
              and ju["after10m"] == {"level": 1, "state": "HUNGRY", "progress": 180, "info": 1} and abs(ju["diesAfter"] - common[0]) <= 1 and ju["diedLevel"] == 1, json.dumps(ju))
        check("v6.3 no meal right after a level-up: the end meal levels it to L2, GROWING from 0%, not hungry, no death timer; next hunger is the mid meal at 50% of L2 (3 m)",
              ju["afterEnd"] == {"full": True, "levelUp": True, "level": 2, "state": "GROWING", "deathLeft": None, "progress": 0, "needs": False, "fed": 0}
              and ju["nextHunger"] == {"after": 180, "level": 2, "state": "HUNGRY", "endMeal": False}, json.dumps(ju))
        check("adult hunger after the wait: an ADULT Guppy gets hungry exactly 4 x L3 grow (48 m = 2880 s) after its last meal / reaching L4",
              bl[3]["hungryAt"] == 2880 == 4 * tj["species"][0]["growSec"][2], json.dumps(bl[3]))
        check("L3 at 100% waits for its end meal (Guppy 2 food); after it: L4 ADULT, not hungry, no death timer, adult wait started (sinceFed 0)",
              f["justL4"]["pre"] == {"level": 3, "state": "HUNGRY", "endMeal": True, "need": 2} and f["justL4"]["taps"] == 2
              and f["justL4"]["level"] == 4 and f["justL4"]["state"] == "ADULT" and f["justL4"]["deathLeft"] is None and 0 <= f["justL4"]["sinceFed"] <= 1, json.dumps(f["justL4"]))
        for w_ in f["walk"]:
            sp_ = next(s_ for s_ in tj["species"] if s_["id"] == w_["id"]); mf = sp_["mealFood"]
            exp = [(lv, e, (mf[lv - 1] - mf[lv - 1] // 2) if e else mf[lv - 1] // 2) for lv in (1, 2, 3) for e in (False, True)]
            got = [(m_["level"], m_["end"], m_["need"]) for m_ in w_["meals"]]
            check(f"v6.3 {sp_['name']} L1-L3 ({sp_['rarity']}): bought not hungry; mid at 50% needs floor(total/2) taps, end at 100% needs the rest; panel food = meal; level unchanged until the end meal is eaten, then GROWING, not hungry",
                  w_["bought"] == ["GROWING", False] and got == exp and all(m_["taps"] == m_["need"] == m_["panel"] for m_ in w_["meals"])
                  and all(abs(m_["pct"] - (1.0 if m_["end"] else 0.5)) < 1e-9 for m_ in w_["meals"])
                  and all(set(m_["levelDuring"]) <= {m_["level"]} for m_ in w_["meals"])
                  and all(m_["levelAfter"] == m_["level"] + (1 if m_["end"] else 0) for m_ in w_["meals"])
                  and all(m_["stateAfter"] == ("ADULT" if m_["end"] and m_["level"] == 3 else "GROWING") and not m_["hungryAfter"] and m_["deathAfter"] is None for m_ in w_["meals"])
                  and all(m_["progressAfter"] == 0 for m_ in w_["meals"] if m_["end"])
                  and sum(m_["taps"] for m_ in w_["meals"]) == sum(mf[:3]) and w_["adult"][:3] == [4, "ADULT", None],
                  json.dumps([[m_["level"], "end" if m_["end"] else "mid", m_["need"], m_["taps"], m_["levelAfter"], m_["stateAfter"]] for m_ in w_["meals"]]))
        check("adults unchanged: an L4 Guppy / Ram gets hungry after 4 x L3 grow and needs one meal of mealFood[3] (5 / 6 food), stays L4 ADULT after",
              all(a_["hungryAt"] == a_["wait"] and a_["need"] == a_["taps"] == a_["meal3"] and a_["after"] == [4, "ADULT", None] for a_ in f["adult"])
              and [a_["meal3"] for a_ in f["adult"]] == [5, 6], json.dumps(f["adult"]))
        check("a just-bought L1 fish starts GROWING with no death timer; unfed it dies after mid-hunger + 12 h (not WAITING)",
              f["waiting"]["atBuy"] == ["GROWING", None] and f["waiting"]["after24h"][0] == "DEAD", json.dumps(f["waiting"]))
        pm = f["platyMeal"]
        check("Rasbora L3 mid meal = 3 food (7 -> 3+4): taps 1-2 are partial (no XP, dirt clock unchanged); tap 3 completes it: +7 feed XP, dirt clock +300 s, growing",
              [x_[0] for x_ in pm] == [False, False, True] and [x_[1] for x_ in pm] == [0, 0, 300] and [x_[2] for x_ in pm] == [0, 0, 7] and pm[2][4] == "GROWING"
              and tj["dirt"]["mealAddsSec"] == 300, json.dumps(pm))
        check("a meal that pushes the dirt over a stage line still counts (XP, growing); the next tap is blocked as dirty",
              f["cross"] == {"full": True, "state": "GROWING", "xp": 1, "stage": 1, "next": "dirty", "spots": tj["dirt"]["spots"][0]}, json.dumps(f["cross"]))

        # real taps: 1 food per tap, fed meter, v3 feeding pays 0 and shows no gold float (v6.3: Platy L3 end meal = 5 - 2 = 3 taps, then L4)
        pid = ev("""fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; const f = G.buyFish('platy');
          f.level = 3; f.state = 'HUNGRY'; f.fed = 0; f.hungerDone = true; f.endMeal = true; f.progress = G.growSec(G.SPECIES.platy, 3); f.deathLeft = G.deathSecFor(G.SPECIES.platy, 3);
          AQ.pinFish(f.id, 0.5, 0.45); return f.id;""")
        page.wait_for_timeout(200); tool("food")
        pos = page.evaluate(f"AQ.fishScreen({pid})")
        page.evaluate("AQ.floats(true)"); s0 = S(); tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s1 = S()
        tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s2 = S()
        f1 = next(x for x in s1["fish"] if x["id"] == pid); f2 = next(x for x in s2["fish"] if x["id"] == pid)
        page.wait_for_timeout(900); fl = page.evaluate("AQ.floats(true)")
        tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(120); s2 = S(); f2 = next(x for x in s2["fish"] if x["id"] == pid)
        check("real Food taps: 1 food per tap, Platy L3 end meal fed 1/3 (still L3), 2/3, then full -> L4 ADULT; only the level-up gold is paid (feedGoldPerFish 0)",
              tj["feedGoldPerFish"] == 0 and s1["food"] == s0["food"] - 1 and f1["fed"] == 1 and f1["state"] == "HUNGRY" and f1["level"] == 3 and s1["gold"] == s0["gold"]
              and s2["food"] == s0["food"] - 3 and f2["state"] == "ADULT" and f2["level"] == 4 and s2["gold"] == s0["gold"] + tj["species"][4]["levelUpGold"][2],
              f"food {s0['food']}->{s1['food']}->{s2['food']} gold {s0['gold']}->{s2['gold']} state {f2['state']}")
        check("full feed shows no gold float at all (no '+0')", not any("gold" in t or "+0" in t for t in fl), str(fl))
        # v6.3 multi-fish real taps: 4 hungry fish apart; every tap on the Platy (L3 end meal, 3 food) feeds the Platy only
        mids = ev("""fresh(); G.state.gold = 5000; G.state.tank.xp = 5000; G.state.speed = 1; const out = {};
          [['guppy', 0.2, 0.62], ['platy', 0.55, 0.4], ['ram', 0.85, 0.62], ['danio', 0.3, 0.3]].forEach(([id, x, y]) => { const f = G.buyFish(id); f.level = 3; f.state = 'HUNGRY'; f.fed = 0;
            f.hungerDone = true; f.endMeal = true; f.progress = G.growSec(G.SPECIES[id], 3); f.deathLeft = G.deathSecFor(G.SPECIES[id], 3); AQ.pinFish(f.id, x, y); out[id] = f.id; });
          return out;""")
        page.wait_for_timeout(250); tool("food"); mfed = []
        for _k in range(3):
            pp = page.evaluate(f"AQ.fishScreen({mids['platy']})"); tank_click(pp["x"], pp["y"]); page.wait_for_timeout(120)
            mfed.append({k_: (fish(v_)["fed"], fish(v_)["level"]) for k_, v_ in mids.items()})
        check("v6.3 multi-fish real taps: with 4 hungry fish, 3 taps on the Platy (L3 end meal = 3) feed only the Platy (1, 2, then L4); the others stay at 0",
              [m_["platy"] for m_ in mfed] == [(1, 3), (2, 3), (0, 4)] and all(m_[k_] == (0, 3) for m_ in mfed for k_ in ("guppy", "ram", "danio")), json.dumps(mfed))
        ev("G.state.fish.forEach((f) => { if (f.state === 'HUNGRY') { f.state = 'GROWING'; f.fed = 0; f.endMeal = false; f.deathLeft = null; f.progress = 0; } });"); s2 = S()
        clear_toasts(); tank_click(pos["x"], pos["y"] - 20); page.wait_for_timeout(150)
        check("tap with nobody hungry: 'Nobody's hungry', no food spent", S()["food"] == s2["food"] and "Nobody's hungry" in page.inner_text("#toasts"), page.inner_text("#toasts"))

        # v1 flake shower on every successful tap (NUMBERS.md 3.4), drifting toward the fed fish; blocked taps show none
        fid = ev("""fresh(); G.state.gold = 1000; G.state.tank.xp = 1200; G.state.speed = 1; const f = G.buyFish('platy');
          f.level = 3; f.state = 'HUNGRY'; f.fed = 0; f.hungerDone = true; f.progress = G.growSec(G.SPECIES.platy, 3) * 0.5; f.deathLeft = G.deathSecFor(G.SPECIES.platy, 3);
          AQ.pinFish(f.id, 0.82, 0.55); return f.id;""")
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
        gid = ev("fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); G.tick(90); AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(2500); clear_toasts(); tool("hand"); click_fish(gid); page.wait_for_timeout(250)
        ht, gt, mt, wt = page.inner_text("#p-hunger"), page.inner_text("#p-growth"), page.inner_text("#p-meal"), page.inner_text("#p-worth")
        segs = page.evaluate("[...document.querySelectorAll('#p-mealbar i')].map((e) => e.classList.contains('on'))")
        check("fish info: 'Hungry! Growth paused · dies in 12h 00m', v6.3 L1 mid meal 'Meal 1 of 2 · needs 1 food' with a 1-segment bar, 'Worth 10 gold'; no tap counts",
              any(ht.startswith("Hungry! Growth paused · dies in " + t) for t in ("12h 00m", "11h 59m")) and "Growth paused" in gt and mt == "Meal 1 of 2 · needs 1 food"
              and segs == [False] and wt == "Worth 10 gold" and "tap" not in (ht + mt + gt).lower(), f"{ht} | {gt} | {mt} | {segs} | {wt}")
        page.screenshot(path=shot("panel_hungry"))
        page.keyboard.press("Escape")

        # ================================================================ C. tank XP / shop gating
        x = ev("""fresh(); G.state.gold = 1000; const a = G.buyFish('guppy'); let n = 0;
          while (a.level < 2 && n++ < 10000) { G.tick(1); if (a.state === 'HUNGRY' && a.level < 2) { clean(); feedFull(a); } }
          const afterLvl = G.state.tank.xp, gu = T.species.find((s) => s.id === 'guppy');
          G.sell(a.id); const afterSell = G.state.tank.xp;
          const table = T.species.map((sp) => [2, 3, 4].map((lv) => G.xpFor('fishLevelUp', { sp, level: lv })));
          const sellXp = T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.xpFor('sell', { sp, level: lv }))), feedXp = T.species.map((sp) => G.xpFor('feed', { sp }));
          return { afterLvl, xp2: gu.levelUpXp[0], gold2: gu.levelUpGold[0], afterSell, table, sellXp, feedXp, retired: G.CFG.XP_SOURCE === undefined && G.CFG.XP_PRESETS === undefined,
            rule: T.tank.xp.fishLevelUp, lv: [0, 59, 60, 399, 400, 1200, 3000].map(G.tankLevelFor) };""")
        check("tank XP v6.3: 2 meals (L1 mid + end) x feed XP 1 + Guppy L2 level-up 10 (pays 1 gold) = 12; selling at L2 adds sellXp 10; tables = tuning",
              x["rule"] == "species.levelUpXp" and x["afterLvl"] == 2 * 1 + x["xp2"] == 12 and x["gold2"] == 1 and x["afterSell"] == x["afterLvl"] + 10 and x["retired"]
              and x["table"] == [s_["levelUpXp"] for s_ in tj["species"]] and x["sellXp"] == [s_["sellXp"] for s_ in tj["species"]]
              and x["feedXp"] == [s_["feedXp"] for s_ in tj["species"]], json.dumps(x))
        # level-up floats: "+2 gold" and "+20 XP" for a Guppy reaching L3 (NUMBERS.md 1f)
        lf = ev("""fresh(); G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); feedFull(f); f.level = 2; f.progress = G.growSec(G.SPECIES.guppy, 2) - 0.5;
          f.hungerDone = true; AQ.pinFish(f.id, 0.5, 0.5); G.tick(1); const pre = [f.level, f.state]; AQ.floats(true); const g0 = G.state.gold, x0 = G.state.tank.xp; feedFull(f);
          return { gold: G.state.gold - g0, xp: G.state.tank.xp - x0 - G.SPECIES.guppy.feedXp, level: f.level, pre };""")
        page.wait_for_timeout(100); fl = page.evaluate("AQ.floats(true)")
        check("level-up (after the L2 end meal) pays v3 gold and shows '+2 gold' and '+20 XP' floats (Guppy L3)", lf["pre"] == [2, "HUNGRY"] and lf["gold"] == 2 and lf["xp"] == 20 and lf["level"] == 3 and "+2 gold" in fl and "+20 XP" in fl, f"{lf} {fl}")
        check("tank levels at 60 / 400 / 1200 / 3000 XP", x["lv"] == [1, 1, 2, 2, 3, 4, 5], str(x["lv"]))
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 55; G.state.speed = 1;")
        page.click("#btn-shop"); page.wait_for_timeout(250)
        lock = {sp: (page.locator(f'button[data-buy="{sp}"]').is_disabled(), page.locator(f'button[data-buy="{sp}"]').inner_text()) for sp in ["guppy", "danio", "neon", "platy"]}
        check("shop: locked species disabled with 'Aquarium level N' (never 'Tank level') even with 1000 gold", not lock["guppy"][0] and all(lock[s][0] and f"Aquarium level {n}" in lock[s][1] and "Tank" not in lock[s][1] for s, n in [("danio", 2), ("neon", 3), ("platy", 4)]), json.dumps(lock))
        check("buying a locked species is refused", ev("return G.canBuy('neon').locked === true && G.buyFish('neon') === null;"))
        page.click('[data-close="shop"]'); clear_toasts()
        ev("toStage(1); rubAll(1.01);")  # clean gives the last 5 XP -> tank level 2
        page.wait_for_timeout(200)
        tt = page.inner_text("#toasts")
        page.click("#btn-shop"); page.wait_for_timeout(250)
        check("aquarium level-up toast ('Aquarium level 2: ...') names the unlock; Danio becomes buyable", "Aquarium level 2" in tt and "Tank level" not in tt and "Zebra Danio" in tt and not page.locator('button[data-buy="danio"]').is_disabled(), tt)
        page.click('[data-close="shop"]')
        # shop prices / "sells up to" match tuning.json (all unlocked)
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 5000; G.state.speed = 1;")
        clear_toasts(); page.click("#btn-shop"); page.wait_for_timeout(250)
        shop = {sp["id"]: (page.locator(f'button[data-buy="{sp["id"]}"] .price').inner_text(), page.locator(f'#shop-list .card:has(button[data-buy="{sp["id"]}"])').inner_text()) for sp in tj["species"]}
        check("shop prices and 'sells up to' adult price match tuning.json for all 14 species",
              [int(shop[s_["id"]][0]) for s_ in tj["species"]] == [s_["price"] for s_ in tj["species"]]
              and len(tj["species"]) == 14 and all(f'sells up to {s_["sell"][3]}g' in shop[s_["id"]][1] for s_ in tj["species"]), json.dumps({k: v[0] for k, v in shop.items()}))
        page.screenshot(path=shot("shop"))
        page.click('[data-close="shop"]')
        sp_tab = ev("return T.species.map((sp) => [1, 2, 3, 4].map((lv) => G.sellPrice(sp, lv)));")
        lg_tab = ev("return T.species.map((sp) => [2, 3, 4].map((lv) => G.levelUpGold(sp, lv)));")
        check("sell prices at every level = (price/2)*level (Guppy 10/20/30/40) and level-up gold (Guppy 1/2/4) follow tuning.json v6",
              sp_tab == [s_["sell"] for s_ in tj["species"]] and sp_tab[0] == [10, 20, 30, 40] and lg_tab == [s_["levelUpGold"] for s_ in tj["species"]] and lg_tab[0] == [1, 2, 4]
              and all(sp_tab[i][lv] == tj["species"][i]["price"] * (lv + 1) // 2 for i in range(len(tj["species"])) for lv in range(4)), json.dumps([sp_tab[0], lg_tab[0]]))
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
        check("fish info has no sell button and shows 'Worth 10 / 20 / 30 / 40 gold' by level", panel_btns == [0, 0, 0, 0] and worth == ["Worth 10 gold", "Worth 20 gold", "Worth 30 gold", "Worth 40 gold"], json.dumps([worth, panel_btns]))
        check("Net confirms: Sell Guppy (L1) for 10 gold? / L2 20 + 10 XP / L3 30 + 25 XP / L4 40 + 80 XP",
              btns == ["Sell Guppy (L1) for 10 gold?", "Sell Guppy (L2) for 20 gold and 10 XP?", "Sell Guppy (L3) for 30 gold and 25 XP?", "Sell Guppy (L4) for 40 gold and 80 XP?"], str(btns))
        tool("hand")

        # debug +50 XP button (NUMBERS.md 9.13): normal XP path, tank level-ups + unlock toasts, no gold, persists
        ev("fresh(); G.state.gold = 1000; G.state.speed = 1;"); page.wait_for_timeout(100)
        assert open_debug()
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
              clicks == 24 and seen[2][:2] == (2, 100) and "Aquarium level 2: Zebra Danio unlocked" in seen[2][2] and seen[3][:2] == (3, 400)
              and "Neon Tetra" in seen[3][2] and "German Blue Ram (rare)" in seen[3][2]
              and seen[4][:2] == (4, 1200) and "Platy" in seen[4][2] and "Harlequin Rasbora (uncommon)" in seen[4][2] and g_after == 1000, json.dumps({"clicks": clicks, "seen": {k: (v[0], v[1], v[2][:80]) for k, v in seen.items()}, "gold": g_after}))
        page.click("#btn-shop"); page.wait_for_timeout(200)
        unl = {sp_["id"]: (page.locator(f'button[data-buy="{sp_["id"]}"]').is_disabled(), page.locator(f'button[data-buy="{sp_["id"]}"]').inner_text()) for sp_ in tj["species"]}
        open4 = [s_["id"] for s_ in tj["species"] if s_["unlockTankLevel"] <= 4]
        check("at tank level 4 the unlockTankLevel<=4 species are buyable; later ones stay locked",
              all(not unl[i][0] for i in open4) and all(unl[s_["id"]][0] for s_ in tj["species"] if s_["unlockTankLevel"] > 4), json.dumps({k: v[0] for k, v in unl.items()}))
        page.click('[data-close="shop"]')
        boot("?speed=1")
        check("debug XP persists after reload (normal save path)", page.evaluate("AQ.game.state.tank.xp") == 1200 and page.evaluate("AQ.game.tankInfo().level") == 4 and S()["gold"] == 1000)

        # ================================================================ D. offline catch-up (real reload) + dead fish
        ids = ev("""fresh(); G.state.speed = 1; G.state.gold = 100; const a = G.buyFish('guppy'); // a grows from buy (no start meal)
          const b = G.buyFish('guppy'); // also growing
          G.save(); G.save = () => {}; // keep this page's periodic/pagehide save from overwriting the edited timestamp
          const k = G.CFG.VISUAL.saveKey, d = JSON.parse(localStorage.getItem(k)); d.lastSeen -= 49 * H * 1000; localStorage.setItem(k, JSON.stringify(d));
          return { a: a.id, b: b.id, t0: G.state.gameTime };""")
        boot(); page.wait_for_timeout(600)
        s = S(); a = fish(ids["a"]); b = fish(ids["b"])
        check("offline 49 h: dirt stage 5, both unfed guppies died at 1m30 + 12h (L1 death) and stay DEAD",
              stage() == 5 and a and a["state"] == "DEAD" and abs(a["diedAt"] - ids["t0"] - 43290) <= 5 and b and b["state"] == "DEAD",
              f"stage={stage()} a={a and a['state']} diedAt-t0={a and a['diedAt'] - ids['t0']:.0f} b={b and b['state']}")
        aw = page.locator("#away").is_visible(); at_ = page.inner_text("#away-time") if aw else ""; al = page.inner_text("#away-list") if aw else ""
        if aw: page.screenshot(path=shot("away_window"))
        check("'While you were away' summary: 49h, Guppy died, 'Tank is at dirt stage 5'", aw and "49h 00m" in at_ and "Guppy died" in al and "Tank is at dirt stage 5" in al and "clean" not in al.lower(), f"{at_} | {al}")
        page.click("#away-ok")
        # (the page's own clock never went back: lastSeen is put back to now afterwards, or the real-clock frame loop would
        #  correctly count the faked hour when the page's Date.now() is 1 h ahead of it)
        r = ev("""const t0 = G.state.gameTime; G.state.lastSeen = Date.now(); const back = G.resume(Date.now() - H * 1000); const d1 = G.state.gameTime - t0;
          G.state.lastSeen = Date.now(); return { back, d1 };""")
        check("clock set backwards counts as 0 offline time", r["back"] is None and r["d1"] == 0, json.dumps(r))
        r = ev("""const snap = JSON.stringify(G.state); G.state.lastSeen = Date.now() - 30 * 24 * H * 1000; const t0 = G.state.gameTime;
          const res = G.resume(Date.now()); const d1 = G.state.gameTime - t0; G.load({ getItem: () => snap }); G.state.lastSeen = Date.now();
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
        full = ev(f"""clean(); G.state.gold = 1000; for (let i = 0; i < 4; i++) {{ const g = G.buyFish('guppy'); g.state = 'HUNGRY'; g.fed = 0; g.hungerDone = true; g.progress = 90; g.deathLeft = G.deathSecFor(G.SPECIES.guppy, 1); }}
          const n = G.state.fish.length, c = G.canBuy('guppy'); const dead = G.state.fish.find((f) => f.id === {ids['a']});
          const r = G.feedTap(dead.x, dead.y); return {{ n, ok: c.ok, reason: c.reason, fedId: r.ok ? r.fish.id : null, deadFed: dead.fed, living: G.living() }};""")
        check("dead fish takes a tank slot (6/6 incl. dead -> 'Tank full')", full["n"] == 6 and not full["ok"] and full["reason"] == "Tank full", json.dumps(full))
        check("dead fish isn't fed and doesn't block feeding (tap on it feeds a living fish)", full["fedId"] not in (None, ids["a"]) and full["deadFed"] == 0, json.dumps(full))
        page.click("#btn-shop"); page.wait_for_timeout(200)
        check("shop disables buying while the tank is full with a dead fish in it", page.locator('button[data-buy="guppy"]').is_disabled())
        page.click('[data-close="shop"]'); tool("hand")
        ev(f"const i = G.state.fish.findIndex((f) => f.id === {ids['b']}); if (i >= 0) G.state.fish.splice(i, 1);")  # the other dead fish can sit under the tap (1180x820 flake: 'Fish removed ×2')
        gold_b, xp_b = S()["gold"], S()["tank"]["xp"]; clear_toasts(); tool("net"); click_fish(ids["a"], "#toasts .toast"); page.wait_for_timeout(150)
        tl_ = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        check("v6.8 NUMBERS 3.8: Net on a dead Guppy removes it at once (no confirm), +floor(20/4) = 5 gold, 0 XP, 'Fish removed · +5 gold' toast, slot freed",
              fish(ids["a"]) is None and not page.locator("#confirm").is_visible() and S()["gold"] == gold_b + 5 and S()["tank"]["xp"] == xp_b and "Fish removed · +5 gold" in tl_ and ev("return G.canBuy('guppy').ok;"), json.dumps(tl_))
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
        check(f"sponge mouse rub cleans stage 3: +{cg[2]} gold (v6.5), +5 XP, 'Sparkling! +{cg[2]} gold' float", ok and s["gold"] == gold_b + cg[2] and s["tank"]["xp"] == xp_b + 5 and f"Sparkling! +{cg[2]} gold" in fl, f"gold {gold_b}->{s['gold']} xp {xp_b}->{s['tank']['xp']} {fl}")
        tool("hand"); page.wait_for_timeout(400)
        page.screenshot(path=shot("after_clean"))
        # L1 release and L2 sell with the Net (both confirmed)
        rt = net_text(gid)
        cb_ = page.evaluate("(() => { const b = document.querySelector('#confirm .modal-box').getBoundingClientRect(), k = document.getElementById('tank-wrap').getBoundingClientRect(), n = document.getElementById('confirm-no').getBoundingClientRect(), y = document.getElementById('confirm-yes').getBoundingClientRect(), pc = document.getElementById('confirm-portrait'); return { w: b.width, cx: (b.left + b.right) / 2 - (k.left + k.right) / 2, cy: (b.top + b.bottom) / 2 - (k.top + k.bottom) / 2, cancelLeft: n.right <= y.left, portrait: pc.offsetParent !== null, no: document.getElementById('confirm-no').textContent }; })()")
        page.screenshot(path=shot("release_confirm"))
        check("Net on an L1 fish: centred confirm (320 / 400 wide) with the fish portrait, 'Sell Guppy (L1) for 10 gold?', Cancel left of Sell",
              rt == "Sell Guppy (L1) for 10 gold?" and abs(cb_["w"] - (400 if LARGE else 320)) < 1 and abs(cb_["cx"]) < 2 and abs(cb_["cy"]) < 2 and cb_["cancelLeft"] and cb_["portrait"]
              and page.inner_text("#confirm-yes") == "Sell" and cb_["no"] == "Cancel", json.dumps([rt, cb_]))
        gb = S()["gold"]; page.click("#confirm-yes"); page.wait_for_timeout(150)
        check("sold L1 for 10 gold (v6 sell = price/2)", S()["gold"] == gb + 10 and fish(gid) is None)
        sid = ev("G.state.gold = 100; const f = G.buyFish('guppy'); f.level = 2; f.state = 'GROWING'; AQ.pinFish(f.id, 0.5, 0.45); return f.id;")
        page.wait_for_timeout(200); st = net_text(sid); gb = S()["gold"]; xb = S()["tank"]["xp"]
        page.click("#confirm-no"); page.wait_for_timeout(100); kept = fish(sid) is not None
        net_text(sid); page.click("#confirm-yes"); page.wait_for_timeout(150)
        l2 = next(s_ for s_ in tj["species"] if s_["id"] == "guppy")["sell"][1]
        check(f"Net sells an L2 Guppy only after confirming: Cancel keeps it, Sell pays {l2} gold + 10 XP", kept and st == f"Sell Guppy (L2) for {l2} gold and 10 XP?" and S()["gold"] == gb + l2 and S()["tank"]["xp"] == xb + 10 and fish(sid) is None, st)
        tool("hand")
        # Net drag (Maksims): the net follows the pointer, the fish under it is highlighted; letting go over a live fish opens
        # its sell / release confirm, over a dead fish removes it (no confirm, Designer 11.4), over empty water does nothing
        nd = ev("""fresh(); G.state.gold = 100; G.state.speed = 1; const a = G.buyFish('guppy'); a.level = 2; a.state = 'GROWING'; AQ.pinFish(a.id, 0.5, 0.5);
                  const d = G.buyFish('guppy'); d.state = 'DEAD'; return { live: a.id, dead: d.id };""")
        page.wait_for_timeout(600); tool("net"); b_ = box(); clear_toasts()
        def mv(x, y, steps=8): page.mouse.move(b_["x"] + x, b_["y"] + y, steps=steps); page.wait_for_timeout(80)
        empty = (b_["width"] * 0.8, b_["height"] * 0.62)
        mv(*empty); n_hover = page.evaluate("AQ.net()"); page.mouse.down(); page.wait_for_timeout(60)
        n_down = page.evaluate("AQ.net()")
        lp = page.evaluate(f"AQ.fishScreen({nd['live']})"); mv(lp["x"], lp["y"], 12); n_on = page.evaluate("AQ.net()")
        page.screenshot(path=shot("net_drag_highlight"))
        # white body outline: the brightest pixel along the fish's top edge is near-white while targeted, not after
        def top_edge_max():   # number of near-white pixels (min channel > 228) in a box around the fish body
            tb2 = box(); png = page.screenshot(clip={"x": tb2["x"], "y": tb2["y"], "width": tb2["width"], "height": tb2["height"]}); _w2, _h2, px2 = png_rgb(png); k2 = _w2 / tb2["width"]
            c_ = page.evaluate(f"AQ.fishScreen({nd['live']})"); fi = page.evaluate(f"AQ.fishIcon({nd['live']})"); hd = fi["halfDepth"]; n_ = 0
            for yy in range(int(c_["y"] - hd * 1.8), int(c_["y"] + hd * 1.8) + 1):
                for xx in range(int(c_["x"] - fi["L"] * 0.6), int(c_["x"] + fi["L"] * 0.6) + 1):
                    if min(px2(int(xx * k2), int(yy * k2))) > 228: n_ += 1
            return n_
        ring = [top_edge_max()]
        rim_on = page.evaluate("AQ.net()")
        mv(*empty, 12); n_off = page.evaluate("AQ.net()")
        mv(*empty, 1); page.wait_for_timeout(250); ring.append(top_edge_max())
        page.mouse.up(); page.wait_for_timeout(300)
        empty_ok = not page.locator("#confirm").is_visible() and len(S()["fish"]) == 2
        page.mouse.down(); lp = page.evaluate(f"AQ.fishScreen({nd['live']})"); mv(lp["x"], lp["y"], 12); page.mouse.up(); page.wait_for_timeout(60)
        dip_ = page.evaluate("AQ.net()"); early = page.locator("#confirm").is_visible(); page.wait_for_timeout(250)
        live_txt = page.inner_text("#confirm-text") if page.locator("#confirm").is_visible() else ""
        page.screenshot(path=shot("net_release_live_confirm")); page.click("#confirm-no"); page.wait_for_timeout(100)
        g0_, x0_ = S()["gold"], S()["tank"]["xp"]; clear_toasts()
        mv(*empty); page.mouse.down(); dp = page.evaluate(f"AQ.fishScreen({nd['dead']})"); mv(dp["x"], dp["y"], 12)
        n_dead = page.evaluate("AQ.net()"); page.screenshot(path=shot("net_drag_dead")); page.mouse.up(); page.wait_for_timeout(300)
        dead_t = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        dead_ok = fish(nd["dead"]) is None and not page.locator("#confirm").is_visible() and S()["gold"] == g0_ + 5 and S()["tank"]["xp"] == x0_ and "Fish removed · +5 gold" in dead_t
        info_nd = {"hover": n_hover, "down": n_down, "on": n_on, "off": n_off, "outlineMaxMin": ring, "emptyOk": empty_ok, "dip": dip_, "confirmDuringDip": early, "liveTxt": live_txt, "dead": n_dead, "deadToasts": dead_t, "deadOk": dead_ok}
        check("AD net cursor: hoop 44 / 60px centred on the mouse, follows it (hover and pressed), tilts while moving; the fish under the hoop is the target and gets a white body outline; letting go over empty water does nothing",
              n_hover["on"] and n_down["on"] and n_down["r"] == (30 if LARGE else 22) and abs(n_down["x"] - empty[0]) < 1.5 and abs(n_down["y"] - empty[1]) < 1.5 and n_on["target"] == nd["live"] and abs(n_on["x"] - lp["x"]) < 1.5
              and 0 < abs(n_on["tilt"]) <= 12 * 3.1416 / 180 + 1e-6 and n_off["target"] is None and empty_ok and ring[0] >= 40 and ring[0] > 3 * ring[1] + 20, json.dumps(info_nd))
        check("Net drag: letting go over a live fish dips the hoop first (no confirm yet at 60 ms), then opens its confirm ('Sell Guppy (L2) for 20 gold and 10 XP?'); over a dead fish it removes it (no confirm, v6.8 +5 gold for a Guppy, 0 XP, 'Fish removed · +5 gold')",
              dip_["dip"] >= 0 and not early and live_txt == "Sell Guppy (L2) for 20 gold and 10 XP?" and n_dead["target"] == nd["dead"] and dead_ok, json.dumps(info_nd))
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
              len(toasts) >= 2 and any("died" in t_["text"] for t_ in toasts) and any("Aquarium level 2" in t_["text"] for t_ in toasts) and not any(hit(t_, band) for t_ in toasts) and 0.055 <= dy <= 0.105,
              json.dumps({"band": band, "toasts": toasts, "deadY": round(dy, 3)}))
        # N3: only dead fish -> no hint; back once a living fish is there
        page.wait_for_timeout(2800)
        h_dead = page.inner_text("#hint").strip() if page.locator("#hint").is_visible() else ""
        page.screenshot(path=shot("only_dead_fish"))
        ev("const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.5, 0.5);"); page.wait_for_timeout(200); h_live = page.inner_text("#hint")
        check("N3: only dead fish -> hint empty; a living (growing) fish brings hints back ('Tap a fish to see its details')",
              h_dead == "" and h_live == "Tap a fish to see its details", json.dumps([h_dead, h_live]))
        # D1: Start new tank modal states exactly what resets, and the button does reset exactly that
        ev("fresh(); G.state.speed = 1; G.state.tank.xp = 1500; G.state.food = 3; G.state.starterGrantUsed = true; const f = G.buyFish('guppy') || null; G.state.gold = 3; if (f) { f.state = 'DEAD'; f.diedAt = G.state.gameTime - 30; } G.tick(1);")
        page.wait_for_timeout(400)
        line = page.inner_text("#newtank-reset") if page.locator("#tankover").is_visible() else ""
        page.screenshot(path=shot("start_new_tank_modal"))
        locked_names = [s_["name"] for s_ in tj["species"] if (s_.get("unlockTankLevel") or 1) > 1]
        locked_txt = (", ".join(locked_names[:-1]) + " and " + locked_names[-1]) if len(locked_names) > 1 else (locked_names[0] if locked_names else "")
        fc = tj["newTank"]["firstCleanReward"]
        exp_line = f"Everything resets: 0 gold, 0 food, 0 diamonds, no fish, aquarium level 1 (0 XP), {locked_txt} lock again, no decorations, and the tank starts dirty (stage 3). The first clean pays {fc['gold']} gold and {fc['food']} food again."
        page.click("#btn-newtank"); page.wait_for_timeout(250)
        after = ev("return { gold: G.state.gold, food: G.state.food, diamonds: G.state.diamonds, fish: G.state.fish.length, xp: G.state.tank.xp, lvl: G.tankInfo().level, locked: ['danio', 'neon', 'platy'].map((id) => !!G.canBuy(id).locked), grant: G.state.starterGrantUsed, speed: G.state.speed, stage: G.dirtStage(), fc: G.state.firstCleanPending };")
        check("D1: 'Your tank is empty' modal has the v6 reset line (first clean 20g+50f), and Start new tank resets exactly that",
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
        # real clean finishing at the far right edge: the spots are pre-rubbed to 3% grime in the page, then one real mouse
        # stroke along the right wall finishes the clean there (deterministic at every tank size)
        ev("fresh(); G.state.gold = 50; G.state.speed = 1; toStage(1); G.state.dirt.spots.forEach((s, i) => { s.x = 0.9; s.y = 0.3 + i * 0.25; s.grime = s.grime0 * 0.03; });")
        page.wait_for_timeout(200); page.evaluate("AQ.floats(true)"); tool("sponge"); b_ = box(); cb = []
        for sp in page.evaluate("AQ.spotsScreen()"):
            page.mouse.move(b_["x"] + b_["width"] - 30, b_["y"] + sp["y"] - 10); page.mouse.down()
            for _k in range(4):
                page.mouse.move(b_["x"] + b_["width"] - 3, b_["y"] + sp["y"] + 10, steps=4)
                page.mouse.move(b_["x"] + b_["width"] - 30, b_["y"] + sp["y"] - 10, steps=4)
                if stage() == 0: break
            page.mouse.up()
            if stage() == 0:
                page.wait_for_timeout(80); cb = [q for q in page.evaluate("AQ.floatBoxes()") if q["text"].startswith("Sparkling")]; break
        page.screenshot(path=shot("float_edge_clamp"))
        check(f"N6: a real clean finished at the far right edge: 'Sparkling! +{tj['dirt']['cleanGold'][0]} gold' fully inside the tank (>= 8 px)",
              stage() == 0 and len(cb) == 1 and cb[0]["x1"] <= Wt - 8 + 0.01 and cb[0]["x0"] >= 8 and cb[0]["x1"] >= Wt - 8 - 25, json.dumps({"stage": stage(), "cb": cb, "Wt": Wt}))
        tool("hand")

        # ================================================================ E3. Playtester pass 7 polish (M2 multi level-up, N4); the M1 callout arrow is gone (v4)
        # M2: 4 Guppies level up in the same tick (3 bunched in the middle, 1 at the right wall): staggered float pairs never
        # overlap, all >= 8px inside the tank; identical toasts merge into one line with a count
        page.wait_for_timeout(1900); clear_toasts(); page.evaluate("AQ.floats(true)")
        ev("""fresh(); G.state.gold = 500; G.state.speed = 1;
              [[0.5, 0.45], [0.52, 0.46], [0.48, 0.44], [0.93, 0.3]].forEach(([x, y]) => { const f = G.buyFish('guppy'); feedFull(f); AQ.pinFish(f.id, x, y); });""")
        page.wait_for_timeout(300); clear_toasts()
        ev("G.state.fish.forEach((f) => { f.progress = G.growSec(G.SPECIES.guppy, f.level) - 0.5; f.hungerDone = true; }); G.tick(1); G.state.fish.forEach((f) => feedFull(f));")
        m2, snaps = [], []
        for wait in (80, 250, 450, 600):   # (shorter total so the merged toast is surely still up for the 5th below)
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
        ev("const f = G.buyFish('guppy'); feedFull(f); f.progress = G.growSec(G.SPECIES.guppy, 1) - 0.5; f.hungerDone = true; AQ.pinFish(f.id, 0.3, 0.7); G.tick(1); feedFull(f);"); page.wait_for_timeout(100)
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
        page.wait_for_timeout(300); assert open_debug()
        n5 = page.evaluate("""(() => { const r = (id) => document.getElementById(id).getBoundingClientRect(); const e = document.getElementById('dbg-reset');
            const rg = document.createRange(); rg.selectNodeContents(e); const lines = new Set([...rg.getClientRects()].map((q) => Math.round(q.top))).size;
            const x = r('dbg-reset'), xp = r('dbg-xp'), c = r('dbg-clock'), dbg = r('debug'), t = r('tank-wrap');
            return { textLines: lines, sameRow: Math.abs(x.top - xp.top) < 0.5, resetRight: x.right, clockRight: c.right, clockTop: c.top, dbgRight: dbg.right, dbgL: dbg.left, tankL: t.left, tankR: t.right,
                     clockOneLine: c.height < 20, fs: parseFloat(getComputedStyle(document.getElementById('debug')).fontSize), h: dbg.height, overflow: document.getElementById('debug').scrollWidth > document.getElementById('debug').clientWidth + 0.5 }; })()""")
        page.locator("#debug").screenshot(path=shot("debug_row"))
        check("debug row: one line under the tank only, 11px / 13px, h 20 / 22 (Job F), Reset save on the button row, clock right-aligned, nothing clipped",
              n5["textLines"] == 1 and n5["sameRow"] and abs(n5["clockRight"] - n5["dbgRight"]) < 1 and n5["clockOneLine"] and n5["fs"] == (13 if LARGE else 11) and abs(n5["h"] - (22 if LARGE else 20)) < 0.5
              and abs(n5["dbgL"] - n5["tankL"]) < 0.5 and abs(n5["dbgRight"] - n5["tankR"]) < 0.5 and not n5["overflow"] and n5["resetRight"] < n5["clockRight"], json.dumps(n5))

        # ================================================================ L. landscape layout v4 (Art Director LANDSCAPE_LAYOUT_V4.md)
        boot("?speed=1"); ev("fresh(); G.state.food = 0; G.state.speed = 1;"); tool("hand"); page.wait_for_timeout(300)
        lay = page.evaluate("AQ.layout()")
        # fluid frame (Maksims 20:10): padding 8 / 12 on top, left and right, bottom only max(4, safe-area) = 4 here; the tank
        # fills everything right of the column and between the top bar and the debug row (AD boxes with the 4px bottom)
        pd, cw, tb_, gp, dh = (12, 96, 48, 8, 22) if LARGE else (8, 68, 36, 6, 20)  # Job F: debug row 20 / 22, no bottom padding
        tx_ = pd + cw + pd if LARGE else pd + cw + 8
        spec = {"column": (pd, pd, cw, VH - pd), "hud": (tx_, pd, VW - tx_ - pd, tb_), "tank": (tx_, pd + tb_ + gp, VW - tx_ - pd, VH - dh - gp - (pd + tb_ + gp)),
                "debug": (tx_, VH - dh, VW - tx_ - pd, dh)}
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
        check("AD v4 3: top bar = gold pill, diamond pill (no food pill; 0 diamonds), 'Aquarium Lv 1' block with '0 / 60', dirt window 240x36 / 320x48 right-aligned; pills 32 / 42 high",
              hud["order"] == ["res-gold", "res-gem", "tanklvl", "dirt-win"] and not hud["food"] and hud["gems"] == "0" and hud["label"] == "Aquarium Lv 1" and hud["xp"] == "0 / 60"
              and abs(hud["dirt"]["width"] - (320 if LARGE else 240)) < 0.5 and abs(hud["dirt"]["height"] - (48 if LARGE else 36)) < 0.5 and abs(hud["dirt"]["right"] - hud["hud"]["right"]) < 0.5
              and abs(hud["gold"]["height"] - (42 if LARGE else 32)) < 0.5 and hud["lvl"]["width"] >= 160 and hud["pillFs"] == ("20px" if LARGE else "16px") and "tabular-nums" in hud["tab"], json.dumps(hud))
        # Maksims / AD v4 3 (2026-09-28): the level block reads "Aquarium Lv N"; "Aquarium Lv 12" + "Dirt: max" must fit on one row without clipping
        lv12 = ev("""toStage(5); if (!G.__tankInfo) G.__tankInfo = G.tankInfo; const real = G.__tankInfo; G.tankInfo = () => Object.assign({}, real(), { level: 12 }); return 0;""")
        page.wait_for_timeout(120)
        fit = page.evaluate("""(() => { const q = (s) => document.querySelector(s), r = (s) => q(s).getBoundingClientRect(); const l = q('#tank-label'), cs = getComputedStyle(l);
            const lb = r('#tank-label'), blk = r('#tanklvl'), dw = r('#dirt-win'), hud = q('#hud'), dl = q('#dirt-label');
            return { label: l.textContent, dirt: dl.textContent, sw: l.scrollWidth, cw: l.clientWidth, dsw: dl.scrollWidth, dcw: dl.clientWidth, ellipsis: cs.textOverflow,
                     inBlock: lb.left >= blk.left - 0.5 && lb.right <= blk.right + 0.5, beforeDirt: blk.right <= dw.left + 0.5, oneRow: hud.scrollHeight <= hud.clientHeight + 0.5 && hud.scrollWidth <= hud.clientWidth + 0.5,
                     title: q('#tanklvl').title }; })()""")
        page.locator("#hud").screenshot(path=shot("topbar_aquarium_lv12"))
        ev("G.tankInfo = G.__tankInfo; delete G.__tankInfo; clean();"); page.wait_for_timeout(80)
        check("AD v4 3 rename: top bar reads 'Aquarium Lv 12' (forced level 12) next to 'Dirt: max' on one row: label not clipped or ellipsed (scrollWidth <= clientWidth), inside its block, block left of the dirt window; tooltip says 'Aquarium level'",
              fit["label"] == "Aquarium Lv 12" and fit["dirt"] == "Dirt: max" and fit["sw"] <= fit["cw"] and fit["dsw"] <= fit["dcw"] and fit["inBlock"] and fit["beforeDirt"] and fit["oneRow"]
              and fit["title"].startswith("Aquarium level"), json.dumps(fit))
        ev("fresh(); G.state.tank.xp = 130;"); page.wait_for_timeout(150); page.screenshot(path=shot("aquarium_label_clean_no_timer"))
        vis = page.evaluate("document.body.innerText")
        check("rename: no player-facing 'Tank Lv' / 'Tank level' text on the main screen; 'Aquarium Lv 2' and 'Dirt: clean' shown with no countdown",
              "Tank Lv" not in vis and "Tank level" not in vis and "Aquarium Lv 2" in vis and "Dirt: clean" in vis and " in " not in page.evaluate("document.getElementById('dirt-win').innerText"), vis[:300])
        def dirt_txt():
            return page.evaluate("""(() => { const l = document.getElementById('dirt-label'), h = document.getElementById('hud'), w = document.getElementById('dirt-win');
              const a = l.getBoundingClientRect(), wr = w.getBoundingClientRect();
              return { label: l.textContent, next: !!document.getElementById('dirt-next'), winText: w.innerText.trim(), hudText: h.innerText,
                       clip: l.scrollWidth > l.clientWidth + 0.5 || a.right > wr.right + 0.5, oneLine: h.scrollHeight <= h.clientHeight + 0.5 }; })()""")
        dt = {}
        for key, js in [("clean", "clean(); G.state.dirt.t = T.dirt.stageAtSec[0] - 30;"), ("s2", "toStage(2); G.state.dirt.t = T.dirt.stageAtSec[2] - 30;"),
                        ("s4", "toStage(4); G.state.dirt.t = T.dirt.stageAtSec[3] + 30;"), ("max", "toStage(5);")]:
            ev(js); page.wait_for_timeout(80); dt[key] = dirt_txt()
        ev("toStage(4); G.state.dirt.t = T.dirt.stageAtSec[3] + 30;"); page.wait_for_timeout(80); page.locator("#hud").screenshot(path=shot("topbar_dirt_stage4"))
        ev("toStage(5);"); page.wait_for_timeout(80); page.locator("#hud").screenshot(path=shot("topbar_dirt_max"))
        import re as _re
        timer_re = _re.compile(r"(Stage \d+ in|Next stage|\d+h \d+m|<1m|Max dirt)")
        check("v6.1 / AD v4 3: dirt window shows the stage only: 'Dirt: clean', 'Dirt: stage 2 of 5', 'Dirt: stage 4 of 5', 'Dirt: max' at stage 5 (one line, no clipping); "
              "no countdown / 'Next stage in' text anywhere in the top bar and no timer element (showTimerToNextStage false)",
              tj["dirt"]["showTimerToNextStage"] is False and dt["clean"]["label"] == "Dirt: clean" and dt["s2"]["label"] == "Dirt: stage 2 of 5" and dt["s4"]["label"] == "Dirt: stage 4 of 5"
              and dt["max"]["label"] == "Dirt: max" and all(not q["next"] and q["winText"] == q["label"] and not timer_re.search(q["hudText"]) and not q["clip"] and q["oneLine"] for q in dt.values()),
              json.dumps(dt))
        jm = ev("""clean(); G.state.dirt.t = 3600 - 30; G.state.food = 20; const f = G.buyFish('guppy'); f.state = 'HUNGRY'; f.fed = 0; f.hungerDone = true; f.progress = 90; f.deathLeft = G.deathSecFor(G.SPECIES.guppy, 1);
          const t0 = G.state.dirt.t; feedFull(f); return { dt: G.state.dirt.t - t0 };""")
        page.wait_for_timeout(80); after_meal = dirt_txt()
        check("v6.1: a meal still moves the hidden dirt clock 5 minutes at once, and no timer text appears", abs(jm["dt"] - 300) < 1 and not timer_re.search(after_meal["hudText"]), json.dumps([jm, after_meal]))
        # tank drawing geometry + pixels
        ev("fresh(); G.state.speed = 1;"); page.wait_for_timeout(350)
        gm = page.evaluate("AQ.geom()"); tb = box()
        exp_surf = max(16, 0.07 * gm["H"])
        png = page.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); pw, ph, px = png_rgb(png); k_ = pw / tb["width"]
        P = lambda x, y: px(int(x * k_), int(y * k_))
        air = P(gm["W"] * 0.33, gm["surf"] * 0.45); water = P(gm["W"] * 0.33, gm["surf"] + 30)
        xr = gm["W"] - gm["inset"]; yl = (gm["surf"] + gm["sand"]) / 2
        line_px, beside = P(xr, yl), P(xr - 9, yl)
        surf_px = max((P(gm["W"] * 0.66, gm["surf"] + d) for d in (-2, -1, 0, 1, 2)), key=sum)  # Large tanks: the 1px surface can fall between ±1 samples
        check("AD v4 4: air gap = top 7% (min 16px: 21 / 49px) filled darker than the water; sand top at 86%; glass lines inset 3.5% of W",
              abs(gm["surf"] - exp_surf) < 0.01 and abs(gm["surf"] - max(16, 0.07 * gm["H"])) < 0.01 and abs(gm["sand"] - min(0.86 * gm["H"], gm["H"] - 36)) < 0.01 and abs(gm["inset"] - 0.035 * gm["W"]) < 0.01
              and sum(air) < sum(water) - 150 and air[2] < 110, json.dumps({"geom": gm, "air": air, "water": water}))
        check("AD v4 4: water surface line is visible (lighter than the water under it)", sum(surf_px) > sum(water) + 40, json.dumps({"surface": surf_px, "water": water}))
        # square tank corners (Maksims 19:57, AD v4 4 updated 19:58): radius 0 on frame, canvas, water and sand
        rad = page.evaluate("['tank-wrap', 'tank'].map((id) => { const c = getComputedStyle(document.getElementById(id)); return [c.borderTopLeftRadius, c.borderTopRightRadius, c.borderBottomRightRadius, c.borderBottomLeftRadius]; })")
        dif = lambda p, q: sum(abs(u - v) for u, v in zip(p, q))
        Wt, Ht = gm["W"], gm["H"]
        # corner pixel vs its nearest tank neighbours (min diff: sand pebbles vary); a rounded corner would show frame
        # there. The bottom (sand) corners must also be far from the frame colours (#1d4b6b / #0b2233).
        def near(cx, cy, sx, sy): return min(dif(P(cx, cy), P(cx + sx * a, cy + sy * b)) for a, b in ((2.5, 2.5), (5, 0), (0, 5), (1.5, 0), (0, 1.5)))
        corners = {"tl": near(0.3, 0.3, 1, 1), "tr": near(Wt - 0.7, 0.3, -1, 1), "bl": near(0.3, Ht - 0.7, 1, -1), "br": near(Wt - 0.7, Ht - 0.7, -1, -1)}
        frame_d = {k: min(dif(P(*xy), (0x1d, 0x4b, 0x6b)), dif(P(*xy), (0x0b, 0x22, 0x33))) for k, xy in (("bl", (0.3, Ht - 0.7)), ("br", (Wt - 0.7, Ht - 0.7)))}
        clips = page.evaluate("['tank-wrap', 'tank'].map((id) => getComputedStyle(document.getElementById(id)).clipPath)")
        check("Maksims / AD v4 4: tank corners are SQUARE: border-radius 0 and no clip-path on the tank frame and canvas; the very corner pixels are tank (air / sand), not frame",
              all(r == "0px" for rr in rad for r in rr) and all(c == "none" for c in clips) and all(v < 30 for v in corners.values()) and all(v > 120 for v in frame_d.values()),
              json.dumps({"radius": rad, "clip": clips, "cornerDiff": corners, "sandCornerVsFrame": frame_d}))
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
        page.evaluate("['toasts', 'hint'].forEach((id) => document.getElementById(id).style.visibility = 'hidden')")  # DOM pills over a spot centre would hide it in both shots
        sp1 = page.evaluate("AQ.spotsScreen()"); gm = page.evaluate("AQ.geom()")
        png = page.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); pw, ph, px = png_rgb(png); k_ = pw / tb["width"]
        ev("clean();"); page.wait_for_timeout(250)
        png0 = page.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); _w0, _h0, px0 = png_rgb(png0)
        diffs = [sum(abs(a_ - b_) for a_, b_ in zip(px(int(q["x"] * k_), int(q["y"] * k_)), px0(int(q["x"] * k_), int(q["y"] * k_)))) for q in sp1]
        check("AD v4 21: stage 1 = 3 spots (dirt.spots[0]), radius 0.10-0.14 of the water height, each clearly visible against clean water (colour change > 40 at its centre)",
              len(sp1) == tj["dirt"]["spots"][0] == 3 and all(0.10 * gm["waterH"] - 0.01 <= q["r"] <= 0.14 * gm["waterH"] + 0.01 for q in sp1) and min(diffs) > 40, json.dumps({"r": [round(q["r"], 1) for q in sp1], "diff": diffs}))
        page.evaluate("['toasts', 'hint'].forEach((id) => document.getElementById(id).style.visibility = '')")
        ev("toStage(1);"); page.wait_for_timeout(250); page.screenshot(path=shot("stage1_dirt")); ev("clean();")
        check("AD v4 6: sponge radius = 0.16 x water height clamped 40-72px", abs(gm["spongeR"] - max(40, min(72, 0.16 * gm["waterH"]))) < 0.01, str(gm["spongeR"]))
        # shop: centred panel, tabs, close pill, food packs, decorations
        ev("fresh(); G.state.gold = 1000; G.state.tank.xp = 5000; G.state.speed = 1;"); page.wait_for_timeout(100)
        page.click("#btn-shop"); page.wait_for_timeout(300)
        sh = page.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const k = r('#tank-wrap'), s = r('#shop'), c = r('#shop-close');
            const cols = getComputedStyle(document.getElementById('shop-list')).gridTemplateColumns.split(' ').length;
            return { w: s.width, h: s.height, cx: (s.left + s.right) / 2 - (k.left + k.right) / 2, top: s.top - k.top, tankW: k.width, tankH: k.height, closeW: c.width, closeH: c.height,
                     closeCx: (c.left + c.right) / 2 - (s.left + s.right) / 2, closeBottom: s.bottom - parseFloat(getComputedStyle(document.getElementById('shop')).borderBottomWidth) - c.bottom, cols, tabs: [...document.querySelectorAll('#shop .tab')].map((t) => t.textContent),
                     title: document.querySelector('#shop h2').textContent, xp: /XP|Tank Lv|Aquarium Lv/.test(document.getElementById('shop').innerText), closeText: document.getElementById('shop-close').textContent,
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
        # ---- Food packs v6.7: unlockTankLevel 1/2/4/6, foodPackLockedLabel, buyable when unlocked ----
        # xp thresholds: Lv1=0, Lv2=60, Lv4=1200, Lv6=10000, Lv9=65000 (read from tank.levelAtXp)
        lvxp = lambda lv: tj["tank"]["levelAtXp"][lv - 1]
        def open_food(xp):
            ev(f"G.state.tank.xp = {xp}; G.state.gold = 1000; G.state.food = 0;"); page.wait_for_timeout(60)
            if not page.locator("#shop").is_visible():
                page.click("#btn-shop"); page.wait_for_timeout(120)
            page.click('#shop .tab[data-tab="food"]'); page.wait_for_timeout(120)
            return page.evaluate("""[...document.querySelectorAll('#shop-food .card')].map((c) => {
              const b = c.querySelector('button[data-food]'), n = c.querySelector('.n'), s = c.querySelector('.s'), lbl = b.querySelector('.lbl'), pr = b.querySelector('.price');
              const cr = c.getBoundingClientRect(), lr = lbl.getBoundingClientRect(), nr = n.getBoundingClientRect();
              const lh = parseFloat(getComputedStyle(n).lineHeight) || parseFloat(getComputedStyle(n).fontSize) * 1.3;
              const llh = parseFloat(getComputedStyle(lbl).lineHeight) || parseFloat(getComputedStyle(lbl).fontSize) * 1.3;
              return { n: n.textContent, s: s.textContent, price: pr.hidden ? null : pr.textContent, lbl: lbl.textContent,
                       locked: c.classList.contains('locked'), disabled: b.disabled, hidden: c.hidden,
                       nFits: n.scrollWidth <= n.clientWidth + 0.5 && nr.height <= lh * 1.5,
                       lblFits: !lbl.textContent || (lbl.scrollWidth <= lbl.clientWidth + 0.5 && lr.height <= llh * 1.6 && lr.right <= cr.right + 0.5) }; })""")
        def packs_reachable():
            # every pack card: scroll it into view inside #shop-scroll, then its whole button must be inside the scroll box,
            # above the Close pill, and hit-test to itself; no horizontal overflow of the grid
            return page.evaluate("""(() => { const sc = document.getElementById('shop-scroll'), close = document.getElementById('shop-close'); const out = [];
              document.querySelectorAll('#shop-food .card').forEach((c) => { const b = c.querySelector('button[data-food]');
                b.scrollIntoView({ block: 'nearest' }); const cl = close.getBoundingClientRect(); if (b.getBoundingClientRect().bottom > cl.top) sc.scrollTop += b.getBoundingClientRect().bottom - cl.top + 4;
                const r = b.getBoundingClientRect(), s = sc.getBoundingClientRect(), k = close.getBoundingClientRect();
                const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
                out.push({ i: +b.dataset.food, inside: r.top >= s.top - 0.5 && r.bottom <= s.bottom + 0.5 && r.left >= s.left - 0.5 && r.right <= s.right + 0.5,
                           clearOfClose: r.bottom <= k.top + 0.5 || r.right <= k.left || r.left >= k.right, hit: !!hit && (hit === b || b.contains(hit)) }); });
              sc.scrollTop = 0; return { cards: out, hOverflow: sc.scrollWidth > sc.clientWidth + 0.5 }; })()""")
        want = ["5 food · 3 gold", "10 food · 5 gold", "50 food · 20 gold", "250 food · 75 gold", "500 food · 125 gold"]
        want_s = ["0.6 gold per food", "0.5 gold per food", "0.4 gold per food", "0.3 gold per food", "0.25 gold per food"]
        lock_lbl = lambda n: (tj.get("foodPackLockedLabel") or "Unlocks at Aquarium Lv {N}").replace("{N}", str(n))
        # Lv1 (xp 0): only the 5-food pack buyable; others visible, greyed, locked label where the price was
        p1 = open_food(lvxp(1)); reach1 = packs_reachable()
        check("v6.7 Food packs (5, rendered from tuning): unlockTankLevel 1/2/4/6/9, foodPackLockedLabel, foodPackLockedShown; labels '5 food · 3 gold' and locked labels fit; every pack button reachable (scroll, not under Close), no sideways overflow",
              closed and ver_at_least(tj, "6.7") and tj.get("foodPackLockedShown") is True
              and tj.get("foodPackLockedLabel") == "Unlocks at Aquarium Lv {N}"
              and [[p["food"], p["gold"], p["unlockTankLevel"]] for p in tj["foodPacks"]] == [[5, 3, 1], [10, 5, 2], [50, 20, 4], [250, 75, 6], [500, 125, 9]] and len(p1) == len(tj["foodPacks"]) == 5
              and [c["n"] for c in p1] == want and [c["s"] for c in p1] == want_s and all(c["nFits"] for c in p1)
              and [c["locked"] for c in p1] == [False, True, True, True, True] and not any(c["hidden"] for c in p1)
              and [c["price"] for c in p1] == ["3", None, None, None, None]
              and [c["lbl"] for c in p1] == ["", lock_lbl(2), lock_lbl(4), lock_lbl(6), lock_lbl(9)]
              and all(c["lblFits"] for c in p1) and not reach1["hOverflow"] and all(r["inside"] and r["clearOfClose"] and r["hit"] for r in reach1["cards"]) and len(reach1["cards"]) == 5, json.dumps([p1, reach1]))
        g0, f0 = S()["gold"], S()["food"]
        page.click('#shop-food button[data-food="0"]'); page.wait_for_timeout(80)
        g1, f1 = S()["gold"], S()["food"]
        # tapping a locked pack does nothing (button disabled; gold/food unchanged; buyFood returns false)
        page.click('#shop-food button[data-food="1"]', force=True); page.wait_for_timeout(60)
        page.click('#shop-food button[data-food="2"]', force=True); page.wait_for_timeout(60)
        page.click('#shop-food button[data-food="3"]', force=True); page.wait_for_timeout(60)
        page.locator('#shop-food button[data-food="4"]').scroll_into_view_if_needed(); page.click('#shop-food button[data-food="4"]', force=True); page.wait_for_timeout(60)
        locked_tap = page.evaluate("({ gold: AQ.game.state.gold, food: AQ.game.state.food, buy: AQ.game.buyFood(3) || AQ.game.buyFood(4) })")
        check("v6.7 Lv1: only 5-food pack buyable (3 gold -> 5 food); tapping locked 10/50/250/500 does nothing",
              (g0 - g1, f1 - f0) == (3, 5) and locked_tap == {"gold": g1, "food": f1, "buy": False}, json.dumps([g0, g1, f0, f1, locked_tap]))
        page.screenshot(path=shot("shop_food_lv1"))
        # Lv2 (xp 60): 10-food unlocks
        p2 = open_food(lvxp(2))
        check("v6.7 Lv2: 10-food pack unlocks (5 still open; 50/250/500 still locked with label)",
              [c["locked"] for c in p2] == [False, False, True, True, True] and p2[1]["price"] == "5" and p2[2]["lbl"] == lock_lbl(4), json.dumps(p2))
        page.click('#shop-food button[data-food="1"]'); page.wait_for_timeout(80)
        check("v6.7 Lv2 buy 10-food: -5 gold +10 food", (S()["gold"], S()["food"]) == (1000 - 5, 10), json.dumps(S()))
        # Lv4 (xp 1200): 50-food unlocks
        p4 = open_food(lvxp(4))
        check("v6.7 Lv4: 50-food pack unlocks (250/500 still locked)",
              [c["locked"] for c in p4] == [False, False, False, True, True] and p4[2]["price"] == "20" and p4[3]["lbl"] == lock_lbl(6) and p4[3]["lblFits"], json.dumps(p4))
        page.click('#shop-food button[data-food="2"]'); page.wait_for_timeout(80)
        check("v6.7 Lv4 buy 50-food: -20 gold +50 food", (S()["gold"], S()["food"]) == (1000 - 20, 50), json.dumps(S()))
        page.screenshot(path=shot("shop_food"))
        # Lv6 (xp 10000): 250-food unlocks
        p6 = open_food(lvxp(6))
        check("v6.7 Lv6: 250-food pack unlocks (75 gold); 500 still locked 'Unlocks at Aquarium Lv 9'",
              [c["locked"] for c in p6] == [False, False, False, False, True] and [c["price"] for c in p6] == ["3", "5", "20", "75", None] and [c["lbl"] for c in p6] == ["", "", "", "", lock_lbl(9)] and p6[4]["lblFits"], json.dumps(p6))
        g4 = S()["gold"]; page.click('#shop-food button[data-food="3"]'); page.wait_for_timeout(80)
        check("v6.7 Lv6 buy 250-food: -75 gold +250 food",
              S()["gold"] == g4 - 75 and S()["food"] == 250, json.dumps(S()))
        # Lv8 (xp levelAtXp[7]): 500 still locked; Lv9: 500-food unlocks
        p8 = open_food(lvxp(8))
        p9 = open_food(lvxp(9)); reach9 = packs_reachable()
        check("v6.7 Lv9: 500-food pack unlocks (locked at Lv8); all five packs open with prices 3/5/20/75/125, all reachable",
              p8[4]["locked"] is True and [c["locked"] for c in p9] == [False] * 5 and [c["price"] for c in p9] == ["3", "5", "20", "75", "125"] and all(c["lbl"] == "" for c in p9)
              and not reach9["hOverflow"] and all(r["inside"] and r["clearOfClose"] and r["hit"] for r in reach9["cards"]), json.dumps([p8[4], p9, reach9]))
        page.locator('#shop-food button[data-food="4"]').scroll_into_view_if_needed()
        g9 = S()["gold"]; page.click('#shop-food button[data-food="4"]'); page.wait_for_timeout(80)
        check("v6.7 Lv9 buy 500-food: -125 gold +500 food", S()["gold"] == g9 - 125 and S()["food"] == 500, json.dumps(S()))
        page.evaluate("document.getElementById('shop-scroll').scrollTop = 1e6"); page.wait_for_timeout(100)
        page.screenshot(path=shot("shop_food_lv9_scrolled"))
        page.click('#shop .tab[data-tab="decor"]'); page.wait_for_timeout(150)
        dec = page.evaluate("[...document.querySelectorAll('#shop-decor .card')].map((c) => [c.querySelector('.n').textContent, c.querySelector('.price').textContent])")
        page.screenshot(path=shot("shop_decorations"))
        # decorations: defaults, buying opens edit mode on the new one
        d0 = page.evaluate("AQ.decorScreen()")
        check("v6.8 NUMBERS 7: a new tank starts empty (newTank.defaultDecorations [], no starter stone / leaves)",
              d0 == [] and ev("return G.newState().decor.length === 0;"), json.dumps(d0))
        page.click('#shop-decor button[data-buydecor="leaf"]'); page.wait_for_timeout(250)
        ed = page.evaluate("AQ.edit()"); dn = page.evaluate("AQ.decorScreen()")[-1]
        toasts_ = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)")
        check("bible 25 / 27 + v6.8 (leaf exception): Decorations tab offers Leaf for 1 gold and Stone for 2 gold (then the 10 shop decorations); buying places it at the floor centre, opens edit mode, selects it and opens its menu",
              dec[:2] == [["Leaf", "1"], ["Stone", "2"]] and len(dec) == 12 and not page.locator("#shop").is_visible() and ed["editing"] and ed["selDecor"] == dn["id"] and ed["menu"] and abs(dn["x"] - 0.5) < 1e-9
              and "Tap a decoration to change it" in toasts_ and page.locator('.tool[data-tool="brush"]').get_attribute("aria-pressed") == "true", json.dumps([dec, ed, dn["x"], toasts_]))
        page.screenshot(path=shot("edit_mode_menu"))
        mr = ed["menu"]; tk_ = ed["tank"]; dnb = ed["done"]
        check("AD v4 7 (2026-09-28 sizes): side menu 296x284 / 392x368 docked 8px from the tank top and side; Done button 72x32 / 96x40 in a top corner 8px in, not covered by the menu",
              abs(mr["w"] - (392 if LARGE else 296)) < 0.5 and abs(mr["h"] - (368 if LARGE else 284)) < 0.5 and abs(mr["y"] - tk_["y"] - 8) < 0.5
              and (abs(mr["x"] - tk_["x"] - 8) < 0.5 or abs(tk_["x"] + tk_["w"] - mr["x"] - mr["w"] - 8) < 0.5) and dnb and abs(dnb["w"] - (96 if LARGE else 72)) < 0.5 and abs(dnb["h"] - (40 if LARGE else 32)) < 0.5
              and abs(dnb["y"] - tk_["y"] - 8) < 0.5 and (dnb["x"] + dnb["w"] <= mr["x"] or dnb["x"] >= mr["x"] + mr["w"]), json.dumps([mr, dnb, tk_]))
        # the menu never covers the decoration it edits: every decoration, at 1.0x and at 2.0 x 2.0
        cover = []
        for scale in (1.0, 2.0):
            for q in page.evaluate("AQ.decorScreen()"):
                ev(f"const d = G.state.decor.find((x) => x.id === '{q['id']}'); d.sh = {scale}; d.sw = {scale}; AQ.selectDecor(d.id);"); page.wait_for_timeout(40)
                e_ = page.evaluate("AQ.edit()"); g_ = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == q["id"]); m_ = e_["menu"]
                mx0, my0 = m_["x"] - e_["tank"]["x"], m_["y"] - e_["tank"]["y"]
                def ov(x0):  # overlap area of the decoration box with a menu docked at x0
                    ox = min(g_["x1"], x0 + m_["w"]) - max(g_["x0"], x0); oy = min(g_["y1"], my0 + m_["h"]) - max(g_["y0"], my0)
                    return ox * oy if ox > 0 and oy > 0 else 0
                here, other = ov(mx0), ov(e_["tank"]["w"] - 8 - m_["w"] if mx0 < e_["tank"]["w"] / 2 else 8)
                # 2026-09-28: the menu is never scaled (touch targets / gaps in CSS px), so a 2.0x decoration wider than the strip between
                # the two dock positions can't be cleared; then it must dock on the side that covers the least of it. Otherwise: never covers.
                if (here > 0 and (scale == 1.0 or other == 0 or other < here)) or m_["w"] < 1: cover.append([q["id"], scale, round(here), round(other)])
        ev("G.state.decor.forEach((d) => { d.sh = 1; d.sw = 1; });")
        check("AD v4 7: the side menu docks away from the decoration (centre x > 50% -> left) and never covers it at 1.0x; at 2.0x it flips to a clear side, or (no clear side, menu never scaled) covers the least",
              not cover, json.dumps(cover))
        # move / size / colour / sell
        did_ = dn["id"]; ev(f"AQ.selectDecor('{did_}');"); page.wait_for_timeout(60)
        x_a = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["bx"]
        page.click('#deco-menu [data-move="right"]'); page.wait_for_timeout(60)
        x_b = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["bx"]
        rb = page.locator('#deco-menu [data-move="left"]').bounding_box()
        page.mouse.move(rb["x"] + rb["width"] / 2, rb["y"] + rb["height"] / 2); page.mouse.down(); page.wait_for_timeout(700); page.mouse.up(); page.wait_for_timeout(60)
        x_c = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["bx"]
        steps_held = round((x_b - x_c) / 8)
        # vertical: 4px per tap (Maksims 20:34, stepPxPerTapY), same hold-repeat
        ev(f"const d = G.state.decor.find((x) => x.id === '{did_}'); d.y = 1.2; AQ.selectDecor(d.id);"); page.wait_for_timeout(60)
        y_a = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["by"]
        page.click('#deco-menu [data-move="down"]'); page.wait_for_timeout(60)
        y_b = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["by"]
        rb = page.locator('#deco-menu [data-move="up"]').bounding_box()
        page.mouse.move(rb["x"] + rb["width"] / 2, rb["y"] + rb["height"] / 2); page.mouse.down(); page.wait_for_timeout(700); page.mouse.up(); page.wait_for_timeout(60)
        y_c = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == did_)["by"]
        vsteps = (y_b - y_c) / 4
        check("AD v4 7 + Maksims 20:34: a Move tap moves 8px left/right and 4px up/down; holding repeats every 80ms after 300ms (0.7 s hold = about 6 steps) at the same step sizes",
              abs(x_b - x_a - 8) < 0.01 and 4 <= steps_held <= 7 and abs(y_b - y_a - 4) < 0.01 and 4 <= round(vsteps) <= 7 and abs(vsteps - round(vsteps)) < 0.01,
              f"x tap {x_b - x_a:.2f}px, x held {steps_held} steps; y tap {y_b - y_a:.2f}px, y held {vsteps:.2f} steps of 4px")
        # Maksims 20:12: move-DOWN runs the decoration's BASE all the way to the sand's front edge (the tank bottom / front
        # glass) at every size; it stays fully visible (full height above the base, top inside the water, not clipped)
        front, fshots = [], []
        sid_ = ev("G.state.gold += 10; const s = G.buyDecor('stone'); s.x = 0.75; return s.id;")
        for dq in (did_, sid_):   # the new leaf and a bought stone (v6.8: no default stone any more)
            for sc in (0.5, 1.0, 2.0):
                ev(f"const d = G.state.decor.find((x) => x.id === '{dq}'); d.sh = {sc}; d.sw = {sc}; d.y = 0; AQ.selectDecor(d.id);"); page.wait_for_timeout(60)
                prev, presses = None, 0
                for _k in range(60):
                    page.click('#deco-menu [data-move="down"]'); presses += 1
                    cur = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == dq)["by"]
                    if prev is not None and abs(cur - prev) < 1e-6: break
                    prev = cur
                gq = page.evaluate("AQ.geom()"); z = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == dq)
                full_h = (z["h"] if z["type"] == "leaf" else z["h"] * (1 - 0.15))
                exp_h = min(0.30 * gq["waterH"] * sc, z["by"] - gq["surf"] - 0.04 * gq["waterH"]) if z["type"] == "leaf" else 0.11 * gq["waterH"] * sc * 0.85
                tbx = box(); sx, sy = z["bx"], z["by"] - (z["by"] - z["y0"]) * 0.3
                pngA = page.screenshot(clip={"x": tbx["x"], "y": tbx["y"], "width": tbx["width"], "height": tbx["height"]}); _wA, _hA, pxA = png_rgb(pngA); kA = _wA / tbx["width"]
                if sc == 2.0: page.screenshot(path=shot(f"decor_front_{z['type']}_2x"))
                ev(f"const d = G.state.decor.find((x) => x.id === '{dq}'); d._x = d.x; d.x = -5;"); page.wait_for_timeout(60)
                pngB = page.screenshot(clip={"x": tbx["x"], "y": tbx["y"], "width": tbx["width"], "height": tbx["height"]}); _wB, _hB, pxB = png_rgb(pngB)
                ev(f"const d = G.state.decor.find((x) => x.id === '{dq}'); d.x = d._x; delete d._x;"); page.wait_for_timeout(40)
                vis_d = sum(abs(a - b) for a, b in zip(pxA(int(sx * kA), int(sy * kA)), pxB(int(sx * kA), int(sy * kA))))
                front.append({"id": dq, "type": z["type"], "size": sc, "presses": presses, "gap": round(gq["H"] - z["by"], 3), "visH": round(z["by"] - z["y0"], 1), "expH": round(exp_h, 1),
                              "top": round(z["y0"], 1), "surf": round(gq["surf"], 1), "x0": round(z["x0"], 1), "x1": round(z["x1"], 1), "W": gq["W"], "pxDiff": vis_d})
        ev("G.state.decor.forEach((d) => { d.sh = 1; d.sw = 1; });"); ev(f"AQ.selectDecor('{did_}');"); page.wait_for_timeout(60)
        check("Maksims 20:12: move-down takes a decoration's BASE to the sand's front edge (gap <= 1px) at 0.5x / 1.0x / 2.0x, leaf and stone; still fully visible (full height, top in the water, inside the glass, drawn)",
              all(0 <= q["gap"] <= 1 and abs(q["visH"] - q["expH"]) < 0.6 and q["top"] > q["surf"] and q["x0"] >= 0 and q["x1"] <= q["W"] and q["pxDiff"] > 40 for q in front) and len(front) == 6,
              json.dumps(front))
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
        check("AD v4 7 + v6.8: 'Sell · refund 1 gold' asks 'Sell this leaf? You get 1 gold back.', then removes it (leaf sellRefundOverride: the full 1 gold paid)",
              sell_t == "Sell this leaf? You get 1 gold back." and sell_btn == "Sell · refund 1 gold" and len(S()["decor"]) == n_before - 1 and S()["gold"] == gd + 1 and not page.locator("#deco-menu").is_visible(), json.dumps([sell_t, sell_btn]))
        # edit mode: fish can't be tapped; Done exits; another tool exits
        fe = ev("const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.45, 0.4); return f.id;"); page.wait_for_timeout(150)
        pos_ = page.evaluate(f"AQ.fishScreen({fe})"); tank_click(pos_["x"], pos_["y"]); page.wait_for_timeout(150)
        no_panel = not page.locator("#panel").is_visible()
        page.click("#deco-done"); page.wait_for_timeout(100); ex1 = page.evaluate("AQ.edit()")
        tool("brush"); page.wait_for_timeout(60); tool("food"); page.wait_for_timeout(60); ex2 = page.evaluate("AQ.edit()")
        check("bible 26 / AD v4 7: in edit mode fish can't be tapped; Done leaves edit mode (back to Look); choosing another tool also leaves it",
              no_panel and not ex1["editing"] and ex1["done"] is None and page.locator('.tool[data-tool="food"]').get_attribute("aria-pressed") == "true" and not ex2["editing"], json.dumps([ex1, ex2]))
        # max 12 decorations, persistence
        ev("G.state.gold += 100; while (G.state.decor.length < 12) G.buyDecor('stone'); G.state.decor[0].x = 0.3; G.state.decor[0].sh = 1.4; G.state.decor[0].color = 70; G.save();")
        page.click("#btn-shop"); page.wait_for_timeout(150); page.click('#shop .tab[data-tab="decor"]'); page.wait_for_timeout(120)
        full_d = page.evaluate("[...document.querySelectorAll('#shop-decor button')].map((b) => [b.disabled, b.innerText.trim()])"); refused = ev("return G.buyDecor('leaf') === null && G.state.decor.length === 12;")
        page.click("#shop-close"); snap_d = S()["decor"]
        boot("?speed=1"); after_d = S()["decor"]
        check("v4 7: max 12 decorations (Buy disabled with 'Tank is full of decorations'); decorations keep position, size and colour across a reload",
              all(d_ and (t_ == "Tank is full of decorations" or t_.startswith("Unlocks at Aquarium Lv")) for d_, t_ in full_d) and any(t_ == "Tank is full of decorations" for d_, t_ in full_d) and refused and after_d == snap_d and after_d[0]["x"] == 0.3 and after_d[0]["sh"] == 1.4 and after_d[0]["color"] == 70, json.dumps(full_d))
        # fish info side panel geometry + meal bar
        fp = ev("""fresh(); G.state.tank.xp = 5000; G.state.gold = 1000; const f = G.buyFish('platy');
          f.level = 3; f.state = 'HUNGRY'; f.fed = 0; f.hungerDone = true; f.endMeal = true; f.progress = G.growSec(G.SPECIES.platy, 3); f.deathLeft = G.deathSecFor(G.SPECIES.platy, 3);
          AQ.pinFish(f.id, 0.3, 0.5); G.feedTap(f.x, f.y); return f.id;""")
        page.wait_for_timeout(150); tool("hand"); click_fish(fp); page.wait_for_timeout(250)
        pn = page.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const k = r('#tank-wrap'), p = r('#panel');
            return { w: p.width, h: p.height, right: k.right - p.right, top: p.top - k.top, tankH: k.height, overflowY: getComputedStyle(document.getElementById('panel')).overflowY,
                     meal: document.getElementById('p-meal').textContent, segs: [...document.querySelectorAll('#p-mealbar i')].map((e) => e.classList.contains('on')),
                     segH: document.querySelector('#p-mealbar i') ? document.querySelector('#p-mealbar i').getBoundingClientRect().height : 0, worth: document.getElementById('p-worth').textContent }; })()""")
        page.screenshot(path=shot("fish_info_meal"))
        check("AD v4 8 / bible 18: fish info docks right (300 / 380 wide, tank height - 16, scrolls); v6.3 L3 Platy end meal after 1 tap 'Meal 2 of 2 · needs 2 food' with a 3-segment 10px bar (1 filled), still L3 'Worth 225 gold'",
              abs(pn["w"] - (380 if LARGE else 300)) < 0.5 and abs(pn["h"] - (pn["tankH"] - 16)) < 0.5 and abs(pn["right"] - 8) < 0.5 and abs(pn["top"] - 8) < 0.5 and pn["overflowY"] == "auto"
              and pn["meal"] == "Meal 2 of 2 · needs 2 food" and pn["segs"] == [True, False, False] and abs(pn["segH"] - 10) < 0.5 and pn["worth"] == "Worth 225 gold", json.dumps(pn))
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
        check("Designer check (a, v6.5): cleaning at stage 1 earns the most gold per day, 64/56/48/40/32 (4/7/12/20/32 over 1.5/3/6/12/24 h), falling with every stage",
              per_day == [64, 56, 48, 40, 32] and all(per_day[i] < per_day[i - 1] for i in range(1, 5)) and all(per_day[i] <= per_day[i - 1] for i in range(1, 5)) and bc["cleanOk"] and bc["cleanPerDay"] == per_day, str(per_day))
        # Designer check (b, v6 10): profit(L) = sell(L) + level-up gold up to L - price - food eaten up to L.
        # v6.3 food to level L: mid + end meal (= mealFood[L-1] total) of every finished level (6 meals to L4). Food at the dearest pack per food (v6.7: 0.6 g).
        # L4 must profit and beat L3 for every species.
        food_val = max(p["gold"] / p["food"] for p in tj["foodPacks"])
        prof = {}
        for sp in tj["species"]:
            port = sp["mealFood"]; rows = []; food = 0; feeds = 0; lvl_gold = 0
            for L in range(1, 5):
                if L > 1:
                    n = 2  # v6.3: every finished level = mid + end meal, together mealFood[L-1]
                    food += port[L - 2]; feeds += n; lvl_gold += sp["levelUpGold"][L - 2]
                no_food = sp["sell"][L - 1] + lvl_gold - sp["price"]
                rows.append((round(no_food - food * food_val + tj["feedGoldPerFish"] * feeds, 2), no_food, food))
            prof[sp["id"]] = rows
        ok_b = all(rows[3][0] > 0 and rows[3][0] > rows[2][0] for rows in prof.values())
        l4ph = [round(prof[s_["id"]][3][0] / (sum(s_["growSec"]) / 3600), 1) for s_ in tj["species"]]
        check("Designer check (b, v6.7 10): L4 profit beats L3 for every species (food at 0.6 g: Guppy L3 +10 / L4 +21.6; food to L4 = 2+3+4 = 9); game's L4 profit per hour matches",
              ok_b and bc["sellOk"] and food_val == 0.6 and [prof["guppy"][i][0] for i in (2, 3)] == [10.0, 21.6] and prof["guppy"][3][2] == 9
              and [r_["l4perHour"] for r_ in bc["sell"]] == l4ph and [r_["rows"][3]["food"] for r_ in bc["sell"]] == [sum(s_["mealFood"][:3]) for s_ in tj["species"]],
              json.dumps({"prof": {k: [r[0] for r in v] for k, v in list(prof.items())[:4]}, "l4ph": l4ph}))

        # v6 9 first session: new tank -> first clean -> buy a Guppy -> five meals to adult -> sell
        sl = ev("""G.reset(); const rows = []; const snap = (k) => rows.push([k, G.state.gold, G.state.food, G.state.tank.xp]);
          snap('start'); rubAll(1.01); snap('clean'); const a = G.buyFish('guppy'); snap('buy'); const d0 = G.state.dirt.t; let t = 0, meals = 0;
          while (a.level < 4 && t < 5000) { G.tick(1); t++; if (a.state === 'HUNGRY') { feedFull(a); meals++; } }
          snap('adult'); const lvl = G.tankInfo().level, dirtMoved = G.state.dirt.t - d0 - t; G.sell(a.id); snap('sold');
          return { rows, meals, lvl, dirtMoved, grow: t, adultState: a.state };""")
        check("v6.3 first session: start 0/0/0 -> clean 20/50/5 -> buy Guppy 0/50/5 -> six meals (9 food) to adult 7/41/81 (Aquarium Lv2) -> sell 47/41/161; meals moved dirt 30 min",
              [r_[1:] for r_ in sl["rows"]] == [[0, 0, 0], [20, 50, 5], [0, 50, 5], [7, 41, 81], [47, 41, 161]] and sl["meals"] == 6 and sl["lvl"] == 2
              and sl["dirtMoved"] == 1800 and sl["grow"] == 1260 and sl["adultState"] == "ADULT", json.dumps(sl))

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
          const res = {
            looks, alphas: V.dirtStages.map((l) => l.alpha), radii: V.dirtStages.map((l) => l.r),
            everyStageStyled: spots.every((s) => s.stage >= 1 && s.stage <= 5 && !!looks[s.stage - 1]),
            radiusInRange: spots.every((s) => s.r >= V.dirtStages[s.stage - 1].r[0] - 1e-9 && s.r <= V.dirtStages[s.stage - 1].r[1] + 1e-9),
            countsOk: counts.every(Boolean), stage1NeverOver: spots.filter((s) => s.stage === 1).every((s) => s.over == null),
            overlapRate: +(ov.length / later.length).toFixed(2),
            overlapDistOk: ov.every((s) => s.d >= 0.4 - 1e-6 && s.d <= 1.6 + 1e-6 && s.olderOk),
            layer: V.dirtLayer, tint: [V.dirtStages[3].tintHalf, V.dirtStages[3].tintMix],
            film: { rgb: V.dirtFilm.rgb, centre: V.dirtFilm.centre, edge: V.dirtFilm.edge, scum: [V.dirtFilm.scumFrac, V.dirtFilm.scumAlpha] },
          };
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
        check("AD ruling 3 + v2: hair-algae patch 0.40, strands 0.5", a["hair"] == [0.40, 0.5], str(a["hair"]))
        fish_v7(page, ev, shot, box, tool, click_fish, tj)

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
        check("touch drags rub the tank clean (touch emulation), stage 1 pays +4 gold (v6.5)", st0 == 1 and tp.evaluate("AQ.game.dirtStage()") == 0 and tp.evaluate("AQ.game.state.gold") == gold0 + tj["dirt"]["cleanGold"][0],
              f"stage {st0}->{tp.evaluate('AQ.game.dirtStage()')}")
        # Maksims 2026-09-28: on touch the fingertip holds the wooden handle 60-70% of the way down it; the hoop sits up and
        # left of the finger; targeting uses the hoop centre; the mouse still centres the hoop on the cursor (checked above)
        nid = tp.evaluate("() => { const G = AQ.game; G.reset(); const d = G.state.dirt; d.t = 0; d.spots = []; d.spawned = 0; G.state.firstCleanPending = false; G.state.gold = 100; G.state.speed = 1; const f = G.buyFish('guppy'); f.level = 2; f.state = 'GROWING'; AQ.pinFish(f.id, 0.5, 0.5); return f.id; }")
        tp.wait_for_timeout(400); tp.tap('.tool[data-tool="net"]'); tp.wait_for_timeout(150); tb = tp.locator("#tank").bounding_box()
        fc_ = tp.evaluate(f"AQ.fishScreen({nid})"); R_ = tp.evaluate("AQ.net().r"); dgrip = R_ * (1 + 0.65 * 1.8)
        fx_, fy_ = fc_["x"] + dgrip * 0.7071, fc_["y"] + dgrip * 0.7071   # finger where the untilted grip point puts the hoop on the fish
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": tb["x"] + fx_ - 30, "y": tb["y"] + fy_}]})
        for t in range(1, 11):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": tb["x"] + fx_ - 30 + 3 * t, "y": tb["y"] + fy_}]})
            tp.wait_for_timeout(16)
        moving = tp.evaluate("AQ.net()")
        tp.wait_for_timeout(500); held = tp.evaluate("AQ.net()")
        def grip_of(n):   # where the fingertip sits along the handle (0 = hoop end, 1 = far end) and how far off its axis
            import math
            a_ = n["handleA"] + n["tilt"]; ux, uy = math.cos(a_), math.sin(a_); vx_, vy_ = n["fx"] - n["x"], n["fy"] - n["y"]
            along = vx_ * ux + vy_ * uy; perp = abs(-vx_ * uy + vy_ * ux)
            return {"frac": round((along - n["r"]) / (n["r"] * n["handleLen"]), 3), "perp": round(perp, 2), "hoopUpLeft": n["x"] < n["fx"] and n["y"] < n["fy"]}
        g_mv, g_held = grip_of(moving), grip_of(held)
        tp.screenshot(path=shot("net_touch_grip"))
        png_t = tp.screenshot(clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]}); _wt, _ht, pxt = png_rgb(png_t); kt = _wt / tb["width"]
        wood = pxt(int(held["fx"] * kt), int(held["fy"] * kt))
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); tp.wait_for_timeout(350)
        ctxt = tp.inner_text("#confirm-text") if tp.locator("#confirm").is_visible() else ""
        check("touch net: the fingertip sits on the wooden handle 60-70% of the way down it (held and while moving/tilted), the hoop is up-left of the finger and its centre picks the fish; letting go opens that fish's confirm",
              0.6 <= g_held["frac"] <= 0.7 and 0.6 <= g_mv["frac"] <= 0.7 and g_held["perp"] < 1 and g_mv["perp"] < 1 and g_held["hoopUpLeft"] and held["touch"]
              and held["target"] == nid and abs(held["x"] - fc_["x"]) < 3 and abs(held["y"] - fc_["y"]) < 3
              and wood[0] > 120 and wood[0] > wood[2] + 40 and ctxt == "Sell Guppy (L2) for 20 gold and 10 XP?",
              json.dumps({"held": g_held, "moving": g_mv, "tilt": [round(moving["tilt"], 3), round(held["tilt"], 3)], "hoop": [round(held["x"], 1), round(held["y"], 1)], "finger": [round(held["fx"], 1), round(held["fy"], 1)], "fish": fc_, "wood": wood, "confirm": ctxt}))
        if tp.locator("#confirm").is_visible(): tp.tap("#confirm-no")
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
        blk = page.evaluate("""(() => { const a = document.getElementById('rotate-icon').getBoundingClientRect(), b = document.getElementById('rotate-text').getBoundingClientRect();
            return [Math.min(a.left, b.left) - 4, Math.min(a.top, b.top) - 4, Math.max(a.right, b.right) + 4, Math.max(a.bottom, b.bottom) + 4]; })()""")
        bad, n = [], 0
        for y in range(0, h_, 6):
            for x in range(0, w_, 6):
                if blk[0] <= x <= blk[2] and blk[1] <= y <= blk[3]: continue  # the icon + text block itself (measured)
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

def fluid_layout():
    """Maksims 20:10: the layout is fluid. On any landscape viewport the debug row sits on the viewport bottom (bottom offset
    max(4px, safe-area) only) and the tank fills everything between the top bar and the debug row, and to the right padding."""
    VIEW[0] = "fluid"
    sizes = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (w, h) in ((844, 390), (1180, 820), (932, 430), (667, 375)):
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2, has_touch=True)
            page = ctx.new_page()
            page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(300)
            m = page.evaluate("""(() => { const r = (id) => document.getElementById(id).getBoundingClientRect(); const t = r('tank-wrap'), d = r('debug'), hud = r('hud'), c = r('tools'), dw = r('dirt-win');
                const tools = [...document.querySelectorAll('#tools .tool')].map((b) => b.getBoundingClientRect());
                return { vw: innerWidth, vh: innerHeight, tank: [t.left, t.top, t.width, t.height], debugBottom: d.bottom, debugTop: d.top, tankBottom: t.bottom, tankRight: t.right,
                         hudRight: hud.right, dirtRight: dw.right, hudLines: new Set([...document.querySelectorAll('#hud > *')].map((e) => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2))).size,
                         toolsBottom: Math.max(...tools.map((q) => q.bottom)), colBottom: c.bottom, toolsLeftOfTank: tools.every((q) => q.right <= t.left - 4),
                         scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight] }; })()""")
            page.screenshot(path=os.path.join(SHOTS, f"fluid_{w}x{h}.png"))
            pad = 12 if h >= 600 else 8
            sizes[f"{w}x{h}"] = f"{m['tank'][2]:.0f}x{m['tank'][3]:.0f} at ({m['tank'][0]:.0f},{m['tank'][1]:.0f})"
            check(f"fluid layout {w}x{h}: debug row bottom on the viewport bottom edge (Job F), tank-to-debug gap <= 8px, tank fills to the right padding, top bar one row, tools fit the column, nothing scrolls",
                  abs(h - m["debugBottom"]) < 0.5 and 0 <= m["debugTop"] - m["tankBottom"] <= 8 and abs(w - pad - m["tankRight"]) < 1 and m["dirtRight"] <= m["hudRight"] + 0.5 and m["hudLines"] == 1
                  and m["toolsBottom"] <= m["colBottom"] + 0.5 and m["toolsLeftOfTank"] and m["scroll"][0] <= w and m["scroll"][1] <= h, json.dumps(m))
            ctx.close()
        browser.close()
    print("   tank sizes:", json.dumps(sizes))

SHOTS7 = os.path.join(HERE, "..", "screenshots", "v7")
REF_RENDER = "/workspace/studio/briefs/aquarium/art/fish-v7/render.js"

def fish_v7(page, ev, shot, box, tool, click_fish, tj):
    """Art Director NEW_FISH_V7.md (owner-approved FISH_REVIEW_SHEET_V7): all 14 fish drawn from the fish-v7 vector data."""
    import base64, re
    os.makedirs(SHOTS7, exist_ok=True)
    view = VIEW[0].split("] ")[-1] if VIEW[0] else "view"
    ids = [s_["id"] for s_ in tj["species"]]
    d = ev("""const V = G.CFG.VISUAL, D = FishArt.V7;
      return { ids: Object.keys(D), v: Object.values(D).map((s) => s.v), stages: Object.values(D).map((s) => s.stages.length),
        size: V.speciesSize, dataSize: Object.fromEntries(Object.entries(D).map(([k, s]) => [k, s.speciesSize])),
        rarity: Object.fromEntries(Object.entries(D).map(([k, s]) => [k, s.rarity])),
        fx: Object.fromEntries(Object.keys(D).map((k) => [k, [1, 2, 3, 4].map((lv) => { const f = FishArt.fxOf(k, lv), st = FishArt.stage(k, lv);
          return { sheen: !!(f && f.sheen), sparkles: f ? f.sparkles.length : 0, aura: st.layers.some((l) => l.n === 'aura'), rim: st.layers.some((l) => l.n === 'rim'), irid: st.layers.some((l) => l.n === 'iridescence') }; })])),
        discus: (() => { const b = FishArt.stage('discus', 4).body, bb = FishArt.stage('discus', 4).bounds; return { ratio: +((b.bottom - b.top) / (b.nose - b.tail)).toFixed(2), lobesBehind: bb[0] < b.tail - 20, tall: bb[3] - bb[1] > 1.3 * (b.bottom - b.top) }; })() };""")
    sizes = {"guppy": 0.82, "danio": 0.95, "neon": 0.85, "ram": 0.97, "platy": 1.0, "rasbora": 0.85, "dwarfgourami": 0.95, "swordtail": 1.05, "cherrybarb": 0.85, "angelfish": 1.0, "pearlgourami": 1.05, "clownloach": 1.18, "rainbowfish": 1.05, "discus": 1.15}
    check("V7 data: all 14 species x L1-L4 from fish-v7 (v 7), in shop order; speciesSize = V7 6 table (ram 0.97, clown loach 1.18) in game and data; rarities = tuning",
          d["ids"] == ids and set(d["v"]) == {7} and set(d["stages"]) == {4} and d["size"] == sizes and d["dataSize"] == sizes
          and d["rarity"] == {s_["id"]: s_["rarity"] for s_ in tj["species"]}, json.dumps({"ids": d["ids"], "size": d["size"]}))
    fx = d["fx"]; rar = d["rarity"]
    ok_fx = True
    for k, lv4 in fx.items():
        r = rar[k]
        for i, e in enumerate(lv4):
            if i < 3: ok_fx &= not e["sheen"] and e["sparkles"] == 0 and not e["aura"] and not e["rim"]
            elif r == "rare": ok_fx &= e["sheen"] and e["sparkles"] == 3 and e["aura"] and e["rim"]
            elif r == "uncommon": ok_fx &= e["sheen"] and e["sparkles"] == 0 and not e["aura"] and not e["rim"]
            else: ok_fx &= not e["sheen"] and e["sparkles"] == 0 and not e["aura"] and not e["rim"]
            if r != "common" and i >= 2: ok_fx &= e["irid"]
            if r == "common": ok_fx &= not e["irid"]
    check("V7 5 rarity cues: rares at L4 aura + sheen + 1 px rim + 3 sparkles, iridescence from L3; uncommons sheen + iridescence only; commons none; no FX below L4",
          ok_fx, json.dumps({k: fx[k][3] for k in ("ram", "rasbora", "guppy", "discus")}))
    check("V7 check 1: Discus is a disc (body height / length >= 0.8) with the dorsal/anal lobes trailing past the body and fins far above/below it (not a ball)",
          d["discus"]["ratio"] >= 0.8 and d["discus"]["lobesBehind"] and d["discus"]["tall"], json.dumps(d["discus"]))
    # the in-game renderer (sprite cache: under + wagging tail + body) against the Art Director's reference render.js, all 56 stages
    page.add_script_tag(content=open(REF_RENDER).read())
    cmp_ = ev("""const out = []; const L = 150;
      for (const id of Object.keys(FishArt.V7)) for (let lv = 1; lv <= 4; lv++) {
        const st = FishArt.stage(id, lv), b = st.bounds, s = L / 100, w = Math.ceil((b[2] - b[0]) * s + 40), h = Math.ceil((b[3] - b[1]) * s + 40);
        const mk = () => { const c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d'); x.fillStyle = '#0a2a3d'; x.fillRect(0, 0, w, h); x.translate(Math.round(20 - b[0] * s), Math.round(20 - b[1] * s)); return x; }; // whole-pixel origin: a sprite is blitted 1:1
        const x1 = mk(); drawFishV7(x1, Object.assign({}, st, { layers: st.layers.filter((l) => l.n !== 'sheen' && l.n !== 'sparkle') }), L);
        const x2 = mk(); FishArt.drawFish(x2, id, L, 0, { level: lv, noFx: true });
        const p = x1.getImageData(0, 0, w, h).data, q = x2.getImageData(0, 0, w, h).data; let sum = 0, big = 0;
        for (let i = 0; i < p.length; i += 4) { const e = Math.abs(p[i] - q[i]) + Math.abs(p[i + 1] - q[i + 1]) + Math.abs(p[i + 2] - q[i + 2]); sum += e; if (e > 60) big++; }
        out.push([id, lv, +(sum / (p.length / 4) / 3).toFixed(2), +(big / (p.length / 4)).toFixed(4)]); }
      return out;""")
    worst = sorted(cmp_, key=lambda r_: -r_[2])[:3]
    check("V7 port: every species at L1-L4 drawn in game (cached sprites) matches the AD reference renderer render.js pixel for pixel (mean < 1/255, < 0.5% of pixels off by > 60)",
          len(cmp_) == 56 and all(r_[2] < 1 and r_[3] < 0.005 for r_ in cmp_), json.dumps(worst))
    # live FX: the rare sheen sweeps and sparkles twinkle (drawn per frame, not baked); commons draw the same at any time
    lv_ = ev("""const pix = (id, t) => { const c = document.createElement('canvas'); c.width = 300; c.height = 240; const x = c.getContext('2d'); x.translate(150, 120);
        FishArt.drawFish(x, id, 180, 0, { level: 4, t }); const d = x.getImageData(0, 0, 300, 240).data; let h = 0; for (let i = 0; i < d.length; i += 97) h = (h * 31 + d[i]) >>> 0; return h; };
      return { ramSweep: pix('ram', 0.3) !== pix('ram', 2.0), ramSpark: pix('ram', 2.0) !== pix('ram', 2.9), rasSweep: pix('rasbora', 0.3) !== pix('rasbora', 2.0),
               guppySame: pix('guppy', 0.3) === pix('guppy', 2.0) && pix('guppy', 2.0) === pix('guppy', 2.9) };""")
    check("V7 3 live FX: a rare adult's sheen sweeps and its sparkles twinkle over time, an uncommon's mild sheen sweeps, a common adult has no FX",
          lv_["ramSweep"] and lv_["ramSpark"] and lv_["rasSweep"] and lv_["guppySame"], json.dumps(lv_))
    # debug grid: 14 species x L1-L4 by the in-game renderer at in-game size (x3 zoom, like the sheet) -> screenshots/v7/grid*.png
    url = ev("return AQ.fishGrid(3).toDataURL('image/png');")
    png = base64.b64decode(url.split(",")[1])
    open(os.path.join(SHOTS7, f"grid_{view}.png"), "wb").write(png)
    if view == "844x390": open(os.path.join(SHOTS7, "grid.png"), "wb").write(png)
    gw, gh, _px = png_rgb(png)
    check("V7 debug grid: all 14 species x 4 levels rendered in game (x3) and saved to screenshots/v7/grid.png", gw == 300 + 348 * 4 and gh > 14 * 64, f"{gw}x{gh} -> screenshots/v7/grid_{view}.png")
    # in-tank: adults of every species, a growth row (L1-L4), rares up close; sprite cache stays warm (no per-frame path drawing)
    def tank_scene(spec):
        return ev(f"""fresh(); G.state.tank.xp = 99999; G.state.gold = 99999; G.state.speed = 1; G.state.fish.length = 0; const out = [];
          {json.dumps(spec)}.forEach(([id, lv, x, y]) => {{ // placed straight into the tank (more fish than the capacity, for the pictures)
            const f = {{ id: G.state.nextId++, sp: id, level: lv, state: 'GROWING', progress: 0, hungerDone: false, deathLeft: null, sinceFed: 0, fed: 0, boughtAt: G.state.gameTime, x, y }};
            G.state.fish.push(f); f.level = lv; f.state = lv >= 4 ? 'ADULT' : 'GROWING'; f.progress = 0; f.hungerDone = false; f.sinceFed = 0; AQ.pinFish(f.id, x, y); out.push(f.id); }});
          return out;""")
    adults = [[id_, 4, 0.12 + 0.19 * (i % 5), 0.2 + 0.2 * (i // 5)] for i, id_ in enumerate(ids)]
    got = tank_scene(adults)
    page.wait_for_timeout(600); m0 = ev("return FishArt.cacheInfo();"); page.wait_for_timeout(1200); m1 = ev("return FishArt.cacheInfo();")
    b_ = box(); page.screenshot(path=os.path.join(SHOTS7, f"tank_adults_{view}.png"), clip={"x": b_["x"], "y": b_["y"], "width": b_["width"], "height": b_["height"]})
    perf = ev("""const c = document.createElement('canvas'), dpr = window.devicePixelRatio || 1; c.width = 1200 * dpr; c.height = 800 * dpr; const x = c.getContext('2d'); x.scale(dpr, dpr);
      const list = G.state.fish.map((f) => [f.sp, f.level, AQ.fishLen(f.sp, f.level)]); let t0 = performance.now(), n = 0;
      for (let fr = 0; fr < 120; fr++) { x.clearRect(0, 0, 1200, 800); list.forEach(([id, lv, L], i) => { x.save(); x.translate(80 + (i % 5) * 220, 120 + Math.floor(i / 5) * 220); if (i % 2) x.scale(-1, 1);
        FishArt.drawFish(x, id, L, fr * 0.2, { level: lv, t: fr / 60 }); x.restore(); n++; }); }
      return { fish: list.length, msPerFrame: +((performance.now() - t0) / 120).toFixed(2) };""")
    check(f"V7 in tank: {len(got)} adults (all 14 species) swim with cached sprites (no new sprite renders once warm); one frame of all of them draws in < 8 ms",
          len(got) == 14 and m1["misses"] == m0["misses"] and perf["msPerFrame"] < 8, json.dumps({"cache": [m0, m1], "perf": perf, "shot": f"screenshots/v7/tank_adults_{view}.png"}))
    growth = [["guppy", lv, 0.1 + 0.2 * (lv - 1), 0.25] for lv in (1, 2, 3, 4)] + [["discus", lv, 0.1 + 0.22 * (lv - 1), 0.62] for lv in (1, 2, 3, 4)]
    tank_scene(growth); page.wait_for_timeout(700)
    page.screenshot(path=os.path.join(SHOTS7, f"tank_growth_{view}.png"), clip={"x": b_["x"], "y": b_["y"], "width": b_["width"], "height": b_["height"]})
    rares = [["ram", 4, 0.2, 0.3], ["dwarfgourami", 4, 0.5, 0.3], ["discus", 4, 0.8, 0.35], ["clownloach", 4, 0.3, 0.68], ["angelfish", 4, 0.7, 0.66]]
    rid = tank_scene(rares); page.wait_for_timeout(700)
    page.screenshot(path=os.path.join(SHOTS7, f"tank_rares_{view}.png"), clip={"x": b_["x"], "y": b_["y"], "width": b_["width"], "height": b_["height"]})
    # tap target: body only, never under 44 x 44; swim bounds keep the whole drawn fish (sword, fins) inside the glass
    tb = ev(f"""const out = {{}}; G.state.fish.forEach((f) => {{ const q = AQ.fishBody(f.id), b = AQ.fishBounds(f.id), e = FishArt.extent(f.sp, AQ.fishLen(f.sp, f.level), f.level), g = AQ.geom();
        out[f.sp] = {{ rx: q.rx, ry: q.ry, inside: b.x0 >= g.inset + Math.min(Math.max(-e.x0, e.x1), (g.W - 2 * g.inset) * 0.3) - 1e-6 }}; }}); return out;""")
    tool("hand"); page.keyboard.press("Escape")
    bc = page.evaluate(f"AQ.fishBody({rid[2]})"); bxy = box()
    page.mouse.click(bxy["x"] + bc["cx"], bxy["y"] + bc["cy"]); page.wait_for_timeout(200)
    opened = page.locator("#panel").is_visible(); rtxt = page.inner_text("#p-rarity") if opened else ""; rvis = page.locator("#p-rarity").is_visible() if opened else False
    page.keyboard.press("Escape")
    check("V6/V7 tap target: body ellipse (fins excluded) >= 44 x 44 px for every fish; tapping the Discus body opens it with a 'Rare' chip; swim bounds use the drawn extent",
          all(v_["rx"] >= 22 and v_["ry"] >= 22 and v_["inside"] for v_ in tb.values()) and opened and rtxt.lower() == "rare" and rvis, json.dumps({"tb": tb, "chip": rtxt}))
    # commons: no rarity chip anywhere; rare shop cards have the 2 px #b884ff border
    g_ = ev(f"""fresh(); G.state.tank.xp = 99999; G.state.gold = 99999; const f = G.buyFish('guppy'); AQ.pinFish(f.id, 0.5, 0.5); return f.id;""")
    page.wait_for_timeout(200); click_fish(g_); cvis = page.locator("#p-rarity").is_visible(); page.keyboard.press("Escape")
    page.click("#btn-shop"); page.wait_for_timeout(250)
    cards = page.evaluate("""[...document.querySelectorAll('#shop-list .card')].map((c) => ({ id: c.dataset.species, b: getComputedStyle(c).borderTopWidth + ' ' + getComputedStyle(c).borderTopColor, txt: c.innerText }))""")
    page.screenshot(path=os.path.join(SHOTS7, f"shop_{view}.png"))
    page.click('[data-close="shop"]')
    rare_ids = [s_["id"] for s_ in tj["species"] if s_["rarity"] == "rare"]
    check("V6 2/4 (kept by V7): no 'common' text in the shop or a common fish's info; rare shop cards have a 2 px #b884ff border, others don't",
          not cvis and all(not re.search(r"\bcommon\b", c_["txt"], re.I) for c_ in cards) and all((c_["b"] == "2px rgb(184, 132, 255)") == (c_["id"] in rare_ids) for c_ in cards),
          json.dumps([[c_["id"], c_["b"]] for c_ in cards]))
    ev("fresh();")

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
          len(tags) == 7 and v is not None and len(loaded) >= 7 and all(f"?v={v}" in n for n in loaded), json.dumps({"tags": tags, "loaded": loaded}))

def home_screen_icons():
    """Home-screen app (Art Director icons): favicon (svg + png), apple-touch-icon 180, manifest.webmanifest with 192 + 512,
    iOS/Android web-app meta tags; every path relative so it works under the GitHub Pages subpath /Fish-Aquarium/."""
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page(viewport={"width": 844, "height": 390})
        page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game")
        head = page.evaluate("""(() => {
            const links = [...document.querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"], link[rel="manifest"]')]
              .map((l) => ({ rel: l.rel, href: l.getAttribute('href'), abs: l.href, sizes: l.getAttribute('sizes') || '', type: l.getAttribute('type') || '' }));
            const meta = Object.fromEntries([...document.querySelectorAll('meta[name]')].map((m) => [m.name, m.content]));
            return { links, meta }; })()""")
        man = next((l for l in head["links"] if l["rel"] == "manifest"), None)
        status, manifest = {}, None
        for l in head["links"]:
            r = page.request.get(l["abs"]); status[l["href"]] = r.status
            if l["rel"] == "manifest" and r.ok: manifest = r.json()
        icon_urls = []
        if manifest:
            base = man["abs"].rsplit("/", 1)[0] + "/"
            for ic in manifest.get("icons", []):
                u = base + ic["src"]; r = page.request.get(u); status["manifest:" + ic["src"]] = r.status
                icon_urls.append((ic["src"], ic.get("sizes"), ic.get("purpose"), r.status, r.headers.get("content-type", "")))
        browser.close()
    L = head["links"]; M = head["meta"]
    rels = {(l["rel"], l["type"], l["sizes"]) for l in L}
    check("home-screen icons: favicon svg + png fallback, apple-touch-icon 180x180 and manifest.webmanifest are linked with relative paths and all load with HTTP 200",
          ("icon", "image/svg+xml", "") in rels and ("icon", "image/png", "192x192") in rels and ("apple-touch-icon", "", "180x180") in rels and man is not None
          and all(not l["href"].startswith(("/", "http:", "https:")) for l in L) and status and all(v == 200 for v in status.values()), json.dumps({"links": L, "status": status}))
    sizes = sorted(i[1] for i in icon_urls)
    check("manifest: name / short_name Aquarium, display standalone (what every iOS version understands) with fullscreen first in display_override (Android Chrome), orientation landscape, theme + background #07192a, "
          "start_url and scope ./ (GitHub Pages /Fish-Aquarium/), icons 192 + 512 purpose any, PNG, HTTP 200, relative src",
          manifest is not None and manifest.get("name") == "Aquarium" and manifest.get("short_name") == "Aquarium" and manifest.get("display") == "standalone"
          and manifest.get("display_override", [])[:1] == ["fullscreen"] and manifest.get("orientation") == "landscape"
          and manifest.get("theme_color") == "#07192a" and manifest.get("background_color") == "#07192a" and manifest.get("start_url") == "./" and manifest.get("scope") == "./"
          and sizes == ["192x192", "512x512"] and all(i[2] and "any" in i[2].split() and i[3] == 200 and i[4].startswith("image/png") and not i[0].startswith("/") for i in icon_urls),
          json.dumps({"manifest": manifest, "icons": icon_urls}))
    check("home-screen meta: apple-mobile-web-app-capable yes, mobile-web-app-capable yes, status bar black-translucent, apple title Aquarium, theme-color #07192a",
          M.get("apple-mobile-web-app-capable") == "yes" and M.get("mobile-web-app-capable") == "yes" and M.get("apple-mobile-web-app-status-bar-style") == "black-translucent"
          and M.get("apple-mobile-web-app-title") == "Aquarium" and M.get("theme-color") == "#07192a", json.dumps(M))


def debug_bottom():
    """Job F (Maksims 17:43): Debug button + options on the very bottom edge so the tank extends lower; password gate kept;
    options never clipped (they open upward on narrow screens); bottom padding is only the safe-area inset."""
    VIEW[0] = "debug-bottom"
    print("\n======== debug bottom (Job F)", flush=True)
    css = open(os.path.join(HERE, "..", "style.css")).read()
    check("Job F CSS: #app bottom padding = the safe-area inset only (no 4px strip); debug row 20 / 22 px; narrow screens open the options upward",
          "max(4px, env(safe-area-inset-bottom" not in css and "max(4px, var(--safe-b))" not in css
          and ("env(safe-area-inset-bottom, 0px) calc(var(--pad)" in css or "var(--safe-b) calc(var(--pad)" in css)
          and "--dbg: 20px" in css and "--dbg: 22px" in css and "#debug.up #dbg-panel" in css, "style.css")
    BEFORE = {"844x390": 306, "1180x820": 708}   # tank height before Job F (debug row 24 / 32 + 4px bottom padding)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (w, h) in ((844, 390), (1180, 820), (568, 320)):
            view = f"{w}x{h}"
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(400)
            m0 = page.evaluate("""(() => { const r = (id) => document.getElementById(id).getBoundingClientRect(); const t = r('tank-wrap'), d = r('debug'), g = r('dbg-toggle');
              return { tankH: t.height, tankW: t.width, tankBottom: t.bottom, debugTop: d.top, debugBottom: d.bottom, toggleBottom: g.bottom, toggleTop: g.top, vh: innerHeight }; })()""")
            if view in BEFORE:
                check(f"{view}: tank taller than before Job F ({BEFORE[view]} -> {m0['tankH']:.0f} px); debug row on the bottom edge, no empty strip under DEBUG (<= 1.5 px)",
                      m0["tankH"] > BEFORE[view] and abs(m0["debugBottom"] - h) < 0.5 and h - m0["toggleBottom"] <= 1.5 and m0["debugTop"] >= m0["tankBottom"], json.dumps(m0))
            # password gate still there: wrong code keeps it closed, 123456 opens
            page.click("#dbg-toggle"); page.wait_for_timeout(80); page.fill("#dbg-pass-input", "000000"); page.click("#dbg-pass-yes"); page.wait_for_timeout(80)
            wrong = page.evaluate("AQ.debugOpen()")
            page.fill("#dbg-pass-input", "123456"); page.click("#dbg-pass-yes"); page.wait_for_timeout(150)
            o = page.evaluate("""(() => { const d = document.getElementById('debug'), vw = innerWidth, vh = innerHeight;
              const btns = [...document.querySelectorAll('#dbg-panel button'), document.getElementById('dbg-toggle')].map((b) => { const r = b.getBoundingClientRect();
                const e = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
                return { t: b.textContent, inView: r.left >= -0.5 && r.right <= vw + 0.5 && r.top >= -0.5 && r.bottom <= vh + 0.5, hit: !!e && (e === b || b.contains(e)), w: r.width }; });
              const pr = document.getElementById('dbg-panel').getBoundingClientRect();
              return { open: AQ.debugOpen(), up: d.classList.contains('up'), clipped: !d.classList.contains('up') && d.scrollWidth > d.clientWidth + 0.5, btns, panel: [pr.left, pr.top, pr.right, pr.bottom],
                       debugBottom: d.getBoundingClientRect().bottom }; })()""")
            page.screenshot(path=os.path.join(SHOTS, f"debug_bottom_after_{view}.png"))
            names = [b_["t"] for b_ in o["btns"]]
            check(f"{view}: password gate kept (wrong code stays closed, 123456 opens); every debug option visible, on screen and tappable (not clipped{'; opens upward' if o['up'] else ''})",
                  wrong is False and o["open"] and not o["clipped"] and all(b_["inView"] and b_["hit"] and b_["w"] > 0 for b_ in o["btns"])
                  and "+100g" in names and "+50 XP" in names and "Reset save" in names and "DEBUG" in names and abs(o["debugBottom"] - h) < 0.5, json.dumps(o))
            if view == "568x320":
                check("568x320 (narrowest landscape phone): options that do not fit the bottom strip open upward over the tank, inside the screen",
                      o["up"] and o["panel"][3] <= m0["debugTop"] + 0.5 and o["panel"][0] >= 0 and o["panel"][2] <= w + 0.5, json.dumps(o))
            else:
                # tap +100g works from the bottom strip
                g0 = page.evaluate("AQ.game.state.gold"); page.click("#dbg-gold"); page.wait_for_timeout(60)
                check(f"{view}: options stay in the one bottom line (no overlay) and work (+100g adds 100 gold)",
                      not o["up"] and page.evaluate("AQ.game.state.gold") == g0 + 100, json.dumps({"up": o["up"]}))
            page.close()
        browser.close()

FIXES = os.path.join(HERE, "..", "screenshots", "fixes")

def edit_spacing():
    """Maksims 2026-09-28 live fix + AD LANDSCAPE_LAYOUT_V4 7 table: decoration edit menu 296x284 / 392x368; round buttons
    drawn 38 / 48 px on 44 / 52 px touch targets; Size gaps 12 / 16, d-pad gaps 6 / 8, Move-Size groups 20 / 24; targets never
    overlap; menu inside the tank near both edges (flip); a tap on each button hits only that button; the same controls
    (drag + d-pad + resize) for every decoration type (generic edit code)."""
    os.makedirs(FIXES, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (VW, VH) in ((844, 390), (1180, 820)):
            VIEW[0] = f"edit-spacing {VW}x{VH}"; LARGE = VH >= 600
            HIT, DRAWN, SGAP, DGAP, GGAP = (52, 48, 16, 8, 24) if LARGE else (44, 38, 12, 6, 20)
            MW, MH = (392, 368) if LARGE else (296, 284)
            ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=2, has_touch=True)
            page = ctx.new_page(); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(300)
            ev = lambda body: page.evaluate("() => { " + JS + body + " }")
            types = page.evaluate("AQ.decorTypes()")
            ids = ev("fresh(); G.state.gold = 99999; G.state.tank.xp = 1e7; G.state.decor = []; const out = {}; for (const t of AQ.decorTypes()) out[t] = G.buyDecor(t).id; AQ.setTool('brush'); return out;")
            page.wait_for_timeout(150)
            css = page.evaluate("""(() => { const cs = getComputedStyle(document.documentElement), b = document.querySelector('#deco-menu [data-size]');
                return { vars: ['--rb', '--rb-hit', '--size-gap', '--dpad-gap', '--group-gap', '--menu-w', '--menu-h'].map((v) => cs.getPropertyValue(v).trim()) }; })()""")
            probs, cases = [], 0
            def gap(a, b):
                return max(b["x"] - (a["x"] + a["w"]), a["x"] - (b["x"] + b["w"]), b["y"] - (a["y"] + a["h"]), a["y"] - (b["y"] + b["h"]))
            for t in types:
                did = ids[t]
                for xf in (0.08, 0.3, 0.5, 0.7, 0.92):
                    for sc in (0.5, 1.0, 2.0):
                        ev(f"const d = G.state.decor.find((q) => q.id === '{did}'); G.state.decor.forEach((q) => {{ q.x = q.id === d.id ? {xf} : -1; }}); d.sh = {sc}; d.sw = {sc}; AQ.selectDecor(d.id);")
                        page.wait_for_timeout(30)
                        e = page.evaluate("AQ.edit()"); btns = page.evaluate("AQ.editButtons()"); m, tk = e["menu"], e["tank"]; cases += 1
                        tag = f"{t} x{xf} {sc}x"
                        if not m or abs(m["w"] - MW) > 0.5 or abs(m["h"] - MH) > 0.5: probs.append([tag, "menu size", m])
                        if m and not (m["x"] >= tk["x"] - 0.5 and m["y"] >= tk["y"] - 0.5 and m["x"] + m["w"] <= tk["x"] + tk["w"] + 0.5 and m["y"] + m["h"] <= tk["y"] + tk["h"] + 0.5): probs.append([tag, "menu outside tank", m, tk])
                        sz = [b for b in btns if b["kind"] == "size"]; mv = [b for b in btns if b["kind"] == "move"]
                        if len(sz) != 4 or len(mv) != 4: probs.append([tag, "buttons", len(sz), len(mv)])
                        for b in btns:
                            if b["id"] == "dm-sell": continue  # full-width Sell bar: AD height 32 / 40, not a size/edit button (still in the overlap check)
                            if b["w"] < 44 - 0.01 or b["h"] < 44 - 0.01: probs.append([tag, "target < 44", b])
                            if b["kind"] != "other" and (abs(b["w"] - HIT) > 0.5 or abs(b["h"] - HIT) > 0.5): probs.append([tag, "target != AD", b])
                            if not (b["x"] >= 0 and b["y"] >= 0 and b["x"] + b["w"] <= VW and b["y"] + b["h"] <= VH and b["x"] >= tk["x"] - 0.5 and b["x"] + b["w"] <= tk["x"] + tk["w"] + 0.5): probs.append([tag, "off screen", b])
                        for i, a in enumerate(btns):
                            for b in btns[i + 1:]:
                                g_ = gap(a, b)
                                if g_ < 0.01: probs.append([tag, "overlap", a["id"], b["id"], g_])
                                if a["kind"] == b["kind"] == "size" and g_ < SGAP - 0.01: probs.append([tag, "size gap", a["id"], b["id"], g_])
                                if a["kind"] == b["kind"] == "move" and g_ < DGAP - 0.01: probs.append([tag, "dpad gap", a["id"], b["id"], g_])
                                if {a["kind"], b["kind"]} == {"size", "move"} and g_ < GGAP - 0.01: probs.append([tag, "group gap", a["id"], b["id"], g_])
                                if a["kind"] == "size" and b["kind"] == "size" and g_ < 12 - 0.01: probs.append([tag, "size gap < 12", g_])
            check(f"edit menu {MW}x{MH} inside the tank (flip at both edges); every Size / Move / close target >= 44 px ({HIT}x{HIT} AD), never overlapping; Size gaps >= {SGAP}, d-pad gaps >= {DGAP}, Move-Size >= {GGAP}; "
                  f"{len(types)} types x 5 positions x 3 sizes ({cases} cases)", not probs and cases == len(types) * 15, json.dumps({"css": css, "probs": probs[:6]}))
            # drawn circle vs target (CSS variables, single place for the Art Director)
            circ = page.evaluate("""(() => { const b = document.querySelector('#deco-menu [data-size]'), c = getComputedStyle(b, '::before'), r = b.getBoundingClientRect();
                return { cw: parseFloat(c.width), ch: parseFloat(c.height), bw: r.width, radius: c.borderRadius, gap: getComputedStyle(document.querySelector('#deco-menu .sizes')).rowGap }; })()""")
            check(f"round buttons drawn {DRAWN}px circles centred on {HIT}px targets; Size grid gap = var(--size-gap) = {SGAP}px",
                  abs(circ["cw"] - DRAWN) < 0.5 and abs(circ["ch"] - DRAWN) < 0.5 and abs(circ["bw"] - HIT) < 0.5 and circ["gap"] == f"{SGAP}px" and css["vars"][2] == f"{SGAP}px", json.dumps(circ))
            # hit test: points all over each target hit that button; points in the gaps hit no button
            for t in types:
                ev(f"const d = G.state.decor.find((q) => q.id === '{ids[t]}'); G.state.decor.forEach((q) => {{ q.x = q.id === d.id ? 0.3 : -1; }}); d.sh = 1; d.sw = 1; AQ.selectDecor(d.id);"); page.wait_for_timeout(30)
                hits = page.evaluate("""(() => { const bad = []; const btns = [...document.querySelectorAll('#deco-menu button')].filter((b) => b.offsetParent && (b.dataset.size || b.dataset.move));
                    for (const b of btns) { const r = b.getBoundingClientRect();
                      for (const [fx, fy] of [[0.5, 0.5], [0.06, 0.06], [0.94, 0.06], [0.06, 0.94], [0.94, 0.94], [0.5, 0.04], [0.04, 0.5]]) {
                        const e = document.elementFromPoint(r.left + r.width * fx, r.top + r.height * fy), hb = e && e.closest('button');
                        if (hb !== b) bad.push([b.dataset.size || b.dataset.move, fx, fy, hb ? (hb.dataset.size || hb.dataset.move || hb.id) : null]); } }
                    const sz = [...document.querySelectorAll('#deco-menu [data-size]')].map((b) => b.getBoundingClientRect());
                    const mids = [[(sz[0].right + sz[1].left) / 2, sz[0].top + sz[0].height / 2], [sz[0].left + sz[0].width / 2, (sz[0].bottom + sz[2].top) / 2]];
                    for (const [x, y] of mids) { const e = document.elementFromPoint(x, y); if (e && e.closest('button')) bad.push(['gap', x, y, e.closest('button').dataset.size]); }
                    return bad; })()""")
                # real taps: each size button changes only its own dimension; each move button only its own axis
                taps = []
                for kind, key, sign in (("taller", "sh", 1), ("shorter", "sh", -1), ("wider", "sw", 1), ("narrower", "sw", -1)):
                    before = ev(f"const d = G.state.decor.find((q) => q.id === '{ids[t]}'); return [d.sh, d.sw, d.x, d.y];")
                    r = page.locator(f'#deco-menu [data-size="{kind}"]').bounding_box(); page.touchscreen.tap(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2); page.wait_for_timeout(60)
                    after = ev(f"const d = G.state.decor.find((q) => q.id === '{ids[t]}'); return [d.sh, d.sw, d.x, d.y];")
                    i = 0 if key == "sh" else 1
                    ok = round(after[i] - before[i], 3) == round(0.1 * sign, 3) and after[1 - i] == before[1 - i] and after[3] == before[3]
                    if not ok: taps.append([kind, before, after])
                for kind, i, sign in (("up", 3, -1), ("down", 3, 1), ("left", 2, -1), ("right", 2, 1)):
                    ev(f"const d = G.state.decor.find((q) => q.id === '{ids[t]}'); d.x = 0.3; d.y = 0.5; d.sh = 1; d.sw = 1;")
                    before = ev(f"const d = G.state.decor.find((q) => q.id === '{ids[t]}'); return [d.sh, d.sw, d.x, d.y];")
                    r = page.locator(f'#deco-menu [data-move="{kind}"]').bounding_box(); page.touchscreen.tap(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2); page.wait_for_timeout(60)
                    after = ev(f"const d = G.state.decor.find((q) => q.id === '{ids[t]}'); return [d.sh, d.sw, d.x, d.y];")
                    j = 5 - i
                    ok = (after[i] - before[i]) * sign > 0 and after[j] == before[j] and after[0] == before[0] and after[1] == before[1]
                    if not ok: taps.append([kind, before, after])
                check(f"{t}: every point of each Size / Move target hits only that button, the gaps hit none; a real tap on each changes only its own size / axis (one step)",
                      not hits and not taps, json.dumps({"hits": hits[:6], "taps": taps}))
                # drag: press on the decoration and drag it; same generic code for every type
                ev(f"const d = G.state.decor.find((q) => q.id === '{ids[t]}'); d.x = 0.4; d.y = 0.5; d.sh = 1; d.sw = 1; AQ.selectDecor(d.id);"); page.wait_for_timeout(40)
                g0 = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == ids[t]); tb = page.locator("#tank").bounding_box()
                sx, sy = tb["x"] + g0["bx"], tb["y"] + (g0["y0"] + g0["by"]) / 2
                page.mouse.move(sx, sy); page.mouse.down(); page.mouse.move(sx + 30, sy, steps=4); page.mouse.move(sx + 60, sy + 3, steps=4); dragging = page.evaluate("AQ.edit()")["dragging"]; page.mouse.up(); page.wait_for_timeout(60)
                g1 = next(z for z in page.evaluate("AQ.decorScreen()") if z["id"] == ids[t]); e1 = page.evaluate("AQ.edit()")
                check(f"{t}: drag in edit mode moves the decoration with the pointer (+60 px -> +60 px), stays selected with its menu open",
                      dragging and abs(g1["bx"] - g0["bx"] - 60) < 1 and e1["selDecor"] == ids[t] and e1["menu"], json.dumps({"dx": g1["bx"] - g0["bx"], "dragging": dragging}))
            if VW == 844:
                ev(f"const d = G.state.decor.find((q) => q.id === '{ids[types[0]]}'); G.state.decor.forEach((q, i) => {{ q.x = 0.25 + i * 0.12; q.sh = 1; q.sw = 1; }}); AQ.selectDecor(d.id);"); page.wait_for_timeout(200)
            else:
                ev(f"const d = G.state.decor.find((q) => q.id === '{ids[types[0]]}'); G.state.decor.forEach((q, i) => {{ q.x = 0.25 + i * 0.12; q.sh = 1; q.sw = 1; }}); AQ.selectDecor(d.id);"); page.wait_for_timeout(200)
            name = "resize_844.png" if VW == 844 else "resize_1180.png"
            page.screenshot(path=os.path.join(FIXES, name))
            check(f"edit mode screenshot saved: screenshots/fixes/{name}; no page errors", not errs, "; ".join(errs[:3]))
            page.evaluate("AQ.game.reset(); AQ.game.save()")
            ctx.close()
        browser.close()

def rarity_tags(base=None, label="after"):
    """AD v4 7 rarity tag (2026-09-28): never a 'Common' tag / badge / frame / text anywhere (shop cards, fish info, toasts,
    tooltips, hidden DOM too); Uncommon and Rare keep a small pill: 9px/800 uppercase, 14px tall, 0 5px padding, no border
    (Large 10 / 16 / 6), overlaying the shop card's top-left corner 4px in. label='before' only takes the screenshots
    (run against the previous build)."""
    import re
    base = base or BASE
    os.makedirs(FIXES, exist_ok=True)
    scan_js = """(() => { const hits = [];
        const txt = document.body.textContent; if (/\\bcommon\\b/i.test(txt)) hits.push(['textContent', (txt.match(/.{0,30}\\bcommon\\b.{0,30}/i) || [''])[0]]);
        if (/\\bcommon\\b/i.test(document.body.innerText)) hits.push(['innerText']);
        for (const el of document.querySelectorAll('*')) for (const a of el.attributes) if (/\\bcommon\\b/i.test(a.value) && a.name !== 'd') hits.push([el.tagName, el.id, a.name, a.value.slice(0, 60)]);
        return hits; })()"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (VW, VH) in ((844, 390), (1180, 820)):
            if label == "before" and VW != 844: continue
            VIEW[0] = f"rarity {VW}x{VH}"; LARGE = VH >= 600
            ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=2)
            page = ctx.new_page(); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(300)
            ev = lambda body: page.evaluate("() => { " + JS + body + " }")
            ev("fresh(); G.state.tank.xp = 99999; G.state.gold = 99999; G.state.decor = [];")
            page.evaluate("AQ.openShop()"); page.wait_for_timeout(250)
            sfx = f"_{VW}"
            page.screenshot(path=os.path.join(FIXES, f"rarity_shop_{label}{sfx}.png"))
            cards = page.evaluate("""[...document.querySelectorAll('#shop-list .card')].map((c) => { const t = c.querySelector('.rar'), r = c.getBoundingClientRect(), cs = t ? getComputedStyle(t) : null, tr = t ? t.getBoundingClientRect() : null;
                const price = getComputedStyle(c.querySelector('.btn .price'));
                return { id: c.dataset.species, text: c.textContent, tag: t ? t.textContent : null, vis: t ? t.checkVisibility() : false, border: getComputedStyle(c).borderTopWidth,
                  fs: cs && cs.fontSize, fw: cs && cs.fontWeight, h: tr && tr.height, pl: cs && cs.paddingLeft, pr: cs && cs.paddingRight, bw: cs && cs.borderTopWidth, tt: cs && cs.textTransform,
                  clip: t ? t.scrollWidth > t.clientWidth + 0.5 : false, dx: tr && tr.left - r.left - c.clientLeft, dy: tr && tr.top - r.top - c.clientTop, priceFs: parseFloat(price.fontSize) }; })""")
            shop_scan = page.evaluate(scan_js)
            page.evaluate("document.querySelector('#shop-close').click()"); page.wait_for_timeout(100)
            # info panel: a common, an uncommon and a rare fish
            ids = ev("const out = {}; for (const [k, sp, x] of [['c', 'guppy', 0.3], ['u', 'rasbora', 0.55], ['r', 'ram', 0.8]]) { const f = G.buyFish(sp); AQ.pinFish(f.id, x, 0.45); out[k] = f.id; } return out;")
            page.evaluate("AQ.setTool('hand')"); page.wait_for_timeout(200)
            info = {}
            for k in ("c", "u", "r"):
                bc = page.evaluate(f"AQ.fishBody({ids[k]})"); tb = page.locator("#tank").bounding_box()
                page.mouse.click(tb["x"] + bc["cx"], tb["y"] + bc["cy"]); page.wait_for_timeout(250)
                info[k] = page.evaluate("""(() => { const c = document.getElementById('p-rarity'), cs = getComputedStyle(c), r = c.getBoundingClientRect();
                    return { open: !document.getElementById('panel').hidden, name: document.getElementById('p-name').textContent, text: c.textContent, vis: c.checkVisibility(),
                             panel: document.getElementById('panel').textContent, fs: cs.fontSize, h: r.height, bw: cs.borderTopWidth, clip: c.scrollWidth > c.clientWidth + 0.5 }; })()""")
                info[k]["scan"] = page.evaluate(scan_js)
                if k in ("c", "r"): page.screenshot(path=os.path.join(FIXES, f"rarity_info_{'common' if k == 'c' else 'rare'}_{label}{sfx}.png"))
                page.keyboard.press("Escape"); page.wait_for_timeout(80)
            # toasts: buying a common fish in the shop, its level-up, an Aquarium-level toast unlocking a common + a rare
            page.evaluate("document.getElementById('toasts').innerHTML = ''")
            ev("G.state.fish.length = 0; G.state.tank.xp = 399; G.state.gold = 1000;")
            page.evaluate("AQ.openShop()"); page.wait_for_timeout(150); page.click('#shop-list button[data-buy="guppy"]'); page.wait_for_timeout(100)
            page.evaluate("document.querySelector('#shop-close').click()")
            ev("const f = G.state.fish[0]; f.state = 'HUNGRY'; f.endMeal = true; f.hungerDone = true; f.progress = G.growSec(G.SPECIES.guppy, 1); f.fed = 0; f.deathLeft = 999; G.state.food = 50; feedFull(f); G.debugAddXp(1);")
            page.wait_for_timeout(150)
            toasts = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)"); toast_scan = page.evaluate(scan_js)
            ev("fresh(); G.state.fish.length = 0;"); page.evaluate("AQ.game.reset(); AQ.game.save()")
            ctx.close()
            if label == "before": continue
            FS, TH, PX = ("10px", 16, "6px") if LARGE else ("9px", 14, "5px")
            tj = merged_tuning(); rar = {s_["id"]: s_["rarity"] for s_ in tj["species"]}
            bad = []
            for c in cards:
                r_ = rar[c["id"]]
                if re.search(r"\bcommon\b", c["text"], re.I): bad.append([c["id"], "common text"])
                if r_ == "common" and (c["tag"] is not None or c["border"] != "1px"): bad.append([c["id"], "common has tag/frame", c["tag"], c["border"]])
                if r_ != "common":
                    if not (c["vis"] and c["tag"] == r_.capitalize() and c["fs"] == FS and c["fw"] == "800" and abs(c["h"] - TH) < 0.5 and c["pl"] == PX and c["pr"] == PX and c["bw"] == "0px"
                            and c["tt"] == "uppercase" and not c["clip"] and abs(c["dx"] - 4) < 0.5 and abs(c["dy"] - 4) < 0.5 and float(c["fs"][:-2]) < c["priceFs"]):
                        bad.append([c["id"], {k_: c[k_] for k_ in ("tag", "fs", "fw", "h", "pl", "bw", "clip", "dx", "dy", "priceFs")}])
            check(f"shop cards: no Common tag / frame / text; Uncommon and Rare show a {FS} bold uppercase {TH}px pill (padding {PX}, no border, not clipped, smaller than the price) on the card's top-left corner 4px in; "
                  "the whole shop DOM (text, hidden text, attributes) never says 'common'",
                  not bad and not shop_scan and sum(1 for c in cards if c["tag"]) == sum(1 for v in rar.values() if v != "common"), json.dumps({"bad": bad[:5], "scan": shop_scan[:3]}))
            ok_i = (info["c"]["open"] and info["c"]["text"] == "" and not info["c"]["vis"] and not info["c"]["scan"] and "common" not in info["c"]["panel"].lower()
                    and info["u"]["open"] and info["u"]["text"] == "Uncommon" and info["u"]["vis"] and info["r"]["open"] and info["r"]["text"] == "Rare" and info["r"]["vis"]
                    and all(info[k]["fs"] == FS and abs(info[k]["h"] - TH) < 0.5 and info[k]["bw"] == "0px" and not info[k]["clip"] for k in ("u", "r")) and not info["u"]["scan"] and not info["r"]["scan"])
            check("fish info panel: a Common fish (Guppy) has no rarity tag and no 'common' anywhere in the DOM (not even hidden); Uncommon (Rasbora) and Rare (Ram) show the small tag",
                  ok_i, json.dumps({k: {k2: v for k2, v in info[k].items() if k2 not in ("panel",)} for k in info}))
            check("toasts for a common fish ('Guppy added', level-up) and an Aquarium-level toast (Neon Tetra and German Blue Ram (rare)): no 'common', the rare still named",
                  toasts and not toast_scan and any("Guppy added" in t for t in toasts) and any("(rare)" in t and "Neon Tetra" in t for t in toasts)
                  and not any(re.search(r"\bcommon\b", t, re.I) for t in toasts), json.dumps({"toasts": toasts, "scan": toast_scan}))
            check("rarity tags: no page errors", not errs, "; ".join(errs[:3]))
        browser.close()

def tuning_68():
    """Tuning 6.8 (approved, stone and leaf ONLY): stone / leaf 2 gold each, +1 XP on the first purchase of each type only,
    moving pays / charges nothing; new games start with an empty tank (starter grant still tops up to 20); existing saves keep
    their pieces as bought for 0 gold and as already bought for first-copy XP; sell refund floor(pricePaid / 2), never removes
    XP; netting a dead fish pays floor(price / 4) at any level (Guppy 5, Danio 12, Discus 812), no XP, no confirm, toast
    'Fish removed · +N gold'. Leaf exception (Maksims 19:13): leaf 1 gold, 0 XP, sells for its full pricePaid (old free leaves 0)."""
    VIEW[0] = "tuning 6.8"
    tj = merged_tuning(); D = tj["decorations"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 844, "height": 390}, device_scale_factor=1)
        page = ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        def boot():
            page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(250)
        ev = lambda body: page.evaluate("() => { " + JS + body + " }")
        boot()
        check("tuning.json 6.8 in config.js verbatim; decorations.price stone 2 / leaf 1, placeXp 1 / 0, sellRefund floor(pricePaid / 2), sellRefundOverride leaf pricePaid, newTank.defaultDecorations [], deadFish.removeGold floor(species.price / 4)",
              page.evaluate("AQ.game.T") == tj and tj["version"] == "6.8" and D["price"].get("stone") == 2 and D["price"].get("leaf") == 1 and D["placeXp"].get("stone") == 1 and D["placeXp"].get("leaf") == 0 and D.get("sellRefundOverride") == {"leaf": "pricePaid"}
              and D["sellRefund"] == "floor(pricePaid / 2)" and tj["newTank"]["defaultDecorations"] == [] and tj["deadFish"]["removeGold"] == "floor(species.price / 4)", tj["version"])
        # new game: empty tank; the reset path too
        page.evaluate("localStorage.clear()"); boot()
        ng = ev("return { decor: G.state.decor.length, bought: G.state.decorBought, gold: G.state.gold };")
        ev("G.state.tank.xp = 500; G.buyDecor; G.state.gold = 50; G.buyDecor('leaf'); G.reset();")
        rs = ev("return { decor: G.state.decor.length, bought: G.state.decorBought, xp: G.state.tank.xp };")
        check("new game and Start new tank / reset: an empty tank (no stone, no leaves), no decoration types bought", ng == {"decor": 0, "bought": {}, "gold": 0} and rs == {"decor": 0, "bought": {}, "xp": 0}, json.dumps([ng, rs]))
        # buying: 2 gold each, +1 XP for the first stone and the first leaf only
        buy = ev("""fresh(); G.state.gold = 20; const out = []; const step = (t) => { const g = G.state.gold, x = G.state.tank.xp, d = G.buyDecor(t); out.push([t, g - G.state.gold, G.state.tank.xp - x, d.pricePaid]); return d; };
            step('stone'); step('stone'); step('leaf'); step('leaf'); step('stone'); return { out, bought: G.state.decorBought };""")
        check("v6.8 buying: stone costs 2 gold (pricePaid 2), leaf 1 gold (pricePaid 1); +1 XP on the FIRST stone only, 0 XP for later stones and for every leaf (placeXp.leaf 0)",
              buy["out"] == [["stone", 2, 1, 2], ["stone", 2, 0, 2], ["leaf", 1, 0, 1], ["leaf", 1, 0, 1], ["stone", 2, 0, 2]] and buy["bought"] == {"stone": True, "leaf": True}, json.dumps(buy))
        poor = ev("fresh(); G.state.starterGrantUsed = true; G.state.gold = 0; const n = G.state.decor.length; const r = G.buyDecor('leaf'); return { r: r === null, n: G.state.decor.length - n, gold: G.state.gold };")
        page.evaluate("AQ.openShop(); AQ.setShopTab('decor')"); page.wait_for_timeout(150)
        shop = page.evaluate("[...document.querySelectorAll('#shop-decor .card')].map((c) => ({ n: c.querySelector('.n').textContent, price: c.querySelector('.price').textContent, dis: c.querySelector('button').disabled }))")
        page.evaluate("document.querySelector('#shop-close').click()")
        check("shop: Leaf 1 gold, Stone 2 gold; with 0 gold the Buy buttons are disabled and buying a leaf is refused",
              shop[:2] == [{"n": "Leaf", "price": "1", "dis": True}, {"n": "Stone", "price": "2", "dis": True}] and poor == {"r": True, "n": 0, "gold": 0}, json.dumps([shop, poor]))
        # moving / resizing / recolouring later pays or charges nothing (d-pad, drag, size)
        did = ev("fresh(); G.state.starterGrantUsed = true; G.state.gold = 100; const d = G.buyDecor('stone'); AQ.setTool('brush'); AQ.selectDecor(d.id); return d.id;"); page.wait_for_timeout(100)
        g0 = ev("return [G.state.gold, G.state.tank.xp];")
        for sel in ('[data-move="right"]', '[data-move="up"]', '[data-size="wider"]', '[data-size="taller"]'): page.click(f"#deco-menu {sel}"); page.wait_for_timeout(40)
        z = next(q for q in page.evaluate("AQ.decorScreen()") if q["id"] == did); tb = page.locator("#tank").bounding_box()
        page.mouse.move(tb["x"] + z["bx"], tb["y"] + (z["y0"] + z["by"]) / 2); page.mouse.down(); page.mouse.move(tb["x"] + z["bx"] - 50, tb["y"] + (z["y0"] + z["by"]) / 2, steps=5); page.mouse.up()
        g1 = ev("return [G.state.gold, G.state.tank.xp];"); moved = next(q for q in page.evaluate("AQ.decorScreen()") if q["id"] == did)["bx"] != z["bx"]
        check("moving (d-pad and drag) and resizing a bought piece pays / charges nothing (gold and XP unchanged)", g0 == g1 and moved, json.dumps([g0, g1]))
        # selling: floor(pricePaid / 2), never removes XP; the type stays bought (a rebuy pays no XP)
        page.click("#dm-sell"); page.wait_for_timeout(80); st = page.inner_text("#confirm-text"); sb = page.inner_text("#dm-sell"); xp_b = ev("return G.state.tank.xp;"); gb = ev("return G.state.gold;")
        page.click("#confirm-yes"); page.wait_for_timeout(100)
        sold = ev("return { gold: G.state.gold, xp: G.state.tank.xp, n: G.state.decor.length, bought: G.state.decorBought.stone };")
        rebuy = ev("const x = G.state.tank.xp; G.buyDecor('stone'); return G.state.tank.xp - x;")
        page.evaluate("AQ.setTool('hand')")
        check("selling a 2-gold stone: 'Sell · refund 1 gold' / 'Sell this stone? You get 1 gold back.', +1 gold, XP not taken back; buying another stone pays 0 XP (first copy already bought)",
              sb == "Sell · refund 1 gold" and st == "Sell this stone? You get 1 gold back." and sold == {"gold": gb + 1, "xp": xp_b, "n": 0, "bought": True} and rebuy == 0, json.dumps([sb, st, sold, rebuy]))
        # leaf exception: a bought leaf sells for its full pricePaid (1) in the UI; generic per-type override (default floor / 2)
        lid = ev("fresh(); G.state.starterGrantUsed = true; G.state.gold = 100; G.state.decorBought = {}; const x = G.state.tank.xp; const d = G.buyDecor('leaf'); window.__lx = G.state.tank.xp - x; AQ.setTool('brush'); AQ.selectDecor(d.id); return d.id;"); page.wait_for_timeout(100)
        lb = page.inner_text("#dm-sell"); page.click("#dm-sell"); page.wait_for_timeout(80); lt = page.inner_text("#confirm-text"); lg = ev("return G.state.gold;")
        page.click("#confirm-yes"); page.wait_for_timeout(100)
        la = ev("return { gold: G.state.gold, n: G.state.decor.length, xp: window.__lx, bought: !!G.state.decorBought.leaf };"); page.evaluate("AQ.setTool('hand')")
        check("leaf exception: first leaf costs 1 gold and gives 0 XP; 'Sell · refund 1 gold' / 'Sell this leaf? You get 1 gold back.' refunds the full 1 gold",
              lb == "Sell · refund 1 gold" and lt == "Sell this leaf? You get 1 gold back." and lg == 99 and la == {"gold": 100, "n": 0, "xp": 0, "bought": True}, json.dumps([lb, lt, lg, la]))
        rf = ev("""const r = (type, p) => G.decorRefund({ type, pricePaid: p });
            return { leaf: [r('leaf', 0), r('leaf', 1), r('leaf', 3)], stone: [r('stone', 0), r('stone', 1), r('stone', 2), r('stone', 5)] };""")
        check("sell refund per type: leaf = full pricePaid (0 -> 0, 1 -> 1, 3 -> 3); stone (no override) = floor(pricePaid / 2) (0, 0, 1, 2)",
              rf == {"leaf": [0, 1, 3], "stone": [0, 0, 1, 2]}, json.dumps(rf))
        # starter grant: first clean 20 gold, 2 gold on decor before any fish -> 18 -> grant tops up to 20 -> the Guppy can still be bought
        grant = ev("""G.reset(); clean(); G.state.gold = 20; G.state.firstCleanPending = false; G.state.starterGrantUsed = false; G.tick(1);
            const a = G.state.gold; G.buyDecor('leaf'); const b = G.state.gold; G.tick(1); const c = G.state.gold, used = G.state.starterGrantUsed; const f = G.buyFish('guppy');
            return { a, b, c, used, fish: !!f, after: G.state.gold };""")
        check("NUMBERS 7 first session: 20 gold -> leaf -> 19; the one-time starter grant tops up to 20 (no living fish); the first Guppy is still affordable",
              grant == {"a": 20, "b": 19, "c": 20, "used": True, "fish": True, "after": 0}, json.dumps(grant))
        # existing (pre-6.8) save: pieces stay, pricePaid 0 (sell 0), types count as already bought (no first-copy XP)
        old = {"v": 4, "gameTime": 100, "lastSeen": 0, "gold": 50, "food": 10, "diamonds": 0, "speed": 1, "nextId": 20, "fish": [], "tank": {"xp": 70}, "firstCleanPending": False, "starterGrantUsed": True,
               "dirt": {"t": 0, "spots": [], "spawned": 0, "grime5": 0, "rubStage": 0}, "stats": {},
               "decor": [{"id": "d1", "type": "leaf", "x": 0.16, "y": 0.5, "sh": 1, "sw": 1, "color": 25, "paid": 0, "seed": 11},
                         {"id": "d2", "type": "leaf", "x": 0.24, "y": 0.5, "sh": 1.3, "sw": 1, "color": 55, "paid": 0, "seed": 48},
                         {"id": "d4", "type": "stone", "x": 0.6, "y": 0.4, "sh": 1, "sw": 0.8, "color": 50, "paid": 0, "seed": 122}]}
        page.evaluate("(s) => { AQ.game.save = () => {}; localStorage.setItem(AQ.game.CFG.VISUAL.saveKey, JSON.stringify(s)); location.reload(); }", {**old, "lastSeen": int(time.time() * 1000)})
        page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(300)
        mig = ev("""return { decor: G.state.decor.map((d) => [d.id, d.type, d.x, d.y, d.sh, d.sw, d.color, d.pricePaid, 'paid' in d]), bought: G.state.decorBought, gold: G.state.gold, xp: G.state.tank.xp,
            refunds: G.state.decor.map((d) => G.decorRefund(d)) };""")
        page.evaluate("AQ.setTool('brush'); AQ.selectDecor('d1')"); page.wait_for_timeout(80); old_btn = page.inner_text("#dm-sell"); page.evaluate("AQ.setTool('hand')")
        mig2 = ev("""const x0 = G.state.tank.xp, g0 = G.state.gold; const nl = G.buyDecor('leaf'), ns = G.buyDecor('stone'); const x1 = G.state.tank.xp, g1 = G.state.gold;
            const r0 = G.sellDecor('d1'), r1 = G.sellDecor(nl.id); return { xpBuy: x1 - x0, goldBuy: g0 - g1, sellOld: r0, sellNew: r1, xpAfter: G.state.tank.xp - x1 };""")
        exp_decor = [[d["id"], d["type"], d["x"], d["y"], d["sh"], d["sw"], d["color"], 0, False] for d in old["decor"]]
        check("pre-6.8 save migration: placed stone / leaves stay exactly where they were (position, size, colour), counted as bought for 0 gold (refund 0, 'Sell · refund 0 gold'); "
              "leaf and stone already count as bought (a new leaf and stone pay 0 XP, cost 1 + 2 gold); the new leaf sells for its full 1 gold; selling never removes XP",
              mig["decor"] == exp_decor and mig["bought"] == {"leaf": True, "stone": True} and mig["gold"] == 50 and mig["xp"] == 70 and mig["refunds"] == [0, 0, 0] and old_btn == "Sell · refund 0 gold"
              and mig2 == {"xpBuy": 0, "goldBuy": 3, "sellOld": 0, "sellNew": 1, "xpAfter": 0}, json.dumps([mig, old_btn, mig2]))
        old2 = {**old, "decor": [old["decor"][2]], "lastSeen": int(time.time() * 1000)}  # an old save with only a stone placed
        page.evaluate("(s) => { AQ.game.save = () => {}; localStorage.setItem(AQ.game.CFG.VISUAL.saveKey, JSON.stringify(s)); location.reload(); }", old2)
        page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(300)
        mig3 = ev("const x = G.state.tank.xp; G.buyDecor('stone'); const a = G.state.tank.xp - x; G.buyDecor('leaf'); return { stoneXp: a, leafXp: G.state.tank.xp - x - a, bought: G.state.decorBought };")
        # a post-6.8 save is not migrated again: pricePaid and decorBought survive a reload
        ev("G.save();"); page.reload(); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(250)
        keep = ev("return { paid: G.state.decor.map((d) => d.pricePaid), bought: G.state.decorBought };")
        check("old save with only a stone: another stone pays 0 XP, the first leaf pays 0 XP (placeXp.leaf 0); a 6.8 save keeps pricePaid (0 old, 2 stone, 1 leaf) and bought types across a reload",
              mig3 == {"stoneXp": 0, "leafXp": 0, "bought": {"stone": True, "leaf": True}} and keep == {"paid": [0, 2, 1], "bought": {"stone": True, "leaf": True}}, json.dumps([mig3, keep]))
        # dead fish: floor(price / 4) at any level, no XP
        dg = ev("""fresh(); G.state.tank.xp = 999999; const out = {};
            for (const sp of ['guppy', 'danio', 'discus']) { out[sp] = []; for (let lv = 1; lv <= 4; lv++) { G.state.gold = 99999; G.state.fish.length = 0; const f = G.buyFish(sp); f.level = lv; f.state = 'DEAD';
              const g = G.state.gold, x = G.state.tank.xp; const r = G.removeDead(f.id); out[sp].push([r, G.state.gold - g, G.state.tank.xp - x]); } } return out;""")
        check("v6.8 dead fish removal pays floor(price / 4) at every level L1-L4 (Guppy 5, Danio 12, Discus 812), 0 XP",
              dg == {"guppy": [[5, 5, 0]] * 4, "danio": [[12, 12, 0]] * 4, "discus": [[812, 812, 0]] * 4}, json.dumps(dg))
        fid = ev("fresh(); G.state.tank.xp = 999; G.state.gold = 100; const f = G.buyFish('danio'); f.level = 3; f.state = 'DEAD'; f.diedAt = G.state.gameTime - 100; AQ.pinFish(f.id, 0.5, 0.5); return f.id;")
        page.evaluate("document.getElementById('toasts').innerHTML = ''; AQ.setTool('net')"); page.wait_for_timeout(300)
        g_b = ev("return [G.state.gold, G.state.tank.xp];"); pos = page.evaluate(f"AQ.fishScreen({fid})"); tb = page.locator("#tank").bounding_box()
        page.mouse.click(tb["x"] + pos["x"], tb["y"] + pos["y"]); page.wait_for_timeout(400)
        tt = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map((e) => e.textContent)"); g_a = ev("return [G.state.gold, G.state.tank.xp, G.state.fish.length];")
        check("Net on a dead L3 Danio: removed at once, no confirm, +12 gold, no XP, toast 'Fish removed · +12 gold'",
              g_a == [g_b[0] + 12, g_b[1], 0] and not page.locator("#confirm").is_visible() and "Fish removed · +12 gold" in tt, json.dumps([g_b, g_a, tt]))
        check("tuning 6.8: no page errors", not errs, "; ".join(errs[:3]))
        page.evaluate("AQ.game.reset(); AQ.game.save()")
        browser.close()

def standalone_ios():
    """Job 3: old-iPad home-screen standalone. Static: exactly one of each iOS web-app tag, manifest display standalone,
    start_url / scope ./ resolving to the page folder at the root AND under /Fish-Aquarium/, apple-touch-icon 200 with no
    redirect; no code path navigates (reload / location / window.open / links / service worker). Live: WebKit (or Chromium
    if WebKit is not installed) with an iPad iOS 12 Safari user agent and navigator.standalone = true: the game runs and
    the main frame never navigates or unloads through load, every tool, the shop tabs, edit mode, debug Reset."""
    import urllib.request, urllib.parse, urllib.error, re
    VIEW[0] = "standalone iOS"
    root = os.path.join(HERE, "..")
    html = open(os.path.join(root, "index.html")).read(); head = html.split("</head>")[0]
    man = json.load(open(os.path.join(root, "manifest.webmanifest")))
    cnt = lambda pat: len(re.findall(pat, head, re.I))
    ok_meta = (cnt(r'<meta name="apple-mobile-web-app-capable" content="yes">') == 1 and cnt(r'name="apple-mobile-web-app-capable"') == 1
               and cnt(r'name="mobile-web-app-capable"') == 1 and cnt(r'name="apple-mobile-web-app-status-bar-style" content="black-translucent"') == 1
               and cnt(r'name="apple-mobile-web-app-status-bar-style"') == 1 and cnt(r'rel="apple-touch-icon"') == 1 and cnt(r'rel="manifest"') == 1
               and cnt(r'name="viewport"[^>]*viewport-fit=cover') == 1 and cnt(r'http-equiv="refresh"') == 0)
    check("iOS web-app tags: exactly one apple-mobile-web-app-capable yes, mobile-web-app-capable, black-translucent status bar, apple-touch-icon, manifest link, viewport-fit=cover; no meta refresh",
          ok_meta, head[:0])
    res = {}
    for base in ("https://example.trycloudflare.com/", "https://fatum22.github.io/Fish-Aquarium/"):
        m = urllib.parse.urljoin(base, "manifest.webmanifest")
        res[base] = [urllib.parse.urljoin(m, man["start_url"]), urllib.parse.urljoin(m, man["scope"]), urllib.parse.urljoin(m, man.get("id", man["start_url"]))]
    check("manifest: display standalone (fullscreen via display_override), start_url / scope / id ./ resolve to exactly the added page URL at the tunnel root and under /Fish-Aquarium/",
          man["display"] == "standalone" and "fullscreen" in man.get("display_override", []) and all(v == [k, k, k] for k, v in res.items()), json.dumps(res))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    op = urllib.request.build_opener(NoRedirect)
    st = {}
    for path in ("", "icons/icon-180.png", "manifest.webmanifest", "icons/icon-192.png"):
        try:
            r = op.open(BASE + path); st[path or "/"] = [r.status, r.headers.get("Content-Type", "")]
        except urllib.error.HTTPError as e:
            st[path or "/"] = [e.code, e.headers.get("Location", "")]
    check("page, apple-touch-icon 180, manifest and icon 192 answer 200 directly (no redirect); icon is image/png",
          all(v[0] == 200 for v in st.values()) and st["icons/icon-180.png"][1].startswith("image/png"), json.dumps(st))
    src = "".join(open(os.path.join(root, f)).read() for f in ("index.html", "config.js", "js/main.js", "js/game.js", "js/fishart.js", "js/fishdata.js", "decor/decor-v1-data.js"))
    nav = re.findall(r"location\.(?:reload|replace|assign)\s*\(|location\.href\s*=|location\s*=[^=]|window\.open\s*\(|serviceWorker|<a\s[^>]*href=|<form|history\.(?:go|back|forward)\s*\(", src)
    check("no code path navigates away (no location.reload / replace / assign / href =, window.open, links, forms, history.go, service worker)", not nav, json.dumps(nav[:5]))
    UA = "Mozilla/5.0 (iPad; CPU OS 12_5_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1.2 Mobile/15E148 Safari/604.1"
    with sync_playwright() as p:
        try:
            browser = p.webkit.launch(); engine = "webkit"
        except Exception:
            browser = p.chromium.launch(); engine = "chromium (webkit not installed)"
        ctx = browser.new_context(viewport={"width": 1024, "height": 768}, user_agent=UA, has_touch=True, is_mobile=engine == "webkit" or None, device_scale_factor=2)
        ctx.add_init_script("""Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true, configurable: true });
            window.addEventListener('beforeunload', () => { try { sessionStorage.setItem('aq-unloads', String(+(sessionStorage.getItem('aq-unloads') || 0) + 1)); } catch (_) {} });""")
        page = ctx.new_page(); errs = []; navs = []; pages = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("framenavigated", lambda f: f == page.main_frame and navs.append(f.url))
        ctx.on("page", lambda pg: pages.append(pg.url))
        page.goto(BASE); page.wait_for_function("window.AQ && window.AQ.game", timeout=20000); page.wait_for_timeout(500)
        info = page.evaluate("({ sa: navigator.standalone, ua: navigator.userAgent, fish: AQ.game.state.fish.length, w: innerWidth })")
        page.evaluate("document.querySelectorAll('.modal').forEach((m) => { if (!m.hidden && m.querySelector('.btn')) {} })")
        steps = []
        def step(name, fn):
            try: fn(); page.wait_for_timeout(150); steps.append([name, True])
            except Exception as e: steps.append([name, str(e)[:120]])
        for t in ("food", "sponge", "net", "brush", "hand"):
            step("tool " + t, lambda t=t: page.evaluate(f"AQ.setTool('{t}')"))
        tb = page.locator("#tank").bounding_box()
        step("tap tank", lambda: page.mouse.click(tb["x"] + tb["width"] / 2, tb["y"] + tb["height"] / 2))
        for tab in ("fish", "food", "decor"):
            step("shop " + tab, lambda tab=tab: page.evaluate(f"AQ.openShop(); AQ.setShopTab('{tab}')"))
        step("shop close", lambda: page.evaluate("document.querySelector('#shop-close').click()"))
        step("buy leaf + edit", lambda: page.evaluate("(() => { const G = AQ.game; G.state.gold += 50; const d = G.buyDecor('leaf'); AQ.setTool('brush'); AQ.selectDecor(d.id); })()"))
        step("edit done", lambda: page.evaluate("document.getElementById('deco-done').click()"))
        step("debug unlock", lambda: page.evaluate("AQ.openDebug('123456')"))
        step("debug reset", lambda: (page.evaluate("document.getElementById('dbg-reset').click()"), page.wait_for_timeout(100), page.evaluate("document.getElementById('confirm-yes').click()")))
        page.wait_for_timeout(400)
        after = page.evaluate("({ unloads: +(sessionStorage.getItem('aq-unloads') || 0), url: location.href, alive: !!(window.AQ && AQ.game), decor: AQ.game.state.decor.length })")
        browser.close()
    check(f"iPad iOS 12 Safari UA + navigator.standalone true ({engine}): the game runs; through load, every tool, a tank tap, all shop tabs, edit mode and debug Reset the page never navigates, unloads or opens a window",
          info["sa"] is True and "iPad" in info["ua"] and len(navs) == 1 and navs[0].rstrip("/") == BASE.rstrip("/") and not pages and after["unloads"] == 0 and after["url"] == navs[0]
          and after["alive"] and after["decor"] == 0 and all(s[1] is True for s in steps) and not errs, json.dumps({"info": info, "navs": navs, "pages": pages, "after": after, "steps": [s for s in steps if s[1] is not True], "errs": errs[:3]}))

FIX_SHOTS = os.path.join(HERE, "..", "screenshots", "fixes")

def tank_corners():
    """Job 2 (Maksims-approved): square tank corners: border-radius 0 / no clip-path on the tank frame, the canvas (water,
    sand, glass, dirt film and glass overlay are all drawn full-rect on it), their pseudo-elements and every overlay layer
    that covers the whole tank; the frame ring is square too; the subtle glass highlight line stays on the RIGHT."""
    os.makedirs(FIX_SHOTS, exist_ok=True)
    dif = lambda p, q: sum(abs(u - v) for u, v in zip(p, q))
    FRAME = (0x1d, 0x4b, 0x6b)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (VW, VH) in ((844, 390), (1180, 820)):
            VIEW[0] = f"tank-corners {VW}x{VH}"
            ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=1)
            page = ctx.new_page(); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(300)
            ev = lambda body: page.evaluate("() => { " + JS + body + " }")
            ev("fresh(); G.state.speed = 1;"); page.wait_for_timeout(350)
            css = page.evaluate("""(() => { const k = document.getElementById('tank-wrap').getBoundingClientRect(), out = [];
                const rad = (c) => [c.borderTopLeftRadius, c.borderTopRightRadius, c.borderBottomRightRadius, c.borderBottomLeftRadius];
                const add = (name, el, pse) => { const c = getComputedStyle(el, pse || null); out.push({ name, rad: rad(c), clip: c.clipPath }); return out[out.length - 1]; };
                for (const id of ['tank-wrap', 'tank']) { const el = document.getElementById(id); add(id, el); add(id + '::before', el, '::before'); add(id + '::after', el, '::after'); }
                for (const m of document.querySelectorAll('#tank-wrap > .modal')) { const h = m.hidden; m.hidden = false; const r = m.getBoundingClientRect();
                  add('#' + m.id, m).covers = Math.abs(r.width - k.width) < 1 && Math.abs(r.height - k.height) < 1; m.hidden = h; }
                return out; })()""")
            mods = [q for q in css if q["name"].startswith("#")]
            check("Maksims: square tank corners in CSS: border-radius 0 (all 4) and no clip-path on #tank-wrap, #tank, their ::before / ::after and every overlay that covers the whole tank",
                  all(r == "0px" for q in css for r in q["rad"]) and all(q["clip"] == "none" for q in css) and len(mods) >= 3 and all(q["covers"] for q in mods), json.dumps(css))
            def grab():
                tb = page.locator("#tank").bounding_box(); m = 8
                png = page.screenshot(clip={"x": tb["x"] - m, "y": tb["y"] - m, "width": tb["width"] + 2 * m, "height": tb["height"] + 2 * m}); _w, _h, px = png_rgb(png)
                return tb, (lambda x, y: px(int(x + m), int(y + m)))  # tank-local CSS px (dpr 1)
            def corners(tb, P):
                Wt, Ht = int(tb["width"]), int(tb["height"]); out = {}
                for k, cx, cy, sx, sy in (("tl", 0, 0, 1, 1), ("tr", Wt - 1, 0, -1, 1), ("bl", 0, Ht - 1, 1, -1), ("br", Wt - 1, Ht - 1, -1, -1)):
                    c = P(cx, cy)
                    out[k] = {"nb": min(dif(c, P(cx + sx * a, cy + sy * b)) for a, b in ((2, 2), (4, 0), (0, 4), (1, 0), (0, 1))),
                              "vsFrame": dif(c, FRAME), "outside": dif(P(cx - sx * 2, cy - sy * 2), FRAME)}
                return out
            ok_c = lambda cs: all(v["nb"] < 30 and v["vsFrame"] > 40 and v["outside"] < 16 for v in cs.values())
            tb, P = grab(); c_clean = corners(tb, P)
            gm = page.evaluate("AQ.geom()"); gl = page.evaluate("AQ.glassLine()")
            yl = (gm["surf"] + gm["sand"]) / 2; lum = lambda q: sum(q)
            right = lum(P(gl["x"], yl)) - lum(P(gl["x"] - 9, yl)); left = lum(P(gm["inset"], yl)) - (lum(P(gm["inset"] - 5, yl)) + lum(P(gm["inset"] + 5, yl))) / 2
            top = lum(P(gl["x"], 1)) - lum(P(gl["x"] - 9, 1))
            page.screenshot(path=os.path.join(FIX_SHOTS, f"corners_{VW}.png"))
            ev("toStage(5);"); page.wait_for_timeout(400)
            tb5, P5 = grab(); c_dirty = corners(tb5, P5); film = page.evaluate("AQ.filmInfo()")
            check("Maksims: the very corner pixels are tank (not frame) and the frame ring is square (frame colour diagonally outside every corner), clean and at dirt max with the stage-5 film + glass overlay drawn",
                  ok_c(c_clean) and ok_c(c_dirty) and film["strength"] > 0, json.dumps({"clean": c_clean, "dirtMax": c_dirty, "film": film["strength"]}))
            check("Maksims: the subtle glass highlight line stays on the tank's RIGHT edge (VISUAL.glassLineSide 'right', at W - inset, visible in the water and the air gap); none on the left",
                  gl["side"] == "right" and abs(gl["x"] - (gm["W"] - gm["inset"])) < 1e-6 and gl["x"] > gm["W"] / 2 and right > 20 and top > 20 and left < 20,
                  json.dumps({"line": gl, "right": right, "top": top, "left": left}))
            check("tank corners: no page errors", not errs, "; ".join(errs[:3]))
            ctx.close()
        browser.close()

DECOR_SHOTS = os.path.join(HERE, "..", "screenshots", "decor")

def decor_v1():
    """Job 2 (approved by Maksims, art approved with no extra review): the 10 shop decorations from tuning
    decorations.shopItems + art/DECOR_V1.md. Shop: leaf, stone, then the 10 in ladder order; locked ones greyed with
    'Unlocks at Aquarium Lv {N}'; price from tuning; placeXp on the first buy of each type only; sell floor(pricePaid / 2);
    the same edit menu / drag / resize for every piece; height cap maxHeightScale (castle 1.8); traced hit outline;
    corals recolour light (0) to dark (100) through coralColors / tintSvg; every asset loads 200 from relative decor/ URLs."""
    os.makedirs(DECOR_SHOTS, exist_ok=True)
    tj = merged_tuning(); SI = tj["decorations"]["shopItems"]; items = SI["items"]; ids = [i["id"] for i in items]
    lvl_xp = tj["tank"]["levelAtXp"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (VW, VH) in ((844, 390), (1180, 820)):
            VIEW[0] = f"decor-v1 {VW}x{VH}"
            ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=1)
            page = ctx.new_page(); errs = []; resp = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("response", lambda r: resp.append([r.status, r.url]))
            page.goto(BASE + "?speed=1"); page.wait_for_function("window.AQ && window.AQ.game"); page.wait_for_timeout(300)
            ev = lambda body: page.evaluate("() => { " + JS + body + " }")
            def shop_cards():
                return page.evaluate("""[...document.querySelectorAll('#shop-decor .card')].map((c) => { const b = c.querySelector('button');
                    return { id: b.dataset.buydecor, n: c.querySelector('.n').textContent, price: c.querySelector('.price').textContent, priceHidden: c.querySelector('.price').hidden,
                      dis: b.disabled, locked: c.classList.contains('locked'), lbl: b.querySelector('.lbl').textContent, filter: getComputedStyle(c).filter, op: +getComputedStyle(c).opacity }; })""")
            def open_decor_shop():
                page.evaluate("AQ.openShop(); AQ.setShopTab('decor')"); page.wait_for_timeout(200)
            # shop at Aquarium Lv 1: leaf, stone, then all 10 in ladder order, all 10 locked (greyed, label, no price, disabled)
            ev("fresh(); G.state.gold = 99999; G.state.tank.xp = 0;")
            open_decor_shop(); c1 = shop_cards()
            exp_ids = ["leaf", "stone"] + ids
            lab = lambda n: SI["lockedLabel"].replace("{N}", str(n))
            ok1 = [c["id"] for c in c1] == exp_ids and all(c["n"] == it["name"] and c["price"] == str(it["price"]) for c, it in zip(c1[2:], items)) \
                and all(c["locked"] and c["dis"] and c["priceHidden"] and c["lbl"] == lab(it["unlockTankLevel"]) and "grayscale" in c["filter"] and c["op"] < 0.7 for c, it in zip(c1[2:], items)) \
                and not c1[0]["locked"] and not c1[1]["locked"]
            check("shop at Aquarium Lv 1: Leaf, Stone, then the 10 shop decorations in ladder order with tuning names / prices; all 10 locked: greyed like locked food packs, disabled, 'Unlocks at Aquarium Lv {N}' instead of the price",
                  ok1, json.dumps(c1[:4]))
            # the shop fits (no horizontal overflow) and scrolls to the last card
            fit = page.evaluate("""(() => { const s = document.getElementById('shop-scroll'), r = s.getBoundingClientRect(); const cards = [...document.querySelectorAll('#shop-decor .card')];
                const over = cards.filter((c) => { const q = c.getBoundingClientRect(); return q.left < r.left - 0.5 || q.right > r.right + 0.5; }).length;
                s.scrollTop = 1e6; const last = cards[cards.length - 1].getBoundingClientRect(); const lr = s.getBoundingClientRect();
                return { over, sw: s.scrollWidth, cw: s.clientWidth, sh: s.scrollHeight, ch: s.clientHeight, lastIn: last.top >= lr.top - 0.5 && last.bottom <= lr.bottom + 0.5, vw: innerWidth, vh: innerHeight, sb: lr.bottom }; })()""")
            page.wait_for_timeout(100)
            check("decor shop fits the screen (no card cut off sideways, no horizontal scroll) and scrolls to the last card (Sunken Ship fully visible)",
                  fit["over"] == 0 and fit["sw"] <= fit["cw"] + 1 and fit["lastIn"] and fit["sb"] <= VH + 0.5, json.dumps(fit))
            page.evaluate("document.getElementById('shop-scroll').scrollTop = 0")
            # unlock gating per level: at each Aquarium level exactly the items with unlockTankLevel <= level are buyable
            gate = []
            for lv in range(1, 8):
                ev(f"G.state.tank.xp = {lvl_xp[lv - 1]}; AQ.openShop(); AQ.setShopTab('decor');"); page.wait_for_timeout(60)
                cs = shop_cards()[2:]
                lvn = ev("return G.tankInfo().level;")
                gate.append([lvn, [c["id"] for c in cs if not c["locked"] and not c["dis"]], [c["id"] for c in cs if c["locked"]]])
            ok_g = all(g[0] == lv and g[1] == [it["id"] for it in items if it["unlockTankLevel"] <= lv] and g[2] == [it["id"] for it in items if it["unlockTankLevel"] > lv] for lv, g in zip(range(1, 8), gate))
            ev(f"G.state.tank.xp = {lvl_xp[3]}; G.state.gold = 1234; AQ.openShop(); AQ.setShopTab('decor');"); page.wait_for_timeout(400)
            trunc = page.evaluate("[...document.querySelectorAll('#shop-decor .card.locked .lbl')].filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent)")
            check("locked labels 'Unlocks at Aquarium Lv {N}' are shown in full (not cut off with an ellipsis)", not trunc, json.dumps(trunc))
            if VW == 844: page.evaluate("document.getElementById('shop-scroll').scrollTop = 1e6"); page.wait_for_timeout(150)  # show the locked row too
            page.screenshot(path=os.path.join(DECOR_SHOTS, f"shop_{VW}.png"))
            # Art Director nit: portraits fit the card by their limiting dimension (contain on the art's opaque bounds), locked cards too
            def portraits():
                page.wait_for_function("[...document.querySelectorAll('#shop-decor .card[data-decor] canvas')].slice(2).every((c) => c.dataset.art)", timeout=10000)
                return page.evaluate("""[...document.querySelectorAll('#shop-decor .card')].slice(2).map((card) => { const cv = card.querySelector('canvas'), q = cv.getBoundingClientRect(), k = card.getBoundingClientRect();
                    const [x, y, w, h] = cv.dataset.art.split(',').map(Number), sx = q.width / cv.width, sy = q.height / cv.height;
                    const px = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height - 19).data; let c0 = cv.width, c1 = -1;
                    for (let j = 0; j < cv.height - 19; j++) for (let i = 0; i < cv.width; i++) if (px[(j * cv.width + i) * 4 + 3] > 8) { c0 = Math.min(c0, i); c1 = Math.max(c1, i); }
                    return { id: card.dataset.decor, locked: card.classList.contains('locked'), wFrac: w * sx / q.width, hFrac: h * sy / q.height, inCanvas: x >= -0.5 && y >= -0.5 && x + w <= cv.width + 0.5 && y + h <= cv.height + 0.5,
                      inCard: q.left >= k.left - 0.5 && q.right <= k.right + 0.5 && q.top >= k.top - 0.5 && q.bottom <= k.bottom + 0.5, limit: Math.max(w / (cv.width - 4), h / (cv.height - 4)), pxFrac: (c1 - c0 + 1) / cv.width }; })""")
            pt = {}
            for lv in (4, 7):  # Lv 4: the ship card is locked (greyed); Lv 7: unlocked
                ev(f"G.state.tank.xp = {lvl_xp[lv - 1]}; AQ.openShop(); AQ.setShopTab('decor');"); page.wait_for_timeout(100)
                pt[lv] = portraits()
            ship = {lv: next(q for q in v if q["id"] == "shipwreck") for lv, v in pt.items()}
            castle = next(q for q in pt[7] if q["id"] == "castle")
            check("shop portraits fit the card by their limiting dimension (contain): the Sunken Ship fills >= 85% of the portrait width, locked (Lv 4) and unlocked (Lv 7); "
                  "every piece touches one side (limit ~1), tall pieces (Castle) use the height and stay inside; no portrait outside its canvas, no canvas outside its card",
                  all(ship[lv]["wFrac"] >= 0.85 and ship[lv]["pxFrac"] >= 0.8 for lv in ship) and ship[4]["locked"] and not ship[7]["locked"]
                  and castle["hFrac"] >= 0.9 and castle["wFrac"] < 0.6 and all(q["inCanvas"] and q["inCard"] and abs(q["limit"] - 1) < 0.01 for v in pt.values() for q in v),
                  json.dumps({"ship": ship, "castle": castle, "bad": [q for v in pt.values() for q in v if not (q["inCanvas"] and q["inCard"] and abs(q["limit"] - 1) < 0.01)]}))
            if VW == 844:
                page.evaluate("document.getElementById('shop-scroll').scrollTop = 1e6"); page.wait_for_timeout(150)
                page.screenshot(path=os.path.join(DECOR_SHOTS, "shop_ship_844.png"))
            page.evaluate("document.querySelector('#shop-close').click()")
            refused = ev(f"""G.state.tank.xp = 0; G.state.gold = 99999; const out = {{}};
                for (const it of T.decorations.shopItems.items) {{ const g = G.state.gold, r = G.buyDecor(it.id); out[it.id] = [r === null, G.state.gold - g, G.state.decor.length]; }} return out;""")
            check("unlock gating: at Aquarium Lv 1..7 exactly the items with unlockTankLevel <= level are buyable (the rest locked); buying a locked one is refused (no gold taken, nothing placed)",
                  ok_g and all(v == [True, 0, 0] for v in refused.values()), json.dumps([gate, refused]))
            # prices, XP once per type, pricePaid, sell floor(pricePaid / 2), XP never taken back
            buy = ev("""fresh(); G.state.gold = 999999; G.state.tank.xp = T.tank.levelAtXp[T.tank.levelAtXp.length - 1]; G.state.decorBought = {}; const out = {};
                for (const it of T.decorations.shopItems.items) { const r = [];
                  for (let k = 0; k < 2; k++) { if (G.state.decor.length >= 12) G.state.decor.length = 0; const g = G.state.gold, x = G.state.tank.xp, d = G.buyDecor(it.id);
                    r.push([g - G.state.gold, G.state.tank.xp - x, d.pricePaid, d.color]); const g2 = G.state.gold, x2 = G.state.tank.xp; const ref = G.sellDecor(d.id); r.push([ref, G.state.gold - g2, G.state.tank.xp - x2]); }
                  out[it.id] = r; } return { out, bought: Object.keys(G.state.decorBought) };""")
            exp_buy = {it["id"]: [[it["price"], it["placeXp"], it["price"], it.get("defaultColor", 50)], [it["price"] // 2, it["price"] // 2, 0],
                                  [it["price"], 0, it["price"], it.get("defaultColor", 50)], [it["price"] // 2, it["price"] // 2, 0]] for it in items}
            check("buying: each shop decoration costs its tuning price (pricePaid stored); placeXp only on the FIRST buy of each type (a rebuy after selling pays 0 XP); selling refunds floor(pricePaid / 2) and never removes XP",
                  buy["out"] == exp_buy and all(i in buy["bought"] for i in ids), json.dumps({k: buy["out"][k] for k in list(buy["out"])[:3]}))
            # place all 10, then edit: tap selects via the traced outline, drag moves, d-pad + resize, castle height cap 1.8
            placed = ev("""fresh(); G.state.gold = 999999; G.state.tank.xp = T.tank.levelAtXp[T.tank.levelAtXp.length - 1]; G.state.decor = []; const out = {};
                for (const it of T.decorations.shopItems.items) { const d = G.buyDecor(it.id); d.x = -1; out[it.id] = d.id; } G.save(); return out;""")
            page.wait_for_timeout(2500)
            art = page.evaluate("AQ.decorArt()")
            check("all 10 placed pieces get a cached bitmap (SVG rastered once into an offscreen canvas, drawn every frame from the cache)",
                  all(art["keys"][placed[i]] in art["ready"] for i in ids) and art["pending"] == 0, json.dumps({"ready": len(art["ready"]), "pending": art["pending"]}))
            cid = placed["castle"]
            ev(f"G.state.decor.forEach((q) => {{ q.x = q.id === '{cid}' ? 0.35 : -5; q.y = 0.5; }}); AQ.setTool('brush');"); page.wait_for_timeout(150)
            gq = page.evaluate("AQ.geom()"); tb = page.locator("#tank").bounding_box()
            z = next(q for q in page.evaluate("AQ.decorScreen()") if q["id"] == cid)
            J = page.evaluate("DECOR_V1.castle")
            tx = lambda u: z["bx"] + (u - J["anchor"]["x"]) * z["sx"]; ty = lambda v: z["by"] + (v - J["anchor"]["y"]) * z["sy"]
            miss = page.evaluate(f"AQ.decorHitAt({tx(385)}, {ty(100)})"); hitc = page.evaluate(f"AQ.decorHitAt({tx(200)}, {ty(300)})")
            page.mouse.click(tb["x"] + tx(200), tb["y"] + ty(300)); page.wait_for_timeout(120); sel = page.evaluate("AQ.edit()")
            check("tap test uses the traced hit outline: a tap on the castle tower selects it; a tap inside its box but on empty water (top-right corner) does not",
                  hitc == cid and miss is None and sel["selDecor"] == cid and sel["menu"], json.dumps([hitc, miss, sel["selDecor"]]))
            # drag
            page.mouse.move(tb["x"] + tx(200), tb["y"] + ty(300)); page.mouse.down(); page.mouse.move(tb["x"] + tx(200) + 60, tb["y"] + ty(300) + 5, steps=6); page.mouse.up(); page.wait_for_timeout(80)
            z2 = next(q for q in page.evaluate("AQ.decorScreen()") if q["id"] == cid)
            # d-pad
            page.click('#deco-menu [data-move="left"]'); page.wait_for_timeout(40)
            z3 = next(q for q in page.evaluate("AQ.decorScreen()") if q["id"] == cid)
            # resize to the cap
            for _ in range(8): page.click('#deco-menu [data-size="taller"]'); page.wait_for_timeout(15)  # 1.0 -> 1.8 by real taps
            page.evaluate("for (let i = 0; i < 6; i++) { document.querySelector('#deco-menu [data-size=\"taller\"]').click(); document.querySelector('#deco-menu [data-size=\"wider\"]').click(); }")
            for _ in range(4): page.click('#deco-menu [data-size="wider"]'); page.wait_for_timeout(15)  # 1.6 -> 2.0
            capd = ev(f"const d = G.state.decor.find((q) => q.id === '{cid}'); return [d.sh, d.sw, document.querySelector('#deco-menu [data-size=\"taller\"]').classList.contains('capped'), document.querySelector('#deco-menu [data-size=\"wider\"]').classList.contains('capped'), document.getElementById('dm-scale').textContent];")
            ev(f"const d = G.state.decor.find((q) => q.id === '{cid}'); d.y = 0; AQ.selectDecor(d.id);"); page.wait_for_timeout(60)
            zc = next(q for q in page.evaluate("AQ.decorScreen()") if q["id"] == cid)
            top = zc["by"] - J["heightAboveBasePx"] * 4 * zc["sy"]  # art top = heightAboveBase compact px = x4 units
            check("castle: drag moves it (+60 px), the d-pad moves it 8 px, Taller stops at maxHeightScale 1.8 (button capped), Wider at 2.0; at the back of the sand at 1.8x its top stays >= 4% of water height below the surface",
                  abs(z2["bx"] - z["bx"] - 60) < 1.5 and abs(z3["bx"] - z2["bx"] + 8) < 0.6 and capd[:4] == [1.8, 2.0, True, True] and J["maxHeightScale"] == 1.8
                  and top >= gq["surf"] + 0.04 * gq["waterH"] - 0.5, json.dumps([z["bx"], z2["bx"], z3["bx"], capd, top, gq["surf"] + 0.04 * gq["waterH"]]))
            others = ev("""const out = {}; for (const d of G.state.decor) { if (d.type === 'castle') continue; d.sh = 1.9; AQ.selectDecor(d.id); for (let i = 0; i < 3; i++) document.querySelector('#deco-menu [data-size="taller"]').click(); out[d.type] = d.sh; } return out;""")
            check("every other shop decoration goes up to height 2.0 (maxHeightScale 2)", all(v == 2.0 for v in others.values()) and len(others) == 9, json.dumps(others))
            # same menu for every piece; colour slider only on the corals
            menus = ev("""const out = {}; for (const d of G.state.decor) { AQ.selectDecor(d.id); const m = document.getElementById('deco-menu').getBoundingClientRect(), c = document.getElementById('dm-color');
                out[d.type] = [Math.round(m.width), Math.round(m.height), getComputedStyle(c).visibility, document.querySelectorAll('#deco-menu [data-size]').length, document.querySelectorAll('#deco-menu [data-move]').length, document.getElementById('dm-title').textContent]; } return out;""")
            m0 = menus[ids[0]]
            check("every piece opens the same edit menu (same size, 4 Move + 4 Size buttons, Sell); title = tuning name; the colour slider shows only on the 4 corals",
                  all(v[:2] == m0[:2] and v[3:5] == [4, 4] for v in menus.values()) and all((v[2] == "visible") == it["colorSlider"] and v[5] == it["name"] for it in items for k, v in menus.items() if k == it["id"]),
                  json.dumps(menus))
            # sell confirm text for the castle
            ev(f"AQ.selectDecor('{cid}');"); page.wait_for_timeout(50)
            sb = page.inner_text("#dm-sell"); page.click("#dm-sell"); page.wait_for_timeout(80); st = page.inner_text("#confirm-text"); page.click("#confirm-no")
            check("castle sell: 'Sell · refund 500 gold' / 'Sell this castle ruins? You get 500 gold back.'", sb == "Sell · refund 500 gold" and st == "Sell this castle ruins? You get 500 gold back.", json.dumps([sb, st]))
            # coral colour mapping: slider 0 light .. 100 dark, via coralColors / tintSvg; track = shadeRamp, thumb = base
            cor = page.evaluate("""() => { const out = {}; const L = (h) => { const n = parseInt(h.slice(1), 16), r = (n >> 16) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255; return (Math.max(r, g, b) + Math.min(r, g, b)) / 2; };
                for (const id of ['coralFan', 'coralStaghorn', 'coralBrain', 'coralTube']) { const J = DECOR_V1[id]; const ls = [0, 25, 50, 75, 100].map((v) => L(coralColors(id, v).base));
                  out[id] = { ends: [coralColors(id, 0).base, coralColors(id, 50).base, coralColors(id, 100).base], ramp: [J.shadeRamp[0], J.shadeRamp[2], J.shadeRamp[4]], dark: ls.every((l, i) => !i || l < ls[i - 1]),
                    same50: J.svgTintKeys.base === coralColors(id, 50).base }; } return out; }""")
            fan = placed["coralFan"]
            ev(f"G.state.decor.forEach((q) => {{ q.x = q.id === '{fan}' ? 0.3 : -5; q.y = 0.5; q.sh = 1; q.sw = 1; }}); AQ.selectDecor('{fan}');"); page.wait_for_timeout(100)
            def set_slider(v):
                page.evaluate(f"(() => {{ const c = document.getElementById('dm-color'); c.value = {v}; c.dispatchEvent(new Event('input', {{ bubbles: true }})); c.dispatchEvent(new Event('change', {{ bubbles: true }})); }})()")
                page.wait_for_function(f"(() => {{ const a = AQ.decorArt(); return a.last['{fan}'] === a.keys['{fan}']; }})()", timeout=10000); page.wait_for_timeout(80)
                return page.evaluate(f"""(() => {{ const c = document.getElementById('tank'), k = c.width / AQ.geom().W, z = AQ.decorScreen().find((q) => q.id === '{fan}');
                    const x0 = Math.round((z.bx - 12) * k), y0 = Math.round((z.by - z.h * 0.6) * k), w = Math.round(24 * k), h = Math.round(z.h * 0.3 * k);
                    const px = c.getContext('2d').getImageData(x0, y0, w, h).data; let s = 0, n = 0; for (let i = 0; i < px.length; i += 4) {{ s += 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]; n++; }}
                    const el = document.getElementById('dm-color'); return {{ lum: s / n, color: AQ.game.state.decor.find((q) => q.id === '{fan}').color, track: el.style.getPropertyValue('--track'), thumb: el.style.getPropertyValue('--thumb') }}; }})()""")
            s0 = set_slider(0); s100 = set_slider(100); s50 = set_slider(50)
            ramp = page.evaluate("DECOR_V1.coralFan.shadeRamp"); c0 = page.evaluate("coralColors('coralFan', 0).base"); c100 = page.evaluate("coralColors('coralFan', 100).base")
            hexrgb = lambda h: f"rgb({int(h[1:3], 16)}, {int(h[3:5], 16)}, {int(h[5:7], 16)})"
            check("coral colour mapping (DECOR_V1 5): for all 4 corals slider 0 / 50 / 100 = shadeRamp stops 0 / 2 / 4, base gets darker at every step, slider 50 = the SVG as drawn",
                  all(v["ends"] == v["ramp"] and v["dark"] and v["same50"] for v in cor.values()), json.dumps(cor))
            check("Fan Coral slider in the game: 0 is lighter than 50, 50 lighter than 100 on the tank canvas (re-tinted bitmap); track = shadeRamp gradient, thumb = coralColors(v).base",
                  s0["color"] == 0 and s100["color"] == 100 and s0["lum"] > s50["lum"] > s100["lum"] and all(hexrgb(r) in s50["track"] or r in s50["track"] for r in ramp)
                  and (s0["thumb"] in (c0, hexrgb(c0))) and (s100["thumb"] in (c100, hexrgb(c100))), json.dumps([s0["lum"], s50["lum"], s100["lum"], s50["track"], s0["thumb"], s100["thumb"]]))
            # screenshot: all 10 in the tank (edit mode off)
            ev("""AQ.setTool('hand'); const P = { castle: [0.86, 0, 1], coralStaghorn: [0.66, 0.05, 1], coralFan: [0.3, 0.02, 1], coralTube: [0.5, 0.12, 1], shipwreck: [0.47, 0.55, 0.9],
                driftwood: [0.2, 0.9, 0.8], coralBrain: [0.68, 1.05, 1], amphora: [0.12, 0.35, 1], chest: [0.8, 1.3, 1], helmet: [0.35, 1.4, 1] };
                G.state.decor.forEach((d) => { const q = P[d.type]; d.x = q[0]; d.y = q[1]; d.sh = q[2]; d.sw = q[2]; d.color = 50; }); G.state.dirt.spots = []; G.state.dirt.t = 0; G.save();""")
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(DECOR_SHOTS, f"tank_all10_{VW}.png"))
            # assets: every decor file the game asked for came back 200 from a relative decor/ URL
            dec = [r for r in resp if "/decor/" in r[1]]
            svgs = {i for i in ids if any(r[1].split("?")[0].endswith(f"/decor/{i}.svg") for r in dec)}
            rel = page.evaluate("[...document.scripts].map((s) => s.getAttribute('src')).filter((s) => s && s.includes('decor'))")
            # shop / confirm portraits are drawn from the SVGs themselves (contain on the art's opaque bounds), so the square thumbs are not requested any more
            check("assets: decor-v1-data.js and all 10 SVGs (also the shop portraits) load with HTTP 200 from relative decor/ URLs (works under a GitHub Pages subpath); no 4xx/5xx",
                  dec and all(r[0] == 200 for r in dec) and svgs == set(ids) and rel == ["decor/decor-v1-data.js?" + rel[0].split("?")[1]] and not any(r[0] >= 400 for r in resp),
                  json.dumps({"n": len(dec), "bad": [r for r in resp if r[0] >= 400][:3], "svgs": sorted(set(ids) - svgs), "rel": rel}))
            check("decorations v1: no page errors", not errs, "; ".join(errs[:3]))
            ev("G.reset(); G.save();")
            ctx.close()
        browser.close()

CLOCK_INIT = """(() => {
  // real_clock test harness: Date.now() = real wall clock + an offset (kept in localStorage so it survives a reload / a new
  // tab); performance.now() and rAF can be frozen like iOS does while the device is locked or the app is in the background
  // (their timestamps do not advance while suspended); document.hidden / visibilitychange / pageshow are simulated.
  const K = '__aq_clock_off', realNow = Date.now.bind(Date), rawPerf = performance.now.bind(performance), rawRaf = window.requestAnimationFrame.bind(window);
  let o = 0; try { o = +(localStorage.getItem(K) || 0); } catch (e) { /* ignore */ }
  let frozen = false, frozenAt = 0, perfOff = 0, held = [], hidden = false, frames = 0;
  Date.now = () => realNow() + o;
  performance.now = () => (frozen ? frozenAt : rawPerf() - perfOff);
  const wrap = (cb) => (t) => { if (frozen) { held.push(cb); return; } frames++; cb(t - perfOff); };
  window.requestAnimationFrame = (cb) => rawRaf(wrap(cb));
  Object.defineProperty(Document.prototype, 'hidden', { get: () => hidden, configurable: true });
  Object.defineProperty(Document.prototype, 'visibilityState', { get: () => (hidden ? 'hidden' : 'visible'), configurable: true });
  window.__clk = {
    add(ms) { o += ms; try { localStorage.setItem(K, String(o)); } catch (e) { /* ignore */ } return o; },
    off: () => o, frames: () => frames, perf: () => performance.now(),
    freeze() { if (!frozen) { frozenAt = rawPerf() - perfOff; frozen = true; } },
    thaw() { if (frozen) { perfOff = rawPerf() - frozenAt; frozen = false; const h = held; held = []; h.forEach((cb) => rawRaf(wrap(cb))); } },
    hide() { hidden = true; document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('blur')); },
    show() { hidden = false; document.dispatchEvent(new Event('visibilitychange')); },
    pageshow(persisted) { window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: !!persisted })); },
    focus() { window.dispatchEvent(new Event('focus')); },
  };
})();"""

def real_clock():
    """Maksims TOP PRIORITY: game time must follow the REAL wall clock through a device lock, an app switch, a closed tab and
    a reload (iOS / iPadOS home-screen app). performance.now() / rAF timestamps stop while iOS suspends the page, so the game
    accounts time from Date.now() (state.lastSeen = wall clock accounted up to); on return the SAME catch-up as on load runs
    (7-day cap, clock backwards = 0, meal rules, dirt 1.5/3/6/12/24 h since the last clean with or without fish), exactly once."""
    tj = merged_tuning(); gup = next(s for s in tj["species"] if s["id"] == "guppy")
    dsec = tj["deathSecByRarity"]["common"]; stage_at = tj["dirt"]["stageAtSec"]; CAP = 7 * 86400
    mid = gup["growSec"][0] * 0.5; adult_wait = gup["growSec"][2] * tj["adultHungerMultOfL3Grow"]
    H_MS = 3600 * 1000
    def stage_of(t): return sum(1 for x in stage_at if t >= x)
    def dismiss(pg):
        if pg.locator("#away").is_visible(): pg.click("#away-ok")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for (VW, VH) in ((844, 390), (1180, 820)):
            VIEW[0] = f"real-clock {VW}x{VH}"
            ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=1)
            ctx.add_init_script(CLOCK_INIT)
            errs = []
            def open_page(q="?speed=1", jump_ms=0):
                pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
                if jump_ms:  # move the wall clock while no game page is open (a closed tab / killed home-screen app)
                    pg.goto(BASE + "manifest.webmanifest"); pg.evaluate(f"__clk.add({jump_ms})")
                pg.goto(BASE + q); pg.wait_for_function("window.AQ && window.AQ.game"); pg.wait_for_timeout(300)
                return pg
            page = open_page()
            ev = lambda body, arg=None: page.evaluate("(arg) => { " + JS + body + " }", arg)
            SNAP = """(() => { const G = AQ.game, s = G.state; return { g: s.gameTime, w: s.lastSeen, now: Date.now(), dirt: s.dirt.t, stage: G.dirtStage(), gold: s.gold,
                fish: s.fish.map((f) => ({ id: f.id, state: f.state, level: f.level, progress: f.progress, deathLeft: f.deathLeft, endMeal: !!f.endMeal, sinceFed: f.sinceFed })),
                away: !document.getElementById('away').hidden, awayList: document.getElementById('away').hidden ? '' : document.getElementById('away-list').innerText.trim(),
                awayTime: document.getElementById('away').hidden ? '' : document.getElementById('away-time').innerText.trim(),
                saved: (JSON.parse(localStorage.getItem(G.CFG.VISUAL.saveKey) || '{}').lastSeen) || 0 }; })()"""
            snap = lambda pg=None: (pg or page).evaluate(SNAP)
            # three guppies at speed x1 on a clean tank: A just bought (mid meal at 50% = 90 s), C 100 s into L1 with the mid meal
            # eaten (end meal at 100% = 180 s, then it waits hungry at L1), B adult just fed (adult wait 48 min)
            SETUP = """fresh(); G.state.speed = 1; G.state.gold = 1000; document.getElementById('away').hidden = true;
              const a = G.buyFish('guppy'), c = G.buyFish('guppy'), b = G.buyFish('guppy');
              c.progress = 100; c.hungerDone = true; b.level = 4; b.state = 'ADULT'; b.progress = 0; b.sinceFed = 0; b.hungerDone = false;
              return { a: a.id, b: b.id, c: c.id };"""
            def expect(s0, s1, ids, label):
                """the analytic result of the meal rules after d = game seconds replayed from the SETUP state"""
                d = s1["g"] - s0["g"]; f = {x["id"]: x for x in s1["fish"]}; f0 = {x["id"]: x for x in s0["fish"]}; out = []
                A, B, C = f.get(ids["a"]), f.get(ids["b"]), f.get(ids["c"])
                a0, b0, c0 = f0[ids["a"]], f0[ids["b"]], f0[ids["c"]]   # the fish at the start of the gap (a few frames after SETUP)
                def hungry_or_dead(x, at, death, lvl, end):
                    if d >= at + death: return x and x["state"] == "DEAD" and x["level"] == lvl
                    return x and x["state"] == "HUNGRY" and x["level"] == lvl and x["endMeal"] == end and abs(x["deathLeft"] - (death - (d - at))) < 0.01
                out.append(hungry_or_dead(A, mid - a0["progress"], dsec[0], 1, False))                                   # growth stops at 50% while hungry
                out.append(hungry_or_dead(C, gup["growSec"][0] - c0["progress"], dsec[0], 1, True) and (C["state"] == "DEAD" or abs(C["progress"] - gup["growSec"][0]) < 1e-6))  # waits hungry at 100% of L1
                bw = adult_wait - b0["sinceFed"]
                out.append(B and ((B["state"] == "DEAD") if d >= bw + dsec[3] else (B["state"] == "ADULT_HUNGRY" and abs(B["deathLeft"] - (dsec[3] - (d - bw))) < 0.01)))
                out.append(abs(s1["dirt"] - s0["dirt"] - d) < 0.01 and s1["stage"] == stage_of(s1["dirt"]) == stage_of(d))                     # dirt since the clean, same clock
                return all(out), d

            # ---- (a) clock jump while the page stays open (device slept; performance.now / rAF frozen, no visibility events)
            for hours in (2, 13):
                ids = ev(SETUP); page.wait_for_timeout(250)
                ev("G.save(); return 0;")
                saved_raw = page.evaluate("localStorage.getItem(AQ.game.CFG.VISUAL.saveKey)")
                s0 = page.evaluate("(raw) => { const d = JSON.parse(raw); return { g: d.gameTime, w: d.lastSeen, dirt: d.dirt.t, fish: d.fish }; }", saved_raw)
                page.evaluate(f"__clk.freeze(); __clk.add({hours} * {H_MS});"); page.wait_for_timeout(150)
                frozen_g = page.evaluate("AQ.game.state.gameTime")
                page.evaluate("__clk.thaw()"); page.wait_for_timeout(400)
                s1 = snap(); ok, d = expect(s0, s1, ids, "session")
                inv = abs((s1["g"] - s0["g"]) - (s1["w"] - s0["w"]) / 1000)
                check(f"(a) clock jump +{hours}h with the page open and performance.now/rAF frozen: the frame loop catches up by the wall clock (game +{d:.0f}s, frozen meanwhile) - growth stops at 50% while hungry, the L1 fish at 100% waits hungry at L1, adult hunger, death timers, dirt stage {s1['stage']}",
                      ok and hours * 3600 <= d < hours * 3600 + 5 and inv < 0.01 and abs(frozen_g - s0["g"]) < 1, json.dumps({"d": d, "inv": inv, "frozen": frozen_g - s0["g"], "fish": s1["fish"], "dirt": s1["dirt"], "stage": s1["stage"]}))
                exp_lines = (["Guppy, Guppy, Guppy are hungry"] if hours == 2 else ["Guppy died", "Guppy died", "Guppy is hungry"]) + [f"Tank is at dirt stage {stage_of(hours * 3600)}"]
                check(f"(a) +{hours}h in session: the away window opens with the load-path summary {exp_lines}",
                      s1["away"] and s1["awayList"].split("\n") == exp_lines and s1["awayTime"].startswith(f"({hours}h 00m"), json.dumps([s1["awayList"], s1["awayTime"]]))
                # the load path from the same save (reload at the same wall clock): identical result
                page.evaluate("(raw) => { AQ.game.save = () => {}; localStorage.setItem(AQ.game.CFG.VISUAL.saveKey, raw); }", saved_raw)
                page.close(); page = open_page()
                s2 = snap(); ok2, d2 = expect(s0, s2, ids, "load")
                same = [(x["state"], x["level"], x["endMeal"], round(x["progress"], 6), None if x["deathLeft"] is None else round(x["deathLeft"] + (s2["g"] - s0["g"]), 2)) for x in s2["fish"]] == \
                       [(x["state"], x["level"], x["endMeal"], round(x["progress"], 6), None if x["deathLeft"] is None else round(x["deathLeft"] + (s1["g"] - s0["g"]), 2)) for x in s1["fish"]]
                check(f"(a) +{hours}h: the reload (load-path resume from lastSeen) gives the same fish / dirt result and the same away window as the in-session catch-up",
                      ok2 and same and abs(d2 - d) < 5 and s2["stage"] == s1["stage"] and s2["awayList"] == s1["awayList"], json.dumps({"d": d, "d2": d2, "s1": s1["fish"], "s2": s2["fish"], "away2": s2["awayList"]}))
                ev = lambda body, arg=None: page.evaluate("(arg) => { " + JS + body + " }", arg)
                dismiss(page)

            # ---- (b) app switch / lock: hidden + visibilitychange (+ pageshow / focus) with performance.now / rAF frozen
            for order in ("events-first", "frame-first"):
                ids = ev(SETUP); page.wait_for_timeout(250)
                s0 = snap()
                page.evaluate("__clk.hide(); __clk.freeze();")
                sh = snap()
                page.evaluate(f"__clk.add(2 * {H_MS});"); page.wait_for_timeout(100)
                if order == "events-first":
                    page.evaluate("__clk.show()"); sv = snap()   # caught up at once by the visibilitychange handler, before any frame
                    page.evaluate("__clk.pageshow(true); __clk.focus();"); se = snap()
                    page.evaluate("__clk.thaw()")
                else:
                    page.evaluate("__clk.thaw()"); page.wait_for_timeout(200)
                    sv = snap(); page.evaluate("__clk.show(); __clk.pageshow(true); __clk.focus();"); se = snap()
                page.wait_for_timeout(500); s1 = snap()
                ok, d = expect(s0, s1, ids, "switch")
                inv = abs((s1["g"] - s0["g"]) - (s1["w"] - s0["w"]) / 1000)
                check(f"(b) {order}: on hide the game saves lastSeen (= now, the wall clock accounted up to)",
                      sh["saved"] == sh["w"] and abs(sh["now"] - sh["w"]) < 100 and abs(sh["g"] - s0["g"]) < 1, json.dumps({k: sh[k] for k in ("saved", "w", "now")}))
                check(f"(b) {order}: 2h switched away with rAF/performance.now frozen is caught up EXACTLY once (game time == wall time accounted; pageshow(persisted) + focus add nothing)",
                      ok and 7200 <= d < 7205 and inv < 0.01 and sv["g"] - s0["g"] >= 7200 and se["g"] - sv["g"] < 0.2 and s1["g"] - se["g"] < 2,
                      json.dumps({"d": d, "inv": inv, "atShow": sv["g"] - s0["g"], "extraEvents": se["g"] - sv["g"], "after": s1["g"] - se["g"]}))
                check(f"(b) {order}: the away window opens after the 2h switch (hungry fish, dirt stage 1)", s1["away"] and s1["awayList"].split("\n") == ["Guppy, Guppy, Guppy are hungry", "Tank is at dirt stage 1"], s1["awayList"])
                dismiss(page)
            for secs in (3, 40):  # a quick switch on a DIRTY tank: time is caught up but no window (nothing new happened)
                ev("fresh(); G.state.speed = 1; G.state.dirt.t = T.dirt.stageAtSec[0] + 60; G.tick(0); document.getElementById('away').hidden = true; return 0;"); page.wait_for_timeout(200)
                s0 = snap(); page.evaluate(f"__clk.hide(); __clk.freeze(); __clk.add({secs * 1000}); __clk.show(); __clk.pageshow(false); __clk.thaw();"); page.wait_for_timeout(400); s1 = snap()
                check(f"(b) a quick {secs}s app switch (dirty tank) catches up {secs}s of game time and shows NO away window",
                      secs <= s1["g"] - s0["g"] < secs + 2 and abs((s1["g"] - s0["g"]) - (s1["w"] - s0["w"]) / 1000) < 0.01 and not s1["away"] and s1["stage"] == 1, json.dumps({"d": s1["g"] - s0["g"], "away": s1["away"]}))

            # ---- (c) no fish: buy one, sell every fish -> the game clock and the dirt clock keep running
            r = ev("""fresh(); G.state.speed = 1; document.getElementById('away').hidden = true; const f = G.buyFish('guppy'); const sold = G.sell(f.id);
              return { sold, fish: G.state.fish.length };""")
            page.wait_for_timeout(200); s0 = snap(); page.wait_for_timeout(1000); s1 = snap()
            check("(c) after buying a fish and selling every fish the game clock and the dirt clock keep running in real time",
                  r["fish"] == 0 and r["sold"] and 0.8 < s1["g"] - s0["g"] < 1.6 and 0.8 < s1["dirt"] - s0["dirt"] < 1.6, json.dumps({"r": r, "g": s1["g"] - s0["g"], "dirt": s1["dirt"] - s0["dirt"]}))
            for hours, how in ((2, "switch"), (13, "sleep")):
                s0 = snap()
                if how == "switch": page.evaluate(f"__clk.hide(); __clk.freeze(); __clk.add({hours} * {H_MS}); __clk.show(); __clk.thaw();")
                else: page.evaluate(f"__clk.freeze(); __clk.add({hours - 2} * {H_MS}); __clk.thaw();")
                page.wait_for_timeout(400); s1 = snap(); d = s1["g"] - s0["g"]
                check(f"(c) empty tank, clock +{hours}h ({how}): game time and dirt advance together (dirt stage {stage_of(hours * 3600)} at {hours}h since the clean), away window names only the dirt",
                      s1["fish"] == [] and abs((s1["dirt"] - s0["dirt"]) - d) < 0.01 and s1["stage"] == stage_of(s1["dirt"]) == stage_of(hours * 3600)
                      and s1["away"] and s1["awayList"] == f"Tank is at dirt stage {stage_of(hours * 3600)}", json.dumps({"d": d, "dirt": s1["dirt"], "stage": s1["stage"], "away": s1["awayList"]}))
                dismiss(page)

            # ---- (d) closed tab / killed app + reload with the clock moved on: resume() from the saved lastSeen
            ids = ev(SETUP); page.wait_for_timeout(2600)   # no hide event: the periodic save alone must carry lastSeen
            s0 = snap()
            check("(d) the periodic save keeps lastSeen current (saved lastSeen = the wall clock accounted up to, < saveEveryMs + a frame old)",
                  0 <= s0["now"] - s0["saved"] <= 2700 and abs(s0["saved"] - s0["w"]) <= 2700, json.dumps({k: s0[k] for k in ("now", "saved", "w")}))
            saved = page.evaluate("JSON.parse(localStorage.getItem(AQ.game.CFG.VISUAL.saveKey))")
            base = {"g": saved["gameTime"], "w": saved["lastSeen"], "dirt": saved["dirt"]["t"], "fish": saved["fish"]}
            page.close(run_before_unload=False)
            page = open_page(jump_ms=13 * H_MS); s1 = snap()
            ok, d = expect(base, s1, ids, "closed")
            check("(d) tab closed, clock +13h, reopened: the load path replays the 13h from the saved lastSeen (two guppies died, adult hungry, dirt stage 4) and shows the away window",
                  ok and 13 * 3600 <= d < 13 * 3600 + 8 and s1["away"] and s1["awayList"].split("\n") == ["Guppy died", "Guppy died", "Guppy is hungry", "Tank is at dirt stage 4"],
                  json.dumps({"d": d, "fish": s1["fish"], "away": s1["awayList"]}))
            dismiss(page)
            ev = lambda body, arg=None: page.evaluate("(arg) => { " + JS + body + " }", arg)

            # ---- (e) clock set backwards counts as 0 (in session and across a reload); time then runs on from the new clock
            ev("fresh(); G.state.speed = 1; document.getElementById('away').hidden = true; G.buyFish('guppy'); return 0;"); page.wait_for_timeout(200)
            s0 = snap(); page.evaluate(f"__clk.add(-5 * {H_MS});"); page.wait_for_timeout(300); s1 = snap(); page.wait_for_timeout(1000); s2 = snap()
            check("(e) clock set back 5h with the page open: counts as 0 (no jump, no negative time), then the clock runs on normally from the new wall time",
                  0 <= s1["g"] - s0["g"] < 1 and abs(s1["now"] - s1["w"]) < 200 and 0.8 < s2["g"] - s1["g"] < 1.6 and not s2["away"], json.dumps({"d1": s1["g"] - s0["g"], "d2": s2["g"] - s1["g"]}))
            ev("G.save(); return 0;"); page.close(run_before_unload=False)
            page = open_page(jump_ms=-5 * H_MS); s3 = snap()
            check("(e) tab closed, clock set back 5h, reopened: 0 offline time, no away window",
                  0 <= s3["g"] - s2["g"] < 4 and not s3["away"], json.dumps({"d": s3["g"] - s2["g"], "away": s3["awayList"]}))
            ev = lambda body, arg=None: page.evaluate("(arg) => { " + JS + body + " }", arg)

            # ---- (f) the 7-day cap: one catch-up replays at most 7 days (in session and on load)
            ev("fresh(); G.state.speed = 1; document.getElementById('away').hidden = true; return 0;"); page.wait_for_timeout(200)
            page.evaluate("__clk.hide(); __clk.freeze();"); s0 = snap(); page.evaluate(f"__clk.add(30 * 24 * {H_MS}); __clk.show();"); s1 = snap(); page.evaluate("__clk.thaw()")
            check("(f) 30 days away in session: exactly 7 days of game time replayed (cap), lastSeen moved to now (no second catch-up later)",
                  abs((s1["g"] - s0["g"]) - CAP) < 0.01 and abs(s1["now"] - s1["w"]) < 200 and s1["stage"] == 5, json.dumps({"d": s1["g"] - s0["g"], "stage": s1["stage"]}))
            page.wait_for_timeout(400); s2 = snap()
            check("(f) after the capped catch-up the clock just runs on (no extra replay)", 0 <= s2["g"] - s1["g"] < 2, f"{s2['g'] - s1['g']:.2f}")
            dismiss(page)
            g_saved = ev("G.save(); return JSON.parse(localStorage.getItem(G.CFG.VISUAL.saveKey)).gameTime;"); page.close(run_before_unload=False)
            page = open_page(jump_ms=30 * 24 * H_MS); s3 = snap()
            check("(f) tab closed 30 days: the load path replays exactly 7 days (away window: 168h 00m)", 0 <= (s3["g"] - g_saved) - CAP < 1.5 and s3["away"] and s3["awayTime"].startswith("(168h 00m"),
                  json.dumps({"d": s3["g"] - g_saved, "time": s3["awayTime"]}))
            check("real clock: no page errors", not errs, "; ".join(errs[:3]))
            page.evaluate("AQ.game.reset(); AQ.game.save();")
            ctx.close()
        browser.close()

if __name__ == "__main__":
    # AQ_ONLY=edit_spacing,rarity_tags ... runs just those sections (names below); default = everything
    only = {x.strip() for x in os.environ.get("AQ_ONLY", "").split(",") if x.strip()}
    run = lambda name: not only or name in only
    views = [tuple(int(v) for v in x.split("x")) for x in os.environ.get("AQ_VIEWS", "844x390,1180x820").split(",") if x.strip()]
    if run("main"):
        for vw, vh in views:
            print(f"\n======== {vw}x{vh}", flush=True)
            main(vw, vh)
    if run("portrait") and os.environ.get("AQ_PORTRAIT", "1") == "1":
        print("\n======== portrait", flush=True)
        portrait()
    if run("fluid") and os.environ.get("AQ_FLUID", "1") == "1":
        print("\n======== fluid layout", flush=True)
        fluid_layout()
    for name, fn in (("debug_bottom", debug_bottom), ("cache_bust", cache_bust), ("home_screen_icons", home_screen_icons), ("edit_spacing", edit_spacing), ("rarity_tags", rarity_tags), ("tuning_68", tuning_68), ("decor_v1", decor_v1), ("standalone_ios", standalone_ios), ("tank_corners", tank_corners), ("real_clock", real_clock)):
        if run(name):
            print(f"\n======== {name}", flush=True)
            fn()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)
