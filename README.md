# Pixora

Windows-first firmware and server tooling for reusing Tidbyt hardware with a Pixora-compatible image endpoint.

## Firmware

Supported firmware targets:

- `tidbyt-gen1`
- `tidbyt-gen1_swap`
- `tidbyt-gen2`
- `pixora-s3`
- `pixora-s3-wide`
- `pixoticker`
- `matrixportal-s3`
- `matrixportal-s3-waveshare`
- `matrixportal-s3-128x32`

Shareable generic firmware releases can be built with:

```powershell
.\scripts\build-firmware-release.ps1
```

Release packages are written to `releases\Pixora-firmware-v<version>\` and zipped beside that folder. See `docs\FIRMWARE_RELEASES.md`.

A shareable Windows app package can be built with:

```powershell
.\scripts\build-windows-app.ps1
```

That build creates:

```text
releases\PixoraSetup-v<version>.exe
releases\Pixora-windows-v<version>.zip
```

The setup executable is built with Inno Setup 6 when `ISCC.exe` is installed. Use `-SkipInstaller` to build only the portable zip.

## Release

The easiest full release path is:

```powershell
.\scripts\release-pixora.ps1 -Version 1.3.62 -Clean -Publish
```

That one command updates the firmware version, builds firmware, builds the Windows installer, syncs the public `bptworld/pixora` README in `.publish-pixora`, pushes that public repo update, and creates or updates the GitHub Release that Pixora uses for update checks.

To sync the public checkout from existing release artifacts without rebuilding or pushing:

```powershell
.\scripts\release-pixora.ps1 -SkipBuild
```

After publishing, verify the GitHub Release assets with:

```powershell
.\scripts\check-pixora-release.ps1 -RequireNoRootDownloads
```

See [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for the full checklist.

## Card Updates

The easiest card update path is:

```powershell
.\scripts\update-pixora-cards.ps1 -Publish
```

That syncs `addons\`, `card_utils.py`, `event_sport_utils.py`, and the AI card brief into `cards\`, compiles every card, commits the changes, and pushes `bptworld/pixora`.

Run it without `-Publish` to create a local card-repo commit without pushing:

```powershell
.\scripts\update-pixora-cards.ps1
```

The public card registry is protected by default. Use `-IncludeRegistry` only when the source `registry.json` is the full public catalog, not the small local app cache.

## Run On Windows

For regular users, download and run the Windows installer:

```text
PixoraSetup-v<version>.exe
```

The installer adds Start Menu shortcuts and launches Pixora. User data, settings, saved devices, groups, and downloaded cards are stored in:

```text
%LOCALAPPDATA%\Pixora
```

The portable zip is still available if you prefer to unzip and run without installing:

```text
Pixora-windows-v<version>.zip
```

Then double-click:

```text
Pixora.exe
```

No Python install is required for the packaged app.

For development, download or unzip Pixora to a Windows folder such as:

```text
C:\Pixora
```

Then double-click:

```text
Start Pixora.bat
```

Pixora will start the local server and open:

```text
http://pixora.local:8088/
```

If that address does not resolve on the Windows machine, use:

```text
http://localhost:8088/
```

## Build On Windows

Open Pixora in a local browser server:

```powershell
.\Start-Pixora.ps1
```

Use `index.html` from that browser window. The flashing page needs localhost so the browser can access USB safely.

For a compact command-builder flow, open:

```text
getting-started.html
```

Set up ESP-IDF once:

```powershell
.\scripts\setup-esp-idf.ps1
```

Create a generic firmware build:

```powershell
.\scripts\build-firmware.ps1 -Target tidbyt-gen1 -Clean
```

Build artifacts are copied to:

```text
dist\firmware\<target>\
```

The important first-flash file is `merged_firmware.bin`.

Device setup is managed from the Windows Pixora control page. Open `index.html`, choose `Setup a New Device`, and Pixora stores that display locally so it appears as a device tab.

When Pixora is started with `.\Start-Pixora.ps1`, the Windows server advertises itself on the local network as:

```text
http://pixora.local:8088/
```

Devices can use `pixora.local` instead of a numeric Windows IP address. Each display also advertises its Device ID as `<device-id>.local`.

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

Call it from an automation:

```yaml
action: rest_command.pixora_message
data:
  message: "Front door opened"
  target: "display"
  mode: "scroll"
  color: "yellow"
  duration: 12
