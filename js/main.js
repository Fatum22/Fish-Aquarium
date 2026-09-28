/* Aquarium UI (landscape v4, Art Director LANDSCAPE_LAYOUT_V4.md): rendering, swimming, input, side panels, shop,
   decorations + edit mode, rotate screen, save loop. Game rules live in game.js. */
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

  // ------------------------------------------------------------ canvas + tank geometry (AD v4 4)
  const canvas = $('tank');
  let ctx = canvas.getContext('2d'); // swapped briefly to draw shop card previews with the same code
  const wrap = $('tank-wrap');
  let W = 752, H = 302, DPR = 1;
  let SURF = 21, WATER_H = 281, SAND = 260, INSET = 26; // water surface y, water height, sand top y, glass-line inset
  const LARGE = () => window.innerHeight >= 600;
  function geom() {
    SURF = Math.max(V.airMinPx, H * V.airFrac);          // air gap: top 7% (min 16 px)
    WATER_H = H - SURF;
    SAND = Math.min(H * V.sandFrac, H - V.sandMinPx);     // sand top at 86% (band >= 36 px)
    INSET = W * V.glassInsetFrac;                          // sand back corners / glass edge lines
  }
  function resize() {
    const r = wrap.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return; // upright: #app is display:none, keep the last landscape geometry
    DPR = Math.min(window.devicePixelRatio || 1, 2.5);
    W = Math.max(100, r.width); H = Math.max(100, r.height);
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    geom();
    pebbles = makePebbles();
    // toasts start just under the dead-fish band (6-10% of the water height below the surface)
    $('toasts').style.top = `${Math.round(SURF + WATER_H * 0.10 + 6)}px`;
    if (selDecor) placeMenu();
  }
  const sandTop = () => SAND;
  const floorY = (d) => SAND + (H - SAND) * V.decorFloorBand * d.y; // decoration base y (top 60% of the sand band)

  let pebbles = [];
  function makePebbles() { // sand texture only (the old random plants and rocks are gone: AD v4 7)
    const out = [], rng = seeded(7);
    for (let i = 0; i < W / 3; i++) out.push({ x: rng() * W, y: SAND + 6 + rng() * (H - SAND), r: 0.8 + rng() * 2, c: 150 + rng() * 80 });
    return out;
  }

  // ------------------------------------------------------------ animation state (not saved)
  const anim = new Map(); // fish id -> motion
  const pellets = [];  // food flakes of the current taps
  const flakeStats = { spawned: 0, showers: 0, eaten: 0 }; // test hook counters
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
  /** fish length in px: min(W, waterH*0.8) * 0.30 * species size * level size (AD v4 4) */
  function fishLen(f) {
    return Math.min(W, WATER_H * 0.8) * V.fishSizeFrac * (V.speciesSize[f.sp] || 1) * V.levelSizeScale[f.level - 1];
  }
  function bounds(f) { // swim area: inside the glass lines, top = surface + 4% of the water height, bottom = sand
    const L = fishLen(f);
    return { x0: INSET + L * 0.6, x1: W - INSET - L * 0.6, y0: SURF + WATER_H * 0.04 + L * 0.3, y1: SAND - L * 0.35 };
  }
  function pickTarget(m, f) {
    const b = bounds(f);
    m.tx = b.x0 + Math.random() * Math.max(1, b.x1 - b.x0);
    const yMid = (b.y0 + b.y1) / 2;
    m.ty = Math.min(b.y1, Math.max(b.y0, yMid + (Math.random() - 0.5) * (b.y1 - b.y0) * 0.95));
    m.retarget = 3 + Math.random() * 5;
  }
  const DEAD_RISE_SEC = 20; // game seconds to rise to the waterline (Art Director dead-fish pose)
  function stepDead(f, m, dt) {
    const b = bounds(f);
    if (m.deadY0 == null) { m.deadY0 = m.y; m.drift = Math.random() < 0.5 ? -1 : 1; }
    const yTop = SURF + WATER_H * 0.08; // dead-fish band: 6-10% of the water height below the surface
    const p = f.diedAt == null ? 1 : Math.max(0, Math.min(1, (G.state.gameTime - f.diedAt) / DEAD_RISE_SEC));
    const e = p * p * (3 - 2 * p);
    m.y = m.deadY0 + (yTop - m.deadY0) * e;
    if (p >= 1) { // drift sideways ~3 px/s, turning back at the glass
      m.x += m.drift * 3 * dt;
      if (m.x < b.x0) { m.x = b.x0; m.drift = 1; } else if (m.x > b.x1) { m.x = b.x1; m.drift = -1; }
    }
    m.vx = 0; m.vy = 0;
    f.x = m.x / W; f.y = m.y / H;
  }
  /** the fish's own flakes still in the water (it rushes to them and eats every one: bible item 16) */
  function flakesFor(id) { return pellets.filter((p) => p.fishId === id); }
  function mouth(m, L) { return { x: m.x + (m.faceAnim >= 0 ? 1 : -1) * L * 0.38, y: m.y }; }
  function stepFish(f, dt) {
    const m = motion(f);
    if (f.state === 'DEAD') { stepDead(f, m, dt); return; }
    const hungry = f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY';
    const L = fishLen(f);
    const mine = flakesFor(f.id);
    let maxSpeed = (hungry ? 0.35 : 1) * (22 + L * 0.9);
    if (mine.length) { // rush: head for the nearest of its flakes, fast, no pauses
      const mo = mouth(m, L);
      let best = mine[0], bd = Infinity;
      for (const p of mine) { const d = Math.hypot(p.x - mo.x, p.y - mo.y); if (d < bd) { bd = d; best = p; } }
      m.tx = best.x - (best.x >= m.x ? 1 : -1) * L * 0.3; m.ty = best.y; m.pause = 0; m.retarget = 0.5;
      maxSpeed = 2.4 * (22 + L * 0.9);
      m.rushing = true;
    } else if (m.rushing) { m.rushing = false; pickTarget(m, f); }
    m.retarget -= dt;
    const dx = m.tx - m.x, dy = m.ty - m.y, dist = Math.hypot(dx, dy);
    if (m.pause > 0) m.pause -= dt;
    else if (!m.rushing && (dist < 8 || m.retarget <= 0)) {
      if (Math.random() < 0.3) m.pause = 0.6 + Math.random() * 1.6;
      pickTarget(m, f);
    }
    let desX = 0, desY = 0;
    if (m.pause <= 0 && dist > 0.01) {
      const ease = Math.min(1, dist / (L * 1.5 + 30));
      const sp = maxSpeed * (0.35 + 0.65 * ease * ease * (3 - 2 * ease));
      desX = (dx / dist) * sp; desY = (dy / dist) * sp * (m.rushing ? 1 : 0.6);
    }
    const k = Math.min(1, dt * (m.rushing ? 4 : 1.6));
    m.vx += (desX - m.vx) * k; m.vy += (desY - m.vy) * k;
    m.x += m.vx * dt; m.y += m.vy * dt;
    const b = bounds(f);
    m.x = Math.min(b.x1, Math.max(b.x0, m.x));
    m.y = Math.min(b.y1, Math.max(b.y0, m.y));
    if (Math.abs(m.vx) > 4) m.face = m.vx > 0 ? 1 : -1;
    m.faceAnim += (m.face - m.faceAnim) * Math.min(1, dt * (m.rushing ? 8 : 5));
    const spd = Math.hypot(m.vx, m.vy);
    m.phase += dt * (hungry && !m.rushing ? 3 : 5 + spd * 0.12);
    m.bob += dt * (hungry ? 1.0 : 1.8);
    f.x = m.x / W; f.y = m.y / H;
    // eat: any of its flakes at the mouth (or inside the body) is gone
    if (mine.length) {
      const mo = mouth(m, L), reach = Math.max(10, L * 0.3);
      for (const p of mine) {
        if (Math.hypot(p.x - mo.x, p.y - mo.y) < reach || (Math.abs(p.x - m.x) < L * 0.45 && Math.abs(p.y - m.y) < L * 0.2)) {
          pellets.splice(pellets.indexOf(p), 1); flakeStats.eaten++;
        }
      }
    }
  }

  // ------------------------------------------------------------ drawing: water, air gap, sand, glass lines
  function surfY(x) { return SURF + Math.sin(x * 0.025 + realTime * Math.PI * 2 / 3) * 1.5; } // +-1.5 px on a 3 s cycle
  function drawWater() {
    // air gap (darker than the water, no rays)
    const a = ctx.createLinearGradient(0, 0, 0, SURF);
    a.addColorStop(0, '#0c2638'); a.addColorStop(1, '#11354f');
    ctx.fillStyle = a; ctx.fillRect(0, 0, W, SURF + 2);
    // water under the waving surface
    const g = ctx.createLinearGradient(0, SURF, 0, H);
    g.addColorStop(0, '#3fc0e8'); g.addColorStop(0.35, '#1d8fc2'); g.addColorStop(1, '#0a4c78');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.moveTo(0, H);
    for (let x = 0; x <= W + 8; x += 8) ctx.lineTo(x, surfY(x));
    ctx.lineTo(W, H); ctx.closePath(); ctx.fill();
    // light rays start at the surface
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    const rayH = WATER_H * 0.8;
    for (let i = 0; i < 6; i++) {
      const x = ((i * 0.18 + 0.04) * W + Math.sin(realTime * 0.2 + i) * 20);
      const gr = ctx.createLinearGradient(0, SURF, 0, SURF + rayH);
      gr.addColorStop(0, 'rgba(255,255,255,0.10)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = gr;
      ctx.beginPath(); ctx.moveTo(x, SURF); ctx.lineTo(x + 40, SURF); ctx.lineTo(x + 120, SURF + rayH); ctx.lineTo(x + 30, SURF + rayH); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
    // surface: 6 px band rgba(255,255,255,0.10) under a 2 px line rgba(191,239,255,0.6)
    ctx.fillStyle = 'rgba(255,255,255,0.10)';
    ctx.beginPath(); ctx.moveTo(0, surfY(0));
    for (let x = 0; x <= W + 8; x += 8) ctx.lineTo(x, surfY(x));
    for (let x = Math.ceil(W / 8) * 8; x >= 0; x -= 8) ctx.lineTo(x, surfY(x) + 6);
    ctx.closePath(); ctx.fill();
    ctx.strokeStyle = 'rgba(191,239,255,0.6)'; ctx.lineWidth = 2;
    ctx.beginPath(); for (let x = 0; x <= W + 8; x += 8) (x ? ctx.lineTo(x, surfY(x)) : ctx.moveTo(x, surfY(x))); ctx.stroke();
  }
  /** sand back edge y at x: gentle wave that is exactly 0 at both back corners (so lines meet the corner point exactly) */
  function sandBackY(x) { const taper = Math.max(0, Math.min(1, (x - INSET) / 40, (W - INSET - x) / 40)); return SAND + Math.sin(x * 0.015) * 2.5 * taper; }
  /** the one glass back line (AD v4 4, updated 19:58): side from VISUAL.glassLineSide, from the frame's inner top edge (y 0) to the sand corner */
  function glassLine() { const side = V.glassLineSide === 'left' ? 'left' : 'right', x = side === 'left' ? INSET : W - INSET; return { side, x, y0: 0, y1: SAND, cornerY: sandBackY(x) }; }
  function drawSand() {
    const st = SAND, drop = Math.min((H - st) * 0.45, INSET * 0.9);
    // floor as a box: back edge between the two corners (inset 3.5% of W), side edges slanting down to the front glass
    const g = ctx.createLinearGradient(0, st - 10, 0, H);
    g.addColorStop(0, '#e8d49a'); g.addColorStop(1, '#b89a5a');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.moveTo(0, H); ctx.lineTo(0, st + drop); ctx.lineTo(INSET, st);
    for (let x = INSET; x <= W - INSET; x += 20) ctx.lineTo(x, sandBackY(x));
    ctx.lineTo(W - INSET, st); ctx.lineTo(W, st + drop); ctx.lineTo(W, H); ctx.closePath(); ctx.fill();
    // the side faces of the sand (between the side edge and the tank side) a touch darker
    ctx.fillStyle = 'rgba(120,90,40,0.18)';
    ctx.beginPath(); ctx.moveTo(0, st + drop); ctx.lineTo(INSET, st); ctx.lineTo(INSET, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fill();
    ctx.beginPath(); ctx.moveTo(W, st + drop); ctx.lineTo(W - INSET, st); ctx.lineTo(W - INSET, H); ctx.lineTo(W, H); ctx.closePath(); ctx.fill();
    pebbles.forEach((p) => { ctx.fillStyle = `rgb(${p.c},${p.c * 0.85},${p.c * 0.6})`; ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill(); });
  }
  /** glass back line (AD v4 4): ONE vertical line from the frame's inner top edge straight down to the sand's back corner on
   *  VISUAL.glassLineSide, plus the side-glass strip between it and the frame on that side. The other side: no line, no strip. */
  function drawGlassLines() {
    const gl = glassLine(), x = gl.x;
    ctx.save();
    ctx.fillStyle = 'rgba(255,255,255,0.03)';
    if (gl.side === 'left') ctx.fillRect(0, 0, x, SAND); else ctx.fillRect(x, 0, W - x, SAND);
    ctx.fillStyle = 'rgba(190,235,255,0.08)'; ctx.fillRect(x - 3, gl.y0, 6, gl.y1 - gl.y0);      // 6 px soft glow
    ctx.fillStyle = 'rgba(190,235,255,0.35)'; ctx.fillRect(x - 1, SURF, 2, gl.y1 - SURF);        // in the water, ends on the sand corner
    ctx.fillStyle = 'rgba(190,235,255,0.45)'; ctx.fillRect(x - 1, gl.y0, 2, SURF - gl.y0);       // through the air gap, starts at the frame top
    ctx.restore();
  }
  function drawBubbles(dt) {
    if (Math.random() < dt * 4) bubbles.push({ x: W * 0.9 + (Math.random() - 0.5) * 8, y: SAND, r: 1.5 + Math.random() * 3, w: Math.random() * 6 });
    ctx.strokeStyle = 'rgba(255,255,255,0.6)'; ctx.lineWidth = 1;
    for (let i = bubbles.length - 1; i >= 0; i--) {
      const b = bubbles[i];
      b.y -= dt * (30 + b.r * 10); b.w += dt * 3;
      const x = b.x + Math.sin(b.w) * 3;
      ctx.beginPath(); ctx.arc(x, b.y, b.r, 0, 7); ctx.stroke();
      if (b.y < SURF + 3) bubbles.splice(i, 1);
    }
  }

  // ------------------------------------------------------------ decorations (AD v4 7)
  function hsl(h, s, l) { return `hsl(${h.toFixed(1)},${s.toFixed(1)}%,${Math.max(0, Math.min(100, l)).toFixed(1)}%)`; }
  function hexRgb(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
  function rgbStr(c, k) { return `rgb(${c.map((v) => Math.round(Math.max(0, Math.min(255, v * (k || 1))))).join(',')})`; }
  /** leaf colour 0..100: light hsl(98,68%,65%) -> dark hsl(135,50%,23%); returns [h, s, l] */
  function leafHsl(c) { const t = c / 100, a = V.leaf.light, b = V.leaf.dark; return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  /** stone colour 0..100: light grey #b8bec4 -> dark slate #3c4550 */
  function stoneRgb(c) { const t = c / 100, a = hexRgb(V.stone.light), b = hexRgb(V.stone.dark); return a.map((v, i) => v + (b[i] - v) * t); }
  function decorColorCss(d) { if (d.type === 'leaf') { const [h, s, l] = leafHsl(d.color); return hsl(h, s, l); } return rgbStr(stoneRgb(d.color)); }
  function decorGradientCss(type) {
    const stops = [0, 25, 50, 75, 100].map((c) => (type === 'leaf' ? hsl(...leafHsl(c)) : rgbStr(stoneRgb(c))));
    return `linear-gradient(90deg, ${stops.join(', ')})`;
  }
  /** size + box of a decoration in tank px. Leaf: 3 blades, height 0.30 x waterH (top kept >= 4% of waterH under the
   *  surface), spread 0.07 x waterH. Stone: 0.20 x 0.11 of waterH, bottom 15% sunk into the sand. */
  function decorGeom(d) {
    const bx = d.x * W, by = floorY(d);
    if (d.type === 'leaf') {
      const h = Math.min(V.leaf.h * WATER_H * d.sh, by - SURF - V.leaf.topGapFrac * WATER_H);
      const spread = V.leaf.spread * WATER_H * d.sw, bw = spread * 0.6;
      const half = spread + bw + h * Math.tan(V.leaf.swayDeg * Math.PI / 180) * 0.6;
      return { bx, by, h, spread, bw, half, x0: bx - half, x1: bx + half, y0: by - h, y1: by + 2 };
    }
    const w = V.stone.w * WATER_H * d.sw, h = V.stone.h * WATER_H * d.sh;
    return { bx, by, w, h, half: w / 2, x0: bx - w / 2, x1: bx + w / 2, y0: by - h * (1 - V.stone.sink), y1: by + 2 };
  }
  function drawLeaf(d, g) {
    const [hh, ss, ll] = leafHsl(d.color);
    const sway = Math.sin(realTime * Math.PI * 2 / V.leaf.swaySec + (d.seed % 17)) * Math.tan(V.leaf.swayDeg * Math.PI / 180);
    const blades = [[-g.spread, 0.82], [0, 1], [g.spread * 0.85, 0.7]];
    blades.forEach(([tipX, hk], i) => {
      const h = g.h * hk, tx = g.bx + tipX + sway * h * (0.9 + i * 0.08), ty = g.by - h;
      const bl = g.bx + (i - 1) * g.bw * 0.35 - g.bw / 2, br = bl + g.bw;
      const gr = ctx.createLinearGradient(0, g.by, 0, ty);
      gr.addColorStop(0, hsl(hh, ss, ll * 0.82)); gr.addColorStop(0.55, hsl(hh, ss, ll)); gr.addColorStop(1, hsl(hh, ss, ll * 1.10));
      ctx.fillStyle = gr;
      const mx = (bl + br) / 2, cx = mx + (tx - mx) * 0.5 + (i - 1) * g.bw * 0.3;
      ctx.beginPath(); ctx.moveTo(bl, g.by);
      ctx.quadraticCurveTo(cx - g.bw * 0.55, g.by - h * 0.5, tx, ty);
      ctx.quadraticCurveTo(cx + g.bw * 0.55, g.by - h * 0.5, br, g.by);
      ctx.closePath(); ctx.fill();
      ctx.strokeStyle = hsl(hh, ss, ll * 0.88); ctx.globalAlpha = 0.5; ctx.lineWidth = Math.max(1, g.bw * 0.08); // midrib, 12% darker at 50%
      ctx.beginPath(); ctx.moveTo(mx, g.by); ctx.quadraticCurveTo(cx, g.by - h * 0.5, tx, ty); ctx.stroke(); ctx.globalAlpha = 1;
    });
  }
  function stonePath(d, g, cx, cy) {
    const rng = seeded(d.seed + 1), k = [0, 1, 2, 3, 4].map(() => rng());
    ctx.beginPath();
    for (let i = 0; i <= 40; i++) {
      const th = (i / 40) * Math.PI * 2;
      const n = 1 + 0.07 * Math.sin(th * 2 + k[0] * 6) + 0.05 * Math.sin(th * 3 + k[1] * 6) + 0.03 * Math.sin(th * 5 + k[2] * 6);
      const x = cx + Math.cos(th) * g.w / 2 * n, y = cy + Math.sin(th) * g.h / 2 * n * (Math.sin(th) < 0 ? 1 : 0.9);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
  }
  function drawStone(d, g) {
    const c = stoneRgb(d.color), cx = g.bx, cy = g.by - g.h * (0.5 - V.stone.sink);
    ctx.fillStyle = 'rgba(0,0,0,0.25)'; // contact shadow
    ctx.beginPath(); ctx.ellipse(cx, g.by + 1, g.w * 0.55, Math.max(3, g.h * 0.12), 0, 0, 7); ctx.fill();
    ctx.save();
    ctx.beginPath(); ctx.rect(g.x0 - 10, g.y0 - 10, g.w + 20, g.by - g.y0 + 10); ctx.clip(); // bottom 15% sunk into the sand
    stonePath(d, g, cx, cy);
    const gr = ctx.createLinearGradient(cx - g.w / 2, cy - g.h / 2, cx + g.w * 0.2, cy + g.h / 2);
    gr.addColorStop(0, rgbStr(c, 1.15)); gr.addColorStop(0.45, rgbStr(c)); gr.addColorStop(1, rgbStr(c, 0.75)); // highlight 15% lighter, bottom 25% darker
    ctx.fillStyle = gr; ctx.fill();
    const rng = seeded(d.seed + 5);
    ctx.fillStyle = rgbStr(c, 0.6);
    for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(cx + (rng() - 0.5) * g.w * 0.6, cy + (rng() - 0.6) * g.h * 0.5, Math.max(1, g.h * 0.04), 0, 7); ctx.fill(); }
    ctx.restore();
  }
  function drawDecor() {
    const list = G.state.decor.slice().sort((a, b) => a.y - b.y); // lower base = in front
    for (const d of list) {
      const g = decorGeom(d);
      if (d.type === 'leaf') drawLeaf(d, g); else drawStone(d, g);
      if (editing) { // edit mode outlines: dashed white 0.5 on each, solid 2px --accent on the selected one
        ctx.save();
        if (d.id === selDecor) { ctx.strokeStyle = '#37c3ff'; ctx.lineWidth = 2; ctx.setLineDash([]); }
        else { ctx.strokeStyle = 'rgba(255,255,255,0.5)'; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]); }
        const ob = Math.min(g.y1 + 2, H - 1.5); // keep the outline's bottom edge inside the tank when the base is at the front glass
        roundRect(g.x0 - 4, g.y0 - 4, g.x1 - g.x0 + 8, ob - g.y0 + 4, 8); ctx.stroke();
        ctx.restore();
      }
    }
  }

  // ------------------------------------------------------------ fish
  function drawFishAll(dt) {
    G.state.fish.forEach((f) => {
      stepFish(f, dt);
      const m = anim.get(f.id);
      const L = fishLen(f);
      const hungry = f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY';
      const dead = f.state === 'DEAD';
      const bobY = dead ? Math.sin(realTime * Math.PI / 2) * 2 : Math.sin(m.bob) * (hungry ? 1.5 : 3); // dead: +-2 px on a 4 s cycle
      ctx.save();
      if (editing) ctx.globalAlpha = 0.3; // edit mode: see-through fish
      ctx.translate(m.x, m.y + bobY);
      const tilt = dead ? Math.sin(realTime * 0.9 + f.id) * 0.14 // +-8 degrees
        : Math.max(-0.35, Math.min(0.35, Math.atan2(m.vy, Math.abs(m.vx) + 10))) + (hungry ? 0.12 : 0);
      ctx.save();
      ctx.scale(m.faceAnim >= 0 ? Math.max(0.08, m.faceAnim) : Math.min(-0.08, m.faceAnim), 1);
      ctx.rotate(tilt);
      if (hungry && !editing) ctx.globalAlpha = 0.9;
      FishArt.drawFish(ctx, f.sp, L, m.phase, { hungry, dead, level: f.level });
      if (tool === 'net' && !editing && net.target && net.target.id === f.id && (net.on || net.dip >= 0)) drawNetTargetGlow(f, L);
      ctx.restore();
      if (!editing) drawStatusIcon(f, L, m);
      ctx.restore();
    });
  }
  /** hunger / waiting icon (AD v4 5): centre y = -(body half-depth) - 12, x = +0.25 L toward the head; r 8 (Large 10) */
  const bodyHalfDepth = (L) => L * 0.21;
  function statusIconPos(f, L, m) { return { x: (m.faceAnim >= 0 ? 1 : -1) * 0.25 * L, y: -bodyHalfDepth(L) - 12 }; }
  function drawStatusIcon(f, L, m) {
    if (f.state === 'DEAD') return;
    let color = null, glyph = null;
    if (f.state === 'WAITING') { color = '#37c3ff'; glyph = 'food'; }
    else if (f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY') {
      const frac = f.deathLeft / G.deathSecFor(G.SPECIES[f.sp], f.level);
      color = frac < 0.33 ? '#ff3b3b' : '#ffa53b'; glyph = '!';
    }
    if (!color) return;
    const pos = statusIconPos(f, L, m), base = LARGE() ? 10 : 8;
    const pulse = 1 + Math.sin(realTime * 6) * 0.08;
    const x = pos.x, y = pos.y, r = base * pulse;
    ctx.fillStyle = color; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x - 3, y + r - 2); ctx.lineTo(x, y + r + 4); ctx.lineTo(x + 3, y + r - 2); ctx.fill();
    ctx.fillStyle = '#fff';
    if (glyph === '!') { ctx.font = `900 ${Math.round(base * 1.4)}px Nunito, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', x, y + 1); }
    else { const k = base / 9; for (const [dx, dy] of [[-3, -2], [2, -3], [0, 2], [3, 2], [-3, 3]]) { ctx.beginPath(); ctx.arc(x + dx * k, y + dy * k, 1.3 * k, 0, 7); ctx.fill(); } }
  }

  // ------------------------------------------------------------ food flakes (bible item 16)
  /** one tap = one small pinch of flakes at the tap point; they sink slowly and the fed fish rushes over and eats all of them */
  function flakeShower(x, y, r) {
    const n = V.flakesPerTap || 12;
    y = Math.max(y, SURF + 4);
    for (let i = 0; i < n; i++) {
      const py = y + (Math.random() - 0.5) * 10;
      pellets.push({ x: x + (Math.random() - 0.5) * 22, y: py, x0: x, y0: py, t: 0, s: Math.random() * 3,
        fishId: r.fish.id, c: ['#d9772f', '#b8542a', '#e8a13a'][i % 3] });
    }
    flakeStats.spawned += n; flakeStats.showers++;
    const m = anim.get(r.fish.id); if (m) { m.pause = 0; m.retarget = 0; }
    if (r.full && r.gold > 0 && m) floatFeedGold(r.gold, m.x, m.y); // v3/v4 feed pays 0: no float
  }
  const FLAKE_SINK = 14; // px/s (slow)
  function drawPellets(dt) {
    for (let i = pellets.length - 1; i >= 0; i--) {
      const p = pellets[i];
      p.t += dt;
      p.x += Math.sin(p.t * 2.2 + p.s) * dt * 6;
      p.y = Math.min(SAND - 2, p.y + (FLAKE_SINK + p.s * 2) * dt);
      if (!G.state.fish.some((f) => f.id === p.fishId && f.state !== 'DEAD') || p.t > 12) { pellets.splice(i, 1); continue; } // its fish is gone
      ctx.fillStyle = p.c; ctx.beginPath(); ctx.ellipse(p.x, p.y, 2.6, 2, p.s + p.t, 0, 7); ctx.fill();
    }
  }

  // ------------------------------------------------------------ dirt: one look per stage, deterministic from spot.seed
  function seeded(seed) { // mulberry32
    let t = Math.floor(seed * 9973) >>> 0;
    return () => { t = (t + 0x6D2B79F5) >>> 0; let r = Math.imul(t ^ (t >>> 15), 1 | t); r ^= r + Math.imul(r ^ (r >>> 7), 61 | r); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; };
  }
  function rgbaHex(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${Math.max(0, Math.min(1, a)).toFixed(3)})`; }
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
    smudge(cx, cy, R, c, a, s, rng, look) { // stage 1 (AD v4 21): soft smudge, darker rim (+0.06 over the outer 25%), 3-5 speckles
      const rim = look.rim || 0;
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
      g.addColorStop(0, rgbaHex(c, a)); g.addColorStop(0.75, rgbaHex(c, a)); g.addColorStop(0.8, rgbaHex(c, a + rim));
      g.addColorStop(0.95, rgbaHex(c, (a + rim) * 0.7)); g.addColorStop(1, rgbaHex(c, 0));
      ctx.fillStyle = g; blobPath(cx, cy, R, s.seed, 0.5); ctx.fill();
      if (look.speckles) {
        const n = look.speckles[0] + Math.floor(rng() * (look.speckles[1] - look.speckles[0] + 1));
        ctx.fillStyle = rgbaHex('#3A3418', look.speckleAlpha * (a / look.alpha));
        for (let i = 0; i < n; i++) {
          const th = rng() * Math.PI * 2, d = Math.sqrt(rng()) * R * 0.7, sr = look.speckleR[0] + rng() * (look.speckleR[1] - look.speckleR[0]);
          ctx.beginPath(); ctx.arc(cx + Math.cos(th) * d, cy + Math.sin(th) * d, sr, 0, 7); ctx.fill();
        }
      }
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
      ctx.strokeStyle = rgbaHex(c, look.strandAlpha * k * (a / look.alpha / Math.max(0.12, k))); ctx.lineWidth = 1.5; ctx.lineCap = 'round';
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
  // ---- blocked-feed pulse (AD v4 6): 0 -> 1 over 0.35 s (ease-out), hold 0.15 s, 1 -> 0 over 0.5 s (ease-in); restarts on every blocked tap
  let pulseT0 = -10;
  const nowSec = () => performance.now() / 1000;
  function pulseAmt(t) {
    const u = (t == null ? nowSec() : t) - pulseT0;
    if (u < 0 || u >= 1) return 0;
    if (u < 0.35) { const k = u / 0.35; return 1 - (1 - k) * (1 - k); }
    if (u < 0.5) return 1;
    const k = (u - 0.5) / 0.5; return 1 - k * k;
  }
  const spotR = (s) => s.r * WATER_H; // AD v4 6: spot radii are fractions of the water height
  // ---- tank-wide dirt layer (AD v2/v4): stage 1-4 flat wash, stage 5 green film
  const film = { cv: null, x: null, img: null, cols: 0, rows: 0, a: null, cap: null, mid: null, strength: 0 };
  /** fill alpha of one spot as drawn (look alpha x rub fade; drip bottom edge +0.08) */
  function spotFillAlpha(s) {
    const look = V.dirtStages[Math.max(1, Math.min(5, s.stage || 1)) - 1];
    const k = Math.max(0.12, s.grime / s.grime0);
    return look.alpha * k + (look.look === 'drip' ? 0.08 : 0);
  }
  function drawFilm(strength, p) {
    const F = V.dirtFilm, cell = F.cellPx;
    const cols = Math.max(4, Math.ceil(W / cell)), rows = Math.max(4, Math.ceil(H / cell));
    if (!film.cv || film.cols !== cols || film.rows !== rows) {
      film.cv = document.createElement('canvas'); film.cv.width = cols; film.cv.height = rows;
      film.x = film.cv.getContext('2d'); film.img = film.x.createImageData(cols, rows);
      Object.assign(film, { cols, rows, a: new Float32Array(cols * rows), cap: new Float32Array(cols * rows), mid: new Uint8Array(cols * rows) });
    }
    const d = film.img.data, spots = G.state.dirt.spots.map((s) => ({ x: s.x * W, y: s.y * H, r: spotR(s) * 1.25, a: spotFillAlpha(s) }));
    const drift = realTime / F.cloudDriftSec;
    for (let j = 0; j < rows; j++) {
      const py = (j + 0.5) * H / rows, ny = py / H;
      for (let i = 0; i < cols; i++) {
        const px = (i + 0.5) * W / cols, nx = px / W, idx = j * cols + i;
        const dist = Math.max(Math.abs(nx - 0.5), Math.abs(ny - 0.5)) * 2;
        const mid = dist <= F.guardZone;
        const t = Math.max(0, Math.min(1, (dist - F.guardZone) / (1 - F.guardZone)));
        let a = F.centre + (F.edge - F.centre) * t * t * (3 - 2 * t);
        const u = (nx - drift) * 6.283, v = ny * 6.283 * H / W;
        a += F.cloud * (Math.sin(u * 1.1 + v * 0.6 + 1.3) + Math.sin(-u * 0.7 + v * 1.3 + 4.1) + 0.6 * Math.sin(u * 1.9 - v * 1.7 + 2.2)) / 2.6;
        let rgb = F.rgb;
        const sy = (py - SURF) / WATER_H; // waterline scum band sits under the surface
        const scum = sy < 0 ? 0 : sy < F.scumFrac ? 1 : sy < F.scumFrac * 1.4 ? 1 - (sy - F.scumFrac) / (F.scumFrac * 0.4) : 0;
        if (scum > 0) { a = a + (F.scumAlpha - a) * scum; rgb = F.scumRgb; }
        let cap = 1;
        if (mid) { // readability guard: film + one spot <= guardMax in the middle of the tank (lifted during a blocked-feed pulse)
          let sMax = 0;
          for (const sp of spots) if (Math.hypot(px - sp.x, py - sp.y) < sp.r && sp.a > sMax) sMax = sp.a;
          cap = sMax >= F.guardMax ? 0 : 1 - (1 - F.guardMax) / (1 - sMax);
          if (!(p > 0)) a = Math.min(a, cap);
        }
        a = Math.max(0, a) * strength;
        if (p > 0) a = Math.max(a, Math.min(0.6, a * (1 + 0.5 * p)));
        film.a[idx] = a; film.cap[idx] = cap; film.mid[idx] = mid ? 1 : 0;
        d[idx * 4] = rgb[0]; d[idx * 4 + 1] = rgb[1]; d[idx * 4 + 2] = rgb[2]; d[idx * 4 + 3] = Math.round(a * 255);
      }
    }
    film.x.putImageData(film.img, 0, 0);
    ctx.save(); ctx.imageSmoothingEnabled = true; ctx.drawImage(film.cv, 0, 0, W, H); ctx.restore();
  }
  function washAlpha(css) { const m = /rgba\([^)]*,\s*([\d.]+)\)/.exec(css); return m ? +m[1] : 0; }
  function drawDirtLayer(p) {
    const stage = G.dirtStage(), layer = stage > 0 ? V.dirtLayer[stage - 1] : null;
    film.strength = layer && layer.film ? G.dirtFilm() : 0;
    if (!layer) return;
    if (layer.wash) {
      const a0 = washAlpha(layer.wash), a = p > 0 ? Math.min(0.6, a0 * (1 + 0.5 * p)) : a0; // pulse: up to 1.5x (max 0.6)
      ctx.fillStyle = layer.wash.replace(/,\s*[\d.]+\)$/, `,${a.toFixed(3)})`); ctx.fillRect(0, 0, W, H);
    }
    if (layer.film && film.strength > 0) drawFilm(film.strength, p);
  }
  const drawnSpots = []; // last drawn alpha per spot (tests)
  function drawSpots(p) {
    drawnSpots.length = 0;
    G.state.dirt.spots.forEach((s) => {
      const look = V.dirtStages[Math.max(1, Math.min(5, s.stage || 1)) - 1];
      const k = Math.max(0.12, s.grime / s.grime0);
      const color = look.tintHalf && Math.floor(s.seed) % 2 ? mixHex(look.color, look.tintHalf, look.tintMix) : look.color;
      const a0 = look.alpha * k, a = a0 + (Math.min(a0 + 0.35, 0.85) - a0) * p; // pulse: alpha -> min(a + 0.35, 0.85)
      SPOT_DRAW[look.look](s.x * W, s.y * H, spotR(s), color, a, s, seeded(s.seed), look, k);
      drawnSpots.push({ id: s.id, alpha: +a.toFixed(3), base: +a0.toFixed(3) });
    });
  }
  function mixHex(a, b, t) {
    const p = parseInt(a.slice(1), 16), q = parseInt(b.slice(1), 16), c = (sh) => Math.round(((p >> sh) & 255) * (1 - t) + ((q >> sh) & 255) * t);
    return '#' + ((c(16) << 16) | (c(8) << 8) | c(0)).toString(16).padStart(6, '0');
  }
  function drawGlass() {
    const g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, 'rgba(255,255,255,0.08)'); g.addColorStop(0.3, 'rgba(255,255,255,0)'); g.addColorStop(0.7, 'rgba(255,255,255,0)'); g.addColorStop(1, 'rgba(255,255,255,0.05)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }
  /** sponge radius: 0.16 x water height, clamped 40-72 px (AD v4 6) */
  function spongeR() { return Math.max(V.spongeMinPx, Math.min(V.spongeMaxPx, V.spongeRadiusFrac * WATER_H)); }
  function spongeLift() { return pointer.touch ? spongeR() * V.spongeTouchLiftFrac : 0; }
  function drawSponge() {
    if (tool !== 'sponge' || !pointer.inside) return;
    const r = spongeR();
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
  // Floating texts are clamped every frame so the whole rendered text box (measured glyph bounds + the 4 px outline)
  // stays inside the tank with FLOAT_MARGIN px to spare (Playtester pass 6 N6). Floats spawned together (level-up
  // "+gold" and "+XP") share a group and are shifted as one unit, so they never pile on top of each other.
  const FLOAT_MARGIN = 8, FLOAT_STROKE = 4, FLOAT_GAP = 10;
  function drawFloaters(dt) {
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const groups = new Map();
    for (let i = floaters.length - 1; i >= 0; i--) {
      const f = floaters[i];
      f.t += dt; f.y -= dt * 28;
      if (f.t > 1.8) { floaters.splice(i, 1); continue; }
      ctx.font = `900 ${f.big ? 22 : 16}px Nunito, sans-serif`;
      const m = ctx.measureText(f.text), h = FLOAT_STROKE / 2;
      f.rel = { l: -m.actualBoundingBoxLeft - h, r: m.actualBoundingBoxRight + h, t: -m.actualBoundingBoxAscent - h, b: m.actualBoundingBoxDescent + h };
      // side-by-side pairs: 'L' ends FLOAT_GAP/2 left of the anchor, 'R' starts FLOAT_GAP/2 right of it (from measured widths)
      const ox = f.side === 'L' ? -f.rel.r - FLOAT_GAP / 2 : f.side === 'R' ? -f.rel.l + FLOAT_GAP / 2 : 0;
      f.rel.l += ox; f.rel.r += ox; f.ox = ox;
      const g = groups.get(f.grp) || { x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity, list: [] };
      g.x0 = Math.min(g.x0, f.x + f.rel.l); g.x1 = Math.max(g.x1, f.x + f.rel.r);
      g.y0 = Math.min(g.y0, f.y + f.rel.t); g.y1 = Math.max(g.y1, f.y + f.rel.b);
      g.list.push(f); groups.set(f.grp, g);
    }
    // Clamp each group inside the tank, then stagger: groups are placed oldest first, and a group that would overlap an
    // already placed one moves up/down in steps of its own height + gap until it is clear (and still inside the margin).
    // The chosen offset is sticky while it stays valid, so floats don't jump between frames.
    const clampShift = (lo, hi, min, max) => (hi - lo > max - min ? (min + max) / 2 - (lo + hi) / 2 : lo < min ? min - lo : hi > max ? max - hi : 0);
    const placed = [];
    const clear = (b) => b.y0 >= FLOAT_MARGIN - 0.01 && b.y1 <= H - FLOAT_MARGIN + 0.01 &&
      placed.every((p) => b.x1 + FLOAT_GAP / 2 <= p.x0 || p.x1 + FLOAT_GAP / 2 <= b.x0 || b.y1 + FLOAT_GAP / 2 <= p.y0 || p.y1 + FLOAT_GAP / 2 <= b.y0);
    [...groups.values()].sort((a, b) => a.list[0].seq - b.list[0].seq).forEach((g) => {
      const dx = clampShift(g.x0, g.x1, FLOAT_MARGIN, W - FLOAT_MARGIN);
      let dy = clampShift(g.y0, g.y1, FLOAT_MARGIN, H - FLOAT_MARGIN);
      const at = (o) => ({ x0: g.x0 + dx, x1: g.x1 + dx, y0: g.y0 + dy + o, y1: g.y1 + dy + o });
      let off = g.list[0].stag || 0;
      if (!clear(at(off))) {
        const step = g.y1 - g.y0 + FLOAT_GAP / 2;
        for (let k = 0; k <= 40; k++) { const o = (k % 2 ? -1 : 1) * Math.ceil(k / 2) * step; if (clear(at(o))) { off = o; break; } }
      }
      g.list.forEach((f) => { f.stag = off; });
      placed.push(at(off)); dy += off;
      for (const f of g.list) {
        const x = f.x + dx, y = f.y + dy, tx = x + f.ox; // rel already includes the pair offset; tx = text anchor
        f.box = { x0: x + f.rel.l, x1: x + f.rel.r, y0: y + f.rel.t, y1: y + f.rel.b }; // drawn bounds (tests)
        ctx.globalAlpha = Math.max(0, 1 - f.t / 1.8);
        ctx.font = `900 ${f.big ? 22 : 16}px Nunito, sans-serif`;
        ctx.lineWidth = FLOAT_STROKE; ctx.strokeStyle = 'rgba(0,0,0,0.5)'; ctx.strokeText(f.text, tx, y);
        ctx.fillStyle = f.color || '#ffd84a'; ctx.fillText(f.text, tx, y);
      }
    });
    ctx.globalAlpha = 1;
  }
  const floatLog = []; // every float text shown (last 50), for tests
  let floatGrp = 0, floatSeq = 0;
  function floatText(text, x, y, color, big, grp, side) {
    floaters.push({ text, x, y, color, big, t: 0, grp: grp == null ? `s${++floatGrp}` : grp, side: side || null, seq: ++floatSeq });
    floatLog.push(text); if (floatLog.length > 50) floatLog.shift();
  }
  // every float in the game goes through one of these
  function floatClean(gold, x, y, food) { floatText(`Sparkling! +${gold} gold${food ? ` +${food} food` : ''}`, x, y - 20, '#9fffd0', true); }
  function floatLevelUp(gold, xp, fx, fy) {
    const grp = `g${++floatGrp}`;
    const both = gold && xp;
    if (gold) floatText(`+${gold} gold`, fx, fy - 10, '#ffd84a', true, grp, both ? 'L' : null);
    if (xp) floatText(`+${xp} XP`, fx, fy - 10, '#9fdcff', true, grp, both ? 'R' : null);
  }
  function floatFeedGold(gold, x, y) { floatText(`+${gold} gold`, x, y - 30, '#ffe07a'); }

  // ------------------------------------------------------------ HUD: gold / diamonds / tank level / dirt window / food bottle
  const goldEl = $('gold'), gemEl = $('gems');
  let lastGold = null, lastGems = null;
  function bump(el) { el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump'); setTimeout(() => el.classList.remove('bump'), 160); }
  /** bottle fill steps (AD v4 2): 0 empty, 1-4 quarter, 5-9 half, 10-19 three quarters, 20+ full */
  function bottleFill(n) { return n <= 0 ? 0 : n < 5 ? 0.25 : n < 10 ? 0.5 : n < 20 ? 0.75 : 1; }
  function updateHUD() {
    const s = G.state;
    if (s.gold !== lastGold) { goldEl.textContent = s.gold; if (lastGold !== null) bump($('res-gold')); lastGold = s.gold; }
    const gems = s.diamonds || 0;
    if (gems !== lastGems) { gemEl.textContent = gems; if (lastGems !== null) bump($('res-gem')); lastGems = gems; }
    // food bottle + badge
    const fill = bottleFill(s.food), badge = $('food-badge');
    badge.textContent = s.food > 999 ? '999+' : String(s.food);
    badge.classList.toggle('zero', s.food <= 0);
    $('food-empty').toggleAttribute('hidden', fill > 0); $('food-partial').toggleAttribute('hidden', fill === 0);
    const cr = $('food-clip-rect'), bh = 15 * fill; cr.setAttribute('y', String(21 - bh)); cr.setAttribute('height', String(bh));
    $('food-icon').dataset.fill = fill;
    // dirt window
    const st = G.dirtStage(), maxSt = T.dirt.stageAtSec.length;
    const bar = $('dirt-bar'); bar.dataset.stage = st;
    [...bar.children].forEach((el, i) => el.classList.toggle('on', i < st));
    // v6.1 (NUMBERS 6.3, AD v4 3): no dirt timer anywhere; the window shows the stage only, 'Dirt: max' at the last stage
    $('dirt-label').textContent = st === 0 ? 'Dirt: clean' : st >= maxSt ? 'Dirt: max' : `Dirt: stage ${st} of ${maxSt}`;
    // tank level block
    const ti = G.tankInfo();
    $('tank-label').textContent = `Aquarium Lv ${ti.level}`;
    $('tank-xp').textContent = ti.max ? 'Max level' : `${ti.xp} / ${ti.next}`;
    $('tank-xpbar').style.width = (ti.max ? 100 : Math.min(100, ((ti.xp - ti.cur) / (ti.next - ti.cur)) * 100)).toFixed(1) + '%';
    $('tankover').hidden = !G.tankOver();
    // hint line (bottom of the tank)
    let hint = '';
    if (editing) hint = '';
    else if (!s.fish.length) hint = st >= 1 && s.firstCleanPending ? 'Pick Clean and rub the dirt off the glass' : 'Open the Shop and buy a baby fish';
    else if (tool === 'food') hint = st >= 1 ? '' : 'Tap near a hungry fish to feed it'; // dirty: the blocked-feed warning is the only message
    else if (tool === 'sponge') hint = st >= 1 ? 'Rub the dirty spots' : 'The glass is clean';
    else if (tool === 'net') hint = 'Drag the net onto a fish and let go';
    else hint = G.living() ? 'Tap a fish to see its details' : '';
    $('hint').textContent = hint;
    $('dbg-clock').textContent = `game ${clock(s.gameTime)} · ×${s.speed}`;
    document.querySelectorAll('#speed-btns .dbg').forEach((b) => b.classList.toggle('on', +b.dataset.speed === s.speed));
  }
  /** NUMBERS.md 2: "1h 12m" when an hour or more is left, "12m 30s" when less */
  function fmt(sec) {
    sec = Math.max(0, Math.ceil(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s).padStart(2, '0')}s`;
  }
  function clock(sec) { // debug bar only (game time)
    sec = Math.max(0, Math.floor(sec)); const d = Math.floor(sec / 86400), h = Math.floor(sec / 3600) % 24, m = Math.floor(sec / 60) % 60;
    return `${d ? d + 'd ' : ''}${h}h ${String(m).padStart(2, '0')}m`;
  }
  function realNote(sec) { return G.state.speed > 1 ? ` (≈${fmt(sec / G.state.speed)} real at ×${G.state.speed})` : ''; }

  // ------------------------------------------------------------ toasts
  // At most 3 on screen. An identical toast still showing merges into one line with a count ("... ×3") unless
  // opts.restart: then it just restarts (blocked feed, edit hint: no stacking).
  function toastTimers(el, ms) {
    ms = ms || 2700;
    clearTimeout(el._tOut); clearTimeout(el._tDel); el.classList.remove('out');
    el._tOut = setTimeout(() => el.classList.add('out'), ms - 400);
    el._tDel = setTimeout(() => el.remove(), ms);
  }
  function toast(text, kind, opts) {
    opts = opts || {};
    const box = $('toasts'), k = kind || '';
    const same = [...box.children].find((e) => e.dataset.base === text && e.dataset.kind === k);
    if (same) {
      if (!opts.restart) { const n = +same.dataset.n + 1; same.dataset.n = n; same.textContent = `${text} ×${n}`; }
      same.classList.remove('merge'); void same.offsetWidth; same.classList.add('merge');
      toastTimers(same, opts.ms); return same;
    }
    const el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.textContent = text; el.dataset.base = text; el.dataset.kind = k; el.dataset.n = 1;
    box.appendChild(el);
    while (box.children.length > 3) box.removeChild(box.firstChild);
    toastTimers(el, opts.ms);
    return el;
  }
  function clearToasts() {
    const box = $('toasts');
    [...box.children].forEach((e) => { clearTimeout(e._tOut); clearTimeout(e._tDel); });
    box.replaceChildren();
  }
  // Blocked feed (AD v4 6, bible 22): top-middle toast, spot pulse and dirt-window flash, all on the same frame,
  // restarting on every blocked tap.
  let blockedCount = 0;
  function blockedFeed() {
    toast('Clean the tank first', 'bad', { restart: true, ms: 2500 });
    pulseT0 = nowSec();
    const w = $('dirt-win'); w.classList.remove('flash'); void w.offsetWidth; w.classList.add('flash');
    clearTimeout(w._t); w._t = setTimeout(() => w.classList.remove('flash'), 1050);
    blockedCount++;
  }

  // ------------------------------------------------------------ tools
  let tool = 'hand';
  function setTool(t) {
    tool = t;
    document.querySelectorAll('.tool[data-tool]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tool === t)));
    wrap.dataset.tool = t;
    net.on = false; net.target = null; net.dip = -1; clearTimeout(netPending); netPending = 0;
    if (t !== 'hand') closePanel();
    closeShop();
    if (t === 'brush') enterEdit(); else exitEdit();
  }
  document.querySelectorAll('.tool[data-tool]').forEach((b) => b.addEventListener('click', () => setTool(b.dataset.tool)));
  $('btn-shop').addEventListener('click', () => ($('shop').hidden ? openShop() : closeShop()));

  // ------------------------------------------------------------ fish info (side panel, AD v4 8)
  let selectedId = null;
  function openPanel(id) { selectedId = id; closeShop(); $('panel').hidden = false; renderPanel(true); }
  function closePanel() { selectedId = null; $('panel').hidden = true; }
  /** v6: L1 has one meal (the mid meal; no start meal after buying), L2 / L3 have two (start at 0%, mid at 50%) */
  function mealCount(f) { return f.level <= 1 ? 1 : (T.mealsPerLevel || 2); }
  function mealIndex(f) { return f.state === 'HUNGRY' ? (f.level <= 1 || f.progress > 0 ? mealCount(f) : 1) : null; }
  function renderPanel() {
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
    $('p-worth').textContent = i.dead ? 'Worth 0 gold' : `Worth ${i.sell} gold`;
    if (!i.dead) {
      const gEl = $('p-growth'), hEl = $('p-hunger'), bar = $('p-growbar');
      gEl.className = 'v'; hEl.className = 'v';
      bar.classList.toggle('paused', f.state === 'HUNGRY');
      bar.style.width = (i.progressFrac * 100).toFixed(1) + '%';
      if (f.state === 'WAITING') { gEl.textContent = 'Not started'; gEl.classList.add('warn'); hEl.textContent = 'Waiting for its first meal'; hEl.classList.add('warn'); }
      else if (f.state === 'GROWING') {
        gEl.textContent = `L${f.level} · next level in ${fmt(i.growLeft)}${realNote(i.growLeft)}`;
        hEl.textContent = i.midHungerIn != null ? `Fed · hungry in ${fmt(i.midHungerIn)}` : 'Fed'; hEl.classList.add('ok');
      } else if (f.state === 'HUNGRY') {
        gEl.textContent = `L${f.level} · Growth paused`; gEl.classList.add('danger');
        hEl.textContent = `Hungry! Growth paused · dies in ${fmt(i.deathLeft)}${realNote(i.deathLeft)}`; hEl.classList.add('danger');
      } else if (f.state === 'ADULT') {
        gEl.textContent = `Adult (L${f.level})`;
        hEl.textContent = `Fed · hungry in ${fmt(i.adultHungerIn)}`; hEl.classList.add('ok');
      } else {
        gEl.textContent = `Adult (L${f.level})`;
        hEl.textContent = `Hungry! dies in ${fmt(i.deathLeft)}${realNote(i.deathLeft)}`; hEl.classList.add('danger');
      }
      // meal progress (moved here from above the fish): in food, never taps
      const k = mealIndex(f), mb = $('p-mealbar');
      if (i.needsFood) {
        $('p-meal').textContent = k ? `Meal ${k} of ${mealCount(f)} · needs ${i.needLeft} food` : `Adult meal · needs ${i.needLeft} food`;
        if (mb.children.length !== i.portion) mb.replaceChildren(...Array.from({ length: i.portion }, () => document.createElement('i')));
        [...mb.children].forEach((el, n) => el.classList.toggle('on', n < i.fed));
      } else { $('p-meal').textContent = 'Fed'; mb.replaceChildren(); }
    }
    drawPortrait($('panel-portrait'), f);
  }
  function drawPortrait(pc, f) {
    const p = pc.getContext('2d');
    p.setTransform(1, 0, 0, 1, 0, 0); p.clearRect(0, 0, pc.width, pc.height);
    p.translate(pc.width * 0.52, pc.height * 0.52);
    const dead = f.state === 'DEAD';
    FishArt.drawFish(p, f.sp, pc.width * 0.5, dead ? 0 : realTime * 5, { hungry: f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY', dead, level: f.level });
  }
  // confirm windows (AD v4 8): centred, portrait, one line of text, Cancel left, action right
  function confirmBox(text, yesLabel, onYes, portrait, yesClass) {
    $('confirm-text').textContent = text;
    const y = $('confirm-yes'); y.textContent = yesLabel; y.className = 'btn ' + (yesClass || 'danger');
    const pc = $('confirm-portrait');
    pc.hidden = !portrait;
    if (portrait) portrait(pc);
    $('confirm').hidden = false;
    y.onclick = () => { $('confirm').hidden = true; onYes(); };
    $('confirm-no').onclick = () => { $('confirm').hidden = true; };
  }
  /** net tool (bible 19, NUMBERS 11.4): a live fish always asks first (sale, or release at L1); a dead fish goes at once */
  function netFish(f) {
    const sp = G.SPECIES[f.sp], name = sp.name, por = (pc) => drawPortrait(pc, f);
    if (f.state === 'DEAD') { G.removeDead(f.id); return; } // Designer NUMBERS 11 item 4: no confirm, 0 gold, 0 XP, "Fish removed" toast
    else { // v6 (NUMBERS 11.2): every live fish sells for (price / 2) x level, L1 included ("Sell Guppy (L1) for 10 gold?")
      const gold = G.sellPrice(sp, f.level), xp = G.xpFor('sell', { sp, level: f.level });
      confirmBox(`Sell ${name} (L${f.level}) for ${gold} gold${xp ? ` and ${xp} XP` : ''}?`, 'Sell', () => G.sell(f.id), por, 'sell');
    }
  }
  document.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => (b.dataset.close === 'panel' ? closePanel() : closeShop())));

  // ------------------------------------------------------------ shop (centred panel, tabs Fish / Food / Decorations)
  let shopTab = 'fish';
  function openShop() { closePanel(); $('shop').hidden = false; $('btn-shop').setAttribute('aria-pressed', 'true'); renderShop(); }
  function closeShop() { $('shop').hidden = true; $('btn-shop').setAttribute('aria-pressed', 'false'); }
  $('shop-close').addEventListener('click', closeShop);
  function setShopTab(t) {
    shopTab = t;
    document.querySelectorAll('#shop .tab').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
    document.querySelectorAll('#shop .grid').forEach((g) => { g.hidden = g.dataset.tab !== t; });
    $('shop-scroll').scrollTop = 0;
    renderShop();
  }
  document.querySelectorAll('#shop .tab').forEach((b) => b.addEventListener('click', () => setShopTab(b.dataset.tab)));
  function drawBottleCard(c, n) {
    c.clearRect(0, 0, 240, 96);
    const k = n >= 50 ? 3 : 1;
    for (let i = 0; i < k; i++) {
      c.save(); c.translate(120 + (i - (k - 1) / 2) * 44, 12); c.scale(3, 3);
      c.fillStyle = '#ff8a3d'; c.beginPath(); c.roundRect(6 - 12, 6 - 3, 12, 15, 3); c.fill();
      c.fillStyle = '#d9d9d9'; c.beginPath(); c.roundRect(7 - 12, 3 - 3, 10, 4, 1.5); c.fill();
      c.restore();
    }
  }
  function drawDecorCard(c, type) {
    c.clearRect(0, 0, 240, 96);
    c.fillStyle = '#d8c48a'; c.fillRect(0, 78, 240, 18);
    const d = { id: 'card', type, x: 0, y: 0, sh: 1, sw: 1, color: T.decorations.types[type].defaultColor, seed: type === 'leaf' ? 11 : 51 };
    const u = 90; // "water height" for the card
    let g;
    if (type === 'leaf') { const h = V.leaf.h * u * 0.95 * 2.3, spread = V.leaf.spread * u * 2.3; g = { bx: 120, by: 84, h: Math.min(h, 76), spread, bw: spread * 0.6 }; }
    else { g = { bx: 120, by: 84, w: V.stone.w * u * 2.3, h: V.stone.h * u * 2.3 }; g.x0 = g.bx - g.w / 2; g.y0 = g.by - g.h * 0.85; }
    ctxSwap(c, () => (type === 'leaf' ? drawLeaf(d, g) : drawStone(d, g))); // reuse the tank drawing code
  }
  function ctxSwap(c, fn) { const keep = ctx; ctx = c; try { fn(); } finally { ctx = keep; } }
  function renderShop() {
    const list = $('shop-list');
    if (!list.children.length) {
      T.species.forEach((sp) => {
        const card = document.createElement('div'); card.className = 'card'; card.dataset.species = sp.id;
        const total = sp.growSec.reduce((a, b) => a + b, 0);
        const rar = sp.rarity && sp.rarity !== 'common' ? `<span class="rar rar-${sp.rarity}">${sp.rarity === 'rare' ? 'Rare' : 'Uncommon'}</span>` : '';
        card.innerHTML = `<canvas width="240" height="96"></canvas>${rar}<div class="n">${sp.name}</div><div class="l">${sp.latin}</div>
          <div class="s">Adult in ${fmt(total)} · sells up to ${G.sellPrice(sp, T.maxLevel)}g</div>
          <button class="btn buy" data-buy="${sp.id}"><svg><use href="#i-coin"/></svg><span class="price">${sp.price}</span><span class="lbl"></span></button>`;
        list.appendChild(card);
        const c = card.querySelector('canvas').getContext('2d');
        c.translate(120, 50); FishArt.drawFish(c, sp.id, 120, 0.6, {});
        card.querySelector('button').addEventListener('click', () => {
          const f = G.buyFish(sp.id);
          if (f) { toast(`${sp.name} added`, 'good'); renderShop(); } // v6: grows at once, no start meal
        });
      });
      T.foodPacks.forEach((p, i) => {
        const card = document.createElement('div'); card.className = 'card'; card.dataset.pack = i;
        card.innerHTML = `<canvas width="240" height="96"></canvas><div class="n">${p.food} food</div><div class="s">${(p.gold / p.food).toFixed(1)} gold per food</div>
          <button class="btn buy" data-food="${i}"><svg><use href="#i-coin"/></svg><span class="price">${p.gold}</span><span class="lbl"></span></button>`;
        $('shop-food').appendChild(card);
        drawBottleCard(card.querySelector('canvas').getContext('2d'), p.food);
        card.querySelector('button').addEventListener('click', () => { G.buyFood(i); renderShop(); });
      });
      ['leaf', 'stone'].forEach((type) => {
        const card = document.createElement('div'); card.className = 'card'; card.dataset.decor = type;
        card.innerHTML = `<canvas width="240" height="96"></canvas><div class="n">${type === 'leaf' ? 'Leaf' : 'Stone'}</div><div class="s">Free · move, size and colour it</div>
          <button class="btn buy" data-buydecor="${type}"><span class="price">${T.decorations.price ? T.decorations.price + ' gold' : 'Free'}</span><span class="lbl"></span></button>`;
        $('shop-decor').appendChild(card);
        drawDecorCard(card.querySelector('canvas').getContext('2d'), type);
        card.querySelector('button').addEventListener('click', () => {
          const d = G.buyDecor(type);
          if (d) { closeShop(); setTool('brush'); selectDecor(d.id); } // bible 27: edit mode opens on the new decoration
        });
      });
    }
    const full = G.state.fish.length >= G.capacity();
    list.querySelectorAll('button[data-buy]').forEach((b) => {
      const sp = G.SPECIES[b.dataset.buy];
      const locked = !G.isUnlocked(sp), poor = G.state.gold < sp.price;
      b.disabled = locked || full || poor;
      b.closest('.card').classList.toggle('locked', locked);
      b.classList.toggle('poor', poor && !full && !locked);
      b.querySelector('.price').hidden = locked; b.querySelector('svg').style.display = locked ? 'none' : '';
      b.querySelector('.lbl').textContent = locked ? `🔒 Aquarium level ${sp.unlockTankLevel}` : full ? ' · Tank full' : '';
    });
    $('shop-food').querySelectorAll('button[data-food]').forEach((b) => {
      const p = T.foodPacks[+b.dataset.food], locked = !G.packUnlocked(p), poor = G.state.gold < p.gold;
      b.disabled = poor || locked; b.classList.toggle('poor', poor && !locked);
      b.closest('.card').classList.toggle('locked', locked);
      b.querySelector('.price').hidden = locked; b.querySelector('svg').style.display = locked ? 'none' : '';
      b.querySelector('.lbl').textContent = locked ? `🔒 Aquarium level ${p.unlockTankLevel}` : '';
    });
    const dfull = G.decorFull();
    $('shop-decor').querySelectorAll('button[data-buydecor]').forEach((b) => {
      b.disabled = dfull; b.querySelector('.price').hidden = dfull;
      b.querySelector('.lbl').textContent = dfull ? 'Tank is full of decorations' : '';
    });
    const dead = G.state.fish.length - G.living();
    $('shop-note').textContent = shopTab === 'fish'
      ? `Tank: ${G.state.fish.length} / ${G.capacity()} fish${dead ? ` (${dead} dead: use the Net to remove)` : ''}. ${G.tankInfo().level < T.tank.maxLevel ? `Aquarium level ${T.tank.maxLevel}: room for ${G.capacityAt(T.tank.maxLevel)} fish.` : ''}`
      : shopTab === 'food' ? `You have ${G.state.food} food.` : `Decorations: ${G.state.decor.length} / ${T.decorations.maxInTank}. Selling one refunds what it cost.`;
  }

  // ------------------------------------------------------------ decoration edit mode (AD v4 7)
  let editing = false, selDecor = null;
  function enterEdit() {
    if (editing) return;
    editing = true; selDecor = null;
    $('deco-menu').hidden = true; $('deco-done').hidden = false; $('deco-done').classList.remove('left');
    toast('Tap a decoration to change it', '', { restart: true });
  }
  function exitEdit() {
    if (!editing) return;
    editing = false; selDecor = null; stopRepeat();
    $('deco-menu').hidden = true; $('deco-done').hidden = true;
    const t = [...$('toasts').children].find((e) => e.dataset.base === 'Tap a decoration to change it'); if (t) t.remove();
  }
  $('deco-done').addEventListener('click', () => setTool('hand'));
  const decorById = (id) => G.state.decor.find((d) => d.id === id);
  function selectDecor(id) {
    if (!editing) setTool('brush');
    selDecor = id;
    const d = decorById(id); if (!d) { deselectDecor(); return; }
    $('deco-menu').hidden = false;
    renderMenu(); placeMenu();
  }
  function deselectDecor() { selDecor = null; stopRepeat(); $('deco-menu').hidden = true; $('deco-done').classList.remove('left'); }
  /** dock on the side away from the decoration (centre x > 50% -> left), 8px from the tank edges and top.
   *  The menu never covers the decoration it edits: if the preferred side would overlap it, the other side is used;
   *  if both would (a 2.0x leaf near the middle), the menu docks on the roomier side and shrinks (CSS scale, not
   *  below 0.8) just enough to clear it. keepSide (moves): stay on the current side while it still clears, so the
   *  menu doesn't jump under the finger while an arrow is held.
   *  While the menu is docked right, the Done button moves to the top-left corner so they don't overlap. */
  function placeMenu(keepSide) {
    const d = decorById(selDecor); if (!d) return;
    const m = $('deco-menu'), g = decorGeom(d), mw = m.offsetWidth, mh = m.offsetHeight, E = 8, GAP = 2;
    const covers = (lft, s) => { const x0 = lft ? E : W - E - mw * s, x1 = x0 + mw * s; return g.x0 < x1 + GAP && g.x1 > x0 - GAP && g.y0 < E + mh * s + GAP && g.y1 > E; };
    let left = g.bx > W / 2, s = 1;
    if (keepSide && (m.classList.contains('dock-left') || m.classList.contains('dock-right'))) {
      const cur = m.classList.contains('dock-left');
      if (!covers(cur, 1)) left = cur;
    }
    if (covers(left, 1) && !covers(!left, 1)) left = !left;
    if (covers(left, 1)) {
      const roomL = g.x0 - E - GAP, roomR = W - E - GAP - g.x1, roomTop = g.y0 - E - GAP;
      left = roomL > roomR;
      s = Math.max(0.8, Math.min(1, Math.max(Math.max(roomL, roomR) / mw, roomTop / mh)));
    }
    m.style.transformOrigin = left ? 'top left' : 'top right';
    m.style.transform = s < 1 ? `scale(${s.toFixed(4)})` : '';
    m.classList.toggle('dock-left', left); m.classList.toggle('dock-right', !left);
    $('deco-done').classList.toggle('left', !left);
  }
  function renderMenu() {
    const d = decorById(selDecor); if (!d) return;
    const S = T.decorations.scale, eps = 1e-6;
    $('dm-title').textContent = d.type === 'leaf' ? 'Leaf' : 'Stone';
    $('dm-scale').textContent = `H ${d.sh.toFixed(1)}x  W ${d.sw.toFixed(1)}x`;
    const cap = { taller: d.sh >= S.heightMax - eps, shorter: d.sh <= S.heightMin + eps, wider: d.sw >= S.widthMax - eps, narrower: d.sw <= S.widthMin + eps };
    document.querySelectorAll('#deco-menu [data-size]').forEach((b) => b.classList.toggle('capped', cap[b.dataset.size]));
    const c = $('dm-color'); if (document.activeElement !== c) c.value = d.color;
    c.style.setProperty('--track', decorGradientCss(d.type)); c.style.setProperty('--thumb', decorColorCss(d));
    $('dm-sell').textContent = `Sell · refund ${d.paid || 0} gold`;
  }
  function clampDecor(d) {
    const g = decorGeom(d), half = g.half, lo = (INSET + half) / W, hi = (W - INSET - half) / W;
    d.x = lo > hi ? 0.5 : Math.max(lo, Math.min(hi, d.x));
    // back / upper limit: the sand's back edge (y 0). Front / lower limit (Maksims 20:12): the BASE may reach the sand's
    // front edge = the bottom of the water area / front glass (y = H), at every size; d.y is in units of the
    // decorFloorBand part of the sand band, so the front edge is y = 1 / decorFloorBand.
    d.y = Math.max(0, Math.min(1 / V.decorFloorBand, d.y));
  }
  function moveDecor(dir) {
    const d = decorById(selDecor); if (!d) return;
    // Maksims 20:34: left/right step stepPxPerTapX (8 px), up/down stepPxPerTapY (4 px); tap and hold-repeat alike
    const mv = T.decorations.move, sx = mv.stepPxPerTapX, sy = mv.stepPxPerTapY, band = (H - SAND) * V.decorFloorBand;
    if (dir === 'left') d.x -= sx / W; else if (dir === 'right') d.x += sx / W;
    else if (dir === 'up') d.y -= sy / band; else if (dir === 'down') d.y += sy / band;
    clampDecor(d); placeMenu(true); G.save();
  }
  function sizeDecor(kind) {
    const d = decorById(selDecor); if (!d) return;
    const S = T.decorations.scale, st = S.stepPerTap, q = (v) => Math.round(v * 10) / 10;
    if (kind === 'taller') d.sh = q(Math.min(S.heightMax, d.sh + st)); else if (kind === 'shorter') d.sh = q(Math.max(S.heightMin, d.sh - st));
    else if (kind === 'wider') d.sw = q(Math.min(S.widthMax, d.sw + st)); else if (kind === 'narrower') d.sw = q(Math.max(S.widthMin, d.sw - st));
    clampDecor(d); renderMenu(); placeMenu(); G.save();
  }
  let repT = 0, repI = 0;
  function stopRepeat() { clearTimeout(repT); clearInterval(repI); document.querySelectorAll('#deco-menu .rb.pressed').forEach((b) => b.classList.remove('pressed')); }
  document.querySelectorAll('#deco-menu [data-move]').forEach((b) => {
    b.addEventListener('pointerdown', (e) => {
      e.preventDefault(); stopRepeat(); b.classList.add('pressed');
      try { b.setPointerCapture(e.pointerId); } catch (_) { /* synthetic events */ }
      moveDecor(b.dataset.move); // one step per tap; holding repeats every 80 ms after 300 ms
      repT = setTimeout(() => { repI = setInterval(() => moveDecor(b.dataset.move), V.decorMoveRepeatMs); }, V.decorMoveDelayMs);
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => b.addEventListener(ev, stopRepeat));
  });
  document.querySelectorAll('#deco-menu [data-size]').forEach((b) => b.addEventListener('click', () => sizeDecor(b.dataset.size)));
  $('dm-color').addEventListener('input', (e) => { const d = decorById(selDecor); if (!d) return; d.color = +e.target.value; renderMenu(); });
  $('dm-color').addEventListener('change', () => G.save());
  $('dm-close').addEventListener('click', deselectDecor);
  $('dm-sell').addEventListener('click', () => {
    const d = decorById(selDecor); if (!d) return;
    const noun = d.type === 'leaf' ? 'leaf' : 'stone';
    confirmBox(`Sell this ${noun}? You get ${d.paid || 0} gold back.`, 'Sell', () => { G.sellDecor(d.id); deselectDecor(); G.save(); },
      (pc) => { const c = pc.getContext('2d'); c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, pc.width, pc.height); drawDecorCard(c, d.type); }, 'danger');
  });
  function hitDecor(x, y) {
    const list = G.state.decor.slice().sort((a, b) => b.y - a.y); // front first
    for (const d of list) {
      const g = decorGeom(d), padX = Math.max(0, (44 - (g.x1 - g.x0)) / 2), padY = Math.max(0, (44 - (g.y1 - g.y0)) / 2);
      if (x >= g.x0 - padX && x <= g.x1 + padX && y >= g.y0 - padY && y <= g.y1 + padY) return d;
    }
    return null;
  }

  // ------------------------------------------------------------ net tool (AD "Net cursor and target highlight")
  // Shown while the Net is selected and a finger is down or a mouse is over the tank. Touch (Maksims 2026-09-28): the
  // fingertip holds the wooden handle NET_TOUCH_GRIP (65%) of the way down it, so the hoop sits up and to the left of the
  // finger, clear of it; the tilt pivots round the fingertip so the finger stays on the stick. Mouse: hoop centre on the
  // cursor. Targeting always uses the hoop centre. Tilts with horizontal movement (max 12 deg, eases back in ~200 ms). The targeted fish gets a white body outline + soft glow and the rim turns --accent.
  // Letting go over a fish: the hoop dips (1 -> 0.9 -> 1 over 150 ms), then the confirm opens (dead fish: removed).
  const net = { on: false, x: 0, y: 0, fx: 0, fy: 0, touch: false, target: null, vx: 0, tilt: 0, dip: -1, lastX: 0, lastT: 0, moved: 0 };
  const netR = () => (LARGE() ? 30 : 22);
  // handle geometry (drawNetCursor): leaves the hoop at 45 deg down-right, from R to R + NET_HANDLE_LEN x R from the centre
  const NET_HANDLE_A = Math.PI / 4, NET_HANDLE_LEN = 1.8, NET_TOUCH_GRIP = 0.65;
  /** distance from the hoop centre to the fingertip on touch: the grip point 65% down the handle */
  const netGripDist = () => netR() * (1 + NET_TOUCH_GRIP * NET_HANDLE_LEN);
  function netAt(px, py, touch) {
    if (!touch) return { x: px, y: py };
    const d = netGripDist(), a = NET_HANDLE_A + net.tilt;
    return { x: px - Math.cos(a) * d, y: py - Math.sin(a) * d };
  }
  /** same pick rule as taps: front-most fish whose body contains the point, otherwise the nearest centre within the hoop radius */
  function netPick(x, y) {
    const fish = G.state.fish;
    for (let i = fish.length - 1; i >= 0; i--) {
      const m = anim.get(fish[i].id); if (!m) continue;
      const L = fishLen(fish[i]), dx = (x - m.x) / (L * 0.5), dy = (y - m.y) / Math.max(4, bodyHalfDepth(L));
      if (dx * dx + dy * dy <= 1) return fish[i];
    }
    let best = null, bestD = netR();
    for (const f of fish) { const m = anim.get(f.id); if (!m) continue; const d = Math.hypot(x - m.x, y - m.y); if (d < bestD) { bestD = d; best = f; } }
    return best;
  }
  function netMove(px, py, touch) {
    const now = performance.now(), dt = Math.max(1, now - net.lastT) / 1000;
    // speed and drag distance from the pointer itself (on touch the hoop also swings with the tilt)
    if (net.on) { net.vx = net.vx * 0.5 + ((px - net.fx) / dt) * 0.5; net.moved += Math.hypot(px - net.fx, py - net.fy); }
    net.fx = px; net.fy = py; net.touch = !!touch; net.lastT = now;
    const q = netAt(px, py, touch); net.x = q.x; net.y = q.y;
  }
  function stepNet(dt) {
    net.vx *= Math.exp(-dt / 0.08);
    const want = Math.max(-1, Math.min(1, net.vx / 500)) * (12 * Math.PI / 180);
    net.tilt += (want - net.tilt) * (1 - Math.exp(-dt / 0.06));
    if (net.touch && (net.on || net.dip >= 0)) { const q = netAt(net.fx, net.fy, true); net.x = q.x; net.y = q.y; } // pivot round the fingertip
    if (net.dip >= 0) { net.dip += dt; if (net.dip > 0.15) net.dip = -1; }
  }
  function drawNetTargetGlow(f, L) { // called inside the fish's own transform: body outline only (fins and tail excluded)
    ctx.save();
    ctx.lineJoin = 'round';
    FishArt.bodyOutline(ctx, f.sp, L, { dead: f.state === 'DEAD' });
    ctx.shadowColor = 'rgba(255,255,255,0.35)'; ctx.shadowBlur = 6 * DPR;
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 6; ctx.stroke();
    ctx.shadowBlur = 0; ctx.shadowColor = 'transparent';
    ctx.strokeStyle = 'rgba(255,255,255,0.9)'; ctx.lineWidth = 2; ctx.stroke();
    ctx.restore();
  }
  function drawNetCursor(dt) {
    stepNet(dt);
    if (tool !== 'net' || editing || !(net.on || net.dip >= 0)) return;
    const big = LARGE(), R = netR(), D = R * 2, rim = big ? 4 : 3, gap = big ? 8 : 6, hw = big ? 7 : 5;
    const k = net.dip >= 0 ? 1 - 0.1 * Math.sin(Math.PI * Math.min(1, net.dip / 0.15)) : 1;
    ctx.save();
    ctx.translate(net.x, net.y); ctx.rotate(net.tilt); ctx.scale(k, k);
    // handle: leaves the hoop's lower-right at 45 deg, 0.9 x hoop diameter (NET_HANDLE_LEN x R) long, rounded end
    const a = NET_HANDLE_A, x0 = Math.cos(a) * R, y0 = Math.sin(a) * R, x1 = Math.cos(a) * R * (1 + NET_HANDLE_LEN), y1 = Math.sin(a) * R * (1 + NET_HANDLE_LEN);
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#6a4424'; ctx.lineWidth = hw + 2; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    ctx.strokeStyle = '#b07a44'; ctx.lineWidth = hw; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    // mesh: fill + 1px diagonal grid, clipped to the hoop
    ctx.save();
    ctx.beginPath(); ctx.arc(0, 0, R, 0, Math.PI * 2); ctx.clip();
    ctx.fillStyle = 'rgba(200,230,255,0.10)'; ctx.fillRect(-R, -R, D, D);
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1; ctx.beginPath();
    for (let c = -2 * R; c <= 2 * R; c += gap) { ctx.moveTo(c - R, -R); ctx.lineTo(c + R, R); ctx.moveTo(c - R, R); ctx.lineTo(c + R, -R); }
    ctx.stroke();
    ctx.restore();
    // rim: 1px #5a6a78 outer edge, then 3px (Large 4px) #e8eef2, --accent while a fish is targeted
    ctx.strokeStyle = '#5a6a78'; ctx.lineWidth = rim + 2; ctx.beginPath(); ctx.arc(0, 0, R, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = net.target ? '#37c3ff' : '#e8eef2'; ctx.lineWidth = rim; ctx.beginPath(); ctx.arc(0, 0, R, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
  }
  let netPending = 0;
  function netRelease(f) { // dip once, then act: live fish -> confirm, dead fish -> removed (a second release during the dip is ignored)
    if (netPending) return;
    net.dip = 0;
    netPending = setTimeout(() => { netPending = 0; net.target = null; if (pointer.touch) net.on = false; if (G.state.fish.includes(f)) netFish(f); }, 150);
  }

  // ------------------------------------------------------------ input on the tank
  const pointer = { x: 0, y: 0, down: false, inside: false, id: null, lx: 0, ly: 0 };
  function local(e) { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  function hitFish(x, y) {
    const fish = G.state.fish;
    for (let i = fish.length - 1; i >= 0; i--) {
      const m = anim.get(fish[i].id); if (!m) continue;
      const L = fishLen(fish[i]);
      const dx = (x - m.x) / Math.max(22, L * 0.7 + 10), dy = (y - m.y) / Math.max(22, L * 0.35 + 12); // tap target >= 44 x 44
      if (dx * dx + dy * dy <= 1) return fish[i];
    }
    let best = null, bestD = 44; // forgiving tap: nearest fish centre within 44px
    for (const f of fish) { const m = anim.get(f.id); if (!m) continue; const d = Math.hypot(x - m.x, y - m.y); if (d < bestD) { bestD = d; best = f; } }
    return best;
  }
  canvas.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    const p = local(e);
    const touch = e.pointerType === 'touch' || e.pointerType === 'pen';
    Object.assign(pointer, { touch, x: p.x, y: p.y, lx: p.x, ly: p.y - (touch && tool === 'sponge' ? spongeR() * V.spongeTouchLiftFrac : 0), down: true, inside: true, id: e.pointerId });
    try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
    if (!$('shop').hidden) { closeShop(); return; }
    if (editing) { const d = hitDecor(p.x, p.y); if (d) selectDecor(d.id); else deselectDecor(); return; } // fish can't be tapped
    if (tool === 'hand') { const f = hitFish(p.x, p.y); if (f) openPanel(f.id); else closePanel(); }
    else if (tool === 'food') {
      const r = G.feedTap(p.x / W, p.y / H, W, H); // 1 food per tap to the hungry fish nearest the tap
      if (r.ok) flakeShower(p.x, p.y, r);
    } else if (tool === 'sponge') rubTo(p.x, p.y - spongeLift());
    else if (tool === 'net') { net.on = false; netMove(p.x, p.y, touch); net.on = true; net.vx = 0; net.moved = 0; net.target = netPick(net.x, net.y); }
  });
  canvas.addEventListener('pointermove', (e) => {
    const p = local(e);
    pointer.inside = true;
    if (!pointer.down) pointer.touch = e.pointerType === 'touch' || e.pointerType === 'pen';
    if (pointer.down && e.pointerId === pointer.id && tool === 'sponge') {
      const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
      (evs.length ? evs : [e]).forEach((ce) => { const q = local(ce); rubTo(q.x, q.y - spongeLift()); });
    }
    pointer.x = p.x; pointer.y = p.y;
    if (tool === 'net' && !editing && net.dip < 0) { // the net follows the pointer (while pressed; mouse also on hover) and targets the fish under the hoop
      const touch = e.pointerType === 'touch' || e.pointerType === 'pen';
      if (pointer.down || !touch) { netMove(p.x, p.y, touch); net.on = true; net.target = netPick(net.x, net.y); }
    }
  });
  function endPointer(e) {
    if (e.pointerId !== pointer.id) return;
    const wasDown = pointer.down;
    pointer.down = false; pointer.id = null;
    if (tool === 'net' && wasDown && !editing) { // let go: live fish -> confirm, dead fish -> removed, empty water -> nothing
      const p = local(e);
      let f = null;
      if (e.type === 'pointerup') {
        // a touch TAP (no drag) picks the fish under the finger, like the other tools; a drag uses the lifted hoop
        f = pointer.touch && net.moved < 8 ? hitFish(p.x, p.y) : (pointer.touch ? netPick(net.x, net.y) : netPick(p.x, p.y));
      }
      if (f) { net.target = f; netRelease(f); }
      else { net.target = null; if (pointer.touch) net.on = false; }
    }
  }
  canvas.addEventListener('pointerup', endPointer);
  canvas.addEventListener('pointercancel', endPointer);
  canvas.addEventListener('pointerleave', () => { if (!pointer.down) { pointer.inside = false; net.on = false; net.target = null; } });
  function rubTo(x, y) {
    const r = G.rub(pointer.lx / W, pointer.ly / H, x / W, y / H, W, H, spongeR(), WATER_H);
    pointer.lx = x; pointer.ly = y;
    if (r.cleaned) floatClean(r.gold, x, y, r.food);
  }
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') { if (!$('dbg-pass').hidden) { closeDbgPass(); return; } closePanel(); closeShop(); if (editing) deselectDecor(); } });

  // ------------------------------------------------------------ game events
  G.on((type, d) => {
    const m = d.fish ? anim.get(d.fish.id) : null;
    const fx = m ? m.x : W / 2, fy = m ? m.y - 20 : H / 2;
    const name = d.fish ? G.SPECIES[d.fish.sp].name : '';
    switch (type) {
      case 'levelup':
        floatLevelUp(d.gold, d.xp, fx, fy);
        toast(d.fish.level >= T.maxLevel ? `${name} is now an adult (L${d.fish.level})! +${d.gold} gold` : `${name} reached level ${d.fish.level}! +${d.gold} gold`, 'good');
        break;
      case 'tanklevel':
        { // NUMBERS v5.1 8 (v6.1: player-facing "Aquarium level"): "Aquarium level 8: Pearl Gourami and Clown Loach (rare) unlocked, room for 2 more fish"
          const names = d.unlocks.map((id) => { const sp = G.SPECIES[id]; return sp.name + (sp.rarity && sp.rarity !== 'common' ? ` (${sp.rarity})` : ''); });
          const parts = [];
          if (names.length) parts.push(`${names.length > 1 ? names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1] : names[0]} unlocked`);
          if (d.extraSlots) parts.push(`room for ${d.extraSlots} more fish`);
          (d.packs || []).forEach((pk) => parts.push(`${pk.food}-food pack in the shop`));
          toast(parts.length ? `Aquarium level ${d.level}: ${parts.join(', ')}` : `Aquarium level ${d.level}!`, 'good');
        }
        break;
      case 'hungry': toast(`${name} is hungry!`, 'bad'); break;
      case 'death': toast(`${name} died`, 'bad'); break;
      case 'removed': anim.delete(d.fish.id); toast('Fish removed', '', { ms: 1600 }); if (selectedId === d.fish.id) closePanel(); break;
      case 'feedblocked': blockedFeed(); break;
      case 'feedfail': toast(d.reason === 'nofood' ? 'Out of food' : "Nobody's hungry", d.reason === 'nofood' ? 'bad' : ''); break;
      case 'cleaned': toast(`Tank clean! +${d.gold} gold${d.food ? ` · +${d.food} food` : ''}${d.xp ? ` · +${d.xp} XP` : ''}`, 'good'); break;
      case 'sold':
        anim.delete(d.fish.id); if (selectedId === d.fish.id) closePanel();
        toast(d.gold ? `Sold ${name} for ${d.gold} gold` : `Released ${name}`, d.gold ? 'good' : '');
        if (d.xp) floatText(`+${d.xp} XP`, fx, fy, '#9fdcff', true);
        break;
      case 'foodbought': toast(`+${d.food} food (−${d.gold} gold)`); break;
      case 'decorsold': toast(`Sold the ${d.decor.type} (+${d.gold} gold)`); break;
      case 'grant': toast(`Starter grant: gold topped up to ${d.gold}`, 'good'); break;
      case 'msg': toast(d.text, 'bad'); break;
      case 'reset': anim.clear(); pellets.length = 0; closePanel(); closeShop(); exitEdit(); setTool('hand'); $('away').hidden = true; break;
      default: break;
    }
    if (!$('shop').hidden) renderShop();
  });

  // ------------------------------------------------------------ debug row
  // ------------------------------------------------------------ debug row (password gate; closed state is NOT saved)
  const DBG_PASS = '123456'; // casual gate: plain string compare is fine (Maksims 2026-09-28)
  let dbgOpen = false;
  function setDebugOpen(on) {
    dbgOpen = !!on;
    $('debug').classList.toggle('open', dbgOpen);
    $('dbg-toggle').setAttribute('aria-pressed', dbgOpen ? 'true' : 'false');
  }
  function closeDbgPass() {
    $('dbg-pass').hidden = true; $('dbg-pass-err').hidden = true; $('dbg-pass-input').value = '';
  }
  function askDbgPass() {
    $('dbg-pass-err').hidden = true; $('dbg-pass-input').value = '';
    $('dbg-pass').hidden = false;
    setTimeout(() => { try { $('dbg-pass-input').focus(); $('dbg-pass-input').select(); } catch (e) { /* ignore */ } }, 30);
  }
  function tryDbgUnlock() {
    const ok = $('dbg-pass-input').value === DBG_PASS;
    if (ok) { closeDbgPass(); setDebugOpen(true); }
    else { $('dbg-pass-err').hidden = false; $('dbg-pass-input').select(); }
    return ok;
  }
  $('dbg-toggle').addEventListener('click', () => {
    if (dbgOpen) { setDebugOpen(false); closeDbgPass(); } // one tap closes, no password
    else askDbgPass(); // every open asks again
  });
  $('dbg-pass-yes').addEventListener('click', tryDbgUnlock);
  $('dbg-pass-no').addEventListener('click', closeDbgPass);
  $('dbg-pass-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); tryDbgUnlock(); }
    else if (e.key === 'Escape') { e.preventDefault(); closeDbgPass(); }
  });
  // click the dimmed backdrop to cancel (same as Cancel)
  $('dbg-pass').addEventListener('click', (e) => { if (e.target === $('dbg-pass')) closeDbgPass(); });
  setDebugOpen(false); // reload always starts closed (not in save)

  T.debugSpeeds.forEach((s) => {
    const b = document.createElement('button'); b.className = 'dbg'; b.dataset.speed = s; b.textContent = `×${s}`;
    b.addEventListener('click', () => { G.state.speed = s; G.save(); });
    $('speed-btns').appendChild(b);
  });
  (() => { // "Your tank is empty" modal line, built from the same numbers newState() uses
    const locked = T.species.filter((sp) => (sp.unlockTankLevel || 1) > 1).map((sp) => sp.name);
    const list = locked.length > 1 ? `${locked.slice(0, -1).join(', ')} and ${locked[locked.length - 1]}` : locked.join('');
    const fc = T.newTank && T.newTank.firstCleanReward;
    $('newtank-reset').textContent = `Everything resets: ${T.startGold} gold, ${T.startFood} food, ${T.startDiamonds || 0} diamonds, no fish, aquarium level 1 (0 XP)` +
      (locked.length ? `, ${list} lock again` : '') + `, only the default decorations, and the tank starts dirty (stage ${T.newTank ? T.newTank.dirtStartStage : 3})` +
      (fc ? `. The first clean pays ${fc.gold} gold and ${fc.food} food again.` : '.');
  })();
  $('btn-newtank').addEventListener('click', () => {
    const keep = G.state.speed; G.reset(); G.state.speed = keep; G.save();
    $('tankover').hidden = true; closePanel(); clearToasts(); toast('New tank started', 'good');
  });
  $('dbg-gold').addEventListener('click', () => { G.state.gold += 100; toast('Debug: +100 gold'); });
  $('dbg-xp').addEventListener('click', () => { G.debugAddXp(50); if (!$('shop').hidden) renderShop(); });
  $('dbg-reset').addEventListener('click', () => {
    confirmBox('Reset the save and start over?', 'Reset', () => {
      const keep = G.state.speed; G.reset(); G.state.speed = keep; G.save(); clearToasts(); toast('Save reset');
    }, null, 'danger');
  });

  // ------------------------------------------------------------ rotate screen (AD v4 1)
  let portrait = false;
  function checkOrientation() {
    const p = window.innerHeight > window.innerWidth;
    document.body.classList.toggle('portrait', p);
    $('rotate').hidden = !p;
    $('rotate').classList.toggle('large', Math.min(window.innerWidth, window.innerHeight) >= 600);
    if (p !== portrait) { portrait = p; if (p) { pointer.down = false; stopRepeat(); } }
  }

  // ------------------------------------------------------------ main loop
  let last = performance.now();
  let panelAcc = 0, frames = 0;
  function frame(now) {
    let dtReal = (now - last) / 1000; last = now;
    if (dtReal < 0) dtReal = 0;
    if (dtReal > 5) { // tab was hidden / device asleep: replay like offline time and summarise
      const r = G.catchUp(dtReal * G.state.speed);
      if (r.sec >= 60) showAway(r);
    } else G.tick(dtReal * G.state.speed); // the game clock runs even while the rotate screen is up
    if (portrait) { requestAnimationFrame(frame); return; } // upright: input and drawing pause
    const dtAnim = Math.min(dtReal, 0.05);
    realTime += dtAnim; frames++;
    const p = pulseAmt();

    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    drawWater();
    drawSand();
    drawGlassLines();
    drawDecor();        // behind the fish, sorted by base y
    drawBubbles(dtAnim);
    drawPellets(dtAnim);
    drawFishAll(dtAnim);
    drawGlass();
    drawDirtLayer(p);   // in front of the fish, behind the spots
    drawSpots(p);
    drawSponge();
    drawFloaters(dtAnim);
    drawNetCursor(dtAnim);

    updateHUD();
    if (selDecor && !$('deco-menu').hidden) renderMenu();
    panelAcc += dtReal;
    if (panelAcc > 0.2) { panelAcc = 0; renderPanel(); }
    requestAnimationFrame(frame);
  }

  setInterval(() => G.save(), V.saveEveryMs);
  document.addEventListener('visibilitychange', () => { if (document.hidden) G.save(); });
  window.addEventListener('pagehide', () => G.save());
  /** fluid layout: pin #app to the visible viewport height (real phones: 844x390, 932x430, 667x375, 896x414 ...) */
  function fitViewport() {
    const vv = window.visualViewport, h = vv && vv.scale <= 1.01 ? vv.height : window.innerHeight;
    document.documentElement.style.setProperty('--app-h', `${Math.round(h)}px`);
  }
  function onViewport() { fitViewport(); checkOrientation(); resize(); }
  window.addEventListener('resize', onViewport);
  window.addEventListener('orientationchange', () => { onViewport(); setTimeout(onViewport, 250); });
  if (window.visualViewport) window.visualViewport.addEventListener('resize', onViewport);
  fitViewport();
  if (window.ResizeObserver) new ResizeObserver(resize).observe(wrap);

  // ------------------------------------------------------------ "while you were away" (NUMBERS v4 11.1): no window when nothing to report
  function showAway(r) {
    if (!r || !r.lines || !r.lines.length) return false;
    $('away-time').textContent = `(${fmt(r.sec)}${r.realSec != null && G.state.speed !== 1 && r.realSec !== r.sec ? ' game time' : ''})`;
    const ul = $('away-list'); ul.innerHTML = '';
    r.lines.forEach((t) => { const li = document.createElement('li'); li.textContent = t[0].toUpperCase() + t.slice(1); ul.appendChild(li); });
    $('away').hidden = false;
    return true;
  }
  $('away-ok').addEventListener('click', () => { $('away').hidden = true; });

  checkOrientation();
  resize();
  setTool('hand');
  if (awaySummary && awaySummary.sec >= 60) showAway(awaySummary);
  G.save();
  requestAnimationFrame((t) => { last = t; frame(t); });

  // ------------------------------------------------------------ test/debug hook (read-mostly): tests/verify.py
  const rect = (el) => { const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
  window.AQ = {
    game: G,
    fishScreen(id) { const m = anim.get(id); return m ? { x: m.x, y: m.y } : null; },
    showAway,
    toast, // test hook
    pinFish(id, nx, ny) {
      const f = G.state.fish.find((x) => x.id === id); if (!f) return false;
      const m = motion(f); m.x = nx * W; m.y = ny * H; m.tx = m.x; m.ty = m.y; m.vx = 0; m.vy = 0; m.pause = 1e9; m.retarget = 1e9;
      f.x = nx; f.y = ny; return true;
    },
    filmInfo() {
      if (!film.strength || !film.a) return { strength: film.strength, max: 0 };
      let max = 0, midMax = 0; for (let i = 0; i < film.a.length; i++) { max = Math.max(max, film.a[i]); if (film.mid[i]) midMax = Math.max(midMax, film.a[i]); }
      return { strength: film.strength, max, midMax, cols: film.cols, rows: film.rows };
    },
    guardCheck() {
      if (!film.strength || !film.a) return { worst: 0 };
      let worst = 0; const spots = G.state.dirt.spots.map((s) => ({ x: s.x * W, y: s.y * H, r: spotR(s) * 1.25, a: spotFillAlpha(s) }));
      for (let j = 0; j < film.rows; j++) for (let i = 0; i < film.cols; i++) {
        const idx = j * film.cols + i; if (!film.mid[idx]) continue;
        const px = (i + 0.5) * W / film.cols, py = (j + 0.5) * H / film.rows;
        for (const sp of spots) if (Math.hypot(px - sp.x, py - sp.y) < sp.r) worst = Math.max(worst, 1 - (1 - film.a[idx]) * (1 - sp.a));
        worst = Math.max(worst, film.a[idx]);
      }
      return { worst: +worst.toFixed(4) };
    },
    spotsScreen() { return G.state.dirt.spots.map((s) => ({ x: s.x * W, y: s.y * H, r: spotR(s), grime: s.grime, stage: s.stage, look: V.dirtStages[s.stage - 1].look, over: s.over })); },
    size() { return { W, H, waterH: WATER_H }; },
    geom() { return { W, H, surf: SURF, waterH: WATER_H, sand: SAND, inset: INSET, spongeR: spongeR() }; },
    glassLine,
    layout() { // screen boxes (CSS px) of the AD v4 frame parts
      const tools = [...document.querySelectorAll('#tools .tool')].map((b) => ({ label: b.querySelector('span:last-child').textContent, ...rect(b),
        icon: rect(b.querySelector('svg')), pressed: b.getAttribute('aria-pressed') }));
      return { vw: innerWidth, vh: innerHeight, tools, column: rect($('tools')), hud: rect($('hud')), tank: rect(wrap), debug: rect($('debug')),
        dirt: rect($('dirt-win')), badge: rect($('food-badge')), foodIcon: rect($('food-icon')),
        scrollW: document.documentElement.scrollWidth, scrollH: document.documentElement.scrollHeight };
    },
    fishIcon(id) { const f = G.state.fish.find((x) => x.id === id), m = anim.get(id); if (!f || !m) return null; const L = fishLen(f), p = statusIconPos(f, L, m); return { x: m.x + p.x, y: m.y + p.y, L, face: m.faceAnim >= 0 ? 1 : -1, halfDepth: bodyHalfDepth(L) }; },
    decorScreen() { return G.state.decor.map((d) => ({ id: d.id, type: d.type, ...decorGeom(d), sh: d.sh, sw: d.sw, color: d.color, x: d.x, y: d.y })); },
    net() { return { on: net.on, x: net.x, y: net.y, fx: net.fx, fy: net.fy, touch: net.touch, target: net.target ? net.target.id : null, tilt: net.tilt, dip: net.dip, r: netR(),
      handleA: NET_HANDLE_A, handleLen: NET_HANDLE_LEN, grip: NET_TOUCH_GRIP }; },
    debugOpen() { return !!dbgOpen; }, openDebug(pw) { if (pw === DBG_PASS) { setDebugOpen(true); closeDbgPass(); return true; } return false; }, closeDebug() { setDebugOpen(false); closeDbgPass(); },
    edit() { return { editing, selDecor, menu: $('deco-menu').hidden ? null : rect($('deco-menu')), done: $('deco-done').hidden ? null : rect($('deco-done')), tank: rect(wrap) }; },
    selectDecor, pulse() { return { p: pulseAmt(), count: blockedCount, spots: drawnSpots.slice() }; },
    pulseAt(t) { return pulseAmt(pulseT0 + t); },
    frames() { return frames; },
    floatBoxes() { return floaters.filter((f) => f.box).map((f) => ({ text: f.text, grp: f.grp, ...f.box })); },
    testFloat(kind, x, y) {
      if (kind === 'clean') floatClean(6, x, y); else if (kind === 'levelup') floatLevelUp(200, 200, x, y); else if (kind === 'feed') floatFeedGold(1, x, y);
    },
    flakes() { return { ...flakeStats, live: pellets.map((p) => ({ x: p.x, y: p.y, x0: p.x0, y0: p.y0, t: p.t, fishId: p.fishId })) }; },
    fishLen(sp, level) { return fishLen({ sp, level }); },
    floats(clear) { const out = floatLog.slice(); if (clear) floatLog.length = 0; return out; },
    setTool, openShop, setShopTab,
  };
})();
