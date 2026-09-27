# Aquarium — one-tank web prototype (Designer v2, "slow game")

## HOW TO RUN

```bash
cd /workspace/aquarium && python3 -m http.server 8766 --bind 127.0.0.1
```

Open **http://127.0.0.1:8766/**. The page always opens at **×1** (real time). The debug bar has **×1 / ×5 / ×10 / ×15 / ×20**, **+100g** (a cheat for testing) and **Reset save**.
Hidden for testing: **`?speed=N`** sets any speed (for example `?speed=3600` = 1 game hour per real second). `?debug=0` hides the debug bar.

Plain HTML/CSS/JS. There's no build step, no framework and no npm.

Tests (server must be running):
- `/workspace/tools/venv-aq/bin/python tests/verify.py`: 61 end-to-end checks (Playwright + Chromium). Hours-long timers are checked by stepping the game inside the page; UI checks use real mouse and touch input.
- `/workspace/tools/venv-aq/bin/python tests/art_shots.py`: review screenshots in `screenshots/`.
- Both reset the save at the end.

## Numbers

Every balance number is in **`config.js`**. `TUNING` there is a **verbatim copy of Designer's `/workspace/studio/briefs/aquarium/design/tuning.json`** (v2). The rules follow `NUMBERS.md` in the same folder. To retune, run `python3 tools/sync_tuning.py`. `verify.py` fails if the two differ.
Outside `TUNING`: `XP_SOURCE` (see below), `OFFLINE_CAP_SEC` (7 days), the drafted rare/epic multipliers (not used in v1), and presentation-only values in `VISUAL`: fish size and growth look, dirt look per stage and the stage 5 film, sponge, and save key `aquarium.save.v2`.

## Rules as implemented (NUMBERS.md v2)

- **Dirt is time only.** Stages come at 3 / 6 / 12 / 24 / 48 h after a new tank or the last full clean, with 2–6 spots. The clock runs **whatever is in the tank: living fish, dead fish or none, so an empty tank gets dirty too.** Stage 5 adds a green film over the whole tank. The bar shows 5 segments and never a clock.
- **Cleaning:** rub the spots with the Sponge (mouse or finger). Each spot needs about 150 px of rubbing at stages 1–2 and about 220 px at stages 3–5. **Every full clean pays 10 gold + 5 XP** at any stage. Partial rubbing pays nothing. Any dirt blocks feeding, and the only message is **"Clean the tank first"** next to the dirt bar (no toast in the middle of the tank).
- **Feeding:** each Food tap gives **1 food** to the nearest fish that still needs food. A fed meter above the fish fills up (portion = `foodBase × level`, so Guppy takes 1–4 taps and Platy 2–8). **+1 gold** when the fish is fully fed. A tap with nobody to feed says "Nobody's hungry". With no food left it says "Out of food".
- **Growth / hunger / death:** growth is 15× slower than v1 (Guppy is adult after 7 h with prompt feeding, Platy after 17.5 h). A fish gets hungry at 50% of each level and growth pauses. It **dies 16 h after getting hungry** if it isn't fed. An adult gets hungry `adultHungerSec` after reaching L4 and after each full feed. A bought fish waits (it never gets hungry) until its first feed.
- **Dead fish** stay in the tank, belly-up and pale, and float up to just under the waterline (top 6–10%). They take a tank slot, aren't fed and don't block feeding. Tap one to open its panel: **"Dead"** and **"Remove (0 gold)"** (no confirm, can't be sold). The starter grant and "Start new tank" count living fish only.
- **Tank level:** 60 / 400 / 1,200 / 3,000 XP for levels 2–5. The default XP sources: a fish level-up gives XP equal to its level-up gold, each clean gives 5 XP, and selling and feeding give 0. Locked species show greyed out in the shop with **"🔒 Tank level N"**. Level 5 shows "Decorations coming soon". Maksims' open question on XP sources is one switch in `config.js`: `XP_SOURCE = 'designer' | 'levelUpsOnly' | 'levelUpsAndSell'`.
- **Offline progress:** on load, the time since the last save is replayed in order, capped at 7 days. A clock set backwards counts as 0. A **"While you were away"** box lists level-ups, deaths, hungry fish, tank levels, the dirt stage and gold earned. A background tab that is away for more than 5 s is handled the same way.
- Sell: L1 = **Release (0 gold)** with a confirm dialog. L2+ = **Sell for X gold**. Tank capacity is 6, dead fish included.
- **Starter grant:** a one-time top-up to 20 gold when there are no living fish and gold is below 20. After it's used, a second wipe-out shows "Your tank is empty" and **Start new tank**.
- Diamonds: a disabled "Diamonds: coming later" stub in the shop only.

## Look (Art Director `DIRT_AND_FISH_GROWTH.md`, v2 dirt section + dead-fish pose)

- Dirt spots per stage: 1 faint smudge, 2 algae dots, 3 drip streak, 4 hair-algae patch (brown crust tint on half the spots), 5 big crust. Each stage is bigger and darker (alpha 0.14 / 0.22 / 0.32 / 0.40 / 0.46).
- Tank layer: a light green wash at stages 2–4. At stage 5, a green film (0.28 in the centre up to 0.42 at the edges) with slowly drifting cloudy blotches and a scum band along the waterline. The film is drawn in front of the fish and behind the spots. It fades as the spots are rubbed away and is gone when the last spot clears. In the middle 60% of the tank, film plus one spot is capped at 0.6 so a fish there stays readable.
- Fish L1–L4: fry with clear fins, then fin colour, a longer tail and markings, then full adult colours.
- Dead fish: belly-up, desaturated, fins at 60%, cloudy eye. It drifts slowly at the top, bobbing and tilting a little.

## Save

Progress is saved to `localStorage` (`aquarium.save.v2`) every 2 s and when the page hides, with the wall-clock time for offline catch-up. v1 saves are ignored (fresh start).

## Files

- `index.html`, `style.css`: layout (HUD / tank / tools / debug bar), portrait-first
- `config.js`: all balance numbers (`TUNING` = tuning.json verbatim) + presentation values (`VISUAL`) + `XP_SOURCE`
- `js/game.js`: game state, simulation, feeding, rubbing, selling, dead fish, tank XP, offline catch-up, save/load, balance self-checks
- `js/fishart.js`: procedural canvas fish art for 4 species (L1-L4 growth look, dead-fish look)
- `js/main.js`: rendering, swimming AI, pointer input, panels, shop, debug bar
- `tests/verify.py`: headless end-to-end test
- `tests/art_shots.py`: review screenshots (dirt stages 1-5 + mid-rub, dead fish, locked shop, fed meter, dirty feed, away summary, fish L1-L4 sheets)
- `tools/sync_tuning.py`: copies Designer's tuning.json into `config.js` `TUNING` verbatim
- `screenshots/`: output from the test run
