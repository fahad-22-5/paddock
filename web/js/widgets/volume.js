// Master volume + mute and a per-app mixer.
import { h, css, icon, onTap } from '../core/dom.js';
import { Slider } from '../ui/slider.js';

css(`
.w-volume { display: flex; flex-direction: column; gap: 14px; padding: 16px; }
.w-volume .head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.w-volume .dev { font-size: 13px; color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.w-volume .row { display: flex; gap: 10px; align-items: center; }
.w-volume .row .btn { flex: none; width: var(--tap); padding: 0; border-radius: 18px; }
.w-volume .row .btn.on { background: color-mix(in oklab, var(--danger) 70%, black); color: white; }
.w-volume .master .slider { height: 72px; border-radius: 22px; font-size: 18px; }
.w-volume .master .btn { height: 72px; width: 72px; border-radius: 22px; }
.w-volume .apps { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; overscroll-behavior: contain; scrollbar-width: none; }
.w-volume .app-ico { width: 30px; height: 30px; flex: none; display: grid; place-items: center; }
.w-volume .app-ico img { width: 30px; height: 30px; object-fit: contain; }
.w-volume .app-ico svg.i { width: 22px; height: 22px; color: var(--text-2); }
.w-volume .muted-row .slider .fill { background: var(--text-3); }
.w-volume .sep { font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-3); margin-top: 2px; }
@container card (height < 240px) { .w-volume .apps, .w-volume .sep { display: none; } .w-volume .master .slider, .w-volume .master .btn { height: 60px; } }
`);

const iconCache = new Map();
function appIcon(token, key) {
  if (!iconCache.has(key)) {
    iconCache.set(key, fetch(`/api/volume/icon/${encodeURIComponent(key)}`, { headers: { authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : null)).then((b) => (b ? URL.createObjectURL(b) : null)).catch(() => null));
  }
  return iconCache.get(key);
}

export default {
  type: 'volume',
  title: 'Volume mixer',
  description: 'Master volume, mute and per-app levels',
  icon: 'volume',
  sizes: [[3, 4], [3, 2], [2, 2], [3, 3], [4, 3], [4, 4], [2, 4]],
  mount(card, ctx) {
    const dev = h('span', { class: 'dev' });
    const master = new Slider({ label: 'Volume', onInput: (v) => ctx.call('volume', 'set_master', { level: v }).catch(ctx.toastError) });
    const muteBtn = h('button', { class: 'btn', 'aria-label': 'Mute' }, icon('volume'));
    const apps = h('div', { class: 'apps' });
    card.append(
      h('div', { class: 'head' }, h('div', { class: 'card-title' }, icon('volume'), 'Volume'), dev),
      h('div', { class: 'row master' }, master.el, muteBtn),
      h('div', { class: 'sep' }, 'Apps'), apps);

    let muted = false;
    onTap(muteBtn, () => {
      muted = !muted;
      paintMute();
      ctx.call('volume', 'set_mute', { muted }).catch(ctx.toastError);
    });
    const paintMute = () => {
      muteBtn.classList.toggle('on', muted);
      muteBtn.replaceChildren(icon(muted ? 'mute' : master.value < 0.35 ? 'volume-low' : 'volume'));
      muteBtn.setAttribute('aria-label', muted ? 'Unmute' : 'Mute');
    };

    const rows = new Map(); // key -> {el, slider, btn, muted}
    const makeRow = (a) => {
      const ico = h('span', { class: 'app-ico' }, icon(a.key === 'system' ? 'settings' : 'app'));
      if (a.icon) appIcon(ctx.conn.token, a.key).then((u) => u && ico.replaceChildren(h('img', { src: u, alt: '' })));
      const r = { muted: a.muted };
      r.slider = new Slider({ label: a.name, onInput: (v) => ctx.call('volume', 'set_app', { key: a.key, level: v }).catch(ctx.toastError) });
      r.btn = h('button', { class: 'btn', 'aria-label': `Mute ${a.name}` });
      onTap(r.btn, () => {
        r.muted = !r.muted;
        paintRow(r);
        ctx.call('volume', 'set_app_mute', { key: a.key, muted: r.muted }).catch(ctx.toastError);
      });
      r.el = h('div', { class: 'row' }, ico, r.slider.el, r.btn);
      return r;
    };
    const paintRow = (r) => {
      r.btn.classList.toggle('on', r.muted);
      r.btn.replaceChildren(icon(r.muted ? 'mute' : 'volume'));
      r.el.classList.toggle('muted-row', r.muted);
    };

    ctx.subscribe('volume', (s) => {
      dev.textContent = s.device || '';
      master.set(s.level);
      if (!master.dragging) { muted = s.muted; paintMute(); }
      const seen = new Set();
      const nodes = s.apps.map((a) => {
        seen.add(a.key);
        let r = rows.get(a.key);
        if (!r) { r = makeRow(a); rows.set(a.key, r); }
        r.slider.set(a.level);
        r.slider.setLabel(a.name);
        if (!r.slider.dragging) { r.muted = a.muted; paintRow(r); }
        return r.el;
      });
      for (const k of rows.keys()) if (!seen.has(k)) rows.delete(k);
      if (nodes.length !== apps.children.length || nodes.some((n, i) => apps.children[i] !== n)) apps.replaceChildren(...nodes);
      if (!nodes.length) apps.replaceChildren(h('div', { class: 'empty-note' }, 'No apps are playing sound.'));
    });
  },
};
