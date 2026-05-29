# ESPHome Hubitat Bridge

A small Dockerized Linux service that connects ESPHome devices directly to Hubitat through Hubitat Maker API.

It does not require Home Assistant. ESPHome stays on the device. Hubitat stays the automation hub. This bridge keeps the two talking.

## What Works

- ESPHome native API connections, including encrypted API keys.
- Binary sensors, sensors, text sensors, switches, lights, numbers, selects, and buttons.
- ESPHome state updates pushed into Hubitat by running Maker API device commands.
- Hubitat virtual switch changes polled through Maker API and sent back to ESPHome switches or lights.
- Health/status endpoint at `http://<docker-host>:8099/health`.
- Entity inventory endpoint at `http://<docker-host>:8099/entities`.

## Hubitat Setup

1. In Hubitat, install the built-in **Maker API** app.
2. Authorize the virtual devices you want the bridge to update.
3. Copy the Maker API `app_id` and `access_token`.
4. Create virtual devices that have commands matching your mapping.

Maker API cannot create Hubitat devices for you. This bridge maps ESPHome entities to existing Hubitat device IDs.

This repo includes an optional catch-all Hubitat driver at:

```text
hubitat-drivers/esphome-bridge-omni.groovy
```

Install it under **Drivers Code**, create a virtual device using **ESPHome Bridge Omni**, and authorize that device in Maker API. It accepts common sensor commands plus `setAttributeValue(attributeName, attributeValue)` for arbitrary ESPHome values.

Useful Hubitat virtual device examples:

- Virtual Motion Sensor: use commands such as `active` and `inactive`.
- Virtual Contact Sensor: use commands such as `open` and `close`.
- Virtual Switch: use commands such as `on` and `off`.
- ESPHome Bridge Omni: use `setAttributeValue`, `setValue`, `setNumber`, or `setText`.

## ESPHome Setup

Your ESPHome YAML needs the native API enabled:

```yaml
api:
  encryption:
    key: "your-api-encryption-key"
```

Then use that key as `encryption_key` in `config.yaml`. If your ESPHome device has no API encryption, leave `encryption_key: null`.

## Run

Copy the example config:

```bash
cp config.example.yaml config.yaml
mkdir -p data
```

Edit `config.yaml`, then start:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f
```

## Mapping Model

Each mapping joins one ESPHome entity to one Hubitat device.

```yaml
- name: "Bedroom Presence"
  esphome_device: "bedroom-mmwave"
  esphome_entity: "binary_sensor.bedroom_mmwave_presence"
  hubitat_device_id: "101"
  hubitat_attribute: "motion"
  state_to_hubitat:
    true:
      command: "active"
    false:
      command: "inactive"
```

For numeric or string values, use the special `value` rule and `{value}` placeholders:

```yaml
state_to_hubitat:
  value:
    command: "setAttributeValue"
    args: ["heartRate", "{value}"]
```

For bidirectional switch/light control, add `hubitat_to_esphome`:

```yaml
hubitat_to_esphome:
  "on": true
  "off": false
```

## Notes

- Use reserved DHCP leases or static IPs for ESPHome devices.
- `network_mode: host` is used so `.local` names and local LAN access behave normally on Linux.
- For health/safety sensors such as fall detection, use this as an automation input, not as the only emergency response system.
