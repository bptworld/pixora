# Pixora LED Studio for Home Assistant

**Pixora LED Studio is now available within Home Assistant.** Build decks, choose cards and manage your LED displays from your own HA hub. Cards render locally and are sent to the panels over local Wi-Fi; a Pixora Cloud account or rendering server is not required.

This repository contains the public card library and graphics used by LED Studio. Install the Home Assistant app and download panel firmware from **[PixoraHQ for Home Assistant](https://github.com/bptworld/PixoraHQforHA)**.

## Install the Home Assistant app

1. In Home Assistant, open **Settings → Apps → App store → ⋮ → Repositories**.
2. Add **https://github.com/bptworld/PixoraHQforHA**.
3. Refresh the store, install **Pixora LED Studio**, then start it and open its interface.

[Add the repository to Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fbptworld%2FPixoraHQforHA) · [Full LED Studio instructions](https://github.com/bptworld/PixoraHQforHA/blob/main/pixora_led_displays/README.md)

## Set up a new display

Pixora LED Studio supports **Adafruit MatrixPortal S3** controllers with **64×32** or **128×32** displays. A 128×32 display uses two 64×32 panels with one controller. Both sizes use the same firmware.

1. Download the [USB first-install firmware](https://github.com/bptworld/PixoraHQforHA/raw/refs/heads/main/firmware/usb/2.0.27/pixora-v2.0.27-s3-first-install-usb.bin).
2. Follow the [USB flashing and Wi-Fi setup guide](https://github.com/bptworld/PixoraHQforHA/blob/main/firmware/usb/2.0.27/README.md).
3. Join the panel's **Pixora-…** setup network using the password shown on its display. Open **http://192.168.4.1**, enter your **2.4 GHz home Wi-Fi**, and select the panel size.
4. Reconnect to home Wi-Fi. In LED Studio, open **Displays & firmware** and connect the panel using its displayed IP address.
5. Add cards to a deck, assign it to the display, then press **Play deck**.

**The USB first-install image erases existing Wi-Fi, pairing and panel settings.** Use it for initial installation; use normal Wi-Fi firmware updates afterward to preserve settings.

[Build-your-own parts list](https://github.com/bptworld/PixoraHQforHA/blob/main/pixora_led_displays/README.md#build-your-own-display)

## Update an existing local display

1. Open **Pixora LED Studio** in Home Assistant.
2. Open **Displays & firmware** and select the display.
3. Under **Panel firmware**, choose **Check for updates**, then **Update display** when an update is available.
4. Keep the display powered on until the update and reconnection finish.

Normal updates use the **S3 user-OTA firmware** and preserve Wi-Fi, pairing and panel settings. Do not select the USB first-install image in the app's firmware update control. Current compiled firmware is published in the [Home Assistant repository releases](https://github.com/bptworld/PixoraHQforHA/releases).

## Cards and graphics

The `cards/` and `graphics/` directories remain the public library used by the Home Assistant app. LED Studio downloads required card files when you save a deck and renders them on the HA hub. Live-data cards may need Internet access or provider credentials.

Firmware source remains private. This repository's older server and device-specific firmware instructions have been replaced by the Home Assistant setup above.
