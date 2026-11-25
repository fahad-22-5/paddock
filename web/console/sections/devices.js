// Devices: paired devices, who's online, remove access, pairing code.
import { h, icon } from '/ui/js/core/dom.js';
import { confirmDialog, promptDialog, toast, toastError } from '/ui/js/core/ui.js';
import { api, store } from '../api.js';
import { head, timeAgo } from './common.js';
import { pairingCard } from './overview.js';

export default {
  id: 'devices',
  title: 'Devices',
  icon: 'device',
  render(main, data) {
    const online = new Set((data.connected || []).map((c) => c.id));
    const revoke = async (d) => {
      if (!await confirmDialog({ title: `Remove “${d.name}”?`, message: 'It is disconnected now and needs a new pairing code to connect again.', confirm: 'Remove', danger: true })) return;
      try { await api('POST', `/devices/${encodeURIComponent(d.id)}/revoke`); await store.load(); } catch (e) { toastError(e); }
    };
    const rename = async (d) => {
      const name = await promptDialog({ title: 'Rename device', message: 'Each paired device needs its own name.', value: d.name, confirm: 'Rename' });
      if (!name || name === d.name) return;
      try { await api('POST', `/devices/${encodeURIComponent(d.id)}/rename`, { name }); toast('Renamed.'); await store.load(); } catch (e) { toastError(e); }
    };
    const removeAll = h('button', { class: 'btn danger' }, icon('trash'), 'Remove all devices');
    removeAll.onclick = async () => {
      if (!await confirmDialog({ title: 'Remove every paired device?', message: 'All devices are disconnected and must pair again.', confirm: 'Remove all', danger: true })) return;
      try {
        for (const d of data.devices) await api('POST', `/devices/${encodeURIComponent(d.id)}/revoke`);
        await store.load();
      } catch (e) { toastError(e); }
    };

    main.append(head('Devices', 'Paired devices keep working until you remove them here (or on the device under Settings).', data.devices.length ? removeAll : null));
    main.append(h('section', { class: 'c-card wide', style: { marginBottom: '16px' } },
      data.devices.length
        ? h('table', { class: 'c-table' },
          h('thead', null, h('tr', null, h('th', null, 'Device'), h('th', null, 'Status'), h('th', null, 'Paired'), h('th', null, 'Last seen'), h('th'))),
          h('tbody', null, data.devices.map((d) => h('tr', null,
            h('td', null, h('div', { class: 'c-row' }, icon('device'), h('b', null, d.name))),
            h('td', null, online.has(d.id) ? h('span', { class: 'c-badge ok' }, 'Connected') : h('span', { class: 'c-badge' }, 'Offline')),
            h('td', { class: 'c-muted' }, new Date(d.created * 1000).toLocaleDateString()),
            h('td', { class: 'c-muted' }, online.has(d.id) ? 'now' : timeAgo(d.last_seen)),
            h('td', null, h('div', { class: 'c-row', style: { justifyContent: 'flex-end' } },
              h('button', { class: 'btn', onclick: () => rename(d) }, 'Rename'),
              h('button', { class: 'btn', onclick: () => revoke(d) }, 'Remove')))))))
        : h('div', { class: 'c-muted' }, 'No devices are paired yet.')));
    main.append(h('div', { class: 'c-cards' }, pairingCard(data)));
  },
};
