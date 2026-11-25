// Clipboard: see the PC clipboard text and copy it to the device; send text to the PC.
import { h, css, icon, onTap } from '../core/dom.js';

css(`
.w-clipboard { display: grid; grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr) auto; gap: 12px; padding: 14px 16px 16px; }
.w-clipboard .pane { display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.w-clipboard .head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.w-clipboard .meta { font-size: 13px; color: var(--text-3); white-space: nowrap; }
.w-clipboard .preview { flex: 1; min-height: 44px; overflow: auto; margin: 0; padding: 10px 12px; border-radius: 14px; background: rgb(0 0 0 / 0.22);
  font: 14px/1.45 var(--mono); white-space: pre-wrap; word-break: break-word; color: var(--text); -webkit-user-select: text; user-select: text; }
.w-clipboard .preview.empty { color: var(--text-3); font-family: var(--font); }
.w-clipboard .send { display: flex; gap: 8px; align-items: stretch; }
.w-clipboard .send textarea { flex: 1; min-height: 56px; max-height: 120px; padding: 14px; }
.w-clipboard .btns { display: flex; gap: 8px; }
.w-clipboard .btn { padding: 0 16px; }
@container card (aspect-ratio > 1.5) and (height > 200px) {
  .w-clipboard { grid-template-columns: 1.3fr 1fr; grid-template-rows: minmax(0, 1fr); }
  .w-clipboard .send { flex-direction: column; } .w-clipboard .send textarea { max-height: none; flex: 1; }
}
@container card (height < 230px) { .w-clipboard .send textarea { display: none; } .w-clipboard .send { justify-content: flex-end; } }
@container card (width < 360px) { .w-clipboard .btn span { display: none; } }
`);

export default {
  type: 'clipboard',
  title: 'Clipboard',
  description: 'Copy text between the PC and this device',
  icon: 'clipboard',
  sizes: [[4, 2], [3, 2], [4, 3], [6, 2], [8, 2]],
  mount(card, ctx) {
    const meta = h('span', { class: 'meta' });
    const preview = h('pre', { class: 'preview empty' }, 'Nothing copied on the PC yet.');
    const copyBtn = h('button', { class: 'btn', 'aria-label': 'Copy to this device' }, icon('copy'), h('span', null, 'Copy here'));
    const input = h('textarea', { class: 'field', placeholder: 'Type or paste text to send to the PC…', rows: 2 });
    const pasteBtn = h('button', { class: 'btn', 'aria-label': 'Paste from this device’s clipboard' }, icon('paste'), h('span', null, 'Paste'));
    const sendBtn = h('button', { class: 'btn primary', 'aria-label': 'Send to PC' }, icon('send'), h('span', null, 'Send to PC'));

    card.append(
      h('div', { class: 'pane' }, h('div', { class: 'head' }, h('div', { class: 'card-title' }, icon('clipboard'), 'PC clipboard'), meta), preview,
        h('div', { class: 'btns' }, copyBtn)),
      h('div', { class: 'pane send' }, input, h('div', { class: 'btns' }, pasteBtn, sendBtn)));

    let clip = null;
    ctx.subscribe('clipboard', (c) => {
      clip = c;
      const has = c && c.text != null && c.text !== '';
      preview.textContent = has ? c.text + (c.truncated ? '\n…' : '') : 'No text on the PC clipboard.';
      preview.classList.toggle('empty', !has);
      meta.textContent = has ? `${c.length.toLocaleString()} chars · ${new Date(c.changed * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : '';
      copyBtn.disabled = !has;
    });

    const canClip = !!navigator.clipboard;
    onTap(copyBtn, async () => {
      if (!clip?.text) return;
      if (!canClip) { ctx.toastError(new Error('Clipboard access needs https:// (see the setup page on the PC).')); return; }
      try {
        if (clip.truncated) {
          // Safari only allows clipboard writes inside the tap, so hand it a promise.
          const blob = ctx.call('clipboard', 'get_full').then((t) => new Blob([t ?? ''], { type: 'text/plain' }));
          await navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })]);
        } else {
          await navigator.clipboard.writeText(clip.text);
        }
        ctx.toast('Copied to this device’s clipboard');
      } catch (e) { ctx.toastError(new Error(`Couldn't copy: ${e.message}`)); }
    });

    onTap(pasteBtn, async () => {
      if (!canClip) { ctx.toastError(new Error('Clipboard access needs https:// (see the setup page on the PC).')); return; }
      try { input.value = await navigator.clipboard.readText(); input.focus(); }
      catch { ctx.toastError(new Error('Paste was not allowed. Long-press the text box and choose Paste instead.')); }
    });

    onTap(sendBtn, async () => {
      const text = input.value;
      if (!text) { input.focus(); return; }
      sendBtn.disabled = true;
      try {
        await ctx.call('clipboard', 'set', { text });
        input.value = '';
        ctx.toast('Sent to the PC clipboard');
      } catch (e) { ctx.toastError(e); }
      sendBtn.disabled = false;
    });
  },
};
