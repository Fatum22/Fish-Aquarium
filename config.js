/*
 * ============================================================================
 *  AQUARIUM - BALANCE CONFIG (single source of truth for every balance number)
 *
 *  TUNING below is a VERBATIM copy of Designer's
 *    /workspace/studio/briefs/aquarium/design/tuning.json   (v2, slow game)
 *  with the rules/proofs in NUMBERS.md (v2) in the same folder. To retune: paste
 *  a new tuning.json over the TUNING object (keys unchanged) and reload. The
 *  headless test (tests/verify.py) asserts TUNING == tuning.json.
 *
 *  Units: seconds of game time at debug speed x1 (the debug speed multiplies
 *  every timer equally, including time while the game is closed).
 *  Gold, food and XP are integers.
 *
 *  How the game reads TUNING (NUMBERS.md v2):
 *   - growSec[i]       : growth time from level i+1 to i+2 (L1->L2, L2->L3, L3->L4)
 *   - hungerPoint      : fraction of the current level's growth at which the fish gets hungry (once per level)
 *   - deathSec         : death timer from the moment a fish gets hungry (same for every species/level)
 *   - adultHungerSec   : an adult (L4) gets hungry this long after reaching L4, then after each full feed
 *   - portion          : foodBase * level * rarityFoodMult[rarity] food; one Food tap gives foodPerTap food
 *                        to the nearest fish that still needs food, so it takes ceil(portion / foodPerTap) taps
 *   - feedGoldPerFish  : gold paid when a fish becomes fully fed
 *   - levelUpGold[i]   : gold on reaching L(i+2); also tank XP when tank.xp.fishLevelUp = "equalsLevelUpGold"
 *   - sell[i]          : sell price at L(i+1); sell[0] = 0 -> "Release (0 gold)"
 *   - unlockTankLevel  : species can only be bought at this tank level or higher
 *   - dirt (model timeSinceClean): stage n at stageAtSec[n-1] seconds since the last full clean
 *                        (the dirt clock only runs while the tank has at least one living fish)
 *   - dirt.spots       : spots on the glass at stage n = spots[n-1]
 *   - dirt.cleanGold   : flat payout for any full clean (+ tank.xp.clean XP)
 *   - dirt.rubPxPerSpot: grime of a spot that appears at stage n = px of sponge travel over it
 *   - tank.levelAtXp   : total XP needed for tank level 1..5
 *   - offlineProgress  : timers keep running while the game is closed (catch-up on load, capped at 7 days)
 *   - deadFish         : dead fish float belly-up until removed (0 gold), take a tank slot and keep the dirt clock running
 *   - debugSpeeds / debugDefaultSpeed : on-screen speed control (x1..x20), page opens at x1; ?speed=N (hidden) allows any N
 * ============================================================================
 */
