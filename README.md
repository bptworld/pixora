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
