// Touch slider: tap anywhere to jump, drag to adjust. Native range inputs on iPhone/iPad
// only respond when you grab the thumb, which is fiddly on a dock.
import { h, clamp } from '../core/dom.js';

export class Slider {
  constructor({ value = 0, label = '', format = (v) => `${Math.round(v * 100)}%`, onInput, onChange,
    thin = false, throttle = 50, ariaLabel = '' } = {}) {
    this.value = value;
    this.format = format;
    this.onInput = onInput;
    this.onChange = onChange;
    this.dragging = false;
    this.labelText = h('span', null, label);
    this.valueText = h('span', null, '');
    this.el = h('div', {
      class: `slider${thin ? ' thin' : ''}`, role: 'slider', tabindex: 0,
      'aria-label': ariaLabel || label, 'aria-valuemin': 0, 'aria-valuemax': 100,
    }, h('div', { class: 'fill' }), !thin && h('div', { class: 'slider-label' }, this.labelText, this.valueText));
    this._lastSent = 0;
    this._timer = null;
    this._bind();
    this._render();
  }

  _bind() {
    const el = this.el;
    const fromEvent = (e) => {
      const r = el.getBoundingClientRect();
      return clamp((e.clientX - r.left) / r.width, 0, 1);
    };
    el.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      el.setPointerCapture(e.pointerId);
      this.dragging = true;
      el.classList.add('dragging');
      this._update(fromEvent(e));
    });
    el.addEventListener('pointermove', (e) => { if (this.dragging) this._update(fromEvent(e)); });
    const end = (e) => {
      if (!this.dragging) return;
      this.dragging = false;
      el.classList.remove('dragging');
      clearTimeout(this._timer);
      this.onInput?.(this.value);
      this.onChange?.(this.value);
      this._holdUntil = Date.now() + 800; // ignore stale server echoes for a moment
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    el.addEventListener('keydown', (e) => {
      const step = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 0.05 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -0.05 : 0;
      if (!step) return;
      e.preventDefault();
      this._update(clamp(this.value + step, 0, 1));
      this.onChange?.(this.value);
    });
  }

  _update(v) {
    this.value = v;
    this._render();
    const now = Date.now();
    clearTimeout(this._timer);
    if (now - this._lastSent >= this.throttleMs) {
      this._lastSent = now;
      this.onInput?.(v);
    } else {
      this._timer = setTimeout(() => { this._lastSent = Date.now(); this.onInput?.(this.value); }, this.throttleMs);
    }
  }

  get throttleMs() { return 50; }

  _render() {
    this.el.style.setProperty('--v', this.value);
    this.el.setAttribute('aria-valuenow', Math.round(this.value * 100));
    this.valueText.textContent = this.format(this.value);
  }

  /** Update from the server unless the user is touching it. */
  set(v) {
    if (this.dragging || Date.now() < (this._holdUntil || 0)) return;
    this.value = clamp(v, 0, 1);
    this._render();
  }

  setLabel(text) { this.labelText.textContent = text; }
  setDisabled(d) { this.el.classList.toggle('disabled', d); }
}
