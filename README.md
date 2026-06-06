# Pixora HQ

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

Cards are downloaded and managed within the Pixora app.
Card updates must be submitted by pull request.

## Running Pixora

After installing, launch Pixora from the Start Menu or desktop shortcut. Pixora starts a local server and opens:

```text
http://pixora.local:8088/
```

If that address does not resolve on the Windows machine, use:

```text
http://localhost:8088/
```
