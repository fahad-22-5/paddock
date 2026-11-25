// Widget registry. To add a widget: create widgets/<name>.js exporting
//   { type, title, description, icon, sizes: [[w, h], ...], mount(card, ctx) -> {destroy?, update?} }
// and list it below. If it needs live data, add a server module (server/modules/).
import { h } from '../core/dom.js';
import { mountActionTile } from './action-tile.js';
import clock from './clock.js';
import system from './system.js';
import notes from './notes.js';
import clipboard from './clipboard.js';
import media from './media.js';
import volume from './volume.js';
import power from './power.js';
import touchpad from './touchpad.js';

const ALL = [clock, media, volume, system, notes, clipboard, power, touchpad];

export const WIDGETS = Object.fromEntries(ALL.map((w) => [w.type, w]));

export function mountItem(el, item, ctx) {
  if (item.kind === 'action') return mountActionTile(el, item, ctx);
  const card = h('div', { class: `card w-${item.type}` });
  el.append(card);
  const def = WIDGETS[item.type];
  if (!def) {
    card.append(h('div', { class: 'empty-note', style: { margin: 'auto' } }, `Unknown widget “${item.type}”`));
    return null;
  }
  return def.mount(card, ctx) || null;
}
