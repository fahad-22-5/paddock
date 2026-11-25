// Settings sheet: accent colour, keep-awake, weather location, paired devices.
import { h, icon, onTap } from '../core/dom.js';
import { confirmDialog, sheet, toast, toastError } from '../core/ui.js';
import { setKeepAwake, wakeLockActive, wakeLockSupported, wakeLockWanted, onWakeLockChange } from '../core/wakelock.js';
import { setToken, startRepair } from './pairing.js';

const SWATCHES = ['#0a84ff', '#5e5ce6', '#bf5af2', '#ff375f', '#ff9f0a', '#ffd60a', '#30d158', '#64d2ff', '#ac8e68', '#8e8e93'];

export function openSettings(shell) {
  const { conn } = shell;
  const cleanups = [];
  sheet('Settings', (body, close) => {
    // --- accent
    const current = () => (shell.config.appearance?.accent || '#0a84ff').toLowerCase();
    const sw = h('div', { class: 'swatches' });
    const setAccent = async (c) => {
      document.documentElement.style.setProperty('--accent', c);
      shell.config.appearance = { ...shell.config.appearance, accent: c };
      shell.applyAppearance();
      drawSwatches();
      try { await conn.call('core', 'set_appearance', { accent: c }); } catch (e) { toastError(e); }
    };
    const custom = h('input', { type: 'color', value: current(), 'aria-label': 'Custom colour' });
    custom.addEventListener('change', () => setAccent(custom.value));
    const drawSwatches = () => {
      sw.replaceChildren(...SWATCHES.map((c) => {
        const b = h('button', { class: 'swatch', style: { '--c': c }, 'aria-label': c, 'aria-pressed': String(current() === c) });
        b.style.setProperty('--c', c);
        onTap(b, () => setAccent(c));
        return b;
      }), h('label', { class: 'swatch swatch-custom', 'aria-pressed': String(!SWATCHES.includes(current())), title: 'Custom' }, custom));
    };
    drawSwatches();
    body.append(h('div', { class: 'section-label' }, 'Accent colour'), sw);

    // --- display
    const awake = h('input', { type: 'checkbox', class: 'switch', checked: wakeLockWanted() });
    const awakeNote = h('small');
    const drawAwake = () => {
      awakeNote.textContent = !wakeLockSupported()
        ? 'Not available: open PadDock over https:// (see the setup page on the PC).'
        : wakeLockActive() ? 'Screen stays on while PadDock is open.' : wakeLockWanted() ? 'Waiting for the app to be in front…' : 'Off';
    };
    drawAwake();
    cleanups.push(onWakeLockChange(drawAwake));
    awake.addEventListener('change', () => setKeepAwake(awake.checked));
    body.append(h('div', { class: 'section-label' }, 'Display'),
      h('div', { class: 'list' }, h('label', { class: 'list-row' }, icon('sun'), h('div', { class: 'grow' }, 'Keep screen on', awakeNote), awake)));

    // --- weather
    const w = shell.config.weather || {};
    const place = h('input', { class: 'field', placeholder: 'City, e.g. Berlin', value: w.name || '', enterkeyhint: 'search' });
    const placeBtn = h('button', { class: 'btn primary' }, 'Set');
    const units = h('div', { class: 'chips' });
    const drawUnits = (u) => units.replaceChildren(...[['celsius', '°C'], ['fahrenheit', '°F']].map(([k, l]) => {
      const c = h('button', { class: 'chip', 'aria-pressed': String(u === k) }, l);
      onTap(c, async () => { drawUnits(k); try { await conn.call('weather', 'set_units', { units: k }); } catch (e) { toastError(e); } });
      return c;
    }));
    drawUnits(w.units || 'celsius');
    const setPlace = async () => {
      if (!place.value.trim()) return;
      placeBtn.disabled = true;
      try {
        const r = await conn.call('weather', 'set_location', { query: place.value.trim() });
        place.value = r.name;
        toast(`Weather location: ${r.name}`);
      } catch (e) { toastError(e); }
      placeBtn.disabled = false;
    };
    onTap(placeBtn, setPlace);
    place.addEventListener('keydown', (e) => { if (e.key === 'Enter') setPlace(); });
    body.append(h('div', { class: 'section-label' }, 'Weather (Open-Meteo)'),
      h('div', { style: { display: 'flex', gap: '10px' } }, place, placeBtn), units);

    // --- devices
    const devList = h('div', { class: 'list' }, h('div', { class: 'list-row muted' }, 'Loading…'));
    const loadDevices = async () => {
      try {
        const { devices, you } = await conn.call('core', 'devices');
        devList.replaceChildren(...devices.map((d) => {
          const isMe = d.id === you;
          const rm = h('button', { class: 'btn', style: { minHeight: '44px' } }, isMe ? 'Unpair' : 'Remove');
          onTap(rm, async () => {
            const ok = await confirmDialog({
              title: isMe ? 'Unpair this device?' : `Remove “${d.name}”?`,
              message: isMe ? 'You’ll need a new pairing code from the PC to connect again.' : 'That device will need a new pairing code to connect again.',
              confirm: isMe ? 'Unpair' : 'Remove', danger: true,
            });
            if (!ok) return;
            try {
              await conn.call('core', 'revoke_device', { id: d.id });
              if (isMe) { setToken(null); location.reload(); } else loadDevices();
            } catch (e) { toastError(e); }
          });
          return h('div', { class: 'list-row' }, icon('device'),
            h('div', { class: 'grow' }, d.name + (isMe ? ' (this device)' : ''),
              h('small', null, `Paired ${new Date(d.created * 1000).toLocaleDateString()} · last seen ${new Date(d.last_seen * 1000).toLocaleString()}`)),
            rm);
        }));
      } catch (e) {
        devList.replaceChildren(h('div', { class: 'list-row muted' }, e.message));
      }
    };
    loadDevices();
    body.append(h('div', { class: 'section-label' }, 'Paired devices'), devList);

    // --- about
    const reload = h('button', { class: 'btn' }, icon('refresh'), 'Reload app');
    onTap(reload, () => location.reload());
    const repair = h('button', { class: 'btn' }, icon('device'), 'Re-pair this device');
    onTap(repair, () => { close(); startRepair(); });
    body.append(h('div', { class: 'section-label' }, 'About'),
      h('div', { class: 'list' },
        h('div', { class: 'list-row' }, icon('device'), h('div', { class: 'grow' }, conn.server?.name || 'PC',
          h('small', null, `PadDock ${conn.server?.version || ''} · ${location.host} · ${conn.state}`)))),
      h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap' } }, reload, repair));
  }, { onClose: () => cleanups.forEach((f) => f()) });
}
