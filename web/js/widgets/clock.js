// Clock, date and optional weather (Open-Meteo via the PC, no API key).
import { h, css } from '../core/dom.js';

css(`
.w-clock { display: flex; align-items: center; padding: clamp(14px, 6cqmin, 28px); gap: 6cqi; }
.w-clock .time-col { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; }
.w-clock .time { font-weight: 200; font-size: min(30cqb, 24cqi); line-height: .95; letter-spacing: -0.04em; font-variant-numeric: tabular-nums; white-space: nowrap; }
.w-clock .time .sec { font-size: .32em; color: var(--text-3); letter-spacing: 0; margin-left: .15em; font-weight: 400; }
.w-clock .time .ampm { font-size: .3em; color: var(--text-2); margin-left: .25em; letter-spacing: 0; font-weight: 500; }
.w-clock .date { font-size: max(15px, min(8cqb, 4.6cqi)); color: var(--text-2); font-weight: 500; margin-top: 1.2cqb; }
.w-clock .date b { color: var(--accent-text); font-weight: 600; }
.w-clock .wx { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; text-align: right; flex: none; }
.w-clock .wx-now { display: flex; align-items: center; gap: 10px; }
.w-clock .wx-emoji { font-size: min(18cqb, 13cqi); line-height: 1; }
.w-clock .wx-temp { font-size: min(20cqb, 14cqi); font-weight: 300; line-height: 1; font-variant-numeric: tabular-nums; }
.w-clock .wx-meta { color: var(--text-2); font-size: 14px; }
.w-clock .wx-days { display: flex; gap: 14px; margin-top: 8px; }
.w-clock .wx-day { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: 13px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.w-clock .wx-day span:nth-child(2) { font-size: 22px; }
.w-clock .wx-day b { color: var(--text); font-weight: 600; }
@container card (aspect-ratio < 1.5) { .w-clock { flex-direction: column; align-items: stretch; justify-content: center; } .w-clock .wx { align-items: flex-start; text-align: left; } .w-clock .time { font-size: min(24cqb, 26cqi); } }
@container card (height < 260px) { .w-clock .wx-days { display: none; } }
@container card (width < 330px) { .w-clock .wx { display: none; } .w-clock .time { font-size: 26cqi; } }
@container card (height < 150px) { .w-clock .time .sec { display: none; } }
`);

// WMO weather codes -> emoji + description
const WMO = {
  0: ['☀️', 'Clear'], 1: ['🌤️', 'Mostly clear'], 2: ['⛅', 'Partly cloudy'], 3: ['☁️', 'Overcast'],
  45: ['🌫️', 'Fog'], 48: ['🌫️', 'Fog'], 51: ['🌦️', 'Drizzle'], 53: ['🌦️', 'Drizzle'], 55: ['🌧️', 'Drizzle'],
  56: ['🌧️', 'Freezing drizzle'], 57: ['🌧️', 'Freezing drizzle'], 61: ['🌦️', 'Light rain'], 63: ['🌧️', 'Rain'], 65: ['🌧️', 'Heavy rain'],
  66: ['🌧️', 'Freezing rain'], 67: ['🌧️', 'Freezing rain'], 71: ['🌨️', 'Light snow'], 73: ['🌨️', 'Snow'], 75: ['❄️', 'Heavy snow'],
  77: ['🌨️', 'Snow grains'], 80: ['🌦️', 'Showers'], 81: ['🌧️', 'Showers'], 82: ['⛈️', 'Heavy showers'],
  85: ['🌨️', 'Snow showers'], 86: ['❄️', 'Snow showers'], 95: ['⛈️', 'Thunderstorm'], 96: ['⛈️', 'Thunderstorm'], 99: ['⛈️', 'Thunderstorm'],
};
export const wmo = (code, isDay = true) => {
  const [e, d] = WMO[code] || ['🌡️', ''];
  return [!isDay && code <= 1 ? '🌙' : e, d];
};

export default {
  type: 'clock',
  title: 'Clock & weather',
  description: 'Big clock, date and local weather',
  icon: 'clock',
  sizes: [[4, 2], [3, 2], [2, 1], [3, 1], [4, 3], [6, 2], [8, 2]],
  mount(card, ctx) {
    const time = h('div', { class: 'time' });
    const date = h('div', { class: 'date' });
    const wx = h('div', { class: 'wx' });
    card.append(h('div', { class: 'time-col' }, time, date), wx);

    const hour12 = new Intl.DateTimeFormat(undefined, { hour: 'numeric' }).resolvedOptions().hour12;
    const fmtDate = new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
    let lastMin = -1;
    const tick = () => {
      const d = new Date();
      let hh = d.getHours();
      const ampm = hh >= 12 ? 'PM' : 'AM';
      if (hour12) hh = hh % 12 || 12;
      const mm = String(d.getMinutes()).padStart(2, '0');
      const ss = String(d.getSeconds()).padStart(2, '0');
      time.innerHTML = `${hour12 ? hh : String(hh).padStart(2, '0')}:${mm}<span class="sec">${ss}</span>${hour12 ? `<span class="ampm">${ampm}</span>` : ''}`;
      if (d.getMinutes() !== lastMin) {
        lastMin = d.getMinutes();
        const parts = fmtDate.formatToParts(d);
        date.innerHTML = parts.map((p) => (p.type === 'weekday' ? `<b>${p.value}</b>` : p.value)).join('');
      }
    };
    tick();
    let timer;
    const schedule = () => { timer = setTimeout(() => { tick(); schedule(); }, 1000 - (Date.now() % 1000) + 5); };
    schedule();

    ctx.subscribe('weather', (w) => {
      if (!w || !w.current) {
        wx.replaceChildren(w?.error ? h('div', { class: 'wx-meta' }, w.error) : '');
        return;
      }
      const [emoji, desc] = wmo(w.current.code, w.current.is_day);
      const u = w.units === 'fahrenheit' ? '°' : '°';
      const today = w.daily?.[0];
      wx.replaceChildren(
        h('div', { class: 'wx-now' }, h('span', { class: 'wx-emoji' }, emoji), h('span', { class: 'wx-temp' }, `${Math.round(w.current.temp)}${u}`)),
        h('div', { class: 'wx-meta' }, `${desc}${today ? ` · ${Math.round(today.max)}° / ${Math.round(today.min)}°` : ''}`),
        h('div', { class: 'wx-meta' }, w.name || ''),
        h('div', { class: 'wx-days' }, (w.daily || []).slice(1, 5).map((d) => h('div', { class: 'wx-day' },
          h('span', null, new Date(d.date + 'T12:00').toLocaleDateString(undefined, { weekday: 'short' })),
          h('span', null, wmo(d.code)[0]),
          h('span', null, h('b', null, `${Math.round(d.max)}°`), ` ${Math.round(d.min)}°`)))),
      );
    });

    return { destroy: () => clearTimeout(timer) };
  },
};
