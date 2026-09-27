# Aquarium — one-tank web prototype (Designer v3 economy on the v2 "slow game")

## HOW TO RUN

```bash
cd /workspace/aquarium && python3 -m http.server 8766 --bind 127.0.0.1
```

Open **http://127.0.0.1:8766/**. The page always opens at **×1** (real time). The debug bar has **×1 / ×5 / ×10 / ×15 / ×20**, **+100g** (a cheat for testing), **+50 XP** and **Reset save**. **+50 XP** (NUMBERS.md §9 edge case 13) adds 50 tank XP through the same XP path real play uses, so tank level-ups, unlock toasts and saving work exactly as in play. It gives no gold. Two taps reach tank level 2, 8 reach level 3 and 24 reach level 4.
Hidden for testing: **`?speed=N`** sets any speed (for example `?speed=3600` = 1 game hour per real second). `?debug=0` hides the debug bar.

Plain HTML/CSS/JS. There's no build step, no framework and no npm.

Tests (server must be running):
- `/workspace/tools/venv-aq/bin/python tests/verify.py`: 75 end-to-end checks (Playwright + Chromium). Hours-long timers are checked by stepping the game inside the page; UI checks use real mouse and touch input.
- `/workspace/tools/venv-aq/bin/python tests/art_shots.py`: review screenshots in `screenshots/`.
- Both reset the save at the end.

## Numbers

Every balance number is in **`config.js`**. `TUNING` there is a **verbatim copy of Designer's `/workspace/studio/briefs/aquarium/design/tuning.json`** (version 3). The rules follow `NUMBERS.md` (v3) in the same folder. To retune, run `python3 tools/sync_tuning.py`. `verify.py` fails if the two differ.
Outside `TUNING`: `OFFLINE_CAP_SEC` (7 days), the drafted rare/epic multipliers (not used in v1), and presentation-only values in `VISUAL`: fish size and growth look, dirt look per stage and the stage 5 film, sponge, and save key `aquarium.save.v2`.

## Economy (v3, approved by Maksims 2026-09-27; NUMBERS.md §1b, §4, §5)

| Species | Price | Level-up gold L2 / L3 / L4 | Tank XP L2 / L3 / L4 | Sell L1 / L2 / L3 / L4 |
|---|---|---|---|---|
| Guppy | 20 | 1 / 2 / 4 | 10 / 20 / 40 | 0 / 8 / 18 / 40 |
| Zebra Danio | 50 | 3 / 5 / 10 | 20 / 40 / 80 | 0 / 20 / 45 / 100 |
| Neon Tetra | 90 | 5 / 9 / 18 | 30 / 60 / 120 | 0 / 36 / 81 / 180 |
| Platy | 150 | 8 / 15 / 30 | 50 / 100 / 200 | 0 / 60 / 135 / 300 |

- **Feeding pays 0** (`feedGoldPerFish` 0), so no gold float is shown on a feed. Food costs 10 gold per 10.
- **Clean pay by stage: 2 / 3 / 4 / 5 / 6 gold** (+5 XP). The pay uses the stage the tank was at when rubbing **started** (the first sponge contact since the last full clean), and it's paid when the last spot clears. If the tank reaches stage 4 while you're rubbing a stage 3 tank, you still get 4. Partial rubbing pays nothing. Gold per day if you always clean at stage n: 16 / 12 / 8 / 5 / 3, so cleaning often wins.
- **Tank XP from level-ups comes from each species' `levelUpXp`** (`tank.xp.fishLevelUp = "species.levelUpXp"`), not from the level-up gold. A level-up shows "+2 gold" and "+20 XP" floats. The v2 `XP_SOURCE` switch is retired, because XP sources are settled (NUMBERS.md §11).
- Profit per fish, with food at 1 gold: selling at L1–L3 never makes a profit, and selling at L4 always does. Selling at L3 gives Guppy −3, Danio −1, Neon −3, Platy 0. Selling at L4 gives +20, +61, +108, +189. `verify.py` checks this, plus the stage 1 cleaning rule.
- First Guppy (tested): buying it leaves 0 gold and 10 food. Reaching adult takes 7 food. With Designer's day-1 check-ins (08/12/16/19/23), the adult has 15 gold and 3 food at 23:00, and a 10-gold food pack covers its 4-food adult feed. Selling it gives 55 gold.

## Rules as implemented (NUMBERS.md v3; everything but gold unchanged from v2)

