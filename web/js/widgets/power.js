// Power: lock, sleep, restart, shut down, each behind a confirmation.
import { h, css, icon, onTap } from '../core/dom.js';
import { confirmDialog } from '../core/ui.js';

css(`
.w-power { display: flex; flex-direction: column; gap: 10px; padding: 14px; }
.w-power .grid4 { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.w-power .pbtn { border: 0; border-radius: 18px; background: rgb(255 255 255 / .06); display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; font-weight: 600; font-size: 14px; min-height: var(--tap); transition: transform 160ms var(--ease), background 160ms; touch-action: manipulation; }
.w-power .pbtn svg.i { width: 28px; height: 28px; }
.w-power .pbtn.pressed { transform: scale(.94); background: rgb(255 255 255 / .12); }
.w-power .pbtn.danger svg.i { color: var(--danger); }
.w-power .pending { display: none; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 8px 8px 14px; border-radius: 16px;
  background: rgb(255 69 58 / .16); font-weight: 600; font-size: 14px; }
.w-power .pending.on { display: flex; }
.w-power .pending .btn { min-height: 44px; }
@container card (aspect-ratio > 2.6) { .w-power .grid4 { grid-template-columns: repeat(4, 1fr); } }
@container card (height < 150px) { .w-power .pbtn { flex-direction: row; } .w-power .pbtn span { display: none; } .w-power .card-title { display: none; } }
@container card (width < 220px) { .w-power .pbtn span { display: none; } }
`);

const ACTIONS = [
  { act: 'lock', label: 'Lock', ic: 'lock', confirm: 'Lock the PC?', msg: 'You’ll need to sign in on the PC again.', go: 'Lock' },
  { act: 'sleep', label: 'Sleep', ic: 'sleep', confirm: 'Put the PC to sleep?', msg: 'PadDock reconnects when the PC wakes up.', go: 'Sleep' },
  { act: 'restart', label: 'Restart', ic: 'restart', confirm: 'Restart the PC?', msg: 'Unsaved work in open apps may be lost. You can cancel for 15 seconds.', go: 'Restart', danger: true },
  { act: 'shutdown', label: 'Shut down', ic: 'power', confirm: 'Shut down the PC?', msg: 'Unsaved work in open apps may be lost. You can cancel for 15 seconds.', go: 'Shut down', danger: true },
];

export default {
  type: 'power',
  title: 'Power',
  description: 'Lock, sleep, restart and shut down',
  icon: 'power',
  sizes: [[3, 2], [2, 2], [4, 1], [2, 1], [4, 2], [8, 1]],
  mount(card, ctx) {
    const pendingText = h('span');
    const cancel = h('button', { class: 'btn' }, 'Cancel');
    const pending = h('div', { class: 'pending' }, pendingText, cancel);
    const grid = h('div', { class: 'grid4' });
    card.append(h('div', { class: 'card-title' }, icon('power'), 'Power'), pending, grid);

    for (const a of ACTIONS) {
      const b = h('button', { class: `pbtn${a.danger ? ' danger' : ''}`, 'aria-label': a.label }, icon(a.ic), h('span', null, a.label));
      onTap(b, async () => {
        if (!await confirmDialog({ title: a.confirm, message: a.msg, confirm: a.go, danger: !!a.danger })) return;
        try { await ctx.call('power', a.act); } catch (e) { ctx.toastError(e); }
      });
      grid.append(b);
    }

    let timer = null;
    onTap(cancel, () => ctx.call('power', 'cancel').then(() => ctx.toast('Cancelled')).catch(ctx.toastError));
    ctx.subscribe('power', (p) => {
      clearInterval(timer);
      pending.classList.toggle('on', !!p.pending);
      if (!p.pending) return;
      const end = Date.now() + p.delay * 1000;
      const draw = () => {
        const s = Math.max(0, Math.ceil((end - Date.now()) / 1000));
        pendingText.textContent = `${p.pending === 'restart' ? 'Restarting' : 'Shutting down'} in ${s}s`;
        if (!s) clearInterval(timer);
      };
      draw();
      timer = setInterval(draw, 250);
    });
    return { destroy: () => clearInterval(timer) };
  },
};
