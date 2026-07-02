# Pixora Codex Card Creator Brief

Use this file when asking Codex to create or modify a Pixora card. Upload it with your request and describe the card you want.

## What Pixora Cards Are

Pixora cards are standalone Python files in the `addons` folder. Each card renders a 64x32 or 128x32 RGB image, usually as a WebP byte string. Cards are optional, can be added or removed from a device deck at any time, and must not require firmware changes.

Cards run on the Windows Pixora server when cards are being prepared or refreshed, then the rendered WebP frames are sent to the device. The device should only need to display the WebP and follow the headers from the server.

## Required Card Shape

Create one file:

```text
addons/<card_id>.py
```

Every card must define:

```python
CARD_ID = "short_unique_id"
CARD_NAME = "Human Name"
CARD_DETAIL = "Short description shown in the card library"
CARD_VERSION = "1.0.0"
CARD_AUTHOR = "Your Name"
CARD_LICENSE = "MIT"
CARD_ALLOWED_DOMAINS = []
REQUIRED_SETTINGS = []
TAGS = []
RULE_VALUES = []
CARD_OPTIONS = [
    {"key": "example", "label": "Example", "type": "text", "default": ""},
]

def render(options=None):
    ...
    return webp_bytes
```

`render(options)` must return either:

```python
bytes
```

or a dictionary:

```python
{
    "body": webp_bytes,
    "dwell_secs": 10,
    "_no_replay": True,
}
```

Use `_no_replay` for finite animations that should play once and hold, not restart repeatedly during the card dwell time.

`CARD_ALLOWED_DOMAINS` is the card-level network allowlist. Public fetch helpers use it automatically when `allowed_domains` is not passed directly.

`RULE_VALUES` lets the Rules Engine discover values exposed by `rule_value(options=None, field="")`:

```python
RULE_VALUES = [{"key": "score", "label": "Score"}]

def rule_value(options=None, field=""):
    if field == "score":
        return 7
    return ""
```

## Device Targets

Cards must support both common layouts:

```python
is_wide = (options or {}).get("_target") == "matrixportal-s3-128x32"
width = 128 if is_wide else 64
height = 32
```

Do not assume only one panel size. If a card has a special 128 layout, keep the 64 layout polished too.

## Options Passed By Pixora

Pixora adds internal metadata to options:

```python
_target            # device target, such as matrixportal-s3-64x32 or matrixportal-s3-128x32
_dwell             # user-selected dwell seconds
_device_id         # active device id
_firmware_version  # device firmware version
_refresh_policy    # global refresh policy
_log               # optional logging function
```

Cards should use normal user options for setup, and only use internal options when needed.

## Supported Option Types

Common option entries:

```python
{"key": "zipCode", "label": "ZIP", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"}
{"key": "team", "label": "Team", "type": "select", "default": "BOS", "choices": [{"value": "BOS", "label": "Boston Red Sox"}]}
{"key": "enabled", "label": "Enabled", "type": "checkbox", "default": True}
{"key": "count", "label": "Count", "type": "number", "default": 5, "min": 1, "max": 20}
```

Pixora also adds schedule controls in the app, so do not build day/time scheduling inside each card unless the card has a special reason.

## Global Settings

Use helpers from `card_utils.py` for shared settings:

```python
from card_utils import _settings_value, format_time, temperature_units

default_zip = _settings_value("defaultZipCode", "")
default_lat = _settings_value("defaultLatitude", "")
default_lon = _settings_value("defaultLongitude", "")
time_text = format_time(datetime.now())
units = temperature_units()
```

If a card has ZIP or lat/lon options, prefill from global defaults when the card option is blank, but let the user override per card.

## Public Helper APIs

Prefer public helpers from `card_utils.py` over custom networking, logging, fallback, color, and option code. These helpers use Pixora-safe defaults for caching, timeouts, image sizes, and display formatting.

Common helpers:

```python
from card_utils import (
    cached_json,
    card_asset_path,
    card_context,
    card_state,
    contrast_text_color,
    dim_color,
    fallback_frame,
    fetch_image_asset,
    load_card_asset_image,
    option_checkbox,
    option_number,
    option_select,
    option_target,
    option_text,
    option_zip,
    parse_color,
    paste_image_asset,
    pixora_log,
    special_graphic,
)
```

Context helper:

```python
ctx = card_context(options)
width = ctx["width"]
now = ctx["now"]
ctx["log"]("rendering")
```

Safe logging:

```python
pixora_log(options, "loaded 3 events")
```

Fallback frame:

```python
return fallback_frame("No games today", width=(options or {}).get("_width", 64), dwell_secs=6)
```

Cached JSON fetch:

```python
data = cached_json(
    "https://api.example.com/status",
    ttl_secs=300,
    allowed_domains=["api.example.com"],
)
```

`cached_json` only allows HTTP/S URLs, rejects localhost/private-network targets, clamps TTLs and response size, and returns stale cached data during transient fetch failures.

