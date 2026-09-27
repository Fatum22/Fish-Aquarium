/* Procedural "realistic-cartoon" fish drawing on canvas. No image assets.
 * drawFish(ctx, speciesId, len, phase, opts) draws a fish facing +x, centred on (0,0).
 */
(function () {
  'use strict';

  const ART = {
    neon: {
      depth: 0.27, tail: 'fork', tailLen: 0.30, tailSpread: 0.95,
      top: '#34455f', mid: '#6d7f95', belly: '#e3ebf0',
      fin: 'rgba(235,245,255,0.45)', finEdge: 'rgba(255,255,255,0.7)', tailFill: 'rgba(230,240,255,0.42)',
      dorsal: 'small', eyeRing: '#9ee8ff',
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
      dorsal: 'small', eyeRing: '#e8e0b8',
    },
    platy: {
      depth: 0.42, tail: 'round', tailLen: 0.30, tailSpread: 1.05,
      top: '#d8391a', mid: '#ff6a2b', belly: '#ffc07a',
      fin: 'rgba(255,120,60,0.85)', finEdge: 'rgba(120,20,10,0.55)', tailFill: null,
      dorsal: 'round', eyeRing: '#ffd9a0',
    },
  };

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

  function drawTail(ctx, id, a, L, hh, sway) {
    ctx.save();
    ctx.translate(-0.31 * L, 0);
    ctx.rotate(sway);
    ctx.translate(0.31 * L, 0);
    tailPath(ctx, a, L, hh);
    const tl = a.tailLen * L, x0 = -0.31 * L;
    if (id === 'guppy') {
      const g = ctx.createLinearGradient(x0, 0, x0 - tl, 0);
      g.addColorStop(0, '#ffb13b'); g.addColorStop(0.45, '#ff5a3c'); g.addColorStop(1, '#7b3cff');
      ctx.fillStyle = g;
    } else if (id === 'platy') {
      const g = ctx.createLinearGradient(x0, 0, x0 - tl, 0);
      g.addColorStop(0, '#ff5a22'); g.addColorStop(1, '#c42a12');
      ctx.fillStyle = g;
    } else {
      ctx.fillStyle = a.tailFill;
    }
    ctx.fill();
    // fin rays / pattern
    ctx.save();
    tailPath(ctx, a, L, hh); ctx.clip();
    ctx.strokeStyle = id === 'guppy' ? 'rgba(40,10,80,0.25)' : 'rgba(255,255,255,0.35)';
    ctx.lineWidth = Math.max(0.5, L * 0.006);
    for (let i = -4; i <= 4; i++) {
      ctx.beginPath(); ctx.moveTo(x0, 0); ctx.lineTo(x0 - tl * 1.2, i * a.tailSpread * hh * 0.3); ctx.stroke();
    }
    if (id === 'guppy') { // spots on fan tail
      const spots = [[0.45, -0.3, '#2bd1ff'], [0.7, 0.25, '#1f3cff'], [0.6, -0.05, '#111'], [0.8, -0.35, '#ffd23b'], [0.35, 0.3, '#2bd1ff']];
      for (const [fx, fy, c] of spots) {
        ctx.fillStyle = c; ctx.globalAlpha = 0.8;
        ctx.beginPath(); ctx.arc(x0 - tl * fx, fy * a.tailSpread * hh, hh * 0.18, 0, 7); ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
    if (id === 'danio') { // stripes continue onto tail
      ctx.strokeStyle = 'rgba(30,60,150,0.8)'; ctx.lineWidth = hh * 0.14;
      for (const s of [-0.28, 0.02, 0.32]) {
        ctx.beginPath(); ctx.moveTo(x0, s * hh * 0.6); ctx.lineTo(x0 - tl * 0.7, s * hh * 1.2); ctx.stroke();
      }
    }
    if (id === 'platy') {
      ctx.strokeStyle = 'rgba(90,10,0,0.45)'; ctx.lineWidth = hh * 0.12;
      tailPath(ctx, a, L, hh); ctx.stroke();
    }
    ctx.restore();
    ctx.restore();
  }

  function drawDorsal(ctx, id, a, L, hh, wave) {
    ctx.beginPath();
    const w = Math.sin(wave) * hh * 0.06;
    if (a.dorsal === 'flag') { // guppy: long flowing dorsal
      ctx.moveTo(0.02 * L, -hh * 0.9);
      ctx.quadraticCurveTo(-0.12 * L, -hh * 1.9 + w, -0.34 * L, -hh * 1.35 + w);
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
    if (id === 'guppy') {
      const g = ctx.createLinearGradient(0, -hh, -0.3 * L, -hh * 1.6);
      g.addColorStop(0, '#5fd0ff'); g.addColorStop(1, '#ff8a3b');
      ctx.fillStyle = g;
    } else ctx.fillStyle = a.fin;
    ctx.fill();
    ctx.strokeStyle = a.finEdge; ctx.lineWidth = Math.max(0.5, L * 0.008); ctx.stroke();
  }

  function drawBellyFins(ctx, id, a, L, hh, wave) {
    const w = Math.sin(wave + 1) * hh * 0.08;
    ctx.fillStyle = id === 'guppy' ? 'rgba(255,160,90,0.7)' : a.fin;
    ctx.strokeStyle = a.finEdge; ctx.lineWidth = Math.max(0.5, L * 0.006);
    // anal fin
    ctx.beginPath();
    ctx.moveTo(-0.06 * L, hh * 0.78);
    ctx.quadraticCurveTo(-0.14 * L, hh * 1.45 + w, -0.24 * L, hh * 1.2 + w);
    ctx.quadraticCurveTo(-0.22 * L, hh * 0.8, -0.2 * L, hh * 0.55);
    ctx.closePath(); ctx.fill(); ctx.stroke();
    // pelvic fin
    ctx.beginPath();
    ctx.moveTo(0.14 * L, hh * 0.9);
    ctx.quadraticCurveTo(0.08 * L, hh * 1.4 - w, 0.02 * L, hh * 1.3 - w);
    ctx.quadraticCurveTo(0.04 * L, hh * 1.0, 0.04 * L, hh * 0.85);
    ctx.closePath(); ctx.fill();
  }

  function drawPattern(ctx, id, a, L, hh) {
    if (id === 'neon') {
      // red lower rear
      const r = ctx.createLinearGradient(0.05 * L, 0, -0.3 * L, 0);
      r.addColorStop(0, 'rgba(232,35,58,0)'); r.addColorStop(0.18, 'rgba(232,35,58,0.95)'); r.addColorStop(1, '#d81f36');
      ctx.fillStyle = r; ctx.fillRect(-0.4 * L, hh * 0.02, 0.5 * L, hh * 1.2);
      // iridescent blue stripe
      const g = ctx.createLinearGradient(0.35 * L, 0, -0.32 * L, 0);
      g.addColorStop(0, '#5ff6ff'); g.addColorStop(0.5, '#2aa8ff'); g.addColorStop(1, '#2a6bff');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(0.36 * L, -hh * 0.22);
      ctx.quadraticCurveTo(0.0, -hh * 0.42, -0.34 * L, -hh * 0.18);
      ctx.lineTo(-0.34 * L, hh * 0.02);
      ctx.quadraticCurveTo(0.0, -hh * 0.08, 0.36 * L, -hh * 0.02);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.35)';
      ctx.fillRect(-0.3 * L, -hh * 0.3, 0.6 * L, hh * 0.05);
    } else if (id === 'danio') {
      ctx.strokeStyle = '#1f3f96'; ctx.lineCap = 'round';
      const ys = [-0.5, -0.18, 0.14, 0.44];
      ys.forEach((y, i) => {
        ctx.lineWidth = hh * (i === 1 || i === 2 ? 0.17 : 0.12);
        ctx.beginPath();
        ctx.moveTo(0.3 * L, y * hh * 0.7);
        ctx.quadraticCurveTo(0.0, y * hh * 1.05, -0.36 * L, y * hh * 0.45);
        ctx.stroke();
      });
      ctx.strokeStyle = 'rgba(255,240,170,0.6)'; ctx.lineWidth = hh * 0.06;
      [-0.34, -0.02, 0.29].forEach((y) => {
        ctx.beginPath(); ctx.moveTo(0.28 * L, y * hh * 0.7);
        ctx.quadraticCurveTo(0.0, y * hh * 1.05, -0.36 * L, y * hh * 0.45); ctx.stroke();
      });
    } else if (id === 'guppy') {
      const spots = [[-0.12, -0.1, '#ff7a1a', 0.2], [-0.22, 0.18, '#2b8cff', 0.16], [-0.02, 0.25, '#111a', 0.12], [-0.25, -0.2, '#ffd23b', 0.12]];
      for (const [x, y, c, r] of spots) {
        ctx.fillStyle = c; ctx.beginPath(); ctx.ellipse(x * L, y * hh, r * hh * 1.3, r * hh, 0, 0, 7); ctx.fill();
      }
      const sheen = ctx.createLinearGradient(0, -hh, 0, hh);
      sheen.addColorStop(0.3, 'rgba(120,220,255,0)'); sheen.addColorStop(0.55, 'rgba(120,220,255,0.35)'); sheen.addColorStop(0.8, 'rgba(120,220,255,0)');
      ctx.fillStyle = sheen; ctx.fillRect(-0.4 * L, -hh, 0.5 * L, hh * 2);
    } else if (id === 'platy') {
      ctx.fillStyle = 'rgba(255,230,150,0.25)';
      for (let i = 0; i < 5; i++) {
        ctx.beginPath(); ctx.arc((0.2 - i * 0.1) * L, -hh * 0.1, hh * 0.18, 0, 7); ctx.fill();
      }
    }
  }

  /**
   * @param ctx canvas 2d context
   * @param id species id
   * @param L body length in px (tail extends beyond)
   * @param phase animation phase (radians) for tail/fins
   * @param opts {dead, hungry}
   */
  function drawFish(ctx, id, L, phase, opts) {
    const a = ART[id] || ART.neon;
    opts = opts || {};
    const hh = (a.depth * L) / 2;
    const sway = opts.dead ? 0 : Math.sin(phase) * (opts.hungry ? 0.14 : 0.28);
    ctx.save();
    if (opts.dead) { ctx.scale(1, -1); ctx.globalAlpha *= 0.85; try { ctx.filter = 'grayscale(0.9) brightness(1.1)'; } catch (e) {} }

    drawTail(ctx, id, a, L, hh, sway);
    drawDorsal(ctx, id, a, L, hh, phase * 0.7);
    drawBellyFins(ctx, id, a, L, hh, phase);

    // body
    bodyPath(ctx, L, hh);
    const g = ctx.createLinearGradient(0, -hh, 0, hh);
    g.addColorStop(0, a.top); g.addColorStop(0.45, a.mid); g.addColorStop(1, a.belly);
    ctx.fillStyle = g; ctx.fill();
    ctx.save();
    bodyPath(ctx, L, hh); ctx.clip();
    drawPattern(ctx, id, a, L, hh);
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
    ctx.rotate(0.5 + (opts.dead ? 0 : Math.sin(phase * 1.6) * 0.35));
    ctx.beginPath(); ctx.ellipse(-hh * 0.4, 0, hh * 0.45, hh * 0.18, 0, 0, 7);
    ctx.fillStyle = id === 'platy' ? 'rgba(255,150,80,0.8)' : 'rgba(255,255,255,0.4)'; ctx.fill();
    ctx.restore();

    // eye
    const ex = 0.33 * L, ey = -hh * 0.18, er = Math.max(1.6, hh * 0.3);
    ctx.fillStyle = a.eyeRing; ctx.beginPath(); ctx.arc(ex, ey, er, 0, 7); ctx.fill();
    if (opts.dead) {
      ctx.strokeStyle = '#222'; ctx.lineWidth = Math.max(1, er * 0.35);
      ctx.beginPath(); ctx.moveTo(ex - er * 0.6, ey - er * 0.6); ctx.lineTo(ex + er * 0.6, ey + er * 0.6);
      ctx.moveTo(ex + er * 0.6, ey - er * 0.6); ctx.lineTo(ex - er * 0.6, ey + er * 0.6); ctx.stroke();
    } else {
      ctx.fillStyle = '#0d0f14'; ctx.beginPath(); ctx.arc(ex + er * 0.12, ey, er * 0.66, 0, 7); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(ex + er * 0.35, ey - er * 0.3, er * 0.25, 0, 7); ctx.fill();
    }
    // mouth
    ctx.strokeStyle = 'rgba(60,20,20,0.5)'; ctx.lineWidth = Math.max(0.6, L * 0.008);
    ctx.beginPath(); ctx.moveTo(0.48 * L, hh * 0.12); ctx.lineTo(0.43 * L, hh * 0.16); ctx.stroke();

    ctx.restore();
  }

  window.FishArt = { drawFish, ART };
})();
