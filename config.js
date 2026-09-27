/*
 * ============================================================================
 *  AQUARIUM - BALANCE CONFIG (single source of truth for every balance number)
 *
 *  TUNING below is a VERBATIM copy of Designer's
 *    /workspace/studio/briefs/aquarium/design/tuning.json   (v1 numbers)
 *  with the rules/proofs in NUMBERS.md in the same folder. The earlier
 *  engineer placeholders were dropped. To retune: paste a new tuning.json over
 *  the TUNING object (keys unchanged) and reload. The headless test
 *  (tests/verify.py) asserts TUNING == tuning.json.
 *
 *  Units: seconds of game time at debug speed x1 (the debug speed multiplies
 *  every timer equally). Gold and food are integers.
 *
 *  How the game reads TUNING (per NUMBERS.md):
 *   - growSec[i]       : growth time from level i+1 to i+2 (L1->L2, L2->L3, L3->L4)
 *   - hungerPoint      : fraction of the current level's growth at which the fish gets hungry (once per level)
 *   - deathMult        : death timer = deathMult * that level's growSec
 *   - adultHungerSec   : "= growSec[2] of species" -> an adult (L4) gets hungry growSec[2] after
 *                        its last feed; its death timer = deathMult * growSec[2]
 *   - food portion     : foodBase * level * rarityFoodMult[rarity]  (per fish actually fed)
 *   - feedGoldPerFish  : gold per fish actually fed on a tap
 *   - levelUpGold[i]   : gold on reaching L(i+2)
 *   - sell[i]          : sell price at L(i+1); sell[0] = 0 -> "Release (0 gold)"
 *   - dirt (model loadPoints): each living fish adds loadPerMinByLevel[level-1] points/min (unfed fish count as L1),
 *     tank total capped at maxLoadPerMin; stage n is reached at stageAtPoints[n-1] points since the last clean
 *                        (dirt only builds while the tank has at least one living fish)
 *   - dirt.spots       : spots on the glass at stage n = spots[n-1]
 *   - dirt.cleanGold   : payout for a full clean, by the stage when the LAST spot clears
 *   - dirt.rubPxPerSpot: grime of a spot that appears at stage n = px of sponge travel over it
 * ============================================================================
 */
window.AQUARIUM_CONFIG = {
  source: 'tuning.json (Designer v1.2 dirt-load, 2026-09-27)',

  // ---- VERBATIM tuning.json ------------------------------------------------
  TUNING: {
    "startGold": 20,
    "startFood": 10,
    "tankCapacity": 6,
    "maxLevel": 4,
    "foodPack": {
      "food": 10,
      "gold": 10
    },
    "feedGoldPerFish": 1,
    "hungerPoint": 0.5,
    "deathMult": 1.5,
    "rarityFoodMult": {
      "common": 1
    },
    "debugSpeeds": [
      1,
      10,
      60
    ],
    "species": [
      {
        "id": "guppy",
        "name": "Guppy",
        "latin": "Poecilia reticulata",
        "rarity": "common",
        "price": 20,
        "foodBase": 1,
        "growSec": [
          240,
          480,
          960
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
        "adultHungerSec": 960
      },
      {
        "id": "danio",
        "name": "Zebra Danio",
        "latin": "Danio rerio",
        "rarity": "common",
        "price": 40,
        "foodBase": 1,
        "growSec": [
          300,
          600,
          1200
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
        "adultHungerSec": 1200
      },
      {
        "id": "neon",
        "name": "Neon Tetra",
        "latin": "Paracheirodon innesi",
        "rarity": "common",
        "price": 60,
        "foodBase": 2,
        "growSec": [
          420,
          840,
          1680
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
        "adultHungerSec": 1680
      },
      {
        "id": "platy",
        "name": "Platy",
        "latin": "Xiphophorus maculatus",
        "rarity": "common",
        "price": 100,
        "foodBase": 2,
        "growSec": [
          600,
          1200,
          2400
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
        "adultHungerSec": 2400
      }
    ],
    "dirt": {
      "model": "loadPoints",
      "loadPerMinByLevel": [
        2,
        3,
        5,
        8
      ],
      "waitingFishCountsAsLevel": 1,
      "maxLoadPerMin": 20,
      "stageAtPoints": [
        24,
        48,
        80,
        120,
        176
      ],
      "spots": [
        2,
        3,
        4,
        5,
        6
      ],
      "cleanGold": [
        7,
        12,
        17,
        20,
        23
      ],
      "rubPxPerSpot": [
        150,
        150,
        220,
        220,
        220
      ]
    },
    "adultHungerFrom": "reachL4ThenLastFeed",
    "starterGrant": {
      "oneTime": true,
      "when": "noLivingFish && gold < 20",
      "topUpGoldTo": 20
    }
  },

  // ---- Rarity scaling for LATER (not in tuning.json; from NUMBERS.md section 7).
  // Only "common" is used in v1. Food multiplier for the game comes from
  // TUNING.rarityFoodMult (falls back to foodMult here for non-common).
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
    },
    saveKey: 'aquarium.save.v1',
    saveEveryMs: 2000,
  },
};

/*
 * Sanity checks of Designer's inequalities (NUMBERS.md sections 4 and 5) are
 * recomputed from TUNING at startup in js/game.js -> Game.balanceChecks() and
 * printed with console.info. Designer's proof (gold per minute per tank slot,
 * food valued at 1 gold/unit, ideal play):
 *   Guppy       sell@L3 3.25  < sell@L4 4.89
 *   Zebra Danio sell@L3 5.27  < sell@L4 7.91
 *   Neon Tetra  sell@L3 5.48  < sell@L4 8.37
 *   Platy       sell@L3 6.50  < sell@L4 9.86
 * Clean gold/hour at stage 1..5: 60 > 50 > 42 > 32 > 24.5 (clean often pays more).
 */
