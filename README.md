# Aquarium: one-tank mobile web prototype (Designer v4 numbers, Art Director landscape layout v4)

## HOW TO RUN

Dev server (no-cache, the one Maksims watches through the tunnel):

```bash
nohup python3 /workspace/tools/nocache_server.py 8767 /workspace/aquarium > /tmp/aq-dev.log 2>&1 &
```

Open **http://127.0.0.1:8767/**. (Port 8766 is the separate *stable* server for the reviewed build in the `/workspace/aquarium-stable` worktree; don't point it at this tree.) Any static server works too, for example `python3 -m http.server 8767 --bind 127.0.0.1`.

The game is **landscape only**. Held upright it shows only a rotate screen. The page always opens at **×1** (real time). The debug row at the bottom has **×1 / ×5 / ×10 / ×15 / ×20**, **+100g** (cheat), **+50 XP** (through the real XP path, no gold) and **Reset save**, with the game clock right-aligned. Hidden for testing: **`?speed=N`** sets any speed (`?speed=3600` = 1 game hour per real second), and `?debug=0` hides the debug row.

Plain HTML/CSS/JS, with no build step, framework or npm. **Cache busting**: every script and CSS tag in `index.html` carries `?v=<build>`, so phones always load fresh files after an update. Run `python3 tools/bump_build.py` (the build id defaults to the UTC time) before handing over a build. `verify.py` checks that all tags carry the same id.

Tests (the dev server must be running):
- `AQ_URL=http://127.0.0.1:8767/ /workspace/tools/venv-aq/bin/python tests/verify.py`: end-to-end checks (Playwright + Chromium) at 844x390 (phone sideways) and 1180x820 (tablet sideways), plus the upright rotate screen (390x844, 820x1180), the fluid layout at 844x390 / 1180x820 / 932x430 / 667x375, and cache busting. Screenshots go to `screenshots/v4/`. Options: `AQ_VIEWS=844x390` (views to run), `AQ_PORTRAIT=0`, `AQ_FLUID=0`.
- `tests/art_shots.py`: the older portrait review screenshots (pre-landscape; kept for reference).
- Both reset the save at the end.

## Numbers

Every balance number is in **`config.js`**. `TUNING` there is a verbatim copy of Designer's **v4** `tuning.json`, pinned to `/workspace/studio/briefs/aquarium/design/v4_archive/tuning.json`. Designer has moved the live `tuning.json` to v5.1 (tank levels 6-10 and 5 new fish), which lands in the next step. `python3 tools/sync_tuning.py` copies the v4 archive by default. Pass a path to take another file. `verify.py` fails if `TUNING` and the v4 file differ.
Presentation-only values are in `VISUAL` (tank geometry, glass line side, fish size, dirt look, decorations look, sponge).

| Species | Price | Unlock (tank Lv) | Grow L1→2 / 2→3 / 3→4 | Food per meal L1-L4 | Level-up gold | Sell L1-L4 | Sell XP L1-L4 |
|---|---|---|---|---|---|---|---|
| Guppy | 20 | 1 | 3 / 6 / 12 min | 1 / 1 / 1 / 2 | 1 / 2 / 4 | 0 / 8 / 18 / 40 | 0 / 10 / 25 / 80 |
| Zebra Danio | 50 | 2 | 3.75 / 7.5 / 15 min | 1 / 2 / 2 / 3 | 3 / 5 / 10 | 0 / 20 / 45 / 100 | 0 / 20 / 50 / 160 |
| Neon Tetra | 90 | 3 | 5.25 / 10.5 / 21 min | 2 / 3 / 3 / 4 | 5 / 9 / 18 | 0 / 36 / 81 / 180 | 0 / 30 / 75 / 240 |
| Platy | 150 | 4 | 7.5 / 15 / 30 min | 3 / 5 / 6 / 7 | 8 / 15 / 30 | 0 / 60 / 135 / 300 | 0 / 50 / 125 / 400 |

