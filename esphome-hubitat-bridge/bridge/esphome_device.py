from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aioesphomeapi import (
    APIClient,
    BinarySensorState,
    ButtonInfo,
    EntityInfo,
    EntityState,
    LightInfo,
    LightState,
    NumberInfo,
    NumberState,
    SelectInfo,
    SelectState,
    SensorState,
    SwitchInfo,
    SwitchState,
    TextSensorState,
)
from .config import ESPHomeDeviceConfig

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityRef:
    device_id: str
    entity_id: str
    key: int
    name: str
    platform: str


class ESPHomeDevice:
    def __init__(
        self,
        config: ESPHomeDeviceConfig,
        on_state: Callable[[str, str, Any], None],
        reconnect_seconds: float,
    ) -> None:
        self.config = config
        self._on_state = on_state
        self._reconnect_seconds = reconnect_seconds
        self._client: APIClient | None = None
        self._entities_by_key: dict[int, EntityRef] = {}
        self._entities_by_id: dict[str, EntityRef] = {}
        self._last_values: dict[str, Any] = {}
        self.connected = False

    @property
    def entities(self) -> list[EntityRef]:
        return sorted(self._entities_by_id.values(), key=lambda item: item.entity_id)

    @property
    def last_values(self) -> dict[str, Any]:
        return dict(self._last_values)

    async def run_forever(self) -> None:
        while True:
            try:
                await self._connect_and_wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("ESPHome device %s crashed; reconnecting", self.config.id)
            self.connected = False
            await asyncio.sleep(self._reconnect_seconds)

    async def command(self, entity_id: str, value: Any) -> None:
        entity = self._entities_by_id.get(entity_id)
        if entity is None:
            raise KeyError(f"Unknown ESPHome entity: {self.config.id}/{entity_id}")
        if self._client is None:
            raise RuntimeError(f"ESPHome device {self.config.id} is not connected.")

        if entity.platform == "switch":
            await self._client.switch_command(entity.key, _as_bool(value))
        elif entity.platform == "light":
            await self._client.light_command(entity.key, state=_as_bool(value))
        elif entity.platform == "number":
            await self._client.number_command(entity.key, float(value))
        elif entity.platform == "select":
            await self._client.select_command(entity.key, str(value))
        elif entity.platform == "button":
            await self._client.button_command(entity.key)
        else:
            raise ValueError(f"Entity {entity_id} is not commandable as {entity.platform}.")

    async def _connect_and_wait(self) -> None:
        self._client = APIClient(
            self.config.host,
            self.config.port,
            self.config.password,
            client_info="esphome-hubitat-bridge",
            noise_psk=self.config.encryption_key,
        )
        stop_event = asyncio.Event()

        async def on_stop(expected_disconnect: bool) -> None:
            LOGGER.warning(
                "ESPHome device %s disconnected expected=%s",
                self.config.id,
                expected_disconnect,
            )
            stop_event.set()

        LOGGER.info("Connecting to ESPHome device %s at %s", self.config.id, self.config.host)
        await self._client.connect(on_stop=on_stop, login=True)
        self.connected = True

        entities, _services = await self._client.list_entities_services()
        self._index_entities(entities)
        LOGGER.info(
            "ESPHome device %s connected with %d entities",
            self.config.id,
            len(self._entities_by_id),
        )
        self._client.subscribe_states(self._handle_state)
        await stop_event.wait()

    def _index_entities(self, entities: list[EntityInfo]) -> None:
        self._entities_by_key.clear()
        self._entities_by_id.clear()
        for info in entities:
            platform = _platform_for_info(info)
            if platform is None:
                continue
            entity_id = f"{platform}.{info.object_id}"
            entity = EntityRef(
                device_id=self.config.id,
                entity_id=entity_id,
                key=info.key,
                name=info.name,
                platform=platform,
            )
            self._entities_by_key[info.key] = entity
            self._entities_by_id[entity_id] = entity

    def _handle_state(self, state: EntityState) -> None:
        entity = self._entities_by_key.get(state.key)
        if entity is None:
            return
        value = _value_from_state(state)
        if value is _MISSING:
            return
        self._last_values[entity.entity_id] = value
        self._on_state(self.config.id, entity.entity_id, value)


_MISSING = object()


def _platform_for_info(info: EntityInfo) -> str | None:
    name = type(info).__name__
    if name == "BinarySensorInfo":
        return "binary_sensor"
    if name == "SensorInfo":
        return "sensor"
    if name == "TextSensorInfo":
        return "text_sensor"
    if isinstance(info, SwitchInfo):
        return "switch"
    if isinstance(info, LightInfo):
        return "light"
    if isinstance(info, NumberInfo):
        return "number"
    if isinstance(info, SelectInfo):
        return "select"
    if isinstance(info, ButtonInfo):
        return "button"
    return None


def _value_from_state(state: EntityState) -> Any:
    if isinstance(state, (BinarySensorState, SwitchState)):
        return bool(state.state)
    if isinstance(state, (SensorState, NumberState)):
        return None if getattr(state, "missing_state", False) else state.state
    if isinstance(state, (TextSensorState, SelectState)):
        return None if getattr(state, "missing_state", False) else state.state
    if isinstance(state, LightState):
        return bool(state.state)
    return _MISSING


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "open", "active", "yes"}
    return bool(value)
