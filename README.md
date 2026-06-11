# Pixora HQ

Pixora provides Windows tools and firmware for running Pixora-compatible pixel displays with either a local Windows server or a Pixora Cloud endpoint.

## Downloads

Download Pixora from the official GitHub Releases page:

https://github.com/bptworld/pixora/releases/latest

### Local Server

Use the Local Server installer when you want Pixora to run on a Windows computer on your network:

```text
PixoraSetup-v<version>.exe
```

The Local Server installer includes the Pixora app, local renderer, cards, device management, and USB setup tools. User data, settings, saved devices, groups, and downloaded cards are stored in:

```text
%LOCALAPPDATA%\Pixora
```

After installing, launch Pixora from the Start Menu or desktop shortcut. Pixora starts a local server and opens:

```text
http://pixora.local:8088/
```

If that address does not resolve on the Windows machine, use:

```text
http://localhost:8088/
```

### Cloud Server

Use the Cloud Server setup installer when your display should connect to a hosted Pixora Cloud endpoint instead of a local Windows server:

```text
PixoraCloudSetup-v<version>.exe
```

The Cloud Server setup tool only sends Wi-Fi and Pixora Cloud endpoint settings to a display over USB. It does not install the local Pixora server, renderer, cards, or firmware build tools.

Firmware downloads are provided only as official prebuilt `.bin` files on the release page.

## Cards

Cards are downloaded and managed within the Pixora app.
Card updates must be submitted by pull request.

## Firmware

Use the OTA firmware files for updates from the Pixora app, and the USB full-flash files for first-time flashing or recovery.
