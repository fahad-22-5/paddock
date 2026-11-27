// Now playing (via the computer's media controls): art, title, artist, seek, transport.
import { h, css, icon, onTap, fmtTime } from '../core/dom.js';
import { sheet } from '../core/ui.js';
import { Slider } from '../ui/slider.js';

css(`
.w-media { display: flex; align-items: center; gap: clamp(14px, 4cqi, 28px); padding: clamp(14px, 4cqmin, 26px); isolation: isolate; }
.w-media .bg { position: absolute; inset: -30%; z-index: -1; background-size: cover; background-position: center; filter: blur(50px) saturate(1.6); opacity: 0; transition: opacity 800ms; }
.w-media .bg.on { opacity: .45; }
.w-media .art { height: min(100%, 46cqi); aspect-ratio: 1; flex: none; border-radius: clamp(10px, 4cqmin, 20px); background: var(--surface-2) center / cover no-repeat;
  box-shadow: 0 14px 40px rgb(0 0 0 / .45); display: grid; place-items: center; color: var(--text-3); transition: background-image 300ms; }
.w-media .art svg.i { width: 40%; height: 40%; }
.w-media .art.has { color: transparent; }
.w-media .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.w-media .src { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; min-height: 32px; padding: 0 12px; border-radius: 999px;
  border: 0; background: rgb(255 255 255 / .1); color: var(--text-2); font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.w-media .src svg.i { width: 14px; height: 14px; }
.w-media .title { font-size: clamp(18px, 7cqmin, 30px); font-weight: 700; letter-spacing: -0.015em; line-height: 1.15;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.w-media .artist { font-size: clamp(14px, 4.5cqmin, 19px); color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.w-media .album { font-size: 14px; color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.w-media .seek { display: flex; flex-direction: column; gap: 10px; margin-top: clamp(8px, 3cqb, 18px); }
.w-media .seek .slider { flex: none; }
.w-media .times { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-3); font-variant-numeric: tabular-nums; margin-top: 4px; }
.w-media .ctrls { display: flex; align-items: center; justify-content: center; gap: clamp(8px, 4cqi, 26px); margin-top: clamp(6px, 2cqb, 14px); }
.w-media .ctrls .btn { background: transparent; border-radius: 50%; width: 64px; height: 64px; }
.w-media .ctrls .btn svg.i { width: 30px; height: 30px; }
.w-media .ctrls .play { width: 76px; height: 76px; background: var(--text); color: #000; }
.w-media .ctrls .play svg.i { width: 34px; height: 34px; }
.w-media .ctrls .play:active { background: #ccc; }
.w-media .idle { color: var(--text-3); }
@container card (aspect-ratio < 1.15) {
  .w-media { flex-direction: column; justify-content: center; text-align: center; }
  .w-media .art { height: auto; width: min(70%, 48cqb); }
  .w-media .info { width: 100%; flex: none; }
  .w-media .src { align-self: center; }
}
@container card (height < 260px) and (aspect-ratio >= 1.15) {
  .w-media .album, .w-media .times { display: none; }
  .w-media .ctrls { justify-content: flex-start; gap: 4px; margin-top: 4px; }
  .w-media .ctrls .btn { width: 56px; height: 56px; }
  .w-media .ctrls .play { width: 60px; height: 60px; }
  .w-media .seek { margin-top: 8px; }
}
@container card (width < 340px) { .w-media .art { display: none; } }
`);

