/*
 * ============================================================================
 *  AQUARIUM - BALANCE CONFIG (single source of truth for every balance number)
 *
 *  TUNING below is a VERBATIM copy of Designer's
 *    /workspace/studio/briefs/aquarium/design/tuning.json   (version 6: 14 species, tank levels 1-10)
 *  with the rules/proofs in NUMBERS.md (v6) in the same folder. To retune: run
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
 *   - foodPacks        : shop Food category (v6.7: 5/3@Lv1, 10/5@Lv2, 50/20@Lv4, 250/75@Lv6, 500/125@Lv9)
 *   - unlockTankLevel  : species can only be bought at this tank level or higher
 *   - dirt (model timeSinceClean): stage n at stageAtSec[n-1] seconds since the last full clean (any fish or none)
 *   - dirt.spots / cleanGold / rubPxPerSpot : spots at stage n, pay for a full clean by the stage when rubbing
 *                        started (+ tank.xp.clean XP), grime px per spot
 *   - newTank          : a new tank starts at dirtClockStartSec (12 h = stage 3), 0 gold / 0 food / 0 diamonds; the
 *                        first full clean pays firstCleanReward (20 gold + 10 food) instead of the stage pay
 *   - tank.levelAtXp   : total XP needed for tank level 1..5; level5Reward.tankCapacity = 8 fish at level 5
 *   - decorations      : free leaf/stone, max 12, size 0.5-2.0x per axis in 0.1 steps, colour 0-100, move 8 px/tap
 *   - offlineProgress  : timers keep running while the game is closed (catch-up on load, capped at 7 days)
 *   - deadFish         : dead fish float belly-up until removed (v6.8: the Net pays floor(price / 4) gold, no XP) and take a tank slot
 *   - debugSpeeds / debugDefaultSpeed : on-screen speed control (x1..x20), page opens at x1; ?speed=N (hidden) allows any N
 * ============================================================================
 */
