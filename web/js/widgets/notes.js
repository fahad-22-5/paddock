// Quick notes: a scratchpad saved on the PC (data/notes.md), synced across devices.
import { h, css, icon, debounce } from '../core/dom.js';

css(`
.w-notes { display: flex; flex-direction: column; padding: 14px 16px 16px; gap: 10px; }
.w-notes .head { display: flex; justify-content: space-between; align-items: center; min-height: 24px; }
.w-notes .status { font-size: 13px; color: var(--text-3); transition: color 200ms; }
.w-notes .status.dirty { color: var(--warn); } .w-notes .status.err { color: var(--danger); }
.w-notes textarea { flex: 1; min-height: 0; width: 100%; resize: none; border: 0; outline: none; background: transparent;
  font: 17px/1.55 var(--font); color: var(--text); padding: 0; -webkit-user-select: text; user-select: text; }
.w-notes textarea::placeholder { color: var(--text-3); }
`);

export default {
  type: 'notes',
  title: 'Quick notes',
  description: 'A scratchpad saved on the PC',
  icon: 'notes',
  sizes: [[4, 3], [3, 2], [4, 2], [5, 4], [8, 4], [2, 2]],
  mount(card, ctx) {
    const status = h('span', { class: 'status' }, '');
    const ta = h('textarea', { placeholder: 'Jot something down…  Saved on your PC as you type.', spellcheck: true, 'aria-label': 'Notes' });
    card.append(h('div', { class: 'head' }, h('div', { class: 'card-title' }, icon('notes'), 'Notes'), status), ta);

    let saved = null; // text the PC has
    let saving = false;
    const setStatus = (text, cls = '') => { status.textContent = text; status.className = `status ${cls}`; };

    const save = debounce(async () => {
      const text = ta.value;
      if (text === saved) { setStatus('Saved'); return; }
      saving = true;
      setStatus('Saving…', 'dirty');
      try {
        await ctx.call('notes', 'save', { text });
        saved = text;
        setStatus(ta.value === saved ? 'Saved' : 'Editing…', ta.value === saved ? '' : 'dirty');
      } catch (e) {
        setStatus(`Not saved: ${e.message}`, 'err');
      } finally {
        saving = false;
        if (ta.value !== saved) save();
      }
    }, 700);

    ta.addEventListener('input', () => { setStatus('Editing…', 'dirty'); save(); });
    ta.addEventListener('blur', () => save.flush());
    const onHide = () => { if (document.hidden && ta.value !== saved) save.flush(); };
    document.addEventListener('visibilitychange', onHide);

    ctx.subscribe('notes', (n) => {
      const localDirty = saved !== null && ta.value !== saved;
      if (saving || (localDirty && document.activeElement === ta)) return; // don't clobber typing
      if (n.text !== ta.value) ta.value = n.text;
      saved = n.text;
      setStatus(n.updated ? `Saved ${new Date(n.updated * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : '');
    });

    return { destroy: () => { document.removeEventListener('visibilitychange', onHide); if (ta.value !== saved) save.flush(); } };
  },
};
