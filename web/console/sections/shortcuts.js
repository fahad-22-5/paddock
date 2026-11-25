// Shortcuts: everything a launcher/macro tile can do. Add programs, files, folders,
// installed apps, links, commands, keyboard shortcuts, text snippets and macros.
import { h, icon } from '/ui/js/core/dom.js';
import { confirmDialog, sheet, toast, toastError } from '/ui/js/core/ui.js';
import { api, apiImage, forgetImages, store } from '../api.js';
import { TYPES, art, detail, head, usage } from './common.js';

let query = '';
let filter = 'all';
const FILTERS = [['all', 'All'], ['apps', 'Apps & files'], ['folders', 'Folders'], ['links', 'Links'], ['commands', 'Commands'], ['keys', 'Keys & text']];

export default {
  id: 'shortcuts',
  title: 'Shortcuts',
  icon: 'bolt',
  render(main, data) {
    const actions = data.config.actions || {};
    const used = usage(data.config);

    const search = h('input', { class: 'field', type: 'search', placeholder: 'Search shortcuts', value: query });
    const list = h('div', { class: 'c-shortcuts' });
    const chips = h('div', { class: 'c-row' });

    const draw = () => {
      chips.replaceChildren(...FILTERS.map(([k, l]) => h('button', { class: 'chip', 'aria-pressed': String(filter === k), onclick: () => { filter = k; draw(); } }, l)));
      const q = query.toLowerCase();
      const rows = Object.entries(actions)
        .filter(([, a]) => filter === 'all' || TYPES[a.type]?.group === filter)
        .filter(([id, a]) => !q || `${a.label} ${detail(a)} ${id}`.toLowerCase().includes(q))
        .sort((x, y) => (x[1].label || '').localeCompare(y[1].label || ''));
      list.replaceChildren(...(rows.length ? rows.map(([id, a]) => shortcutCard(id, a, used[id])) :
        [h('div', { class: 'c-empty', style: { gridColumn: '1 / -1' } }, Object.keys(actions).length ? 'No shortcuts match.' : 'No shortcuts yet. Add an app, folder or keyboard shortcut to get started.')]));
    };
    search.addEventListener('input', () => { query = search.value; draw(); });

    main.append(
      head('Shortcuts', 'Shortcuts become tiles on the dock. Programs, folders and commands can only be created here on the PC.',
        h('button', { class: 'btn', onclick: () => openAppPicker() }, icon('app'), 'Add installed app'),
        h('button', { class: 'btn', onclick: () => quickAdd('folder') }, icon('folder'), 'Add folder'),
        h('button', { class: 'btn', onclick: () => quickAdd('file') }, icon('page'), 'Add file or program'),
        h('button', { class: 'btn primary', onclick: () => openEditor() }, icon('plus'), 'New shortcut')),
      h('div', { class: 'c-toolbar' }, search, chips),
      list);
    draw();
  },
};

function shortcutCard(id, a, pages = []) {
  const test = h('button', { class: 'btn icon', title: 'Run it now on this PC', 'aria-label': 'Test' }, icon('play'));
  test.onclick = async () => {
    try { await api('POST', `/actions/${encodeURIComponent(id)}/test`); toast(`Ran “${a.label}”`); } catch (e) { toastError(e); }
  };
  const edit = h('button', { class: 'btn icon', title: 'Edit', 'aria-label': 'Edit', onclick: () => openEditor(id) }, icon('edit'));
  const del = h('button', { class: 'btn icon', title: 'Delete', 'aria-label': 'Delete' }, icon('trash'));
  del.onclick = async () => {
    const where = pages.length ? ` It's on: ${pages.join(', ')}.` : '';
    if (!await confirmDialog({ title: `Delete “${a.label}”?`, message: `The shortcut and its tiles are removed.${where}`, confirm: 'Delete', danger: true })) return;
    try { await api('DELETE', `/actions/${encodeURIComponent(id)}`); await store.load(); } catch (e) { toastError(e); }
  };
  return h('div', { class: 'c-sc' },
    art(id, a),
    h('div', { class: 'name', title: a.label }, a.label),
    h('div', { class: 'btns' }, test, edit, del),
    h('div', { class: 'detail', title: detail(a) },
      h('span', { class: 'c-badge' }, TYPES[a.type]?.label || a.type),
      a.origin === 'ipad' ? h('span', { class: 'c-badge' }, 'made on a device') : '',
      h('span', { class: 'txt' }, detail(a) || '')),
    h('div', { class: 'pages' }, pages.length ? pages.map((p) => h('span', { class: 'c-badge ok' }, p)) : h('span', { class: 'c-muted' }, 'Not on any page')));
}

