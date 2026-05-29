# Pixora Firmware Releases

Use `scripts\build-firmware-release.ps1` to create firmware that can be shared with other users.

The release build is generic. It does not include your Wi-Fi name, Wi-Fi password, Pixora server address, or device hostname.

## Build A Release

```powershell
.\scripts\build-firmware-release.ps1
```

By default this builds:

- `tidbyt-gen1`
- `matrixportal-s3-waveshare`

To build specific targets:

```powershell
.\scripts\build-firmware-release.ps1 -Target tidbyt-gen1, matrixportal-s3-waveshare
```

To force a clean rebuild:

```powershell
.\scripts\build-firmware-release.ps1 -Clean
```

## Output

The script creates:

```text
releases\Pixora-firmware-v<version>\
releases\Pixora-firmware-v<version>.zip
```

Each target folder includes:

- `merged_firmware.bin` for first USB flash
- `firmware.bin` for Wi-Fi updates after Pixora is installed
- `bootloader.bin`, `partition-table.bin`, and `flash_args` for manual flashing
- `README.txt`

The release folder also includes:

- `manifest.json`
- `SHA256SUMS.txt`

## User Setup

After first flash, the user opens the Pixora Windows app and configures:

- Wi-Fi SSID
- Wi-Fi password
- Pixora server, normally `http://pixora.local:8088`
- Device ID/name

The firmware advertises the device on mDNS after setup.