window.AQUARIUM_CONFIG = {
  source: 'tuning.json (Designer v2 slow game, 2026-09-27)',

  // ---- VERBATIM tuning.json ------------------------------------------------
  TUNING: {
    "version": 2,
    "startGold": 20,
    "startFood": 10,
    "tankCapacity": 6,
    "maxLevel": 4,
    "foodPack": {
      "food": 10,
      "gold": 10
    },
    "foodPerTap": 1,
    "feedGoldPerFish": 1,
    "hungerPoint": 0.5,
    "deathSec": 57600,
    "rarityFoodMult": {
      "common": 1
    },
    "offlineProgress": true,
    "debugSpeeds": [
      1,
      5,
      10,
      15,
      20
    ],
    "species": [
      {
        "id": "guppy",
        "name": "Guppy",
        "latin": "Poecilia reticulata",
        "rarity": "common",
        "unlockTankLevel": 1,
        "price": 20,
        "foodBase": 1,
        "growSec": [
          3600,
          7200,
          14400
        ],
        "levelUpGold": [
          10,
          20,
          40
        ],
        "sell": [
          0,
          10,
          30,
          90
        ],
        "adultHungerSec": 14400
      },
      {
        "id": "danio",
        "name": "Zebra Danio",
        "latin": "Danio rerio",
        "rarity": "common",
        "unlockTankLevel": 2,
        "price": 40,
        "foodBase": 1,
        "growSec": [
          4500,
          9000,
          18000
        ],
        "levelUpGold": [
          20,
          40,
          80
        ],
        "sell": [
          0,
          20,
          60,
          180
        ],
        "adultHungerSec": 18000
      },
      {
        "id": "neon",
        "name": "Neon Tetra",
        "latin": "Paracheirodon innesi",
        "rarity": "common",
        "unlockTankLevel": 3,
        "price": 60,
        "foodBase": 2,
        "growSec": [
          6300,
          12600,
          25200
        ],
        "levelUpGold": [
          30,
          60,
          120
        ],
        "sell": [
          0,
          30,
          90,
          270
        ],
        "adultHungerSec": 25200
      },
      {
        "id": "platy",
        "name": "Platy",
        "latin": "Xiphophorus maculatus",
        "rarity": "common",
        "unlockTankLevel": 4,
        "price": 100,
        "foodBase": 2,
        "growSec": [
          9000,
          18000,
          36000
        ],
        "levelUpGold": [
          50,
          100,
          200
        ],
        "sell": [
          0,
          50,
          150,
          450
        ],
        "adultHungerSec": 36000
      }
    ],
    "adultHungerFrom": "reachL4ThenLastFeed",
    "dirt": {
      "model": "timeSinceClean",
      "stageAtSec": [
        10800,
        21600,
        43200,
        86400,
        172800
      ],
      "spots": [
        2,
        3,
        4,
        5,
        6
      ],
      "cleanGold": 10,
      "rubPxPerSpot": [
        150,
        150,
        220,
        220,
        220
      ],
      "stage5Film": true,
      "runsWithEmptyTank": true
    },
    "tank": {
      "levelAtXp": [
        0,
        60,
        400,
        1200,
        3000
      ],
      "maxLevel": 5,
      "xp": {
        "fishLevelUp": "equalsLevelUpGold",
        "clean": 5,
        "sell": 0,
        "feed": 0
      },
      "level5Reward": "decorationsLater"
    },
    "starterGrant": {
      "oneTime": true,
      "when": "noLivingFish && gold < 20",
      "topUpGoldTo": 20
    },
    "debugDefaultSpeed": 1,
    "deadFish": {
      "staysUntilRemoved": true,
      "removeGold": 0,
      "takesTankSlot": true
    }
  },

  // ---- Tank XP source switch (NUMBERS.md 1f / 11: open question for Maksims) --
  // 'designer' = use TUNING.tank.xp as written (default: level-ups give XP equal to their gold,
  // +5 per clean, 0 for selling/feeding). The other presets exist so the answer is a one-word change
  // here without editing the verbatim TUNING copy.
  XP_SOURCE: 'designer',
  XP_PRESETS: {
    levelUpsOnly:    { fishLevelUp: 'equalsLevelUpGold', clean: 0, sell: 0, feed: 0 },
    levelUpsAndSell: { fishLevelUp: 'equalsLevelUpGold', clean: 5, sell: 'equalsSellGold', feed: 0 },
  },

  // ---- Offline catch-up (NUMBERS.md 9.3) -------------------------------------
  OFFLINE_CAP_SEC: 7 * 24 * 3600, // one catch-up replays at most 7 days of game time

  // ---- Rarity scaling for LATER (not in tuning.json; NUMBERS.md section 8).
  // Only "common" is used now. Food multiplier comes from TUNING.rarityFoodMult
  // (falls back to foodMult here for non-common).
  RARITY_LATER: {
    common: { growthMult: 1, foodMult: 1, goldMult: 1,  diamondStub: false },
    rare:   { growthMult: 2, foodMult: 3, goldMult: 4,  diamondStub: true },
    epic:   { growthMult: 4, foodMult: 6, goldMult: 10, diamondStub: true },
  },

  // ---- Presentation only (NOT balance; engineer-chosen, safe to change) -----
  VISUAL: {
    levelSizeScale: [0.55, 0.7, 0.85, 1.0], // fish drawing size by level L1..L4
    speciesSize: { guppy: 0.82, danio: 0.95, neon: 0.85, platy: 1.0 },
    spongeRadiusFrac: 0.14,  // doubled per Maksims 2026-09-27 (finger hid the sponge)
    spongeTouchLiftFrac: 1.25, // on touch, sponge drawn + cleans this many sponge radii above the fingertip
    // Dirt look per stage (Art Director DIRT_AND_FISH_GROWTH.md s.1). r = radius range as a fraction of
    // tank width (stage 3: the long radius of its 2.2:1 drip). A spot keeps the look of the stage it spawned at.
    dirtStages: [
      { look: 'smudge', r: [0.075, 0.11], color: '#7A8A4A', alpha: 0.16 }, // soft round film, no speckles
      { look: 'dots',   r: [0.10, 0.13],  color: '#6B8F3A', alpha: 0.20 }, // 5-8 small algae dots
      { look: 'drip',   r: [0.14, 0.18],  color: '#5E7A2E', alpha: 0.24 }, // 2.2:1 streak, darker bottom
      { look: 'hair',   r: [0.16, 0.20],  color: '#4A6B24', alpha: 0.28, strandAlpha: 0.5 }, // patch 0.28 + 6-10 wavy strands at ~50% (AD ruling 3)
      { look: 'crust',  r: [0.20, 0.24],  color: '#5A5228', alpha: 0.34 }, // rough brown crust + speckles
    ],
    dirtOverlapChance: 0.5,   // stage 2+ spot spawns overlapping an older spot this often
    dirtOverlapEdgeFrac: 0.6, // ...with its centre within 0.6 x older radius of the older spot's edge
    dirtWashPerStage: 0.03,   // whole-tank green wash alpha per stage
    // Fish growth look by level L1..L4 (s.2). Size still comes from levelSizeScale.
    fishGrowth: {
      sat:        [0.30, 0.55, 0.80, 1.00], // body colour saturation vs adult palette
      tailLen:    [0.45, 0.65, 0.85, 1.00],
      tailSpread: [0.50, 0.70, 0.85, 1.00],
      finAlpha:   [0,    0.40, 0.70, 1.00], // 0 = clear fins rgba(235,240,245,0.22) + white edge
      markAlpha:  [0,    0.40, 1.00, 1.00], // main markings; L4 adds adult detail
      // AD ruling 2026-09-27: platy (only warm fish) fins+tail total opacity 65% at L2, 85% at L3 so orange doesn't turn grey over blue water.
      // Multipliers on the platy's own fin alpha 0.85: 0.65/0.85 and 0.85/0.85.
      finAlphaBySpecies: { platy: [0, 0.65 / 0.85, 1.00, 1.00] },
    },
    saveKey: 'aquarium.save.v2', // v2 rules: v1 saves are not loaded
    saveEveryMs: 2000,
  },
};

/*
 * Designer's proofs (NUMBERS.md v2 sections 4 and 5) are recomputed from TUNING at startup in
 * js/game.js -> Game.balanceChecks() and printed with console.info:
 *   clean gold per day at stage 1..5: 80 > 40 > 20 > 10 > 5 (cleaning at stage 1 earns 16x stage 5)
 *   gold per hour, sell@L3 vs sell@L4: Guppy 13.0 < 19.6, Danio 21.1 < 31.7, Neon 21.9 < 33.5, Platy 26.0 < 39.4
 */
