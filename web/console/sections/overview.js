// Overview: is it running, how to reach it, who's connected, quick actions.
import { h, icon } from '/ui/js/core/dom.js';
import { confirmDialog, toast, toastError } from '/ui/js/core/ui.js';
import { api, apiImage, forgetImages, store } from '../api.js';
import { card, copyButton, head } from './common.js';

const ipPort = (url) => { try { const u = new URL(url); return `${u.hostname} : ${u.port}`; } catch { return url; } };

function uptime(started) {
  const s = Date.now() / 1000 - started;
  const d = Math.floor(s / 86400), hh = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d} d ${hh} h` : hh ? `${hh} h ${m} min` : `${m} min`;
}

export function pairingCard(data) {
  const qr = h('div', { class: 'c-qr' });
  apiImage(`/pairing/qr?u=${encodeURIComponent(data.setup_url)}`).then((u) => u && qr.append(h('img', { src: u, alt: 'QR code for the setup page' })));
  const rotate = h('button', { class: 'btn' }, icon('refresh'), 'New code');
  rotate.onclick = async () => {
    try { await api('POST', '/pairing/rotate'); await store.load(); toast('The old code no longer works.'); } catch (e) { toastError(e); }
  };
  return card('Pair a new device', 'device',
    h('div', { class: 'c-row', style: { alignItems: 'flex-start', gap: '20px' } },
      h('div', { class: 'c-grow', style: { display: 'flex', flexDirection: 'column', gap: '10px' } },
        h('div', { class: 'c-code' }, `${data.pairing_code.slice(0, 3)} ${data.pairing_code.slice(3)}`),
        h('p', { class: 'c-muted', style: { margin: 0 } }, 'Enter this code in PadDock on the new device. It changes after every pairing. First time on this device? Scan the QR code with its camera first: it opens the setup page.'),
        h('div', null, rotate)),
      qr));
}

export default {
  id: 'overview',
  title: 'Overview',
  icon: 'home',
  render(main, data) {
    const c = data.config;
    const conn = data.connected || [];
    const open = (what) => api('POST', '/open', { what }).catch(toastError);
    const restart = h('button', { class: 'btn' }, icon('restart'), 'Restart server');
    restart.onclick = async () => {
      if (!await confirmDialog({ title: 'Restart the PadDock server?', message: 'Connected devices reconnect by themselves in a few seconds.', confirm: 'Restart' })) return;
      try { await api('POST', '/restart'); toast('Restarting…'); setTimeout(() => location.reload(), 3500); } catch (e) { toastError(e); }
    };

    main.append(
      head('Overview', null),
      h('div', { class: 'c-cards' },
        card('Status', 'power',
          h('div', { class: 'c-big' }, h('span', { style: { color: 'var(--ok)' } }, '● '), 'Running'),
          h('div', { class: 'c-muted' }, `PadDock ${data.version} on ${data.host} · up ${uptime(data.started)}`),
          h('div', { class: 'c-muted' }, `${Object.keys(c.actions || {}).length} shortcuts · ${(c.pages || []).length} pages · ${data.devices.length} paired device(s)`)),
        card('Open on your device', 'globe',
          data.local_name && h('div', { class: 'c-muted' }, 'By name (recommended, keeps working if the IP changes):'),
          data.local_name && h('div', { class: 'c-urlbox' }, h('code', null, data.app_url), copyButton(data.app_url)),
          h('div', { class: 'c-muted' }, `By IP address and port (${ipPort(data.app_url_ip)}):`),
          h('div', { class: 'c-urlbox' }, h('code', null, data.app_url_ip), copyButton(data.app_url_ip)),
          !data.local_name && h('div', { class: 'c-muted', style: { color: 'var(--warn)' } }, 'The .local name isn’t being announced. Check Settings → Server → Network name.'),
          h('div', { class: 'c-muted' }, 'Setup page (certificate, first-time steps):'),
          h('div', { class: 'c-urlbox' }, h('code', null, data.setup_url), copyButton(data.setup_url)),
          !data.https && h('div', { class: 'c-muted', style: { color: 'var(--warn)' } }, 'HTTPS is off: keep-screen-on and the device clipboard won’t work.')),
        card('Connected now', 'device',
          conn.length
            ? h('div', { class: 'list' }, conn.map((d) => h('div', { class: 'list-row' }, icon('device'), h('div', { class: 'grow' }, d.name), h('span', { class: 'c-badge ok' }, 'online'))))
            : h('div', { class: 'c-muted' }, 'No device is connected right now.')),
        pairingCard(data),
        card('Files & server', 'settings',
          h('div', { class: 'c-row' },
            h('button', { class: 'btn', onclick: () => open('config') }, icon('notes'), 'Open config.json'),
            h('button', { class: 'btn', onclick: () => open('data') }, icon('folder'), 'Open data folder'),
            h('button', { class: 'btn', onclick: () => open('log') }, icon('text'), 'Open log'),
            restart),
          h('div', { class: 'c-muted' }, 'Hand edits to config.json are picked up automatically.'))));
    forgetImages('/pairing/qr');
  },
};
