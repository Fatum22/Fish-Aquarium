/* Aquarium game logic (Designer v2, slow game): state, simulation, actions, offline catch-up, save/load.
 * No DOM here. All balance numbers come from window.AQUARIUM_CONFIG.TUNING (config.js = tuning.json).
 */
(function (root) {
  'use strict';
  const CFG = root.AQUARIUM_CONFIG;
  const T = CFG.TUNING;
  const SPECIES = {};
  T.species.forEach((s) => { SPECIES[s.id] = s; });

  // ---------------------------------------------------------------- helpers
  function rarityFoodMult(r) {
    if (T.rarityFoodMult && T.rarityFoodMult[r] != null) return T.rarityFoodMult[r];
    return (CFG.RARITY_LATER[r] || { foodMult: 1 }).foodMult;
  }
  function rarityGrowthMult(r) { return r === 'common' ? 1 : (CFG.RARITY_LATER[r] || { growthMult: 1 }).growthMult; }
  function rarityGoldMult(r) { return r === 'common' ? 1 : (CFG.RARITY_LATER[r] || { goldMult: 1 }).goldMult; }

  /** growth seconds needed to go from `level` to level+1 (null at max) */
  function growSec(sp, level) {
    if (level >= T.maxLevel) return null;
    return sp.growSec[level - 1] * rarityGrowthMult(sp.rarity);
  }
  /** adult: hungry this long after reaching L4, then after each full feed (adultHungerFrom = reachL4ThenLastFeed) */
  function adultHungerSec(sp) { return sp.adultHungerSec * rarityGrowthMult(sp.rarity); }
  /** v2: one death timer for every species and level (NUMBERS.md 1a DEATH_SEC) */
  function deathSecFor() { return T.deathSec; }
  function portion(sp, level) { return Math.ceil(sp.foodBase * level * rarityFoodMult(sp.rarity)); }
  function tapsFor(food) { return Math.ceil(food / T.foodPerTap); }
  function sellPrice(sp, level) { return Math.round(sp.sell[level - 1] * rarityGoldMult(sp.rarity)); }
  function levelUpGold(sp, newLevel) { return Math.round(sp.levelUpGold[newLevel - 2] * rarityGoldMult(sp.rarity)); }

  function dirtStage(sec) {
    let s = 0;
    T.dirt.stageAtSec.forEach((t) => { if (sec >= t) s++; });
    return s;
  }

  // ---------------------------------------------------------------- tank XP / level
  /** XP rules: TUNING.tank.xp unless config.js XP_SOURCE picks one of XP_PRESETS (Maksims' open question) */
  function xpRules() { return (CFG.XP_SOURCE && CFG.XP_SOURCE !== 'designer' && CFG.XP_PRESETS[CFG.XP_SOURCE]) || T.tank.xp; }
  function xpFor(kind, gold) {
    const v = xpRules()[kind];
    if (typeof v === 'number') return v;
    if (typeof v === 'string' && v.indexOf('equals') === 0) return gold || 0; // "equalsLevelUpGold" / "equalsSellGold"
    return 0;
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
      emit('tanklevel', { level: lv, unlocks, decorations: lv >= T.tank.maxLevel });
    }
  }
  function isUnlocked(sp) { return tankLevelFor(S.tank.xp) >= (sp.unlockTankLevel || 1); }

  // ---------------------------------------------------------------- state
  function newState() {
    return {
      v: 2,
      gameTime: 0,
      lastSeen: Date.now(),  // wall clock (ms) of the last save; offline catch-up starts here
      gold: T.startGold,
      food: T.startFood,
      speed: T.debugDefaultSpeed || 1,
      nextId: 1,
      fish: [],
      dirt: { t: 0, spots: [], spawned: 0, grime5: 0 }, // t = game seconds since new tank / last full clean
      tank: { xp: 0 },
      starterGrantUsed: false,
      stats: { cleans: 0, feeds: 0, taps: 0, levelUps: 0, deaths: 0, sold: 0, removed: 0 },
    };
  }

  let S = newState();
  const listeners = [];
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
      if (f.state === 'WAITING' || f.state === 'DEAD') return; // WAITING: never hungry, never dies (rule 7)
      f.sinceFed += dt;
      if (f.state === 'GROWING') {
        const need = growSec(sp, f.level);
        const hungerAt = need * T.hungerPoint;
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

  function levelUp(f) {
    const sp = SPECIES[f.sp];
    f.level++;
    f.progress = 0;
    f.hungerDone = false;
    const g = levelUpGold(sp, f.level);
    S.gold += g;
    S.stats.levelUps++;
    f.state = f.level >= T.maxLevel ? 'ADULT' : 'GROWING';
    if (f.state === 'ADULT') f.sinceFed = 0; // first adult hunger counts from reaching L4
    const xp = xpFor('fishLevelUp', g);
    emit('levelup', { fish: f, gold: g, xp });
    addXp(xp, 'levelup');
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

  /** v2 dirt: purely time since new tank / last full clean, whatever is in the tank (NUMBERS.md 1e) */
  function tickDirt(dt) {
    const before = dirtStage(S.dirt.t);
    S.dirt.t += dt;
    const st = dirtStage(S.dirt.t);
    if (st > 0) {
      const target = T.dirt.spots[st - 1];
      while (S.dirt.spawned < target) spawnSpot(st);
      if (st >= 5 && !S.dirt.grime5) S.dirt.grime5 = totalGrime(); // film fades against this
    }
    if (st !== before) emit('dirtstage', { stage: st });
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
      const asp = (root.AQ && root.AQ.size) ? root.AQ.size() : { W: 1, H: 1.4 };
      for (let i = 0; i < 12; i++) {
        const th = Math.random() * Math.PI * 2;
        const d = o.r * rnd(1 - V.dirtOverlapEdgeFrac, 1 + V.dirtOverlapEdgeFrac); // in tank widths
        x = o.x + Math.cos(th) * d; y = o.y + Math.sin(th) * d * asp.W / asp.H;
        if (x > 0.08 && x < 0.92 && y > 0.08 && y < 0.8) { over = o.id; break; }
      }
    }
    if (over === null) {
      let tries = 0;
      do {
        x = rnd(0.14, 0.86); y = rnd(0.14, 0.78); tries++;
      } while (tries < 20 && older.some((s) => Math.hypot(s.x - x, (s.y - y) * 1.3) < 0.2));
    }
    S.dirt.spots.push({ id: S.nextId++, x, y, r, grime, grime0: grime, stage, seed: Math.random() * 1000, over });
    S.dirt.spawned++;
  }

  function cheapestBaby() { return Math.min(...Object.values(SPECIES).map((sp) => sp.price)); }
  /** Producer ruling: after the one-time top-up is spent, a wipe-out (no LIVING fish, gold < cheapest baby) ends the run. */
  function tankOver() { return S.starterGrantUsed && living() === 0 && S.gold < cheapestBaby(); }

  function checkStarterGrant() {
    // NUMBERS.md 9.4: one-time top-up to 20 gold when no LIVING fish and gold < cheapest baby. Food ignored.
    if (!S.starterGrantUsed && living() === 0 && S.gold < cheapestBaby()) { S.gold = T.starterGrant.topUpGoldTo; S.starterGrantUsed = T.starterGrant.oneTime; emit('grant', { gold: S.gold }); }
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
    ev.tank.forEach((t) => lines.push(`tank level ${t.level}` + (t.unlocks.length ? `: ${t.unlocks.map((id) => SPECIES[id].name).join(', ')} unlocked` : t.decorations ? ': decorations coming soon' : '')));
    const hungry = S.fish.filter((f) => f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY');
    if (hungry.length) lines.push(`${hungry.map((f) => SPECIES[f.sp].name).join(', ')} ${hungry.length > 1 ? 'are' : 'is'} hungry`);
    const st = dirtStage(S.dirt.t);
    lines.push(st > 0 ? `tank is at dirt stage ${st}` : 'tank is clean');
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
    if (!isUnlocked(sp)) return { ok: false, reason: `Tank level ${sp.unlockTankLevel}`, locked: true };
    if (S.fish.length >= T.tankCapacity) return { ok: false, reason: 'Tank full' }; // dead fish take a slot until removed
    if (S.gold < sp.price) return { ok: false, reason: 'Not enough gold' };
    return { ok: true };
  }

  function buyFish(id) {
    const c = canBuy(id);
    if (!c.ok) { emit('msg', { text: c.reason }); return null; }
    const sp = SPECIES[id];
    S.gold -= sp.price;
    const f = {
      id: S.nextId++, sp: id, level: 1, state: 'WAITING', progress: 0, hungerDone: false,
      deathLeft: null, sinceFed: 0, fed: 0, boughtAt: S.gameTime,
      x: rnd(0.2, 0.8), y: rnd(0.25, 0.6),
    };
    S.fish.push(f);
    emit('bought', { fish: f });
    return f;
  }

  function buyFood() {
    const p = T.foodPack;
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
      addXp(xpFor('feed', gold), 'feed');
    }
    const r = { ok: true, fish: f, spent: give, full, gold, fed: full ? need : f.fed, need };
    emit('tapfed', r);
    if (full) emit('fed', { fish: f, gold });
    checkStarterGrant();
    return r;
  }

  /** Sponge rub along a segment in tank-normalized coords (x by width, y by height).
   *  W,H = tank size in CSS px (grime is measured in px of sponge travel). */
  function rub(x0, y0, x1, y1, W, H, spongeR) {
    const stage = dirtStage(S.dirt.t);
    if (!S.dirt.spots.length) return { cleaned: false };
    const ax = x0 * W, ay = y0 * H, bx = x1 * W, by = y1 * H;
    const len = Math.hypot(bx - ax, by - ay);
    if (len <= 0) return { cleaned: false };
    let touched = false;
    for (const s of S.dirt.spots) {
      const cx = s.x * W, cy = s.y * H, R = s.r * W;
      // distance from spot centre to segment
      const t = Math.max(0, Math.min(1, ((cx - ax) * (bx - ax) + (cy - ay) * (by - ay)) / (len * len)));
      const px = ax + t * (bx - ax), py = ay + t * (by - ay);
      const d = Math.hypot(cx - px, cy - py);
      if (d < R + spongeR) { s.grime -= len; touched = true; } // full drawn sponge radius counts (Playtester pass 1 note 1)
    }
    S.dirt.spots = S.dirt.spots.filter((s) => s.grime > 0);
    if (touched && S.dirt.spots.length === 0 && stage >= 1 && S.dirt.spawned >= T.dirt.spots[stage - 1]) {
      const gold = T.dirt.cleanGold; // v2: every full clean pays the same, whatever the stage
      S.gold += gold;
      S.dirt.t = 0; S.dirt.spawned = 0; S.dirt.spots = []; S.dirt.grime5 = 0;
      S.stats.cleans++;
      const xp = xpFor('clean', gold);
      emit('cleaned', { stage, gold, xp });
      addXp(xp, 'clean');
      return { cleaned: true, gold, xp, stage };
    }
    return { cleaned: false, touched };
  }

  function sell(fishId) {
    const f = S.fish.find((x) => x.id === fishId);
    if (!f || isDead(f)) return null; // dead fish can't be sold, only removed
    const price = sellPrice(SPECIES[f.sp], f.level);
    S.fish = S.fish.filter((x) => x !== f);
    S.gold += price;
    S.stats.sold++;
    emit('sold', { fish: f, gold: price });
    addXp(xpFor('sell', price), 'sell');
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
      sell: sellPrice(sp, f.level), portion: food,
      taps: tapsFor(food), tapsFed: tapsFor(f.fed || 0), fed: f.fed || 0,
      needsFood: needsFood(f),
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
      if (!d || d.v !== 2) return false;
      const base = newState();
      S = Object.assign(base, d);
      S.dirt = Object.assign(newState().dirt, d.dirt || {});
      S.tank = Object.assign(newState().tank, d.tank || {});
      S.stats = Object.assign(newState().stats, d.stats || {});
      S.fish = (d.fish || []).filter((f) => SPECIES[f.sp]).map((f) => Object.assign({ fed: 0 }, f));
      return true;
    } catch (e) { return false; }
  }
  function reset(storage) {
    try { (storage || root.localStorage).removeItem(CFG.VISUAL.saveKey); } catch (e) { /* ignore */ }
    S = newState();
    emit('reset');
  }

  // ---------------------------------------------------------------- balance checks (NUMBERS.md v2 sections 4, 5)
  function balanceChecks() {
    const out = [];
    const L = T.maxLevel;
    T.species.forEach((sp) => {
      // ideal play, food valued at foodPack.gold/foodPack.food per unit
      const foodVal = T.foodPack.gold / T.foodPack.food;
      const route = (sellAt) => {
        let gold = -sp.price, time = 0, feeds = 1, food = portion(sp, 1);
        for (let lv = 1; lv < sellAt; lv++) {
          time += growSec(sp, lv);
          feeds++; food += portion(sp, lv);
          gold += levelUpGold(sp, lv + 1);
        }
        // a fish sold at level N was fed at: first feed + hunger in L1..L(N-1)
        gold += feeds * T.feedGoldPerFish - food * foodVal + sellPrice(sp, sellAt);
        return { gold, time, perHour: gold / (time / 3600) };
      };
      const r3 = route(L - 1), r4 = route(L);
      out.push({ species: sp.name, sellL3perHour: +r3.perHour.toFixed(1), sellL4perHour: +r4.perHour.toFixed(1), l3gold: r3.gold, l4gold: r4.gold, ok: r4.perHour > r3.perHour });
    });
    const cleanPerDay = T.dirt.stageAtSec.map((t) => +(T.dirt.cleanGold * 86400 / t).toFixed(1));
    const cleanOk = cleanPerDay.every((v, i) => i === 0 || v < cleanPerDay[i - 1]);
    return { sell: out, sellOk: out.every((o) => o.ok), cleanPerDay, cleanOk, cleanRatio: +(cleanPerDay[0] / cleanPerDay[cleanPerDay.length - 1]).toFixed(2) };
  }

  root.Game = {
    CFG, T, SPECIES,
    get state() { return S; },
    on(fn) { listeners.push(fn); },
    tick, catchUp, resume, buyFish, buyFood, feedTap, rub, sell, removeDead, canBuy, isUnlocked,
    dirtStage: () => dirtStage(S.dirt.t), dirtStageAt: dirtStage, dirtFilm,
    fishInfo, portion, tapsFor, sellPrice, growSec, deathSecFor, adultHungerSec, needsFood,
    tankInfo, tankLevelFor, xpFor,
    save, load, reset, newState, balanceChecks, living, tankOver,
  };
})(typeof window !== 'undefined' ? window : globalThis);
