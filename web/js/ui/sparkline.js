// Canvas sparkline that scrolls smoothly at display refresh rate between samples.
// New points arrive every ~1 s; the line glides left continuously instead of jumping.

const live = new Set();
let rafId = 0;
function loop(now) {
  rafId = 0;
  for (const s of live) s._draw(now);
  if (live.size && !document.hidden) rafId = requestAnimationFrame(loop);
}
function kick() { if (!rafId && live.size && !document.hidden) rafId = requestAnimationFrame(loop); }
document.addEventListener('visibilitychange', kick);

let accent = null;
export function refreshSparklineColors() { accent = null; }

export class Sparkline {
  /** max: fixed upper bound (e.g. 100) or null to auto-scale. */
  constructor({ points = 60, max = 100, color = null, interval = 1000 } = {}) {
    this.n = points;
    this.max = max;
    this.color = color;
    this.interval = interval;
    this.values = [];
    this.lastAt = 0;
    this.scale = max || 1;
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'spark';
    this.ctx = this.canvas.getContext('2d');
    this.visible = false;
    this._ro = new ResizeObserver(() => this._resize());
    this._ro.observe(this.canvas);
    this._io = new IntersectionObserver(([e]) => {
      this.visible = e.isIntersecting;
      this.visible ? live.add(this) : live.delete(this);
      kick();
    });
    this._io.observe(this.canvas);
  }

  push(v) {
    const now = performance.now();
    if (this.lastAt) this.interval = this.interval * 0.8 + Math.min(4000, now - this.lastAt) * 0.2;
    this.lastAt = now;
    this.values.push(v ?? 0);
    if (this.values.length > this.n + 2) this.values.shift();
    if (!this.visible) return;
    kick();
  }

  _resize() {
    const r = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = r.width; this.h = r.height;
    this.canvas.width = Math.max(1, Math.round(r.width * dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._draw(performance.now());
  }

  _draw(now) {
    const { ctx, w, h, values } = this;
    if (!w || !h) return;
    ctx.clearRect(0, 0, w, h);
    if (values.length < 2) return;
    if (!accent) accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#0a84ff';
    const color = this.color || accent;

    // Auto-scale smoothly for unbounded series (network speed).
    if (!this.max) {
      const target = Math.max(1, ...values) * 1.15;
      this.scale += (target - this.scale) * 0.08;
    }
    const step = w / (this.n - 1);
    const t = Math.min(1, (now - this.lastAt) / this.interval);
    const pad = 2;
    const y = (v) => h - pad - (Math.min(v, this.scale) / this.scale) * (h - pad * 2);
    const last = values.length - 1;
    const x = (i) => w + (1 - t) * step - (last - i) * step;

    ctx.beginPath();
    let started = false;
    for (let i = 0; i <= last; i++) {
      const xi = x(i);
      if (xi < -step) continue;
      if (!started) { ctx.moveTo(xi, y(values[i])); started = true; continue; }
      // Smooth curve through midpoints.
      const xp = x(i - 1), yp = y(values[i - 1]);
      const xm = (xp + xi) / 2, ym = (yp + y(values[i])) / 2;
      ctx.quadraticCurveTo(xp, yp, xm, ym);
    }
    ctx.lineTo(x(last), y(values[last]));
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.strokeStyle = color;
    ctx.stroke();

    ctx.lineTo(x(last), h);
    ctx.lineTo(Math.max(x(0), -step), h);
    ctx.closePath();
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, hexA(color, 0.35));
    g.addColorStop(1, hexA(color, 0));
    ctx.fillStyle = g;
    ctx.fill();
  }

  destroy() {
    live.delete(this);
    this._ro.disconnect();
    this._io.disconnect();
  }
}

function hexA(color, a) {
  const m = /^#?([0-9a-f]{6})$/i.exec(color);
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}
