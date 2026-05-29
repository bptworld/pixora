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
_target            # device target, such as matrixportal-s3-waveshare or matrixportal-s3-128x32
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

for target in ("matrixportal-s3-waveshare", "matrixportal-s3-128x32"):
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

