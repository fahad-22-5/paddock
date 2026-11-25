// Toasts, confirm dialogs and bottom sheets.
import { h, icon } from './dom.js';

let toastHost;
export function toast(message, { error = false, action = null, duration = 3200 } = {}) {
  toastHost ??= document.body.appendChild(h('div', { class: 'toasts', role: 'status', 'aria-live': 'polite' }));
  const el = h('div', { class: `toast${error ? ' error' : ''}` }, h('span', null, message));
  const close = () => { el.classList.add('leaving'); setTimeout(() => el.remove(), 230); };
  if (action) el.append(h('button', { class: 'btn', onclick: () => { action.run(); close(); } }, action.label));
  toastHost.append(el);
  while (toastHost.children.length > 3) toastHost.firstChild.remove();
  setTimeout(close, duration);
  return close;
}

export const toastError = (err) => toast(err?.message || String(err), { error: true });

/** confirmDialog({title, message, confirm: 'Shut down', danger: true}) -> Promise<boolean> */
export function confirmDialog({ title, message = '', confirm = 'OK', cancel = 'Cancel', danger = false }) {
  return new Promise((resolve) => {
    const dlg = h('dialog', null,
      h('form', { class: 'dlg', method: 'dialog' },
        h('h2', null, title),
        message && h('p', null, message),
        h('div', { class: 'row' },
          h('button', { class: 'btn', value: 'cancel' }, cancel),
          h('button', { class: `btn ${danger ? 'danger' : 'primary'}`, value: 'ok', autofocus: true }, confirm))));
    dlg.addEventListener('close', () => { resolve(dlg.returnValue === 'ok'); dlg.remove(); });
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close('cancel'); });
    document.body.append(dlg);
    dlg.showModal();
  });
}

/** promptDialog({title, value, placeholder}) -> Promise<string|null> */
export function promptDialog({ title, message = '', value = '', placeholder = '', confirm = 'Save' }) {
  return new Promise((resolve) => {
    const input = h('input', { class: 'field', value, placeholder, autocomplete: 'off', enterkeyhint: 'done' });
    const dlg = h('dialog', null,
      h('form', { class: 'dlg', method: 'dialog' },
        h('h2', null, title), message && h('p', null, message), input,
        h('div', { class: 'row' },
          h('button', { class: 'btn', value: 'cancel', formnovalidate: true }, 'Cancel'),
          h('button', { class: 'btn primary', value: 'ok' }, confirm))));
    dlg.addEventListener('close', () => { resolve(dlg.returnValue === 'ok' ? input.value.trim() : null); dlg.remove(); });
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close('cancel'); });
    document.body.append(dlg);
    dlg.showModal();
    input.focus();
  });
}

/** A titled sheet with a scrolling body. Returns {dlg, body, close}. */
export function sheet(title, build, { onClose } = {}) {
  const body = h('div', { class: 'sheet-body' });
  const dlg = h('dialog', { class: 'sheet' },
    h('div', { class: 'sheet-head' },
      h('h2', null, title),
      h('button', { class: 'btn icon ghost', 'aria-label': 'Close', onclick: () => dlg.close() }, icon('close'))),
    body);
  const close = () => dlg.close();
  dlg.addEventListener('close', () => { onClose?.(); dlg.remove(); });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  document.body.append(dlg);
  build(body, close);
  dlg.showModal();
  return { dlg, body, close };
}