Safe image/logo fetch:

```python
logo = fetch_image_asset(team_logo_url, size=16, ttl_secs=3600, allowed_domains=["site.example.com"])
if logo:
    image.paste(logo, (0, 8), logo)
```

or:

```python
paste_image_asset(image, team_logo_url, (0, 8), size=16, allowed_domains=["site.example.com"])
```

Images are size-limited, cached, converted to RGBA, thumbnail-cropped into a square canvas, and alpha-cleaned for LED display.

Color helpers:

```python
team_color = parse_color("#0033A0", (40, 120, 255))
muted = dim_color(team_color, 0.45)
text_color = contrast_text_color(team_color)
```

Option builders:

```python
CARD_OPTIONS = [
    option_zip(),
    option_text("label", "Label", "Pixora"),
    option_target("goalAnimationTarget", "Goal Animation", default="group_wall"),
    option_select("team", "Team", [{"value": "USA", "label": "United States"}], default="USA"),
    option_number("days", "Days", default=7, min_value=1, max_value=30),
    option_checkbox("onlyGameDay", "Only show on game day", default=True),
]
```

Safe per-card state:

```python
state = card_state(CARD_ID)
last_seen = state.get("last_seen", "")
state.set("last_seen", "2026-07-01T12:00:00Z")
```

Use `card_state()` instead of direct file paths. Pixora stores JSON under its card-state area and sanitizes the card id.

Static card assets:

```python
logo = load_card_asset_image(CARD_ID, "logo.png", size=16)
if logo:
    image.paste(logo, (0, 8), logo)
```

Place bundled assets under:

```text
cards/assets/<CARD_ID>/logo.png
```

Asset helpers are read-only, keep paths inside the card's asset folder, reject path traversal, and ignore files larger than 768 KB.

## Rendering Rules

Use Pillow:

```python
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

image = Image.new("RGB", (width, 32), (0, 0, 0))
draw = ImageDraw.Draw(image)

out = BytesIO()
image.save(out, "WEBP", lossless=True, quality=100)
return out.getvalue()
```

Prefer crisp pixel art. Avoid blur, anti-aliased resizing, shadows, gradients that make LEDs fuzzy, and tiny text that clips.

Use `draw_sharp_text` from `card_utils.py` for crisp text:

```python
from card_utils import draw_sharp_text
draw_sharp_text(image, (x, y), "Text", (255, 255, 255), font)
```

Use `Image.Resampling.NEAREST` for pixel art scaling.

## Fonts

Available fonts in the Pixora root include:

```text
assets/fonts/Silkscreen-Regular.ttf
assets/fonts/Silkscreen-Bold.ttf
assets/fonts/PixelifySans.ttf
assets/fonts/PixelifySans-Bold.ttf
assets/fonts/Jersey10-Regular.ttf
assets/fonts/Jersey15-Regular.ttf
assets/fonts/Jersey20-Regular.ttf
```

Silkscreen Regular is usually best for small text. Be careful with bold fonts at tiny sizes. For numbers, prefer Pixora's bitmap number helpers when the card needs chunky LED-style numbers:

```python
from card_utils import draw_bitmap_number_fit, draw_bitmap_number_fit_bold
```

## Animation Rules

Animated WebPs are allowed, but keep them light.

For 64x32:

```python
max_frames = 45
```

For 128x32:

```python
max_frames = 32
```

Avoid huge 128-wide animations with 80 or 90 frames. They can stress the ESP32-S3 decoder. If the animation should play once, return:

```python
{"body": body, "dwell_secs": dwell, "_no_replay": True}
```

Animation should loop smoothly if it is a fun ambient card. No snap-back unless the card intentionally cuts to a new scene.

## Special Device And Wall Graphics

Cards may return special break-in graphics for live events, alerts, or one-time moments. Use public keys, not Pixora's internal underscore keys:

```python
return {
    "body": normal_card_body,
    "dwell_secs": 6,
    "deviceGraphic": {
        "renderer": "render_goal_animation",
        "kind": "goal",
        "team": {"abbreviation": "USA", "color": "0033A0"},
        "dwell_secs": 6,
        "stay": True,
    },
    "wallGraphic": {
        "renderer": "render_goal_wall_frames",
        "kind": "goal",
        "team": {"abbreviation": "USA", "color": "0033A0"},
        "dwell_secs": 6,
    },
}
```

`deviceGraphic` is for a single device. `wallGraphic` is for a device group / wall and Pixora will render one wide animation, slice it per device, queue each slice, and show the current device's slice immediately. If both are present and the card is targeting a wall, the wall graphic wins.

Renderer functions must live in the same card file:

```python
def render_goal_animation(team, kind="goal"):
    # Return WebP bytes, or return (frames, durations_ms)
    ...

def render_goal_wall_frames(team, kind="goal"):
    width = int(team.get("_width") or 192)
    # Return a list of PIL RGB frames and matching duration values.
    return frames, durations_ms
```

