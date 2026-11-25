"""A tiny plain-HTTP helper site (default port 8766).

The device can't open the HTTPS app until it trusts PadDock's certificate, so this page
explains the steps and serves the certificate. It also hosts the "Show pairing code"
page opened from the tray icon, which only answers requests from this PC itself.
"""
from __future__ import annotations

import html
import io
from typing import Callable

import qrcode
import qrcode.image.svg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import certs
from .app import NoStaleCache, PrivateNetworkOnly
from .paths import WEB_DIR

PAGE_CSS = """
:root{color-scheme:dark;--accent:#0a84ff}
*{box-sizing:border-box}
body{margin:0;font:17px/1.5 -apple-system,system-ui,"Segoe UI",sans-serif;background:#0b0d12;color:#e8eaf0;
  padding:max(24px,env(safe-area-inset-top)) max(20px,env(safe-area-inset-right)) 40px max(20px,env(safe-area-inset-left))}
main{max-width:720px;margin:0 auto}
h1{font-size:34px;margin:8px 0 4px;letter-spacing:-.02em} h2{font-size:21px;margin:0 0 6px}
p{margin:6px 0;color:#b4b9c6} code,b{color:#fff}
.card{background:#161a22;border:1px solid #262c38;border-radius:20px;padding:20px 22px;margin:16px 0}
.n{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:50%;background:var(--accent);color:#fff;font-weight:700;margin-right:10px}
a.btn{display:inline-flex;align-items:center;justify-content:center;min-height:56px;padding:0 26px;border-radius:16px;
  background:var(--accent);color:#fff;font-weight:600;text-decoration:none;margin-top:10px}
ol{margin:8px 0 0;padding-left:22px;color:#b4b9c6} li{margin:4px 0}
.status{font-weight:600} .ok{color:#30d158} .bad{color:#ff9f0a}
.code{font:700 64px/1 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.12em;color:#fff;margin:10px 0}
.qr{background:#fff;border-radius:16px;padding:14px;width:260px;height:260px}
.qr svg{width:100%;height:100%}
"""


def _qr_svg(data: str) -> str:
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, border=1)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    return svg[svg.index("<svg"):]


