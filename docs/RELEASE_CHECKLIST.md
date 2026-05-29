# Pixora Release Checklist

Use this checklist when publishing a Pixora app, firmware, and card update.

## Before Release

- Confirm the app opens locally from `.\Start-Pixora.ps1`.
- Confirm the Help pages and Setup Options screens load.
- Confirm any changed cards render locally.
- Confirm public card URLs point to `https://raw.githubusercontent.com/bptworld/pixora/main/cards/...`.
- If cards changed, run:

```powershell
.\scripts\update-pixora-cards.ps1 -Publish
```

## App And Firmware Release

Run one command from `C:\Pixora`:

```powershell
.\scripts\release-pixora.ps1 -Version 1.3.62 -Clean -Publish
```

This builds firmware, builds the Windows installer, syncs the public repo README, and creates or updates the GitHub Release.

## Verify Release

Run:

```powershell
.\scripts\check-pixora-release.ps1 -RequireNoRootDownloads
```

Confirm the script reports all three assets:

- `PixoraSetup-v<version>.exe`
- `Pixora-windows-v<version>.zip`
- `Pixora-firmware-v<version>.zip`

## Final Checks

- Open the GitHub Release page and confirm it is the latest release.
- Confirm the public README links point to GitHub Release downloads.
- Start Pixora and confirm the update checker reports the expected latest version.
- Keep release files attached to GitHub Releases, not committed to the public repo root.
