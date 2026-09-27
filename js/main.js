/* Aquarium UI: rendering, swimming animation, input, panels, save loop. */
(function () {
  'use strict';
  const G = window.Game, T = G.T, CFG = G.CFG, V = CFG.VISUAL;
  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------ boot / URL
  const params = new URLSearchParams(location.search);
  G.load();
  const urlSpeed = parseFloat(params.get('speed'));
  if (urlSpeed > 0 && urlSpeed <= 1000) G.state.speed = urlSpeed; // ?speed=60 overrides saved/default speed
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
  const corpses = [];
  const pellets = [];
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
  function stepFish(f, dt) {
    const m = motion(f);
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
      const bobY = Math.sin(m.bob) * (hungry ? 1.5 : 3);
      ctx.save();
      ctx.translate(m.x, m.y + bobY);
      if (selectedId === f.id) {
        ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.setLineDash([5, 4]); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.ellipse(0, 0, L * 0.75, L * 0.45, 0, 0, 7); ctx.stroke(); ctx.setLineDash([]);
      }
      const tilt = Math.max(-0.35, Math.min(0.35, Math.atan2(m.vy, Math.abs(m.vx) + 10))) + (hungry ? 0.12 : 0);
      ctx.save();
      ctx.scale(m.faceAnim >= 0 ? Math.max(0.08, m.faceAnim) : Math.min(-0.08, m.faceAnim), 1);
      ctx.rotate(tilt);
      if (hungry) ctx.globalAlpha = 0.9;
      FishArt.drawFish(ctx, f.sp, L, m.phase, { hungry });
      ctx.restore();
      drawStatusIcon(f, L);
      ctx.restore();
    });
  }
  function drawStatusIcon(f, L) {
    let color = null, glyph = null;
    if (f.state === 'WAITING') { color = '#37c3ff'; glyph = 'food'; }
    else if (f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY') {
      const frac = f.deathLeft / G.deathSecFor(G.SPECIES[f.sp], f.level);
      color = frac < 0.33 ? '#ff3b3b' : '#ffa53b'; glyph = '!';
    }
    if (!color) return;
    const pulse = 1 + Math.sin(realTime * 6) * 0.08;
    const y = -L * 0.45 - 12, r = 9 * pulse;
    ctx.fillStyle = color; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(0, y, r, 0, 7); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-4, y + r - 2); ctx.lineTo(0, y + r + 5); ctx.lineTo(4, y + r - 2); ctx.fill();
    ctx.fillStyle = '#fff';
    if (glyph === '!') { ctx.font = '900 13px Nunito, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', 0, y + 1); }
    else { for (const [dx, dy] of [[-3, -2], [2, -3], [0, 2], [3, 2], [-3, 3]]) { ctx.beginPath(); ctx.arc(dx, y + dy, 1.4, 0, 7); ctx.fill(); } }
  }
  function drawCorpses(dt) {
    for (let i = corpses.length - 1; i >= 0; i--) {
      const c = corpses[i];
      c.t += dt; c.y -= dt * 25; if (c.y < 14) c.y = 14;
      ctx.save(); ctx.globalAlpha = Math.max(0, 1 - c.t / 4);
      ctx.translate(c.x, c.y + Math.sin(c.t * 2) * 2);
      FishArt.drawFish(ctx, c.sp, c.L, 0, { dead: true });
      ctx.restore();
      if (c.t > 4) corpses.splice(i, 1);
    }
  }
  function drawPellets(dt) {
    for (let i = pellets.length - 1; i >= 0; i--) {
      const p = pellets[i];
      p.t += dt;
      if (p.y < sandTop() - 2) { p.y += dt * (26 + p.s * 8); p.x += Math.sin(p.t * 3 + p.s) * dt * 8; }
      ctx.globalAlpha = Math.max(0, Math.min(1, 5 - p.t));
      ctx.fillStyle = p.c; ctx.beginPath(); ctx.ellipse(p.x, p.y, 2.6, 2, p.s, 0, 7); ctx.fill();
      ctx.globalAlpha = 1;
      if (p.t > 5) pellets.splice(i, 1);
    }
  }
  function spotPath(s, R, cx, cy) {
    // irregular blob from seeded harmonics
    ctx.beginPath();
    for (let a = 0; a <= 24; a++) {
      const th = (a / 24) * Math.PI * 2;
      const rr = R * (0.8 + 0.14 * Math.sin(th * 3 + s.seed) + 0.08 * Math.sin(th * 5 + s.seed * 2));
      const x = cx + Math.cos(th) * rr, y = cy + Math.sin(th) * rr;
      a ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
  }
  function drawDirt() {
    const stage = G.dirtStage();
    if (stage > 0) { ctx.fillStyle = `rgba(95,110,40,${0.035 * stage})`; ctx.fillRect(0, 0, W, H); }
    G.state.dirt.spots.forEach((s) => {
      const R = s.r * W, cx = s.x * W, cy = s.y * H;
      const k = Math.max(0.12, s.grime / s.grime0);
      const a = (0.4 + 0.1 * stage) * k;
      const g = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R);
      g.addColorStop(0, `rgba(86,96,34,${a})`); g.addColorStop(0.7, `rgba(110,118,48,${a * 0.85})`); g.addColorStop(1, `rgba(120,125,60,${a * 0.2})`);
      ctx.fillStyle = g; spotPath(s, R, cx, cy); ctx.fill();
      // speckles
      ctx.fillStyle = `rgba(60,55,20,${a * 0.8})`;
      for (let i = 0; i < 7; i++) {
        const th = s.seed + i * 2.1, rr = R * 0.55 * ((i * 37 % 10) / 10);
        ctx.beginPath(); ctx.arc(cx + Math.cos(th) * rr, cy + Math.sin(th) * rr, 1.5 + (i % 3), 0, 7); ctx.fill();
      }
    });
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
  function floatText(text, x, y, color, big) { floaters.push({ text, x, y, color, big, t: 0 }); }

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
    $('dirt-label').textContent = st === 0 ? 'Dirt: clean' : `Dirt: stage ${st} of ${T.dirt.stageAtPoints.length}`;
    $('buyfood-label').textContent = `+${T.foodPack.food} food · ${T.foodPack.gold}g`;
    $('btn-buyfood').disabled = s.gold < T.foodPack.gold;
    $('tankover').hidden = !G.tankOver();
    // hint line
    let hint = '';
    if (!s.fish.length) hint = 'Open the Shop and buy a baby fish';
    else if (tool === 'food') hint = st >= 1 ? 'Clean the tank first (Sponge)' : 'Tap the tank to feed';
    else if (tool === 'sponge') hint = st >= 1 ? 'Rub the dirty spots' : 'The glass is clean';
    else if (s.fish.some((f) => f.state === 'WAITING')) hint = 'New fish! Pick Food and tap the tank to start growth';
    else hint = 'Tap a fish to see its details';
    $('hint').textContent = hint;
    $('dbg-clock').textContent = `game ${fmt(s.gameTime)} · ×${s.speed}`;
    document.querySelectorAll('#speed-btns .dbg').forEach((b) => b.classList.toggle('on', +b.dataset.speed === s.speed));
  }
  function fmt(sec) {
    sec = Math.max(0, Math.ceil(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    const ss = String(s).padStart(2, '0');
    return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
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
    $('p-name').textContent = sp.name;
    $('p-latin').textContent = sp.latin;
    $('p-rarity').textContent = sp.rarity[0].toUpperCase() + sp.rarity.slice(1);
    $('p-level').textContent = f.level >= T.maxLevel ? `Adult (L${f.level})` : `Level ${f.level} / ${T.maxLevel}`;
    const gEl = $('p-growth'), hEl = $('p-hunger'), bar = $('p-growbar');
    gEl.className = 'v'; hEl.className = 'v';
    bar.classList.toggle('paused', f.state === 'HUNGRY');
    bar.style.width = (i.progressFrac * 100).toFixed(1) + '%';
    if (f.state === 'WAITING') { gEl.textContent = 'Not started - feed to start'; gEl.classList.add('warn'); }
    else if (f.state === 'GROWING') gEl.textContent = `L${f.level + 1} in ${fmt(i.growLeft)}${realNote(i.growLeft)}`;
    else if (f.state === 'HUNGRY') { gEl.textContent = `Paused · L${f.level + 1} in ${fmt(i.growLeft)} once fed`; gEl.classList.add('danger'); }
    else gEl.textContent = `Adult (L${f.level}) · max level`;
    if (f.state === 'WAITING') hEl.textContent = 'Waiting for first feed';
    else if (f.state === 'HUNGRY') { hEl.textContent = 'Hungry! Growth paused'; hEl.classList.add('danger'); }
    else if (f.state === 'ADULT_HUNGRY') { hEl.textContent = 'Hungry!'; hEl.classList.add('danger'); }
    else if (f.state === 'ADULT') { hEl.textContent = `Fed · hungry in ${fmt(i.adultHungerIn)}`; hEl.classList.add('ok'); }
    else { hEl.textContent = 'Fed'; hEl.classList.add('ok'); }
    const dying = f.state === 'HUNGRY' || f.state === 'ADULT_HUNGRY';
    $('p-death-row').hidden = !dying;
    if (dying) $('p-death').textContent = `dies in ${fmt(i.deathLeft)}${realNote(i.deathLeft)}`;
    $('p-portion').textContent = `${i.portion} food`;
    const btn = $('p-sell');
    btn.className = 'btn wide ' + (f.level === 1 ? 'danger' : 'sell');
    btn.textContent = f.level === 1 ? 'Release (0 gold)' : `Sell for ${i.sell} gold`;
    btn.dataset.fish = f.id;
    // portrait
    const pc = $('panel-portrait'), p = pc.getContext('2d');
    p.setTransform(1, 0, 0, 1, 0, 0); p.clearRect(0, 0, pc.width, pc.height);
    p.translate(pc.width * 0.55, pc.height * 0.52);
    FishArt.drawFish(p, f.sp, pc.width * 0.5, realTime * 5, { hungry: dying });
  }
  $('p-sell').addEventListener('click', () => {
    const id = +$('p-sell').dataset.fish;
    const f = G.state.fish.find((x) => x.id === id);
    if (!f) return;
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
          <div class="s">Baby · adult in ${Math.round(total / 60)} min · sells up to ${G.sellPrice(sp, T.maxLevel)}g</div>
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
    const full = G.living() >= T.tankCapacity;
    list.querySelectorAll('button[data-buy]').forEach((b) => {
      const sp = G.SPECIES[b.dataset.buy];
      const poor = G.state.gold < sp.price;
      b.disabled = full || poor;
      b.classList.toggle('poor', poor && !full);
      b.querySelector('.lbl').textContent = full ? ' · Tank full' : '';
    });
    $('shop-note').textContent = `Tank: ${G.living()} / ${T.tankCapacity} fish. Numbers: Designer v1 (config.js ← tuning.json).`;
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
      const r = G.feed();
      if (r.ok || r.reason === 'nobodyhungry' || r.reason === 'nofood') {
        for (let i = 0; i < (r.ok ? 7 : 2); i++) pellets.push({ x: p.x + (Math.random() - 0.5) * 24, y: p.y + (Math.random() - 0.5) * 10, t: 0, s: Math.random() * 3, c: ['#d9772f', '#b8542a', '#e8a13a'][i % 3] });
      }
      if (r.ok) floatText(`-${r.spent} food  +${r.gold}g`, p.x, p.y - 16, '#ffe07a');
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
    if (r.cleaned) floatText(`Sparkling! +${r.gold}g`, x, y - 20, '#9fffd0', true);
  }

  // ------------------------------------------------------------ game events
  G.on((type, d) => {
    const m = d.fish ? anim.get(d.fish.id) : null;
    const fx = m ? m.x : W / 2, fy = m ? m.y - 20 : H / 2;
    const name = d.fish ? G.SPECIES[d.fish.sp].name : '';
    switch (type) {
      case 'levelup':
        floatText(`+${d.gold}g`, fx, fy - 10, '#ffd84a', true);
        toast(d.fish.level >= T.maxLevel ? `${name} is now an adult (L${d.fish.level})! +${d.gold} gold` : `${name} reached level ${d.fish.level}! +${d.gold} gold`, 'good');
        break;
      case 'hungry': toast(`${name} is hungry!`, 'bad'); break;
      case 'death':
        corpses.push({ x: fx, y: fy + 20, sp: d.fish.sp, L: fishLen(d.fish), t: 0 });
        anim.delete(d.fish.id);
        toast(`${name} died of hunger`, 'bad');
        break;
      case 'feedblocked': toast('Clean the tank first', 'bad'); dirtyCallout(); break;
      case 'feedfail':
        toast(d.reason === 'nofish' ? 'No fish to feed. Visit the Shop.' : d.reason === 'nofood' ? 'Not enough food. Buy food.' : "Nobody's hungry", d.reason === 'nofood' ? 'bad' : '');
        break;
      case 'fed': if (d.unfed) toast(`Not enough food: ${d.unfed} fish left unfed`, 'bad'); break;
      case 'cleaned': toast(`Tank clean! +${d.gold} gold`, 'good'); break;
      case 'sold':
        anim.delete(d.fish.id);
        toast(d.gold ? `Sold ${name} for ${d.gold} gold` : `Released ${name} (0 gold)`, d.gold ? 'good' : '');
        break;
      case 'foodbought': toast(`+${d.food} food (−${d.gold} gold)`); break;
      case 'grant': toast(`Starter grant: gold topped up to ${d.gold}`, 'good'); break;
      case 'msg': toast(d.text, 'bad'); break;
      case 'reset': anim.clear(); corpses.length = 0; closePanel(); closeShop(); break;
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
    const keep = G.state.speed; G.reset(); G.state.speed = urlSpeed > 0 ? urlSpeed : keep; G.save();
    $('tankover').hidden = true; closePanel(); toast('New tank started', 'good');
  });
  $('dbg-gold').textContent = '+100g';
  $('dbg-gold').addEventListener('click', () => { G.state.gold += 100; toast('Debug: +100 gold'); });
  $('dbg-reset').addEventListener('click', () => {
    confirmBox('Reset the save and start over?', 'Reset', () => {
      const keep = G.state.speed; G.reset(); G.state.speed = urlSpeed > 0 ? urlSpeed : keep; G.save(); toast('Save reset');
    });
  });

  // ------------------------------------------------------------ main loop
  let last = performance.now();
  let panelAcc = 0;
  function frame(now) {
    let dtReal = (now - last) / 1000; last = now;
    if (dtReal < 0) dtReal = 0;
    // Hidden tab: rAF stops; on return we catch up the real elapsed time (NUMBERS.md §8.9).
    G.tick(dtReal * G.state.speed);
    const dtAnim = Math.min(dtReal, 0.05);
    realTime += dtAnim;

    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    drawWater();
    drawBack();
    drawBubbles(dtAnim);
    decor.plants.forEach((p, i) => { if (i % 2) drawPlant(p, 0.9); });
    drawPellets(dtAnim);
    drawCorpses(dtAnim);
    drawFishAll(dtAnim);
    drawGlass();
    drawDirt();
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

  resize();
  setTool('hand');
  requestAnimationFrame((t) => { last = t; frame(t); });

  // Test/debug hook (read-mostly): used by tests/verify.py
  window.AQ = {
    game: G,
    fishScreen(id) { const m = anim.get(id); return m ? { x: m.x, y: m.y } : null; },
    spotsScreen() { return G.state.dirt.spots.map((s) => ({ x: s.x * W, y: s.y * H, r: s.r * W, grime: s.grime })); },
    size() { return { W, H }; },
    setTool,
  };
})();
