/* Aquarium fish drawing, V7 (Art Director NEW_FISH_V7.md): hand-authored layered vector art from
 * studio/briefs/aquarium/art/fish-v7/<id>.json, shipped as window.FISH_V7 (js/fishdata.js).
 * drawFish(ctx, speciesId, L, phase, opts) draws a fish facing +x, centred on (0,0) (the middle of the
 * snout..tail-tip span), L = on-screen length in px (adult snout..tail tip = 100 units, so scale = L / 100).
 * opts: { level 1..4 (default 4), hungry, dead, t (seconds, for the live rare FX), noFx }.
 *
 * Performance (V7 3): each (species, level, size, device scale) is rendered once into three cached canvases:
 * "under" (contact shadow + rare aura), "tail" (layers with part 'tail', wagged around stage.tailPivot) and
 * "body" (everything else except the live FX). Per frame a fish is 3 drawImage calls, plus for uncommon/rare
 * adults a sheen band swept across the body clip and (rares) three sparkles twinkling one at a time.
 * The layer renderer is the AD's reference render.js (drawFishV7), ported as is (plus shadowBlur x device scale).
 */
(function () {
  'use strict';

  const DATA = window.FISH_V7 || {};
  const FIN = new Set(['caudal', 'dorsal', 'dorsal1', 'anal', 'pelvic', 'pelvicFar', 'pectoral', 'adipose', 'sword', 'feeler']);
  const LIVE = new Set(['sheen', 'sparkle']);
  const WAG = 0.18, WAG_HUNGRY = 0.09;          // tail swing in radians (about +-10 deg; V7 3 asks +-8-12)
  const LOD_PX = 30, LOD_MIN_DETAIL = 0.35;      // V7 3: fish under 30 px skip lines thinner than 0.35 screen px
  const PAD = 12;                                 // sprite padding in CSS px (glow / shadow)
  const SHEEN = { rare: { period: 4, sweep: 1.2 }, uncommon: { period: 4, sweep: 1.4 } };
  const SPARKLE = { cycle: 2.4, each: 0.6 };      // three glints, one at a time, 0 -> 1 -> 0 over 0.6 s
  const DEAD = { sat: 0.35, wash: [0xD8, 0xDC, 0xD6], washMix: 0.2, finAlpha: 0.6, eye: '#C9CFCF' };

  function species(id) { return DATA[id] || DATA.neon || Object.values(DATA)[0]; }
  function stage(id, level) { const sp = species(id); return sp.stages[Math.max(1, Math.min(4, level || 4)) - 1]; }
  function paths(st) { return st._p || (Object.defineProperty(st, '_p', { value: {}, enumerable: false }), st._p); }
  function P(st, d) { const c = paths(st); return c[d] || (c[d] = new Path2D(d)); }

  function paint(ctx, p) {
    if (typeof p === 'string') return p;
    let g;
    if (p.type === 'linear') g = ctx.createLinearGradient(p.x1, p.y1, p.x2, p.y2);
    else g = ctx.createRadialGradient(p.x0, p.y0, p.r0, p.x1, p.y1, p.r1);
    for (const [o, c] of p.stops) g.addColorStop(o, c);
    return g;
  }
  /** fin group per layer (for the dead pose: fins at 60%): a fin base sets the group, 'mark' layers inherit it */
  function groups(st) {
    if (st._g) return st._g;
    let g = 'body';
    const out = st.layers.map((l) => {
      const base = l.n.split('.')[0];
      if (l.part === 'tail' || FIN.has(base)) g = 'fin'; else if (l.n !== 'mark') g = 'body';
      return g;
    });
    Object.defineProperty(st, '_g', { value: out, enumerable: false });
    return out;
  }
  /** the reference renderer (render.js drawFishV7), one layer. s = units -> CSS px, k = CSS px -> device px */
  function drawLayer(ctx, st, l, s, k, o) {
    if (o.minDetailPx && l.lw && l.lw * s < o.minDetailPx && l.n !== 'outline') return;
    ctx.save();
    if (l.clip) ctx.clip(P(st, st.shapes[l.clip]));
    if (l.dx || l.dy) ctx.translate(l.dx || 0, l.dy || 0);
    const path = l.shape ? P(st, st.shapes[l.shape]) : P(st, l.d);
    if (l.alpha != null) ctx.globalAlpha *= l.alpha;
    if (o.alpha != null) ctx.globalAlpha *= o.alpha;
    if (l.blend) ctx.globalCompositeOperation = l.blend;
    if (l.glow) { ctx.shadowColor = l.glow.color; ctx.shadowBlur = l.glow.blur * s * k; }
    const fill = o.fill || l.fill;
    if (fill) { ctx.fillStyle = paint(ctx, fill); ctx.fill(path); }
    if (l.stroke) {
      ctx.strokeStyle = paint(ctx, l.stroke);
      ctx.lineWidth = l.lwPx ? l.lwPx / s : l.lw;
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.stroke(path);
    }
    ctx.restore();
  }
  /** draw a stage's layers straight to ctx (no cache). which: 'all' | 'under' | 'tail' | 'body' | 'bake' (all but live FX) */
  function drawLayers(ctx, st, L, which, opts) {
    opts = opts || {};
    const s = L / 100, k = opts.k || 1, dead = !!opts.dead, grp = groups(st);
    const firstTail = st.layers.findIndex((l) => l.part === 'tail');
    ctx.save();
    ctx.scale(s, s);
    st.layers.forEach((l, i) => {
      const under = firstTail >= 0 ? i < firstTail && !l.part : l.n === 'shadow' || l.n === 'aura';
      if (which === 'under' && !under) return;
      if (which === 'tail' && l.part !== 'tail') return;
      if (which === 'body' && (under || l.part === 'tail' || LIVE.has(l.n))) return;
      if (which === 'bake' && LIVE.has(l.n)) return;
      const o = { minDetailPx: opts.minDetailPx };
      if (dead) {
        if (l.n === 'shadow' || l.n === 'aura' || l.n === 'eye.pupil' || l.n === 'eye.hi2' || LIVE.has(l.n)) return;
        if (grp[i] === 'fin') o.alpha = DEAD.finAlpha;
        if (l.n === 'eye.iris') o.fill = DEAD.eye; // cloudy pale-grey eye, no pupil (no cartoon X eyes)
      }
      drawLayer(ctx, st, l, s, k, o);
    });
    ctx.restore();
  }

  // ---- sprite cache
  const cache = new Map();
  let cacheMisses = 0;
  function sprite(id, level, L, k, part, dead) {
    const key = `${id}|${level}|${part}|${Math.round(L * k * 4)}|${k}|${dead ? 1 : 0}`;
    let c = cache.get(key);
    if (c) return c;
    cacheMisses++;
    const st = stage(id, level), s = L / 100, b = st.bounds;
    // origin on a whole device pixel so an unmoved sprite lands pixel-exact (no resampling blur)
    const ox = Math.ceil((-b[0] * s + PAD) * k) / k, oy = Math.ceil((-b[1] * s + PAD) * k) / k;
    const w = Math.ceil((ox + b[2] * s + PAD) * k) / k, h = Math.ceil((oy + b[3] * s + PAD) * k) / k;
    const cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.ceil(w * k)); cv.height = Math.max(1, Math.ceil(h * k));
    const x = cv.getContext('2d');
    x.scale(k, k); x.translate(ox, oy);
    drawLayers(x, st, L, part, { k, dead, minDetailPx: L < LOD_PX ? LOD_MIN_DETAIL : 0 });
    if (dead) deadColour(x, cv);
    c = { cv, ox, oy, w, h };
    if (cache.size > 600) cache.delete(cache.keys().next().value);
    cache.set(key, c);
    return c;
  }
  /** dead pose colour pass (DIRT_AND_FISH_GROWTH.md): 35% of living saturation, blended 20% toward #D8DCD6 (no ctx.filter: Safari) */
  function deadColour(x, cv) {
    const img = x.getImageData(0, 0, cv.width, cv.height), d = img.data, [wr, wg, wb] = DEAD.wash, t = DEAD.washMix;
    for (let i = 0; i < d.length; i += 4) {
      if (!d[i + 3]) continue;
      const y = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      d[i] = (y + (d[i] - y) * DEAD.sat) * (1 - t) + wr * t;
      d[i + 1] = (y + (d[i + 1] - y) * DEAD.sat) * (1 - t) + wg * t;
      d[i + 2] = (y + (d[i + 2] - y) * DEAD.sat) * (1 - t) + wb * t;
    }
    x.putImageData(img, 0, 0);
  }
  function blit(ctx, sp) { ctx.drawImage(sp.cv, -sp.ox, -sp.oy, sp.w, sp.h); }
  /** device px per CSS px of the current transform, from the y axis (the face-turn squash only scales x) */
  function devScale(ctx) {
    const m = ctx.getTransform(), k = Math.hypot(m.c, m.d) || 1;
    return Math.max(0.5, Math.min(4, Math.round(k * 4) / 4));
  }

  // ---- live FX (uncommon / rare adults)
  function fxOf(id, level) {
    const st = stage(id, level);
    if (st._fx !== undefined) return st._fx;
    const sheen = st.layers.find((l) => l.n === 'sheen'), spark = st.layers.find((l) => l.n === 'sparkle');
    let fx = null;
    if (sheen || spark) {
      fx = { rarity: species(id).rarity, sheen, sparkles: [] };
      if (sheen) { const xs = (sheen.d.match(/-?\d+(\.\d+)?/g) || []).map(Number).filter((_, i) => i % 2 === 0); fx.sheenX = (Math.min(...xs) + Math.max(...xs)) / 2; fx.sheenHalf = (Math.max(...xs) - Math.min(...xs)) / 2; }
      if (spark) fx.sparkles = spark.d.split(/(?=M)/).map((d) => Object.assign({}, spark, { d }));
    }
    Object.defineProperty(st, '_fx', { value: fx, enumerable: false });
    return fx;
  }
  function drawFx(ctx, id, level, L, t) {
    const fx = fxOf(id, level);
    if (!fx) return;
    const st = stage(id, level), s = L / 100, k = devScale(ctx);
    ctx.save();
    ctx.scale(s, s);
    if (fx.sheen) { // the AD's sheen band, swept tail -> head across the body clip
      const cfg = SHEEN[fx.rarity] || SHEEN.uncommon, p = ((t % cfg.period) + cfg.period) % cfg.period;
      if (p < cfg.sweep) {
        const b = st.body, from = b.tail - fx.sheenHalf, to = b.nose + fx.sheenHalf, cx = from + (to - from) * (p / cfg.sweep);
        drawLayer(ctx, st, Object.assign({}, fx.sheen, { dx: cx - fx.sheenX }), s, k, {});
      }
    }
    fx.sparkles.forEach((sp, i) => {
      const q = ((t - i * SPARKLE.each * 1.3) % SPARKLE.cycle + SPARKLE.cycle) % SPARKLE.cycle;
      if (q < SPARKLE.each) drawLayer(ctx, st, sp, s, k, { alpha: Math.sin(Math.PI * q / SPARKLE.each) });
    });
    ctx.restore();
  }

  /**
   * @param ctx canvas 2D context, origin at the fish centre, facing +x
   * @param id species id; @param L length in px; @param phase swim phase (radians, drives the tail wag)
   * @param opts {dead, hungry, level (1..4, default 4), t (seconds), noFx}
   */
  function drawFish(ctx, id, L, phase, opts) {
    opts = opts || {};
    const level = Math.max(1, Math.min(4, opts.level || 4)), k = devScale(ctx);
    if (opts.dead) {
      ctx.save(); ctx.scale(1, -1); // belly-up
      blit(ctx, sprite(id, level, L, k, 'bake', true));
      ctx.restore();
      return;
    }
    const st = stage(id, level), s = L / 100;
    blit(ctx, sprite(id, level, L, k, 'under', false));
    const sway = Math.sin(phase || 0) * (opts.hungry ? WAG_HUNGRY : WAG);
    const px = st.tailPivot[0] * s, py = st.tailPivot[1] * s;
    ctx.save(); ctx.translate(px, py); ctx.rotate(sway); ctx.translate(-px, -py);
    blit(ctx, sprite(id, level, L, k, 'tail', false));
    ctx.restore();
    blit(ctx, sprite(id, level, L, k, 'body', false));
    if (!opts.noFx) drawFx(ctx, id, level, L, opts.t != null ? opts.t : performance.now() / 1000);
  }

  /** the body outline as a Path2D in the fish's local px frame (fins, tail, feelers, sword excluded): net target glow */
  function bodyPath(id, L, level, dead) {
    const st = stage(id, level), s = L / 100, p = new Path2D();
    p.addPath(P(st, st.shapes.body), new DOMMatrix([s, 0, 0, dead ? -s : s, 0, 0]));
    return p;
  }
  /** body box in px (fish facing +x): nose / tail x, top / bottom y, from stage.body */
  function bodyBox(id, L, level) {
    const b = stage(id, level).body, s = L / 100;
    return { nose: b.nose * s, tail: b.tail * s, top: b.top * s, bottom: b.bottom * s };
  }
  /** full drawn extent in px (incl. fins, tail, sword, feelers), fish facing +x: stage.bounds (V7 6: use for tank-edge clamping) */
  function extent(id, L, level) {
    const b = stage(id, level).bounds, s = L / 100;
    return { x0: b[0] * s, y0: b[1] * s, x1: b[2] * s, y1: b[3] * s };
  }

  window.FishArt = {
    drawFish, drawLayers, bodyPath, bodyBox, extent, stage, fxOf, DEAD,
    V7: DATA, cacheInfo: () => ({ size: cache.size, misses: cacheMisses }), clearCache: () => cache.clear(),
  };
})();
