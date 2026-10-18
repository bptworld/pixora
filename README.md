# Pixora LED Studio for Home Assistant

**Pixora LED Studio is now available within Home Assistant.** Build decks, choose cards and manage your LED displays from your own HA hub. Cards render locally and are sent to the panels over local Wi-Fi; a Pixora Cloud account or rendering server is not required.

This repository contains the public card library and graphics used by LED Studio. Install the Home Assistant app and download panel firmware from **[PixoraHQ for Home Assistant](https://github.com/bptworld/PixoraHQforHA)**.

## Cards and graphics

The `cards/` and `graphics/` directories remain the public library used by the Home Assistant app. LED Studio downloads required card files when you save a deck and renders them on the HA hub. Live-data cards may need Internet access or provider credentials.

Want to make your own card? Give the [HA AI Card Creator Brief](cards/Pixora-Codex-Card-Brief.md) to your AI and import the resulting Python file in LED Studio’s **My Apps** tab (1.2.24+). A [starter card](cards/templates/custom_card_starter.py) is included.

Firmware source remains private. Setup instructions and compiled panel firmware are available in the [Home Assistant repository](https://github.com/bptworld/PixoraHQforHA).