```

Use a Pixora group ID or group name as `target` with `mode: wall` to send a synchronized wall message. Extra `data` fields supported by wall mode include `speed` (`slow`, `normal`, `fast`, `turbo`) and `graphic` (`none`, `baseball`, `arrow`, `bullet`, `delorean`).

The current Home Assistant endpoint, devices, groups, and a generated `rest_command` template are available as JSON at:

```text
http://pixora.local:8088/api/home-assistant
```

## SmartThings Integration

Add the `SmartThings Entity` card to show live SmartThings device state on a Pixora display. It uses a SmartThings Personal Access Token with device read permission, then reads device state from the SmartThings API.

Common card settings:

- `Device`: load devices from SmartThings after entering the token.
- `Capability`: examples include `temperatureMeasurement`, `switch`, `contactSensor`, `motionSensor`, `battery`, `lock`.
- `Attribute`: examples include `temperature`, `switch`, `contact`, `motion`, `battery`, `lock`.
- `Component`: usually `main`.

Pixora also accepts SmartThings-friendly message pushes at:

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

Use a Pixora group ID or group name as `target` with `"mode": "wall"` for a synchronized wall message. Discovery information for local Pixora targets is available at:

```text
http://pixora.local:8088/api/smartthings
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

Payloads can be plain text:

```text
Front door opened
```

Or JSON:

```json
{
  "message": "Front door opened",
  "target": "display",
  "data": {
    "mode": "scroll",
    "color": "yellow",
    "duration": 12
  }
}
```

For wall messages, publish to `pixora/group/main-wall/message` or set the JSON `target` to a Pixora group ID/name and use:

```json
{
  "message": "Washer finished",
  "data": {
    "mode": "wall",
    "speed": "fast",
    "graphic": "arrow"
  }
}
```

Pixora publishes retained connection state to `pixora/status` and non-retained queue results to `pixora/last`.

The setup page collects:

- Wi-Fi SSID and password
- Pixora server address
- Device ID/name
- Pixora endpoint, generated as `http://pixora.local:8088/<device-id>/next`

The editable setup pages are right in the project root:

```text
index.html
setup.html
setup-success.html
```

`index.html` is the local Pixora control page. `setup.html` is the Windows-side device setup form.

Cards are downloaded inside the Pixora app from the card registry. Downloaded card files are stored locally in:

```text
addons\
```

The Windows release package does not include bundled cards.

## Flash Or Update A Device

The first install is USB because the device is not on Wi-Fi yet:

```powershell
.\Flash-Device.ps1 -Port COM3 -Target tidbyt-gen1
```

Change `COM3` to the port Windows assigned to the device.

Wi-Fi credentials can be baked into that first USB firmware image:

```powershell
.\scripts\build-firmware.ps1 -Target tidbyt-gen1 -WifiSsid "your-wifi" -WifiPassword "your-password" -RemoteUrl "http://pixora.local:8088/kitchen/next" -Clean
```

That command uses Wi-Fi settings inside the firmware; it does not upload over Wi-Fi.

After the device is running Pixora firmware and is on Wi-Fi, update it by IP address or its `.local` name:

```powershell
.\Update-DeviceWifi.ps1 -DeviceIp 192.168.4.20 -Target tidbyt-gen1
```

```powershell
.\Update-DeviceWifi.ps1 -DeviceIp display.local -Target tidbyt-gen1
```

For development only, the build script can still bake provisioning values into firmware:

```powershell
.\scripts\build-firmware.ps1 -Target tidbyt-gen1 -WifiSsid "your-wifi" -WifiPassword "your-password" -RemoteUrl "http://pixora.local:8088/kitchen/next" -Clean
```
