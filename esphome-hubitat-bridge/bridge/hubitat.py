from __future__ import annotations

from typing import Any
from urllib.parse import quote

import aiohttp

from .config import HubitatCommand, HubitatConfig


class HubitatClient:
    def __init__(self, config: HubitatConfig) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self._config.request_timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()

    async def get_device(self, device_id: str) -> dict[str, Any]:
        url = self._url(f"devices/{quote(str(device_id), safe='')}")
        async with self._request("GET", url) as response:
            return await response.json()

    async def send_command(
        self,
        device_id: str,
        command: HubitatCommand,
        value: Any = None,
    ) -> dict[str, Any] | None:
        parts = [
            "devices",
            quote(str(device_id), safe=""),
            quote(command.command, safe=""),
        ]
        for arg in command.args:
            rendered = render_template(arg, value)
            parts.append(quote(rendered, safe=""))

        url = self._url("/".join(parts))
        async with self._request("GET", url) as response:
            if response.content_type == "application/json":
                return await response.json()
            await response.text()
            return None

    def _url(self, path: str) -> str:
        base = self._config.base_url.rstrip("/")
        app_id = quote(str(self._config.app_id), safe="")
        token = quote(str(self._config.access_token), safe="")
        return f"{base}/apps/api/{app_id}/{path}?access_token={token}"

    def _request(self, method: str, url: str) -> aiohttp.ClientResponse:
        if self._session is None:
            raise RuntimeError("Hubitat client is not started.")
        return self._session.request(method, url)


def render_template(template: str, value: Any) -> str:
    if value is None:
        rendered = ""
    elif isinstance(value, bool):
        rendered = "true" if value else "false"
    else:
        rendered = str(value)
    return template.replace("{value}", rendered)


def get_attribute(device: dict[str, Any], attribute_name: str) -> Any:
    attributes = device.get("attributes") or []
    for attribute in attributes:
        if attribute.get("name") == attribute_name:
            return attribute.get("currentValue")
    return None
