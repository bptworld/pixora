from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiohttp import web


class StatusServer:
    def __init__(
        self,
        host: str,
        port: int,
        health_provider: Callable[[], dict[str, Any]],
        entities_provider: Callable[[], dict[str, Any]],
    ) -> None:
        self._host = host
        self._port = port
        self._health_provider = health_provider
        self._entities_provider = entities_provider
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/entities", self._entities)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _health(self, _request: web.Request) -> web.Response:
        return web.json_response(self._health_provider())

    async def _entities(self, _request: web.Request) -> web.Response:
        return web.json_response(self._entities_provider())