// ---- quick add from a native picker -----------------------------------------
async function quickAdd(kind) {
  try {
    const { path } = await api('POST', '/pick', { kind: kind === 'folder' ? 'folder' : 'file' });
    if (!path) return;
    const name = path.split(/[\\/]/).filter(Boolean).pop() || path;
    const label = kind === 'folder' ? name : name.replace(/\.(exe|lnk|bat|cmd)$/i, '');
    openEditor(null, { type: kind === 'folder' ? 'folder' : 'exe', path, label: label.slice(0, 40) });
  } catch (e) { toastError(e); }
}

// ---- editor --------------------------------------------------------------
const SWATCHES = ['#0a84ff', '#5e5ce6', '#bf5af2', '#ff375f', '#ff9f0a', '#30d158', '#64d2ff', '#24292f'];

function defaultPageFor(type, pages) {
  const want = ['keys', 'text', 'steps'].includes(type) ? /macro/i : /launch/i;
  return (pages.find((p) => want.test(p.title)) || pages[0])?.id || '';
}

export function openEditor(editId = null, preset = null) {
  const data = store.data;
  const existing = editId ? data.config.actions[editId] : null;
  const s = structuredClone(existing || preset || { type: 'exe', label: '' });
  let addTo = editId ? '' : defaultPageFor(s.type, data.config.pages);
  let pageTouched = false;

  const form = h('div', { class: 'form' });
  const preview = h('div', { class: 'c-preview' });

  const { dlg, body, close } = sheet(existing ? `Edit “${existing.label}”` : 'New shortcut', (b) => b.append(form, preview));
  dlg.classList.add('c-editor');

  const input = (key, attrs = {}) => {
    const el = h(attrs.rows ? 'textarea' : 'input', { class: 'field', value: s[key] ?? '', ...attrs });
    if (attrs.rows) el.value = s[key] ?? '';
    el.addEventListener('input', () => { s[key] = el.value; drawPreview(); });
    return el;
  };
  const field = (label, control, hint) => h('label', { class: 'f' }, label, control, hint && h('span', { class: 'hint' }, hint));
  const check = (key, label) => {
    const c = h('input', { type: 'checkbox', checked: !!s[key] });
    c.onchange = () => { s[key] = c.checked; };
    return h('label', { class: 'check' }, c, label);
  };
  const browse = (key, kind, target, labelFromPath = true) => h('button', {
    class: 'btn', type: 'button',
    onclick: async () => {
      try {
        const { path } = await api('POST', '/pick', { kind, initial: s[key] || null });
        if (!path) return;
        s[key] = path;
        target.value = path;
        if (labelFromPath && !s.label) {
          s.label = (path.split(/[\\/]/).filter(Boolean).pop() || '').replace(/\.(exe|lnk|bat|cmd)$/i, '').slice(0, 40);
          labelInput.value = s.label;
        }
        drawPreview();
      } catch (e) { toastError(e); }
    },
  }, 'Browse…');

  let labelInput;

  function drawForm() {
    form.replaceChildren();
    // Type picker (an installed app keeps its type; it's created from the app list).
    const types = Object.entries(TYPES).filter(([t]) => t !== 'app' || s.type === 'app');
    form.append(h('div', { class: 'types' }, types.map(([t, m]) => h('button', {
      class: 'chip', type: 'button', 'aria-pressed': String(s.type === t),
      onclick: () => {
        s.type = t;
        if (!editId && !pageTouched) addTo = defaultPageFor(t, data.config.pages);
        drawForm(); drawPreview();
        labelInput.focus();
      },
    }, icon(m.icon), m.label))));

    labelInput = input('label', { placeholder: 'What the tile says', maxlength: 40 });
    form.append(field('Label', labelInput));

    if (s.type === 'exe') {
      const p = input('path', { placeholder: 'C:\\Program Files\\App\\app.exe or any file' });
      form.append(field('Program or file', h('div', { class: 'c-row' }, h('div', { class: 'c-grow' }, p), browse('path', 'file', p)),
        'A program, a shortcut (.lnk), a script, or any document: it opens with its default app.'));
      form.append(field('Arguments', input('args', { placeholder: 'Optional, e.g. --new-window' })));
      const cwd = input('cwd', { placeholder: 'Optional; defaults to the program’s folder' });
      form.append(field('Start in', h('div', { class: 'c-row' }, h('div', { class: 'c-grow' }, cwd), browse('cwd', 'folder', cwd, false))));
      form.append(check('admin', 'Run as administrator (Windows asks for confirmation on the PC)'));
    } else if (s.type === 'app') {
      form.append(field('App', input('appid', { placeholder: 'App id' }), 'Started the way the Start menu starts it.'));
    } else if (s.type === 'folder') {
      const p = input('path', { placeholder: 'C:\\Users\\you\\Documents' });
      form.append(field('Folder', h('div', { class: 'c-row' }, h('div', { class: 'c-grow' }, p), browse('path', 'folder', p)),
        'Opens in File Explorer on the PC. %USERPROFILE% and other variables work.'));
    } else if (s.type === 'url') {
      form.append(field('Link', input('url', { placeholder: 'https://… or spotify:, ms-settings:, steam://…' }), 'Opens on the PC with its default app.'));
    } else if (s.type === 'shell') {
      form.append(field('Command', input('command', { rows: 3, placeholder: 'ipconfig /flushdns' }), 'Runs with cmd.exe.'));
      const cwd = input('cwd', { placeholder: 'Optional' });
      form.append(field('Start in', h('div', { class: 'c-row' }, h('div', { class: 'c-grow' }, cwd), browse('cwd', 'folder', cwd, false))));
      form.append(check('window', 'Show a console window (otherwise it runs hidden)'));
    } else if (s.type === 'keys') {
      const k = input('keys', { placeholder: 'ctrl+shift+m' });
      form.append(field('Keys', h('div', { class: 'c-row' }, h('div', { class: 'c-grow' }, k), recordButton(k, (v) => { s.keys = v; drawPreview(); })),
        'Click Record and press the shortcut. Or type it: ctrl, shift, alt, win + a key. Several in a row: “ctrl+k ctrl+c”.'));
    } else if (s.type === 'text') {
      form.append(field('Text', input('text', { rows: 5, placeholder: 'Typed into the focused window on the PC' })));
    } else if (s.type === 'steps') {
      form.append(field('Steps', stepsEditor()));
    }

    // Appearance
    const emoji = h('input', { class: 'field', style: { width: '90px' }, maxlength: 8, placeholder: '🙂', value: s.icon && !/[\\/.]/.test(s.icon) ? s.icon : '' });
    emoji.addEventListener('input', () => { s.icon = emoji.value.trim() || undefined; drawPreview(); });
    const iconFile = h('button', {
      class: 'btn', type: 'button',
      onclick: async () => {
        try {
          const { path } = await api('POST', '/pick', { kind: 'icon' });
          if (path) { s.icon = path; emoji.value = ''; drawPreview(); }
        } catch (e) { toastError(e); }
      },
    }, 'Icon file…');
    const auto = h('button', { class: 'btn', type: 'button', onclick: () => { delete s.icon; emoji.value = ''; drawPreview(); } }, 'Automatic');
    form.append(field('Icon', h('div', { class: 'c-row' }, emoji, iconFile, auto), 'An emoji, an .ico/.png/.exe file, or automatic (the program’s own icon).'));

    const sw = h('div', { class: 'c-swatches' });
    const drawSw = () => sw.replaceChildren(
      h('button', { type: 'button', class: 'swatch none', title: 'No colour', 'aria-pressed': String(!s.color), onclick: () => { delete s.color; drawSw(); drawPreview(); } }, '✕'),
      ...SWATCHES.map((c) => {
        const b = h('button', { type: 'button', class: 'swatch', title: c, 'aria-pressed': String(s.color === c), onclick: () => { s.color = c; drawSw(); drawPreview(); } });
        b.style.setProperty('--c', c);
        return b;
      }),
      (() => {
        const i = h('input', { type: 'color', value: s.color || '#0a84ff' });
        i.addEventListener('input', () => { s.color = i.value; drawPreview(); });
        return h('label', { class: 'swatch swatch-custom', title: 'Custom' }, i);
      })());
    drawSw();
    form.append(field('Tile colour', sw, 'Shown behind emoji and glyph icons.'));

    if (!editId) {
      const sel = h('select', null, h('option', { value: '' }, 'Don’t add a tile yet'),
        data.config.pages.map((p) => h('option', { value: p.id, selected: p.id === addTo }, `Add a tile to “${p.title}”`)));
      sel.onchange = () => { addTo = sel.value; pageTouched = true; };
      form.append(field('Page', sel));
    }

    const save = h('button', { class: 'btn primary', type: 'button' }, existing ? 'Save' : 'Create shortcut');
    save.onclick = async () => {
      save.disabled = true;
      try {
        const clean = Object.fromEntries(Object.entries(s).filter(([, v]) => v !== undefined && v !== '' && v !== false));
        await api('POST', '/actions', { id: editId, action: clean, add_to_page: addTo || null });
        forgetImages('/action-icon/');
        close();
        toast(existing ? 'Saved. The dock updates right away.' : 'Shortcut created.');
        await store.load();
      } catch (e) { toastError(e); save.disabled = false; }
    };
    form.append(h('div', { class: 'foot' }, h('button', { class: 'btn', type: 'button', onclick: close }, 'Cancel'), save));
  }

  function stepsEditor() {
    s.steps ||= [{ keys: 'win+r' }, { delay: 0.5 }, { text: 'notepad' }, { keys: 'enter' }];
    const wrap = h('div', { class: 'c-steps' });
    const draw = () => {
      wrap.replaceChildren(...s.steps.map((st, i) => {
        const kind = 'keys' in st ? 'keys' : 'text' in st ? 'text' : 'delay';
        const sel = h('select', null, ['keys', 'text', 'delay'].map((k) => h('option', { value: k, selected: k === kind }, { keys: 'Press keys', text: 'Type text', delay: 'Wait (s)' }[k])));
        const val = h('input', { class: 'field', value: st[kind] ?? '' });
        sel.onchange = () => { s.steps[i] = { [sel.value]: sel.value === 'delay' ? 0.5 : '' }; draw(); };
        val.oninput = () => { s.steps[i] = { [kind]: kind === 'delay' ? val.value : val.value }; };
        const rm = h('button', { class: 'btn icon', type: 'button', 'aria-label': 'Remove step', onclick: () => { s.steps.splice(i, 1); draw(); } }, icon('close'));
        return h('div', { class: 'c-step' }, sel, val, rm);
      }), h('div', null, h('button', { class: 'btn', type: 'button', onclick: () => { s.steps.push({ keys: '' }); draw(); } }, icon('plus'), 'Add step')));
    };
    draw();
    return wrap;
  }

  function drawPreview() {
    const sub = s.type === 'keys' ? s.keys : s.type === 'url' ? (s.url || '').replace(/^https?:\/\//, '').split('/')[0] : '';
    preview.replaceChildren(
      h('div', { class: 'c-muted' }, 'On the dock'),
      h('div', { class: 'tile' }, art(null, s, 'art', { unsaved: true }), h('span', { class: 'label' }, s.label || 'Label'), sub && h('span', { class: 'sub' }, sub)));
  }

  drawForm();
  drawPreview();
  setTimeout(() => labelInput?.focus(), 50);
}

// ---- keyboard recorder ---------------------------------------------------------
const CODE_NAMES = {
  Enter: 'enter', NumpadEnter: 'enter', Escape: 'esc', Tab: 'tab', Space: 'space', Backspace: 'backspace', Delete: 'delete',
  Insert: 'insert', Home: 'home', End: 'end', PageUp: 'pageup', PageDown: 'pagedown',
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', PrintScreen: 'printscreen', Pause: 'pause',
  CapsLock: 'capslock', ContextMenu: 'menu', Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Semicolon: ';',
  Quote: "'", Comma: ',', Period: '.', Slash: '/', Backslash: '\\', Backquote: '`',
  MediaPlayPause: 'media_play_pause', MediaTrackNext: 'media_next', MediaTrackPrevious: 'media_previous',
  AudioVolumeUp: 'volume_up', AudioVolumeDown: 'volume_down', AudioVolumeMute: 'volume_mute',
};

function codeName(code) {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^(Digit|Numpad)\d$/.test(code)) return code.slice(-1);
  if (/^F\d{1,2}$/.test(code)) return code.toLowerCase();
  return CODE_NAMES[code];
}

