# Pixora

Pixora is a Windows app and firmware package for running Pixora-compatible pixel displays on your local network.

## Downloads

Download Pixora from the official GitHub Releases page:

https://github.com/bptworld/pixora/releases/latest

Use the Windows installer:

```text
PixoraSetup-v<version>.exe
```

The installer includes everything needed to run Pixora on Windows. User data, settings, saved devices, groups, and downloaded cards are stored in:

```text
%LOCALAPPDATA%\Pixora
```

Firmware downloads are provided only as official prebuilt `.bin` files on the release page.

## Cards

The public card catalog lives in:

```text
cards/
```

Pixora downloads cards from the official registry:

```text
https://raw.githubusercontent.com/bptworld/pixora/main/cards/registry.json
```

Downloaded card files are stored locally by the app.

## Maintainer Card Updates

From the Pixora checkout, publish card changes to GitHub with:

```powershell
.\cards\scripts\update-from-pixora.ps1 -Publish -IncludeRegistry
```

That flow updates only the public card catalog under `cards/`. Windows installers and firmware binaries are distributed only through GitHub Releases.

## Running Pixora

After installing, launch Pixora from the Start Menu or desktop shortcut. Pixora starts a local server and opens:

```text
http://pixora.local:8088/
```

If that address does not resolve on the Windows machine, use:

```text
http://localhost:8088/
```

## Home Assistant Messages

Pixora accepts Home Assistant-friendly message pushes at:

```text
http://pixora.local:8088/api/home-assistant/message
```

Example `rest_command`:

```yaml
rest_command:
  pixora_message:
    url: "http://pixora.local:8088/api/home-assistant/message"
    method: post
    content_type: "application/json"
    payload: >
      {
        "message": "{{ message }}",
        "target": "{{ target | default('all') }}",
        "data": {
          "mode": "{{ mode | default('wrap') }}",
          "color": "{{ color | default('white') }}",
          "duration": {{ duration | default(10) }}
        }
      }
```

## SmartThings Messages

Pixora accepts SmartThings-friendly message pushes at:

```text
http://pixora.local:8088/api/smartthings/message
```

Example payload:

```json
{
  "title": "SmartThings",
  "message": "Garage door opened",
  "target": "display",
  "data": {
    "mode": "scroll",
    "color": "yellow",
    "duration": 12
  }
}
```

## MQTT Messages

Enable MQTT in Pixora Global Options, then set your broker host, port, optional username/password, TLS, and base topic. The default base topic is:

```text
pixora
```

Pixora subscribes to:

```text
pixora/message
pixora/<target>/message
pixora/device/<device-id>/message
pixora/group/<group-id>/message
```
