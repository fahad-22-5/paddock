"""The FastAPI application: pairing, the WebSocket endpoint, module routes and the web UI."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .hub import Client
from .modules.base import ActionError, Context, Module
from .netutil import is_private_address
from .paths import WEB_DIR

log = logging.getLogger("paddock.app")


class PrivateNetworkOnly:
    """Reject any HTTP or WebSocket connection that doesn't come from a private address."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            host = (scope.get("client") or ("", 0))[0]
            if not is_private_address(host):
                log.warning("Refused connection from non-private address %s", host)
                if scope["type"] == "http":
                    await JSONResponse({"error": "LAN only"}, status_code=403)(scope, receive, send)
                else:
                    await send({"type": "websocket.close", "code": 1008})
                return
        await self.app(scope, receive, send)


class NoStaleCache:
    """Make Safari revalidate the UI files on every launch so updates show up at once.
    (Responses still carry ETags, so unchanged files come back as cheap 304s.)"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                headers.append((b"cache-control", b"no-cache"))
                if scope["path"] == "/sw.js":
                    headers.append((b"service-worker-allowed", b"/"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class PairRequest(BaseModel):
    code: str = Field(max_length=12)
    name: str = Field(default="Dock", max_length=60)
    replace_token: str | None = Field(default=None, max_length=200)  # set when this device re-pairs


def create_app(ctx: Context, modules: list[Module]) -> FastAPI:
    by_name = {m.name: m for m in modules}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for m in modules:
            try:
                await m.start()
            except Exception:
                log.exception("Module %s failed to start; its features are unavailable", m.name)
        yield
        for m in modules:
            await m.stop()

    app = FastAPI(title="PadDock", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(NoStaleCache)
    app.add_middleware(PrivateNetworkOnly)
    app.state.ctx = ctx

    # ---- HTTP auth -----------------------------------------------------
    def require_device(request: Request):
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
        dev = ctx.devices.verify(token)
        if not dev:
            raise HTTPException(status_code=401, detail="Not paired")
        return dev

    app.state.require_device = require_device

    @app.get("/api/health")
    async def health():
        return {"ok": True, "app": "PadDock", "version": __version__}

    @app.post("/api/pair")
    async def pair(body: PairRequest, request: Request):
        token, error = ctx.pairing.attempt(request.client.host, body.code, body.name, body.replace_token)
        if error:
            raise HTTPException(status_code=403, detail=error)
        return {"token": token}

    @app.get("/api/me")
    async def me(dev=Depends(require_device)):
        return dev.public()

    for m in modules:
        r = m.router()
        if r is not None:
            app.include_router(r, prefix=f"/api/{m.name}", dependencies=[Depends(require_device)])

    # ---- WebSocket -----------------------------------------------------
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
        except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
            await ws.close(code=4400)
            return
        token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
        dev = ctx.devices.verify(token)
        if not dev:
            await ws.send_json({"type": "auth_failed"})
            await ws.close(code=4401)
            return

        client = Client(ws, dev)
        ctx.hub.add(client)
        sender = asyncio.create_task(client.sender())
        client.send({"type": "hello", "device": dev.public(), "server": ctx.info})
        ctx.hub.subscribe(client, ["config"])
        try:
            while not client.closed:
                text = await ws.receive_text()
                try:
                    msg = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                # Every message must carry the token it authenticated with.
                if not isinstance(msg.get("t"), str) or ctx.devices.verify(msg["t"]) is not dev:
                    client.send({"type": "auth_failed"})
                    client.close(4401)
                    break
                ctx.devices.touch(dev)
                kind = msg.get("type")
                if kind == "ping":
                    client.send({"type": "pong"})
                elif kind == "sub":
                    ctx.hub.subscribe(client, list(msg.get("topics") or []))
                elif kind == "unsub":
                    ctx.hub.unsubscribe(client, list(msg.get("topics") or []))
                elif kind == "call":
                    await _dispatch(client, msg)
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("WebSocket error")
        finally:
            ctx.hub.remove(client)
            if not sender.done():
                # Let a pending close (e.g. revoked token) flush, otherwise stop.
                if getattr(client, "close_code", None):
                    try:
                        await asyncio.wait_for(sender, timeout=2)
                    except Exception:
                        pass
                sender.cancel()

    async def _dispatch(client: Client, msg: dict) -> None:
        call_id = msg.get("id")
        mod = by_name.get(msg.get("mod"))
        fn = mod.actions.get(msg.get("act")) if mod else None
        args = msg.get("args") if isinstance(msg.get("args"), dict) else {}

        def reply(ok: bool, data=None, error: str | None = None):
            if call_id is not None:
                client.send({"type": "result", "id": call_id, "ok": ok, **({"data": data} if ok else {"error": error})})

        if fn is None:
            reply(False, error=f"Unknown action {msg.get('mod')}.{msg.get('act')}")
            return

        if not inspect.iscoroutinefunction(fn):
            # Fast, synchronous handlers (touchpad moves) run inline to keep their order.
            try:
                reply(True, fn(args, client))
            except ActionError as e:
                reply(False, error=str(e))
            except Exception as e:
                log.exception("%s.%s failed", mod.name, msg.get("act"))
                reply(False, error=f"Failed: {e}")
            return

        async def run():
            try:
                reply(True, await fn(args, client))
            except ActionError as e:
                reply(False, error=str(e))
            except Exception as e:
                log.exception("%s.%s failed", mod.name, msg.get("act"))
                reply(False, error=f"Failed: {e}")

        asyncio.create_task(run())

    # ---- web UI (public static files; all data needs a token) -----------
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
