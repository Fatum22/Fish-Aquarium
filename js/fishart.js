/* Procedural "realistic-cartoon" fish drawing on canvas. No image assets.
 * drawFish(ctx, speciesId, len, phase, opts) draws a fish facing +x, centred on (0,0).
 * opts.level (1..4, default 4) applies Art Director's growth look (DIRT_AND_FISH_GROWTH.md s.2):
 * body saturation, tail length/spread, clear fins at L1, markings fading in, adult detail at L4.
 * Body shape and tail type never change with level, so each species stays recognisable.
 */
(function () {
  'use strict';

  const GROW = ((window.AQUARIUM_CONFIG || {}).VISUAL || {}).fishGrowth || {
    sat: [0.3, 0.55, 0.8, 1], tailLen: [0.45, 0.65, 0.85, 1], tailSpread: [0.5, 0.7, 0.85, 1],
    finAlpha: [0, 0.4, 0.7, 1], markAlpha: [0, 0.4, 1, 1],
  };
  const CLEAR_FIN = 'rgba(235,240,245,0.22)', CLEAR_EDGE = 'rgba(255,255,255,0.35)';
  // Art Director rulings 2026-09-27: danio stripes start at L2 (none at L1); neon L2 line at 85% / >= 2 px (was 70%, 55%); platy fins 65%/85% at L2/L3 (VISUAL.fishGrowth.finAlphaBySpecies).
  // AD ruling (neon L2 at 390 px phone size read as plain silver): L2 line at 85%, at least 2 px thick at tank size (2.4 drawn so antialiased edges still measure >= 2) and
  // never under 12% of body depth (13% used), same blue gradient as the adult stripe, no glow. L3/L4 unchanged.
  const LOOK = { neonL2LineAlpha: 0.85, neonL2LineMinPx: 2.4, neonL2LineDepthFrac: 0.13, neonStripe: ['#5ff6ff', '#2aa8ff', '#2a6bff'], danioStripes: [[], [1, 2], [0, 1, 2, 3], [0, 1, 2, 3]] };

  // Adult palette (L4). Pushed richer per the spec: vivid guppy tail, deep red platy, dark-blue danio stripes.
  const ART = {
    neon: {
      depth: 0.27, tail: 'fork', tailLen: 0.30, tailSpread: 0.95,
      top: '#34455f', mid: '#6d7f95', belly: '#e3ebf0',
      fin: 'rgba(235,245,255,0.45)', finEdge: 'rgba(255,255,255,0.7)', tailFill: 'rgba(230,240,255,0.42)',
      dorsal: 'small', eyeRing: '#9ee8ff', translucentL1: true,
    },
    guppy: {
      depth: 0.30, tail: 'fan', tailLen: 0.62, tailSpread: 2.3,
      top: '#6f7a58', mid: '#a4a882', belly: '#efe8cf',
      fin: 'rgba(120,170,255,0.75)', finEdge: 'rgba(255,255,255,0.6)', tailFill: null,
      dorsal: 'flag', eyeRing: '#f4e3a1',
    },
    danio: {
      depth: 0.235, tail: 'fork', tailLen: 0.32, tailSpread: 1.0,
      top: '#b8ae78', mid: '#e0dab0', belly: '#fbfaf0',
      fin: 'rgba(250,245,220,0.55)', finEdge: 'rgba(40,70,160,0.6)', tailFill: 'rgba(245,240,215,0.6)',
      dorsal: 'small', eyeRing: '#e8e0b8', translucentL1: true,
    },
    platy: {
      depth: 0.42, tail: 'round', tailLen: 0.30, tailSpread: 1.05,
      top: '#a01208', mid: '#d0260e', belly: '#ff8a3a',
      // juvenile hue: platy goes orange-brown -> orange -> red-orange -> deep red (mix toward adult by level)
      juv: { top: '#a04c14', mid: '#e07e26', belly: '#f8b46a' }, juvMix: [0, 0.2, 0.6, 1],
      fin: 'rgba(255,110,50,0.85)', finEdge: 'rgba(120,20,10,0.55)', tailFill: null,
      dorsal: 'round', eyeRing: '#ffd9a0',
    },
  };

  // ---- colour helpers (no ctx.filter: Safari canvas lacks it)
  function parse(c) {
    if (c[0] === '#') {
      let h = c.slice(1);
      if (h.length <= 4) h = h.split('').map((x) => x + x).join('');
      const n = parseInt(h.slice(0, 6), 16);
      return [n >> 16, (n >> 8) & 255, n & 255, h.length === 8 ? parseInt(h.slice(6), 16) / 255 : 1];
    }
    const m = c.match(/[\d.]+/g).map(Number);
    return [m[0], m[1], m[2], m[3] == null ? 1 : m[3]];
  }
  const str = (r, g, b, a) => `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${+a.toFixed(3)})`;
  /** blend a colour toward its own grey; s = 1 keeps it, 0 = grey */
  function sat(c, s) {
    const [r, g, b, a] = parse(c), y = 0.299 * r + 0.587 * g + 0.114 * b;
    return str(y + (r - y) * s, y + (g - y) * s, y + (b - y) * s, a);
  }
  function mix(c1, c2, t) {
    const p = parse(c1), q = parse(c2);
    return str(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t, p[3] + (q[3] - p[3]) * t);
  }

  function growth(level, id) {
    const i = Math.max(1, Math.min(4, level || 4)) - 1;
    const fin = ((GROW.finAlphaBySpecies || {})[id] || GROW.finAlpha)[i];
    return { lv: i + 1, sat: GROW.sat[i], tl: GROW.tailLen[i], ts: GROW.tailSpread[i], fin, mark: GROW.markAlpha[i], clear: GROW.finAlpha[i] === 0 };
  }
  /** fill the current path as a fin: clear at L1, else the species' own fin colour (never grey-blended,
   *  AD ruling 5) at finAlpha of its alpha */
  function finFill(ctx, k, style) {
    if (k.clear) { ctx.fillStyle = CLEAR_FIN; ctx.fill(); return; }
    ctx.save(); ctx.globalAlpha *= k.fin; ctx.fillStyle = style; ctx.fill(); ctx.restore();
  }
  /** fin edge stroke: white 0.35 at L1, else the species edge colour with only its alpha scaled by level */
  function finStroke(ctx, k, a) {
    if (k.clear) { ctx.strokeStyle = CLEAR_EDGE; ctx.stroke(); return; }
    ctx.save(); ctx.globalAlpha *= k.fin; ctx.strokeStyle = a.finEdge; ctx.stroke(); ctx.restore();
  }

  function bodyPath(ctx, L, hh) {
    const nx = 0.48 * L, px = -0.32 * L, ph = hh * 0.24;
    ctx.beginPath();
    ctx.moveTo(nx, hh * 0.05);
    ctx.bezierCurveTo(nx + 0.01 * L, -hh * 0.75, 0.18 * L, -hh * 1.05, -0.06 * L, -hh * 0.82);
    ctx.bezierCurveTo(-0.2 * L, -hh * 0.62, -0.28 * L, -ph * 1.2, px, -ph);
    ctx.lineTo(px, ph);
    ctx.bezierCurveTo(-0.28 * L, ph * 1.2, -0.2 * L, hh * 0.6, -0.06 * L, hh * 0.78);
    ctx.bezierCurveTo(0.2 * L, hh * 1.0, nx, hh * 0.7, nx, hh * 0.05);
    ctx.closePath();
  }

  function tailPath(ctx, a, L, hh) {
    const px = -0.31 * L, ph = hh * 0.22;
    const tl = a.tailLen * L, sp = a.tailSpread * hh;
    ctx.beginPath();
    ctx.moveTo(px + 2, -ph);
    if (a.tail === 'fork') {
      ctx.quadraticCurveTo(px - tl * 0.5, -sp * 0.55, px - tl, -sp);
      ctx.quadraticCurveTo(px - tl * 0.72, -sp * 0.15, px - tl * 0.62, 0);
      ctx.quadraticCurveTo(px - tl * 0.72, sp * 0.15, px - tl, sp);
      ctx.quadraticCurveTo(px - tl * 0.5, sp * 0.55, px + 2, ph);
    } else if (a.tail === 'fan') {
      ctx.quadraticCurveTo(px - tl * 0.35, -sp * 0.35, px - tl * 0.9, -sp * 0.55);
      ctx.bezierCurveTo(px - tl * 1.12, -sp * 0.3, px - tl * 1.12, sp * 0.3, px - tl * 0.9, sp * 0.55);
      ctx.quadraticCurveTo(px - tl * 0.35, sp * 0.35, px + 2, ph);
    } else { // round
      ctx.quadraticCurveTo(px - tl * 0.4, -sp * 0.6, px - tl * 0.85, -sp * 0.55);
      ctx.bezierCurveTo(px - tl * 1.1, -sp * 0.3, px - tl * 1.1, sp * 0.3, px - tl * 0.85, sp * 0.55);
      ctx.quadraticCurveTo(px - tl * 0.4, sp * 0.6, px + 2, ph);
    }
    ctx.closePath();
  }

  function drawTail(ctx, id, a, L, hh, sway, k) {
    ctx.save();
    ctx.translate(-0.31 * L, 0);
    ctx.rotate(sway);
    ctx.translate(0.31 * L, 0);
    tailPath(ctx, a, L, hh);
    const tl = a.tailLen * L, x0 = -0.31 * L;
    let fill = a.tailFill;
    if (id === 'guppy') {
      if (k.lv === 2) fill = a.fin; // short fan tinted blue
      else {
        const g = ctx.createLinearGradient(x0, 0, x0 - tl, 0);
        if (k.lv === 3) { g.addColorStop(0, '#3f8cff'); g.addColorStop(1, '#ff8a2a'); } // blue fading to orange
        else { g.addColorStop(0, '#1f6bff'); g.addColorStop(0.5, '#ff7a1a'); g.addColorStop(1, '#e8243a'); } // vivid blue, orange, red
        fill = g;
      }
    } else if (id === 'platy') {
      const g = ctx.createLinearGradient(x0, 0, x0 - tl, 0);
      g.addColorStop(0, k.lv >= 4 ? '#e8401e' : '#ff6a2b'); g.addColorStop(1, k.lv >= 4 ? '#c01e10' : '#e0461e');
      fill = g;
    }
    finFill(ctx, k, fill);
    if (k.clear) { ctx.strokeStyle = CLEAR_EDGE; ctx.lineWidth = Math.max(0.6, L * 0.008); ctx.stroke(); }
    // fin rays / pattern
    ctx.save();
    tailPath(ctx, a, L, hh); ctx.clip();
    ctx.strokeStyle = k.clear ? 'rgba(255,255,255,0.18)' : id === 'guppy' ? 'rgba(40,10,80,0.25)' : id === 'platy' ? 'rgba(160,40,10,0.3)' : 'rgba(255,255,255,0.35)'; // platy rays in its own red, not white
    ctx.lineWidth = Math.max(0.5, L * 0.006);
    for (let i = -4; i <= 4; i++) {
      ctx.beginPath(); ctx.moveTo(x0, 0); ctx.lineTo(x0 - tl * 1.2, i * a.tailSpread * hh * 0.3); ctx.stroke();
    }
    if (id === 'guppy' && k.lv >= 3) { // L3 a few black spots; L4 adds the coloured adult spots
      const spots = k.lv === 3
        ? [[0.55, -0.2, '#111'], [0.75, 0.2, '#111'], [0.4, 0.3, '#111']]
        : [[0.45, -0.3, '#2bd1ff'], [0.7, 0.25, '#111'], [0.6, -0.05, '#111'], [0.8, -0.35, '#ffd23b'], [0.35, 0.3, '#2bd1ff'], [0.85, 0.05, '#111']];
      for (const [fx, fy, c] of spots) {
        ctx.fillStyle = c; ctx.globalAlpha = k.lv === 3 ? 0.6 : 0.85;
        ctx.beginPath(); ctx.arc(x0 - tl * fx, fy * a.tailSpread * hh, hh * (k.lv === 3 ? 0.13 : 0.16), 0, 7); ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
    if (id === 'danio' && k.lv >= 3) { // L3 stripes just starting on the tail, L4 crisp stripes running into it
      ctx.strokeStyle = k.lv === 3 ? 'rgba(42,74,168,0.6)' : 'rgba(26,47,134,0.95)'; ctx.lineWidth = hh * 0.14; ctx.lineCap = 'round';
      const reach = k.lv === 3 ? 0.3 : 0.75;
      for (const s of [-0.28, 0.02, 0.32]) {
        ctx.beginPath(); ctx.moveTo(x0 + 2, s * hh * 0.6); ctx.lineTo(x0 - tl * reach, s * hh * (0.6 + 0.8 * reach)); ctx.stroke();
      }
    }
    if (id === 'platy' && k.lv >= 4) { // adult: darker edge on the red round tail
      ctx.strokeStyle = 'rgba(90,10,0,0.6)'; ctx.lineWidth = hh * 0.16;
      tailPath(ctx, a, L, hh); ctx.stroke();
    }
    ctx.restore();
    ctx.restore();
  }

  function drawDorsal(ctx, id, a, L, hh, wave, k) {
    ctx.beginPath();
    const w = Math.sin(wave) * hh * 0.06;
    if (a.dorsal === 'flag') { // guppy: flag dorsal, grows with the tail (small at L2, full at L4)
      const d = k.tl;
      ctx.moveTo(0.02 * L, -hh * 0.9);
      ctx.quadraticCurveTo(-0.12 * L, -hh * (0.9 + d) + w, -(0.14 + 0.2 * d) * L, -hh * (0.9 + 0.45 * d) + w);
      ctx.quadraticCurveTo(-0.2 * L, -hh * 0.9, -0.16 * L, -hh * 0.62);
    } else if (a.dorsal === 'round') { // platy
      ctx.moveTo(0.08 * L, -hh * 0.95);
      ctx.bezierCurveTo(0.02 * L, -hh * 1.55 + w, -0.14 * L, -hh * 1.5 + w, -0.18 * L, -hh * 0.72);
    } else {
      ctx.moveTo(0.0 * L, -hh * 0.88);
      ctx.quadraticCurveTo(-0.06 * L, -hh * 1.6 + w, -0.14 * L, -hh * 1.45 + w);
      ctx.quadraticCurveTo(-0.13 * L, -hh * 1.0, -0.14 * L, -hh * 0.72);
    }
    ctx.closePath();
    let fill = a.fin;
    if (id === 'guppy' && k.lv >= 3) {
      fill = ctx.createLinearGradient(0, -hh, -0.3 * L, -hh * 1.6);
      fill.addColorStop(0, '#5fd0ff'); fill.addColorStop(1, k.lv >= 4 ? '#ff6a2b' : '#ff9a4a');
    }
    finFill(ctx, k, fill);
    ctx.lineWidth = Math.max(0.5, L * 0.008); finStroke(ctx, k, a);
  }

  function drawBellyFins(ctx, id, a, L, hh, wave, k) {
    const w = Math.sin(wave + 1) * hh * 0.08;
    const fill = id === 'guppy' ? 'rgba(255,160,90,0.7)' : a.fin;
    ctx.lineWidth = Math.max(0.5, L * 0.006);
    // anal fin
    ctx.beginPath();
    ctx.moveTo(-0.06 * L, hh * 0.78);
    ctx.quadraticCurveTo(-0.14 * L, hh * 1.45 + w, -0.24 * L, hh * 1.2 + w);
    ctx.quadraticCurveTo(-0.22 * L, hh * 0.8, -0.2 * L, hh * 0.55);
    ctx.closePath(); finFill(ctx, k, fill); finStroke(ctx, k, a);
    // pelvic fin
    ctx.beginPath();
    ctx.moveTo(0.14 * L, hh * 0.9);
    ctx.quadraticCurveTo(0.08 * L, hh * 1.4 - w, 0.02 * L, hh * 1.3 - w);
    ctx.quadraticCurveTo(0.04 * L, hh * 1.0, 0.04 * L, hh * 0.85);
    ctx.closePath(); finFill(ctx, k, fill);
  }

  /** markings: none at L1, main marking at L2, full at L3, + adult detail at L4 */
  function drawPattern(ctx, id, a, L, hh, k) {
    const lv = k.lv;
    ctx.save();
    if (id === 'neon') {
      if (lv >= 3) { // red rear: L3 rear half at 60%, L4 full red from mid-body to tail base
        const start = lv >= 4 ? 0.05 : -0.06;
        const r = ctx.createLinearGradient(start * L, 0, -0.3 * L, 0);
        r.addColorStop(0, 'rgba(232,35,58,0)'); r.addColorStop(0.18, 'rgba(232,35,58,0.95)'); r.addColorStop(1, '#d81f36');
        ctx.globalAlpha = lv >= 4 ? 1 : 0.6;
        ctx.fillStyle = r; ctx.fillRect(-0.4 * L, hh * 0.02, (start + 0.4) * L, hh * 1.2);
        ctx.globalAlpha = 1;
      }
      if (lv === 2) { // thin blue line: adult stripe colours at 85%, >= max(2 px, 13% of body depth), no glow
        const lg = ctx.createLinearGradient(0.35 * L, 0, -0.32 * L, 0);
        lg.addColorStop(0, LOOK.neonStripe[0]); lg.addColorStop(0.5, LOOK.neonStripe[1]); lg.addColorStop(1, LOOK.neonStripe[2]);
        ctx.strokeStyle = lg; ctx.globalAlpha = LOOK.neonL2LineAlpha; ctx.shadowBlur = 0;
        ctx.lineWidth = Math.max(LOOK.neonL2LineMinPx, LOOK.neonL2LineDepthFrac * 2 * hh); ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(0.34 * L, -hh * 0.12); ctx.quadraticCurveTo(0.0, -hh * 0.27, -0.32 * L, -hh * 0.08); ctx.stroke();
      } else if (lv >= 3) { // full electric-blue stripe; L4 glows (soft ~2px)
        const g = ctx.createLinearGradient(0.35 * L, 0, -0.32 * L, 0);
        g.addColorStop(0, LOOK.neonStripe[0]); g.addColorStop(0.5, LOOK.neonStripe[1]); g.addColorStop(1, LOOK.neonStripe[2]);
        ctx.fillStyle = g;
        if (lv >= 4) { const m = ctx.getTransform(); ctx.shadowColor = 'rgba(95,240,255,0.95)'; ctx.shadowBlur = 4 * Math.hypot(m.a, m.b); }
        ctx.beginPath();
        ctx.moveTo(0.36 * L, -hh * 0.22);
        ctx.quadraticCurveTo(0.0, -hh * 0.42, -0.34 * L, -hh * 0.18);
        ctx.lineTo(-0.34 * L, hh * 0.02);
        ctx.quadraticCurveTo(0.0, -hh * 0.08, 0.36 * L, -hh * 0.02);
        ctx.closePath(); ctx.fill();
        ctx.shadowBlur = 0; ctx.shadowColor = 'transparent';
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.fillRect(-0.3 * L, -hh * 0.3, 0.6 * L, hh * 0.05);
      }
      if (lv >= 4) { // silver belly
        const b = ctx.createLinearGradient(0, hh * 0.25, 0, hh);
        b.addColorStop(0, 'rgba(240,246,252,0)'); b.addColorStop(1, 'rgba(240,246,252,0.75)');
        ctx.fillStyle = b; ctx.fillRect(0.02 * L, hh * 0.25, 0.5 * L, hh);
      }
    } else if (id === 'danio') {
      const ys = [-0.5, -0.18, 0.14, 0.44];
      ctx.strokeStyle = lv >= 4 ? '#1a2f86' : '#2a4aa8'; ctx.lineCap = 'round';
      ctx.globalAlpha = k.mark;
      LOOK.danioStripes[lv - 1].forEach((i) => { // none at L1 (AD ruling 1)
        const y = ys[i];
        ctx.lineWidth = hh * (i === 1 || i === 2 ? 0.17 : 0.12);
        ctx.beginPath();
        ctx.moveTo(0.3 * L, y * hh * 0.7);
        ctx.quadraticCurveTo(0.0, y * hh * 1.05, -0.36 * L, y * hh * 0.45);
        ctx.stroke();
      });
      if (lv >= 4) { // gold sheen between stripes
        ctx.globalAlpha = 1; ctx.strokeStyle = 'rgba(255,212,110,0.75)'; ctx.lineWidth = hh * 0.07;
        [-0.34, -0.02, 0.29].forEach((y) => {
          ctx.beginPath(); ctx.moveTo(0.28 * L, y * hh * 0.7);
          ctx.quadraticCurveTo(0.0, y * hh * 1.05, -0.36 * L, y * hh * 0.45); ctx.stroke();
        });
      }
    } else if (id === 'guppy') {
      // L2 faint orange spot, L3 faint orange + blue side spots, L4 all spots + light side shimmer
      const spots = [[-0.12, -0.1, '#ff7a1a', 0.2], [-0.22, 0.18, '#2b8cff', 0.16], [-0.02, 0.25, '#111a', 0.12], [-0.25, -0.2, '#ffd23b', 0.12]];
      const n = [0, 1, 2, 4][lv - 1];
      ctx.globalAlpha = [0, 0.3, 0.55, 1][lv - 1];
      for (const [x, y, c, r] of spots.slice(0, n)) {
        ctx.fillStyle = c; ctx.beginPath(); ctx.ellipse(x * L, y * hh, r * hh * 1.3, r * hh, 0, 0, 7); ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (lv >= 4) {
        const sheen = ctx.createLinearGradient(0, -hh, 0, hh);
        sheen.addColorStop(0.3, 'rgba(120,220,255,0)'); sheen.addColorStop(0.55, 'rgba(120,220,255,0.35)'); sheen.addColorStop(0.8, 'rgba(120,220,255,0)');
        ctx.fillStyle = sheen; ctx.fillRect(-0.4 * L, -hh, 0.5 * L, hh * 2);
      }
    } else if (id === 'platy') {
      ctx.globalAlpha = k.mark;
      ctx.fillStyle = 'rgba(255,230,150,0.25)';
      for (let i = 0; i < 5; i++) {
        ctx.beginPath(); ctx.arc((0.2 - i * 0.1) * L, -hh * 0.1, hh * 0.18, 0, 7); ctx.fill();
      }
      if (lv >= 4) { // glossy highlight
        ctx.globalAlpha = 1;
        const gl = ctx.createLinearGradient(0, -hh * 0.8, 0, -hh * 0.3);
        gl.addColorStop(0, 'rgba(255,255,255,0.55)'); gl.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = gl; ctx.beginPath(); ctx.ellipse(0.08 * L, -hh * 0.52, 0.26 * L, hh * 0.2, -0.08, 0, 7); ctx.fill();
      }
    }
    ctx.restore();
  }

  /**
   * @param ctx canvas 2d context
   * @param id species id
   * @param L body length in px (tail extends beyond)
   * @param phase animation phase (radians) for tail/fins
   * @param opts {dead, hungry, level (1..4, default 4)}
   */
  function drawFish(ctx, id, L, phase, opts) {
    opts = opts || {};
    if (opts.dead) { drawDead(ctx, id, L, opts); return; }
    drawLive(ctx, id, L, phase, opts);
  }

  // ---- dead pose (Art Director, DIRT_AND_FISH_GROWTH.md "Dead fish pose"): belly-up, same species/size/tail/markings,
  // colour 35% of living saturation blended 20% toward #D8DCD6, fins/tail at 60% opacity, cloudy pale-grey eye, no motion.
  // Rendered once per species/level/size into an offscreen canvas (colour pass on pixels; no ctx.filter, Safari lacks it).
  const DEAD = { sat: 0.35, wash: [0xD8, 0xDC, 0xD6], washMix: 0.2, finAlpha: 0.6, eye: '#C9CFCF' };
  const deadCache = new Map();
  function deadSprite(id, L, level, scale) {
    const key = `${id}|${level}|${Math.round(L)}|${scale.toFixed(2)}`;
    let c = deadCache.get(key);
    if (c) return c;
    const ox = 1.2 * L, oy = 0.62 * L, w = 1.85 * L, h = 1.24 * L;
    const cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.ceil(w * scale)); cv.height = Math.max(1, Math.ceil(h * scale));
    const x = cv.getContext('2d');
    x.scale(scale, scale); x.translate(ox, oy);
    drawLive(x, id, L, 0, { level, deadParts: true });
    const img = x.getImageData(0, 0, cv.width, cv.height), d = img.data, [wr, wg, wb] = DEAD.wash, t = DEAD.washMix;
    for (let i = 0; i < d.length; i += 4) {
      if (!d[i + 3]) continue;
      const y = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      d[i] = (y + (d[i] - y) * DEAD.sat) * (1 - t) + wr * t;
      d[i + 1] = (y + (d[i + 1] - y) * DEAD.sat) * (1 - t) + wg * t;
      d[i + 2] = (y + (d[i + 2] - y) * DEAD.sat) * (1 - t) + wb * t;
    }
    x.putImageData(img, 0, 0);
    c = { cv, ox, oy, w, h };
    if (deadCache.size > 60) deadCache.delete(deadCache.keys().next().value);
    deadCache.set(key, c);
    return c;
  }
  function drawDead(ctx, id, L, opts) {
    const m = ctx.getTransform(), scale = Math.max(0.5, Math.min(4, Math.hypot(m.a, m.b) || 1));
    const sp = deadSprite(id, L, opts.level || 4, scale);
    ctx.save();
    ctx.scale(1, -1); // belly-up
    ctx.drawImage(sp.cv, -sp.ox, -sp.oy, sp.w, sp.h);
    ctx.restore();
  }

  function drawLive(ctx, id, L, phase, opts) {
    const base = ART[id] || ART.neon;
    const dead = !!opts.deadParts;
    const k = growth(opts.level, id);
    const a = Object.assign({}, base, { tailLen: base.tailLen * k.tl, tailSpread: base.tailSpread * k.ts });
    const hh = (a.depth * L) / 2;
    const sway = dead ? 0 : Math.sin(phase) * (opts.hungry ? 0.14 : 0.28);
    ctx.save();

    ctx.save();
    if (dead) ctx.globalAlpha *= DEAD.finAlpha; // dead: fins and tail at 60% of their living opacity
    drawTail(ctx, id, a, L, hh, sway, k);
    drawDorsal(ctx, id, a, L, hh, dead ? 0 : phase * 0.7, k);
    drawBellyFins(ctx, id, a, L, hh, dead ? 0 : phase, k);
    ctx.restore();

    // body: adult palette blended toward grey by level (platy also shifts hue orange -> deep red)
    let top = a.top, mid = a.mid, belly = a.belly;
    if (a.juv) { const t = a.juvMix[k.lv - 1]; top = mix(a.juv.top, top, t); mid = mix(a.juv.mid, mid, t); belly = mix(a.juv.belly, belly, t); }
    ctx.save();
    if (a.translucentL1 && k.lv === 1) ctx.globalAlpha *= 0.8;
    bodyPath(ctx, L, hh);
    const g = ctx.createLinearGradient(0, -hh, 0, hh);
    g.addColorStop(0, sat(top, k.sat)); g.addColorStop(0.45, sat(mid, k.sat)); g.addColorStop(1, sat(belly, k.sat));
    ctx.fillStyle = g; ctx.fill();
    ctx.restore();
    ctx.save();
    bodyPath(ctx, L, hh); ctx.clip();
    drawPattern(ctx, id, a, L, hh, k);
    // soft top highlight + shading
    const hl = ctx.createRadialGradient(0.15 * L, -hh * 0.5, 1, 0.1 * L, -hh * 0.3, L * 0.45);
    hl.addColorStop(0, 'rgba(255,255,255,0.35)'); hl.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = hl; ctx.fillRect(-L, -hh * 2, 2 * L, hh * 4);
    // scale hint
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 0.6;
    for (let x = 0.2 * L; x > -0.3 * L; x -= L * 0.06) {
      ctx.beginPath(); ctx.arc(x, 0, hh * 0.7, -0.9, 0.9); ctx.stroke();
    }
    ctx.restore();
    bodyPath(ctx, L, hh);
    ctx.strokeStyle = 'rgba(20,30,50,0.35)'; ctx.lineWidth = Math.max(0.6, L * 0.01); ctx.stroke();

    // gill line
    ctx.strokeStyle = 'rgba(40,30,30,0.3)'; ctx.lineWidth = Math.max(0.6, L * 0.008);
    ctx.beginPath(); ctx.arc(0.34 * L, 0, hh * 0.6, 2.2, 4.1); ctx.stroke();

    // pectoral fin (flaps)
    ctx.save();
    ctx.translate(0.24 * L, hh * 0.25);
    ctx.rotate(0.5 + (dead ? 0 : Math.sin(phase * 1.6) * 0.35));
    if (dead) ctx.globalAlpha *= DEAD.finAlpha;
    ctx.beginPath(); ctx.ellipse(-hh * 0.4, 0, hh * 0.45, hh * 0.18, 0, 0, 7);
    if (id === 'platy') finFill(ctx, k, 'rgba(255,150,80,0.8)');
    else { ctx.fillStyle = k.clear ? CLEAR_FIN : 'rgba(255,255,255,0.4)'; ctx.fill(); }
    ctx.restore();

    // eye
    const ex = 0.33 * L, ey = -hh * 0.18, er = Math.max(1.6, hh * 0.3);
    ctx.fillStyle = sat(a.eyeRing, k.sat); ctx.beginPath(); ctx.arc(ex, ey, er, 0, 7); ctx.fill();
    if (dead) { // cloudy pale grey disc instead of the pupil (no cartoon X eyes)
      ctx.fillStyle = DEAD.eye; ctx.beginPath(); ctx.arc(ex + er * 0.08, ey, er * 0.72, 0, 7); ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.35)'; ctx.beginPath(); ctx.arc(ex - er * 0.1, ey - er * 0.2, er * 0.35, 0, 7); ctx.fill();
    } else {
      ctx.fillStyle = '#0d0f14'; ctx.beginPath(); ctx.arc(ex + er * 0.12, ey, er * 0.66, 0, 7); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(ex + er * 0.35, ey - er * 0.3, er * 0.25, 0, 7); ctx.fill();
    }
    // mouth
    ctx.strokeStyle = 'rgba(60,20,20,0.5)'; ctx.lineWidth = Math.max(0.6, L * 0.008);
    ctx.beginPath(); ctx.moveTo(0.48 * L, hh * 0.12); ctx.lineTo(0.43 * L, hh * 0.16); ctx.stroke();

    ctx.restore();
  }

  /** the body outline only (no fins or tail), in the same local frame drawFish uses: for the net's target highlight */
  function bodyOutline(ctx, id, L, opts) {
    const base = ART[id] || ART.neon, hh = (base.depth * L) / 2;
    if (opts && opts.dead) ctx.scale(1, -1); // belly-up, like drawDead
    bodyPath(ctx, L, hh);
  }
  window.FishArt = { drawFish, bodyOutline, ART, growth, LOOK, DEAD };
})();
