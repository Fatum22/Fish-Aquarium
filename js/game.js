/* Aquarium game logic (Designer v4: v3 gold economy, fish timers /20, two meals per level, new-tank start, decorations):
 * state, simulation, actions, offline catch-up, save/load.
 * No DOM here. All balance numbers come from window.AQUARIUM_CONFIG.TUNING (config.js = tuning.json).
 */
(function (root) {
  'use strict';
  const CFG = root.AQUARIUM_CONFIG;
  const T = CFG.TUNING;
  const SPECIES = {};
  T.species.forEach((s) => { SPECIES[s.id] = s; });

  // ---------------------------------------------------------------- helpers
  // v5.1 (NUMBERS 2a): every species' numbers in tuning.json are explicit (rarity multipliers only document how they were
  // built from the level's common baseline), so the game applies no rarity multiplier.
  function rarityFoodMult() { return 1; }
  function rarityGrowthMult() { return 1; }
  function rarityGoldMult() { return 1; }

  /** growth seconds needed to go from `level` to level+1 (null at max) */
  function growSec(sp, level) {
    if (level >= T.maxLevel) return null;
    return sp.growSec[level - 1] * rarityGrowthMult(sp.rarity);
  }
  /** v6 (NUMBERS 2a.2): the adult hunger wait = adultHungerMultOfL3Grow (4) x the L3 grow time; it starts when the fish
   *  reaches L4 (not hungry then) and again after each full adult meal (adultHungerFrom = onReachL4_startWait_thenLastFeed).
   *  tuning.json also carries the result per species (adultHungerSec); verify.py checks the two agree. */
  function adultHungerSec(sp) {
    const k = T.adultHungerMultOfL3Grow;
    return (k ? sp.growSec[T.maxLevel - 2] * k : sp.adultHungerSec) * rarityGrowthMult(sp.rarity);
  }
  /** v6 NUMBERS 3a: death timer by rarity and by the fish's level at the moment it gets hungry:
   *  deathSecByRarity[rarity][level-1] (common / uncommon 12 / 14 / 18 / 20 h, rare 18 / 21 / 27 / 30 h).
   *  A fish hungry for its start meal right after a level-up uses its NEW level's value.
   *  Fallbacks: the species' own deathSec copy, then the global deathSec (a plain number = one timer for every level). */
  function deathSecFor(sp, level) {
    const byR = T.deathSecByRarity, d = (byR && sp && byR[sp.rarity]) || (sp && sp.deathSec) || T.deathSec;
    return Array.isArray(d) ? d[Math.max(1, Math.min(d.length, level || 1)) - 1] : d;
  }
  /** v4: food per meal by species and level (mealFood[level-1]) x rarity food multiplier, rounded up */
  function portion(sp, level) { return Math.ceil(sp.mealFood[Math.min(level, sp.mealFood.length) - 1] * rarityFoodMult(sp.rarity)); }
  /** v4: the mid-level meal comes at hungerPoints[1] (0.5) of the level; the start meal (hungerPoints[0] = 0) is at level start */
  const MID_HUNGER = T.hungerPoints ? T.hungerPoints[T.hungerPoints.length - 1] : 0.5;
  function tapsFor(food) { return Math.ceil(food / T.foodPerTap); }
  /** v6 (NUMBERS 2, rarity.sellFormula): sell = (price / 2) x fish level, integer, for every species (L1 = half the price,
   *  L4 = 2 x price). tuning.json's per-species sell tables hold the same numbers; verify.py checks they agree. */
  function sellPrice(sp, level) { return Math.floor(sp.price * level / 2 * rarityGoldMult(sp.rarity)); }
  function levelUpGold(sp, newLevel) { return Math.round(sp.levelUpGold[newLevel - 2] * rarityGoldMult(sp.rarity)); }

  function dirtStage(sec) {
    let s = 0;
    T.dirt.stageAtSec.forEach((t) => { if (sec >= t) s++; });
    return s;
  }

  // ---------------------------------------------------------------- tank XP / level
  /** XP rules come straight from TUNING.tank.xp (v3: settled, XP_SOURCE switch retired).
   *  fishLevelUp = "species.levelUpXp" -> the species' own levelUpXp table (no longer the level-up gold). */
  function xpFor(kind, ctx) {
    const v = T.tank.xp[kind];
    if (typeof v === 'number') return v;
    if (!ctx || !ctx.sp) return 0;
    if (v === 'species.levelUpXp') return ctx.sp.levelUpXp[ctx.level - 2] || 0;
    if (/^species\.feedXp/.test(v)) return ctx.sp.feedXp || 0;               // per completed meal
    if (/^species\.sellXp/.test(v)) return ctx.sp.sellXp[ctx.level - 1] || 0; // by level sold
    return 0;
  }
  /** v3: clean pay by the stage the tank was at when rubbing started (dirt.cleanGoldIndex = byStageAtCleanStart) */
  function cleanGoldFor(stage) {
    const g = T.dirt.cleanGold;
    if (Array.isArray(g)) return g[Math.max(1, Math.min(g.length, stage)) - 1];
    return g;
  }
  function tankLevelFor(xp) {
    let lv = 0;
    T.tank.levelAtXp.forEach((need) => { if (xp >= need) lv++; });
    return Math.max(1, Math.min(T.tank.maxLevel, lv));
  }
  function tankInfo() {
    const xp = S.tank.xp, level = tankLevelFor(xp), max = level >= T.tank.maxLevel;
    return { xp, level, max, cur: T.tank.levelAtXp[level - 1], next: max ? null : T.tank.levelAtXp[level] };
  }
  function addXp(n, why) {
    if (!n) return;
    const before = tankLevelFor(S.tank.xp);
    S.tank.xp += n;
    const after = tankLevelFor(S.tank.xp);
    emit('xp', { xp: n, why });
    for (let lv = before + 1; lv <= after; lv++) {
      const unlocks = T.species.filter((sp) => sp.unlockTankLevel === lv).map((sp) => sp.id);
      const cap = capacityAt(lv), prev = capacityAt(lv - 1);
      const packs = T.foodPacks.filter((p) => p.unlockTankLevel === lv);
      emit('tanklevel', { level: lv, unlocks, capacity: cap !== prev ? cap : null, extraSlots: cap - prev, packs });
    }
  }
  /** v5.1 (NUMBERS 8): tank.levelRewards { "5": {tankCapacity 8}, "8": {10}, "10": {12} }; below them tankCapacity (6) */
  function capacityAt(level) {
    let cap = T.tankCapacity;
    const r = T.tank.levelRewards || {};
    Object.keys(r).forEach((k) => { if (/^\d+$/.test(k) && +k <= level && r[k].tankCapacity) cap = Math.max(cap, r[k].tankCapacity); });
    return cap;
  }
  function capacity() { return capacityAt(tankLevelFor(S.tank.xp)); }
  function packUnlocked(p) { return tankLevelFor(S.tank.xp) >= (p.unlockTankLevel || 1); }
  function isUnlocked(sp) { return tankLevelFor(S.tank.xp) >= (sp.unlockTankLevel || 1); }

  // ---------------------------------------------------------------- state
  const SAVE_V = 4;
  /** v4 new tank (NUMBERS.md 1, 6.2, 11.2): 0 gold / 0 food / 0 diamonds, dirt clock at 12 h (stage 3, spots already
   *  there), first-clean reward armed, default decorations (placed by main.js from VISUAL.defaultDecorations). */
  function newState() {
    const nt = T.newTank || {};
    return {
      v: SAVE_V,
      gameTime: 0,
      lastSeen: Date.now(),  // wall clock (ms) of the last save; offline catch-up starts here
      gold: T.startGold,
      food: T.startFood,
      diamonds: T.startDiamonds || 0,
      speed: T.debugDefaultSpeed || 1,
      nextId: 1,
      fish: [],
      dirt: { t: nt.dirtClockStartSec || 0, spots: [], spawned: 0, grime5: 0, rubStage: 0 }, // t = game s since new tank start / last full clean; rubStage = stage when rubbing started (0 = not started)
      tank: { xp: 0 },
      firstCleanPending: !!nt.firstCleanReward, // the first full clean pays firstCleanReward instead of the stage pay
      decor: defaultDecor(), // decorations (NUMBERS v4 7, AD LANDSCAPE_LAYOUT_V4 7): [{ id, type, x, y, sh, sw, color, paid, seed }]
      starterGrantUsed: false,
      stats: { cleans: 0, feeds: 0, taps: 0, meals: 0, levelUps: 0, deaths: 0, sold: 0, removed: 0 },
    };
  }

  /** default decorations of a new tank: 3 leaves + 1 stone at the Art Director's positions (config VISUAL.defaultDecorations).
   *  x = base point as a fraction of tank width, y = base point as a fraction of the floor band (0 = sand top edge,
   *  1 = 60% down the sand band); sh / sw = height / width scale; color 0..100 (light..dark); paid = gold paid (0). */
  function defaultDecor() {
    return (CFG.VISUAL.defaultDecorations || []).map((d, i) => ({ id: 'd' + (i + 1), type: d.type, x: d.x, y: d.y, sh: 1, sw: 1, color: d.color, paid: 0, seed: d.seed != null ? d.seed : i * 37 + 11 }));
  }

  let S = newState();
  const listeners = [];
  // (the initial S gets its stage 3 spots below, once the helpers exist)
  function emit(type, data) { listeners.slice().forEach((fn) => fn(type, data || {})); }

  const isDead = (f) => f.state === 'DEAD';
  function living() { return S.fish.filter((f) => !isDead(f)).length; }

  function rnd(a, b) { return a + Math.random() * (b - a); }

  // ---------------------------------------------------------------- simulation
  /** advance one fish by dt game seconds (handles carry-over across state changes) */
  function tickFish(f, dt) {
    const sp = SPECIES[f.sp];
    let guard = 0;
    while (dt > 1e-9 && guard++ < 20) {
      if (f.state === 'WAITING' || f.state === 'DEAD') return; // WAITING (pre-v6 saves only; load() converts it): never hungry, never dies
      f.sinceFed += dt;
      if (f.state === 'GROWING') {
        const need = growSec(sp, f.level);
        const hungerAt = need * MID_HUNGER; // mid-level meal
        if (!f.hungerDone && f.progress + dt >= hungerAt) {
          dt -= Math.max(0, hungerAt - f.progress);
          f.sinceFed -= dt; // re-added by the next loop iteration
          f.progress = hungerAt;
          f.hungerDone = true;
          f.state = 'HUNGRY';
          f.fed = 0;
          f.deathLeft = deathSecFor(sp, f.level);
          emit('hungry', { fish: f });
          continue;
        }
        if (f.progress + dt >= need) {
          dt -= need - f.progress;
          f.sinceFed -= dt;
          levelUp(f);
          continue;
        }
        f.progress += dt; dt = 0;
      } else if (f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY') {
        if (dt >= f.deathLeft) { f.deathLeft = 0; die(f); return; }
        f.deathLeft -= dt; dt = 0;
      } else if (f.state === 'ADULT') {
        const every = adultHungerSec(sp);
        if (f.sinceFed >= every) {
          const over = f.sinceFed - every;
          f.sinceFed = every;
          f.state = 'ADULT_HUNGRY';
          f.fed = 0;
          f.deathLeft = deathSecFor(sp, f.level);
          emit('hungry', { fish: f });
          dt = over;
          f.sinceFed -= dt;
          continue;
        }
        dt = 0;
      } else return;
    }
  }

  /** v6 (NUMBERS 3.3-3.4): at 100% the fish goes up a level and pays level-up gold + XP. At L2 / L3 it is immediately
   *  hungry for that level's start meal with the death timer running. At L4 it is NOT hungry: the adult hunger wait
   *  (adultHungerSec, 4 x L3 grow) starts now and no death timer runs until it ends. */
  function levelUp(f) {
    const sp = SPECIES[f.sp];
    f.level++;
    f.progress = 0;
    f.hungerDone = false; // the mid meal of the new level is still ahead
    const g = levelUpGold(sp, f.level);
    S.gold += g;
    S.stats.levelUps++;
    const adult = f.level >= T.maxLevel;
    f.state = adult ? 'ADULT' : 'HUNGRY';
    f.fed = 0;
    f.deathLeft = adult ? null : deathSecFor(sp, f.level);
    f.sinceFed = 0;
    const xp = xpFor('fishLevelUp', { sp, level: f.level });
    emit('levelup', { fish: f, gold: g, xp });
    addXp(xp, 'levelup');
    if (!adult) emit('hungry', { fish: f, start: true });
  }

  /** v2: a dead fish stays in the tank (belly-up) until removed; part-eaten food is lost */
  function die(f) {
    f.state = 'DEAD';
    f.fed = 0;
    f.deathLeft = null;
    f.diedAt = S.gameTime;
    S.stats.deaths++;
    emit('death', { fish: f });
  }

  /** dirt: time since new tank / last full clean, whatever is in the tank, plus mealAddsSec per completed meal (v4 4.5).
   *  Spots are spawned stage by stage, so a jump over a stage line (new tank at 12 h, a meal's +5 min) still gives
   *  each stage's own spots. */
  function tickDirt(dt) {
    const before = dirtStage(S.dirt.t);
    S.dirt.t += dt;
    const st = dirtStage(S.dirt.t);
    for (let k = 1; k <= st; k++) { const target = T.dirt.spots[k - 1]; while (S.dirt.spawned < target) spawnSpot(k); }
    if (st >= 5 && !S.dirt.grime5) S.dirt.grime5 = totalGrime(); // film fades against this
    if (st !== before) emit('dirtstage', { stage: st });
  }
  /** seconds of game time until the next dirt stage (null at the last stage) */
  function dirtNextIn() {
    const at = T.dirt.stageAtSec, st = dirtStage(S.dirt.t);
    return st >= at.length ? null : at[st] - S.dirt.t;
  }
  function totalGrime() { return S.dirt.spots.reduce((a, s) => a + Math.max(0, s.grime), 0); }
  /** stage 5 film strength 0..1: grime left / grime when stage 5 started (0 below stage 5 and once clean) */
  function dirtFilm() {
    if (!T.dirt.stage5Film || dirtStage(S.dirt.t) < 5 || !S.dirt.spots.length) return 0;
    return S.dirt.grime5 > 0 ? Math.min(1, totalGrime() / S.dirt.grime5) : 1;
  }

  function spawnSpot(stage) {
    const grime = T.dirt.rubPxPerSpot[stage - 1];
    const V = CFG.VISUAL, look = V.dirtStages[stage - 1];
    const r = rnd(look.r[0], look.r[1]);
    // positions normalized to the tank (0..1); avoid the very edges. Visual placement only.
    let x, y, over = null;
    const older = S.dirt.spots;
    if (stage >= 2 && older.length && Math.random() < V.dirtOverlapChance) {
      // overlap an older spot: centre within dirtOverlapEdgeFrac x its radius of its edge (px, aspect-correct)
      const o = older[Math.floor(Math.random() * older.length)];
      const sz = (root.AQ && root.AQ.size) ? root.AQ.size() : { W: 752, H: 302, waterH: 281 };
      for (let i = 0; i < 12; i++) {
        const th = Math.random() * Math.PI * 2;
        const d = o.r * rnd(1 - V.dirtOverlapEdgeFrac, 1 + V.dirtOverlapEdgeFrac); // in water heights
        x = o.x + Math.cos(th) * d * sz.waterH / sz.W; y = o.y + Math.sin(th) * d * sz.waterH / sz.H;
        if (x > 0.08 && x < 0.92 && y > 0.08 && y < 0.8) { over = o.id; break; }
      }
    }
    if (over === null) {
      let tries = 0;
      do {
        x = rnd(0.14, 0.86); y = rnd(0.14, 0.78); tries++;
      } while (tries < 20 && older.some((s) => Math.hypot((s.x - x) * 2.5, s.y - y) < 0.3)); // landscape tank (about 2.5:1)
    }
    S.dirt.spots.push({ id: S.nextId++, x, y, r, grime, grime0: grime, stage, seed: Math.random() * 1000, over });
    S.dirt.spawned++;
  }

  function cheapestBaby() { return Math.min(...Object.values(SPECIES).map((sp) => sp.price)); }
  /** Producer ruling: after the one-time top-up is spent, a wipe-out (no LIVING fish, gold < cheapest baby) ends the run. */
  function tankOver() { return S.starterGrantUsed && living() === 0 && S.gold < cheapestBaby(); }

  function checkStarterGrant() {
    // NUMBERS.md 9.4: one-time top-up to 20 gold when no LIVING fish and gold < cheapest baby. Food ignored.
    // v4 11.3: the first-clean reward is separate and comes first, so no grant while it's still pending.
    if (!S.starterGrantUsed && !S.firstCleanPending && living() === 0 && S.gold < cheapestBaby()) { S.gold = T.starterGrant.topUpGoldTo; S.starterGrantUsed = T.starterGrant.oneTime; emit('grant', { gold: S.gold }); }
  }

  /** advance the game by dtGame seconds (already multiplied by speed). Order per step: growth, hunger, death, then dirt. */
  function tick(dtGame) {
    let left = Math.max(0, dtGame);
    while (left > 0) {
      const dt = Math.min(1, left); // 1 s chunks keep ordering sane during catch-up
      left -= dt;
      S.gameTime += dt;
      S.fish.slice().forEach((f) => tickFish(f, dt));
      tickDirt(dt);
    }
    checkStarterGrant();
  }

  /** replay dtGame seconds and summarise what happened (offline catch-up, NUMBERS.md 9.2) */
  function catchUp(dtGame) {
    const sec = Math.max(0, Math.min(CFG.OFFLINE_CAP_SEC, dtGame || 0));
    const ev = { level: new Map(), died: [], tank: [], gold0: S.gold, stage0: dirtStage(S.dirt.t) };
    const rec = (type, d) => {
      if (type === 'levelup') ev.level.set(d.fish.id, d.fish);
      else if (type === 'death') { ev.died.push(d.fish); ev.level.delete(d.fish.id); }
      else if (type === 'tanklevel') ev.tank.push(d);
    };
    listeners.unshift(rec);
    try { tick(sec); } finally { listeners.splice(listeners.indexOf(rec), 1); }
    const lines = [];
    ev.level.forEach((f) => lines.push(`${SPECIES[f.sp].name} reached L${f.level}${f.level >= T.maxLevel ? ' (adult)' : ''}`));
    ev.died.forEach((f) => lines.push(`${SPECIES[f.sp].name} died`));
    ev.tank.forEach((t) => lines.push(`aquarium level ${t.level}` + (t.unlocks.length ? `: ${t.unlocks.map((id) => SPECIES[id].name).join(', ')} unlocked` : t.extraSlots ? `: room for ${t.extraSlots} more fish` : '')));
    const hungry = S.fish.filter((f) => f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY');
    if (hungry.length) lines.push(`${hungry.map((f) => SPECIES[f.sp].name).join(', ')} ${hungry.length > 1 ? 'are' : 'is'} hungry`);
    const st = dirtStage(S.dirt.t);
    if (st > 0) lines.push(`tank is at dirt stage ${st}`); // v4 11.1: dirt only when dirty, never "clean"; no lines = no window
    const gold = S.gold - ev.gold0;
    if (gold > 0) lines.push(`+${gold} gold`);
    return { sec, lines, text: 'While you were away: ' + lines.join(', '), died: ev.died.length, stage: st };
  }

  /** offline progress: replay the wall-clock time since the last save at the saved speed (clock backwards = 0, cap 7 days) */
  function resume(nowMs) {
    if (!T.offlineProgress) return null;
    let away = ((nowMs || Date.now()) - (S.lastSeen || 0)) / 1000;
    if (!(away > 0)) away = 0;
    const game = Math.min(CFG.OFFLINE_CAP_SEC, away * (S.speed || 1));
    S.lastSeen = nowMs || Date.now();
    if (game <= 0) return null;
    const r = catchUp(game);
    r.realSec = away;
    return r;
  }

  // ---------------------------------------------------------------- actions
  function canBuy(id) {
    const sp = SPECIES[id];
    if (!sp) return { ok: false, reason: 'Unknown species' };
    if (!isUnlocked(sp)) return { ok: false, reason: `Aquarium level ${sp.unlockTankLevel}`, locked: true };
    if (S.fish.length >= capacity()) return { ok: false, reason: 'Tank full' }; // dead fish take a slot until removed
    if (S.gold < sp.price) return { ok: false, reason: 'Not enough gold' };
    return { ok: true };
  }

  function buyFish(id) {
    const c = canBuy(id);
    if (!c.ok) { emit('msg', { text: c.reason }); return null; }
    const sp = SPECIES[id];
    S.gold -= sp.price;
    const f = {
      // v6 (NUMBERS 3.1): a new baby grows from 0% at once, not hungry, no start meal; first hunger = the L1 mid meal at 50%
      id: S.nextId++, sp: id, level: 1, state: 'GROWING', progress: 0, hungerDone: false,
      deathLeft: null, sinceFed: 0, fed: 0, boughtAt: S.gameTime,
      x: rnd(0.2, 0.8), y: rnd(0.25, 0.6),
    };
    S.fish.push(f);
    emit('bought', { fish: f });
    return f;
  }

  /** food packs are bought in the shop's Food category (v6 foodPacks: 5 for 2, 10 for 5, 50 for 25, 250 for 125 from tank Lv6) */
  function buyFood(i) {
    const p = T.foodPacks[i || 0];
    if (!p) return false;
    if (!packUnlocked(p)) { emit('msg', { text: `Aquarium level ${p.unlockTankLevel} needed` }); return false; }
    if (S.gold < p.gold) { emit('msg', { text: 'Not enough gold for food' }); return false; }
    S.gold -= p.gold; S.food += p.food;
    emit('foodbought', { food: p.food, gold: p.gold });
    return true;
  }

  function needsFood(f) { return f.state === 'WAITING' || f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY'; }

  /** Food tool tap (NUMBERS.md 3): one tap gives foodPerTap food to the nearest fish that still needs food.
   *  (nx, ny) = tap point in tank-normalised coords; W, H scale them to px for the distance. */
  function feedTap(nx, ny, W, H) {
    W = W || 1; H = H || 1;
    if (dirtStage(S.dirt.t) >= 1) { const r = { ok: false, reason: 'dirty' }; emit('feedblocked', r); return r; }
    const eaters = S.fish.filter(needsFood);
    if (!eaters.length) { const r = { ok: false, reason: 'nobodyhungry' }; emit('feedfail', r); return r; }
    if (S.food <= 0) { const r = { ok: false, reason: 'nofood' }; emit('feedfail', r); return r; }
    const dl = (f) => (f.state === 'WAITING' ? Infinity : f.deathLeft);
    let best = null, bestD = Infinity;
    const px = (nx == null ? 0.5 : nx) * W, py = (ny == null ? 0.5 : ny) * H;
    for (const f of eaters) {
      const d = Math.hypot(f.x * W - px, f.y * H - py);
      if (d < bestD - 1e-6 || (Math.abs(d - bestD) <= 1e-6 && dl(f) < dl(best))) { best = f; bestD = d; }
    }
    const f = best, sp = SPECIES[f.sp], need = portion(sp, f.level);
    const give = Math.min(T.foodPerTap, S.food);
    S.food -= give; f.fed = (f.fed || 0) + give;
    S.stats.taps++;
    let gold = 0;
    const full = f.fed >= need;
    if (full) {
      if (f.state === 'WAITING') { f.state = 'GROWING'; f.progress = 0; f.hungerDone = false; }
      else if (f.state === 'HUNGRY') f.state = 'GROWING';
      else if (f.state === 'ADULT_HUNGRY') f.state = 'ADULT';
      f.deathLeft = null; f.sinceFed = 0; f.fed = 0;
      gold = T.feedGoldPerFish; S.gold += gold;
      S.stats.feeds++;
    }
    const r = { ok: true, fish: f, spent: give, full, gold, fed: full ? need : f.fed, need, xp: 0, dirtAdded: 0 };
    emit('tapfed', r);
    if (full) {
      // v4 4.5 / 4.6: a completed meal gives the species' feed XP and moves the dirt clock forward (partial food doesn't).
      // The meal counts fully even if that pushes the dirt to a new stage; only the next tap is blocked.
      r.xp = xpFor('feed', { sp }); S.stats.meals++;
      r.dirtAdded = T.dirt.mealAddsSec || 0;
      if (r.dirtAdded) tickDirt(r.dirtAdded);
      emit('fed', { fish: f, gold, xp: r.xp, dirtAdded: r.dirtAdded });
      addXp(r.xp, 'feed');
    }
    checkStarterGrant();
    return r;
  }

  /** Sponge rub along a segment in tank-normalized coords (x by width, y by height).
   *  W,H = tank size in CSS px (grime is measured in px of sponge travel); rBase = px per unit of spot radius (water height). */
  function rub(x0, y0, x1, y1, W, H, spongeR, rBase) {
    const stage = dirtStage(S.dirt.t);
    if (!S.dirt.spots.length) return { cleaned: false };
    const ax = x0 * W, ay = y0 * H, bx = x1 * W, by = y1 * H;
    const len = Math.hypot(bx - ax, by - ay);
    if (len <= 0) return { cleaned: false };
    let touched = false;
    const rubStage0 = S.dirt.rubStage;
    for (const s of S.dirt.spots) {
      const cx = s.x * W, cy = s.y * H, R = s.r * (rBase || W); // AD v4 6: spot radii are fractions of the water height (rBase)
      // distance from spot centre to segment
      const t = Math.max(0, Math.min(1, ((cx - ax) * (bx - ax) + (cy - ay) * (by - ay)) / (len * len)));
      const px = ax + t * (bx - ax), py = ay + t * (by - ay);
      const d = Math.hypot(cx - px, cy - py);
      if (d < R + spongeR) { s.grime -= len; touched = true; } // full drawn sponge radius counts (Playtester pass 1 note 1)
    }
    if (touched && !rubStage0) S.dirt.rubStage = stage; // first sponge contact since the last full clean
    S.dirt.spots = S.dirt.spots.filter((s) => s.grime > 0);
    if (touched && S.dirt.spots.length === 0 && stage >= 1 && S.dirt.spawned >= T.dirt.spots[stage - 1]) {
      const payStage = S.dirt.rubStage || stage;
      // v3: 2/3/4/5/6 by the stage at rub start, paid when the last spot clears.
      // v6: the first full clean of a new tank pays firstCleanReward (20 gold + 50 food) INSTEAD of the stage pay.
      const fc = S.firstCleanPending && T.newTank && T.newTank.firstCleanReward;
      const gold = fc ? fc.gold : cleanGoldFor(payStage), food = fc ? fc.food : 0;
      S.gold += gold; S.food += food;
      S.firstCleanPending = false;
      S.dirt.t = 0; S.dirt.spawned = 0; S.dirt.spots = []; S.dirt.grime5 = 0; S.dirt.rubStage = 0;
      S.stats.cleans++;
      const xp = xpFor('clean');
      emit('cleaned', { stage: payStage, stageNow: stage, gold, food, first: !!fc, xp });
      addXp(xp, 'clean');
      checkStarterGrant();
      return { cleaned: true, gold, food, first: !!fc, xp, stage: payStage, stageNow: stage };
    }
    return { cleaned: false, touched };
  }

  // ---- decorations (NUMBERS v4 7): free leaf and stone, max 12 counting the defaults, selling refunds the price paid
  function decorFull() { return S.decor.length >= T.decorations.maxInTank; }
  /** buy a decoration: base at the floor centre, or the nearest free x (no other base within 0.06 of the width) */
  function buyDecor(type) {
    const D = T.decorations;
    if (!D.types[type]) return null;
    if (decorFull()) { emit('msg', { text: 'Tank is full of decorations' }); return null; }
    const price = D.price || 0;
    if (S.gold < price) { emit('msg', { text: 'Not enough gold' }); return null; }
    let x = 0.5;
    for (let k = 0; k <= 16; k++) {
      const c = 0.5 + (k % 2 ? 1 : -1) * Math.ceil(k / 2) * 0.05;
      if (c < 0.1 || c > 0.9) continue;
      if (S.decor.every((d) => Math.abs(d.x - c) >= 0.06)) { x = c; break; }
    }
    S.gold -= price;
    const d = { id: 'd' + S.nextId++, type, x, y: 0.5, sh: D.scale.default, sw: D.scale.default, color: D.types[type].defaultColor, paid: price, seed: Math.floor(Math.random() * 1000) };
    S.decor.push(d);
    emit('decorbought', { decor: d });
    return d;
  }
  function sellDecor(id) {
    const d = S.decor.find((x) => x.id === id);
    if (!d) return null;
    S.decor = S.decor.filter((x) => x !== d);
    S.gold += d.paid || 0;
    emit('decorsold', { decor: d, gold: d.paid || 0 });
    return d.paid || 0;
  }

  function sell(fishId) {
    const f = S.fish.find((x) => x.id === fishId);
    if (!f || isDead(f)) return null; // dead fish can't be sold, only removed
    const price = sellPrice(SPECIES[f.sp], f.level);
    const xp = xpFor('sell', { sp: SPECIES[f.sp], level: f.level }); // v4 5: sell XP by species and level (0 at L1)
    S.fish = S.fish.filter((x) => x !== f);
    S.gold += price;
    S.stats.sold++;
    emit('sold', { fish: f, gold: price, xp });
    addXp(xp, 'sell');
    checkStarterGrant();
    return price;
  }

  /** remove a dead fish (0 gold, frees its tank slot) */
  function removeDead(fishId) {
    const f = S.fish.find((x) => x.id === fishId);
    if (!f || !isDead(f)) return null;
    S.fish = S.fish.filter((x) => x !== f);
    const gold = T.deadFish ? T.deadFish.removeGold : 0;
    S.gold += gold;
    S.stats.removed++;
    emit('removed', { fish: f, gold });
    return gold;
  }

  // ---------------------------------------------------------------- info for UI
  function fishInfo(f) {
    const sp = SPECIES[f.sp];
    const need = growSec(sp, f.level);
    const food = portion(sp, f.level);
    return {
      species: sp, level: f.level, state: f.state, maxLevel: T.maxLevel, dead: isDead(f),
      growNeed: need, growLeft: need != null ? need - f.progress : null,
      progressFrac: need ? f.progress / need : 1,
      deathLeft: f.deathLeft, deathTotal: deathSecFor(sp, f.level),
      sell: sellPrice(sp, f.level), sellXp: xpFor('sell', { sp, level: f.level }), portion: food,
      taps: tapsFor(food), tapsFed: tapsFor(f.fed || 0), fed: f.fed || 0,
      needLeft: needsFood(f) ? Math.max(0, food - (f.fed || 0)) : 0, // food still needed for the current meal
      needsFood: needsFood(f),
      midHungerIn: f.state === 'GROWING' && !f.hungerDone ? need * MID_HUNGER - f.progress : null,
      adultHungerIn: f.state === 'ADULT' ? adultHungerSec(sp) - f.sinceFed : null,
    };
  }

  // ---------------------------------------------------------------- save/load
  // Offline progress (v2): the save stores the wall-clock time (lastSeen); on load, main.js calls
  // resume() which replays the time away in order and returns the "while you were away" summary.
  function save(storage) {
    S.lastSeen = Date.now();
    try { (storage || root.localStorage).setItem(CFG.VISUAL.saveKey, JSON.stringify(S)); } catch (e) { /* ignore */ }
  }
  function load(storage) {
    try {
      const raw = (storage || root.localStorage).getItem(CFG.VISUAL.saveKey);
      if (!raw) return false;
      const d = JSON.parse(raw);
      if (!d || d.v !== SAVE_V) return false; // v4 rules: older saves are not loaded
      const base = newState();
      S = Object.assign(base, d);
      S.dirt = Object.assign(newState().dirt, d.dirt || {});
      S.tank = Object.assign(newState().tank, d.tank || {});
      S.stats = Object.assign(newState().stats, d.stats || {});
      S.fish = (d.fish || []).filter((f) => SPECIES[f.sp]).map((f) => Object.assign({ fed: 0 }, f));
      // v6: a pre-v6 fish still waiting for its L1 start meal starts growing from 0% (no start meal any more)
      S.fish.forEach((f) => { if (f.state === 'WAITING') { f.state = 'GROWING'; f.progress = 0; f.hungerDone = false; f.fed = 0; f.deathLeft = null; } });
      S.decor = Array.isArray(d.decor) ? d.decor.filter((x) => T.decorations.types[x.type]) : defaultDecor();
      return true;
    } catch (e) { return false; }
  }
  function reset(storage) {
    try { (storage || root.localStorage).removeItem(CFG.VISUAL.saveKey); } catch (e) { /* ignore */ }
    S = newState();
    tickDirt(0); // a new tank starts at dirt stage 3 with its spots
    emit('reset');
  }

  // ---------------------------------------------------------------- balance checks (NUMBERS.md v6 section 10)
  /** Designer's required checks:
   *  (a) cleaning at stage 1 earns the most gold per day (cleanGold[n] * 24 h / stage n time), never rising with the stage (v6.1: 32/32/24/16/10);
   *  (b) v6: per species, selling at L4 is a profit and beats selling at L3 (L3 may now show a profit: sell = 1.5 x price).
   *      profit(L) = sell(L) + level-up gold up to L - price - food eaten up to L. Food eaten before selling at L = the meals
   *      of every finished level: L1 mid only (no start meal since v6), then start + mid of L2 and L3 (5 meals to L4).
   *      Food is valued at 0.5 gold (the dearest pack per food, as in NUMBERS 10); noFood = the same without food. */
  function mealsBefore(lv) { return lv <= 1 ? [0.5] : T.hungerPoints || [0, 0.5]; } // v6: L1 has only the mid meal
  function balanceChecks() {
    const L = T.maxLevel, foodVal = Math.max(...T.foodPacks.map((p) => p.gold / p.food));
    const sell = T.species.map((sp) => {
      const rows = [];
      let lvlGold = 0, food = 0, feeds = 0, time = 0;
      for (let lv = 1; lv <= L; lv++) {
        if (lv > 1) { const n = mealsBefore(lv - 1).length; lvlGold += levelUpGold(sp, lv); time += growSec(sp, lv - 1); food += n * portion(sp, lv - 1); feeds += n; }
        const noFood = sellPrice(sp, lv) + lvlGold - sp.price;
        const profit = noFood + feeds * T.feedGoldPerFish - food * foodVal;
        rows.push({ level: lv, profit: +profit.toFixed(2), noFood, food, meals: feeds, hours: time / 3600 });
      }
      const adult = rows[L - 1], l3 = rows[L - 2];
      return { species: sp.name, rows, l4perHour: +(adult.profit / adult.hours).toFixed(1),
        ok: adult.profit > 0 && adult.profit > l3.profit };
    });
    const cleanPerDay = T.dirt.stageAtSec.map((t, i) => +(cleanGoldFor(i + 1) * 86400 / t).toFixed(2));
    // v6.1 (NUMBERS 6.5): 32 / 32 / 24 / 16 / 10 a day; cleaning early never pays less (stages 1 and 2 tie), stage 1 pays the most
    const cleanOk = cleanPerDay.every((v, i) => i === 0 || v <= cleanPerDay[i - 1]) && cleanPerDay[0] === Math.max(...cleanPerDay) && cleanPerDay[0] > cleanPerDay[cleanPerDay.length - 1];
    return { sell, sellOk: sell.every((o) => o.ok), cleanPerDay, cleanOk, cleanRatio: +(cleanPerDay[0] / cleanPerDay[cleanPerDay.length - 1]).toFixed(2) };
  }

  tickDirt(0); // the initial new tank starts at dirt stage 3 with its spots (a loaded save replaces S)

  root.Game = {
    CFG, T, SPECIES,
    get state() { return S; },
    on(fn) { listeners.push(fn); },
    tick, catchUp, resume, buyFish, buyFood, packUnlocked, capacityAt, feedTap, rub, sell, removeDead, canBuy, isUnlocked, buyDecor, sellDecor, decorFull,
    dirtStage: () => dirtStage(S.dirt.t), dirtStageAt: dirtStage, dirtFilm, dirtNextIn, tickDirt,
    fishInfo, portion, tapsFor, sellPrice, growSec, deathSecFor, adultHungerSec, needsFood, MID_HUNGER,
    tankInfo, tankLevelFor, xpFor, cleanGoldFor, levelUpGold, capacity,
    /** debug +50 XP button (NUMBERS.md 9.13): the normal XP path (addXp), so tank level-ups/unlock toasts/saves behave as in play; no gold */
    debugAddXp(n) { addXp(n, 'debug'); return tankInfo(); },
    save, load, reset, newState, balanceChecks, living, tankOver,
  };
})(typeof window !== 'undefined' ? window : globalThis);