- **Dirt is time only.** Stages come at 3 / 6 / 12 / 24 / 48 h after a new tank or the last full clean, with 2–6 spots. The clock runs **whatever is in the tank: living fish, dead fish or none, so an empty tank gets dirty too.** Stage 5 adds a green film over the whole tank. The bar shows 5 segments and never a clock.
- **Cleaning:** rub the spots with the Sponge (mouse or finger). Each spot needs about 150 px of rubbing at stages 1–2 and about 220 px at stages 3–5. A full clean pays **2 / 3 / 4 / 5 / 6 gold by stage** (the stage when rubbing started) **+ 5 XP**. Partial rubbing pays nothing. Any dirt blocks feeding, and the only message is **"Clean the tank first"** next to the dirt bar (no toast in the middle of the tank).
- **Feeding:** each Food tap gives **1 food** to the nearest fish that still needs food. It shows a shower of small flakes (the v1 look, 16 flakes) falling through the water from the tap point and drifting toward that fish, which eats them. A blocked tap (dirty, nobody hungry, out of food) shows no flakes. A fed meter above the fish fills up (portion = `foodBase × level`, so Guppy takes 1–4 taps and Platy 2–8). Feeding pays nothing (v3). A tap with nobody to feed says "Nobody's hungry". With no food left it says "Out of food".
- **Growth / hunger / death:** growth is 15× slower than v1 (Guppy is adult after 7 h with prompt feeding, Platy after 17.5 h). A fish gets hungry at 50% of each level and growth pauses. It **dies 16 h after getting hungry** if it isn't fed. An adult gets hungry `adultHungerSec` after reaching L4 and after each full feed. A bought fish waits (it never gets hungry) until its first feed.
- **Dead fish** stay in the tank, belly-up and pale, and float up to just under the waterline (top 6–10%). They take a tank slot, aren't fed and don't block feeding. Tap one to open its panel: **"Dead"** and **"Remove (0 gold)"** (no confirm, can't be sold). The starter grant and "Start new tank" count living fish only.
- **Tank level:** 60 / 400 / 1,200 / 3,000 XP for levels 2–5. XP: a fish level-up gives its species' `levelUpXp`, each clean gives 5 XP, and selling and feeding give 0. Locked species show greyed out in the shop with **"🔒 Tank level N"**. Level 5 shows "Decorations coming soon".
- **Offline progress:** on load, the time since the last save is replayed in order, capped at 7 days. A clock set backwards counts as 0. A **"While you were away"** box lists level-ups, deaths, hungry fish, tank levels, the dirt stage and gold earned. A background tab that is away for more than 5 s is handled the same way.
- Sell: L1 = **Release (0 gold)** with a confirm dialog. L2+ = **Sell for X gold**. Tank capacity is 6, dead fish included.
- **Starter grant:** a one-time top-up to 20 gold when there are no living fish and gold is below 20. After it's used, a second wipe-out shows "Your tank is empty" and **Start new tank**.
- Diamonds: a disabled "Diamonds: coming later" stub in the shop only.

## Look (Art Director `DIRT_AND_FISH_GROWTH.md`, v2 dirt section + dead-fish pose)

- Dirt spots per stage: 1 faint smudge, 2 algae dots, 3 drip streak, 4 hair-algae patch (brown crust tint on half the spots), 5 big crust. Each stage is bigger and darker (alpha 0.14 / 0.22 / 0.32 / 0.40 / 0.46).
- Tank layer: a light green wash at stages 2–4. At stage 5, a green film (0.28 in the centre up to 0.42 at the edges) with slowly drifting cloudy blotches and a scum band along the waterline. The film is drawn in front of the fish and behind the spots. It fades as the spots are rubbed away and is gone when the last spot clears. In the middle 60% of the tank, film plus one spot is capped at 0.6 so a fish there stays readable.
- Fish L1–L4: fry with clear fins, then fin colour, a longer tail and markings, then full adult colours. Neon L2 (AD ruling): a blue line in the adult stripe colours at 85%, at least 2 px thick at tank size and at least 12% of body depth, with no glow.
- Dead fish: belly-up, desaturated, fins at 60%, cloudy eye. It drifts slowly at the top, bobbing and tilting a little.

## Save

Progress is saved to `localStorage` (`aquarium.save.v2`) every 2 s and when the page hides, with the wall-clock time for offline catch-up. v1 saves are ignored (fresh start).

## Files

- `index.html`, `style.css`: layout (HUD / tank / tools / debug bar), portrait-first
- `config.js`: all balance numbers (`TUNING` = tuning.json verbatim) + presentation values (`VISUAL`) + `OFFLINE_CAP_SEC`
- `js/game.js`: game state, simulation, feeding, rubbing, selling, dead fish, tank XP, offline catch-up, save/load, balance self-checks
- `js/fishart.js`: procedural canvas fish art for 4 species (L1-L4 growth look, dead-fish look)
- `js/main.js`: rendering, swimming AI, pointer input, panels, shop, debug bar
- `tests/verify.py`: headless end-to-end test
- `tests/art_shots.py`: review screenshots (dirt stages 1-5 + mid-rub, dead fish, locked shop, fed meter, dirty feed, away summary, fish L1-L4 sheets)
- `tools/sync_tuning.py`: copies Designer's tuning.json into `config.js` `TUNING` verbatim
- `screenshots/`: output from the test run
