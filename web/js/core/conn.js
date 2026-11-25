// WebSocket connection to the PC: auth, topic subscriptions, calls with replies,
// heartbeat, and automatic reconnect when the PC sleeps or Wi-Fi drops.
//
// Events: 'state' (detail: 'connecting' | 'open' | 'down' | 'unauthorized'), 'hello'.

const BACKOFF = [400, 1000, 2000, 3000, 5000];
const PING_EVERY = 5000;
const DEAD_AFTER = 12000;

export class Connection extends EventTarget {
  constructor(token) {
    super();
    this.token = token;
    this.ws = null;
    this.state = 'connecting';
    this.attempt = 0;
    this.nextRetryAt = 0;
    this.listeners = new Map(); // topic -> Set<fn>
    this.last = new Map(); // topic -> last data (for late subscribers)
    this.pending = new Map(); // id -> {resolve, reject, timer}
    this.seq = 0;
    this.lastMsgAt = 0;
    this.server = null;
    this._retryTimer = null;
    this._pingTimer = null;

    const wake = () => this.checkNow();
    document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });
    window.addEventListener('online', wake);
    window.addEventListener('pageshow', wake);
    window.addEventListener('focus', wake);
  }

  // ---- lifecycle ----------------------------------------------------
  connect() {
    clearTimeout(this._retryTimer);
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;
    this._setState(this.attempt === 0 ? 'connecting' : this.state === 'down' ? 'down' : 'connecting');
    const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
    let ws;
    try { ws = new WebSocket(url); } catch { this._scheduleRetry(); return; }
    this.ws = ws;
    const opened = setTimeout(() => { if (ws.readyState !== WebSocket.OPEN) ws.close(); }, 6000);

    ws.onopen = () => {
      clearTimeout(opened);
      ws.send(JSON.stringify({ type: 'auth', token: this.token }));
    };
    ws.onmessage = (e) => this._onMessage(e.data);
    ws.onclose = (e) => { clearTimeout(opened); this._closed(ws, e.code); };
    ws.onerror = () => {}; // onclose follows
  }

  _closed(ws, code) {
    if (this.ws !== ws) return; // an old socket we already gave up on
    this.ws = null;
    clearInterval(this._pingTimer);
    for (const [, p] of this.pending) { clearTimeout(p.timer); p.reject(new Error('Disconnected')); }
    this.pending.clear();
    if (code === 4401) { this._setState('unauthorized'); return; }
    this._scheduleRetry();
  }

  _scheduleRetry() {
    if (this.state === 'unauthorized') return;
    const delay = BACKOFF[Math.min(this.attempt, BACKOFF.length - 1)] + Math.random() * 300;
    this.attempt++;
    // Show "Disconnected" after the first quick retry fails, not on every blip.
    this._setState(this.attempt > 1 ? 'down' : 'connecting');
    this.nextRetryAt = Date.now() + delay;
    this.dispatchEvent(new CustomEvent('retry', { detail: this.nextRetryAt }));
    this._retryTimer = setTimeout(() => this.connect(), delay);
  }

  /** Reconnect immediately (Retry button, app came back to the foreground). */
  retryNow() {
    this.attempt = Math.min(this.attempt, 1);
    clearTimeout(this._retryTimer);
    const ws = this.ws;
    if (ws) { this.ws = null; clearInterval(this._pingTimer); try { ws.close(); } catch {} }
    this.connect();
  }

  /** After the app was in the background the socket may be silently dead: verify quickly. */
  checkNow() {
    if (this.state === 'unauthorized') return;
    if (!this.ws) { this.retryNow(); return; }
    if (this.state === 'open') {
      this._send({ type: 'ping' });
      const sent = Date.now();
      setTimeout(() => { if (this.lastMsgAt < sent && this.ws) this.retryNow(); }, 2500);
    }
  }

  _setState(s) {
    if (this.state === s) return;
    this.state = s;
    document.documentElement.dataset.conn = s;
    this.dispatchEvent(new CustomEvent('state', { detail: s }));
  }

  // ---- messages -----------------------------------------------------
  _onMessage(text) {
    this.lastMsgAt = Date.now();
    let msg;
    try { msg = JSON.parse(text); } catch { return; }
    switch (msg.type) {
      case 'hello':
        this.attempt = 0;
        this.server = msg.server;
        this.device = msg.device;
        this._setState('open');
        const topics = [...this.listeners.keys()].filter((t) => this.listeners.get(t).size);
        if (topics.length) this._send({ type: 'sub', topics });
        clearInterval(this._pingTimer);
        this._pingTimer = setInterval(() => this._heartbeat(), PING_EVERY);
        this.dispatchEvent(new CustomEvent('hello', { detail: msg }));
        break;
      case 'event': {
        this.last.set(msg.topic, msg.data);
        const set = this.listeners.get(msg.topic);
        if (set) for (const fn of [...set]) { try { fn(msg.data); } catch (err) { console.error(err); } }
        break;
      }
      case 'result': {
        const p = this.pending.get(msg.id);
        if (!p) break;
        this.pending.delete(msg.id);
        clearTimeout(p.timer);
        msg.ok ? p.resolve(msg.data) : p.reject(new Error(msg.error || 'Failed'));
        break;
      }
      case 'auth_failed':
        this._setState('unauthorized');
        break;
    }
  }

  _heartbeat() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    if (Date.now() - this.lastMsgAt > DEAD_AFTER) {
      // PC asleep or network gone: TCP can hang for minutes, so give up ourselves.
      const ws = this.ws;
      try { ws.close(); } catch {}
      this._closed(ws, 1006);
      return;
    }
    this._send({ type: 'ping' });
  }

  _send(msg) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify({ ...msg, t: this.token }));
    return true;
  }

  // ---- public API ---------------------------------------------------
  /** Listen to a topic. Returns an unsubscribe function. */
  subscribe(topic, fn) {
    let set = this.listeners.get(topic);
    if (!set) this.listeners.set(topic, (set = new Set()));
    const first = set.size === 0;
    set.add(fn);
    if (first && this.state === 'open') this._send({ type: 'sub', topics: [topic] });
    else if (this.last.has(topic)) queueMicrotask(() => set.has(fn) && fn(this.last.get(topic)));
    return () => {
      set.delete(fn);
      if (!set.size && topic !== 'config') this._send({ type: 'unsub', topics: [topic] });
    };
  }

  /** Call a server action and wait for its result. */
  call(mod, act, args = {}, timeout = 15000) {
    return new Promise((resolve, reject) => {
      const id = ++this.seq;
      if (!this._send({ type: 'call', id, mod, act, args })) { reject(new Error('Not connected to the PC')); return; }
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('The PC took too long to answer')); }, timeout);
      this.pending.set(id, { resolve, reject, timer });
    });
  }

  /** Fire-and-forget call (no reply), for high-rate input like the touchpad. */
  fire(mod, act, args = {}) {
    return this._send({ type: 'call', mod, act, args });
  }
}
