// System monitor: CPU, RAM, GPU usage + temperature, network, disks, with live sparklines.
import { h, css, icon, fmtBytes, fmtRate } from '../core/dom.js';
import { Sparkline } from '../ui/sparkline.js';

css(`
.w-system { display: flex; flex-direction: column; gap: 12px; padding: 14px; }
.w-system .sys-cells { flex: 1; min-height: 0; display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); grid-auto-rows: minmax(0, 1fr); }
.w-system .cell { position: relative; overflow: hidden; border-radius: 18px; background: rgb(255 255 255 / 0.04);
  padding: 12px 14px; display: flex; flex-direction: column; min-height: 0; container: cell / size; }
.w-system .cell .k { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-3); position: relative; z-index: 1; }
.w-system .cell .k svg.i { width: 15px; height: 15px; }
.w-system .cell .v { font-size: clamp(20px, 22cqmin, 38px); font-weight: 600; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; line-height: 1.1; margin-top: 2px; position: relative; z-index: 1; white-space: nowrap; }
.w-system .cell .v small { font-size: .5em; color: var(--text-2); font-weight: 500; margin-left: 2px; }
.w-system .cell .s { font-size: 13px; color: var(--text-2); font-variant-numeric: tabular-nums; position: relative; z-index: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.w-system .cell canvas { position: absolute; left: 0; right: 0; bottom: 0; width: 100%; height: 55%; }
.w-system .cell .up { color: #64d2ff; } .w-system .cell .down { color: var(--accent-text); }
.w-system .cell.hot .v { color: var(--warn); } .w-system .cell.danger .v { color: var(--danger); }
@container cell (height < 90px) { .w-system .cell .s { display: none; } }
.w-system .disks { display: flex; gap: 10px; flex-wrap: wrap; }
.w-system .disk { flex: 1 1 120px; min-width: 110px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.w-system .disk .top { display: flex; justify-content: space-between; gap: 6px; }
.w-system .disk b { color: var(--text); }
.w-system .bar { height: 6px; border-radius: 4px; background: rgb(255 255 255 / 0.08); overflow: hidden; }
.w-system .bar i { display: block; height: 100%; width: var(--p); background: var(--accent); border-radius: inherit; transition: width 600ms var(--ease); }
.w-system .bar.full i { background: var(--warn); }
@container card (height < 300px) { .w-system .disks { display: none; } }
@container card (height < 200px) { .w-system .sys-cells { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); } }
`);

function cell(key, ic, { max = 100, color = null } = {}) {
  const v = h('div', { class: 'v' }, '–');
  const s = h('div', { class: 's' });
  const spark = new Sparkline({ max, color });
  const el = h('div', { class: 'cell' }, h('div', { class: 'k' }, icon(ic), key), v, s, spark.canvas);
  return { el, v, s, spark };
}

export default {
  type: 'system',
  title: 'System monitor',
  description: 'CPU, memory, GPU, network and disks',
  icon: 'cpu',
  sizes: [[4, 2], [6, 2], [8, 2], [4, 3], [8, 3], [3, 2], [8, 4]],
  mount(card, ctx) {
    const cells = h('div', { class: 'sys-cells' });
    const disks = h('div', { class: 'disks' });
    card.append(cells, disks);

    const cpu = cell('CPU', 'cpu');
    const mem = cell('Memory', 'memory');
    const net = cell('Network', 'net', { max: null });
    const netUp = new Sparkline({ max: null, color: '#64d2ff' });
    netUp.canvas.style.opacity = '0.8';
    net.el.append(netUp.canvas);
    let gpu = null, gpuTemp = null;
    cells.append(cpu.el, mem.el, net.el);

    const sparks = [cpu.spark, mem.spark, net.spark, netUp];
    let lastDisks = '';

    ctx.subscribe('system', (d) => {
      cpu.v.innerHTML = `${Math.round(d.cpu)}<small>%</small>`;
      cpu.s.textContent = d.cpu_freq ? `${(d.cpu_freq / 1000).toFixed(2)} GHz · ${d.cores?.length || ''} threads` : '';
      cpu.spark.push(d.cpu);

      mem.v.innerHTML = `${Math.round(d.mem.percent)}<small>%</small>`;
      mem.s.textContent = `${fmtBytes(d.mem.used)} of ${fmtBytes(d.mem.total, 0)}`;
      mem.spark.push(d.mem.percent);
      mem.el.classList.toggle('hot', d.mem.percent > 90);

      net.v.innerHTML = `<span class="down">↓</span> ${fmtRate(d.net.down)}`;
      net.s.innerHTML = `<span class="up">↑ ${fmtRate(d.net.up)}</span>`;
      net.spark.push(d.net.down);
      netUp.push(d.net.up);

      const g = d.gpus?.[0];
      if (g && !gpu) {
        gpu = cell('GPU', 'gpu');
        gpuTemp = cell('GPU temp', 'sun', { color: '#ff9f0a' });
        cells.insertBefore(gpu.el, net.el);
        cells.insertBefore(gpuTemp.el, net.el);
        sparks.push(gpu.spark, gpuTemp.spark);
      }
      if (g) {
        gpu.v.innerHTML = g.util == null ? 'n/a' : `${Math.round(g.util)}<small>%</small>`;
        gpu.s.textContent = `${g.name}${g.mem_total ? ` · ${fmtBytes(g.mem_used)} / ${fmtBytes(g.mem_total, 0)}` : ''}`;
        gpu.spark.push(g.util ?? 0);
        gpuTemp.v.innerHTML = g.temp == null ? 'n/a' : `${Math.round(g.temp)}<small>°C</small>`;
        gpuTemp.s.textContent = [g.power != null && `${Math.round(g.power)} W`, g.fan != null && `fan ${Math.round(g.fan)}%`].filter(Boolean).join(' · ');
        gpuTemp.spark.push(g.temp ?? 0);
        gpuTemp.el.classList.toggle('hot', g.temp >= 80 && g.temp < 90);
        gpuTemp.el.classList.toggle('danger', g.temp >= 90);
      }

      const key = JSON.stringify(d.disks);
      if (key !== lastDisks) {
        lastDisks = key;
        disks.replaceChildren(...(d.disks || []).map((k) => h('div', { class: 'disk' },
          h('div', { class: 'top' }, h('b', null, k.mount), h('span', null, `${fmtBytes(k.total - k.used)} free`)),
          h('div', { class: `bar${k.percent > 90 ? ' full' : ''}`, style: { '--p': `${k.percent}%` } }, h('i')))));
        disks.querySelectorAll('.bar').forEach((b, i) => b.style.setProperty('--p', `${d.disks[i].percent}%`));
      }
    });

    return { destroy: () => sparks.forEach((s) => s.destroy()) };
  },
};
