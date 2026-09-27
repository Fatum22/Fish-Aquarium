/*
 * ============================================================================
 *  AQUARIUM - BALANCE CONFIG (single source of truth for every balance number)
 *
 *  TUNING below is a VERBATIM copy of Designer's
 *    /workspace/studio/briefs/aquarium/design/v4_archive/tuning.json   (version 4)
 *  with the rules/proofs in NUMBERS.md (v4) in the same folder (v5.1 comes later). To retune: run
 *  `python3 tools/sync_tuning.py` (copies tuning.json over TUNING) and reload. The
 *  headless test (tests/verify.py) asserts TUNING == tuning.json.
 *
 *  Units: seconds of game time at debug speed x1 (the debug speed multiplies
 *  every timer equally, including time while the game is closed).
 *  Gold, food and XP are integers.
 *
 *  How the game reads TUNING (NUMBERS.md v4):
 *   - growSec[i]       : growth time from level i+1 to i+2 (L1->L2, L2->L3, L3->L4); v4 = v3 / 20
 *   - hungerPoints     : [0, 0.5] = two meals per level: a start meal (at level start) and a mid meal at 50%.
 *                        A new L1 fish WAITS for its start meal (never hungry, never dies); at L2-L4 the start
 *                        meal is a real hunger with the death timer running.
 *   - deathSec[L-1]    : death timer by the fish's level when it gets hungry (L1 6 h, L2 7 h, L3 9 h, L4 10 h; same
 *                        for every species; just levelled up = the new level's timer)
 *   - adultHungerSec   : after its L4 start meal an adult gets hungry this long after its last full meal
 *   - mealFood[L-1]    : food per meal at level L (x rarity foodMult); one Food tap = foodPerTap food to the nearest
 *                        hungry fish; a completed meal gives species feedXp and moves the dirt clock dirt.mealAddsSec
 *   - feedGoldPerFish  : 0 (no feed gold)
 *   - levelUpGold[i] / levelUpXp[i] : gold / tank XP on reaching L(i+2)
 *   - sell[i] / sellXp[i] : gold / tank XP for selling at L(i+1); sell[0] = 0 -> "Release"
 *   - foodPacks        : shop Food category (10 food / 5 gold, 50 / 25)
 *   - unlockTankLevel  : species can only be bought at this tank level or higher
 *   - dirt (model timeSinceClean): stage n at stageAtSec[n-1] seconds since the last full clean (any fish or none)
 *   - dirt.spots / cleanGold / rubPxPerSpot : spots at stage n, pay for a full clean by the stage when rubbing
 *                        started (+ tank.xp.clean XP), grime px per spot
 *   - newTank          : a new tank starts at dirtClockStartSec (12 h = stage 3), 0 gold / 0 food / 0 diamonds; the
 *                        first full clean pays firstCleanReward (20 gold + 10 food) instead of the stage pay
 *   - tank.levelAtXp   : total XP needed for tank level 1..5; level5Reward.tankCapacity = 8 fish at level 5
 *   - decorations      : free leaf/stone, max 12, size 0.5-2.0x per axis in 0.1 steps, colour 0-100, move 8 px/tap
 *   - offlineProgress  : timers keep running while the game is closed (catch-up on load, capped at 7 days)
 *   - deadFish         : dead fish float belly-up until removed (0 gold) and take a tank slot
 *   - debugSpeeds / debugDefaultSpeed : on-screen speed control (x1..x20), page opens at x1; ?speed=N (hidden) allows any N
 * ============================================================================
 */
