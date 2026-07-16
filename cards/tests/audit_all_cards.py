import argparse
import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image


CARDS_DIR = Path(__file__).resolve().parents[1]
ADDONS_DIR = CARDS_DIR / "addons"
REGISTRY_FILE = CARDS_DIR / "registry.json"


def registry_cards():
    payload = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return [item for item in payload.get("cards", []) if isinstance(item, dict) and item.get("id")]


def default_options(card):
    options = {}
    for item in card.get("options") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        value = item.get("default")
        if value is not None:
            options[str(item["key"])] = value
    for key in ("zipCode", "homeZip"):
        if key in options and len(str(options[key] or "")) != 5:
            options[key] = "01826"
    return options


def inspect_body(body, expected_width):
    if isinstance(body, bytearray):
        body = bytes(body)
    if not isinstance(body, bytes) or not body:
        return {"status": "empty"}
    with Image.open(io.BytesIO(body)) as image:
        image.load()
        width, height = image.size
        frames = int(getattr(image, "n_frames", 1) or 1)
        fmt = str(image.format or "").upper()
    if fmt != "WEBP":
        return {"status": "malformed", "reason": f"format={fmt or 'unknown'}"}
    if height == 32 and width in (64, 128) and width != expected_width:
        width = expected_width
    if (width, height) != (expected_width, 32):
        return {"status": "malformed", "reason": f"size={width}x{height}"}
    return {"status": "ok", "bytes": len(body), "frames": frames}


def worker(card_id, width, options):
    os.chdir(CARDS_DIR)
    sys.path.insert(0, str(CARDS_DIR))
    sys.path.insert(0, str(ADDONS_DIR))
    path = ADDONS_DIR / f"{card_id}.py"
    if not path.exists():
        return {"card": card_id, "width": width, "status": "missing", "reason": str(path)}
    spec = importlib.util.spec_from_file_location(f"pixora_audit_{card_id}", path)
    if spec is None or spec.loader is None:
        return {"card": card_id, "width": width, "status": "import_error", "reason": "no module loader"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    render = getattr(module, "render", None)
    if not callable(render):
        return {"card": card_id, "width": width, "status": "missing_render"}
    target = "matrixportal-s3-128x32" if width == 128 else "matrixportal-s3"
    runtime = {
        **options,
        "_width": width,
        "_target": target,
        "_pixora_target": "pixora-s3-wide" if width == 128 else "pixora-s3",
        "_pixora_cloud": True,
        "_is_prefetch": True,
        "_dwell": 10,
        "_device_id": f"audit-{width}-{card_id}",
        "_settings": {"defaultZipCode": "01826", "defaultTimezone": "America/New_York", "temperatureUnits": "F"},
    }
    result = render(runtime)
    dwell = 10
    if isinstance(result, dict):
        dwell = int(result.get("dwell_secs") or dwell)
        body = result.get("body")
        if not body and (result.get("deviceGraphic") or result.get("wallGraphic") or result.get("_group_wall")):
            return {"card": card_id, "width": width, "status": "structured", "dwell": dwell}
    else:
        body = result
    inspected = inspect_body(body, width)
    inspected.update({"card": card_id, "width": width, "dwell": dwell})
    return inspected


def run_worker(args):
    try:
        result = worker(args.card, args.width, json.loads(base64.b64decode(args.options).decode("utf-8")))
    except Exception as exc:
        result = {"card": args.card, "width": args.width, "status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, sort_keys=True))
    return 0


def audit_one(card, width, timeout):
    encoded = base64.b64encode(json.dumps(default_options(card)).encode("utf-8")).decode("ascii")
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--card", card["id"], "--width", str(width), "--options", encoded]
    try:
        completed = subprocess.run(command, cwd=CARDS_DIR, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"card": card["id"], "width": width, "status": "timeout", "reason": f">{timeout}s"}
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return {"card": card["id"], "width": width, "status": "worker_error", "reason": completed.stderr.strip()[-500:]}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"card": card["id"], "width": width, "status": "worker_error", "reason": (completed.stdout + completed.stderr)[-500:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--card", default="")
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--options", default="e30=")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--output", default="")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.worker:
        return run_worker(args)

    cards = registry_cards()
    tasks = [(card, width) for card in cards for width in (64, 128)]
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        pending = {executor.submit(audit_one, card, width, args.timeout): (card["id"], width) for card, width in tasks}
        for completed_count, future in enumerate(as_completed(pending), start=1):
            result = future.result()
            results.append(result)
            if not args.quiet or result.get("status") not in ("ok", "empty", "structured"):
                print(json.dumps(result, sort_keys=True), flush=True)
            elif completed_count % 20 == 0:
                print(f"audited {completed_count}/{len(tasks)} renders", flush=True)
    results.sort(key=lambda item: (item.get("card", ""), item.get("width", 0)))
    summary = {}
    for result in results:
        status = result.get("status", "unknown")
        summary[status] = summary.get(status, 0) + 1
    report = {"cards": len(cards), "renders": len(results), "summary": summary, "results": results}
    output = Path(args.output) if args.output else Path(tempfile.gettempdir()) / "pixora-card-audit.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), **report["summary"]}, sort_keys=True))
    return 1 if any(status in summary for status in ("missing", "import_error", "missing_render", "malformed", "error", "timeout", "worker_error")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