- **New game / Start new tank**: an empty tank at dirt stage 3, 0 gold, 0 food, 0 diamonds, 1 stone and 3 leaves. The **first clean pays 20 gold + 10 food** (instead of the stage pay).
- **Meals**: two per level (at the start and halfway). A meal needs the species' food for that level. Each food tap gives 1 food to the nearest fish that needs it. A finished meal gives the species' feed XP and **brings the dirt 5 minutes closer**.
- **Death** after getting hungry: 6 / 7 / 9 / 10 h by fish level (a new L1 baby waits and never dies before its first meal).
- **Dirt** is time only: stages at 3 / 6 / 12 / 24 / 48 h, 3 / 4 / 5 / 6 / 7 spots. A full clean pays 2 / 3 / 4 / 5 / 6 gold by the stage when rubbing started, + 5 XP.
- **Tank level**: 60 / 400 / 1,200 / 3,000 XP for levels 2-5. XP comes from fish level-ups, meals, cleans and selling (selling gives the most). Level 5 raises capacity from 6 to 8 fish.
- **Food packs** (Shop → Food): 10 food for 5 gold, 50 food for 25 gold.

## Screen (Art Director LANDSCAPE_LAYOUT_V4.md)

- **Fluid frame**: a tool column on the left (full height), the top bar right of it, the tank under the top bar, and the one-line debug row **anchored to the viewport bottom** (bottom offset `max(4px, safe-area-inset-bottom)`). The tank takes all the remaining width and height on any landscape viewport. `#app` is sized to the visible viewport (`100dvh`, a `100vh` fallback, then `visualViewport` / `innerHeight` on resize, orientationchange and visualViewport resize). Compact (height < 600): 8px padding, 68px column, 36px top bar. At 844x390 the tank is **752x306 at (84,50)**. Large (height >= 600): 12px padding, 96px column, 48px top bar. At 1180x820 the tank is **1048x708 at (120,68)**.
- **Tool column**, top to bottom: **Look** (hand), **Food** (bottle), **Clean** (sponge), **Net**, **Decorate** (paintbrush), **Shop**. Buttons are 68x54 with 36px icons (compact) or 96x88 with 52px icons (large). There are no tool buttons at the bottom.
- **Food bottle**: a count badge (999+ above that, red at 0). The orange fill drains in steps (20+ full, 10-19 three quarters, 5-9 half, 1-4 quarter), and at 0 it's drawn empty.
- **Top bar**: gold, diamonds, "Tank Lv N" with the XP bar and "xp / next", and the dirt window: "Dirt: stage N of 5" (or "Dirt: clean") and **"Stage N in Xh Ym"** ("42m", "<1m", "Max dirt" at stage 5) over a 5-segment bar. The food count is not in the top bar.
- **Rotate screen**: held upright (height > width), only the rotate screen shows: an opaque `#07192a` background, a 120px (large: 160px) phone outline with a curved arrow turning -90°, and "Turn your device sideways". The tank, column, top bar, debug row, open panels, confirmation dialogs and toasts are all hidden (not just covered). The game clock keeps running, but drawing and input pause. Turning back resumes with nothing lost.

## Tank look

- **Square corners** everywhere on the tank (frame, water, sand, canvas: radius 0, no clip). Panels and buttons stay rounded.
- The **top 7%** of the tank (min 16px) is air, darker than the water, and the water surface is a waving line under it.
- The sand top sits at 86%, with back corners inset 3.5% of the width.
- **One glass back line**: from the sand's back corner straight up to the inner top edge of the frame, with a faint side-glass strip between it and the frame on that side only. Nothing is drawn on the other side. The side is one setting: `VISUAL.glassLineSide = 'right'` (set `'left'` to flip it).
- Fish size = `min(W, waterH*0.8) * 0.30 * species * level`, and every fish has a tap target of at least 44x44.
- The grey circle meter above fish is gone. The hunger icon sits 12px above the head.
- **Dirt**: spot radii and the sponge (0.16 of the water height, 40-72px) scale with the water height. Stage 1 = 3 smudges at 0.22 alpha, each with a darker rim and 3-5 speckles, plus a faint tank-wide wash. Stages 2-5 keep the v2 looks. At stage 5 a film covers the tank.

