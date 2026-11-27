// Settings: accent colour, weather, start at login, server ports/HTTPS.
import { h, icon } from '/ui/js/core/dom.js';
import { confirmDialog, toast, toastError } from '/ui/js/core/ui.js';
import { api, store } from '../api.js';
import { card, head, isMac, trayWord } from './common.js';

const SWATCHES = ['#0a84ff', '#5e5ce6', '#bf5af2', '#ff375f', '#ff9f0a', '#ffd60a', '#30d158', '#64d2ff', '#ac8e68', '#8e8e93'];

export default {
  id: 'settings',
  title: 'Settings',
  icon: 'settings',
  render(main, data) {
    const c = data.config;
    const set = async (body, msg) => {
      try { await api('POST', '/settings', body); await store.load(); if (msg) toast(msg); } catch (e) { toastError(e); }
    };

    // Appearance
    const accent = (c.appearance?.accent || '#0a84ff').toLowerCase();
    const custom = h('input', { type: 'color', value: accent });
    custom.addEventListener('change', () => set({ accent: custom.value }));
    const swatches = h('div', { class: 'swatches' }, SWATCHES.map((col) => {
      const b = h('button', { class: 'swatch', title: col, 'aria-pressed': String(col === accent), onclick: () => set({ accent: col }) });
      b.style.setProperty('--c', col);
      return b;
    }), h('label', { class: 'swatch swatch-custom', title: 'Custom', 'aria-pressed': String(!SWATCHES.includes(accent)) }, custom));

    // Weather
    const w = c.weather || {};
    const city = h('input', { class: 'field', placeholder: 'City, e.g. Mumbai', value: w.name || '' });
    const setCity = () => city.value.trim() && set({ city: city.value.trim() }, 'Weather location updated.');
    city.addEventListener('keydown', (e) => { if (e.key === 'Enter') setCity(); });
    const units = h('div', { class: 'chips' }, [['celsius', '°C'], ['fahrenheit', '°F']].map(([k, l]) =>
      h('button', { class: 'chip', 'aria-pressed': String((w.units || 'celsius') === k), onclick: () => set({ units: k }) }, l)));
    const wxOn = h('input', { type: 'checkbox', class: 'switch', checked: w.enabled !== false });
    wxOn.onchange = () => set({ weather_enabled: wxOn.checked });

    // Album art
    const artOn = h('input', { type: 'checkbox', class: 'switch', checked: c.media?.online_art !== false });
    artOn.onchange = () => set({ online_art: artOn.checked }, artOn.checked ? 'Sharp album art lookup is on.' : 'Album art now comes only from the music app.');

    // Startup
    const auto = h('input', { type: 'checkbox', class: 'switch', checked: data.autostart });
    auto.onchange = async () => {
      try {
        const r = await api('POST', '/autostart', { enabled: auto.checked });
        toast(r.enabled ? `PadDock will start (with its ${trayWord()}) when you log in.` : 'PadDock won’t start at login any more.');
        await store.load();
      } catch (e) { toastError(e); auto.checked = !auto.checked; }
    };

    // Server
    const srv = c.server || {};
    const port = h('input', { class: 'field', type: 'number', min: 1024, max: 65535, value: srv.port ?? 8765 });
    const setupPort = h('input', { class: 'field', type: 'number', min: 1024, max: 65535, value: srv.setup_port ?? 8766 });
    const bind = h('input', { class: 'field', value: srv.bind || 'auto', placeholder: 'auto' });
    const hostname = h('input', { class: 'field', value: srv.hostname || 'paddock', placeholder: 'paddock', maxlength: 32, style: { width: '180px' } });
    const https = h('input', { type: 'checkbox', class: 'switch', checked: srv.https !== false });
    const saveServer = h('button', { class: 'btn primary' }, icon('restart'), 'Save and restart');
    saveServer.onclick = async () => {
      const body = { server: { port: +port.value, setup_port: +setupPort.value, bind: bind.value.trim() || 'auto', https: https.checked, hostname: hostname.value.trim() || 'paddock' } };
      const nameChanged = body.server.hostname !== (srv.hostname || 'paddock');
      const portChanged = body.server.setup_port !== (srv.setup_port ?? 8766);
      if (!await confirmDialog({
        title: 'Restart with these settings?',
        message: `Connected devices reconnect by themselves${nameChanged || body.server.port !== srv.port || body.server.https !== (srv.https !== false) ? ', but the device address changes: add PadDock to the Home Screen again from the new address and pair again' : ''}.`,
        confirm: 'Save and restart',
      })) return;
      try {
        await api('POST', '/settings', body);
        await api('POST', '/restart');
        toast('Restarting…');
        if (portChanged) {
          setTimeout(() => { location.href = `http://127.0.0.1:${body.server.setup_port}/console/`; }, 3500);
        } else setTimeout(() => location.reload(), 3500);
      } catch (e) { toastError(e); }
    };

    const row = (label, ...controls) => [h('label', null, label), h('div', { class: 'c-row' }, ...controls)];
    main.append(
      head('Settings', null),
      h('div', { class: 'c-cards' },
        card('Appearance', 'sun', swatches, h('div', { class: 'c-muted' }, 'The accent colour of the dock app and this console.')),
        card('Weather (Open-Meteo)', 'sun',
          h('div', { class: 'c-row' }, h('div', { class: 'c-grow' }, city), h('button', { class: 'btn primary', onclick: setCity }, 'Set')),
          h('div', { class: 'c-row' }, units, h('div', { class: 'c-grow' }), h('label', { class: 'c-row' }, 'Show weather', wxOn)),
          h('div', { class: 'c-muted' }, w.name ? `Now showing: ${w.name}` : 'No city set yet.')),
        card('Album art', 'music',
          h('label', { class: 'c-row' }, h('div', { class: 'c-grow' }, h('b', null, 'Look up sharp covers online'),
            h('div', { class: 'c-muted' }, 'Some players (like YouTube Music in Chrome) only share a tiny thumbnail. PadDock can fetch the matching full-size cover from the iTunes Search API. This sends the song title and artist to Apple.')), artOn)),
        card('Startup', 'power',
          h('label', { class: 'c-row' }, h('div', { class: 'c-grow' }, h('b', null, 'Start PadDock when I log in'),
            h('div', { class: 'c-muted' }, isMac() ? 'Runs in the background with a menu bar icon (a LaunchAgent, no admin needed).' : 'Runs in the background with a tray icon (Startup folder shortcut, no admin needed).')), auto))),
      h('div', { class: 'c-section-title' }, 'Server'),
      h('section', { class: 'c-card wide' },
        h('div', { class: 'c-form' },
          ...row('Network name', hostname, h('span', { class: 'c-muted' }, '.local, so the device opens https://NAME.local:PORT')),
          ...row('App port', port),
          ...row('Setup & console port', setupPort),
          ...row('Listen on', bind, h('span', { class: 'c-muted' }, '“auto” = this PC’s Wi-Fi/Ethernet address + localhost')),
          ...row('HTTPS', https, h('span', { class: 'c-muted' }, 'Needed for keep-screen-on and the device clipboard'))),
        h('div', { class: 'c-row' }, saveServer, h('span', { class: 'c-muted' }, 'Only private-network devices can connect, whatever you choose here.'))));
  },
};