export default {
  type: 'media',
  title: 'Now playing',
  description: 'Media controls for Spotify, browsers and more',
  icon: 'music',
  sizes: [[4, 2], [5, 2], [3, 2], [5, 4], [4, 3], [3, 4], [6, 2], [8, 2]],
  mount(card, ctx) {
    const bg = h('div', { class: 'bg' });
    const art = h('div', { class: 'art' }, icon('music'));
    const src = h('button', { class: 'src' }, icon('music'), h('span', null, 'Nothing playing'));
    const title = h('div', { class: 'title idle' }, 'Nothing playing');
    const artist = h('div', { class: 'artist' }, 'Start music or a video on the PC');
    const album = h('div', { class: 'album' });
    const tNow = h('span', null, '0:00'), tEnd = h('span', null, '0:00');
    const seek = new Slider({ thin: true, ariaLabel: 'Seek', onChange: (v) => {
      if (!state?.duration) return;
      basePos = v * state.duration; baseAt = performance.now();
      ctx.call('media', 'seek', { position: v * state.duration }).catch(ctx.toastError);
    } });
    const prev = h('button', { class: 'btn icon', 'aria-label': 'Previous' }, icon('prev'));
    const play = h('button', { class: 'btn icon play', 'aria-label': 'Play or pause' }, icon('play'));
    const next = h('button', { class: 'btn icon', 'aria-label': 'Next' }, icon('next'));

    card.append(bg, art, h('div', { class: 'info' }, src, title, artist, album,
      h('div', { class: 'seek' }, seek.el, h('div', { class: 'times' }, tNow, tEnd)),
      h('div', { class: 'ctrls' }, prev, play, next)));

    let state = null, basePos = 0, baseAt = 0, raf = 0, lastIcon = '';
    const cmd = (act) => ctx.call('media', act).catch(ctx.toastError);
    onTap(prev, () => cmd('prev'));
    onTap(next, () => cmd('next'));
    onTap(play, () => {
      // Optimistic toggle so the button feels instant.
      if (state) { state.status = state.status === 'playing' ? 'paused' : 'playing'; basePos = curPos(); baseAt = performance.now(); render(); }
      cmd('play_pause');
    });
    onTap(src, () => {
      if (!state?.sessions?.length) return;
      sheet('Media source', (body, close) => {
        const row = (label, id) => {
          const b = h('button', { class: 'list-row' }, icon('music'), h('div', { class: 'grow' }, label),
            (id === null ? !selected : selected === id) ? icon('check') : '');
          onTap(b, () => { selected = id; ctx.saveOptions({ source: id }); ctx.call('media', 'select', { id }); close(); });
          return b;
        };
        body.append(h('div', { class: 'list' }, row('Automatic', null), state.sessions.map((s) => row(s.name, s.id))));
      });
    });
    let selected = ctx.item.options?.source || null;
    // Re-apply a pinned source after every (re)connect; the PC forgets it when restarted.
    const applySource = () => { if (selected) ctx.call('media', 'select', { id: selected }).catch(() => {}); };
    ctx.conn.addEventListener('hello', applySource);
    if (ctx.conn.state === 'open') applySource();

    const curPos = () => {
      if (!state) return 0;
      const p = state.status === 'playing' ? basePos + (performance.now() - baseAt) / 1000 : basePos;
      return state.duration ? Math.min(p, state.duration) : p;
    };

    const tick = () => {
      raf = 0;
      if (!state?.active) return;
      const p = curPos();
      if (state.duration) seek.set(p / state.duration);
      tNow.textContent = fmtTime(p);
      if (state.status === 'playing' && !document.hidden) raf = requestAnimationFrame(tick);
    };

    function render() {
      const s = state;
      const active = s?.active;
      src.lastChild.textContent = active ? s.app_name : (s?.sessions?.length ? 'Choose source' : 'Nothing playing');
      title.textContent = active ? (s.title || 'Unknown title') : 'Nothing playing';
      title.classList.toggle('idle', !active);
      artist.textContent = active ? s.artist : 'Start music or a video on the PC';
      album.textContent = active ? s.album : '';
      tEnd.textContent = active && s.duration ? fmtTime(s.duration) : '';
      seek.setDisabled(!active || !s.can?.seek);
      for (const [b, k] of [[prev, 'prev'], [next, 'next'], [play, 'play_pause']]) b.disabled = !active || !s.can?.[k];
      const ic = active && s.status === 'playing' ? 'pause' : 'play';
      if (ic !== lastIcon) { play.replaceChildren(icon(ic)); lastIcon = ic; }
      if (!raf) raf = requestAnimationFrame(tick);
    }

    ctx.subscribe('media', (s) => {
      state = s;
      basePos = s.position || 0;
      baseAt = performance.now();
      render();
    });
    ctx.subscribe('media_art', (a) => {
      const url = a?.src ? `url("${a.src}")` : '';
      art.style.backgroundImage = url;
      bg.style.backgroundImage = url;
      art.classList.toggle('has', !!url);
      bg.classList.toggle('on', !!url);
    });
    const onVis = () => { if (!document.hidden && !raf) raf = requestAnimationFrame(tick); };
    document.addEventListener('visibilitychange', onVis);

    return {
      destroy() {
        cancelAnimationFrame(raf);
        document.removeEventListener('visibilitychange', onVis);
        ctx.conn.removeEventListener('hello', applySource);
      },
      update(item) { selected = item.options?.source || null; },
    };
  },
};