function recordButton(input, onValue) {
  const b = h('button', { class: 'btn', type: 'button' }, icon('keyboard'), 'Record');
  let on = false;
  const stop = () => {
    on = false;
    input.classList.remove('recording');
    b.lastChild.textContent = 'Record';
    window.removeEventListener('keydown', onKey, true);
  };
  const onKey = (e) => {
    if (['Control', 'Shift', 'Alt', 'Meta', 'OS'].includes(e.key)) return; // wait for the main key
    e.preventDefault();
    e.stopPropagation();
    const name = codeName(e.code);
    if (!name) { toast(`That key (${e.code}) can’t be recorded; type it instead.`); stop(); return; }
    const combo = [e.ctrlKey && 'ctrl', e.shiftKey && 'shift', e.altKey && 'alt', e.metaKey && 'win', name].filter(Boolean).join('+');
    input.value = combo;
    onValue(combo);
    stop();
  };
  b.onclick = () => {
    if (on) { stop(); return; }
    on = true;
    input.classList.add('recording');
    b.lastChild.textContent = 'Press keys…';
    window.addEventListener('keydown', onKey, true);
  };
  return b;
}

// ---- installed apps --------------------------------------------------------
function openAppPicker() {
  const data = store.data;
  const known = new Set(Object.values(data.config.actions).map((a) => (a.appid || a.path || '').toLowerCase()));
  let apps = null;
  let q = '';
  let page = defaultPageFor('app', data.config.pages);
  const search = h('input', { class: 'field', type: 'search', placeholder: 'Search apps' });
  const pageSel = h('select', null, h('option', { value: '' }, 'Don’t add tiles'),
    data.config.pages.map((p) => h('option', { value: p.id, selected: p.id === page }, `Add tiles to “${p.title}”`)));
  pageSel.onchange = () => { page = pageSel.value; };
  const list = h('div', { class: 'c-applist' }, h('div', { class: 'c-muted' }, 'Reading the Start menu…'));

  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      io.unobserve(e.target);
      const p = e.target.dataset.icon;
      apiImage(`/icon?path=${encodeURIComponent(p)}`).then((u) => { if (u) e.target.replaceChildren(h('img', { src: u, alt: '' })); });
    }
  });

  const draw = () => {
    if (!apps) return;
    const rows = apps.filter((a) => !q || a.name.toLowerCase().includes(q));
    list.replaceChildren(...rows.map((a) => {
      const ico = h('span', { class: 'ico', dataset: a.icon ? { icon: a.icon } : {} }, icon('app'));
      if (a.icon) io.observe(ico);
      const added = known.has(a.appid.toLowerCase()) || (a.path && known.has(a.path.toLowerCase()));
      const btn = h('button', { class: `btn${added ? '' : ' primary'}`, disabled: added }, added ? 'Added' : 'Add');
      btn.onclick = async () => {
        btn.disabled = true;
        try {
          await api('POST', '/actions', { action: { type: 'app', label: a.name.slice(0, 40), appid: a.appid, ...(a.icon ? { icon: a.icon } : {}) }, add_to_page: page || null });
          known.add(a.appid.toLowerCase());
          btn.textContent = 'Added';
          btn.classList.remove('primary');
          store.load();
        } catch (e) { toastError(e); btn.disabled = false; }
      };
      return h('div', { class: 'c-app' }, ico, h('span', { class: 'name', title: a.name }, a.name), btn);
    }));
    if (!rows.length) list.replaceChildren(h('div', { class: 'c-muted' }, 'No apps match.'));
  };
  search.addEventListener('input', () => { q = search.value.toLowerCase(); draw(); });

  const { dlg } = sheet('Add installed apps', (body) => body.append(h('div', { class: 'c-row' }, h('div', { class: 'c-grow' }, search), pageSel), list),
    { onClose: () => io.disconnect() });
  dlg.classList.add('c-apps');
  search.focus();
  api('GET', '/apps').then((r) => { apps = r; draw(); }).catch((e) => list.replaceChildren(h('div', { class: 'c-muted' }, e.message)));
}
