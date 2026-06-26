# Pixora MatrixPortal S3 Firmware

Fresh source-controlled firmware for Adafruit MatrixPortal S3 displays.

This rebuild starts with:

- two-line boot status screens: `WAITING / FOR WIFI`, `WAITING / ON CLOUD`
- USB serial setup compatible with the Pixora setup scripts:
  `PIXORA_CONFIG {"ssid":"...","pass":"...","url":"...","mode":"cloud","host":"..."}`
- cloud/local polling through `/next`
- raw RGB565 frame mode for the new firmware path
- headers for dwell, brightness, reboot, and OTA URL

The old firmware source was lost. Existing `.bin` files show the legacy firmware was an ESP-IDF app named `pixora`, but this rebuild intentionally starts from a simpler Arduino/PlatformIO base so the source can stay in this repo from now on.

## Build

Install PlatformIO, then:

```powershell
cd D:\pixorahq\pixora-src\firmware\matrixportal-s3
pio run -e matrixportal_s3_64x32
pio run -e matrixportal_s3_128x32
```

## First Flash

Use the MatrixPortal S3 BOOT/RESET buttons if Windows does not expose the USB serial port normally:

1. Hold `BOOT`.
2. Tap `RESET`.
3. Release `BOOT`.
4. Upload/flash from PlatformIO.

## Which Firmware File

The package script writes three names for each panel size:

- `*-user-ota-firmware.bin`: use this for customer/cloud updates. It is meant to preserve existing setup.
- `*-factory-firmware.bin`: use this label for pre-ship install/testing on your side.
- `*-ota-firmware.bin`: compatibility alias for existing Pixora tooling.

The app does not intentionally erase setup. It reads and writes only the current `pixora` settings namespace using the short setup keys `ssid`, `pass`, `url`, `mode`, and `host`. A full chip erase or flashing the wrong full image can still clear setup; customer updates should use the user OTA `.bin`.

## USB Setup

After flashing, the Pixora Cloud setup app sends the current short-key config line. On success, firmware prints:

```text
PIXORA_CONFIG_SAVED
```

## Frame Format

This rebuild asks the server for `format=rgb565`. The response body is expected to be packed little-endian RGB565 pixels:

```text
width * height * 2 bytes
```

The cloud/server fallback still renders normal Pixora cards. The firmware side avoids WebP decoding on-device for this new path.
