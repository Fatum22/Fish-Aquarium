# Aquarium — one-tank web prototype

## HOW TO RUN

```bash
cd /workspace/aquarium && python3 -m http.server 8766 --bind 127.0.0.1
```

Open **http://127.0.0.1:8766/**. For fast, repeatable timer testing, open **http://127.0.0.1:8766/?speed=60**.
The `?speed=N` URL parameter overrides the saved or default debug speed (any value from 1 to 1000). `?debug=0` hides the debug bar.

Plain HTML/CSS/JS. There's no build step, no framework and no npm. It also opens straight from `index.html` (file://).

## How to test (about 5 minutes at ×60)

1. **Start:** the tank is empty, with 20 gold and 10 food.
2. **Buy:** Shop → Guppy (20). The fish swims in and shows a blue "feed me" marker. Tap it with **Look** and the panel reads *Growth: Not started - feed to start* and *Waiting for first feed*. An unfed fish never gets hungry or dies.
3. **Feed:** pick **Food** and tap the tank. Pellets drop, it costs 1 food, you get +1 gold, and growth starts.
4. **Get hungry:** at ×60 the Guppy is hungry after about 2 s (halfway through L1). It shows an orange "!" marker and swims sluggishly. With **Look**, tap it: *Hungry! Growth paused*, the growth bar is striped and frozen, and **Death timer: dies in m:ss** counts down.
5. **Dirty → blocked:** the dirt bar fills in 5 stages (no clock is shown) and spots appear on the glass. At stage 1 or higher, a Food tap is refused with **"Clean the tank first"**.
6. **Rub clean:** pick **Sponge** and drag (mouse or finger) back and forth over the spots. Each spot fades as you rub. When the last spot clears, you're paid gold (3/5/7/8/9 for stages 1–5) and the dirt timer resets.
7. **Feed again:** the death timer clears and growth resumes.
8. **Level up:** at the end of L1 the fish grows, you get **+10 gold** (Guppy) with a floating "+10g", and it gets bigger. Max level is L4 (Adult).
9. **Sell / release:** open the panel. L2 or higher shows **Sell for X gold**. L1 shows **Release (0 gold)** with a confirm dialog.
10. **Death:** leave a hungry fish unfed. At ×60 an L1 Guppy dies about 6 s after getting hungry. It floats up grey, belly-up, and a toast says "Guppy died of hunger".
11. **Debug bar:** ×1 / ×10 / ×60 speed, **+100g** (a cheat for testing), **Reset save**.

Automated check: `/workspace/tools/venv-aq/bin/python tests/verify.py` (Playwright + Chromium, uses `?speed=60`, writes `screenshots/`).

## Numbers

Every balance number is in **`config.js`**. `TUNING` there is a **verbatim copy of Designer's `/workspace/studio/briefs/aquarium/design/tuning.json`** (v1.2, dirt-load model). The rules follow `NUMBERS.md` in the same folder. The test asserts that `config.js` and `tuning.json` match. To retune, paste a new tuning.json over `TUNING`. The only non-tuning values in config.js are the drafted rare/epic multipliers (NUMBERS.md §7, not used in v1) and presentation-only values (fish draw size, sponge size, save key).

## Rules as implemented (NUMBERS.md)

- Per-fish states: WAITING → GROWING ⇄ HUNGRY → … → ADULT ⇄ ADULT_HUNGRY, or → dead (removed, toast, no gold).
- The fish gets hungry at 50% of each level's growth. While hungry, growth pauses and the death timer (1.5 × that level's growth) runs. Feeding clears it.
- An adult gets hungry `growSec[2]` after its **last feed**, with a death timer of 1.5 × that.
- One Food tap feeds every WAITING or hungry fish. Each fish costs `foodBase × level × rarityFoodMult` and pays +1 gold. When food is short, fish closest to death eat first (WAITING fish last). Any dirt blocks feeding. Dirt builds from the fish: each living fish adds `loadPerMinByLevel` points per minute (L1 2, L2 3, L3 5, adult 8; a never-fed fish counts as L1), capped at 20 per minute; stages start at 24, 48, 80, 120 and 176 points. The sponge is twice the old size and, on touch, is drawn just above the fingertip.
- Dirt builds only while there's at least one living fish (it pauses, and doesn't reset, if the tank empties). Stages come at 180/360/600/900/1320 s, with 2–6 spots. Each spot's grime is px of sponge travel (150 px for spots that appear at stages 1–2, 220 px at stages 3–5). The payout depends on the stage when the last spot clears.
- Tank capacity is 6 (Buy shows "Tank full"). Unaffordable prices show in red and the Buy button is disabled.
- **Edge case 5 (pending Maksims' veto):** a one-time top-up to 20 gold when there are no living fish and gold is below the cheapest baby (20). Food is ignored. A flag is saved so it fires once per save. It's one line in `js/game.js` → `checkStarterGrant`.
- Diamonds: a disabled "Diamonds: coming later" stub in the shop only. No payments.

## Save

Progress is saved to `localStorage` (`aquarium.save.v1`) every 2 s and when the page hides. **Simple rule: time doesn't pass while the page is closed.** After a reload the game resumes exactly where it was saved, with no offline progress. If the tab is only in the background, timers catch up on return, deaths included (NUMBERS.md §8.9).

## Files

- `index.html`, `style.css`: layout (HUD / tank / tools / debug bar), portrait-first
- `config.js`: all balance numbers (tuning.json)
- `js/game.js`: game state, simulation, feeding, rubbing, selling, save/load, balance self-checks
- `js/fishart.js`: procedural canvas fish art for 4 species
- `js/main.js`: rendering, swimming AI, pointer input, panels, shop, debug bar
- `tests/verify.py`: headless end-to-end test
- `screenshots/`: output from the test run
