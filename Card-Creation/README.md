# Creating Pixora Cards

Pixora cards are small Python files that render a `64 x 32` image for the display.

Cards are downloaded by Pixora from a GitHub card registry, then stored locally in the user's `addons` folder.

## What A Card Needs

Each card file needs:

- `CARD_ID`
- `CARD_NAME`
- `CARD_DETAIL`
- `CARD_OPTIONS`
- `render(options=None)`

The `render()` function must return image bytes in `WEBP` format.

## Basic File Shape

```python
from io import BytesIO

CARD_ID = "hello"
CARD_NAME = "Hello"
CARD_DETAIL = "Simple starter card"
CARD_OPTIONS = []


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()

    draw.text((4, 10), "HELLO", fill=(20, 149, 255), font=font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
```

## Card Metadata

### `CARD_ID`

Short unique ID for the card.

Use lowercase letters, numbers, and underscores:

```python
CARD_ID = "weather_forecast"
```

The file name should usually match:

```text
weather_forecast.py
```

### `CARD_NAME`

Friendly name shown in Pixora:

```python
CARD_NAME = "Weather Forecast"
```

### `CARD_DETAIL`

Short description shown under the card:

```python
CARD_DETAIL = "Today and tomorrow"
```

## Card Options

Options let users configure cards from the Pixora app.

Example:

```python
CARD_OPTIONS = [
    {
        "key": "zipCode",
        "label": "ZIP",
        "type": "text",
        "default": "02134",
        "maxlength": 5,
        "inputmode": "numeric"
    }
]
```

Inside `render()`:

```python
def render(options=None):
    options = options or {}
    zip_code = options.get("zipCode", "02134")
```

Common option fields:

- `key`: value name passed into `render(options)`
- `label`: label shown in the Pixora UI
- `type`: usually `text`
- `default`: default value
- `maxlength`: optional input length limit
- `inputmode`: optional browser input hint, such as `numeric`

## Rendering Rules

Pixora displays are tiny. Design for:

- `64 x 32` pixels
- high contrast
- short labels
- simple shapes
- no tiny paragraphs
- no soft shadows or blur

Use `WEBP` output:

```python
out = BytesIO()
image.save(out, "WEBP", lossless=True, quality=100)
return out.getvalue()
```

## Fetching Internet Data

Cards can fetch internet data from the Windows Pixora server while rendering.

Use Python's built-in libraries when possible:

```python
import json
import urllib.request


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Pixora Card"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())
```

Cache network results so the card does not hammer an API:

```python
from datetime import datetime, timedelta, timezone

_CACHE = {
    "expires": datetime.min.replace(tzinfo=timezone.utc),
    "data": None,
}
```

## Registry Entry

To make a card downloadable in Pixora, add it to the card registry:

```json
{
  "id": "hello",
  "name": "Hello",
  "category": "Utility",
  "detail": "Simple starter card",
  "description": "Shows HELLO on the display.",
  "author": "your-name",
  "version": "1.0",
  "url": "https://raw.githubusercontent.com/your-name/pixora/main/cards/addons/hello.py"
}
```

The `url` must point directly to the raw `.py` file.

## Suggested GitHub Layout

```text
pixora/cards/
  registry.json
  addons/
    hello.py
    weather.py
```

## Testing A Card

1. Put the card `.py` file in Pixora's local `addons` folder.
2. Restart Pixora.
3. Open the Pixora app.
4. Add the card to a device.
5. Watch the device or preview endpoint.

For registry testing:

1. Push the card to GitHub.
2. Add it to `registry.json`.
3. In Pixora, open **Browse Cards**.
4. Set the registry source if needed.
5. Install the card.

## Starter Template

Use [starter_card.py](starter_card.py) as a copy/paste starting point.
