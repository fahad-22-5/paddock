"""Weather from Open-Meteo (free, no API key). The PC fetches it every 15 minutes while
the clock widget is on screen, and caches it so every device shares one request."""
from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import urllib.request

from .base import ActionError, Module, action

FORECAST = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
REFRESH = 15 * 60


def _get_json(url: str, params: dict) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "PadDock/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class WeatherModule(Module):
    name = "weather"

    async def start(self) -> None:
        self._refresh = asyncio.Event()
        self.config.on_change(lambda _: self._refresh.set())
        self.spawn(self._loop())

    async def _loop(self) -> None:
        last_key = None
        last_at = 0.0
        while True:
            await self.hub.wait_for_subscribers("weather")
            w = self.config.get("weather") or {}
            key = (w.get("latitude"), w.get("longitude"), w.get("units"), w.get("enabled", True))
            if key != last_key or time.time() - last_at > REFRESH:
                self.hub.publish("weather", await self._fetch(w))
                last_key, last_at = key, time.time()
            self._refresh.clear()
            try:
                await asyncio.wait_for(self._refresh.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    async def _fetch(self, w: dict) -> dict:
        if not w.get("enabled", True):
            return {"disabled": True}
        if w.get("latitude") is None or w.get("longitude") is None:
            return {"error": "Set your city in Settings ⚙"}
        units = "fahrenheit" if w.get("units") == "fahrenheit" else "celsius"
        params = {
            "latitude": w["latitude"], "longitude": w["longitude"], "timezone": "auto", "forecast_days": 5,
            "current": "temperature_2m,apparent_temperature,weather_code,is_day,relative_humidity_2m,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "temperature_unit": units,
        }
        try:
            d = await asyncio.to_thread(_get_json, FORECAST, params)
        except Exception as e:
            self.log.warning("Weather fetch failed: %s", e)
            return {"error": "Weather unavailable", "name": w.get("name")}
        c, daily = d.get("current", {}), d.get("daily", {})
        days = [
            {"date": day, "code": code, "max": hi, "min": lo}
            for day, code, hi, lo in zip(daily.get("time", []), daily.get("weather_code", []),
                                         daily.get("temperature_2m_max", []), daily.get("temperature_2m_min", []))
        ]
        return {
            "name": w.get("name") or "", "units": units, "fetched": time.time(),
            "current": {
                "temp": c.get("temperature_2m"), "feels": c.get("apparent_temperature"), "code": c.get("weather_code", 0),
                "is_day": bool(c.get("is_day", 1)), "humidity": c.get("relative_humidity_2m"), "wind": c.get("wind_speed_10m"),
            },
            "daily": days,
        }

    @action
    async def set_location(self, args, client):
        query = str(args.get("query", "")).strip()[:80]
        if not query:
            raise ActionError("Type a city name.")
        try:
            res = await asyncio.to_thread(_get_json, GEOCODE, {"name": query, "count": 1, "language": "en", "format": "json"})
        except Exception:
            raise ActionError("Couldn't reach Open-Meteo. Is the PC online?")
        hits = res.get("results") or []
        if not hits:
            raise ActionError(f"No place called “{query}” found.")
        h = hits[0]
        name = ", ".join(x for x in (h.get("name"), h.get("admin1"), h.get("country_code")) if x)

        def mutate(d):
            d.setdefault("weather", {}).update(name=name, latitude=h["latitude"], longitude=h["longitude"], enabled=True)

        self.config.update(mutate)
        return {"name": name}

    @action
    async def set_units(self, args, client):
        units = args.get("units")
        if units not in ("celsius", "fahrenheit"):
            raise ActionError("Units must be celsius or fahrenheit.")
        self.config.update(lambda d: d.setdefault("weather", {}).__setitem__("units", units))
        return True
