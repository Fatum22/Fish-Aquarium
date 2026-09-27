/* Aquarium game logic: state, simulation, actions, save/load. No DOM here.
 * All balance numbers come from window.AQUARIUM_CONFIG.TUNING (config.js).
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
  /** adult: hungry this long after reaching L4, then after each adult feed (tuning adultHungerFrom = reachL4ThenLastFeed) */
  function adultHungerSec(sp) { return sp.adultHungerSec * rarityGrowthMult(sp.rarity); }
  function deathSecFor(sp, level) {
    const base = level >= T.maxLevel ? adultHungerSec(sp) : growSec(sp, level);
    return T.deathMult * base;
  }
  function portion(sp, level) { return Math.ceil(sp.foodBase * level * rarityFoodMult(sp.rarity)); }
  function sellPrice(sp, level) { return Math.round(sp.sell[level - 1] * rarityGoldMult(sp.rarity)); }
  function levelUpGold(sp, newLevel) { return Math.round(sp.levelUpGold[newLevel - 2] * rarityGoldMult(sp.rarity)); }

  function dirtStage(elapsed) {
    let s = 0;
    T.dirt.stageAtSec.forEach((t) => { if (elapsed >= t) s++; });
    return s;
  }

  // ---------------------------------------------------------------- state
  function newState() {
    return {
      v: 1,
      gameTime: 0,
      gold: T.startGold,
      food: T.startFood,
      speed: 1,
      nextId: 1,
      fish: [],
      dirt: { elapsed: 0, spots: [], spawned: 0 },
      starterGrantUsed: false,
      stats: { cleans: 0, feeds: 0, levelUps: 0, deaths: 0, sold: 0 },
    };
  }

  let S = newState();
  const listeners = [];
  function emit(type, data) { listeners.forEach((fn) => fn(type, data || {})); }

  function living() { return S.fish.length; }

  // Seeded-ish random for spot shapes
  function rnd(a, b) { return a + Math.random() * (b - a); }

  // ---------------------------------------------------------------- simulation
  /** advance one fish by dt game seconds (handles carry-over across state changes) */
  function tickFish(f, dt) {
    const sp = SPECIES[f.sp];
    let guard = 0;
    while (dt > 1e-9 && guard++ < 20) {
      if (f.state === 'WAITING') return; // decision (1): never hungry, never dies before first feed
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
        f.deathLeft -= dt; dt = 0;
        if (f.deathLeft <= 0) { die(f); return; }
      } else if (f.state === 'ADULT') {
        const every = adultHungerSec(sp);
        if (f.sinceFed >= every) {
          const over = f.sinceFed - every;
          f.sinceFed = every;
          f.state = 'ADULT_HUNGRY';
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
    if (f.state === 'ADULT') f.sinceFed = 0; // first adult hunger counts from reaching L4 (NUMBERS.md 1c/step 5)
    emit('levelup', { fish: f, gold: g });
  }

  function die(f) {
    S.fish = S.fish.filter((x) => x !== f);
    S.stats.deaths++;
    emit('death', { fish: f });
  }

  function tickDirt(dt) {
    if (living() === 0) return; // with 0 fish, dirt does not build up
    const before = dirtStage(S.dirt.elapsed);
    S.dirt.elapsed += dt;
    const st = dirtStage(S.dirt.elapsed);
    if (st > 0) {
      const target = T.dirt.spots[st - 1];
      while (S.dirt.spawned < target) spawnSpot(st);
    }
    if (st !== before) emit('dirtstage', { stage: st });
  }

  function spawnSpot(stage) {
    const grime = T.dirt.rubPxPerSpot[stage - 1];
    const [r0, r1] = CFG.VISUAL.spotRadiusFrac;
    // positions normalized to the tank (0..1); avoid the very edges
    let x, y, tries = 0;
    do {
      x = rnd(0.14, 0.86); y = rnd(0.14, 0.78); tries++;
    } while (tries < 20 && S.dirt.spots.some((s) => Math.hypot(s.x - x, (s.y - y) * 1.3) < 0.2));
    S.dirt.spots.push({ id: S.nextId++, x, y, r: rnd(r0, r1), grime, grime0: grime, stage, seed: Math.random() * 1000 });
    S.dirt.spawned++;
  }

  function cheapestBaby() { return Math.min(...Object.values(SPECIES).map((sp) => sp.price)); }
  /** Producer ruling: after the one-time top-up is spent, a second wipe-out ends the run ("Start new tank"). */
  function tankOver() { return S.starterGrantUsed && living() === 0 && S.gold < cheapestBaby(); }

  function checkStarterGrant() {
    // EDGE CASE 5 (pending Maksims' veto; Producer ruling 2026-09-27): one-time 20g top-up when no living fish and gold < cheapest baby. Food ignored.
    if (!S.starterGrantUsed && living() === 0 && S.gold < cheapestBaby()) { S.gold = T.starterGrant.topUpGoldTo; S.starterGrantUsed = T.starterGrant.oneTime; emit('grant', { gold: S.gold }); }
  }

  /** advance the game by dtGame seconds (already multiplied by speed) */
  function tick(dtGame) {
    let left = Math.max(0, dtGame);
    while (left > 0) {
      const dt = Math.min(1, left); // 1 s chunks keep ordering sane during catch-up
      left -= dt;
      S.gameTime += dt;
      tickDirt(dt);
      S.fish.slice().forEach((f) => tickFish(f, dt));
    }
    checkStarterGrant();
  }

  // ---------------------------------------------------------------- actions
  function canBuy(id) {
    const sp = SPECIES[id];
    if (!sp) return { ok: false, reason: 'Unknown species' };
    if (living() >= T.tankCapacity) return { ok: false, reason: 'Tank full' };
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
      deathLeft: null, sinceFed: 0, boughtAt: S.gameTime,
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

  /** Food tool tap. Returns {ok, reason?, fed:[], spent, gold, unfed} */
  function feed() {
    const stage = dirtStage(S.dirt.elapsed);
    if (stage >= 1) { const r = { ok: false, reason: 'dirty' }; emit('feedblocked', r); return r; }
    if (living() === 0) { const r = { ok: false, reason: 'nofish' }; emit('feedfail', r); return r; }
    const eaters = S.fish.filter(needsFood);
    if (eaters.length === 0) { const r = { ok: false, reason: 'nobodyhungry' }; emit('feedfail', r); return r; }
    // least death time left first; WAITING fish last
    eaters.sort((a, b) => {
      const da = a.state === 'WAITING' ? Infinity : a.deathLeft;
      const db = b.state === 'WAITING' ? Infinity : b.deathLeft;
      return da - db;
    });
    const fed = []; let spent = 0;
    for (const f of eaters) {
      const p = portion(SPECIES[f.sp], f.level);
      if (S.food - spent >= p) { spent += p; fed.push(f); }
    }
    const unfed = eaters.length - fed.length;
    if (fed.length === 0) { const r = { ok: false, reason: 'nofood' }; emit('feedfail', r); return r; }
    S.food -= spent;
    const gold = fed.length * T.feedGoldPerFish;
    S.gold += gold;
    fed.forEach((f) => {
      if (f.state === 'WAITING') { f.state = 'GROWING'; f.progress = 0; f.hungerDone = false; }
      else if (f.state === 'HUNGRY') { f.state = 'GROWING'; }
      else if (f.state === 'ADULT_HUNGRY') { f.state = 'ADULT'; }
      f.deathLeft = null;
      f.sinceFed = 0;
    });
    S.stats.feeds++;
    const r = { ok: true, fed, spent, gold, unfed };
    emit('fed', r);
    checkStarterGrant();
    return r;
  }

  /** Sponge rub along a segment in tank-normalized coords (x by width, y by height).
   *  W,H = tank size in CSS px (grime is measured in px of sponge travel). */
  function rub(x0, y0, x1, y1, W, H, spongeR) {
    const stage = dirtStage(S.dirt.elapsed);
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
      const gold = T.dirt.cleanGold[stage - 1];
      S.gold += gold;
      S.dirt.elapsed = 0; S.dirt.spawned = 0; S.dirt.spots = [];
      S.stats.cleans++;
      emit('cleaned', { stage, gold });
      return { cleaned: true, gold, stage };
    }
    return { cleaned: false, touched };
  }

  function sell(fishId) {
    const f = S.fish.find((x) => x.id === fishId);
    if (!f) return null;
    const price = sellPrice(SPECIES[f.sp], f.level);
    S.fish = S.fish.filter((x) => x !== f);
    S.gold += price;
    S.stats.sold++;
    emit('sold', { fish: f, gold: price });
    checkStarterGrant();
    return price;
  }

  // ---------------------------------------------------------------- info for UI
  function fishInfo(f) {
    const sp = SPECIES[f.sp];
    const need = growSec(sp, f.level);
    const info = {
      species: sp, level: f.level, state: f.state, maxLevel: T.maxLevel,
      growNeed: need, growLeft: need != null ? need - f.progress : null,
      progressFrac: need ? f.progress / need : 1,
      deathLeft: f.deathLeft, deathTotal: deathSecFor(sp, f.level),
      sell: sellPrice(sp, f.level), portion: portion(sp, f.level),
      adultHungerIn: f.state === 'ADULT' ? adultHungerSec(sp) - f.sinceFed : null,
    };
    return info;
  }

  // ---------------------------------------------------------------- save/load
  // Simple rule: the game clock only runs while the page is open. On reload
  // the save resumes exactly where it was (no offline progress). While the tab
  // is merely hidden, the next frame catches up the elapsed wall-clock time.
  function save(storage) {
    try { (storage || root.localStorage).setItem(CFG.VISUAL.saveKey, JSON.stringify(S)); } catch (e) { /* ignore */ }
  }
  function load(storage) {
    try {
      const raw = (storage || root.localStorage).getItem(CFG.VISUAL.saveKey);
      if (!raw) return false;
      const d = JSON.parse(raw);
      if (!d || d.v !== 1) return false;
      const base = newState();
      S = Object.assign(base, d);
      S.dirt = Object.assign(newState().dirt, d.dirt || {});
      S.stats = Object.assign(newState().stats, d.stats || {});
      S.fish = (d.fish || []).filter((f) => SPECIES[f.sp]);
      return true;
    } catch (e) { return false; }
  }
  function reset(storage) {
    try { (storage || root.localStorage).removeItem(CFG.VISUAL.saveKey); } catch (e) { /* ignore */ }
    S = newState();
    emit('reset');
  }

  // ---------------------------------------------------------------- balance checks
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
        return { gold, time, perMin: gold / (time / 60) };
      };
      const r3 = route(L - 1), r4 = route(L);
      out.push({ species: sp.name, sellL3perMin: +r3.perMin.toFixed(2), sellL4perMin: +r4.perMin.toFixed(2), ok: r4.perMin > r3.perMin });
    });
    const cleanPerHour = T.dirt.stageAtSec.map((t, i) => +(T.dirt.cleanGold[i] * 3600 / t).toFixed(1));
    const cleanOk = cleanPerHour.every((v, i) => i === 0 || v < cleanPerHour[i - 1]);
    return { sell: out, sellOk: out.every((o) => o.ok), cleanPerHour, cleanOk };
  }

  root.Game = {
    CFG, T, SPECIES,
    get state() { return S; },
    on(fn) { listeners.push(fn); },
    tick, buyFish, buyFood, feed, rub, sell, canBuy,
    dirtStage: () => dirtStage(S.dirt.elapsed),
    fishInfo, portion, sellPrice, growSec, deathSecFor, adultHungerSec,
    save, load, reset, newState, balanceChecks, living, tankOver,
  };
})(typeof window !== 'undefined' ? window : globalThis);
