// Touchpad: use the device as a trackpad and scroll surface for the PC mouse.
//   one finger: move · tap: click · double-tap and drag: drag
//   two-finger tap: right-click · two fingers: scroll (with momentum)
import { h, css, icon, onTap, storage } from '../core/dom.js';
import { Slider } from '../ui/slider.js';

css(`
.w-touchpad { display: flex; flex-direction: column; gap: 10px; padding: 12px; }
.w-touchpad .pad { flex: 1; min-height: 0; border-radius: 20px; touch-action: none; position: relative;
  background: radial-gradient(circle at 50% 40%, rgb(255 255 255 / .05), rgb(0 0 0 / .18)); border: 1px solid var(--border);
  display: grid; place-items: center; color: var(--text-3); font-size: 14px; text-align: center; overflow: hidden; }
.w-touchpad .pad .hint { max-width: 420px; padding: 20px; line-height: 1.6; pointer-events: none; transition: opacity 300ms; }
.w-touchpad .pad.used .hint { opacity: 0; }
.w-touchpad .pad .dot { position: absolute; width: 56px; height: 56px; margin: -28px 0 0 -28px; border-radius: 50%;
  background: color-mix(in oklab, var(--accent) 35%, transparent); pointer-events: none; transition: opacity 200ms; }
.w-touchpad .pad.dragging { outline: 2px solid var(--accent); outline-offset: -2px; }
.w-touchpad .bar { display: flex; gap: 10px; align-items: center; }
.w-touchpad .mb { flex: 1; min-height: 64px; border-radius: 18px; border: 0; background: rgb(255 255 255 / .07); font-weight: 600; touch-action: none; }
.w-touchpad .mb.down { background: var(--accent); color: white; }
.w-touchpad .speed { flex: 1.2; }
.w-touchpad .kb { display: none; gap: 8px; align-items: center; flex-wrap: wrap; }
.w-touchpad.typing .kb { display: flex; }
.w-touchpad .kb input { flex: 1; min-width: 160px; }
.w-touchpad .kb .btn { padding: 0 14px; }
.w-touchpad .tools .btn[aria-pressed="true"] { background: var(--accent); color: white; }
@container card (width < 520px) { .w-touchpad .speed { display: none; } }
`);

const TAP_MS = 220, TAP_SLOP = 10, DOUBLE_MS = 300;

