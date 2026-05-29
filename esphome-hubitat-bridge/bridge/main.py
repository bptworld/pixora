from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from typing import Any

from .config import AppConfig, HubitatCommand, MappingConfig, load_config
from .esphome_device import ESPHomeDevice
from .hubitat import HubitatClient, get_attribute
from .state_store import StateStore
from .status_server import StatusServer

LOGGER = logging.getLogger(__name__)


class Bridge:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._hubitat = HubitatClient(config.hubitat)
        self._state_store = StateStore(config.bridge.state_file)
        self._devices: dict[str, ESPHomeDevice] = {
            device_id: ESPHomeDevice(
                device_config,
                self._on_esphome_state,
                config.bridge.reconnect_seconds,
            )
            for device_id, device_config in config.esphome_devices.items()
        }
        self._mappings_by_esphome: dict[tuple[str, str], list[MappingConfig]] = {}
        for mapping in config.mappings:
            self._mappings_by_esphome.setdefault(
                (mapping.esphome_device, mapping.esphome_entity),
                [],
            ).append(mapping)
        self._tasks: list[asyncio.Task[Any]] = []
        self._status = StatusServer(
            config.bridge.status_host,
            config.bridge.status_port,
            self._health,
            self._entities,
        )

    async def run(self) -> None:
        await self._hubitat.start()
        await self._status.start()
        LOGGER.info(
            "Status server listening on %s:%s",
            self._config.bridge.status_host,
            self._config.bridge.status_port,
        )
        self._tasks = [
            asyncio.create_task(device.run_forever(), name=f"esphome:{device_id}")
            for device_id, device in self._devices.items()
        ]
        self._tasks.append(asyncio.create_task(self._poll_hubitat(), name="hubitat-poll"))

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda _signum, _frame: stop_event.set())
        await stop_event.wait()
        await self.stop()

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._status.stop()
        await self._hubitat.close()

    def _on_esphome_state(self, device_id: str, entity_id: str, value: Any) -> None:
        asyncio.create_task(self._sync_esphome_state(device_id, entity_id, value))

    async def _sync_esphome_state(self, device_id: str, entity_id: str, value: Any) -> None:
        mappings = self._mappings_by_esphome.get((device_id, entity_id), [])
        if not mappings:
            return

        for mapping in mappings:
            rule = _select_rule(mapping, value)
            if rule is None:
                LOGGER.debug("No Hubitat rule for %s=%r", mapping.name, value)
                continue

            state_key = f"esphome:{device_id}:{entity_id}:hubitat:{mapping.hubitat_device_id}"
            current_signature = {"command": rule.command, "args": rule.args, "value": value}
            if self._state_store.get(state_key) == current_signature:
                continue

            try:
                LOGGER.info("Hubitat <- ESPHome %s: %r", mapping.name, value)
                await self._hubitat.send_command(mapping.hubitat_device_id, rule, value)
                self._state_store.set(state_key, current_signature)
            except Exception:
                LOGGER.exception("Failed to update Hubitat for mapping %s", mapping.name)

    async def _poll_hubitat(self) -> None:
        while True:
            await asyncio.sleep(self._config.bridge.poll_hubitat_seconds)
            for mapping in self._config.mappings:
                if not mapping.hubitat_to_esphome or not mapping.hubitat_attribute:
                    continue
                await self._poll_mapping(mapping)

    async def _poll_mapping(self, mapping: MappingConfig) -> None:
        try:
            device = await self._hubitat.get_device(mapping.hubitat_device_id)
            hubitat_value = get_attribute(device, mapping.hubitat_attribute or "")
        except Exception:
            LOGGER.exception("Failed to poll Hubitat for mapping %s", mapping.name)
            return

        if hubitat_value is None:
            return
        normalized = str(hubitat_value).lower()
        if normalized not in mapping.hubitat_to_esphome:
            return

        target = mapping.hubitat_to_esphome[normalized]
        state_key = f"hubitat:{mapping.hubitat_device_id}:{mapping.hubitat_attribute}:esphome"
        current_signature = {
            "device": mapping.esphome_device,
            "entity": mapping.esphome_entity,
            "value": target,
        }
        if self._state_store.get(state_key) == current_signature:
            return

        try:
            LOGGER.info("ESPHome <- Hubitat %s: %r", mapping.name, hubitat_value)
            await self._devices[mapping.esphome_device].command(mapping.esphome_entity, target)
            self._state_store.set(state_key, current_signature)
        except Exception:
            LOGGER.exception("Failed to command ESPHome for mapping %s", mapping.name)

    def _health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "devices": {
                device_id: {"connected": device.connected}
                for device_id, device in self._devices.items()
            },
            "mappings": len(self._config.mappings),
        }

    def _entities(self) -> dict[str, Any]:
        return {
            device_id: [
                {
                    "entity_id": entity.entity_id,
                    "name": entity.name,
                    "platform": entity.platform,
                    "last_value": device.last_values.get(entity.entity_id),
                }
                for entity in device.entities
            ]
            for device_id, device in self._devices.items()
        }


def _select_rule(mapping: MappingConfig, value: Any) -> HubitatCommand | None:
    if isinstance(value, bool):
        bool_key = "true" if value else "false"
        if bool_key in mapping.state_to_hubitat:
            return mapping.state_to_hubitat[bool_key]
    exact_key = str(value)
    if exact_key in mapping.state_to_hubitat:
        return mapping.state_to_hubitat[exact_key]
    return mapping.state_to_hubitat.get("value")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge ESPHome devices to Hubitat Maker API.")
    parser.add_argument("--config", default="config.yaml", help="Path to bridge YAML config.")
    args = parser.parse_args()

    config = load_config(args.config)
    logging.basicConfig(
        level=getattr(logging, config.bridge.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(Bridge(config).run())