window.AQUARIUM_CONFIG = {
  source: 'tuning.json v6 (Designer, 2026-09-28 16:05)',
  // v6 rules read by js/game.js (NUMBERS v6): sell = (price / 2) x level; death = deathSecByRarity[rarity][level-1];
  // a bought baby grows from 0% with no start meal (first hunger = L1 mid at 50%); reaching L4 is not hungry and starts
  // the adult wait (adultHungerMultOfL3Grow x L3 grow); first clean 20 gold + 50 food; foodPacks (v6.7) 5/3@Lv1, 10/5@Lv2, 50/20@Lv4, 250/75@Lv6, 500/125@Lv9; foodPackLockedLabel.

  // ---- VERBATIM tuning.json ------------------------------------------------
  TUNING: {
    "version": "6.8",
    "startGold": 0,
    "startFood": 0,
    "tankCapacity": 6,
    "maxLevel": 4,
    "foodPerTap": 1,
    "feedGoldPerFish": 0,
    "deathSec": [
      43200,
      50400,
      64800,
      72000
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
          10,
          20,
          30,
          40
        ],
        "adultHungerSec": 2880,
        "levelUpXp": [
          10,
          20,
          40
        ],
        "mealFood": [
          2,
          3,
          4,
          5
        ],
        "feedXp": 1,
        "sellXp": [
          0,
          10,
          25,
          80
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
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
          25,
          50,
          75,
          100
        ],
        "adultHungerSec": 3600,
        "levelUpXp": [
          20,
          40,
          80
        ],
        "mealFood": [
          2,
          3,
          4,
          5
        ],
        "feedXp": 2,
        "sellXp": [
          0,
          20,
          50,
          160
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
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
          45,
          90,
          135,
          180
        ],
        "adultHungerSec": 5040,
        "levelUpXp": [
          30,
          60,
          120
        ],
        "mealFood": [
          2,
          3,
          4,
          5
        ],
        "feedXp": 3,
        "sellXp": [
          0,
          30,
          75,
          240
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "ram",
        "name": "German Blue Ram",
        "latin": "Mikrogeophagus ramirezi",
        "rarity": "rare",
        "unlockTankLevel": 3,
        "price": 230,
        "growSec": [
          630,
          1260,
          2520
        ],
        "levelUpGold": [
          12,
          23,
          46
        ],
        "sell": [
          115,
          230,
          345,
          460
        ],
        "adultHungerSec": 10080,
        "levelUpXp": [
          70,
          140,
          280
        ],
        "mealFood": [
          2,
          3,
          5,
          6
        ],
        "feedXp": 7,
        "sellXp": [
          0,
          70,
          175,
          560
        ],
        "deathSec": [
          64800,
          75600,
          97200,
          108000
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
          75,
          150,
          225,
          300
        ],
        "adultHungerSec": 7200,
        "levelUpXp": [
          50,
          100,
          200
        ],
        "mealFood": [
          2,
          4,
          5,
          7
        ],
        "feedXp": 5,
        "sellXp": [
          0,
          50,
          125,
          400
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "rasbora",
        "name": "Harlequin Rasbora",
        "latin": "Trigonostigma heteromorpha",
        "rarity": "uncommon",
        "unlockTankLevel": 4,
        "price": 240,
        "growSec": [
          630,
          1260,
          2520
        ],
        "levelUpGold": [
          12,
          24,
          48
        ],
        "sell": [
          120,
          240,
          360,
          480
        ],
        "adultHungerSec": 10080,
        "levelUpXp": [
          75,
          150,
          300
        ],
        "mealFood": [
          2,
          4,
          7,
          9
        ],
        "feedXp": 7,
        "sellXp": [
          0,
          75,
          188,
          600
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "dwarfgourami",
        "name": "Dwarf Gourami",
        "latin": "Trichogaster lalius",
        "rarity": "rare",
        "unlockTankLevel": 5,
        "price": 500,
        "growSec": [
          1035,
          2070,
          4140
        ],
        "levelUpGold": [
          25,
          50,
          100
        ],
        "sell": [
          250,
          500,
          750,
          1000
        ],
        "adultHungerSec": 16560,
        "levelUpXp": [
          145,
          290,
          580
        ],
        "mealFood": [
          2,
          5,
          9,
          12
        ],
        "feedXp": 14,
        "sellXp": [
          0,
          145,
          363,
          1160
        ],
        "deathSec": [
          64800,
          75600,
          97200,
          108000
        ]
      },
      {
        "id": "swordtail",
        "name": "Swordtail",
        "latin": "Xiphophorus hellerii",
        "rarity": "common",
        "unlockTankLevel": 6,
        "price": 250,
        "growSec": [
          600,
          1200,
          2400
        ],
        "levelUpGold": [
          13,
          25,
          50
        ],
        "sell": [
          125,
          250,
          375,
          500
        ],
        "adultHungerSec": 9600,
        "levelUpXp": [
          80,
          160,
          320
        ],
        "mealFood": [
          2,
          4,
          6,
          8
        ],
        "feedXp": 8,
        "sellXp": [
          0,
          80,
          200,
          640
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "cherrybarb",
        "name": "Cherry Barb",
        "latin": "Puntius titteya",
        "rarity": "uncommon",
        "unlockTankLevel": 6,
        "price": 400,
        "growSec": [
          840,
          1680,
          3360
        ],
        "levelUpGold": [
          20,
          40,
          80
        ],
        "sell": [
          200,
          400,
          600,
          800
        ],
        "adultHungerSec": 13440,
        "levelUpXp": [
          120,
          240,
          480
        ],
        "mealFood": [
          2,
          5,
          7,
          10
        ],
        "feedXp": 12,
        "sellXp": [
          0,
          120,
          300,
          960
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "angelfish",
        "name": "Angelfish",
        "latin": "Pterophyllum scalare",
        "rarity": "uncommon",
        "unlockTankLevel": 7,
        "price": 640,
        "growSec": [
          1095,
          2190,
          4380
        ],
        "levelUpGold": [
          32,
          64,
          128
        ],
        "sell": [
          320,
          640,
          960,
          1280
        ],
        "adultHungerSec": 17520,
        "levelUpXp": [
          180,
          360,
          720
        ],
        "mealFood": [
          2,
          6,
          9,
          13
        ],
        "feedXp": 18,
        "sellXp": [
          0,
          180,
          450,
          1440
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "pearlgourami",
        "name": "Pearl Gourami",
        "latin": "Trichopodus leerii",
        "rarity": "common",
        "unlockTankLevel": 8,
        "price": 600,
        "growSec": [
          1020,
          2040,
          4080
        ],
        "levelUpGold": [
          30,
          60,
          120
        ],
        "sell": [
          300,
          600,
          900,
          1200
        ],
        "adultHungerSec": 16320,
        "levelUpXp": [
          170,
          340,
          680
        ],
        "mealFood": [
          2,
          5,
          9,
          12
        ],
        "feedXp": 17,
        "sellXp": [
          0,
          170,
          425,
          1360
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "clownloach",
        "name": "Clown Loach",
        "latin": "Chromobotia macracantha",
        "rarity": "rare",
        "unlockTankLevel": 8,
        "price": 1500,
        "growSec": [
          2040,
          4080,
          8160
        ],
        "levelUpGold": [
          75,
          150,
          300
        ],
        "sell": [
          750,
          1500,
          2250,
          3000
        ],
        "adultHungerSec": 32640,
        "levelUpXp": [
          385,
          770,
          1540
        ],
        "mealFood": [
          2,
          7,
          11,
          16
        ],
        "feedXp": 38,
        "sellXp": [
          0,
          385,
          963,
          3080
        ],
        "deathSec": [
          64800,
          75600,
          97200,
          108000
        ]
      },
      {
        "id": "rainbowfish",
        "name": "Boeseman's Rainbowfish",
        "latin": "Melanotaenia boesemani",
        "rarity": "uncommon",
        "unlockTankLevel": 9,
        "price": 1440,
        "growSec": [
          1935,
          3870,
          7740
        ],
        "levelUpGold": [
          72,
          144,
          288
        ],
        "sell": [
          720,
          1440,
          2160,
          2880
        ],
        "adultHungerSec": 30960,
        "levelUpXp": [
          360,
          720,
          1440
        ],
        "mealFood": [
          2,
          7,
          11,
          16
        ],
        "feedXp": 36,
        "sellXp": [
          0,
          360,
          900,
          2880
        ],
        "deathSec": [
          43200,
          50400,
          64800,
          72000
        ]
      },
      {
        "id": "discus",
        "name": "Discus",
        "latin": "Symphysodon aequifasciatus",
        "rarity": "rare",
        "unlockTankLevel": 10,
        "price": 3250,
        "growSec": [
          3600,
          7200,
          14400
        ],
        "levelUpGold": [
          163,
          325,
          650
        ],
        "sell": [
          1625,
          3250,
          4875,
          6500
        ],
        "adultHungerSec": 57600,
        "levelUpXp": [
          720,
          1440,
          2880
        ],
        "mealFood": [
          2,
          7,
          11,
          16
        ],
        "feedXp": 72,
        "sellXp": [
          0,
          720,
          1800,
          5760
        ],
        "deathSec": [
          64800,
          75600,
          97200,
          108000
        ]
      }
    ],
    "adultHungerFrom": "onReachL4_startWait_thenLastFeed",
    "dirt": {
      "model": "timeSinceClean",
      "stageAtSec": [
        5400,
        10800,
        21600,
        43200,
        86400
      ],
      "spots": [
        3,
        4,
        5,
        6,
        7
      ],
      "cleanGold": [
        4,
        7,
        12,
        20,
        32
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
      "showTimerToNextStage": false,
      "cleanGoldRule": "v6.5 (Maksims approved 2026-09-28): 4 / 7 / 12 / 20 / 32 by stage at first sponge contact"
    },
    "tank": {
      "levelAtXp": [
        0,
        60,
        400,
        1200,
        3000,
        10000,
        22000,
        40000,
        65000,
        100000
      ],
      "maxLevel": 10,
      "xp": {
        "fishLevelUp": "species.levelUpXp",
        "clean": 5,
        "feed": "species.feedXp per full meal",
        "sell": "species.sellXp by level sold"
      },
      "levelRewards": {
        "5": {
          "tankCapacity": 8
        },
        "8": {
          "tankCapacity": 10
        },
        "10": {
          "tankCapacity": 12
        },
        "note": "every level 2-10 also unlocks the species whose unlockTankLevel matches"
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
      "removeGold": "floor(species.price / 4)",
      "takesTankSlot": true,
      "removeGoldNote": "Approved by Maksims 2026-09-28 17:57. Same at any level the fish died at. No XP. No confirm; toast reads 'Fish removed · +N gold'.",
      "removeXp": 0
    },
    "startDiamonds": 0,
    "newTank": {
      "dirtStartStage": 3,
      "dirtClockStartSec": 21600,
      "firstCleanReward": {
        "gold": 20,
        "food": 50,
        "replacesStagePay": true
      },
      "defaultDecorations": []
    },
    "foodPacks": [
      {
        "food": 5,
        "gold": 3,
        "unlockTankLevel": 1
      },
      {
        "food": 10,
        "gold": 5,
        "unlockTankLevel": 2
      },
      {
        "food": 50,
        "gold": 20,
        "unlockTankLevel": 4
      },
      {
        "food": 250,
        "gold": 75,
        "unlockTankLevel": 6
      },
      {
        "food": 500,
        "gold": 125,
        "unlockTankLevel": 9
      }
    ],
    "mealsPerLevel": 2,
    "hungerPoints": [
      0.5,
      1.0
    ],
    "levelStartHunger": {
      "onBuy": "growingNotHungry",
      "at50Percent": "hungryMidMeal",
      "at100Percent": "hungryEndMeal_levelUpAfterFed",
      "onLevelUpL2orL3": "notHungryGrowFrom0",
      "onReachL4": "notHungryStartAdultWait",
      "adultAfterWait": "hungryWithDeathTimer"
    },
    "timerScale": "v3 divided by 20, dirt unchanged",
    "rarity": {
      "common": {
        "vsLevelCommon": {
          "p": 1,
          "g": 1,
          "m": 1,
          "x": 1
        }
      },
      "uncommon": {
        "vsLevelCommon": {
          "p": 1.6,
          "g": 1.4,
          "m": 1.25,
          "x": 1.5
        }
      },
      "rare": {
        "vsLevelCommon": {
          "p": 2.5,
          "g": 2,
          "m": 1.5,
          "x": 2.25
        }
      },
      "epic": {
        "later": true
      },
      "mealFoodCap": 16,
      "note": "rarity independent of unlock level; sell is v6 formula; deathSec longer for rare; multipliers only document how price/grow/meals/xp were built; v6.2: mealFood set directly per species (mealFoodRule), rarity m no longer used",
      "sellFormula": "(price / 2) * fishLevel, integer; L1=price/2 … L4=2*price"
    },
    "decorations": {
      "price": {
        "stone": 2,
        "leaf": 1
      },
      "sellRefund": "floor(pricePaid / 2)",
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
        "stepPxPerTapX": 8,
        "stepPxPerTapY": 4,
        "holdRepeatMs": 100,
        "clampInsideWater": true
      },
      "positionStoredAs": "fractionOfTankWaterArea",
      "shopItems": {
        "status": "locked 2026-09-28 18:54 (Maksims asked Designer to set logical numbers; art approved without extra review)",
        "items": [
          {
            "id": "driftwood",
            "name": "Driftwood Branch",
            "unlockTankLevel": 2,
            "price": 60,
            "placeXp": 15,
            "lookNote": "Twisted bleached branch lying on the sand, bark detail and knots",
            "colorSlider": false
          },
          {
            "id": "coralFan",
            "name": "Fan Coral",
            "unlockTankLevel": 2,
            "price": 100,
            "placeXp": 25,
            "lookNote": "Flat lacy sea-fan shape (shape name is a suggestion; Art Director owns the look)",
            "colorSlider": true,
            "colorRange": "pinkToRedToDarkRed",
            "colorSliderRange": [
              0,
              100
            ],
            "defaultColor": 50
          },
          {
            "id": "amphora",
            "name": "Clay Amphora",
            "unlockTankLevel": 3,
            "price": 150,
            "placeXp": 38,
            "lookNote": "Old terracotta jar on its side, chipped rim, faded painted band",
            "colorSlider": false
          },
          {
            "id": "coralStaghorn",
            "name": "Staghorn Coral",
            "unlockTankLevel": 3,
            "price": 220,
            "placeXp": 55,
            "lookNote": "Branching antler-like arms (shape name is a suggestion; Art Director owns the look)",
            "colorSlider": true,
            "colorRange": "lightBlueToDarkBlue",
            "colorSliderRange": [
              0,
              100
            ],
            "defaultColor": 50
          },
          {
            "id": "chest",
            "name": "Treasure Chest",
            "unlockTankLevel": 4,
            "price": 300,
            "placeXp": 75,
            "lookNote": "Wooden chest with iron bands, lid ajar, a few gold coins spilling out",
            "colorSlider": false
          },
          {
            "id": "coralBrain",
            "name": "Brain Coral",
            "unlockTankLevel": 4,
            "price": 420,
            "placeXp": 105,
            "lookNote": "Round dome with winding grooves (shape name is a suggestion; Art Director owns the look)",
            "colorSlider": true,
            "colorRange": "lightGreenToDarkGreen",
            "colorSliderRange": [
              0,
              100
            ],
            "defaultColor": 50
          },
          {
            "id": "helmet",
            "name": "Diver's Helmet",
            "unlockTankLevel": 5,
            "price": 600,
            "placeXp": 150,
            "lookNote": "Brass diving helmet with round portholes, green patina",
            "colorSlider": false
          },
          {
            "id": "coralTube",
            "name": "Tube Coral",
            "unlockTankLevel": 5,
            "price": 800,
            "placeXp": 200,
            "lookNote": "Cluster of upright hollow tubes (shape name is a suggestion; Art Director owns the look)",
            "colorSlider": true,
            "colorRange": "yellowToOrangeToDarkOrange",
            "colorSliderRange": [
              0,
              100
            ],
            "defaultColor": 50
          },
          {
            "id": "castle",
            "name": "Castle Ruins",
            "unlockTankLevel": 6,
            "price": 1000,
            "placeXp": 250,
            "lookNote": "Crumbling stone tower with an arched doorway and broken battlements",
            "colorSlider": false
          },
          {
            "id": "shipwreck",
            "name": "Sunken Ship",
            "unlockTankLevel": 7,
            "price": 1600,
            "placeXp": 400,
            "lookNote": "Broken wooden hull tilted in the sand, mast snapped, torn sail",
            "colorSlider": false
          }
        ],
        "xpRule": "placeXp = price / 4 (rounded). Paid when the bought decoration is placed in the tank. Moving, resizing or recolouring later pays nothing.",
        "xpOncePerType": true,
        "xpOncePerTypeNote": "XP is paid only the first time each shop decoration is bought on this tank (until reset). Repeat copies cost gold and pay 0 XP. Selling pays half the price paid, rounded down, and never takes XP back.",
        "colorSlider": false,
        "scaleAndMove": "same as leaf/stone",
        "countsTowardMaxInTank": true,
        "lockedLabel": "Unlocks at Aquarium Lv {N}",
        "sellRefund": "floor(pricePaid / 2)",
        "sellRemovesXp": false,
        "colorSliderNote": "Corals use the same colour slider as leaf/stone (0 light to 100 dark). The other 6 have fixed colours."
      },
      "placeXp": {
        "stone": 1,
        "leaf": 0
      },
      "basicXpNote": "Stone and leaf: XP paid only for the first copy of each type on this tank (until reset), same rule as shopItems. Both available from Aquarium Lv 1. Colour slider stays.",
      "existingSaves": "Stone/leaf already placed in a save from before v6.8 are kept, counted as bought with pricePaid 0 (so selling them refunds 0), and their type counts as already bought for first-copy XP. Only brand-new tanks start empty.",
      "basicStatus": "approved by Maksims 2026-09-28 17:55 (stone/leaf 2 gold, 1 XP first buy, new tanks empty, existing-saves rule)",
      "sellRemovesXp": false,
      "sellRefundNote": "Approved by Maksims 2026-09-28 17:56. 2-gold stone/leaf sells for 1; old free pieces (pricePaid 0) sell for 0. XP is never taken back.",
      "sellRefundOverride": {
        "leaf": "pricePaid"
      },
      "leafNote": "Maksims 2026-09-28 19:13: leaf costs 1 gold, sells back for the full price paid (1 gold; old free leaves still sell for 0), gives no XP. Stone stays 2 gold, 1 XP first buy, sells for 1."
    },
    "deathSecBy": "species.rarity → deathSecByRarity[rarity][fishLevel-1]; uncommon matches common; rare is longer at every level",
    "levelCommonBaseline": {
      "1": {
        "price": 20,
        "growL1Sec": 180,
        "mealFood": [
          1,
          1,
          1,
          2
        ],
        "xpBase": 10
      },
      "2": {
        "price": 50,
        "growL1Sec": 225,
        "mealFood": [
          1,
          2,
          2,
          3
        ],
        "xpBase": 20
      },
      "3": {
        "price": 90,
        "growL1Sec": 315,
        "mealFood": [
          2,
          3,
          3,
          4
        ],
        "xpBase": 30
      },
      "4": {
        "price": 150,
        "growL1Sec": 450,
        "mealFood": [
          3,
          5,
          6,
          7
        ],
        "xpBase": 50
      },
      "5": {
        "price": 200,
        "growL1Sec": 520,
        "mealFood": [
          3,
          5,
          6,
          8
        ],
        "xpBase": 65
      },
      "6": {
        "price": 250,
        "growL1Sec": 600,
        "mealFood": [
          4,
          5,
          6,
          8
        ],
        "xpBase": 80
      },
      "7": {
        "price": 400,
        "growL1Sec": 780,
        "mealFood": [
          5,
          6,
          8,
          10
        ],
        "xpBase": 120
      },
      "8": {
        "price": 600,
        "growL1Sec": 1020,
        "mealFood": [
          6,
          8,
          9,
          12
        ],
        "xpBase": 170
      },
      "9": {
        "price": 900,
        "growL1Sec": 1380,
        "mealFood": [
          7,
          9,
          11,
          14
        ],
        "xpBase": 240
      },
      "10": {
        "price": 1300,
        "growL1Sec": 1800,
        "mealFood": [
          8,
          10,
          12,
          16
        ],
        "xpBase": 320
      }
    },
    "deathSecByRarity": {
      "common": [
        43200,
        50400,
        64800,
        72000
      ],
      "uncommon": [
        43200,
        50400,
        64800,
        72000
      ],
      "rare": [
        64800,
        75600,
        97200,
        108000
      ]
    },
    "adultHungerMultOfL3Grow": 4,
    "hungerPointsNote": "v6.3: L1-L3 each have 2 meals, mid at 50% and end at 100%. Growth pauses while hungry. The level-up happens only when the end meal is complete. No meal on buy or on level-up. L4: one meal of mealFood[3] each time adultHungerSec runs out.",
    "mealFoodRule": "v6.3 (Maksims): mealFood[L1..L3] = total food per level, split mid/end; L1 total = 2 (1+1) for every species; L1 < L2 < L3 < L4 strictly, rares included",
    "mealSplit": {
      "appliesTo": "L1-L3",
      "meaning": "mealFood[L] is the total food for that level",
      "midMeal": "floor(mealFood[L] / 2)",
      "endMeal": "mealFood[L] - midMeal",
      "L4": "mealFood[3] is one adult meal per adult wait"
    },
    "foodPackLockedLabel": "Unlocks at Aquarium Lv {N}",
    "foodPackLockedShown": true
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
    speciesSize: { guppy: 0.82, danio: 0.95, neon: 0.85, platy: 1.0, // V7 sizes (NEW_FISH_V7.md 6 = V6 3: ram 0.97, clown loach 1.18)
      ram: 0.97, rasbora: 0.85, dwarfgourami: 0.95, swordtail: 1.05, cherrybarb: 0.85, angelfish: 1.0, pearlgourami: 1.05, clownloach: 1.18, rainbowfish: 1.05, discus: 1.15 },
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