class LoopbackOnlyPaths:
    """The PC console (/console) and its UI files (/ui) only answer this PC."""

    PREFIXES = ("/console", "/ui")

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(self.PREFIXES):
            host = (scope.get("client") or ("", 0))[0]
            if host not in ("127.0.0.1", "::1"):
                await PlainTextResponse("The PadDock console only works on the PC itself.", status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_setup_app(get_state: Callable[[], dict], dock=None) -> FastAPI:
    """get_state() -> {"app_url", "setup_url", "https", "code", "host"}"""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(LoopbackOnlyPaths)
    app.add_middleware(PrivateNetworkOnly)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        s = get_state()
        url = html.escape(s["app_url"])
        if not s["https"]:
            cert_steps = "<div class='card'><p>HTTPS is turned off in config.json, so you can skip the certificate. " \
                         "Keep-awake and clipboard features won't work without it.</p></div>"
        else:
            cert_steps = f"""
<div class="card"><h2><span class="n">1</span>Install the certificate</h2>
<p>This lets Safari trust the PadDock server on <b>{html.escape(s['host'])}</b>. It only works for this PC.</p>
<a class="btn" href="/paddock-ca.crt">Download certificate</a>
<p><b>iPhone / iPad:</b></p>
<ol><li>Tap <b>Allow</b>, then <b>Close</b>.</li>
<li>Open <b>Settings → General → VPN &amp; Device Management</b>, tap <b>PadDock Local CA</b>, then <b>Install</b>.</li>
<li>Open <b>Settings → General → About → Certificate Trust Settings</b> and switch on <b>PadDock Local CA</b>.</li></ol>
<p><b>Android:</b> open <b>Settings</b>, search for <b>CA certificate</b> (usually under Security → More security settings →
Encryption &amp; credentials → Install a certificate), choose <b>CA certificate</b> and pick the downloaded <b>PadDock-CA.crt</b>.</p></div>
<div class="card"><h2><span class="n">2</span>Check</h2>
<p class="status" id="st">Checking the secure connection…</p></div>"""
        body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>PadDock setup</title><style>{PAGE_CSS}</style></head><body><main>
<h1>Set up PadDock</h1><p>Three steps, once. Keep this page open on your device.</p>
{cert_steps}
<div class="card"><h2><span class="n">{3 if s['https'] else 1}</span>Open PadDock and add it to your Home Screen</h2>
<a class="btn" href="{url}" id="open">Open {url}</a>
{f'<p id="alt" style="display:none">The name <b>{html.escape(s["local_name"])}</b> isn’t found on this network. Use the IP address instead: <a href="{html.escape(s["app_url_ip"])}" style="color:#64d2ff">{html.escape(s["app_url_ip"])}</a></p>' if s.get('local_name') else ''}
<ol><li>Add it to your Home Screen: in Safari tap <b>Share → Add to Home Screen</b>; in Chrome on Android tap <b>⋮ → Add to Home screen</b>. Then open PadDock from there.</li>
<li>Enter the 6-digit pairing code shown on the PC.</li></ol>
<p>Pair from the Home Screen app, not the Safari tab: iPhone and iPad keep their storage separate.</p></div>
</main><script>
const st=document.getElementById('st');
const IP_URL={s['app_url_ip']!r}, NAME_URL={s['app_url']!r};
const ping=(u)=>fetch(u+'api/health',{{mode:'no-cors',cache:'no-store'}}).then(()=>true,()=>false);
async function check(){{
  // Trust check by IP (doesn't depend on the .local name).
  if(st){{
    if(await ping(IP_URL)){{ st.textContent='✓ Secure connection works. Go to step 3.'; st.className='status ok'; }}
    else {{ st.textContent='Not trusted yet. Finish step 1, then come back here.'; st.className='status bad'; setTimeout(check,3000); return; }}
  }}
  // If the friendly name doesn't resolve on this network, offer the IP address.
  if(NAME_URL!==IP_URL && !(await ping(NAME_URL))){{
    const alt=document.getElementById('alt'); if(alt) alt.style.display='block';
    const o=document.getElementById('open'); if(o){{ o.href=IP_URL; o.textContent='Open '+IP_URL; }}
  }}
}}
check(); document.addEventListener('visibilitychange',()=>{{ if(!document.hidden) check(); }});
</script></body></html>"""
        return HTMLResponse(body, headers={"cache-control": "no-store"})

    @app.get("/paddock-ca.crt")
    async def ca():
        return Response(
            certs.ca_cert_der(),
            media_type="application/x-x509-ca-cert",
            headers={"content-disposition": 'attachment; filename="PadDock-CA.crt"'},
        )

    @app.get("/local/pairing", response_class=HTMLResponse)
    async def local_pairing(request: Request):
        if request.client.host not in ("127.0.0.1", "::1"):
            return PlainTextResponse("Only available on the PC itself.", status_code=403)
        s = get_state()
        body = f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="5">
<title>PadDock pairing code</title><style>{PAGE_CSS} main{{text-align:center}} .qr{{margin:16px auto}}</style></head>
<body><main><h1>PadDock pairing code</h1><div class="code">{s['code'][:3]} {s['code'][3:]}</div>
<p>Enter this code on your device. It changes after each successful pairing.</p>
<div class="qr">{_qr_svg(s['setup_url'])}</div>
<p>Scan with your device’s camera to open the setup page:<br><b>{html.escape(s['setup_url'])}</b></p>
<p>The app itself: <b>{html.escape(s['app_url'])}</b></p></main></body></html>"""
        return HTMLResponse(body, headers={"cache-control": "no-store"})

    # ---- PC management console (loopback only; its API needs the console key) ----
    if dock is not None:
        from .console import create_console_router

        app.include_router(create_console_router(dock))
        app.add_middleware(NoStaleCache)

        @app.get("/console")
        async def console_redirect():
            return RedirectResponse("/console/")

        app.mount("/console", StaticFiles(directory=WEB_DIR / "console", html=True), name="console")
        app.mount("/ui", StaticFiles(directory=WEB_DIR), name="ui")

    return app
