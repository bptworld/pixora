from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class HubitatConfig:
    base_url: str
    app_id: str
    access_token: str
    request_timeout_seconds: float = 10


@dataclass(frozen=True)
class BridgeConfig:
    poll_hubitat_seconds: float = 2
    reconnect_seconds: float = 10
    state_file: str = "/config/state.json"
    status_host: str = "0.0.0.0"
    status_port: int = 8099
    log_level: str = "INFO"


@dataclass(frozen=True)
class ESPHomeDeviceConfig:
    id: str
    name: str
    host: str
    port: int = 6053
    password: str | None = None
    encryption_key: str | None = None


@dataclass(frozen=True)
class HubitatCommand:
    command: str
    args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MappingConfig:
    name: str
    esphome_device: str
    esphome_entity: str
    hubitat_device_id: str
    hubitat_attribute: str | None = None
    state_to_hubitat: dict[str, HubitatCommand] = field(default_factory=dict)
    hubitat_to_esphome: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AppConfig:
    hubitat: HubitatConfig
    bridge: BridgeConfig
    esphome_devices: dict[str, ESPHomeDeviceConfig]
    mappings: list[MappingConfig]


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a YAML object.")

    hubitat = HubitatConfig(**raw["hubitat"])
    bridge = BridgeConfig(**raw.get("bridge", {}))

    devices_raw = raw.get("esphome", {}).get("devices", [])
    devices = {
        item["id"]: ESPHomeDeviceConfig(**item)
        for item in devices_raw
    }
    if not devices:
        raise ValueError("At least one esphome.devices entry is required.")

    mappings = [_parse_mapping(item) for item in raw.get("mappings", [])]
    return AppConfig(
        hubitat=hubitat,
        bridge=bridge,
        esphome_devices=devices,
        mappings=mappings,
    )


def _parse_mapping(raw: dict[str, Any]) -> MappingConfig:
    state_rules = {}
    for key, value in (raw.get("state_to_hubitat") or {}).items():
        if isinstance(value, str):
            state_rules[str(key)] = HubitatCommand(command=value)
        elif isinstance(value, dict):
            state_rules[str(key)] = HubitatCommand(
                command=str(value["command"]),
                args=[str(arg) for arg in value.get("args", [])],
            )
        else:
            raise ValueError(f"Invalid state_to_hubitat rule for {raw.get('name')}: {key}")

    return MappingConfig(
        name=str(raw["name"]),
        esphome_device=str(raw["esphome_device"]),
        esphome_entity=str(raw["esphome_entity"]),
        hubitat_device_id=str(raw["hubitat_device_id"]),
        hubitat_attribute=raw.get("hubitat_attribute"),
        state_to_hubitat=state_rules,
        hubitat_to_esphome=dict(raw.get("hubitat_to_esphome") or {}),
    )
