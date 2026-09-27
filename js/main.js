/* Aquarium UI: rendering, swimming animation, input, panels, save loop. */
(function () {
  'use strict';
  const G = window.Game, T = G.T, CFG = G.CFG, V = CFG.VISUAL;
  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------ boot / URL
  const params = new URLSearchParams(location.search);
  const hadSave = G.load();
  // Offline progress (NUMBERS.md 9.2-9.3): replay the time away at the speed that was running when the game closed.
  let awaySummary = hadSave ? G.resume(Date.now()) : null;
  // The page always opens at the default speed (x1); a hidden ?speed=N (any N > 0) overrides it for tests/Playtester.
  const urlSpeed = parseFloat(params.get('speed'));
  G.state.speed = urlSpeed > 0 ? urlSpeed : (T.debugDefaultSpeed || 1);
  if (params.get('debug') === '0') document.body.classList.add('nodebug');
  console.info('[Aquarium] numbers from', CFG.source, 'balance checks:', JSON.stringify(G.balanceChecks()));

  // ------------------------------------------------------------ canvas setup
  const canvas = $('tank'), ctx = canvas.getContext('2d');
  const wrap = $('tank-wrap');
  let W = 300, H = 400, DPR = 1;
  function resize() {
    const r = wrap.getBoundingClientRect();
    DPR = Math.min(window.devicePixelRatio || 1, 2.5);
    W = Math.max(100, r.width); H = Math.max(100, r.height);
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    decor = makeDecor();
  }
  const sandTop = () => H * 0.86;

  // ------------------------------------------------------------ decor (static per size)
  let decor = null;
  function makeDecor() {
    const plants = [];
    const n = Math.max(5, Math.round(W / 60));
    for (let i = 0; i < n; i++) {
      const x = (i + 0.3 + Math.random() * 0.4) * (W / n);
      const blades = 2 + Math.floor(Math.random() * 3);
      for (let b = 0; b < blades; b++) {
        plants.push({ x: x + (b - blades / 2) * 6, h: H * (0.1 + Math.random() * 0.22), w: 5 + Math.random() * 5,
          hue: 110 + Math.random() * 40, light: 28 + Math.random() * 18, ph: Math.random() * 6.28 });
      }
    }
    const rocks = [];
    for (let i = 0; i < 4; i++) rocks.push({ x: Math.random() * W, w: 26 + Math.random() * 40, h: 14 + Math.random() * 18, c: 90 + Math.random() * 60 });
    const pebbles = [];
    for (let i = 0; i < W / 3; i++) pebbles.push({ x: Math.random() * W, y: sandTop() + 6 + Math.random() * (H - sandTop()), r: 0.8 + Math.random() * 2, c: 150 + Math.random() * 80 });
    return { plants, rocks, pebbles };
  }

  // ------------------------------------------------------------ animation state (not saved)
  const anim = new Map(); // fish id -> motion
  const pellets = [];  // food flakes: travel from the tap point to the fish they feed
  const floaters = [];
  const bubbles = [];
  let realTime = 0;

  function motion(f) {
    let m = anim.get(f.id);
    if (!m) {
      m = { x: f.x * W, y: f.y * H, vx: 0, vy: 0, tx: 0, ty: 0, face: Math.random() < 0.5 ? -1 : 1, faceAnim: 1,
        phase: Math.random() * 6, bob: Math.random() * 6, retarget: 0, pause: 0, scale: 1 };
      m.faceAnim = m.face;
      pickTarget(m, f);
      anim.set(f.id, m);
    }
    return m;
  }
  function fishLen(f) {
    return Math.min(W, H * 0.8) * 0.27 * (V.speciesSize[f.sp] || 1) * V.levelSizeScale[f.level - 1];
  }
  function bounds(f) {
    const L = fishLen(f);
    return { x0: L * 0.8, x1: W - L * 0.8, y0: H * 0.1 + L * 0.3, y1: sandTop() - L * 0.35 };
  }
  function pickTarget(m, f) {
    const b = bounds(f);
    // prefer mid-water, mostly horizontal travel
    m.tx = b.x0 + Math.random() * Math.max(1, b.x1 - b.x0);
    const yMid = (b.y0 + b.y1) / 2;
    m.ty = Math.min(b.y1, Math.max(b.y0, yMid + (Math.random() - 0.5) * (b.y1 - b.y0) * 0.95));
    m.retarget = 3 + Math.random() * 5;
  }
  const DEAD_RISE_SEC = 20; // game seconds to rise to the waterline (Art Director dead-fish pose)
  function stepDead(f, m, dt) {
    const L = fishLen(f), b = bounds(f);
    if (m.deadY0 == null) { m.deadY0 = m.y; m.drift = Math.random() < 0.5 ? -1 : 1; }
    const yTop = Math.max(H * 0.08, L * 0.36 + 4); // just under the waterline (top 6-10%), never behind the edge
    const p = f.diedAt == null ? 1 : Math.max(0, Math.min(1, (G.state.gameTime - f.diedAt) / DEAD_RISE_SEC));
    const e = p * p * (3 - 2 * p);
    m.y = m.deadY0 + (yTop - m.deadY0) * e;
    if (p >= 1) { // drift sideways ~3 px/s, turning back at the walls
      m.x += m.drift * 3 * dt;
      if (m.x < b.x0) { m.x = b.x0; m.drift = 1; } else if (m.x > b.x1) { m.x = b.x1; m.drift = -1; }
    }
    m.vx = 0; m.vy = 0;
    f.x = m.x / W; f.y = m.y / H;
  }
  function stepFish(f, dt) {
    const m = motion(f);
    if (f.state === 'DEAD') { stepDead(f, m, dt); return; }
    const hungry = f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY';
    const L = fishLen(f);
    const maxSpeed = (hungry ? 0.35 : 1) * (22 + L * 0.9);
    m.retarget -= dt;
    const dx = m.tx - m.x, dy = m.ty - m.y, dist = Math.hypot(dx, dy);
    if (m.pause > 0) m.pause -= dt;
    else if (dist < 8 || m.retarget <= 0) {
      if (Math.random() < 0.3) m.pause = 0.6 + Math.random() * 1.6;
      pickTarget(m, f);
    }
    // arrive steering with easing
    let desX = 0, desY = 0;
    if (m.pause <= 0 && dist > 0.01) {
      const ease = Math.min(1, dist / (L * 1.5 + 30));
      const sp = maxSpeed * (0.35 + 0.65 * ease * ease * (3 - 2 * ease));
      desX = (dx / dist) * sp; desY = (dy / dist) * sp * 0.6;
    }
    const k = Math.min(1, dt * 1.6);
    m.vx += (desX - m.vx) * k; m.vy += (desY - m.vy) * k;
    m.x += m.vx * dt; m.y += m.vy * dt;
    const b = bounds(f);
    m.x = Math.min(b.x1, Math.max(b.x0, m.x));
    m.y = Math.min(b.y1, Math.max(b.y0, m.y));
    if (Math.abs(m.vx) > 4) m.face = m.vx > 0 ? 1 : -1;
    m.faceAnim += (m.face - m.faceAnim) * Math.min(1, dt * 5);
    const spd = Math.hypot(m.vx, m.vy);
    m.phase += dt * (hungry ? 3 : 5 + spd * 0.12);
    m.bob += dt * (hungry ? 1.0 : 1.8);
    f.x = m.x / W; f.y = m.y / H;
  }

  // ------------------------------------------------------------ drawing
  function drawWater() {
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#3fc0e8'); g.addColorStop(0.35, '#1d8fc2'); g.addColorStop(1, '#0a4c78');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    // light rays
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 5; i++) {
      const x = ((i * 0.23 + 0.05) * W + Math.sin(realTime * 0.2 + i) * 20);
      const gr = ctx.createLinearGradient(0, 0, 0, H * 0.8);
      gr.addColorStop(0, 'rgba(255,255,255,0.10)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = gr;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + 40, 0); ctx.lineTo(x + 120, H * 0.8); ctx.lineTo(x + 30, H * 0.8); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
    // surface line
    ctx.fillStyle = 'rgba(255,255,255,0.18)';
    ctx.beginPath(); ctx.moveTo(0, 0);
    for (let x = 0; x <= W; x += 10) ctx.lineTo(x, 6 + Math.sin(x * 0.04 + realTime * 1.5) * 2.5);
    ctx.lineTo(W, 0); ctx.closePath(); ctx.fill();
  }
  function drawBack() {
    const st = sandTop();
    // back plants
    decor.plants.forEach((p, i) => {
      if (i % 2) return; drawPlant(p, 0.55);
    });
    // sand
    const g = ctx.createLinearGradient(0, st - 10, 0, H);
    g.addColorStop(0, '#e8d49a'); g.addColorStop(1, '#b89a5a');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.moveTo(0, st + 6);
    for (let x = 0; x <= W; x += 20) ctx.lineTo(x, st + Math.sin(x * 0.015) * 6);
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fill();
    decor.pebbles.forEach((p) => { ctx.fillStyle = `rgb(${p.c},${p.c * 0.85},${p.c * 0.6})`; ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill(); });
    decor.rocks.forEach((r) => {
      const rg = ctx.createLinearGradient(0, st - r.h, 0, st + 8);
      rg.addColorStop(0, `rgb(${r.c + 30},${r.c + 30},${r.c + 40})`); rg.addColorStop(1, `rgb(${r.c - 30},${r.c - 30},${r.c - 20})`);
      ctx.fillStyle = rg;
      ctx.beginPath(); ctx.ellipse(r.x, st + 4, r.w / 2, r.h, 0, Math.PI, 0); ctx.fill();
    });
  }
  function drawPlant(p, alpha) {
    const st = sandTop() + 4;
    const sway = Math.sin(realTime * 0.9 + p.ph) * p.h * 0.08;
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.fillStyle = `hsl(${p.hue},55%,${p.light}%)`;
    ctx.beginPath();
    ctx.moveTo(p.x - p.w / 2, st);
    ctx.quadraticCurveTo(p.x - p.w + sway * 0.5, st - p.h * 0.5, p.x + sway, st - p.h);
    ctx.quadraticCurveTo(p.x + p.w + sway * 0.5, st - p.h * 0.5, p.x + p.w / 2, st);
    ctx.closePath(); ctx.fill();
    ctx.strokeStyle = `hsla(${p.hue},60%,${p.light + 15}%,0.5)`; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(p.x, st); ctx.quadraticCurveTo(p.x + sway * 0.5, st - p.h * 0.5, p.x + sway, st - p.h); ctx.stroke();
    ctx.restore();
  }
  function drawBubbles(dt) {
    if (Math.random() < dt * 4) bubbles.push({ x: W * 0.9 + (Math.random() - 0.5) * 8, y: sandTop(), r: 1.5 + Math.random() * 3, w: Math.random() * 6 });
    ctx.strokeStyle = 'rgba(255,255,255,0.6)'; ctx.lineWidth = 1;
    for (let i = bubbles.length - 1; i >= 0; i--) {
      const b = bubbles[i];
      b.y -= dt * (30 + b.r * 10); b.w += dt * 3;
      const x = b.x + Math.sin(b.w) * 3;
      ctx.beginPath(); ctx.arc(x, b.y, b.r, 0, 7); ctx.stroke();
      if (b.y < 5) bubbles.splice(i, 1);
    }
  }
  function drawFishAll(dt) {
    G.state.fish.forEach((f) => {
      stepFish(f, dt);
      const m = anim.get(f.id);
      const L = fishLen(f);
      const hungry = f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY';
      const dead = f.state === 'DEAD';
      const bobY = dead ? Math.sin(realTime * Math.PI / 2) * 2 : Math.sin(m.bob) * (hungry ? 1.5 : 3); // dead: +-2 px on a 4 s cycle
      ctx.save();
      ctx.translate(m.x, m.y + bobY);
      if (selectedId === f.id) {
        ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.setLineDash([5, 4]); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.ellipse(0, 0, L * 0.75, L * 0.45, 0, 0, 7); ctx.stroke(); ctx.setLineDash([]);
      }
      const tilt = dead ? Math.sin(realTime * 0.9 + f.id) * 0.14 // +-8 degrees
        : Math.max(-0.35, Math.min(0.35, Math.atan2(m.vy, Math.abs(m.vx) + 10))) + (hungry ? 0.12 : 0);
      ctx.save();
      ctx.scale(m.faceAnim >= 0 ? Math.max(0.08, m.faceAnim) : Math.min(-0.08, m.faceAnim), 1);
      ctx.rotate(tilt);
      if (hungry) ctx.globalAlpha = 0.9;
      FishArt.drawFish(ctx, f.sp, L, m.phase, { hungry, dead, level: f.level });
      ctx.restore();
      drawStatusIcon(f, L);
      ctx.restore();
    });
  }
  /** small "fed" meter (taps received of taps needed) above a fish that still needs food (NUMBERS.md 3.5) */
  function drawFeedMeter(f, L) {
    const i = G.fishInfo(f); if (!i.needsFood) return;
    const n = i.taps, got = i.tapsFed, seg = n > 8 ? 5 : 8, gap = 2, w = n * seg + (n - 1) * gap, y = -L * 0.45 - 8;
    ctx.fillStyle = 'rgba(6,24,42,0.75)'; roundRect(-w / 2 - 3, y - 3, w + 6, 11, 5); ctx.fill();
    for (let k = 0; k < n; k++) {
      ctx.fillStyle = k < got ? '#3ddc84' : 'rgba(255,255,255,0.25)';
      roundRect(-w / 2 + k * (seg + gap), y, seg, 5, 2); ctx.fill();
    }
  }
  function drawStatusIcon(f, L) {
    if (f.state === 'DEAD') return;
    drawFeedMeter(f, L);
    let color = null, glyph = null;
    if (f.state === 'WAITING') { color = '#37c3ff'; glyph = 'food'; }
    else if (f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY') {
      const frac = f.deathLeft / G.deathSecFor(G.SPECIES[f.sp], f.level);
      color = frac < 0.33 ? '#ff3b3b' : '#ffa53b'; glyph = '!';
    }
    if (!color) return;
    const pulse = 1 + Math.sin(realTime * 6) * 0.08;
    const y = -L * 0.45 - 28, r = 9 * pulse;
    ctx.fillStyle = color; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(0, y, r, 0, 7); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-4, y + r - 2); ctx.lineTo(0, y + r + 5); ctx.lineTo(4, y + r - 2); ctx.fill();
    ctx.fillStyle = '#fff';
    if (glyph === '!') { ctx.font = '900 13px Nunito, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', 0, y + 1); }
    else { for (const [dx, dy] of [[-3, -2], [2, -3], [0, 2], [3, 2], [-3, 3]]) { ctx.beginPath(); ctx.arc(dx, y + dy, 1.4, 0, 7); ctx.fill(); } }
  }
  function drawPellets(dt) {
    for (let i = pellets.length - 1; i >= 0; i--) {
      const p = pellets[i];
      p.t += dt;
      const m = p.fishId != null ? anim.get(p.fishId) : null;
      if (m) { // flake glides/drops to its fish
        const dx = m.x - p.x, dy = m.y - p.y, d = Math.hypot(dx, dy), step = dt * 260;
        if (d <= step + 4) { if (p.full && p.gold > 0) floatText(`+${p.gold} gold`, m.x, m.y - 30, '#ffe07a'); /* v3 feed pays 0: no float at all */ pellets.splice(i, 1); continue; }
        p.x += dx / d * step; p.y += dy / d * step;
      } else { p.y += dt * 40; if (p.t > 2) { pellets.splice(i, 1); continue; } }
      ctx.fillStyle = p.c; ctx.beginPath(); ctx.ellipse(p.x, p.y, 3.2, 2.4, p.t * 3, 0, 7); ctx.fill();
    }
  }
  // ---- dirt: one look per stage (Art Director DIRT_AND_FISH_GROWTH.md s.1), deterministic from spot.seed
  function seeded(seed) { // mulberry32
    let t = Math.floor(seed * 9973) >>> 0;
    return () => { t = (t + 0x6D2B79F5) >>> 0; let r = Math.imul(t ^ (t >>> 15), 1 | t); r ^= r + Math.imul(r ^ (r >>> 7), 61 | r); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; };
  }
  function rgbaHex(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${Math.min(1, a).toFixed(3)})`; }
  // irregular blob edge radius at angle th; rough 2 = edge noise doubled (crust)
  function blobR(R, seed, rough, th) {
    return R * (0.84 + rough * (0.1 * Math.sin(th * 3 + seed) + 0.06 * Math.sin(th * 5 + seed * 2) + 0.03 * Math.sin(th * 11 + seed * 3)));
  }
  function blobPath(cx, cy, R, seed, rough) {
    ctx.beginPath();
    for (let i = 0; i <= 48; i++) {
      const th = (i / 48) * Math.PI * 2, rr = blobR(R, seed, rough, th);
      i ? ctx.lineTo(cx + Math.cos(th) * rr, cy + Math.sin(th) * rr) : ctx.moveTo(cx + Math.cos(th) * rr, cy + Math.sin(th) * rr);
    }
    ctx.closePath();
  }
  const SPOT_DRAW = {
    smudge(cx, cy, R, c, a, s) { // soft round film, no speckles
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
      g.addColorStop(0, rgbaHex(c, a)); g.addColorStop(0.6, rgbaHex(c, a * 0.85)); g.addColorStop(1, rgbaHex(c, 0));
      ctx.fillStyle = g; blobPath(cx, cy, R, s.seed, 0.5); ctx.fill();
    },
    dots(cx, cy, R, c, a, s, rng) { // cluster of 5-8 small round algae dots, dot r 0.15-0.3 R
      const n = 5 + Math.floor(rng() * 4);
      ctx.fillStyle = rgbaHex(c, a);
      for (let i = 0; i < n; i++) {
        const dr = R * (0.15 + rng() * 0.15), th = rng() * Math.PI * 2, d = Math.sqrt(rng()) * (R - dr);
        ctx.beginPath(); ctx.arc(cx + Math.cos(th) * d, cy + Math.sin(th) * d, dr, 0, 7); ctx.fill();
      }
    },
    drip(cx, cy, R, c, a, s, rng) { // 2.2:1 ellipse, long axis within +-30 deg of vertical, darker bottom edge
      ctx.save(); ctx.translate(cx, cy); ctx.rotate((rng() * 2 - 1) * Math.PI / 6);
      const g = ctx.createLinearGradient(0, -R, 0, R);
      g.addColorStop(0, rgbaHex(c, a)); g.addColorStop(0.72, rgbaHex(c, a)); g.addColorStop(0.86, rgbaHex(c, a + 0.08)); g.addColorStop(1, rgbaHex(c, a + 0.08));
      ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(0, 0, R / 2.2, R, 0, 0, 7); ctx.fill();
      ctx.restore();
    },
    hair(cx, cy, R, c, a, s, rng, look, k) { // irregular patch + 6-10 short wavy strands (1.5px, 0.3R) out of the edge
      ctx.fillStyle = rgbaHex(c, a); blobPath(cx, cy, R, s.seed, 1); ctx.fill();
      const n = 6 + Math.floor(rng() * 5);
      ctx.strokeStyle = rgbaHex(c, look.strandAlpha * k); ctx.lineWidth = 1.5; ctx.lineCap = 'round'; // strands ~50% (AD ruling 3); patch body stays look.alpha
      for (let i = 0; i < n; i++) {
        const th = ((i + rng() * 0.6) / n) * Math.PI * 2, rr = blobR(R, s.seed, 1, th) * 0.96, len = R * 0.3;
        const ux = Math.cos(th), uy = Math.sin(th), w = len * 0.18 * (rng() < 0.5 ? 1 : -1);
        const x0 = cx + ux * rr, y0 = cy + uy * rr;
        ctx.beginPath(); ctx.moveTo(x0, y0);
        ctx.bezierCurveTo(x0 + ux * len * 0.33 - uy * w, y0 + uy * len * 0.33 + ux * w,
          x0 + ux * len * 0.66 + uy * w, y0 + uy * len * 0.66 - ux * w, x0 + ux * len, y0 + uy * len);
        ctx.stroke();
      }
    },
    crust(cx, cy, R, c, a, s, rng) { // rough brown crust (edge noise doubled) + 10-14 dark speckles
      ctx.fillStyle = rgbaHex(c, a); blobPath(cx, cy, R, s.seed, 2); ctx.fill();
      const n = 10 + Math.floor(rng() * 5);
      ctx.fillStyle = rgbaHex('#3A3418', Math.min(1, a * 1.6));
      for (let i = 0; i < n; i++) {
        const th = rng() * Math.PI * 2, d = Math.sqrt(rng()) * R * 0.6, sr = R * (0.025 + rng() * 0.04);
        ctx.beginPath(); ctx.ellipse(cx + Math.cos(th) * d, cy + Math.sin(th) * d, sr * 1.3, sr, th, 0, 7); ctx.fill();
      }
    },
  };
  // ---- tank-wide dirt layer (Art Director v2): stages 2-4 flat wash, stage 5 green film (config VISUAL.dirtLayer)
  const film = { cv: null, x: null, img: null, cols: 0, rows: 0, a: null, cap: null, mid: null, strength: 0 };
  /** fill alpha of one spot as drawn (look alpha x rub fade; drip bottom edge +0.08) */
  function spotFillAlpha(s) {
    const look = V.dirtStages[Math.max(1, Math.min(5, s.stage || 1)) - 1];
    const k = Math.max(0.12, s.grime / s.grime0);
    return look.alpha * k + (look.look === 'drip' ? 0.08 : 0);
  }
  function drawFilm(strength) {
    const F = V.dirtFilm, cell = F.cellPx;
    const cols = Math.max(4, Math.ceil(W / cell)), rows = Math.max(4, Math.ceil(H / cell));
    if (!film.cv || film.cols !== cols || film.rows !== rows) {
      film.cv = document.createElement('canvas'); film.cv.width = cols; film.cv.height = rows;
      film.x = film.cv.getContext('2d'); film.img = film.x.createImageData(cols, rows);
      Object.assign(film, { cols, rows, a: new Float32Array(cols * rows), cap: new Float32Array(cols * rows), mid: new Uint8Array(cols * rows) });
    }
    const d = film.img.data, spots = G.state.dirt.spots.map((s) => ({ x: s.x * W, y: s.y * H, r: s.r * W * 1.25, a: spotFillAlpha(s) }));
    const drift = realTime / F.cloudDriftSec; // tank widths
    for (let j = 0; j < rows; j++) {
      const py = (j + 0.5) * H / rows, ny = py / H;
      for (let i = 0; i < cols; i++) {
        const px = (i + 0.5) * W / cols, nx = px / W, idx = j * cols + i;
        const dist = Math.max(Math.abs(nx - 0.5), Math.abs(ny - 0.5)) * 2; // 0 centre .. 1 edges and corners
        const mid = dist <= F.guardZone;
        const t = Math.max(0, Math.min(1, (dist - F.guardZone) / (1 - F.guardZone)));
        let a = F.centre + (F.edge - F.centre) * t * t * (3 - 2 * t);
        const u = (nx - drift) * 6.283, v = ny * 6.283 * H / W;
        a += F.cloud * (Math.sin(u * 1.1 + v * 0.6 + 1.3) + Math.sin(-u * 0.7 + v * 1.3 + 4.1) + 0.6 * Math.sin(u * 1.9 - v * 1.7 + 2.2)) / 2.6;
        let rgb = F.rgb;
        const scum = ny < F.scumFrac ? 1 : ny < F.scumFrac * 1.4 ? 1 - (ny - F.scumFrac) / (F.scumFrac * 0.4) : 0; // soft bottom edge
        if (scum > 0) { a = a + (F.scumAlpha - a) * scum; rgb = F.scumRgb; }
        let cap = 1;
        if (mid) { // readability guard: film + one spot <= guardMax in the middle of the tank
          let sMax = 0;
          for (const sp of spots) if (Math.hypot(px - sp.x, py - sp.y) < sp.r && sp.a > sMax) sMax = sp.a;
          cap = sMax >= F.guardMax ? 0 : 1 - (1 - F.guardMax) / (1 - sMax);
          a = Math.min(a, cap);
        }
        a = Math.max(0, a) * strength;
        film.a[idx] = a; film.cap[idx] = cap; film.mid[idx] = mid ? 1 : 0;
        d[idx * 4] = rgb[0]; d[idx * 4 + 1] = rgb[1]; d[idx * 4 + 2] = rgb[2]; d[idx * 4 + 3] = Math.round(a * 255);
      }
    }
    film.x.putImageData(film.img, 0, 0);
    ctx.save(); ctx.imageSmoothingEnabled = true; ctx.drawImage(film.cv, 0, 0, W, H); ctx.restore();
  }
  function drawDirtLayer() {
    const stage = G.dirtStage(), layer = stage > 0 ? V.dirtLayer[stage - 1] : null;
    film.strength = layer && layer.film ? G.dirtFilm() : 0; // fades with rub progress, gone when the last spot clears
    if (!layer) return;
    if (layer.wash) { ctx.fillStyle = layer.wash; ctx.fillRect(0, 0, W, H); }
    if (layer.film && film.strength > 0) drawFilm(film.strength);
  }
  function drawSpots() {
    // array order = spawn order, so older spots are drawn first and newer ones on top (source-over)
    G.state.dirt.spots.forEach((s) => {
      const look = V.dirtStages[Math.max(1, Math.min(5, s.stage || 1)) - 1];
      const k = Math.max(0.12, s.grime / s.grime0); // fades while rubbed
      const color = look.tintHalf && Math.floor(s.seed) % 2 ? mixHex(look.color, look.tintHalf, look.tintMix) : look.color;
      SPOT_DRAW[look.look](s.x * W, s.y * H, s.r * W, color, look.alpha * k, s, seeded(s.seed), look, k);
    });
  }
  function mixHex(a, b, t) {
    const p = parseInt(a.slice(1), 16), q = parseInt(b.slice(1), 16), c = (sh) => Math.round(((p >> sh) & 255) * (1 - t) + ((q >> sh) & 255) * t);
    return '#' + ((c(16) << 16) | (c(8) << 8) | c(0)).toString(16).padStart(6, '0');
  }
  function drawGlass() {
    const g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, 'rgba(255,255,255,0.10)'); g.addColorStop(0.3, 'rgba(255,255,255,0)'); g.addColorStop(0.7, 'rgba(255,255,255,0)'); g.addColorStop(1, 'rgba(255,255,255,0.06)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }
  function spongeLift() { return pointer.touch ? W * V.spongeRadiusFrac * V.spongeTouchLiftFrac : 0; }
  function drawSponge() {
    if (tool !== 'sponge' || !pointer.inside) return;
    const r = W * V.spongeRadiusFrac;
    ctx.save(); ctx.translate(pointer.x, pointer.y - spongeLift()); ctx.rotate(-0.2);
    ctx.fillStyle = '#ffd84a'; ctx.strokeStyle = '#b08d12'; ctx.lineWidth = 2;
    roundRect(-r, -r * 0.7, r * 2, r * 1.4, 8); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#3aa35a'; roundRect(-r, r * 0.25, r * 2, r * 0.45, 5); ctx.fill();
    ctx.fillStyle = '#c8a21a';
    for (const [x, y, rr] of [[-0.5, -0.3, 0.12], [0.1, -0.1, 0.15], [0.55, -0.35, 0.1], [-0.1, -0.45, 0.08]]) { ctx.beginPath(); ctx.arc(x * r, y * r, rr * r, 0, 7); ctx.fill(); }
    if (pointer.down) { ctx.fillStyle = 'rgba(255,255,255,0.7)'; for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc((Math.random() - 0.5) * r * 2.2, (Math.random() - 0.5) * r * 1.6, 2 + Math.random() * 3, 0, 7); ctx.fill(); } }
    ctx.restore();
  }
  function roundRect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function drawFloaters(dt) {
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (let i = floaters.length - 1; i >= 0; i--) {
      const f = floaters[i];
      f.t += dt; f.y -= dt * 28;
      ctx.globalAlpha = Math.max(0, 1 - f.t / 1.8);
      ctx.font = `900 ${f.big ? 22 : 16}px Nunito, sans-serif`;
      ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(0,0,0,0.5)'; ctx.strokeText(f.text, f.x, f.y);
      ctx.fillStyle = f.color || '#ffd84a'; ctx.fillText(f.text, f.x, f.y);
      ctx.globalAlpha = 1;
      if (f.t > 1.8) floaters.splice(i, 1);
    }
  }
  const floatLog = []; // every float text shown (last 50), for tests
  function floatText(text, x, y, color, big) { floaters.push({ text, x, y, color, big, t: 0 }); floatLog.push(text); if (floatLog.length > 50) floatLog.shift(); }

  // ------------------------------------------------------------ HUD / UI
  const goldEl = $('gold'), foodEl = $('food');
  let lastGold = null, lastFood = null;
  function bump(el) { el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump'); setTimeout(() => el.classList.remove('bump'), 160); }
  function updateHUD() {
    const s = G.state;
    if (s.gold !== lastGold) { goldEl.textContent = s.gold; if (lastGold !== null) bump($('res-gold')); lastGold = s.gold; }
    if (s.food !== lastFood) { foodEl.textContent = s.food; if (lastFood !== null) bump($('res-food')); lastFood = s.food; }
    const st = G.dirtStage();
    const bar = $('dirt-bar'); bar.dataset.stage = st;
    [...bar.children].forEach((el, i) => el.classList.toggle('on', i < st));
    $('dirt-label').textContent = st === 0 ? 'Dirt: clean' : `Dirt: stage ${st} of ${T.dirt.stageAtSec.length}`;
    const ti = G.tankInfo();
    $('tank-label').textContent = ti.max ? `Tank Lv ${ti.level} · ${ti.xp} XP · Decorations coming soon` : `Tank Lv ${ti.level} · ${ti.xp} / ${ti.next} XP`;
    $('tank-xpbar').style.width = (ti.max ? 100 : Math.min(100, ((ti.xp - ti.cur) / (ti.next - ti.cur)) * 100)).toFixed(1) + '%';
    $('buyfood-label').textContent = `+${T.foodPack.food} food · ${T.foodPack.gold}g`;
    $('btn-buyfood').disabled = s.gold < T.foodPack.gold;
    $('tankover').hidden = !G.tankOver();
    // hint line
    let hint = '';
    if (!s.fish.length) hint = 'Open the Shop and buy a baby fish';
    else if (tool === 'food') hint = st >= 1 ? 'Dirty glass: pick the Sponge' : 'Tap near a hungry fish to feed it';
    else if (tool === 'sponge') hint = st >= 1 ? 'Rub the dirty spots' : 'The glass is clean';
    else if (s.fish.some((f) => f.state === 'WAITING')) hint = 'New fish! Pick Food and tap the tank to start growth';
    else hint = 'Tap a fish to see its details';
    $('hint').textContent = $('dirt-callout').hidden ? hint : ''; // one message at a time: the dirt-bar callout wins
    $('dbg-clock').textContent = `game ${clock(s.gameTime)} · ×${s.speed}`;
    document.querySelectorAll('#speed-btns .dbg').forEach((b) => b.classList.toggle('on', +b.dataset.speed === s.speed));
  }
  /** NUMBERS.md 2: "1h 12m" when an hour or more is left, "12m 30s" when less */
  function fmt(sec) {
    sec = Math.max(0, Math.ceil(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s).padStart(2, '0')}s`;
  }
  function clock(sec) { // debug bar only (game time), never used for dirt
    sec = Math.max(0, Math.floor(sec)); const d = Math.floor(sec / 86400), h = Math.floor(sec / 3600) % 24, m = Math.floor(sec / 60) % 60;
    return `${d ? d + 'd ' : ''}${h}h ${String(m).padStart(2, '0')}m`;
  }
  function realNote(sec) { return G.state.speed > 1 ? ` (≈${fmt(sec / G.state.speed)} real at ×${G.state.speed})` : ''; }

  function toast(text, kind) {
    const el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.textContent = text;
    const box = $('toasts'); box.appendChild(el);
    while (box.children.length > 3) box.removeChild(box.firstChild);
    setTimeout(() => el.classList.add('out'), 2200);
    setTimeout(() => el.remove(), 2700);
  }
  let calloutTimer = 0;
  function dirtyCallout() {
    const c = $('dirt-callout'); c.hidden = false;
    const w = $('dirt-wrap'); w.classList.remove('shake'); void w.offsetWidth; w.classList.add('shake');
    clearTimeout(calloutTimer); calloutTimer = setTimeout(() => { c.hidden = true; }, 2200);
  }

  // tools
  let tool = 'hand';
  function setTool(t) {
    tool = t;
    document.querySelectorAll('.tool[data-tool]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tool === t)));
    wrap.dataset.tool = t;
    if (t !== 'hand') closePanel();
    closeShop();
  }
  document.querySelectorAll('.tool[data-tool]').forEach((b) => b.addEventListener('click', () => setTool(b.dataset.tool)));
  $('btn-shop').addEventListener('click', () => ($('shop').hidden ? openShop() : closeShop()));
  $('btn-buyfood').addEventListener('click', () => { G.buyFood(); });

  // ------------------------------------------------------------ fish panel
  let selectedId = null;
  function openPanel(id) { selectedId = id; closeShop(); $('panel').hidden = false; renderPanel(true); }
  function closePanel() { selectedId = null; $('panel').hidden = true; }
  function renderPanel(force) {
    if (selectedId == null) return;
    const f = G.state.fish.find((x) => x.id === selectedId);
    if (!f) { closePanel(); return; }
    const i = G.fishInfo(f), sp = i.species;
    const panel = $('panel');
    panel.classList.toggle('dead', i.dead);
    $('p-name').textContent = sp.name;
    $('p-latin').textContent = sp.latin;
    $('p-rarity').textContent = sp.rarity[0].toUpperCase() + sp.rarity.slice(1);
    $('p-level').textContent = i.dead ? 'Dead' : f.level >= T.maxLevel ? `Adult (L${f.level})` : `Level ${f.level} / ${T.maxLevel}`;
    const btn = $('p-sell');
    btn.dataset.fish = f.id;
    if (i.dead) { // NUMBERS.md 9.12: "Dead" and one button, Remove (0 gold), no confirm, no selling
      $('p-dead').textContent = 'Dead';
      btn.className = 'btn wide danger'; btn.dataset.action = 'remove';
      btn.textContent = `Remove (${T.deadFish ? T.deadFish.removeGold : 0} gold)`;
    } else {
      const gEl = $('p-growth'), hEl = $('p-hunger'), bar = $('p-growbar');
      gEl.className = 'v'; hEl.className = 'v';
      bar.classList.toggle('paused', f.state === 'HUNGRY');
      bar.style.width = (i.progressFrac * 100).toFixed(1) + '%';
      const fedTxt = `${i.tapsFed}/${i.taps} fed`;
      if (f.state === 'WAITING') { gEl.textContent = 'Not started'; gEl.classList.add('warn'); hEl.textContent = `Waiting for first feed · ${fedTxt}`; hEl.classList.add('warn'); }
      else if (f.state === 'GROWING') {
        gEl.textContent = `L${f.level} · next level in ${fmt(i.growLeft)}${realNote(i.growLeft)}`;
        const hungerIn = f.hungerDone ? null : i.growNeed * T.hungerPoint - f.progress;
        hEl.textContent = hungerIn != null ? `Fed · hungry in ${fmt(hungerIn)}` : 'Fed'; hEl.classList.add('ok');
      } else if (f.state === 'HUNGRY') {
        gEl.textContent = `L${f.level} · Growth paused`; gEl.classList.add('danger');
        hEl.textContent = `Hungry! ${fedTxt} · Growth paused · dies in ${fmt(i.deathLeft)}${realNote(i.deathLeft)}`; hEl.classList.add('danger');
      } else if (f.state === 'ADULT') {
        gEl.textContent = `Adult (L${f.level})`;
        hEl.textContent = `Fed · hungry in ${fmt(i.adultHungerIn)}`; hEl.classList.add('ok');
      } else { // ADULT_HUNGRY
        gEl.textContent = `Adult (L${f.level})`;
        hEl.textContent = `Hungry! ${fedTxt} · dies in ${fmt(i.deathLeft)}${realNote(i.deathLeft)}`; hEl.classList.add('danger');
      }
      $('p-portion').textContent = `${i.portion} food · ${i.taps} tap${i.taps > 1 ? 's' : ''}`;
      btn.className = 'btn wide ' + (f.level === 1 ? 'danger' : 'sell'); btn.dataset.action = 'sell';
      btn.textContent = f.level === 1 ? 'Release (0 gold)' : `Sell for ${i.sell} gold`;
    }
    // portrait
    const pc = $('panel-portrait'), p = pc.getContext('2d');
    p.setTransform(1, 0, 0, 1, 0, 0); p.clearRect(0, 0, pc.width, pc.height);
    p.translate(pc.width * 0.55, pc.height * 0.52);
    FishArt.drawFish(p, f.sp, pc.width * 0.5, i.dead ? 0 : realTime * 5, { hungry: f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY', dead: i.dead, level: f.level });
  }
  $('p-sell').addEventListener('click', () => {
    const id = +$('p-sell').dataset.fish;
    const f = G.state.fish.find((x) => x.id === id);
    if (!f) return;
    if (f.state === 'DEAD') { G.removeDead(id); closePanel(); return; } // no confirm for a dead fish
    if (f.level === 1) {
      confirmBox(`Release this ${G.SPECIES[f.sp].name}? Level 1 fish give 0 gold.`, 'Release (0 gold)', () => { G.sell(id); closePanel(); });
    } else { G.sell(id); closePanel(); }
  });
  function confirmBox(text, yesLabel, onYes) {
    $('confirm-text').textContent = text; $('confirm-yes').textContent = yesLabel;
    $('confirm').hidden = false;
    $('confirm-yes').onclick = () => { $('confirm').hidden = true; onYes(); };
    $('confirm-no').onclick = () => { $('confirm').hidden = true; };
  }
  document.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => (b.dataset.close === 'panel' ? closePanel() : closeShop())));

  // ------------------------------------------------------------ shop
  function openShop() { closePanel(); $('shop').hidden = false; renderShop(); }
  function closeShop() { $('shop').hidden = true; }
  function renderShop() {
    const list = $('shop-list');
    if (!list.children.length) {
      T.species.forEach((sp) => {
        const card = document.createElement('div'); card.className = 'card'; card.dataset.species = sp.id;
        const total = sp.growSec.reduce((a, b) => a + b, 0);
        card.innerHTML = `<canvas width="240" height="96"></canvas><div class="n">${sp.name}</div><div class="l">${sp.latin}</div>
          <div class="s">Baby · adult in ${fmt(total)} · sells up to ${G.sellPrice(sp, T.maxLevel)}g</div>
          <button class="btn buy" data-buy="${sp.id}"><svg><use href="#i-coin"/></svg><span class="price">${sp.price}</span><span class="lbl"></span></button>`;
        list.appendChild(card);
        const c = card.querySelector('canvas').getContext('2d');
        c.translate(120, 50); FishArt.drawFish(c, sp.id, 120, 0.6, {});
        card.querySelector('button').addEventListener('click', () => {
          const f = G.buyFish(sp.id);
          if (f) { toast(`${sp.name} added. Feed it to start growth!`, 'good'); renderShop(); }
        });
      });
    }
    const full = G.state.fish.length >= T.tankCapacity; // dead fish take a slot until removed
    list.querySelectorAll('button[data-buy]').forEach((b) => {
      const sp = G.SPECIES[b.dataset.buy];
      const locked = !G.isUnlocked(sp);
      const poor = G.state.gold < sp.price;
      b.disabled = locked || full || poor;
      b.closest('.card').classList.toggle('locked', locked);
      b.classList.toggle('poor', poor && !full && !locked);
      b.querySelector('.price').hidden = locked; b.querySelector('svg').style.display = locked ? 'none' : '';
      b.querySelector('.lbl').textContent = locked ? `🔒 Tank level ${sp.unlockTankLevel}` : full ? ' · Tank full' : '';
    });
    const ti = G.tankInfo(), dead = G.state.fish.length - G.living();
    $('shop-tank').textContent = ti.max ? `Tank Lv ${ti.level} · ${ti.xp} XP` : `Tank Lv ${ti.level} · ${ti.xp} / ${ti.next} XP`;
    $('shop-tankbar').style.width = (ti.max ? 100 : Math.min(100, ((ti.xp - ti.cur) / (ti.next - ti.cur)) * 100)).toFixed(1) + '%';
    $('shop-note').textContent = `Tank: ${G.state.fish.length} / ${T.tankCapacity} fish${dead ? ` (${dead} dead: tap to remove)` : ''}. Tank level ${T.tank.maxLevel}: Decorations coming soon. Numbers: Designer v${T.version || 2} (config.js ← tuning.json).`;
  }

  // ------------------------------------------------------------ input on tank
  const pointer = { x: 0, y: 0, down: false, inside: false, id: null, lx: 0, ly: 0 };
  function local(e) { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  function hitFish(x, y) {
    const fish = G.state.fish;
    for (let i = fish.length - 1; i >= 0; i--) {
      const m = anim.get(fish[i].id); if (!m) continue;
      const L = fishLen(fish[i]);
      const dx = (x - m.x) / (L * 0.7 + 10), dy = (y - m.y) / (L * 0.35 + 12);
      if (dx * dx + dy * dy <= 1) return fish[i];
    }
    // forgiving tap: nearest fish centre within 44px (moving fish are hard to hit; Playtester pass 1 note 2)
    let best = null, bestD = 44;
    for (const f of fish) { const m = anim.get(f.id); if (!m) continue; const d = Math.hypot(x - m.x, y - m.y); if (d < bestD) { bestD = d; best = f; } }
    return best;
  }
  canvas.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    const p = local(e);
    const touch = e.pointerType === 'touch' || e.pointerType === 'pen';
    Object.assign(pointer, { touch, x: p.x, y: p.y, lx: p.x, ly: p.y - (touch && tool === 'sponge' ? W * V.spongeRadiusFrac * V.spongeTouchLiftFrac : 0), down: true, inside: true, id: e.pointerId });
    try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
    if (!$('shop').hidden) closeShop();
    if (tool === 'hand') {
      const f = hitFish(p.x, p.y);
      if (f) openPanel(f.id); else closePanel();
    } else if (tool === 'food') {
      const r = G.feedTap(p.x / W, p.y / H, W, H); // 1 food per tap to the nearest fish that still needs food
      if (r.ok) pellets.push({ x: p.x, y: p.y, t: 0, fishId: r.fish.id, full: r.full, gold: r.gold, c: ['#d9772f', '#b8542a', '#e8a13a'][G.state.stats.taps % 3] });
    } else if (tool === 'sponge') {
      rubTo(p.x, p.y - spongeLift());
    }
  });
  canvas.addEventListener('pointermove', (e) => {
    const p = local(e);
    pointer.inside = true;
    if (!pointer.down) pointer.touch = e.pointerType === 'touch' || e.pointerType === 'pen';
    if (pointer.down && e.pointerId === pointer.id && tool === 'sponge') {
      // use coalesced events for smooth fast rubbing
      const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
      (evs.length ? evs : [e]).forEach((ce) => { const q = local(ce); rubTo(q.x, q.y - spongeLift()); });
    }
    pointer.x = p.x; pointer.y = p.y;
  });
  function endPointer(e) { if (e.pointerId === pointer.id) { pointer.down = false; pointer.id = null; } }
  canvas.addEventListener('pointerup', endPointer);
  canvas.addEventListener('pointercancel', endPointer);
  canvas.addEventListener('pointerleave', () => { if (!pointer.down) pointer.inside = false; });
  function rubTo(x, y) {
    const r = G.rub(pointer.lx / W, pointer.ly / H, x / W, y / H, W, H, W * V.spongeRadiusFrac);
    pointer.lx = x; pointer.ly = y;
    if (r.cleaned) floatText(`Sparkling! +${r.gold} gold`, x, y - 20, '#9fffd0', true);
  }

  // ------------------------------------------------------------ game events
  G.on((type, d) => {
    const m = d.fish ? anim.get(d.fish.id) : null;
    const fx = m ? m.x : W / 2, fy = m ? m.y - 20 : H / 2;
    const name = d.fish ? G.SPECIES[d.fish.sp].name : '';
    switch (type) {
      case 'levelup':
        if (d.gold) floatText(`+${d.gold} gold`, fx - 30, fy - 10, '#ffd84a', true);
        if (d.xp) floatText(`+${d.xp} XP`, fx + 34, fy - 10, '#9fdcff', true);
        toast(d.fish.level >= T.maxLevel ? `${name} is now an adult (L${d.fish.level})! +${d.gold} gold` : `${name} reached level ${d.fish.level}! +${d.gold} gold`, 'good');
        break;
      case 'tanklevel':
        toast(d.unlocks.length ? `Tank level ${d.level}! ${d.unlocks.map((id) => G.SPECIES[id].name).join(', ')} unlocked` : `Tank level ${d.level}! Decorations coming soon`, 'good');
        break;
      case 'hungry': toast(`${name} is hungry!`, 'bad'); break;
      case 'death': toast(`${name} died`, 'bad'); break; // stays in the tank belly-up until removed
      case 'removed': anim.delete(d.fish.id); toast(`Removed ${name} (${d.gold} gold)`); break;
      case 'feedblocked': dirtyCallout(); break; // Maksims: ONLY the message by the dirt bar, no centre toast
      case 'feedfail': toast(d.reason === 'nofood' ? 'Out of food' : "Nobody's hungry", d.reason === 'nofood' ? 'bad' : ''); break;
      case 'cleaned': toast(`Tank clean! +${d.gold} gold${d.xp ? ` · +${d.xp} XP` : ''}`, 'good'); break;
      case 'sold':
        anim.delete(d.fish.id);
        toast(d.gold ? `Sold ${name} for ${d.gold} gold` : `Released ${name} (0 gold)`, d.gold ? 'good' : '');
        break;
      case 'foodbought': toast(`+${d.food} food (−${d.gold} gold)`); break;
      case 'grant': toast(`Starter grant: gold topped up to ${d.gold}`, 'good'); break;
      case 'msg': toast(d.text, 'bad'); break;
      case 'reset': anim.clear(); pellets.length = 0; closePanel(); closeShop(); $('away').hidden = true; break;
      default: break;
    }
    if (!$('shop').hidden) renderShop();
  });

  // ------------------------------------------------------------ debug bar
  T.debugSpeeds.forEach((s) => {
    const b = document.createElement('button'); b.className = 'dbg'; b.dataset.speed = s; b.textContent = `×${s}`;
    b.addEventListener('click', () => { G.state.speed = s; G.save(); });
    $('speed-btns').appendChild(b);
  });
  $('btn-newtank').addEventListener('click', () => {
    const keep = G.state.speed; G.reset(); G.state.speed = keep; G.save();
    $('tankover').hidden = true; closePanel(); toast('New tank started', 'good');
  });
  $('dbg-gold').textContent = '+100g';
  $('dbg-gold').addEventListener('click', () => { G.state.gold += 100; toast('Debug: +100 gold'); });
  $('dbg-reset').addEventListener('click', () => {
    confirmBox('Reset the save and start over?', 'Reset', () => {
      const keep = G.state.speed; G.reset(); G.state.speed = keep; G.save(); toast('Save reset');
    });
  });

  // ------------------------------------------------------------ main loop
  let last = performance.now();
  let panelAcc = 0;
  function frame(now) {
    let dtReal = (now - last) / 1000; last = now;
    if (dtReal < 0) dtReal = 0;
    // Hidden tab: rAF stops; on return we catch up the real elapsed time (NUMBERS.md §8.9).
    if (dtReal > 5) { // tab was hidden / device asleep: replay like offline time and summarise
      const r = G.catchUp(dtReal * G.state.speed);
      if (r.sec >= 60) showAway(r);
    } else G.tick(dtReal * G.state.speed);
    const dtAnim = Math.min(dtReal, 0.05);
    realTime += dtAnim;

    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    drawWater();
    drawBack();
    drawBubbles(dtAnim);
    decor.plants.forEach((p, i) => { if (i % 2) drawPlant(p, 0.9); });
    drawPellets(dtAnim);
    drawFishAll(dtAnim);
    drawGlass();
    drawDirtLayer(); // in front of the fish (dead ones too), behind the spots
    drawSpots();
    drawSponge();
    drawFloaters(dtAnim);

    updateHUD();
    panelAcc += dtReal;
    if (panelAcc > 0.2) { panelAcc = 0; renderPanel(); }
    requestAnimationFrame(frame);
  }

  // save loop: periodic + on hide/unload. Offline time is NOT simulated (pause while closed).
  setInterval(() => G.save(), V.saveEveryMs);
  document.addEventListener('visibilitychange', () => { if (document.hidden) G.save(); });
  window.addEventListener('pagehide', () => G.save());
  window.addEventListener('resize', resize);
  if (window.ResizeObserver) new ResizeObserver(resize).observe(wrap);

  // ------------------------------------------------------------ "while you were away" summary (NUMBERS.md 9.2)
  function showAway(r) {
    if (!r) return;
    $('away-time').textContent = `(${fmt(r.sec)}${r.realSec != null && G.state.speed !== 1 && r.realSec !== r.sec ? ' game time' : ''})`;
    const ul = $('away-list'); ul.innerHTML = '';
    r.lines.forEach((t) => { const li = document.createElement('li'); li.textContent = t[0].toUpperCase() + t.slice(1); ul.appendChild(li); });
    $('away').hidden = false;
  }
  $('away-ok').addEventListener('click', () => { $('away').hidden = true; });

  resize();
  setTool('hand');
  if (awaySummary && awaySummary.sec >= 60) showAway(awaySummary);
  G.save();
  requestAnimationFrame((t) => { last = t; frame(t); });

  // Test/debug hook (read-mostly): used by tests/verify.py
  window.AQ = {
    game: G,
    fishScreen(id) { const m = anim.get(id); return m ? { x: m.x, y: m.y } : null; },
    showAway,
    pinFish(id, nx, ny) { // screenshot/test hook: park a living fish at (nx, ny) of the tank
      const f = G.state.fish.find((x) => x.id === id); if (!f) return false;
      const m = motion(f); m.x = nx * W; m.y = ny * H; m.tx = m.x; m.ty = m.y; m.vx = 0; m.vy = 0; m.pause = 1e9; m.retarget = 1e9;
      f.x = nx; f.y = ny; return true;
    },
    filmInfo() { // test hook: last drawn film grid (alpha per cell, guard cap, middle-zone flag)
      if (!film.strength || !film.a) return { strength: film.strength, max: 0 };
      let max = 0, midMax = 0; for (let i = 0; i < film.a.length; i++) { max = Math.max(max, film.a[i]); if (film.mid[i]) midMax = Math.max(midMax, film.a[i]); }
      return { strength: film.strength, max, midMax, cols: film.cols, rows: film.rows };
    },
    guardCheck() { // worst "film + one spot" combined opacity in the middle zone, using each spot's own fill alpha
      if (!film.strength || !film.a) return { worst: 0 };
      let worst = 0; const spots = G.state.dirt.spots.map((s) => ({ x: s.x * W, y: s.y * H, r: s.r * W * 1.25, a: spotFillAlpha(s) }));
      for (let j = 0; j < film.rows; j++) for (let i = 0; i < film.cols; i++) {
        const idx = j * film.cols + i; if (!film.mid[idx]) continue;
        const px = (i + 0.5) * W / film.cols, py = (j + 0.5) * H / film.rows;
        for (const sp of spots) if (Math.hypot(px - sp.x, py - sp.y) < sp.r) worst = Math.max(worst, 1 - (1 - film.a[idx]) * (1 - sp.a));
        worst = Math.max(worst, film.a[idx]);
      }
      return { worst: +worst.toFixed(4) };
    },
    spotsScreen() { return G.state.dirt.spots.map((s) => ({ x: s.x * W, y: s.y * H, r: s.r * W, grime: s.grime, stage: s.stage, look: V.dirtStages[s.stage - 1].look, over: s.over })); },
    size() { return { W, H }; },
    fishLen(sp, level) { return fishLen({ sp, level }); }, // tank render length (CSS px) of a fish
    floats(clear) { const out = floatLog.slice(); if (clear) floatLog.length = 0; return out; }, // test hook: float texts shown since the last clear

    setTool,
  };
})();