## Play

- **Look**: tap a fish to open its info panel (docked right). It shows growth, hunger, **"Meal N of 2 · needs X food"** with a segment bar, and **"Worth N gold"**. There's no sell button and no tap counts.
- **Food**: tap near a hungry fish. A pinch of flakes falls slowly, and the nearest hungry fish rushes over and eats **all** of them. If the tank is dirty, the tap is blocked. "Clean the tank first" shows at the top middle, the dirt spots pulse more solid and back (1 s), and the dirt window flashes red twice. There's no callout and no arrow. With nobody hungry it says "Nobody's hungry", and with no food it says "Out of food".
- **Clean**: rub the spots with the sponge (mouse or finger).
- **Net**: tap a fish to sell it (L2+) or release it (L1), always with a confirmation dialog showing its portrait. Dead fish are removed with the net too.
- **Shop**: a centred panel with **Fish / Food / Decorations** tabs and a permanent **Close** pill at the bottom middle. It doesn't show the tank level or XP. Locked species show "🔒 Tank level N".
- **Decorations**: the shop sells a **Leaf** and a **Stone** for free, up to 12 per tank. Buying one places it at the floor centre and opens edit mode with it selected. In **edit mode** (paintbrush), fish turn see-through and can't be tapped, and every decoration gets a dashed outline. Tapping one opens a side menu docked on the side away from it, which never covers it (with a 2.0x leaf in the middle, the menu shrinks slightly to fit). The menu has 4 round **move** arrows (8px per tap; hold to repeat every 80ms after 300ms), 4 round **size** buttons (taller, shorter, wider, narrower; 0.5x-2.0x in 0.1 steps, with separate height and width and the capped button dimmed), a **colour** slider (0-100, light to dark green for leaves, light to dark grey for stones) and **Sell · refund N gold**, with a confirmation. The base can move from the sand's back edge down to its **front edge** (the bottom of the tank) at every size. Leaving edit mode: **Done** or any other tool. Positions are saved as fractions of the tank (x of the width, y of the sand band), so they stay put across reloads and screen sizes.
- **While you were away**: lists only real events (level-ups, deaths, hungry fish, tank levels, gold) and the dirt stage when the tank is dirty. It never says the tank is clean, and it doesn't appear when there's nothing to report.

## Save

Progress is saved to `localStorage` (`aquarium.save.v4`) every 2 s and when the page hides, with the wall-clock time for offline catch-up (capped at 7 days). Older saves are ignored (fresh start).

## Files

- `index.html`, `style.css`: landscape frame (tool column / top bar / tank / debug row), rotate screen, panels, shop, edit menu
- `config.js`: `TUNING` (v4 tuning.json verbatim), presentation values in `VISUAL`, `OFFLINE_CAP_SEC`
- `js/game.js`: game state, simulation, meals, rubbing, selling, decorations, tank XP, offline catch-up, save/load, balance self-checks
- `js/fishart.js`: procedural canvas fish art for 4 species (L1-L4 growth look, dead-fish look)
- `js/main.js`: rendering, swimming AI, input, tools, panels, shop, edit mode, rotate screen, fluid layout
- `tests/verify.py`: headless end-to-end test; `tests/art_shots.py`: older review screenshots
- `tools/sync_tuning.py`: copies the (v4) tuning.json into `config.js`; `tools/bump_build.py`: stamps `?v=<build>` on the script and CSS tags
- `screenshots/v4/`: landscape screenshots from the test run