Pixora injects `_width` into the renderer's `team` payload. For `deviceGraphic`, `_width` is the device width. For `wallGraphic`, `_width` is the total wall width. Do not hard-code wall widths.

Supported fields:

- `renderer`: required function name in the same card file.
- `kind` or `type`: event type such as `goal`, `run`, `win`, `launch`, or `alert`.
- `team`: small JSON-safe payload for labels, colors, logos, player names, or event text.
- `dwell_secs` or `dwellSecs`: how long the break-in graphic should stay up.
- `card` or `cardId`: optional display/card id override.
- `groupId` or `group`: optional wall group override for `wallGraphic`.
- `stay`: optional for device graphics that should hold the final frame.

Keep special graphics short, cached, and finite. Do not fetch data inside the special renderer; fetch in `render(options)` and pass only the needed data into `team`.

You may build those dictionaries manually, or use `special_graphic()`:

```python
return {
    "body": body,
    "dwell_secs": 6,
    **special_graphic(
        renderer="render_goal_animation",
        wall_renderer="render_goal_wall_frames",
        kind="goal",
        team={"abbreviation": "USA", "color": "0033A0"},
        dwell_secs=6,
        include_device=True,
        include_wall=True,
        stay=True,
    ),
}
```

For a complete starter, see:

```text
cards/templates/custom_card_starter.py
```

## Data Fetching Rules

Cards may fetch data from APIs, but must cache aggressively and fail gracefully.

Rules:

- Do not block card rendering for a long time.
- Cache API responses in module-level dictionaries.
- Use sensible TTLs.
- If data is missing, render a clean message instead of crashing.
- If an API uses credits, never poll more often than needed.
- Startup may refresh once, then each card should follow its own polling rules.
- If a flight/game/event is final, landed, cancelled, postponed, or otherwise done, stop unnecessary polling.

Use standard Python libraries unless a dependency already exists in Pixora.

## Layout Expectations

For 64x32:

- Keep text short.
- Use 1 or 2 pixel spacing carefully.
- Avoid bottom text clipping.
- Icons must be recognizable at small size.
- If showing scores, standings, or financial values, align columns tightly.

For 128x32:

- Use the extra width, not extra height.
- Larger logos/icons can sit far left/right.
- More detail can fit, but still keep vertical spacing tight.
- If a 64 card has two pages, consider showing both halves side by side on 128.

## Category And Registry

After adding a card, update the card registry/catalog used by Pixora if the project has one. Put the card in the correct category and keep categories/cards alphabetized.

Common categories:

```text
Finance
Fun
Home
Social
Sports
Travel
Utility
Weather
```

Sports may have subcategories such as Pro Sports, College Sports, and Fantasy.

## Thumbnail

If the card library uses thumbnails, create a realistic thumbnail that looks like the real card with sample data. Do not make a generic title card unless thumbnails are intentionally disabled.

## Testing Checklist

After creating or changing a card:

1. Run Python syntax check:

```powershell
python -m py_compile C:\Pixora\addons\<card_id>.py
```

2. Render both targets:

```powershell
@'
import importlib.util
from pathlib import Path
from PIL import Image, ImageSequence

path = Path(r"C:\Pixora\addons\<card_id>.py")
spec = importlib.util.spec_from_file_location("card", path)
card = importlib.util.module_from_spec(spec)
spec.loader.exec_module(card)

for target in ("matrixportal-s3-64x32", "matrixportal-s3-128x32"):
    body = card.render({"_target": target, "_dwell": 10})
    out = Path(r"C:\Pixora\data") / f"check-{card.CARD_ID}-{target}.webp"
    out.write_bytes(body["body"] if isinstance(body, dict) else body)
    im = Image.open(out)
    print(out.name, out.stat().st_size, im.size, sum(1 for _ in ImageSequence.Iterator(im)))
'@ | python -
```

3. Confirm:

- 64 output is exactly 64x32.
- 128 output is exactly 128x32.
- Text is not clipped.
- Animation frame count is reasonable.
- No card-specific logic was added to firmware.
- No old project names or unrelated branding were introduced.

## Minimal New Card Template

```python
from io import BytesIO

from card_utils import draw_sharp_text

CARD_ID = "example_card"
CARD_NAME = "Example Card"
CARD_DETAIL = "Short example card"
CARD_OPTIONS = [
    {"key": "message", "label": "Message", "type": "text", "default": "Hello Pixora", "maxlength": 40},
]


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    text = str(opts.get("message") or "Hello Pixora").strip()

    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = _font(10 if is_wide else 8)

    while text and _text_width(draw, text, font) > width - 4:
        text = text[:-1].rstrip()
    if not text:
        text = "..."

    x = (width - _text_width(draw, text, font)) // 2
    draw_sharp_text(image, (x, 11), text, (0, 220, 210), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
```