export default {
  type: 'touchpad',
  title: 'Touchpad',
  description: 'Use this device as a trackpad for the PC',
  icon: 'mouse',
  sizes: [[8, 4], [6, 4], [4, 3], [4, 4], [8, 3]],
  mount(card, ctx) {
    const pad = h('div', { class: 'pad', 'aria-label': 'Touchpad surface' },
      h('div', { class: 'hint' }, 'Move with one finger · tap to click · tap with two fingers to right-click · scroll with two fingers · double-tap and drag to drag'));
    const left = h('button', { class: 'mb' }, 'Left');
    const right = h('button', { class: 'mb' }, 'Right');
    let speed = storage.get('paddock.padSpeed', 0.5);
    const speedSlider = new Slider({ label: 'Speed', value: speed, format: (v) => `${(0.5 + v * 3).toFixed(1)}×`,
      onChange: (v) => { speed = v; storage.set('paddock.padSpeed', v); } });
    speedSlider.el.classList.add('speed');
    const kbBtn = h('button', { class: 'btn icon', 'aria-label': 'Keyboard', 'aria-pressed': 'false' }, icon('keyboard'));
    const input = h('input', { class: 'field', placeholder: 'Type here to type on the PC', autocomplete: 'off', autocapitalize: 'off', autocorrect: 'off', spellcheck: false });
    const keyBtn = (label, key) => { const b = h('button', { class: 'btn' }, label); onTap(b, () => ctx.call('macros', 'key', { key }).catch(ctx.toastError)); return b; };
    card.append(pad,
      h('div', { class: 'kb' }, input, keyBtn('⌫', 'backspace'), keyBtn('⏎', 'enter'), keyBtn('Tab', 'tab'), keyBtn('Esc', 'esc'),
        keyBtn('←', 'left'), keyBtn('→', 'right'), keyBtn('↑', 'up'), keyBtn('↓', 'down')),
      h('div', { class: 'bar tools' }, left, right, speedSlider.el, kbBtn));

    onTap(kbBtn, () => {
      const on = !card.classList.contains('typing');
      card.classList.toggle('typing', on);
      kbBtn.setAttribute('aria-pressed', String(on));
      if (on) input.focus();
    });
    // Send what's typed straight away and keep the field empty.
    input.addEventListener('beforeinput', (e) => {
      e.preventDefault();
      if (e.inputType === 'insertText' || e.inputType === 'insertReplacementText' || e.inputType === 'insertFromPaste') {
        const text = e.data ?? e.dataTransfer?.getData('text/plain');
        if (text) ctx.call('macros', 'type', { text }).catch(ctx.toastError);
      }
    });
    // Special keys (on-screen and hardware keyboards both send keydown for these).
    input.addEventListener('keydown', (e) => {
      const map = { Enter: 'enter', Backspace: 'backspace', Tab: 'tab', Escape: 'esc', ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
      if (map[e.key] && !e.isComposing) { e.preventDefault(); ctx.call('macros', 'key', { key: map[e.key] }).catch(() => {}); }
    });

    // Hold-able mouse buttons.
    for (const [btn, name] of [[left, 'left'], [right, 'right']]) {
      btn.addEventListener('pointerdown', (e) => { e.preventDefault(); btn.setPointerCapture(e.pointerId); btn.classList.add('down'); ctx.fire('touchpad', 'down', { button: name }); });
      const up = () => { if (!btn.classList.contains('down')) return; btn.classList.remove('down'); ctx.fire('touchpad', 'up', { button: name }); };
      btn.addEventListener('pointerup', up);
      btn.addEventListener('pointercancel', up);
    }

    // ---- gestures ----
    const pts = new Map(); // pointerId -> {x, y, sx, sy, t}
    let mode = 'idle'; // idle | move | scroll | drag
    let maxPts = 0, gestureStart = 0, moved = false;
    let lastTapAt = 0;
    let accX = 0, accY = 0, scrX = 0, scrY = 0, raf = 0;
    let vel = { x: 0, y: 0, t: 0 }, momentum = 0;

    const flush = () => {
      raf = 0;
      const mx = Math.trunc(accX), my = Math.trunc(accY);
      if (mx || my) { ctx.fire('touchpad', 'move', { dx: mx, dy: my }); accX -= mx; accY -= my; }
      const sy = Math.trunc(scrY), sx = Math.trunc(scrX);
      if (sx || sy) { ctx.fire('touchpad', 'scroll', { dx: sx, dy: sy }); scrX -= sx; scrY -= sy; }
    };
    const queue = () => { if (!raf) raf = requestAnimationFrame(flush); };
    const gain = () => 0.5 + speed * 3;

    pad.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      pad.setPointerCapture(e.pointerId);
      pad.classList.add('used');
      cancelAnimationFrame(momentum); momentum = 0;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY });
      if (pts.size === 1) {
        gestureStart = performance.now();
        moved = false;
        maxPts = 1;
        // Second touch soon after a tap: may become a drag.
        mode = gestureStart - lastTapAt < DOUBLE_MS ? 'maybe-drag' : 'move';
      } else {
        maxPts = Math.max(maxPts, pts.size);
        if (mode === 'drag') { ctx.fire('touchpad', 'up', { button: 'left' }); pad.classList.remove('dragging'); }
        mode = 'scroll';
        vel = { x: 0, y: 0, t: performance.now() };
      }
    });

    pad.addEventListener('pointermove', (e) => {
      const p = pts.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      p.x = e.clientX; p.y = e.clientY;
      if (Math.hypot(p.x - p.sx, p.y - p.sy) > TAP_SLOP) moved = true;
      if (mode === 'maybe-drag' && moved) {
        mode = 'drag';
        pad.classList.add('dragging');
        ctx.fire('touchpad', 'down', { button: 'left' });
      }
      if (mode === 'move' || mode === 'drag') {
        const g = gain() * Math.min(2.2, 1 + Math.hypot(dx, dy) / 25); // light acceleration
        accX += dx * g; accY += dy * g;
        queue();
      } else if (mode === 'scroll') {
        // Use the average of the fingers: each finger contributes 1/n.
        const n = pts.size;
        const sdy = (dy / n) * 4, sdx = (-dx / n) * 4; // natural scrolling, like a touchscreen
        scrY += sdy; scrX += sdx;
        const now = performance.now(), dt = Math.max(1, now - vel.t);
        vel = { x: vel.x * 0.6 + (sdx / dt) * 0.4 * 16, y: vel.y * 0.6 + (sdy / dt) * 0.4 * 16, t: now };
        queue();
      }
    });

    const end = (e) => {
      if (!pts.has(e.pointerId)) return;
      pts.delete(e.pointerId);
      if (pts.size) return; // wait for all fingers to lift
      const dur = performance.now() - gestureStart;
      const isTap = !moved && dur < TAP_MS * (maxPts > 1 ? 1.5 : 1);
      if (mode === 'drag') {
        ctx.fire('touchpad', 'up', { button: 'left' });
        pad.classList.remove('dragging');
      } else if (isTap && maxPts >= 2) {
        ctx.fire('touchpad', 'click', { button: 'right' });
      } else if (isTap) {
        ctx.fire('touchpad', 'click', { button: 'left' });
        lastTapAt = performance.now();
      } else if (mode === 'scroll' && performance.now() - vel.t < 80 && Math.hypot(vel.x, vel.y) > 2) {
        // Momentum: keep scrolling and slow down, like iOS.
        let vx = vel.x, vy = vel.y;
        const step = () => {
          vx *= 0.94; vy *= 0.94;
          scrX += vx; scrY += vy;
          flush();
          momentum = Math.hypot(vx, vy) > 0.5 ? requestAnimationFrame(step) : 0;
        };
        momentum = requestAnimationFrame(step);
      }
      if (!isTap || maxPts > 1) lastTapAt = 0;
      mode = 'idle';
    };
    pad.addEventListener('pointerup', end);
    pad.addEventListener('pointercancel', end);

    return { destroy() { cancelAnimationFrame(raf); cancelAnimationFrame(momentum); } };
  },
};
