// Pairing screen: enter the 6-digit code the PC shows, receive a token.
// Re-pairing (from the Disconnected banner or Settings) sends the old token along, so the
// PC replaces this device's old entry instead of adding a second one.
import { h, storage } from '../core/dom.js';
import { confirmDialog } from '../core/ui.js';

export const TOKEN_KEY = 'paddock.token';
const REPLACE_KEY = 'paddock.replaceToken'; // old token kept while re-pairing
const NAME_KEY = 'paddock.deviceName';
export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch {} };
export const rememberDeviceName = (name) => storage.set(NAME_KEY, name);

/** Ask, then forget this device's pairing and show the pairing screen. Works while disconnected. */
export async function startRepair() {
  const ok = await confirmDialog({
    title: 'Re-pair this device?',
    message: 'Use this when the PC was reinstalled or this device keeps saying “Disconnected”. You’ll need the 6-digit code from the PC: open the PadDock console, or click its tray / menu bar icon and choose “Show pairing code”.',
    confirm: 'Re-pair',
  });
  if (!ok) return;
  const old = getToken();
  try { if (old) localStorage.setItem(REPLACE_KEY, old); } catch {}
  setToken(null);
  location.replace(`${location.pathname}#repair`);
  location.reload();
}

export function showPairing(root, { reason = '' } = {}) {
  return new Promise((resolve) => {
    let replaceToken = null;
    try { replaceToken = localStorage.getItem(REPLACE_KEY); } catch {}
    const repairing = !!replaceToken;
    const fromHash = (location.hash.match(/pair=(\d{6})/) || [])[1] || '';
    const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
    const code = h('input', {
      class: 'field code-input', inputmode: 'numeric', pattern: '[0-9]*', maxlength: 6,
      autocomplete: 'one-time-code', placeholder: '••••••', 'aria-label': 'Pairing code', value: fromHash,
    });
    const name = h('input', {
      class: 'field', value: storage.get(NAME_KEY, 'Dock'), maxlength: 40, 'aria-label': 'Device name',
      placeholder: 'Device name, e.g. Living room tablet',
    });
    const error = h('div', { class: 'error', role: 'alert' }, reason);
    const setupUrl = `http://${location.hostname}:${(+location.port || 443) + 1}/`;
    const certHint = h('p', { class: 'hint', hidden: true },
      'If PadDock is running on the PC, its security certificate may have changed (for example after reinstalling). ',
      'Open the setup page and install the certificate again: ', h('a', { href: setupUrl, style: { color: 'var(--accent-text)' } }, setupUrl));
    const submit = h('button', { class: 'btn primary', type: 'submit' }, repairing ? 'Re-pair' : 'Pair');
    const back = repairing && h('button', {
      class: 'btn', type: 'button',
      onclick: () => {
        // Changed your mind: go back to the previous pairing.
        setToken(replaceToken);
        try { localStorage.removeItem(REPLACE_KEY); } catch {}
        history.replaceState(null, '', location.pathname);
        location.reload();
      },
    }, 'Cancel');

    const form = h('form', {
      class: 'pair-card',
      onsubmit: async (e) => {
        e.preventDefault();
        const value = code.value.replace(/\D/g, '');
        if (value.length !== 6) { error.textContent = 'Enter all 6 digits.'; return; }
        const deviceName = name.value.trim() || 'Dock';
        submit.disabled = true;
        error.textContent = '';
        try {
          const res = await fetch('/api/pair', {
            method: 'POST', headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ code: value, name: deviceName, replace_token: replaceToken }),
          });
          const body = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(body.detail || `Pairing failed (${res.status})`);
          setToken(body.token);
          rememberDeviceName(deviceName);
          try { localStorage.removeItem(REPLACE_KEY); } catch {}
          if (location.hash) history.replaceState(null, '', location.pathname);
          resolve(body.token);
        } catch (err) {
          const offline = err.message === 'Load failed' || err.message === 'Failed to fetch';
          error.textContent = offline ? "Can't reach the PC. Is PadDock running, and is this device on the same Wi-Fi?" : err.message;
          certHint.hidden = !offline;
          submit.disabled = false;
          if (/already paired/i.test(err.message)) { name.focus(); name.select(); } else code.select();
        }
      },
    },
      h('img', { src: '/icons/icon-192.png', alt: '' }),
      h('h1', null, repairing ? 'Re-pair with your PC' : 'Pair with your PC'),
      h('p', null, 'Enter the 6-digit code from the PadDock console on your PC, or from “Show pairing code” in its tray or menu bar icon.'),
      code,
      h('label', { class: 'hint', style: { textAlign: 'left', marginBottom: '-10px' } }, 'Device name (each device needs its own)'),
      name, error, certHint,
      h('div', { style: { display: 'flex', gap: '10px' } }, back, h('div', { style: { flex: 1, display: 'flex' } }, submit)),
      !standalone && h('p', { class: 'hint' },
        'Tip: add PadDock to your Home Screen first (Share → Add to Home Screen) and pair from there. ' +
        'iPhone and iPad keep Home Screen apps’ storage separate from Safari.'),
    );
    submit.style.flex = '1';
    code.addEventListener('input', () => {
      code.value = code.value.replace(/\D/g, '').slice(0, 6);
      if (code.value.length === 6) form.requestSubmit();
    });
    root.replaceChildren(h('div', { class: 'pair' }, form));
    if (!fromHash) code.focus();
  });
}