window.AQUARIUM_CONFIG = {
  source: 'tuning.json v4 (Designer, 2026-09-27 19:30)',

  // ---- VERBATIM tuning.json ------------------------------------------------
  TUNING: {
    "version": 4,
    "startGold": 0,
    "startFood": 0,
    "tankCapacity": 6,
    "maxLevel": 4,
    "foodPerTap": 1,
    "feedGoldPerFish": 0,
    "deathSec": [
      21600,
      25200,
      32400,
      36000
    ],
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
        "growSec": [
          180,
          360,
          720
        ],
        "levelUpGold": [
          1,
          2,
          4
        ],
        "sell": [
          0,
          8,
          18,
          40
        ],
        "adultHungerSec": 720,
        "levelUpXp": [
          10,
          20,
          40
        ],
        "mealFood": [
          1,
          1,
          1,
          2
        ],
        "feedXp": 1,
        "sellXp": [
          0,
          10,
          25,
          80
        ]
      },
      {
        "id": "danio",
        "name": "Zebra Danio",
        "latin": "Danio rerio",
        "rarity": "common",
        "unlockTankLevel": 2,
        "price": 50,
        "growSec": [
          225,
          450,
          900
        ],
        "levelUpGold": [
          3,
          5,
          10
        ],
        "sell": [
          0,
          20,
          45,
          100
        ],
        "adultHungerSec": 900,
        "levelUpXp": [
          20,
          40,
          80
        ],
        "mealFood": [
          1,
          2,
          2,
          3
        ],
        "feedXp": 2,
        "sellXp": [
          0,
          20,
          50,
          160
        ]
      },
      {
        "id": "neon",
        "name": "Neon Tetra",
        "latin": "Paracheirodon innesi",
        "rarity": "common",
        "unlockTankLevel": 3,
        "price": 90,
        "growSec": [
          315,
          630,
          1260
        ],
        "levelUpGold": [
          5,
          9,
          18
        ],
        "sell": [
          0,
          36,
          81,
          180
        ],
        "adultHungerSec": 1260,
        "levelUpXp": [
          30,
          60,
          120
        ],
        "mealFood": [
          2,
          3,
          3,
          4
        ],
        "feedXp": 3,
        "sellXp": [
          0,
          30,
          75,
          240
        ]
      },
      {
        "id": "platy",
        "name": "Platy",
        "latin": "Xiphophorus maculatus",
        "rarity": "common",
        "unlockTankLevel": 4,
        "price": 150,
        "growSec": [
          450,
          900,
          1800
        ],
        "levelUpGold": [
          8,
          15,
          30
        ],
        "sell": [
          0,
          60,
          135,
          300
        ],
        "adultHungerSec": 1800,
        "levelUpXp": [
          50,
          100,
          200
        ],
        "mealFood": [
          3,
          5,
          6,
          7
        ],
        "feedXp": 5,
        "sellXp": [
          0,
          50,
          125,
          400
        ]
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
        3,
        4,
        5,
        6,
        7
      ],
      "cleanGold": [
        2,
        3,
        4,
        5,
        6
      ],
      "rubPxPerSpot": [
        150,
        150,
        220,
        220,
        220
      ],
      "stage5Film": true,
      "runsWithEmptyTank": true,
      "cleanGoldIndex": "byStageAtCleanStart",
      "mealAddsSec": 300,
      "mealAddsWhen": "fishFullyFedForOneMeal",
      "showTimerToNextStage": true
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
        "fishLevelUp": "species.levelUpXp",
        "clean": 5,
        "feed": "species.feedXp per full meal",
        "sell": "species.sellXp by level sold"
      },
      "level5Reward": {
        "tankCapacity": 8
      }
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
    },
    "startDiamonds": 0,
    "newTank": {
      "dirtStartStage": 3,
      "dirtClockStartSec": 43200,
      "firstCleanReward": {
        "gold": 20,
        "food": 10,
        "replacesStagePay": true
      },
      "defaultDecorations": [
        {
          "type": "stone",
          "count": 1
        },
        {
          "type": "leaf",
          "count": 3
        }
      ]
    },
    "foodPacks": [
      {
        "food": 10,
        "gold": 5
      },
      {
        "food": 50,
        "gold": 25
      }
    ],
    "mealsPerLevel": 2,
    "hungerPoints": [
      0.0,
      0.5
    ],
    "levelStartHunger": {
      "L1": "waitingNoDeathTimer",
      "L2toL4": "hungryWithDeathTimer"
    },
    "timerScale": "v3 divided by 20, dirt unchanged",
    "rarity": {
      "common": {
        "growMult": 1,
        "foodMult": 1
      },
      "rare": {
        "growMult": 2,
        "foodMult": 3,
        "later": true
      },
      "epic": {
        "growMult": 4,
        "foodMult": 6,
        "later": true
      }
    },
    "decorations": {
      "price": 0,
      "sellRefund": "pricePaid",
      "maxInTank": 12,
      "types": {
        "leaf": {
          "colorRange": "lightGreenToDarkGreen",
          "colorSlider": [
            0,
            100
          ],
          "defaultColor": 50
        },
        "stone": {
          "colorRange": "lightGreyToDarkGrey",
          "colorSlider": [
            0,
            100
          ],
          "defaultColor": 50
        }
      },
      "scale": {
        "heightMin": 0.5,
        "heightMax": 2.0,
        "widthMin": 0.5,
        "widthMax": 2.0,
        "stepPerTap": 0.1,
        "default": 1.0
      },
      "move": {
        "stepPxPerTap": 8,
        "holdRepeatMs": 100,
        "clampInsideWater": true
      },
      "positionStoredAs": "fractionOfTankWaterArea"
    },
    "deathSecBy": "fishLevel (index 0 = L1), same for every species in v1"
  },
  // ---- END VERBATIM tuning.json (tools/sync_tuning.py replaces everything above up to TUNING) ----

  // Tank XP sources are settled (NUMBERS.md 11): the game reads TUNING.tank.xp directly. The v2
  // XP_SOURCE / XP_PRESETS switch is retired.

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
    flakesPerTap: 16,                       // food flakes in one tap's shower (visual only; still 1 food per tap)
    speciesSize: { guppy: 0.82, danio: 0.95, neon: 0.85, platy: 1.0 },
    // Landscape tank geometry (Art Director LANDSCAPE_LAYOUT_V4.md 4)
    airFrac: 0.07, airMinPx: 16,          // top 7% of the tank (min 16 px) is air; the water surface is under it
    sandFrac: 0.86, sandMinPx: 36,        // sand top edge at 86% of tank height (sand band at least 36 px)
    glassInsetFrac: 0.035,                // sand back corners inset 3.5% of tank width (both sides)
    glassLineSide: 'right',               // the ONE glass back line + side-glass strip: 'right' | 'left' (waiting on Maksims; AD v4 4)
    fishSizeFrac: 0.30,                   // fish length = min(W, waterH*0.8) * 0.30 * speciesSize * levelSize
    spongeRadiusFrac: 0.16, spongeMinPx: 40, spongeMaxPx: 72, // sponge radius = 0.16 x water height, clamped 40-72 px (AD v4 6)
    spongeTouchLiftFrac: 1.25, // on touch, sponge drawn + cleans this many sponge radii above the fingertip
    // Dirt look per stage (Art Director DIRT_AND_FISH_GROWTH.md "v2 dirt look", replaces the s.1 table; shapes as s.1).
    // r = radius range as a fraction of the WATER HEIGHT (AD v4 6; was tank width) (stage 3: the long radius of its 2.2:1 drip).
    // Stage 1 = AD v4 item 21 look: bigger, more solid smudges with a darker rim and 3-5 speckles.
    // A spot keeps the look of the stage it spawned at.
    dirtStages: [
      { look: 'smudge', r: [0.10, 0.14], color: '#7A8A4A', alpha: 0.22, rim: 0.06, speckles: [3, 5], speckleR: [1.5, 2.5], speckleAlpha: 0.35 },
      { look: 'dots',   r: [0.11, 0.14],  color: '#6B8F3A', alpha: 0.22 }, // 5-8 small algae dots
      { look: 'drip',   r: [0.16, 0.20],  color: '#5E7A2E', alpha: 0.32 }, // 2.2:1 streak, darker bottom (+0.08); reads like old stage 5
      { look: 'hair',   r: [0.20, 0.25],  color: '#4A6B24', alpha: 0.40, strandAlpha: 0.5, // patch + wavy strands at ~50% (AD ruling 3)
        tintHalf: '#5A5228', tintMix: 0.6 },                                             // brown crust tint on half the spots
      { look: 'crust',  r: [0.24, 0.30],  color: '#5A5228', alpha: 0.46 }, // rough brown crust + speckles
    ],
    // Tank-wide layer per stage, drawn in front of the fish and behind the spots. null = none,
    // { wash: css colour } = flat tint, { film: true } = the stage 5 film below.
    dirtLayer: [
      { wash: 'rgba(95,110,40,0.03)' }, // AD v4 21: stage 1 wash (was none)
      { wash: 'rgba(95,110,40,0.04)' },
      { wash: 'rgba(95,110,40,0.08)' },
      { wash: 'rgba(108,116,38,0.12)' }, // slight yellow-green
      { film: true },
    ],
    dirtFilm: {
      rgb: [70, 110, 40], centre: 0.28, edge: 0.42, // radial vignette: flat in the middle 60%, rising to the edges/corners
      cloud: 0.06, cloudDriftSec: 120,               // low-frequency blotches +-0.06, drifting one tank width per 2 minutes
      scumRgb: [96, 108, 46], scumFrac: 0.08, scumAlpha: 0.45, // waterline scum band (top 8%, soft bottom edge)
      guardZone: 0.6, guardMax: 0.6,                 // middle 60% of the tank: film + one spot <= 0.6 combined opacity
      cellPx: 6,                                     // film is computed on a coarse grid and smoothed
    },
    dirtOverlapChance: 0.5,   // stage 2+ spot spawns overlapping an older spot this often
    dirtOverlapEdgeFrac: 0.6, // ...with its centre within 0.6 x older radius of the older spot's edge
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
    // Decorations (AD LANDSCAPE_LAYOUT_V4.md 7). Default tank: 3 leaves + 1 stone. x = fraction of tank width,
    // y = fraction of the floor band (0 = sand top edge .. 1 = 60% down the sand band; engineer-chosen depths).
    defaultDecorations: [
      { type: 'leaf', x: 0.16, y: 0.25, color: 25, seed: 11 },
      { type: 'leaf', x: 0.24, y: 0.55, color: 55, seed: 23 },
      { type: 'leaf', x: 0.82, y: 0.35, color: 40, seed: 37 },
      { type: 'stone', x: 0.60, y: 0.50, color: 50, seed: 51 },
    ],
    decorFloorBand: 0.60,   // base y stays within the top 60% of the sand band
    leaf: { h: 0.30, spread: 0.07, light: [98, 68, 65], dark: [135, 50, 23], swayDeg: 6, swaySec: 4, topGapFrac: 0.04 },
    stone: { w: 0.20, h: 0.11, light: '#b8bec4', dark: '#3c4550', sink: 0.15 },
    decorMoveRepeatMs: 80, decorMoveDelayMs: 300, // AD v4 7: hold repeats every 80 ms after 300 ms (tuning's holdRepeatMs 100 is not used)
    saveKey: 'aquarium.save.v4', // v4 rules: older saves are not loaded (fresh start)
    saveEveryMs: 2000,
  },
};

/*
 * Designer's proofs (NUMBERS.md v2 sections 4 and 5) are recomputed from TUNING at startup in
 * js/game.js -> Game.balanceChecks() and printed with console.info:
 *   clean gold per day at stage 1..5: 80 > 40 > 20 > 10 > 5 (cleaning at stage 1 earns 16x stage 5)
 *   gold per hour, sell@L3 vs sell@L4: Guppy 13.0 < 19.6, Danio 21.1 < 31.7, Neon 21.9 < 33.5, Platy 26.0 < 39.4
 */
