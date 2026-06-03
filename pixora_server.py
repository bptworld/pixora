from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import hashlib
import base64
import binascii
import importlib.util
import json
import os
import re
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import subprocess
import tempfile
import threading
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path


from collections import deque

def app_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = app_root()
os.chdir(ROOT)
APP_NAME = "Pixora"
DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/bptworld/pixora/main/cards/registry.json"
LEGACY_REGISTRY_HOSTS = (
    "raw.githubusercontent.com/bptworld/pixora-cards/",
    "github.com/bptworld/pixora-cards/",
)


def user_root():
    override = os.environ.get("PIXORA_USER_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
    if ROOT.name == ".run-pixora":
        return ROOT.parent
    return ROOT


USER_ROOT = user_root()
if str(USER_ROOT) not in sys.path:
    sys.path.insert(0, str(USER_ROOT))
DATA_DIR = USER_ROOT / "data"
ADDONS_DIR = USER_ROOT / "addons"
GRAPHICS_DIR = DATA_DIR / "graphics"
OTA_DIR = DATA_DIR / "ota"
DEVICES_FILE = DATA_DIR / "devices.json"
GROUPS_FILE = DATA_DIR / "groups.json"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
NEXT_STATE = {}
DEVICE_LAST_POLL = {}
DEVICE_RUNTIME = {}
DEVICE_STORE_LOCK = threading.RLock()
ROTATION_LOCKS = {}
ROTATION_LOCKS_GUARD = threading.Lock()
CARD_REGISTRY = {}
CARD_RENDER_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="pixora-card")
CARD_RENDER_TIMEOUT_SECS = 25
DISABLE_GROUP_WAIT_MESSAGE = True
MESSAGE_STATE = {}
INTERRUPT_STATE = {}  # {device_id: [{"id": str, "body": bytes, "dwell_secs": int, "expires": datetime}]}
WALL_RUN_STATE = {}  # {device_id: [{"id": str, "body": bytes, "start_at": datetime, ...}]}


def virtual_webp_dwell_floor(body):
    try:
        from PIL import Image, ImageSequence
        image = Image.open(BytesIO(body))
        frame_count = int(getattr(image, "n_frames", 1) or 1)
        if frame_count <= 1:
            return None
        total_ms = 0
        for frame in ImageSequence.Iterator(image):
            total_ms += max(20, int(frame.info.get("duration") or image.info.get("duration") or 100))
        if total_ms <= 0:
            return None
        return max(1, min(300, (total_ms + 999) // 1000))
    except Exception:
        return None


def virtual_webp_sprite(body):
    def shifted_match_score(a, b, dx):
        from PIL import ImageChops
        width, height = a.size
        step = abs(dx)
        if step <= 0 or step >= width:
            return 0
        if dx < 0:
            left = a.crop((step, 0, width, height))
            right = b.crop((0, 0, width - step, height))
        else:
            left = a.crop((0, 0, width - step, height))
            right = b.crop((step, 0, width, height))
        diff = ImageChops.difference(left, right).convert("L")
        hist = diff.histogram()
        matching = hist[0]
        return matching / max(1, (width - step) * height)

    def midpoint_frame(a, b, dx):
        from PIL import Image
        width, height = a.size
        direction = -1 if dx < 0 else 1
        mid = Image.new("RGB", (width, height), (0, 0, 0))
        if direction < 0:
            mid.paste(a.crop((1, 0, width, height)), (0, 0))
            mid.paste(b.crop((width - 1, 0, width, height)), (width - 1, 0))
        else:
            mid.paste(a.crop((0, 0, width - 1, height)), (1, 0))
            mid.paste(b.crop((0, 0, 1, height)), (0, 0))
        return mid

    def expand_scrolling_frames(frames, durations):
        expanded_frames = []
        expanded_durations = []
        for index, frame in enumerate(frames):
            next_frame = frames[index + 1] if index + 1 < len(frames) else None
            best_dx = 0
            best_score = 0
            if next_frame is not None:
                for dx in (-4, -3, -2, 2, 3, 4):
                    score = shifted_match_score(frame, next_frame, dx)
                    if score > best_score:
                        best_score = score
                        best_dx = dx
            if best_dx and best_score >= 0.82:
                half = max(20, int(round(durations[index] / 2)))
                expanded_frames.append(frame)
                expanded_durations.append(half)
                expanded_frames.append(midpoint_frame(frame, next_frame, best_dx))
                expanded_durations.append(max(20, durations[index] - half))
            else:
                expanded_frames.append(frame)
                expanded_durations.append(durations[index])
        return expanded_frames, expanded_durations

    try:
        from PIL import Image, ImageSequence
        image = Image.open(BytesIO(body))
        frame_count = int(getattr(image, "n_frames", 1) or 1)
        if frame_count <= 1:
            return None
        frames = []
        durations = []
        max_frames = min(frame_count, 480)
        for index, frame in enumerate(ImageSequence.Iterator(image)):
            if index >= max_frames:
                break
            frames.append(frame.convert("RGB"))
            durations.append(max(20, int(frame.info.get("duration") or image.info.get("duration") or 100)))
        if len(frames) <= 1:
            return None
        width, height = frames[0].size
        expanded_frames, expanded_durations = expand_scrolling_frames(frames, durations)
        if height * len(expanded_frames) <= 16383:
            frames, durations = expanded_frames, expanded_durations
        if width <= 0 or height <= 0 or height * len(frames) > 16383:
            return None
        sprite = Image.new("RGB", (width, height * len(frames)), (0, 0, 0))
        for index, frame in enumerate(frames):
            sprite.paste(frame, (0, index * height))
        out = BytesIO()
        sprite.save(out, "WEBP", lossless=True, quality=100)
        return {
            "body": out.getvalue(),
            "frame_count": len(frames),
            "frame_width": width,
            "frame_height": height,
            "durations": durations,
            "duration_secs": max(1, min(300, (sum(durations) + 999) // 1000)),
        }
    except Exception:
        return None
WALL_READY_STATE = {}  # {run_id: {"ready": set(device_ids), "members": set(device_ids), "released": bool}}
WALL_READY_CONDITION = threading.Condition()
WALL_PLAN_CACHE = {}
WALL_PLAN_CACHE_TTL_SECS = 900
WALL_MIN_ARM_SECONDS = 1.0
WALL_STALE_GRACE_SECONDS = 10.0
WALL_READY_WAIT_SECONDS = 8.0
CARD_ERRORS = {}   # {device_id: {card_id: error_str}}
OTA_PENDING = {}   # {device_id: {"url": ota_url, "version": firmware_version}} - sent on next poll
QH_PENDING  = {}   # {device_id: "en,start_hour,end_hour,utc_offset,start_min,end_min,brightness"}
SWAP_PENDING = {}  # {device_id: "0"|"1"} - sent as Pixora-Swap-Colors on next poll
SETTINGS_FILE = DATA_DIR / "settings.json"
OTA_PENDING_FILE = OTA_DIR / "pending.json"
FLASH_JOB = {"running": False, "done": True, "ok": None, "lines": [], "device": None}
LOG_BUFFER = deque(maxlen=200)
MDNS_HOSTNAME = "pixora.local."
MDNS_SERVICES = []
MQTT_CLIENT = None
MQTT_LOCK = threading.Lock()
MQTT_STATUS = {"enabled": False, "connected": False, "error": "", "subscriptions": []}
ETSY_OAUTH_STATE = {}
ETSY_OAUTH_WORKER_CALLBACK = "https://pixora-etsy-oauth.bptworld.workers.dev/etsy/oauth/callback"
PRIORITY_GRAPHIC_OPTION_KEYS = {
    "runAnimationTarget",
    "goalAnimationTarget",
    "scoreAnimationTarget",
    "launchAnimationTarget",
}
PRIORITY_WATCH_INTERVAL_SECS = 5
PRIORITY_WATCH_STOP = threading.Event()
UPDATE_CHECK_INTERVAL_SECS = 24 * 60 * 60
UPDATE_CHECK_STOP = threading.Event()
UPDATE_CHECK_LOCK = threading.Lock()
UPDATE_STATUS = {
    "checkedAt": "",
    "ok": None,
    "updateAvailable": False,
    "currentVersion": "",
    "latestVersion": "",
    "latestName": "",
    "htmlUrl": "",
    "error": "",
    "source": "",
}
SERVER_PORT = 8088
WINDOWS_STARTUP_VALUE_NAME = "Pixora"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def log(msg):
    entry = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
    LOG_BUFFER.append(entry)
    print(entry, flush=True)


def is_windows():
    return os.name == "nt"


def startup_command():
    args = []
    if getattr(sys, "frozen", False):
        args = [str(Path(sys.executable).resolve())]
    else:
        python_path = Path(sys.executable).resolve()
        pythonw_path = python_path.with_name("pythonw.exe")
        if pythonw_path.exists():
            python_path = pythonw_path
        args = [str(python_path), str(Path(__file__).resolve())]
    args.extend([str(SERVER_PORT), "--no-browser"])
    return subprocess.list2cmdline(args)


def get_windows_startup_status():
    status = {
        "supported": is_windows(),
        "enabled": False,
        "command": "",
        "error": "",
    }
    if not status["supported"]:
        return status
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, WINDOWS_STARTUP_VALUE_NAME)
            except FileNotFoundError:
                value = ""
        expected = startup_command()
        status["command"] = value or expected
        status["enabled"] = bool(value)
        status["matchesCurrentCommand"] = bool(value) and value == expected
    except Exception as error:
        status["error"] = str(error)
    return status


def set_windows_startup_enabled(enabled):
    if not is_windows():
        return {"supported": False, "enabled": False, "command": "", "error": "Windows startup is only available on Windows."}
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, WINDOWS_STARTUP_VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, WINDOWS_STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass
    return get_windows_startup_status()


def exit_process_later(delay_seconds=0.5):
    def worker():
        time.sleep(delay_seconds)
        os._exit(0)

    thread = threading.Thread(target=worker, name="pixora-exit", daemon=False)
    thread.start()


def rotation_lock_for(device_id):
    with ROTATION_LOCKS_GUARD:
        lock = ROTATION_LOCKS.get(device_id)
        if lock is None:
            lock = threading.Lock()
            ROTATION_LOCKS[device_id] = lock
        return lock


def local_ipv4_addresses():
    addresses = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        sock.connect(("8.8.8.8", 80))
        addresses.append(sock.getsockname()[0])
        sock.close()
    except Exception:
        pass

    try:
        for item in socket.gethostbyname_ex(socket.gethostname())[2]:
            if item and not item.startswith("127.") and item not in addresses:
                addresses.append(item)
    except Exception:
        pass

    return addresses or ["127.0.0.1"]


def pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def oauth_token_text(length=48):
    return base64.urlsafe_b64encode(os.urandom(length)).decode("ascii").rstrip("=")


def etsy_redirect_uri(handler):
    settings = read_settings()
    return str(settings.get("etsyOAuthRedirectUri") or ETSY_OAUTH_WORKER_CALLBACK).strip()


def exchange_etsy_oauth_code(oauth_state, code):
    form = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": oauth_state["client_id"],
        "redirect_uri": oauth_state["redirect_uri"],
        "code": code,
        "code_verifier": oauth_state["code_verifier"],
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.etsy.com/v3/public/oauth/token",
        data=form,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Pixora/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        token = json.loads(response.read().decode("utf-8"))
    if not token.get("access_token"):
        raise ValueError("Etsy did not return an access token.")
    return token


def prune_etsy_oauth_state():
    now = datetime.now(timezone.utc)
    for state, item in list(ETSY_OAUTH_STATE.items()):
        created = item.get("created")
        if not created or (now - created).total_seconds() > 900:
            ETSY_OAUTH_STATE.pop(state, None)


def ota_server_base(remote_url, device_ip=""):
    try:
        uri = urllib.parse.urlparse(remote_url)
        port = uri.port or (443 if uri.scheme == "https" else 80)
    except Exception:
        port = 8088

    addresses = [ip for ip in local_ipv4_addresses() if not ip.startswith("127.")]
    device_parts = (device_ip or "").split(".")
    if len(device_parts) == 4:
        device_prefix = ".".join(device_parts[:3]) + "."
        for ip in addresses:
            if ip.startswith(device_prefix):
                return f"http://{ip}:{port}"

    if addresses:
        return f"http://{addresses[0]}:{port}"

    return re.sub(r"/[^/]+/next/?$", "", remote_url).rstrip("/")


def firmware_file_matches_target_name(filename, target):
    name = Path(str(filename or "")).name.lower()
    target = canonical_device_target(target) or ""
    if target == "tidbyt-gen1":
        display = "tidbyt"
    elif target == "matrixportal-s3-128x32":
        display = "128x32"
    elif target == "matrixportal-s3-64x32":
        display = "64x32"
    else:
        display = target
    return bool(display and f"-{display.lower()}-" in name)


def firmware_file_is_ota(filename):
    name = Path(str(filename or "")).name.lower()
    return name.endswith("-ota-firmware.bin")


def firmware_file_is_usb_full_flash(filename):
    name = Path(str(filename or "")).name.lower()
    return name.endswith("-usb-full-flash.bin")


def start_mdns(port):
    try:
        from zeroconf import IPVersion, ServiceInfo, Zeroconf
    except Exception as error:
        log(f"mDNS unavailable: install Python package 'zeroconf' ({error})")
        return None

    try:
        zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        addresses = [socket.inet_aton(ip) for ip in local_ipv4_addresses()]
        props = {"path": "/index.html", "role": "pixora-server"}
        for service_type, instance, server_name in (
            ("_pixora._tcp.local.", "Pixora._pixora._tcp.local.", "pixora.local."),
            ("_http._tcp.local.", "Pixora._http._tcp.local.", "pixora.local."),
        ):
            info = ServiceInfo(
                service_type,
                instance,
                addresses=addresses,
                port=port,
                properties=props,
                server=server_name,
            )
            zeroconf.register_service(info)
            MDNS_SERVICES.append(info)
        log(f"mDNS: Pixora server advertised as http://pixora.local:{port}/")
        return zeroconf
    except Exception as error:
        log(f"mDNS failed to start: {error}")
        try:
            zeroconf.close()
        except Exception:
            pass
        return None


def stop_mdns(zeroconf):
    if not zeroconf:
        return
    for service in MDNS_SERVICES:
        try:
            zeroconf.unregister_service(service)
        except Exception:
            pass
    zeroconf.close()

for import_path in (ROOT, ROOT / "addons", ADDONS_DIR):
    text_path = str(import_path)
    if text_path not in sys.path:
        sys.path.insert(0, text_path)

from card_utils import (
    render_text_webp, weather_for_zip,
    parse_color, render_message_wrap, render_message_scroll, render_message_flash,
)


def read_settings():
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def write_settings(settings):
    DATA_DIR.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def ensure_user_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ADDONS_DIR.mkdir(parents=True, exist_ok=True)
    GRAPHICS_DIR.mkdir(parents=True, exist_ok=True)


def graphics_manifest_path():
    return GRAPHICS_DIR / "graphics.json"


def read_graphics():
    try:
        if graphics_manifest_path().exists():
            data = json.loads(graphics_manifest_path().read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def write_graphics(items):
    ensure_user_dirs()
    graphics_manifest_path().write_text(json.dumps(items, indent=2), encoding="utf-8")


def graphic_file_path(graphic_id):
    graphic_id = str(graphic_id or "").strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", graphic_id):
        return None
    return GRAPHICS_DIR / f"{graphic_id}.png"


def graphic_by_id(graphic_id):
    for item in read_graphics():
        if str(item.get("id") or "") == str(graphic_id or ""):
            return item
    return None


def app_version_file():
    for path in (
        ROOT / "VERSION",
        ROOT / "firmware" / "pixora-firmware" / "main" / "version.h",
    ):
        if path.exists():
            return path
    return ROOT / "VERSION"


def quiet_brightness():
    try:
        value = int(read_settings().get("quietBrightness", 5))
    except Exception:
        value = 5
    return max(0, min(100, value))


def _local_utc_offset_hours():
    try:
        offset = datetime.now().astimezone().utcoffset() or timedelta()
        return int(round(offset.total_seconds() / 3600))
    except Exception:
        return 0


def is_loopback_ip(value):
    text = str(value or "").strip().lower()
    return text in {"127.0.0.1", "::1", "localhost"} or text.startswith("127.")


def _quiet_time_parts(value, fallback):
    text = _valid_time_text(value, fallback)
    hour, minute = text.split(":")
    hour = int(hour)
    minute = int(minute)
    return hour, minute, hour * 60 + minute


def queue_device_quiet_hours_sync(device, qh=None, utc_offset=None, push=False):
    if not isinstance(device, dict) or not device.get("id"):
        return {"pushed": False, "error": "Invalid device"}
    device_id = device.get("id")
    qh = qh if isinstance(qh, dict) else device.get("quietHours", {})
    qh = qh if isinstance(qh, dict) else {}
    en = 1 if qh.get("enabled", False) else 0
    start_hour, start_minute, start_total = _quiet_time_parts(qh.get("start", "22:00"), "22:00")
    end_hour, end_minute, end_total = _quiet_time_parts(qh.get("end", "06:00"), "06:00")
    if utc_offset is None:
        utc_offset = _local_utc_offset_hours()
    brightness = quiet_brightness()
    qh_value = f"{en},{start_hour},{end_hour},{int(utc_offset)},{start_total},{end_total},{brightness}"
    QH_PENDING[device_id] = qh_value
    log(f"[qh] Queued quiet hours for {device_id}: {qh_value}")

    pushed = False
    push_error = ""
    if push:
        last_ip = str(device.get("lastIp", "")).strip()
        if last_ip:
            try:
                body = json.dumps({
                    "enabled": bool(en),
                    "start": start_hour,
                    "end": end_hour,
                    "start_min": start_total,
                    "end_min": end_total,
                    "utc_offset": int(utc_offset),
                    "brightness": brightness,
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"http://{last_ip}/quiet-hours",
                    data=body,
                    headers={"Content-Type": "application/json", "User-Agent": "Pixora/0.1"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3):
                    pass
                pushed = True
                QH_PENDING.pop(device_id, None)
                log(f"[qh] Synced quiet hours directly to {device_id} at {last_ip}: {en},{start_hour:02d}:{start_minute:02d},{end_hour:02d}:{end_minute:02d},{int(utc_offset)},brightness={brightness}")
            except Exception as e:
                push_error = str(e)
                log(f"[qh] Direct quiet-hours sync skipped for {device_id} at {last_ip}: {push_error}")
    return {"pushed": pushed, "error": push_error}


def default_device_fields():
    settings = read_settings()
    try:
        brightness = max(1, min(100, int(settings.get("defaultBrightness", 50))))
    except Exception:
        brightness = 50
    return {
        "brightness": brightness,
        "quietHours": {
            "enabled": True,
            "start": _valid_time_text(settings.get("defaultQuietStart"), "22:00"),
            "end": _valid_time_text(settings.get("defaultQuietEnd"), "06:00"),
        },
    }


def normalize_registry_url(value):
    url = str(value or "").strip()
    if not url:
        return DEFAULT_REGISTRY_URL
    lowered = url.lower()
    if any(host in lowered for host in LEGACY_REGISTRY_HOSTS):
        return DEFAULT_REGISTRY_URL
    return url


def get_registry_url(settings=None):
    settings = settings if settings is not None else read_settings()
    return normalize_registry_url(settings.get("registryUrl"))


def load_card_file(path):
    try:
        spec = importlib.util.spec_from_file_location(f"pixora_addon_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        card_id = getattr(mod, "CARD_ID", path.stem)
        CARD_REGISTRY[card_id] = {
            "id": card_id,
            "name": getattr(mod, "CARD_NAME", card_id),
            "category": getattr(mod, "CARD_CATEGORY", ""),
            "detail": getattr(mod, "CARD_DETAIL", ""),
            "options": getattr(mod, "CARD_OPTIONS", []),
            "render": mod.render,
            "module": mod,
        }
        log(f"Loaded card: {card_id}")
        return card_id
    except Exception as e:
        log(f"Failed to load addon {path.name}: {e}")
        return None


def load_cards():
    for addons_dir in (ROOT / "addons", ADDONS_DIR):
        if not addons_dir.exists():
            continue
        for path in sorted(addons_dir.glob("*.py")):
            if not path.stem.startswith("_"):
                load_card_file(path)


def clean_env():
    env = os.environ.copy()
    for name in (
        "IDF_PYTHON_ENV_PATH",
        "ESP_IDF_PYTHON_ENV_PATH",
        "IDF_TOOLS_EXPORT_CMD",
        "IDF_DEACTIVATE_FILE_PATH",
        "VIRTUAL_ENV",
        "PYTHONHOME",
    ):
        env.pop(name, None)
    env["PATH"] = os.pathsep.join(
        part
        for part in env.get("PATH", "").split(os.pathsep)
        if part and ".espressif\\python_env" not in part.lower()
    )
    return env


def firmware_cache_key(target, ssid, password, remote_url):
    key = json.dumps(
        {
            "target": target,
            "ssid": ssid,
            "password": password,
            "remoteUrl": remote_url,
            "firmware": firmware_build_stamp(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def firmware_build_stamp():
    version_path = app_version_file()
    try:
        text = version_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'FIRMWARE_VERSION\s+"([^"]+)"', text)
        if match:
            return match.group(1)
        text = text.strip()
        if re.match(r"^\d+\.\d+\.\d+([-.][A-Za-z0-9]+)?$", text):
            return text
    except Exception:
        pass
    try:
        return str(int(version_path.stat().st_mtime))
    except Exception:
        return "unknown"


def version_tuple(value):
    nums = re.findall(r"\d+", str(value or ""))
    return tuple(int(n) for n in nums[:4]) or (0,)


def github_update_repo(settings=None):
    settings = settings or read_settings()
    owner = str(settings.get("updateRepoOwner") or "bptworld").strip() or "bptworld"
    repo = str(settings.get("updateRepoName") or "pixora").strip() or "pixora"
    return owner, repo


def fetch_github_latest_release(owner, repo):
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/releases?per_page=30"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Pixora/0.1",
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    releases = data if isinstance(data, list) else []
    candidates = []
    for release in releases:
        tag = str(release.get("tag_name") or release.get("name") or "").strip()
        if re.search(r"\d+", tag):
            candidates.append((version_tuple(tag), release))
    if candidates:
        return sorted(candidates, key=lambda row: row[0])[-1][1]

    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Pixora/0.1",
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_pixora_update(force=False):
    now = datetime.now(timezone.utc)
    with UPDATE_CHECK_LOCK:
        checked_at = UPDATE_STATUS.get("checkedAt")
        if not force and checked_at:
            try:
                last = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
                if (now - last).total_seconds() < UPDATE_CHECK_INTERVAL_SECS:
                    return dict(UPDATE_STATUS)
            except Exception:
                pass

        current = firmware_build_stamp()
        owner, repo = github_update_repo()
        latest = {}
        source = "github releases"
        try:
            latest = fetch_github_latest_release(owner, repo)
            latest_version = str(latest.get("tag_name") or latest.get("name") or "").strip()
            latest_version = re.sub(r"^[vV]", "", latest_version)
            update_available = bool(
                latest_version
                and current != "unknown"
                and version_tuple(latest_version) > version_tuple(current)
            )
            UPDATE_STATUS.update({
                "checkedAt": now.isoformat(),
                "ok": True,
                "updateAvailable": update_available,
                "currentVersion": current,
                "latestVersion": latest_version,
                "latestName": latest.get("name") or latest_version,
                "htmlUrl": latest.get("html_url") or f"https://github.com/{owner}/{repo}/releases",
                "error": "" if latest_version else "No GitHub release/package version found.",
                "source": source,
            })
            if update_available:
                log(f"[update] Pixora update available: {current} -> {latest_version}")
            else:
                log(f"[update] Pixora update check complete: current={current} latest={latest_version or 'unknown'}")
        except Exception as error:
            UPDATE_STATUS.update({
                "checkedAt": now.isoformat(),
                "ok": False,
                "updateAvailable": False,
                "currentVersion": current,
                "latestVersion": "",
                "latestName": "",
                "htmlUrl": f"https://github.com/{owner}/{repo}/releases",
                "error": str(error),
                "source": source,
            })
            log(f"[update] Pixora update check failed: {error}")
        return dict(UPDATE_STATUS)


def update_check_loop():
    check_for_pixora_update(force=True)
    while not UPDATE_CHECK_STOP.wait(UPDATE_CHECK_INTERVAL_SECS):
        check_for_pixora_update(force=True)


def start_update_checker():
    threading.Thread(target=update_check_loop, name="pixora-update-check", daemon=True).start()
    log(f"[update] watcher started, interval={UPDATE_CHECK_INTERVAL_SECS}s")


def firmware_image_version(path):
    try:
        blob = path.read_bytes()
        matches = sorted({
            item.decode("ascii", errors="ignore")
            for item in re.findall(rb"\b1\.\d+\.\d+\b", blob)
        }, key=version_tuple, reverse=True)
        if matches:
            return matches[0]
        stamp = firmware_build_stamp()
        if stamp != "unknown" and stamp.encode("ascii", errors="ignore") in blob:
            return stamp
        for candidate in (b"1.3.3", b"1.3.2", b"1.2.2"):
            if candidate in blob:
                return candidate.decode("ascii")
    except Exception:
        pass
    return firmware_build_stamp()


def strip_ansi(value):
    return re.sub(r"\x1b\[[0-9;]*m", "", value or "")


def summarize_command_error(output):
    clean = strip_ansi(output)
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if re.search(r"(wrong boot mode|download mode)", clean, re.I):
        return (
            "The display did not enter ESP32 download mode.\n"
            "Unplug it, plug it back in with the USB-A to USB-C cable, then press Build and Flash USB again."
        )
    important = [
        line for line in lines
        if re.search(r"(fatal error|error:|failed|not found|timed out)", line, re.I)
        and not re.search(r"^exception:", line, re.I)
        and ".ps1:" not in line.lower()
    ]
    if important:
        return "\n".join(important[-6:])
    return "\n".join(lines[-8:]) or "Unknown error."


def device_id_from_remote_url(remote_url):
    match = re.search(r"https?://[^/]+/([^/?#]+)/next", remote_url or "", re.I)
    raw = match.group(1) if match else "display"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-")
    return cleaned or "display"


def canonical_device_target(target):
    value = str(target or "").strip().lower()
    if value in ("matrixportal-s3-waveshare", "matrixportal-s3", "waveshare"):
        return "matrixportal-s3-64x32"
    if value in ("matrixportal-s3-64x32", "matrixportal-s3-128x32", "tidbyt-gen1"):
        return value
    return ""


def infer_device_target(device):
    if not isinstance(device, dict):
        return ""
    target = canonical_device_target(device.get("target"))
    if target:
        return target
    text = " ".join(
        str(device.get(key) or "").lower()
        for key in ("id", "name", "endpoint", "server")
    )
    if "128" in text:
        return "matrixportal-s3-128x32"
    if "64" in text:
        return "matrixportal-s3-64x32"
    if "tidbyt" in text or "display" in text:
        return "tidbyt-gen1"
    return "matrixportal-s3-64x32"


def normalize_device_record(device):
    clean = dict(device)
    clean["target"] = infer_device_target(clean)
    return clean


def total_device_cards(devices):
    total = 0
    for device in devices or []:
        cards = device.get("cards") if isinstance(device, dict) else None
        if isinstance(cards, list):
            total += len(cards)
    return total


def merge_duplicate_devices(devices):
    merged = {}
    order = []
    for device in devices or []:
        if not isinstance(device, dict):
            continue
        device_id = str(device.get("id") or "").strip()
        if not device_id:
            continue
        if device_id not in merged:
            merged[device_id] = dict(device)
            order.append(device_id)
            continue
        existing = merged[device_id]
        existing_cards = existing.get("cards") if isinstance(existing.get("cards"), list) else []
        incoming_cards = device.get("cards") if isinstance(device.get("cards"), list) else []
        combined = {**existing, **device}
        if len(existing_cards) >= len(incoming_cards):
            combined["cards"] = existing_cards
        elif incoming_cards:
            combined["cards"] = incoming_cards
        for key in ("brightness", "quietHours", "name", "createdAt"):
            if existing.get(key) is not None and device.get(key) is None:
                combined[key] = existing.get(key)
        merged[device_id] = combined
        log(f"[device] merged duplicate device record for {device_id}; kept {len(combined.get('cards') or [])} card(s)")
    return [merged[device_id] for device_id in order]


def _write_devices_file_unlocked(devices, reason="save"):
    DATA_DIR.mkdir(exist_ok=True)
    clean = merge_duplicate_devices([normalize_device_record(item) for item in devices if isinstance(item, dict)])
    if DEVICES_FILE.exists():
        try:
            old = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
            old_devices = old if isinstance(old, list) else [old]
            if total_device_cards(clean) < total_device_cards(old_devices):
                backup_dir = DATA_DIR / "backups"
                backup_dir.mkdir(exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup = backup_dir / f"devices-before-{reason}-{stamp}.json"
                shutil.copy2(DEVICES_FILE, backup)
                log(f"[backup] saved {backup.name} before device card count changed")
        except Exception as error:
            log(f"[backup] skipped device backup: {error}")
    tmp_file = DEVICES_FILE.with_name(f"{DEVICES_FILE.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
    tmp_file.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp_file, DEVICES_FILE)
            break
        except PermissionError:
            if attempt == 19:
                try:
                    tmp_file.unlink(missing_ok=True)
                except Exception:
                    pass
                raise
            time.sleep(0.05)
    return clean


def write_devices_file(devices, reason="save"):
    with DEVICE_STORE_LOCK:
        return _write_devices_file_unlocked(devices, reason=reason)


def _read_devices_unlocked():
    for attempt in range(3):
        try:
            if DEVICES_FILE.exists():
                data = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [normalize_device_record(item) for item in data if isinstance(item, dict)]
                if isinstance(data, dict):
                    return [normalize_device_record(data)]
        except Exception as error:
            if attempt == 2:
                log(f"[device] could not read {DEVICES_FILE.name}: {error}")
                return []
            time.sleep(0.05)
    return []


def read_devices():
    with DEVICE_STORE_LOCK:
        return _read_devices_unlocked()


def read_groups():
    try:
        if GROUPS_FILE.exists():
            data = json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass
    return []


def write_groups(groups):
    DATA_DIR.mkdir(exist_ok=True)
    clean = []
    for group in groups:
        group_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(group.get("id") or "")).strip("-")
        name = str(group.get("name") or group_id or "Device Group").strip()
        device_ids = []
        for device_id in group.get("deviceIds") or []:
            device_id = str(device_id or "").strip()
            if device_id and device_id not in device_ids:
                device_ids.append(device_id)
            if len(device_ids) >= 3:
                break
        if group_id and device_ids:
            clean.append({"id": group_id, "name": name, "deviceIds": device_ids})
    GROUPS_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return clean


def device_width(device):
    target = str((device or {}).get("target") or "").lower()
    if "128x32" in target:
        return 128
    return 64


def queue_interrupt(device_id, body, dwell_secs=6, priority=100, label="interrupt", start_at=None):
    if not body:
        return None
    now = datetime.now(timezone.utc)
    interrupt_id = uuid.uuid4().hex[:12]
    item = {
        "id": interrupt_id,
        "body": body,
        "dwell_secs": max(1, min(300, int(dwell_secs or 6))),
        "priority": int(priority),
        "label": label,
        "expires": now + timedelta(seconds=300),
    }
    if start_at is not None:
        item["start_at"] = start_at
    queue = INTERRUPT_STATE.setdefault(device_id, [])
    queue.append(item)
    queue.sort(key=lambda entry: -int(entry.get("priority") or 0))
    NEXT_STATE.pop(device_id, None)
    return interrupt_id


def queue_wall_frame(
    device_id,
    body,
    dwell_secs=8,
    priority=200,
    label="wall",
    start_at=None,
    run_id=None,
    group_id=None,
    group_members=None,
    total_width=None,
    slice_x=None,
    slice_width=None,
    frame_count=None,
    animation_ms=None,
    arm_seconds=None,
):
    if not body:
        return None
    now = datetime.now(timezone.utc)
    run_id = run_id or uuid.uuid4().hex[:12]
    item = {
        "id": run_id,
        "body": body,
        "dwell_secs": max(1, min(300, int(dwell_secs or 8))),
        "priority": int(priority),
        "label": label,
        "group_id": group_id,
        "group_members": list(group_members or []),
        "start_at": start_at or now,
        "queued_at": now,
        "expires": now + timedelta(seconds=300),
        "total_width": total_width,
        "slice_x": slice_x,
        "slice_width": slice_width,
        "frame_count": frame_count,
        "animation_ms": animation_ms,
        "arm_seconds": arm_seconds,
    }
    queue = WALL_RUN_STATE.setdefault(device_id, [])
    queue.append(item)
    queue.sort(
        key=lambda entry: (
            entry.get("start_at", now),
            -int(entry.get("priority") or 0),
        )
    )
    members = {str(member) for member in (group_members or []) if str(member or "").strip()}
    if run_id and members:
        with WALL_READY_CONDITION:
            state = WALL_READY_STATE.setdefault(
                run_id,
                {"ready": set(), "members": set(members), "released": False, "release_start_at": None},
            )
            state["members"].update(members)
            WALL_READY_CONDITION.notify_all()
    NEXT_STATE.pop(device_id, None)
    return run_id


def wall_run_items(run_id):
    items = []
    for queue in WALL_RUN_STATE.values():
        for item in queue:
            if item.get("id") == run_id:
                items.append(item)
    return items


def wait_for_wall_run_ready(item, device_id):
    run_id = item.get("id")
    members = {str(member) for member in (item.get("group_members") or []) if str(member or "").strip()}
    if not run_id or not members or device_id not in members:
        return item
    deadline = time.monotonic() + WALL_READY_WAIT_SECONDS
    with WALL_READY_CONDITION:
        state = WALL_READY_STATE.setdefault(
            run_id,
            {"ready": set(), "members": set(members), "released": False, "release_start_at": None},
        )
        state["members"].update(members)
        state["ready"].add(device_id)
        while not state.get("released"):
            missing = state["members"] - state["ready"]
            remaining = deadline - time.monotonic()
            if not missing or remaining <= 0:
                current_arm = float(item.get("arm_seconds") or 0)
                arm_seconds = max(
                    WALL_MIN_ARM_SECONDS,
                    current_arm,
                    max((float(entry.get("arm_seconds") or 0) for entry in wall_run_items(run_id)), default=0.0),
                )
                release_start_at = datetime.now(timezone.utc) + timedelta(seconds=arm_seconds)
                state["released"] = True
                state["release_start_at"] = release_start_at
                for entry in wall_run_items(run_id):
                    entry["start_at"] = release_start_at
                if missing:
                    log(f"[wall] released run {run_id} after ready timeout; missing={','.join(sorted(missing))}")
                else:
                    log(f"[wall] released run {run_id}; all members ready={','.join(sorted(state['ready']))}")
                WALL_READY_CONDITION.notify_all()
                break
            WALL_READY_CONDITION.wait(timeout=remaining)
        release_start_at = state.get("release_start_at")
        if isinstance(release_start_at, datetime):
            item["start_at"] = release_start_at
    return item


def pop_wall_frame(device_id, wait_ready=False):
    queue = WALL_RUN_STATE.get(device_id)
    if not queue:
        return None
    now = datetime.now(timezone.utc)
    queue[:] = [
        item for item in queue
        if item.get("expires", datetime.min.replace(tzinfo=timezone.utc)) >= now
    ]
    if not queue:
        WALL_RUN_STATE.pop(device_id, None)
        return None
    ready = []
    for item in queue:
        start_at = item.get("start_at")
        if isinstance(start_at, datetime):
            age = (now - start_at).total_seconds()
            if age > WALL_STALE_GRACE_SECONDS:
                log(f"[wall] dropped stale run {item.get('id')} for {device_id} age={age:.2f}s slice={item.get('slice_x')}+{item.get('slice_width')}/{item.get('total_width')}")
                continue
        ready.append(item)
    queue[:] = ready
    if not queue:
        WALL_RUN_STATE.pop(device_id, None)
        return None
    item = queue.pop(0)
    if not queue:
        WALL_RUN_STATE.pop(device_id, None)
    if wait_ready:
        item = wait_for_wall_run_ready(item, device_id)
    return item


def pop_interrupt(device_id, interrupt_id=None):
    queue = INTERRUPT_STATE.get(device_id)
    if not queue:
        return None
    now = datetime.now(timezone.utc)
    queue[:] = [
        item for item in queue
        if item.get("expires", datetime.min.replace(tzinfo=timezone.utc)) >= now
    ]
    if not queue:
        INTERRUPT_STATE.pop(device_id, None)
        return None
    index = 0
    if interrupt_id:
        match = next((i for i, item in enumerate(queue) if item.get("id") == interrupt_id), None)
        if match is None:
            return None
        index = match
    item = queue.pop(index)
    if not queue:
        INTERRUPT_STATE.pop(device_id, None)
    return item


def group_wait_message_text(value):
    if DISABLE_GROUP_WAIT_MESSAGE:
        return ""
    key = str(value or "blank").strip().lower()
    options = {
        "blank": "",
        "none": "",
        "alert": "** Alert **",
        "message": "Message to Follow",
        "incoming": "Incoming",
        "standby": "Stand By",
    }
    return options.get(key, "")


def render_group_wait_message(text, width):
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    from card_utils import draw_sharp_text

    msg = str(text or "").strip()
    if not msg:
        return None
    width = 128 if int(width or 64) >= 96 else 64
    img = Image.new("RGB", (width, 32), (0, 0, 0))
    try:
        font = ImageFont.truetype(str(ROOT / "assets/fonts/Silkscreen-Regular.ttf"), 8)
    except Exception:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(img)
    words = msg.split()
    lines = [msg]
    if width <= 64 and len(msg) > 10 and len(words) > 1:
        midpoint = max(1, len(words) // 2)
        lines = [" ".join(words[:midpoint]), " ".join(words[midpoint:])]
    elif width > 64 and len(msg) > 18 and len(words) > 1:
        midpoint = max(1, len(words) // 2)
        lines = [" ".join(words[:midpoint]), " ".join(words[midpoint:])]
    bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_h = 8
    start_y = max(0, (32 - (len(lines) * line_h + (len(lines) - 1) * 2)) // 2)
    for index, line in enumerate(lines):
        text_w = bboxes[index][2] - bboxes[index][0]
        x = max(0, (width - text_w) // 2)
        y = start_y + index * (line_h + 2)
        draw_sharp_text(img, (x, y), line, (245, 250, 255), font)
    out = BytesIO()
    img.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def group_scroll_speed(speed):
    speed = str(speed or "normal").strip().lower()
    if speed in ("slow", "easy"):
        return 1, 80
    if speed in ("fast", "quick"):
        return 2, 30
    if speed in ("turbo", "very fast"):
        return 3, 18
    return 2, 55


def group_start_delay_seconds(speed=None, graphic=None, slices=None, plan=None):
    if plan is None:
        plan = {}
    slice_map = plan.get("slices") if isinstance(plan, dict) else None
    if slice_map is None:
        slice_map = slices or {}
    max_bytes = max((len(body) for body in slice_map.values()), default=0)
    member_count = max(1, int((plan or {}).get("member_count") or len(slice_map) or 1))
    frame_count = max(1, int((plan or {}).get("frame_count") or 1))

    # Wall runs are also delivered through /interrupt, so this only needs to
    # cover interrupt polling plus download/decode, not a full card dwell.
    transfer_budget = min(8.0, max_bytes / 18000.0)
    poll_budget = min(2.5, 0.60 * member_count)
    decode_budget = min(1.5, 0.20 + frame_count / 500.0)
    return max(WALL_MIN_ARM_SECONDS, min(15.0, 1.5 + transfer_budget + poll_budget + decode_budget))


def wall_dwell_seconds(requested_dwell, plan):
    animation_ms = int((plan or {}).get("animation_ms") or 0)
    animation_secs = (animation_ms + 999) // 1000
    return max(1, min(300, max(int(requested_dwell or 8), animation_secs + 1)))


def group_graphic_width(graphic):
    graphic = str(graphic or "none").strip().lower()
    custom = custom_graphic_image(graphic)
    if custom:
        return custom.width
    if graphic == "baseball":
        return 14
    if graphic == "arrow":
        return 26
    if graphic == "bullet":
        return 30
    if graphic == "delorean":
        return 44
    return 0


def custom_graphic_image(graphic):
    graphic = str(graphic or "").strip().lower()
    if not graphic.startswith("custom:"):
        return None
    return custom_graphic_image_by_id(graphic.split(":", 1)[1])


@lru_cache(maxsize=64)
def custom_graphic_image_by_id(graphic_id):
    path = graphic_file_path(graphic_id)
    if not path or not path.exists():
        return None
    try:
        from PIL import Image
        img = Image.open(path).convert("RGBA")
        target_h = 16
        scale = target_h / max(1, img.height)
        target_w = max(1, min(44, int(round(img.width * scale))))
        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    except Exception:
        return None


def draw_group_graphic(image, draw, graphic, x, y, frame, total_width):
    graphic = str(graphic or "none").strip().lower()
    custom = custom_graphic_image(graphic)
    if custom:
        image.paste(custom, (int(x), int(y)), custom)
        return
    if graphic == "baseball":
        cx = x + 7
        cy = y + 7
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(245, 245, 235), outline=(190, 190, 180))
        seam_shift = frame % 4
        draw.arc((cx - 5, cy - 5 + seam_shift // 2, cx + 5, cy + 5), 90, 260, fill=(220, 35, 40))
        draw.arc((cx - 5, cy - 5, cx + 5, cy + 5 - seam_shift // 2), 270, 80, fill=(220, 35, 40))
        for dx, dy in ((-2, -3), (-1, 3), (3, -2), (2, 3)):
            draw.point((cx + dx, cy + dy), fill=(220, 35, 40))
        return
    if graphic == "arrow":
        cy = y + 7
        shaft = (170, 115, 62)
        metal = (225, 230, 235)
        feather1 = (255, 60, 65)
        feather2 = (255, 245, 210)
        draw.polygon([(x, cy), (x + 7, cy - 4), (x + 5, cy), (x + 7, cy + 4)], fill=metal)
        draw.line((x + 5, cy, x + 24, cy), fill=shaft)
        draw.polygon([(x + 20, cy), (x + 25, cy - 4), (x + 23, cy)], fill=feather1)
        draw.polygon([(x + 20, cy), (x + 25, cy + 4), (x + 23, cy)], fill=feather2)
        draw.point((x + 10 + (frame % 3), cy - 1), fill=(255, 215, 120))
        return
    if graphic == "bullet":
        cy = y + 7
        body = (185, 190, 195)
        shine = (238, 242, 245)
        shadow = (95, 100, 108)
        gold = (225, 175, 70)
        smoke = [(110, 120, 120), (80, 90, 92), (140, 150, 150)]
        # Pointed gold tip on the left, flat silver casing on the right.
        draw.polygon(
            [(x, cy), (x + 7, cy - 5), (x + 11, cy - 5), (x + 11, cy + 5), (x + 7, cy + 5)],
            fill=gold,
        )
        draw.rectangle((x + 11, cy - 5, x + 23, cy + 5), fill=body)
        draw.line((x + 12, cy - 3, x + 22, cy - 3), fill=shine)
        draw.line((x + 12, cy + 4, x + 22, cy + 4), fill=shadow)
        draw.line((x + 23, cy - 5, x + 23, cy + 5), fill=(70, 72, 78))
        for i, (dx, dy) in enumerate(((24, -3), (27, 1), (30, -1), (33, 3), (36, 0))):
            sx = x + dx + ((frame + i) % 3)
            sy = cy + dy
            draw.point((sx, sy), fill=smoke[i % len(smoke)])
            if i % 2 == 0:
                draw.point((sx + 1, sy), fill=(55, 65, 66))
        return
    if graphic == "delorean":
        body = (150, 154, 156)
        mid = (184, 188, 190)
        bright = (230, 234, 236)
        shadow = (74, 78, 82)
        trim = (24, 27, 30)
        glass = (28, 47, 60)
        car_y = y + 2
        for index, (dx, dy) in enumerate(((38, 12), (42, 10), (45, 13), (49, 11), (53, 14))):
            drift = (frame + index * 2) % 4
            px = x + dx + drift
            py = car_y + dy + ((frame + index) % 2)
            draw.point((px, py), fill=((105, 118, 118), (80, 92, 94), (135, 145, 142))[index % 3])
        draw.polygon(
            [(x + 0, car_y + 8), (x + 9, car_y + 5), (x + 21, car_y + 4), (x + 31, car_y + 6), (x + 36, car_y + 8), (x + 33, car_y + 10), (x + 2, car_y + 10)],
            fill=body,
            outline=bright,
        )
        draw.polygon([(x + 12, car_y + 5), (x + 17, car_y + 2), (x + 26, car_y + 6), (x + 11, car_y + 6)], fill=mid, outline=bright)
        draw.polygon([(x + 15, car_y + 5), (x + 17, car_y + 3), (x + 22, car_y + 6), (x + 14, car_y + 6)], fill=glass)
        draw.line((x + 2, car_y + 8, x + 35, car_y + 8), fill=trim)
        draw.line((x + 8, car_y + 6, x + 32, car_y + 6), fill=(202, 206, 208))
        draw.line((x + 21, car_y + 4, x + 21, car_y + 10), fill=shadow)
        draw.point((x + 1, car_y + 8), fill=(255, 242, 170))
        draw.point((x + 35, car_y + 8), fill=(255, 60, 60))
        draw.ellipse((x + 7, car_y + 8, x + 13, car_y + 14), fill=(8, 10, 12), outline=(210, 216, 218))
        draw.ellipse((x + 25, car_y + 8, x + 31, car_y + 14), fill=(8, 10, 12), outline=(210, 216, 218))


def render_group_scroll_plan(group, text, color_rgb=(245, 250, 255), dwell_secs=8, speed="normal", graphic="none", waiting_message=""):
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    from card_utils import draw_sharp_text

    devices_by_id = {d.get("id"): d for d in read_devices()}
    members = [devices_by_id.get(device_id) for device_id in group.get("deviceIds") or []]
    members = [device for device in members if device]
    if not members:
        return {"slices": {}}

    widths = [device_width(device) for device in members]
    total_width = sum(widths)
    height = 32
    try:
        font = ImageFont.truetype(str(ROOT / "assets/fonts/Silkscreen-Regular.ttf"), 8)
    except Exception:
        font = ImageFont.load_default()
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    msg = str(text or "").strip() or "Pixora Alert"
    text_w = dummy.textbbox((0, 0), msg, font=font)[2]
    px_per_frame, frame_ms = group_scroll_speed(speed)
    graphic_w = group_graphic_width(graphic)
    gap = 8 if graphic_w else 0
    content_w = graphic_w + gap + text_w
    total_steps = total_width + content_w + 24
    waiting_message = str(waiting_message or "").strip()
    wait_ms = 1200 if waiting_message else 0
    frames = []
    for step in range(0, total_steps, px_per_frame):
        img = Image.new("RGB", (total_width, height), (0, 0, 0))
        x = total_width - step
        draw = ImageDraw.Draw(img)
        if graphic_w:
            draw_group_graphic(img, draw, graphic, x, 9, step // max(1, px_per_frame), total_width)
        draw_sharp_text(img, (x + graphic_w + gap, 11), msg, color_rgb, font)
        frames.append(img)

    slices = {}
    slice_meta = {}
    x_offset = 0
    for device, width in zip(members, widths):
        device_frames = [frame.crop((x_offset, 0, x_offset + width, height)) for frame in frames]
        durations = [frame_ms] * len(device_frames)
        if wait_ms:
            wall_wait_img = Image.new("RGB", (total_width, height), (0, 0, 0))
            wall_wait_draw = ImageDraw.Draw(wall_wait_img)
            wb = wall_wait_draw.textbbox((0, 0), waiting_message, font=font)
            wait_x = max(0, (total_width - (wb[2] - wb[0])) // 2)
            draw_sharp_text(wall_wait_img, (wait_x, 11), waiting_message, (245, 250, 255), font)
            device_frames.insert(0, wall_wait_img.crop((x_offset, 0, x_offset + width, height)))
            durations.insert(0, wait_ms)
        out = BytesIO()
        device_frames[0].save(
            out,
            "WEBP",
            save_all=True,
            append_images=device_frames[1:],
            duration=durations,
            loop=1,
            lossless=True,
            quality=100,
        )
        slices[device["id"]] = out.getvalue()
        slice_meta[device["id"]] = {"x": x_offset, "width": width}
        x_offset += width
    frame_count = len(frames) + (1 if wait_ms else 0)
    animation_ms = (len(frames) * frame_ms) + wait_ms
    return {
        "slices": slices,
        "slice_meta": slice_meta,
        "member_count": len(members),
        "widths": widths,
        "total_width": total_width,
        "frame_count": frame_count,
        "frame_ms": frame_ms,
        "animation_ms": animation_ms,
    }


def group_for_device_id(device_id):
    device_id = str(device_id or "").strip()
    if not device_id:
        return None
    groups = read_groups()
    preferred = next(
        (
            group for group in groups
            if group.get("id") == "main-wall" and device_id in (group.get("deviceIds") or [])
        ),
        None,
    )
    if preferred:
        return preferred
    return next(
        (group for group in groups if device_id in (group.get("deviceIds") or [])),
        None,
    )


def render_mlb_run_wall_plan(group, mlb_module, team):
    from io import BytesIO

    devices_by_id = {d.get("id"): d for d in read_devices()}
    members = [devices_by_id.get(device_id) for device_id in group.get("deviceIds") or []]
    members = [device for device in members if device]
    if not members:
        return {"slices": {}}
    if not mlb_module or not hasattr(mlb_module, "_render_run_animation_frames"):
        return {"slices": {}}

    widths = [device_width(device) for device in members]
    total_width = sum(widths)
    team_for_wall = dict(team or {})
    team_for_wall["_width"] = total_width
    team_for_wall["_wall"] = True
    team_for_wall["_wall_members"] = len(members)
    team_for_wall["_wall_widths"] = widths
    frames, durations = mlb_module._render_run_animation_frames(team_for_wall)
    if not frames:
        return {"slices": {}}

    slices = {}
    slice_meta = {}
    x_offset = 0
    for device, width in zip(members, widths):
        device_frames = [frame.crop((x_offset, 0, x_offset + width, 32)) for frame in frames]
        out = BytesIO()
        device_frames[0].save(
            out,
            "WEBP",
            save_all=True,
            append_images=device_frames[1:],
            duration=durations,
            loop=1,
            lossless=True,
            quality=100,
        )
        slices[device["id"]] = out.getvalue()
        slice_meta[device["id"]] = {"x": x_offset, "width": width}
        x_offset += width

    return {
        "slices": slices,
        "slice_meta": slice_meta,
        "member_count": len(members),
        "widths": widths,
        "total_width": total_width,
        "frame_count": len(frames),
        "animation_ms": sum(int(duration or 0) for duration in durations),
    }


def queue_mlb_run_wall(group, mlb_module, team, dwell_secs=6, priority=220, source="mlb"):
    wall_plan = render_mlb_run_wall_plan(group, mlb_module, team)
    slices = wall_plan.get("slices", {})
    if not slices:
        return None

    lead_seconds = group_start_delay_seconds(plan=wall_plan)
    start_at = datetime.now(timezone.utc) + timedelta(seconds=lead_seconds)
    wall_dwell = wall_dwell_seconds(dwell_secs, wall_plan)
    run_id = uuid.uuid4().hex[:12]
    slice_meta = wall_plan.get("slice_meta", {})
    queued = []
    for device_id, body in slices.items():
        meta = slice_meta.get(device_id, {})
        queue_wall_frame(
            device_id,
            body,
            dwell_secs=wall_dwell,
            priority=priority,
            label=f"{source}:mlb-run",
            start_at=start_at,
            run_id=run_id,
            group_id=group.get("id"),
            group_members=list(slices.keys()),
            total_width=wall_plan.get("total_width"),
            slice_x=meta.get("x"),
            slice_width=meta.get("width"),
            frame_count=wall_plan.get("frame_count"),
            animation_ms=wall_plan.get("animation_ms"),
            arm_seconds=lead_seconds,
        )
        MESSAGE_STATE.pop(device_id, None)
        queued.append(device_id)

    team_name = (team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "MLB"
    log(f"[{source}] scheduled MLB run wall {run_id} {wall_plan.get('total_width')}x32 for group '{group.get('id')}' team={team_name} lead={lead_seconds:.2f}s dwell={wall_dwell}s frames={wall_plan.get('frame_count')}: {', '.join(queued)}")
    return {
        "runId": run_id,
        "queued": queued,
        "startsAt": start_at.isoformat(),
        "leadSeconds": lead_seconds,
        "wall": {
            "width": wall_plan.get("total_width"),
            "height": 32,
            "frames": wall_plan.get("frame_count"),
            "animationMs": wall_plan.get("animation_ms"),
            "dwellSeconds": wall_dwell,
        },
    }


def _wall_team_signature(team):
    team = team or {}
    try:
        payload = json.dumps(
            {
                key: team.get(key)
                for key in ("abbreviation", "shortDisplayName", "displayName", "name", "logo", "color", "alternateColor")
            },
            sort_keys=True,
            default=str,
        )
    except Exception:
        payload = repr(team)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def wall_plan_cache_key(group, module, renderer_name, team, kind=None):
    devices_by_id = {d.get("id"): d for d in read_devices()}
    members = [devices_by_id.get(device_id) for device_id in (group or {}).get("deviceIds") or []]
    layout = [
        [device.get("id"), device_width(device)]
        for device in members
        if device
    ]
    module_id = getattr(module, "CARD_ID", getattr(module, "__name__", "module"))
    payload = {
        "group": (group or {}).get("id"),
        "layout": layout,
        "module": module_id,
        "renderer": renderer_name,
        "kind": kind,
        "team": _wall_team_signature(team),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def cached_wall_plan(group, module, renderer_name, team, kind=None, render=None):
    now = datetime.now(timezone.utc)
    for key, item in list(WALL_PLAN_CACHE.items()):
        if (now - item.get("seen", now)).total_seconds() > WALL_PLAN_CACHE_TTL_SECS:
            WALL_PLAN_CACHE.pop(key, None)
    key = wall_plan_cache_key(group, module, renderer_name, team, kind=kind)
    cached = WALL_PLAN_CACHE.get(key)
    if cached:
        cached["seen"] = now
        return cached.get("plan") or {"slices": {}}
    plan = render() if render else {"slices": {}}
    if plan.get("slices"):
        WALL_PLAN_CACHE[key] = {"plan": plan, "seen": now}
    return plan


def render_sports_moment_wall_plan_uncached(group, module, renderer_name, team, kind=None):
    from io import BytesIO

    devices_by_id = {d.get("id"): d for d in read_devices()}
    members = [devices_by_id.get(device_id) for device_id in group.get("deviceIds") or []]
    members = [device for device in members if device]
    renderer = getattr(module, renderer_name or "", None)
    if not members or not renderer:
        return {"slices": {}}

    widths = [device_width(device) for device in members]
    total_width = sum(widths)
    team_for_wall = dict(team or {})
    team_for_wall["_width"] = total_width
    team_for_wall["_wall"] = True
    team_for_wall["_wall_members"] = len(members)
    if kind is None:
        frames, durations = renderer(team_for_wall)
    else:
        frames, durations = renderer(team_for_wall, kind)
    if not frames:
        return {"slices": {}}

    slices = {}
    slice_meta = {}
    x_offset = 0
    for device, width in zip(members, widths):
        device_frames = [frame.crop((x_offset, 0, x_offset + width, 32)) for frame in frames]
        out = BytesIO()
        device_frames[0].save(
            out,
            "WEBP",
            save_all=True,
            append_images=device_frames[1:],
            duration=durations,
            loop=1,
            lossless=True,
            quality=100,
        )
        slices[device["id"]] = out.getvalue()
        slice_meta[device["id"]] = {"x": x_offset, "width": width}
        x_offset += width

    return {
        "slices": slices,
        "slice_meta": slice_meta,
        "member_count": len(members),
        "widths": widths,
        "total_width": total_width,
        "frame_count": len(frames),
        "animation_ms": sum(int(duration or 0) for duration in durations),
    }


def render_sports_moment_wall_plan(group, module, renderer_name, team, kind=None):
    return cached_wall_plan(
        group,
        module,
        renderer_name,
        team,
        kind=kind,
        render=lambda: render_sports_moment_wall_plan_uncached(group, module, renderer_name, team, kind=kind),
    )


def queue_sports_moment_wall(group, module, renderer_name, team, kind=None, dwell_secs=6, priority=220, source="sports", label="moment"):
    wall_plan = render_sports_moment_wall_plan(group, module, renderer_name, team, kind=kind)
    slices = wall_plan.get("slices", {})
    if not slices:
        return None

    lead_seconds = group_start_delay_seconds(plan=wall_plan)
    start_at = datetime.now(timezone.utc) + timedelta(seconds=lead_seconds)
    wall_dwell = wall_dwell_seconds(dwell_secs, wall_plan)
    run_id = uuid.uuid4().hex[:12]
    slice_meta = wall_plan.get("slice_meta", {})
    queued = []
    for device_id, body in slices.items():
        meta = slice_meta.get(device_id, {})
        queue_wall_frame(
            device_id,
            body,
            dwell_secs=wall_dwell,
            priority=priority,
            label=f"{source}:{label}",
            start_at=start_at,
            run_id=run_id,
            group_id=group.get("id"),
            group_members=list(slices.keys()),
            total_width=wall_plan.get("total_width"),
            slice_x=meta.get("x"),
            slice_width=meta.get("width"),
            frame_count=wall_plan.get("frame_count"),
            animation_ms=wall_plan.get("animation_ms"),
            arm_seconds=lead_seconds,
        )
        MESSAGE_STATE.pop(device_id, None)
        queued.append(device_id)

    team_name = (team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "TEAM"
    log(f"[{source}] scheduled sports wall {run_id} {wall_plan.get('total_width')}x32 label={label} team={team_name} kind={kind or ''} group='{group.get('id')}' lead={lead_seconds:.2f}s dwell={wall_dwell}s frames={wall_plan.get('frame_count')}: {', '.join(queued)}")
    return {
        "runId": run_id,
        "queued": queued,
        "startsAt": start_at.isoformat(),
        "leadSeconds": lead_seconds,
        "wall": {
            "width": wall_plan.get("total_width"),
            "height": 32,
            "frames": wall_plan.get("frame_count"),
            "animationMs": wall_plan.get("animation_ms"),
            "dwellSeconds": wall_dwell,
        },
    }


def card_priority_graphic_keys(card_entry):
    keys = []
    for option in (card_entry or {}).get("options") or []:
        if isinstance(option, dict):
            key = option.get("key")
            if key in PRIORITY_GRAPHIC_OPTION_KEYS:
                keys.append(key)
    return keys


def card_priority_target(options):
    for key in PRIORITY_GRAPHIC_OPTION_KEYS:
        value = str((options or {}).get(key) or "").strip().lower()
        if value:
            return value
    return "device"


def card_options_signature(card_id, options):
    clean = {
        key: value
        for key, value in (options or {}).items()
        if not str(key).startswith("_")
    }
    try:
        payload = json.dumps(clean, sort_keys=True, default=str)
    except Exception:
        payload = repr(sorted(clean.items()))
    return hashlib.sha1(f"{card_id}:{payload}".encode("utf-8")).hexdigest()


def queue_priority_card_result(device, card_id, result, dwell_seconds, source="watch"):
    if not isinstance(result, dict):
        return False

    device_id = device.get("id")
    group_wall = result.get("_group_wall")
    if group_wall:
        group = group_for_device_id(device_id)
        module_for_wall = (CARD_REGISTRY.get(card_id) or {}).get("module")
        if not group:
            log(f"[priority] no group contains {device_id}; {card_id} animation stayed off wall")
            return False
        renderer_name = group_wall.get("renderer") or "_render_run_animation_frames"
        queued_wall = queue_sports_moment_wall(
            group,
            module_for_wall,
            renderer_name,
            group_wall.get("team") or {},
            kind=group_wall.get("kind"),
            dwell_secs=group_wall.get("dwell_secs") or result.get("dwell_secs") or 6,
            source=f"{source}:{card_id}:{device_id}",
            label=group_wall.get("type") or "moment",
        )
        if queued_wall:
            log(f"[priority] queued {card_id} graphic on group wall {group.get('id')} from {device_id}")
            return True
        return False

    body = result.get("body")
    is_priority_body = bool(result.get("_no_replay") or result.get("_priority") or result.get("_priority_graphic"))
    if body is not None and is_priority_body:
        dwell_secs = result.get("dwell_secs") or dwell_seconds or 6
        interrupt_id = queue_interrupt(
            device_id,
            body,
            dwell_secs=dwell_secs,
            priority=220,
            label=f"{source}:{card_id}",
        )
        if interrupt_id:
            MESSAGE_STATE.pop(device_id, None)
            log(f"[priority] queued {card_id} graphic for {device_id}")
            return True
    return False


def priority_graphic_watch_once():
    devices = read_devices()
    seen_group_cards = set()
    for device in devices:
        device_id = device.get("id")
        if not device_id or is_quiet_hours(device):
            continue
        cards = device.get("cards") or []
        for card in cards:
            if isinstance(card, dict):
                if card.get("disabled") or not _card_schedule_active(card):
                    continue
                card_id = card.get("id", "clock")
                options = card.get("options") or {}
                dwell_seconds = int(card.get("dwellSeconds", 10) or 10)
            else:
                card_id = str(card or "clock")
                options = {}
                dwell_seconds = 10

            card_entry = CARD_REGISTRY.get(card_id)
            if not card_entry or not card_priority_graphic_keys(card_entry):
                continue

            target = card_priority_target(options)
            if target in ("group", "group_wall", "wall"):
                group = group_for_device_id(device_id)
                group_key = (
                    group.get("id") if group else device_id,
                    card_id,
                    card_options_signature(card_id, options),
                )
                if group_key in seen_group_cards:
                    continue
                seen_group_cards.add(group_key)

            opts_with_meta = {
                **options,
                "_dwell": dwell_seconds,
                "_device_id": device_id,
                "_firmware_version": device.get("firmwareVersion", ""),
                "_target": device.get("target", ""),
                "_refresh_policy": read_settings().get("refreshPolicy", "balanced"),
                "_priority_watch": True,
                "_log": log,
            }
            try:
                future = CARD_RENDER_POOL.submit(card_entry["render"], opts_with_meta)
                result = future.result(timeout=CARD_RENDER_TIMEOUT_SECS)
                queue_priority_card_result(device, card_id, result, dwell_seconds, source="watch")
                CARD_ERRORS.get(device_id, {}).pop(card_id, None)
            except TimeoutError:
                future.cancel()
                CARD_ERRORS.setdefault(device_id, {})[card_id] = f"Priority watch timed out after {CARD_RENDER_TIMEOUT_SECS}s"
                log(f"[priority] {device_id} -> {card_id} watch timed out")
            except Exception as error:
                CARD_ERRORS.setdefault(device_id, {})[card_id] = str(error)
                log(f"[priority] {device_id} -> {card_id} watch skipped: {error}")


def priority_graphic_watch_loop():
    while not PRIORITY_WATCH_STOP.wait(PRIORITY_WATCH_INTERVAL_SECS):
        priority_graphic_watch_once()


def start_priority_graphic_watcher():
    threading.Thread(target=priority_graphic_watch_loop, name="pixora-priority-watch", daemon=True).start()
    log(f"[priority] watcher started, interval={PRIORITY_WATCH_INTERVAL_SECS}s")


def render_group_scroll_slices(group, text, color_rgb=(245, 250, 255), dwell_secs=8, speed="normal", graphic="none", waiting_message=""):
    return render_group_scroll_plan(
        group,
        text,
        color_rgb=color_rgb,
        dwell_secs=dwell_secs,
        speed=speed,
        graphic=graphic,
        waiting_message=waiting_message,
    ).get("slices", {})


def save_device(device):
    with DEVICE_STORE_LOCK:
        DATA_DIR.mkdir(exist_ok=True)
        device = normalize_device_record(device)
        devices = [item for item in _read_devices_unlocked() if item.get("id") != device.get("id")]
        devices.append(device)
        _write_devices_file_unlocked(devices, reason="save")


def delete_device(device_id):
    with DEVICE_STORE_LOCK:
        DATA_DIR.mkdir(exist_ok=True)
        devices = _read_devices_unlocked()
        kept = [item for item in devices if item.get("id") != device_id]
        _write_devices_file_unlocked(kept, reason="delete")
    NEXT_STATE.pop(device_id, None)
    ROTATION_LOCKS.pop(device_id, None)
    MESSAGE_STATE.pop(device_id, None)
    INTERRUPT_STATE.pop(device_id, None)
    WALL_RUN_STATE.pop(device_id, None)
    CARD_ERRORS.pop(device_id, None)
    OTA_PENDING.pop(device_id, None)
    QH_PENDING.pop(device_id, None)
    SWAP_PENDING.pop(device_id, None)
    return len(kept) != len(devices)


def remove_device_card(device_id, card_index):
    with DEVICE_STORE_LOCK:
        devices = _read_devices_unlocked()
        target = next((item for item in devices if item.get("id") == device_id), None)
        if not target:
            return None
        cards = target.get("cards")
        if not isinstance(cards, list) or not (0 <= card_index < len(cards)):
            return None
        removed = cards.pop(card_index)
        _write_devices_file_unlocked(devices, reason="remove-card")
    NEXT_STATE.pop(device_id, None)
    return removed


def update_device(device):
    with DEVICE_STORE_LOCK:
        cards_authoritative = bool(device.pop("_cardsAuthoritative", False))
        deck_mutation = bool(device.pop("_deckMutation", False))
        if not cards_authoritative or not deck_mutation:
            device.pop("cards", None)
        existing = next((item for item in _read_devices_unlocked() if item.get("id") == device.get("id")), {})
        merged = {**existing, **device}
        if "createdAt" not in merged:
            merged["createdAt"] = datetime.now(timezone.utc).isoformat()
        device = normalize_device_record(merged)
        devices = [item for item in _read_devices_unlocked() if item.get("id") != device.get("id")]
        devices.append(device)
        _write_devices_file_unlocked(devices, reason="save")
        return device


def clear_card_option(device_id, card_index, option_key):
    with DEVICE_STORE_LOCK:
        devices = _read_devices_unlocked()
        changed = False
        for device in devices:
            if device.get("id") != device_id:
                continue
            cards = device.get("cards") or []
            if 0 <= card_index < len(cards) and isinstance(cards[card_index], dict):
                options = cards[card_index].get("options") or {}
                if option_key in options:
                    options.pop(option_key, None)
                    cards[card_index]["options"] = options
                    changed = True
        if changed:
            _write_devices_file_unlocked(devices, reason="clear-card-option")
    return changed


def device_for_id(device_id):
    return next((item for item in read_devices() if item.get("id") == device_id), None)


def safe_ota_device_id(device_id):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(device_id or "")).strip("-") or "device"


def ota_firmware_path_for(device_id):
    return OTA_DIR / safe_ota_device_id(device_id) / "firmware.bin"


def ota_url_for_device(device):
    device_id = (device or {}).get("id", "")
    base_url = ota_server_base(
        (device or {}).get("endpoint") or (device or {}).get("server") or "",
        (device or {}).get("lastIp") or "",
    )
    return f"{base_url}/data/ota/{urllib.parse.quote(safe_ota_device_id(device_id))}/firmware.bin"


def save_pending_ota_jobs():
    try:
        OTA_DIR.mkdir(parents=True, exist_ok=True)
        records = []
        for device_id, info in OTA_PENDING.items():
            if isinstance(info, str):
                info = {"url": info, "version": ""}
            records.append({
                "deviceId": device_id,
                "version": str((info or {}).get("version") or ""),
                "queuedAt": str((info or {}).get("queuedAt") or datetime.now(timezone.utc).isoformat()),
                "sentAt": str((info or {}).get("sentAt") or ""),
                "sentFirmware": str((info or {}).get("sentFirmware") or ""),
                "sentUptime": (info or {}).get("sentUptime"),
                "sentCount": int((info or {}).get("sentCount") or 0),
            })
        if records:
            OTA_PENDING_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")
        elif OTA_PENDING_FILE.exists():
            OTA_PENDING_FILE.unlink()
    except Exception as error:
        log(f"[ota] Failed to save pending OTA jobs: {error}")


def load_pending_ota_jobs():
    try:
        if not OTA_PENDING_FILE.exists():
            return
        raw = json.loads(OTA_PENDING_FILE.read_text(encoding="utf-8"))
        records = raw if isinstance(raw, list) else raw.get("jobs", [])
        restored = 0
        for record in records:
            device_id = str((record or {}).get("deviceId") or "").strip()
            if not device_id:
                continue
            device = device_for_id(device_id)
            firmware_path = ota_firmware_path_for(device_id)
            if not device or not firmware_path.is_file():
                continue
            version = str((record or {}).get("version") or "").strip() or firmware_image_version(firmware_path)
            OTA_PENDING[device_id] = {
                "url": ota_url_for_device(device),
                "version": version,
                "queuedAt": str((record or {}).get("queuedAt") or datetime.now(timezone.utc).isoformat()),
                "sentAt": str((record or {}).get("sentAt") or ""),
                "sentFirmware": str((record or {}).get("sentFirmware") or ""),
                "sentUptime": (record or {}).get("sentUptime"),
                "sentCount": int((record or {}).get("sentCount") or 0),
            }
            restored += 1
        if restored:
            log(f"[ota] restored {restored} pending OTA job(s)")
        else:
            save_pending_ota_jobs()
    except Exception as error:
        log(f"[ota] Failed to load pending OTA jobs: {error}")


def group_for_id(group_id):
    group_id = str(group_id or "").strip()
    if not group_id:
        return None
    group_key = group_id.lower()
    for group in read_groups():
        if str(group.get("id") or "").lower() == group_key:
            return group
        if str(group.get("name") or "").lower() == group_key:
            return group
    return None


def devices_for_home_assistant_target(target):
    devices = read_devices()
    if target in (None, "", "*", "all", "ALL"):
        return devices
    values = target if isinstance(target, list) else [target]
    if any(str(value or "").strip().lower() in ("", "*", "all") for value in values):
        return devices
    matches = []
    for value in values:
        key = str(value or "").strip().lower()
        if not key:
            continue
        for device in devices:
            if str(device.get("id") or "").lower() == key or str(device.get("name") or "").lower() == key:
                if device not in matches:
                    matches.append(device)
    return matches


def device_for_path(path_segment):
    """Find device by URL path segment - matches endpoint URL first, then ID."""
    for device in read_devices():
        endpoint = device.get("endpoint", "")
        m = re.search(r"https?://[^/]+/([^/?#]+)/next", endpoint, re.I)
        if m and m.group(1) == path_segment:
            return device
    return device_for_id(path_segment)


def adopt_polling_device(path_segment, client_ip="", firmware_version="", reset_reason="", uptime_text=""):
    device_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(path_segment or "")).strip("-")
    if not device_id or device_id in {"api", "assets", "dist", "favicon.ico"}:
        return None
    existing = device_for_id(device_id)
    if existing:
        return existing
    server = "http://pixora.local:8088"
    device = {
        **default_device_fields(),
        "id": device_id,
        "name": device_id.replace("-", " ").replace("_", " ").title(),
        "server": server,
        "endpoint": f"{server}/{device_id}/next",
        "cards": ["clock"],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    if client_ip and not is_loopback_ip(client_ip):
        device["lastIp"] = client_ip
    if firmware_version:
        device["firmwareVersion"] = firmware_version
    if reset_reason:
        device["lastResetReason"] = reset_reason
    try:
        if uptime_text:
            device["lastUptime"] = int(uptime_text)
    except Exception:
        pass
    save_device(device)
    log(f"[device] adopted polling device {device_id} at {client_ip or 'unknown ip'}")
    return device


def is_quiet_hours(device):
    qh = device.get("quietHours", {})
    if not qh.get("enabled"):
        return False
    try:
        from datetime import time as time_type
        now = datetime.now().time()
        start = time_type.fromisoformat(qh.get("start", "22:00"))
        end = time_type.fromisoformat(qh.get("end", "07:00"))
        if start <= end:
            return start <= now < end
        else:
            return now >= start or now < end
    except Exception:
        return False


def clear_card_runtime_caches():
    def reset_cache_dict(value):
        if "events" in value and "expires" in value:
            value["events"] = []
            value["expires"] = datetime.min.replace(tzinfo=timezone.utc)
            return True
        if "body" in value and "expires" in value:
            value["body"] = b""
            value["expires"] = datetime.min.replace(tzinfo=timezone.utc)
            return True
        if "token" in value and "expires" in value:
            value["token"] = None
            value["expires"] = datetime.min.replace(tzinfo=timezone.utc)
            return True
        value.clear()
        return True

    cleared = 0
    modules = []
    for entry in CARD_REGISTRY.values():
        mod = entry.get("module")
        if mod and mod not in modules:
            modules.append(mod)
    for mod in modules:
        for name, value in list(vars(mod).items()):
            if "CACHE" in name and isinstance(value, dict):
                if reset_cache_dict(value):
                    cleared += 1
    try:
        import card_utils
        for name, value in list(vars(card_utils).items()):
            if "CACHE" in name and isinstance(value, dict):
                if reset_cache_dict(value):
                    cleared += 1
    except Exception:
        pass
    return cleared


def _valid_time_text(value, fallback):
    text = str(value or "").strip()
    return text if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", text) else fallback


def _card_schedule_active(card):
    if not isinstance(card, dict):
        return True
    schedule = card.get("schedule") or {}
    days = schedule.get("days")
    if not isinstance(days, list) or not days:
        days = list(range(7))
    try:
        days = {int(day) for day in days}
    except Exception:
        days = set(range(7))
    now_local = datetime.now().astimezone()
    today = (now_local.weekday() + 1) % 7
    if today not in days:
        return False
    start = _valid_time_text(schedule.get("start"), "00:00")
    end = _valid_time_text(schedule.get("end"), "23:59")
    current = now_local.strftime("%H:%M")
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def handle_device_startup_poll(device_id, now_utc):
    last_poll = DEVICE_LAST_POLL.get(device_id)
    state = NEXT_STATE.get(device_id, {})
    expected_dwell = int(state.get("custom_dwell") or state.get("dwell") or 30)
    wake_gap = max(300, expected_dwell * 3)
    DEVICE_LAST_POLL[device_id] = now_utc
    if not last_poll:
        return False
    gap = (now_utc - last_poll).total_seconds()
    if gap < wake_gap:
        return False
    NEXT_STATE.pop(device_id, None)
    MESSAGE_STATE.pop(device_id, None)
    cleared = clear_card_runtime_caches()
    log(f"[startup] {device_id} returned after {int(gap)}s; reset rotation and cleared {cleared} card caches")
    return True


def _configured_card_id(card):
    return card if isinstance(card, str) else card.get("id", "clock")


def _is_live_espn_scoreboard_card(card_id):
    detail = str((CARD_REGISTRY.get(card_id) or {}).get("detail") or "").lower()
    return "live espn" in detail and "scoreboard" in detail


def _find_card_slot(cards, card_id, fallback=0):
    for idx, card in enumerate(cards):
        if _configured_card_id(card) == card_id:
            return idx
    return fallback


def render_next_card(device_id):
    device = device_for_id(device_id)
    if not device:
        return render_text_webp("SETUP", (20, 184, 166))

    if is_quiet_hours(device):
        clock_opts = {}
        for c in device.get("cards", []):
            if isinstance(c, dict) and c.get("id") == "clock":
                clock_opts = c.get("options", {})
                break
        clock_render = CARD_REGISTRY.get("clock", {}).get("render")
        return clock_render(clock_opts) if clock_render else render_text_webp("ZZZ", (100, 100, 180))

    interrupt = pop_interrupt(device_id)
    if interrupt:
        now = datetime.now(timezone.utc)
        dwell_secs = max(1, int(interrupt.get("dwell_secs") or 6))
        NEXT_STATE[device_id] = {
            "index": NEXT_STATE.get(device_id, {}).get("index", 0),
            "until": now + timedelta(seconds=dwell_secs),
            "body": interrupt["body"],
            "card": interrupt.get("label") or "interrupt",
            "dwell": dwell_secs,
            "custom_dwell": dwell_secs,
            "no_replay": True,
            "replay_body": render_text_webp("ALERT", (255, 210, 80)),
        }
        log(f"[interrupt] delivered {interrupt.get('label', 'interrupt')} to {device_id} via /next fallback")
        return interrupt["body"]

    cards = device.get("cards") or ["clock"]
    now = datetime.now(timezone.utc)
    state = NEXT_STATE.get(
        device_id,
        {"index": 0, "until": datetime.min.replace(tzinfo=timezone.utc), "body": None},
    )
    if state.get("body") is not None and state.get("until", now) > now:
        cached_card_id = state.get("card")
        rendered_at = state.get("rendered_at")
        live_scoreboard_stale = (
            _is_live_espn_scoreboard_card(cached_card_id)
            and (
                not isinstance(rendered_at, datetime)
                or (now - rendered_at).total_seconds() >= 15
            )
        )
        if live_scoreboard_stale:
            state = {
                **state,
                "index": _find_card_slot(cards, cached_card_id, state.get("index", 0)),
                "until": datetime.min.replace(tzinfo=timezone.utc),
                "body": None,
                "frames": [],
            }
            NEXT_STATE[device_id] = state
            log(f"[sports] expired stale live scoreboard frame for {device_id} -> {cached_card_id}")
        elif state.get("no_replay"):
            replay_body = state.get("replay_body")
            if replay_body is not None:
                return replay_body
        else:
            return state["body"]

    queued_frames = state.get("frames") or []
    if queued_frames:
        frame = queued_frames[0]
        remaining_frames = queued_frames[1:]
        body = frame.get("body")
        if body is not None:
            frame_dwell = max(1, int(frame.get("dwell_secs") or state.get("custom_dwell") or state.get("dwell") or 30))
            NEXT_STATE[device_id] = {
                "index":        state.get("index", 0),
                "until":        now + timedelta(seconds=max(1, frame_dwell - 1)),
                "body":         body,
                "card":         frame.get("card") or state.get("card") or "frame",
                "dwell":        state.get("dwell", frame_dwell),
                "custom_dwell": frame_dwell,
                "no_replay":    bool(frame.get("no_replay")),
                "replay_body":   frame.get("replay_body"),
                "frames":       remaining_frames,
                "rendered_at":   now,
            }
            log(f"[frame] {device_id} dwell={frame_dwell}s queued={len(remaining_frames)} no_replay={bool(frame.get('no_replay'))}")
            return body

    index = state.get("index", 0) % len(cards)

    for attempt in range(len(cards)):
        slot = (index + attempt) % len(cards)
        card = cards[slot]
        card_id = _configured_card_id(card)
        if isinstance(card, dict) and card.get("disabled"):
            CARD_ERRORS.setdefault(device_id, {})[card_id] = "Card disabled for this device."
            continue
        if not _card_schedule_active(card):
            CARD_ERRORS.setdefault(device_id, {}).pop(card_id, None)
            log(f"[schedule] {device_id} skipped {card_id}")
            continue
        options = {} if isinstance(card, str) else card.get("options", {})
        dwell_seconds = 10 if isinstance(card, str) else int(card.get("dwellSeconds", 10) or 10)
        try:
            card_entry = CARD_REGISTRY.get(card_id) or CARD_REGISTRY.get("clock")
            opts_with_meta = {
                **options,
                "_dwell": dwell_seconds,
                "_device_id": device_id,
                "_firmware_version": device.get("firmwareVersion", ""),
                "_target": device.get("target", ""),
                "_refresh_policy": read_settings().get("refreshPolicy", "balanced"),
                "_log": log,
            }
            log(f"[render] {device_id} -> {card_id} start")
            if card_entry:
                future = CARD_RENDER_POOL.submit(card_entry["render"], opts_with_meta)
                try:
                    result = future.result(timeout=CARD_RENDER_TIMEOUT_SECS)
                except TimeoutError:
                    future.cancel()
                    raise TimeoutError(f"{card_id} render timed out after {CARD_RENDER_TIMEOUT_SECS}s")
            else:
                result = render_text_webp("ERR", (238, 111, 111))
            if card_id == "airport_board" and isinstance(card, dict):
                opts = card.get("options") or {}
                if opts.pop("_forceRefresh", None) is not None:
                    card["options"] = opts
                    if clear_card_option(device_id, slot, "_forceRefresh"):
                        log(f"[airport_board] {device_id} cleared one-shot refresh flag")
            log(f"[render] {device_id} -> {card_id} done")
            CARD_ERRORS.get(device_id, {}).pop(card_id, None)
        except Exception as e:
            CARD_ERRORS.setdefault(device_id, {})[card_id] = str(e)
            log(f"[render] {device_id} -> {card_id} skipped: {e}")
            result = None
        wall_queued = False
        wall_body_is_special = False
        if isinstance(result, dict):
            body         = result.get("body")
            custom_dwell = result.get("dwell_secs", dwell_seconds)
            stay         = result.get("_stay", False)
            no_replay    = result.get("_no_replay", False)
            replay_body  = result.get("_replay_body")
            frames       = result.get("_frames") or []
            group_wall   = result.get("_group_wall")
            wall_body_is_special = bool(no_replay or result.get("_priority") or result.get("_priority_graphic") or replay_body is not None)
            if group_wall:
                group = group_for_device_id(device_id)
                module_for_wall = (CARD_REGISTRY.get(card_id) or {}).get("module")
                if group:
                    renderer_name = group_wall.get("renderer") or "_render_run_animation_frames"
                    queued_wall = queue_sports_moment_wall(
                        group,
                        module_for_wall,
                        renderer_name,
                        group_wall.get("team") or {},
                        kind=group_wall.get("kind"),
                        dwell_secs=group_wall.get("dwell_secs") or 6,
                        source=f"{card_id}:{device_id}",
                        label=group_wall.get("type") or "moment",
                    )
                    if queued_wall:
                        wall_queued = True
                        log(f"[sports] routed {card_id} animation from {device_id} to group wall {group.get('id')}")
                else:
                    log(f"[sports] no group contains {device_id}; {card_id} animation stayed on device")
        else:
            body, custom_dwell, stay, no_replay, replay_body, frames = result, None, False, False, None, []
        if body is not None:
            effective_dwell = custom_dwell if custom_dwell is not None else dwell_seconds
            card_detail = str((CARD_REGISTRY.get(card_id) or {}).get("detail") or "").lower()
            if "live espn" in card_detail and "scoreboard" in card_detail:
                effective_dwell = min(max(1, int(effective_dwell or dwell_seconds or 10)), 15)
            next_index = slot % len(cards) if stay else (slot + 1) % len(cards)
            NEXT_STATE[device_id] = {
                "index":        next_index,
                "until":        now + timedelta(seconds=max(1, effective_dwell - 1)),
                "body":         body,
                "card":         card_id,
                "dwell":        dwell_seconds,
                "custom_dwell": custom_dwell,
                "no_replay":    no_replay,
                "replay_body":   replay_body,
                "frames":       frames,
                "wall_queued":   wall_queued,
                "wall_body_is_special": wall_body_is_special,
                "rendered_at":   now,
            }
            log(f"[card] {device_id} -> {card_id} dwell={effective_dwell}s stay={stay} no_replay={no_replay}")
            return body

    clock_render = CARD_REGISTRY.get("clock", {}).get("render")
    body = clock_render({}) if clock_render else render_text_webp("WAIT", (100, 100, 180))
    NEXT_STATE[device_id] = {
        "index": index,
        "until": now + timedelta(seconds=60),
        "body": body,
        "card": "clock",
        "rendered_at": now,
    }
    return body


def render_message_frame(device_id, msg):
    text = msg.get("text", "")
    color = msg.get("color_rgb", (255, 255, 255))
    mode = msg.get("mode", "wrap")
    if not msg.get("body"):
        if mode == "scroll":
            msg["body"] = render_message_scroll(text, color)
        elif mode == "flash":
            msg["body"] = render_message_flash(text, color)
        else:
            msg["body"] = render_message_wrap(text, color)
    remaining = (msg["expires"] - datetime.now(timezone.utc)).total_seconds()
    dwell = max(1, remaining) if mode in ("scroll", "flash") else max(1, min(30, remaining))
    return msg["body"], dwell


def clamp_int(value, default, low, high):
    try:
        number = int(value)
    except Exception:
        number = default
    return max(low, min(high, number))


def message_body_for_mode(text, color_rgb, mode):
    if mode == "scroll":
        return render_message_scroll(text, color_rgb)
    if mode == "flash":
        return render_message_flash(text, color_rgb)
    return render_message_wrap(text, color_rgb)


def home_assistant_message_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    def pick(*keys, default=""):
        for source in (payload, data):
            for key in keys:
                value = source.get(key)
                if value not in (None, ""):
                    return value
        return default

    message = str(pick("message", "text", "body", default="")).strip()
    title = str(pick("title", default="")).strip()
    if title and message:
        text = f"{title}: {message}"
    else:
        text = message or title

    mode = str(pick("mode", default="")).strip().lower()
    group_id = pick("group", "groupId", "group_id", default="")
    target = pick("target", "targets", "device", "deviceId", "device_id", default="")
    group = group_for_id(group_id) if group_id else None
    if not group and target:
        values = target if isinstance(target, list) else [target]
        for value in values:
            group = group_for_id(value)
            if group:
                break
    if not mode:
        mode = "wall" if group else "wrap"
    if mode not in ("wrap", "scroll", "flash", "wall", "group"):
        mode = "wrap"

    return {
        "source": str(payload.get("_source") or "home-assistant").strip() or "home-assistant",
        "text": text,
        "title": title,
        "message": message,
        "target": target,
        "group": group,
        "mode": mode,
        "color": pick("color", default="white"),
        "duration": clamp_int(pick("duration", "dwell", "dwell_secs", default=10), 10, 1, 300),
        "priority": clamp_int(pick("priority", default=180), 180, 1, 999),
        "speed": str(pick("speed", default="normal")).strip().lower(),
        "graphic": str(pick("graphic", "icon", default="none")).strip().lower(),
        "waiting_message": pick("waitingMessage", "waiting_message", default=""),
    }


def queue_home_assistant_message(payload):
    msg = home_assistant_message_payload(payload)
    source = msg["source"]
    text = msg["text"]
    if not text:
        return 400, {"ok": False, "error": "message or title is required"}

    color_rgb = parse_color(msg["color"])
    group = msg["group"]
    mode = msg["mode"]
    duration = msg["duration"]
    priority = msg["priority"]
    queued = []

    if group and mode in ("wall", "group"):
        waiting_message = group_wait_message_text(msg["waiting_message"])
        wall_plan = render_group_scroll_plan(
            group,
            text,
            color_rgb=color_rgb,
            dwell_secs=duration,
            speed=msg["speed"],
            graphic=msg["graphic"],
            waiting_message=waiting_message,
        )
        slices = wall_plan.get("slices", {})
        if not slices:
            return 404, {"ok": False, "error": "group has no available devices"}
        lead_seconds = group_start_delay_seconds(plan=wall_plan)
        start_at = datetime.now(timezone.utc) + timedelta(seconds=lead_seconds)
        wall_dwell = wall_dwell_seconds(duration, wall_plan)
        run_id = uuid.uuid4().hex[:12]
        slice_meta = wall_plan.get("slice_meta", {})
        for device_id, body in slices.items():
            meta = slice_meta.get(device_id, {})
            queued_id = queue_wall_frame(
                device_id,
                body,
                dwell_secs=wall_dwell,
                priority=priority,
                label=f"{source}:wall",
                start_at=start_at,
                run_id=run_id,
                group_id=group.get("id"),
                group_members=list(slices.keys()),
                total_width=wall_plan.get("total_width"),
                slice_x=meta.get("x"),
                slice_width=meta.get("width"),
                frame_count=wall_plan.get("frame_count"),
                animation_ms=wall_plan.get("animation_ms"),
                arm_seconds=lead_seconds,
            )
            MESSAGE_STATE.pop(device_id, None)
            queued.append({"device": device_id, "id": queued_id})
        log(f"[{source}] scheduled wall run {run_id} {wall_plan.get('total_width')}x32 for group '{group.get('id')}' lead={lead_seconds:.2f}s dwell={wall_dwell}s frames={wall_plan.get('frame_count')}: \"{text}\"")
        return 200, {"ok": True, "source": source, "mode": "wall", "group": group.get("id"), "runId": run_id, "queued": queued, "wall": {"width": wall_plan.get("total_width"), "height": 32, "frames": wall_plan.get("frame_count"), "leadSeconds": lead_seconds, "dwellSeconds": wall_dwell}}

    if group:
        devices = devices_for_home_assistant_target(group.get("deviceIds") or [])
    else:
        devices = devices_for_home_assistant_target(msg["target"])
    if not devices:
        return 404, {"ok": False, "error": "no matching Pixora devices"}

    device_mode = mode if mode in ("wrap", "scroll", "flash") else "wrap"
    body = message_body_for_mode(text, color_rgb, device_mode)
    for device in devices:
        device_id = device.get("id")
        interrupt_id = queue_interrupt(
            device_id,
            body,
            dwell_secs=duration,
            priority=priority,
            label=f"{source}:{device_mode}",
        )
        MESSAGE_STATE.pop(device_id, None)
        queued.append({"device": device_id, "id": interrupt_id})
    log(f"[{source}] queued {device_mode} message for {len(queued)} device(s): \"{text}\"")
    return 200, {"ok": True, "source": source, "mode": device_mode, "queued": queued}


def mqtt_base_topic(settings=None):
    settings = settings or read_settings()
    base = str(settings.get("mqttBaseTopic") or "pixora").strip().strip("/")
    return base or "pixora"


def mqtt_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def mqtt_topic_matches(topic, pattern):
    topic_parts = str(topic or "").strip("/").split("/")
    pattern_parts = str(pattern or "").strip("/").split("/")
    if len(topic_parts) != len(pattern_parts):
        return False
    for actual, expected in zip(topic_parts, pattern_parts):
        if expected == "+":
            continue
        if actual != expected:
            return False
    return True


def mqtt_payload_to_message(topic, payload, settings=None):
    base = mqtt_base_topic(settings)
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            data = {"message": str(data)}
    except Exception:
        data = {"message": text}
    data["_source"] = "mqtt"

    topic = str(topic or "").strip("/")
    parts = topic.split("/")
    base_parts = base.split("/")
    rest = parts[len(base_parts):] if parts[:len(base_parts)] == base_parts else []
    if len(rest) == 2 and rest[1] == "message" and "target" not in data:
        data["target"] = urllib.parse.unquote(rest[0])
    elif len(rest) == 3 and rest[0] == "device" and rest[2] == "message":
        data["target"] = urllib.parse.unquote(rest[1])
    elif len(rest) == 3 and rest[0] == "group" and rest[2] == "message":
        data["target"] = urllib.parse.unquote(rest[1])
        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        if "mode" not in data and "mode" not in nested:
            data["mode"] = "wall"
    return data


def mqtt_subscription_topics(settings=None):
    base = mqtt_base_topic(settings)
    return [
        f"{base}/message",
        f"{base}/+/message",
        f"{base}/device/+/message",
        f"{base}/group/+/message",
    ]


def stop_mqtt_client():
    global MQTT_CLIENT
    with MQTT_LOCK:
        client = MQTT_CLIENT
        MQTT_CLIENT = None
    if client:
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass
    MQTT_STATUS.update({"connected": False, "subscriptions": []})


def start_mqtt_client(settings=None):
    global MQTT_CLIENT
    settings = settings or read_settings()
    enabled = mqtt_bool(settings.get("mqttEnabled"))
    host = str(settings.get("mqttHost") or "").strip()
    if not enabled:
        stop_mqtt_client()
        MQTT_STATUS.update({"enabled": False, "error": ""})
        return False
    MQTT_STATUS.update({"enabled": True, "connected": False, "error": "", "subscriptions": []})
    if not host:
        stop_mqtt_client()
        MQTT_STATUS["error"] = "MQTT host is required."
        return False

    stop_mqtt_client()
    try:
        import paho.mqtt.client as mqtt
    except Exception as error:
        MQTT_STATUS["error"] = f"paho-mqtt is not installed: {error}"
        log(f"[mqtt] unavailable: {MQTT_STATUS['error']}")
        return False

    port = clamp_int(settings.get("mqttPort", 1883), 1883, 1, 65535)
    client_id = str(settings.get("mqttClientId") or "pixora-server").strip() or "pixora-server"
    username = str(settings.get("mqttUsername") or "").strip()
    password = str(settings.get("mqttPassword") or "")
    use_tls = mqtt_bool(settings.get("mqttTls"))
    base = mqtt_base_topic(settings)

    try:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        except Exception:
            client = mqtt.Client(client_id=client_id)
        if username:
            client.username_pw_set(username, password)
        if use_tls:
            client.tls_set()

        def on_connect(client, userdata, flags, reason_code, *extra):
            reason_text = str(reason_code)
            try:
                reason_int = int(reason_code)
            except Exception:
                reason_int = None
            if reason_int == 0 or reason_text in ("0", "Success"):
                topics = mqtt_subscription_topics(settings)
                for topic in topics:
                    client.subscribe(topic, qos=0)
                client.publish(f"{base}/status", "online", qos=0, retain=True)
                MQTT_STATUS.update({"connected": True, "error": "", "subscriptions": topics})
                log(f"[mqtt] connected to {host}:{port}; subscribed to {', '.join(topics)}")
            else:
                MQTT_STATUS.update({"connected": False, "error": f"connect failed: {reason_code}"})
                log(f"[mqtt] connect failed: {reason_code}")

        def on_disconnect(client, userdata, *args):
            MQTT_STATUS["connected"] = False
            log("[mqtt] disconnected")

        def on_message(client, userdata, message):
            try:
                payload = mqtt_payload_to_message(message.topic, message.payload, settings)
                if not payload:
                    return
                status, result = queue_home_assistant_message(payload)
                if status >= 400:
                    log(f"[mqtt] message rejected on {message.topic}: {result.get('error', 'unknown error')}")
                else:
                    client.publish(f"{base}/last", json.dumps(result), qos=0, retain=False)
            except Exception as error:
                log(f"[mqtt] message error on {getattr(message, 'topic', '?')}: {error}")

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.will_set(f"{base}/status", "offline", qos=0, retain=True)
        client.connect_async(host, port, keepalive=60)
        client.loop_start()
        with MQTT_LOCK:
            MQTT_CLIENT = client
        log(f"[mqtt] connecting to {host}:{port}")
        return True
    except Exception as error:
        MQTT_STATUS.update({"connected": False, "error": str(error), "subscriptions": []})
        log(f"[mqtt] ERROR: {error}")
        return False


def device_update_url(device_ip):
    normalized = device_ip.strip().rstrip("/")
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized + "/update"
    return "http://" + normalized + "/update"


def check_device_reachable(device_ip):
    update_url = device_update_url(device_ip)
    request = urllib.request.Request(update_url, method="HEAD")
    try:
        urllib.request.urlopen(request, timeout=2).close()
        return True, update_url, ""
    except urllib.error.HTTPError:
        return True, update_url, ""
    except Exception as error:
        return False, update_url, str(error)


def firmware_source_available():
    return False


def queue_startup_device_syncs():
    queued = 0
    for device in read_devices():
        if isinstance(device, dict) and device.get("id"):
            queue_device_quiet_hours_sync(device)
            queued += 1
    if queued:
        log(f"[startup] queued quiet-hours sync for {queued} device(s)")


def _run_flash_job(payload):
    global FLASH_JOB
    FLASH_JOB["ok"] = False
    FLASH_JOB["lines"].append("Firmware flashing is available only through official release binaries.")
    FLASH_JOB["running"] = False
    FLASH_JOB["done"] = True


def _run_wifi_ota_job(payload):
    global FLASH_JOB
    device_id = str(payload.get("deviceId") or payload.get("id") or "").strip()
    target = canonical_device_target(payload.get("target")) or ""
    firmware_name = Path(str(payload.get("firmwareName") or "")).name
    firmware_b64 = str(payload.get("firmwareData") or "")

    try:
        if not device_id:
            raise ValueError("Choose a display to update.")
        device = device_for_id(device_id)
        if not device:
            raise ValueError("Device not found.")
        if target not in ("tidbyt-gen1", "matrixportal-s3-64x32", "matrixportal-s3-128x32"):
            raise ValueError("Choose a firmware target.")
        if not firmware_file_matches_target_name(firmware_name, target):
            raise ValueError(f"The selected firmware file does not match {target}.")
        if not firmware_file_is_ota(firmware_name):
            raise ValueError("For OTA updates, choose the target's ota-firmware.bin file.")
        try:
            firmware = base64.b64decode(firmware_b64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The selected firmware file could not be read.")
        if len(firmware) < 500_000 or len(firmware) > 8_000_000:
            raise ValueError("The selected firmware file size does not look valid.")

        safe_id = safe_ota_device_id(device_id)
        ota_dir = OTA_DIR / safe_id
        ota_dir.mkdir(parents=True, exist_ok=True)
        firmware_path = ota_dir / "firmware.bin"
        firmware_path.write_bytes(firmware)
        version = firmware_image_version(firmware_path)
        ota_url = ota_url_for_device(device)
        OTA_PENDING[device_id] = {
            "url": ota_url,
            "version": version,
            "queuedAt": datetime.now(timezone.utc).isoformat(),
        }
        save_pending_ota_jobs()
        FLASH_JOB["lines"].append(f"Queued OTA for {device_id}: {firmware_name} ({version})")
        FLASH_JOB["lines"].append("The display will update on its next poll, then reboot.")
        log(f"[ota] queued {device_id} target={target} version={version} url={ota_url}")
        FLASH_JOB["ok"] = True
    except Exception as error:
        FLASH_JOB["ok"] = False
        FLASH_JOB["lines"].append(str(error))
    finally:
        FLASH_JOB["running"] = False
        FLASH_JOB["done"] = True


def _run_official_firmware_file_flash(payload):
    global FLASH_JOB
    port = str(payload.get("port") or "").strip()
    target = canonical_device_target(payload.get("target")) or ""
    firmware_name = Path(str(payload.get("firmwareName") or "")).name
    firmware_b64 = str(payload.get("firmwareData") or "")
    chip = "esp32s3" if target.startswith("matrixportal-s3") else "esp32"
    baud = "921600" if chip == "esp32s3" else "460800"

    try:
        if not port:
            raise ValueError("USB port is required.")
        if target not in ("tidbyt-gen1", "matrixportal-s3-64x32", "matrixportal-s3-128x32"):
            raise ValueError("Choose a firmware target.")
        if not firmware_file_matches_target_name(firmware_name, target):
            raise ValueError(f"The selected firmware file does not match {target}.")
        if not firmware_file_is_usb_full_flash(firmware_name):
            raise ValueError("For USB flashing, choose the target's usb-full-flash.bin file.")
        try:
            firmware = base64.b64decode(firmware_b64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The selected firmware file could not be read.")
        if len(firmware) < 500_000 or len(firmware) > 8_000_000:
            raise ValueError("The selected firmware file size does not look valid.")

        FLASH_JOB["lines"].append(f"Flashing {target} {firmware_name} to {port}...")
        with tempfile.TemporaryDirectory(prefix="pixora-firmware-") as tmp:
            firmware_path = Path(tmp) / firmware_name
            firmware_path.write_bytes(firmware)
            command = [
                sys.executable,
                "--pixora-esptool",
                "--chip",
                chip,
                "--port",
                port,
                "--baud",
                baud,
                "write_flash",
                "0x0",
                str(firmware_path),
            ]
            proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=clean_env(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    FLASH_JOB["lines"].append(line)
            code = proc.wait()
            if code != 0:
                raise RuntimeError(f"Firmware flash failed with exit code {code}.")
        FLASH_JOB["lines"].append("Firmware flash complete. The display should reboot.")
        FLASH_JOB["ok"] = True
    except Exception as error:
        FLASH_JOB["ok"] = False
        FLASH_JOB["lines"].append(str(error))
    finally:
        FLASH_JOB["running"] = False
        FLASH_JOB["done"] = True


class PixoraHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_firmware_file(self, path):
        try:
            if path.startswith("/data/ota/"):
                relative = path.removeprefix("/data/")
                base_dir = DATA_DIR
                file_path = (base_dir / relative).resolve()
            else:
                base_dir = ROOT
                file_path = (base_dir / path.lstrip("/")).resolve()
            if not str(file_path).startswith(str(base_dir.resolve())):
                self.send_error(403)
                return
            if not file_path.is_file():
                self.send_error(404)
                return

            size = file_path.stat().st_size
            start = 0
            end = size - 1
            status = 200
            range_header = self.headers.get("Range", "").strip()
            if range_header:
                m = re.match(r"bytes=(\d*)-(\d*)$", range_header)
                if not m:
                    self.send_error(416)
                    return
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                if not m.group(1) and m.group(2):
                    suffix_len = int(m.group(2))
                    start = max(0, size - suffix_len)
                    end = size - 1
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = 206

            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(file_path, "rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except BrokenPipeError:
            pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        url_path = urllib.parse.urlparse(self.path).path
        if re.match(r"^/dist/firmware/[^/]+/firmware\.bin$", url_path):
            self._send_firmware_file(url_path)
            return
        if re.match(r"^/data/ota/[^/]+/firmware\.bin$", url_path):
            self._send_firmware_file(url_path)
            return
        super().do_HEAD()

    def do_GET(self):
        url_path = urllib.parse.urlparse(self.path).path
        if re.match(r"^/dist/firmware/[^/]+/firmware\.bin$", url_path):
            self._send_firmware_file(url_path)
            return
        if re.match(r"^/data/ota/[^/]+/firmware\.bin$", url_path):
            self._send_firmware_file(url_path)
            return

        if self.path == "/api/devices":
            self._send_json(200, {"devices": read_devices()})
            return

        if self.path == "/api/groups":
            self._send_json(200, {"groups": read_groups()})
            return

        if self.path.startswith("/api/home-assistant"):
            host = self.headers.get("Host") or "pixora.local:8088"
            base_url = f"http://{host}"
            devices = [
                {"id": item.get("id"), "name": item.get("name") or item.get("id")}
                for item in read_devices()
            ]
            groups = [
                {"id": item.get("id"), "name": item.get("name") or item.get("id"), "deviceIds": item.get("deviceIds") or []}
                for item in read_groups()
            ]
            self._send_json(200, {
                "ok": True,
                "endpoint": f"{base_url}/api/home-assistant/message",
                "devices": devices,
                "groups": groups,
                "rest_command": {
                    "pixora_message": {
                        "url": f"{base_url}/api/home-assistant/message",
                        "method": "post",
                        "content_type": "application/json",
                        "payload": "{\"message\":\"{{ message }}\",\"target\":\"{{ target }}\",\"data\":{\"mode\":\"{{ mode | default('wrap') }}\",\"color\":\"{{ color | default('white') }}\",\"duration\":{{ duration | default(10) }}}}",
                    }
                },
            })
            return

        if self.path.startswith("/api/smartthings"):
            host = self.headers.get("Host") or "pixora.local:8088"
            base_url = f"http://{host}"
            self._send_json(200, {
                "ok": True,
                "messageEndpoint": f"{base_url}/api/smartthings/message",
                "devicesEndpoint": f"{base_url}/api/smartthings/devices",
                "pixoraDevices": [
                    {"id": item.get("id"), "name": item.get("name") or item.get("id")}
                    for item in read_devices()
                ],
                "pixoraGroups": [
                    {"id": item.get("id"), "name": item.get("name") or item.get("id"), "deviceIds": item.get("deviceIds") or []}
                    for item in read_groups()
                ],
            })
            return

        if self.path == "/api/cards":
            def card_preview_url(card_id):
                preview_path = ROOT / "assets" / "previews" / f"{card_id}.webp"
                if not preview_path.exists():
                    return ""
                return f"/assets/previews/{card_id}.webp?v={int(preview_path.stat().st_mtime)}"

            cards = [
                {
                    "id": v["id"],
                    "name": v["name"],
                    "category": v.get("category", ""),
                    "detail": v["detail"],
                    "options": v["options"],
                    "previewUrl": card_preview_url(v["id"]),
                }
                for v in CARD_REGISTRY.values()
            ]
            self._send_json(200, {"cards": cards})
            return

        if self.path == "/api/graphics":
            graphics = []
            for item in read_graphics():
                graphic_id = str(item.get("id") or "")
                if graphic_file_path(graphic_id) and graphic_file_path(graphic_id).exists():
                    graphics.append({**item, "url": f"/api/graphics/{graphic_id}.png"})
            self._send_json(200, {"ok": True, "graphics": graphics})
            return

        if self.path.startswith("/api/graphics/") and self.path.endswith(".png"):
            graphic_id = self.path.rsplit("/", 1)[-1][:-4]
            path = graphic_file_path(graphic_id)
            if not path or not path.exists():
                self.send_error(404)
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/addons/registry":
            try:
                import time
                bust = f"{'?' if '?' not in get_registry_url() else '&'}_={int(time.time())}"
                req = urllib.request.Request(
                    get_registry_url() + bust,
                    headers={"User-Agent": "Pixora/0.1", "Cache-Control": "no-cache", "Pragma": "no-cache"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                body = data
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._send_json(502, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/build-status":
            self._send_json(200, {
                "running": FLASH_JOB["running"],
                "done":    FLASH_JOB["done"],
                "ok":      FLASH_JOB["ok"],
                "lines":   FLASH_JOB["lines"],
                "device":  FLASH_JOB["device"],
            })
            return

        if self.path == "/api/settings":
            settings = read_settings()
            settings["registryUrl"] = get_registry_url(settings)
            status = dict(MQTT_STATUS)
            status["baseTopic"] = mqtt_base_topic(settings)
            startup_status = get_windows_startup_status()
            self._send_json(200, {
                **settings,
                "mqttStatus": status,
                "windowsStartupSupported": startup_status.get("supported", False),
                "windowsStartupEnabled": startup_status.get("enabled", False),
                "windowsStartupCommand": startup_status.get("command", ""),
                "windowsStartupError": startup_status.get("error", ""),
            })
            return

        if self.path == "/api/update-status":
            self._send_json(200, check_for_pixora_update(force=False))
            return

        if self.path == "/api/version":
            self._send_json(200, {
                "version": firmware_build_stamp(),
                "source": str(app_version_file()),
            })
            return

        if url_path == "/api/etsy/oauth/callback":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            state = (query.get("state") or [""])[0]
            code = (query.get("code") or [""])[0]
            error = (query.get("error") or [""])[0]
            error_description = (query.get("error_description") or [""])[0]
            prune_etsy_oauth_state()
            oauth_state = ETSY_OAUTH_STATE.pop(state, None)
            if error:
                message = error_description or error
                script = f'if (window.opener) window.opener.postMessage({{type:"pixora-etsy-oauth", ok:false, error:{json.dumps(message)}}}, window.location.origin);'
                title, body_text = "Etsy connection cancelled", message
            elif not oauth_state or not code:
                message = "The Etsy OAuth session expired or did not match. Try Connect Etsy again."
                script = f'if (window.opener) window.opener.postMessage({{type:"pixora-etsy-oauth", ok:false, error:{json.dumps(message)}}}, window.location.origin);'
                title, body_text = "Etsy connection failed", message
            else:
                try:
                    token = exchange_etsy_oauth_code(oauth_state, code)
                    access_token = token.get("access_token") or ""
                    refresh_token = token.get("refresh_token") or ""
                    expires_in = token.get("expires_in") or 3600
                    script = (
                        "if (window.opener) window.opener.postMessage("
                        f'{{type:"pixora-etsy-oauth", ok:true, accessToken:{json.dumps(access_token)}, refreshToken:{json.dumps(refresh_token)}, expiresIn:{json.dumps(expires_in)}}}, '
                        "window.location.origin); setTimeout(function(){ window.close(); }, 700);"
                    )
                    title, body_text = "Etsy connected", "You can close this window."
                except Exception as error:
                    message = str(error)
                    script = f'if (window.opener) window.opener.postMessage({{type:"pixora-etsy-oauth", ok:false, error:{json.dumps(message)}}}, window.location.origin);'
                    title, body_text = "Etsy connection failed", message
            html = f'<!doctype html><html><head><title>Pixora Etsy</title></head><body style="font-family:Arial;background:#0b1117;color:#f4f7f8;padding:24px;"><h1>{title}</h1><p>{body_text}</p><script>{script}</script></body></html>'
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/mqtt":
            settings = read_settings()
            self._send_json(200, {
                "ok": True,
                "enabled": mqtt_bool(settings.get("mqttEnabled")),
                "host": settings.get("mqttHost", ""),
                "port": settings.get("mqttPort", 1883),
                "baseTopic": mqtt_base_topic(settings),
                "status": MQTT_STATUS,
                "topics": mqtt_subscription_topics(settings),
            })
            return

        if self.path == "/api/logs":
            self._send_json(200, {"lines": list(LOG_BUFFER)})
            return

        if self.path.startswith("/api/device-status"):
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                device_id = (query.get("id") or [""])[0].strip()
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                last_ip = device.get("lastIp", "")
                if not last_ip:
                    self._send_json(200, {"ok": False, "error": "IP not recorded yet - waiting for next poll"})
                    return
                req = urllib.request.Request(f"http://{last_ip}/status",
                    headers={"User-Agent": "Pixora/0.1"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read())
                self._send_json(200, {"ok": True, "status": data})
            except Exception as e:
                self._send_json(200, {"ok": False, "error": str(e)})
            return

        if self.path.startswith("/api/card-errors"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            device_id = (query.get("device") or [""])[0].strip()
            self._send_json(200, {"errors": CARD_ERRORS.get(device_id, {})})
            return

        if self.path.startswith("/api/device-ping"):
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                ip = (query.get("ip") or [""])[0].strip()
                if not ip:
                    self._send_json(400, {"ok": False, "error": "ip required"})
                    return
                reachable, _, _ = check_device_reachable(ip)
                self._send_json(200, {"reachable": reachable})
            except Exception as e:
                self._send_json(200, {"reachable": False})
            return

        if self.path.startswith("/api/weather"):
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                zip_code = (query.get("zip") or [""])[0]
                self._send_json(200, {"ok": True, "weather": weather_for_zip(zip_code)})
            except Exception as error:
                self._send_json(400, {"ok": False, "output": str(error)})
            return

        if re.match(r"^/[^/?#]+/interrupt/?(?:\?.*)?$", self.path):
            path_segment = self.path.strip("/").split("/")[0]
            device = device_for_path(path_segment)
            device_id = device.get("id") if device else path_segment
            if device and is_quiet_hours(device):
                self.send_response(404)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                log(f"[interrupt] suppressed priority poll for {device_id} during quiet hours")
                return
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            requested_id = (query.get("id") or [""])[0].strip() or None
            with rotation_lock_for(device_id):
                wall_frame = None if requested_id else pop_wall_frame(device_id)
                interrupt = None if wall_frame else pop_interrupt(device_id, requested_id)
            if not wall_frame and not interrupt:
                self.send_response(404)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            item = wall_frame or interrupt
            body = item["body"]
            dwell_secs = max(1, int(item.get("dwell_secs") or (8 if wall_frame else 6)))
            start_at = item.get("start_at")
            start_delay_ms = 0
            if isinstance(start_at, datetime):
                start_delay_ms = max(0, int((start_at - datetime.now(timezone.utc)).total_seconds() * 1000))
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Pixora-Dwell-Secs", str(dwell_secs))
            if start_delay_ms > 0:
                self.send_header("Pixora-Start-Delay-Ms", str(start_delay_ms))
            if device and device.get("brightness") is not None:
                self.send_header("Pixora-Brightness", str(int(device["brightness"])))
            if wall_frame:
                self.send_header("Pixora-Wall-Run-Id", str(wall_frame.get("id") or ""))
                if wall_frame.get("group_id"):
                    self.send_header("Pixora-Wall-Group", str(wall_frame.get("group_id")))
                if wall_frame.get("total_width") is not None:
                    self.send_header("Pixora-Wall-Width", str(int(wall_frame.get("total_width"))))
                if wall_frame.get("slice_x") is not None:
                    self.send_header("Pixora-Slice-X", str(int(wall_frame.get("slice_x"))))
                if wall_frame.get("slice_width") is not None:
                    self.send_header("Pixora-Slice-W", str(int(wall_frame.get("slice_width"))))
                if wall_frame.get("frame_count") is not None:
                    self.send_header("Pixora-Frame-Count", str(int(wall_frame.get("frame_count"))))
                if wall_frame.get("animation_ms") is not None:
                    self.send_header("Pixora-Animation-Ms", str(int(wall_frame.get("animation_ms"))))
            self.end_headers()
            self.wfile.write(body)
            if wall_frame:
                log(f"[interrupt] delivered wall run {wall_frame.get('id')} to {device_id} start_delay={start_delay_ms}ms slice={wall_frame.get('slice_x')}+{wall_frame.get('slice_width')}/{wall_frame.get('total_width')}")
            else:
                log(f"[interrupt] delivered {interrupt.get('label', 'interrupt')} to {device_id}")
            return

        if re.match(r"^/[^/?#]+/next/?(?:\?.*)?$", self.path):
            path_segment = self.path.strip("/").split("/")[0]
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            virtual_client = (query.get("virtual") or [""])[0].strip().lower() in ("1", "true", "yes")
            device = device_for_path(path_segment)
            now_utc = datetime.now(timezone.utc)
            # Capture firmware version and client IP on every poll
            fw_ver = self.headers.get("X-Firmware-Version", "").strip()
            uptime_text = (self.headers.get("X-Pixora-Uptime") or "").strip()
            reset_reason = (self.headers.get("X-Pixora-Reset-Reason") or "").strip()
            client_ip = (self.headers.get("X-Forwarded-For") or self.client_address[0] or "").split(",")[0].strip()
            if not device:
                device = adopt_polling_device(path_segment, client_ip, fw_ver, reset_reason, uptime_text)
            device_id = device.get("id") if device else path_segment
            start_delay_ms = 0
            if device and (fw_ver or client_ip or uptime_text or reset_reason):
                changed = False
                if fw_ver and device.get("firmwareVersion") != fw_ver:
                    device["firmwareVersion"] = fw_ver
                    changed = True
                if client_ip and not is_loopback_ip(client_ip) and device.get("lastIp") != client_ip:
                    device["lastIp"] = client_ip
                    changed = True
                if reset_reason and device.get("lastResetReason") != reset_reason:
                    device["lastResetReason"] = reset_reason
                    changed = True
                try:
                    uptime_s = int(uptime_text)
                except Exception:
                    uptime_s = None
                if uptime_s is not None:
                    previous = DEVICE_RUNTIME.get(device_id, {})
                    previous_uptime = previous.get("uptime")
                    previous_reason = previous.get("reset_reason")
                    if previous_uptime is not None and uptime_s + 10 < previous_uptime:
                        log(f"[reset] {device_id} uptime dropped {previous_uptime}s -> {uptime_s}s reason={reset_reason or 'unknown'} ip={client_ip}")
                    elif previous_reason and reset_reason and reset_reason != previous_reason:
                        log(f"[reset] {device_id} reset reason changed {previous_reason} -> {reset_reason} uptime={uptime_s}s ip={client_ip}")
                    DEVICE_RUNTIME[device_id] = {
                        "uptime": uptime_s,
                        "reset_reason": reset_reason,
                        "seen": now_utc.isoformat(),
                    }
                    device["lastUptime"] = uptime_s
                    changed = True
                if changed:
                    update_device({
                        "id": device_id,
                        "lastIp": device.get("lastIp", ""),
                        "firmwareVersion": device.get("firmwareVersion", ""),
                        "lastResetReason": device.get("lastResetReason", ""),
                        "lastUptime": device.get("lastUptime"),
                    })
                    device = device_for_id(device_id) or device
            with rotation_lock_for(device_id):
                handle_device_startup_poll(device_id, now_utc)
                state = NEXT_STATE.get(device_id, {})
                msg = MESSAGE_STATE.get(device_id)
                quiet = bool(device and is_quiet_hours(device))
                wall_frame = None
                interrupt = None
                if quiet:
                    MESSAGE_STATE.pop(device_id, None)
                    INTERRUPT_STATE.pop(device_id, None)
                    WALL_RUN_STATE.pop(device_id, None)
                    if state.get("body") or state.get("frames"):
                        log(f"[quiet] cleared cached rotation for {device_id}")
                    NEXT_STATE[device_id] = {
                        "index": state.get("index", 0),
                        "until": now_utc + timedelta(seconds=30),
                        "body": None,
                        "card": "clock",
                        "dwell": 30,
                        "custom_dwell": None,
                        "no_replay": False,
                        "replay_body": None,
                        "frames": [],
                    }
                    body = render_next_card(device_id)
                    state = NEXT_STATE.get(device_id, {})
                    dwell_secs = 30
                else:
                    wall_frame = pop_wall_frame(device_id)
                if wall_frame:
                    body = wall_frame["body"]
                    dwell_secs = max(1, int(wall_frame.get("dwell_secs") or 8))
                    start_at = wall_frame.get("start_at")
                    if isinstance(start_at, datetime):
                        start_delay_ms = max(0, int((start_at - now_utc).total_seconds() * 1000))
                    log(f"[wall] delivered run {wall_frame.get('id')} to {device_id} via /next start_delay={start_delay_ms}ms slice={wall_frame.get('slice_x')}+{wall_frame.get('slice_width')}/{wall_frame.get('total_width')}")
                elif not quiet and msg and msg.get("expires", now_utc) > now_utc:
                    body, dwell_secs = render_message_frame(device_id, msg)
                elif not quiet:
                    MESSAGE_STATE.pop(device_id, None)
                    body = render_next_card(device_id)
                    wall_frame = pop_wall_frame(device_id)
                    if wall_frame:
                        normal_body = body
                        body = wall_frame["body"]
                        dwell_secs = max(1, int(wall_frame.get("dwell_secs") or 8))
                        start_at = wall_frame.get("start_at")
                        if isinstance(start_at, datetime):
                            start_delay_ms = max(0, int((start_at - now_utc).total_seconds() * 1000))
                        state = NEXT_STATE.get(device_id, {})
                        followup_frames = []
                        if normal_body is not None and not state.get("wall_body_is_special"):
                            followup_frames.append({
                                "body": normal_body,
                                "card": state.get("card"),
                                "dwell_secs": state.get("custom_dwell") or state.get("dwell") or 10,
                            })
                        NEXT_STATE[device_id] = {
                            "index":        state.get("index", 0),
                            "until":        datetime.min.replace(tzinfo=timezone.utc),
                            "body":         None,
                            "card":         wall_frame.get("label") or "wall",
                            "dwell":        state.get("dwell", dwell_secs),
                            "custom_dwell": state.get("custom_dwell"),
                            "no_replay":    False,
                            "replay_body":   None,
                            "frames":       followup_frames,
                        }
                        log(f"[wall] promoted run {wall_frame.get('id')} ahead of normal {device_id} card start_delay={start_delay_ms}ms")
                    else:
                        state = NEXT_STATE.get(device_id, {})
                        until = state.get("until", now_utc)
                        remaining = max(1, int((until - now_utc).total_seconds()) + 1)
                        configured_dwell = state.get("custom_dwell") or state.get("dwell", 30)
                        dwell_secs = min(remaining, configured_dwell)
            if virtual_client:
                virtual_sprite = virtual_webp_sprite(body)
                if virtual_sprite:
                    body = virtual_sprite["body"]
                    dwell_secs = max(1, int(dwell_secs or 1), virtual_sprite["duration_secs"])
                else:
                    animated_dwell = virtual_webp_dwell_floor(body)
                    if animated_dwell:
                        dwell_secs = max(1, int(dwell_secs or 1), animated_dwell)
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            if virtual_client and virtual_sprite:
                self.send_header("Pixora-Virtual-Frame-Count", str(virtual_sprite["frame_count"]))
                self.send_header("Pixora-Virtual-Frame-Width", str(virtual_sprite["frame_width"]))
                self.send_header("Pixora-Virtual-Frame-Height", str(virtual_sprite["frame_height"]))
                self.send_header("Pixora-Virtual-Frame-Durations", ",".join(str(duration) for duration in virtual_sprite["durations"]))
            if device:
                if is_quiet_hours(device):
                    self.send_header("Pixora-Brightness", str(quiet_brightness()))
                elif device.get("brightness") is not None:
                    self.send_header("Pixora-Brightness", str(int(device["brightness"])))
            if dwell_secs is not None:
                self.send_header("Pixora-Dwell-Secs", str(dwell_secs))
                log(f"[dwell] {device_id} -> {dwell_secs}s  (card dwell={state.get('dwell')} custom={state.get('custom_dwell')})")
            current_card = state.get("card")
            if current_card:
                self.send_header("Pixora-Card", str(current_card))
            if start_delay_ms > 0:
                self.send_header("Pixora-Start-Delay-Ms", str(start_delay_ms))
            if wall_frame:
                self.send_header("Pixora-Wall-Run-Id", str(wall_frame.get("id") or ""))
                if wall_frame.get("group_id"):
                    self.send_header("Pixora-Wall-Group", str(wall_frame.get("group_id")))
                if wall_frame.get("total_width") is not None:
                    self.send_header("Pixora-Wall-Width", str(int(wall_frame.get("total_width"))))
                if wall_frame.get("slice_x") is not None:
                    self.send_header("Pixora-Slice-X", str(int(wall_frame.get("slice_x"))))
                if wall_frame.get("slice_width") is not None:
                    self.send_header("Pixora-Slice-W", str(int(wall_frame.get("slice_width"))))
                if wall_frame.get("frame_count") is not None:
                    self.send_header("Pixora-Frame-Count", str(int(wall_frame.get("frame_count"))))
                if wall_frame.get("animation_ms") is not None:
                    self.send_header("Pixora-Animation-Ms", str(int(wall_frame.get("animation_ms"))))
            if device_id in OTA_PENDING:
                ota_info = OTA_PENDING.get(device_id)
                if isinstance(ota_info, str):
                    ota_url = ota_info
                    ota_version = ""
                else:
                    ota_url = ota_info.get("url", "")
                    ota_version = ota_info.get("version", "")
                sent_at = "" if isinstance(ota_info, str) else str(ota_info.get("sentAt") or "")
                sent_fw = "" if isinstance(ota_info, str) else str(ota_info.get("sentFirmware") or "")
                try:
                    sent_uptime = None if isinstance(ota_info, str) else int(ota_info.get("sentUptime"))
                except Exception:
                    sent_uptime = None
                rebooted_after_send = (
                    sent_uptime is not None
                    and uptime_s is not None
                    and uptime_s + 10 < sent_uptime
                )
                version_changed_after_send = bool(sent_fw and fw_ver and sent_fw != fw_ver)
                if ota_version and fw_ver == ota_version and sent_at and (version_changed_after_send or rebooted_after_send):
                    OTA_PENDING.pop(device_id, None)
                    save_pending_ota_jobs()
                    log(f"[ota] Cleared OTA for {device_id}; device reports {fw_ver}")
                elif ota_url:
                    if not isinstance(ota_info, str):
                        ota_info["sentAt"] = datetime.now(timezone.utc).isoformat()
                        ota_info["sentFirmware"] = fw_ver
                        ota_info["sentUptime"] = uptime_s
                        ota_info["sentCount"] = int(ota_info.get("sentCount") or 0) + 1
                        save_pending_ota_jobs()
                    self.send_header("Pixora-OTA-URL", ota_url)
                    log(f"[ota] Sent OTA URL to {device_id}: {ota_url} (waiting for {ota_version or 'new firmware'})")
            if device_id in QH_PENDING:
                qh_val = QH_PENDING.pop(device_id)
                self.send_header("Pixora-Quiet-Hours", qh_val)
                log(f"[qh] Sent quiet hours to {device_id}: {qh_val}")
            if device_id in SWAP_PENDING:
                swap_val = SWAP_PENDING.pop(device_id)
                self.send_header("Pixora-Swap-Colors", swap_val)
                log(f"[display] Sent color-order swap to {device_id}: {swap_val}")
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def do_POST(self):
        if self.path == "/api/restart":
            self._send_json(200, {"ok": True})
            script = str(ROOT / "Start-Pixora.ps1")
            try:
                subprocess.Popen(
                    [POWERSHELL or "powershell", "-File", script],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            except Exception:
                pass
            exit_process_later()
            return

        if self.path == "/api/stop":
            log("[server] Stop requested from UI")
            self._send_json(200, {"ok": True})
            exit_process_later()
            return

        if self.path == "/api/update-check":
            self._send_json(200, check_for_pixora_update(force=True))
            return

        if self.path == "/api/devices/save":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                device = json.loads(self.rfile.read(content_length).decode("utf-8"))
                saved = update_device(device)
                self._send_json(200, {"ok": True, "device": saved})
            except Exception as error:
                self._send_json(500, {"ok": False, "output": str(error)})
            return

        if self.path == "/api/devices/delete":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                device_id = str(payload.get("id", "")).strip()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                deleted = delete_device(device_id)
                self._send_json(200, {"ok": True, "deleted": deleted})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/groups/save":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                group_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(payload.get("id") or "wall").strip()).strip("-") or "wall"
                name = str(payload.get("name") or group_id).strip()
                device_ids = [str(item).strip() for item in (payload.get("deviceIds") or []) if str(item).strip()]
                if not device_ids:
                    self._send_json(400, {"ok": False, "error": "Pick at least one device"})
                    return
                if len(device_ids) > 3:
                    self._send_json(400, {"ok": False, "error": "Pick up to 3 devices"})
                    return
                groups = [g for g in read_groups() if g.get("id") != group_id]
                groups.append({"id": group_id, "name": name, "deviceIds": device_ids})
                saved = write_groups(groups)
                self._send_json(200, {"ok": True, "groups": saved})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/groups/delete":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                group_id = str(payload.get("id") or "").strip()
                groups = [g for g in read_groups() if g.get("id") != group_id]
                write_groups(groups)
                self._send_json(200, {"ok": True})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/groups/test-scroll":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                group_id = str(payload.get("id") or "").strip()
                group = next((g for g in read_groups() if g.get("id") == group_id), None)
                if not group:
                    self._send_json(404, {"ok": False, "error": "Group not found"})
                    return
                text = str(payload.get("text") or "Pixora wall test").strip()
                dwell_secs = max(3, min(60, int(payload.get("dwellSeconds") or 8)))
                color = parse_color(payload.get("color", "white"))
                speed = str(payload.get("speed") or "normal").strip().lower()
                if speed not in ("slow", "normal", "fast", "turbo"):
                    speed = "normal"
                graphic = str(payload.get("graphic") or "none").strip().lower()
                if graphic.startswith("custom:"):
                    if not custom_graphic_image(graphic):
                        graphic = "none"
                elif graphic not in ("none", "baseball", "arrow", "bullet", "delorean"):
                    graphic = "none"
                waiting_message = group_wait_message_text(payload.get("waitingMessage"))
                wall_plan = render_group_scroll_plan(group, text, color, dwell_secs, speed=speed, graphic=graphic, waiting_message=waiting_message)
                slices = wall_plan.get("slices", {})
                if not slices:
                    self._send_json(400, {"ok": False, "error": "No devices in this group"})
                    return
                lead_seconds = group_start_delay_seconds(plan=wall_plan)
                start_at = datetime.now(timezone.utc) + timedelta(seconds=lead_seconds)
                wall_dwell = wall_dwell_seconds(dwell_secs, wall_plan)
                run_id = uuid.uuid4().hex[:12]
                slice_meta = wall_plan.get("slice_meta", {})
                for device_id, body in slices.items():
                    meta = slice_meta.get(device_id, {})
                    queue_wall_frame(
                        device_id,
                        body,
                        dwell_secs=wall_dwell,
                        priority=200,
                        label=f"group:{group_id}",
                        start_at=start_at,
                        run_id=run_id,
                        group_id=group_id,
                        group_members=list(slices.keys()),
                        total_width=wall_plan.get("total_width"),
                        slice_x=meta.get("x"),
                        slice_width=meta.get("width"),
                        frame_count=wall_plan.get("frame_count"),
                        animation_ms=wall_plan.get("animation_ms"),
                        arm_seconds=lead_seconds,
                    )
                wait_note = f" wait='{waiting_message}'" if waiting_message else ""
                log(f"[group] scheduled wall run {run_id} {wall_plan.get('total_width')}x32 scroll '{text}' speed={speed} graphic={graphic}{wait_note} lead={lead_seconds:.2f}s dwell={wall_dwell}s frames={wall_plan.get('frame_count')} for {group_id}: {', '.join(slices.keys())}; starts {start_at.isoformat()}")
                self._send_json(200, {"ok": True, "runId": run_id, "queued": list(slices.keys()), "startsAt": start_at.isoformat(), "leadSeconds": lead_seconds, "wall": {"width": wall_plan.get("total_width"), "height": 32, "frames": wall_plan.get("frame_count"), "animationMs": wall_plan.get("animation_ms"), "dwellSeconds": wall_dwell}})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path in ("/api/home-assistant/message", "/api/ha/message", "/api/smartthings/message", "/api/st/message"):
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                payload["_source"] = "smartthings" if "smartthings" in self.path or self.path.startswith("/api/st/") else "home-assistant"
                status, result = queue_home_assistant_message(payload)
                self._send_json(status, result)
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "error": "invalid JSON"})
            except Exception as error:
                log(f"[home-assistant] ERROR: {error}")
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/devices/reboot":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                device_id = str(payload.get("id", "")).strip()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                last_ip = str(device.get("lastIp", "")).strip()
                if not last_ip:
                    self._send_json(400, {"ok": False, "error": "No IP recorded for this device yet"})
                    return

                req = urllib.request.Request(
                    f"http://{last_ip}/reboot",
                    data=b"",
                    method="POST",
                    headers={"User-Agent": "Pixora/0.1"},
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                log(f"Reboot sent to {device_id} at {last_ip}")
                self._send_json(200, {"ok": True, "output": "Reboot command sent.", "response": body})
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    self._send_json(502, {"ok": False, "error": "Device firmware does not support reboot yet. Update firmware first."})
                else:
                    self._send_json(502, {"ok": False, "error": f"Device returned HTTP {error.code}"})
            except Exception as error:
                self._send_json(502, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/test-card-animation":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                device_id = str(payload.get("id", "")).strip()
                card_id = str(payload.get("cardId", "")).strip()
                kind = str(payload.get("kind", "")).strip().lower()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                if card_id not in ("college_baseball", "college_softball", "mens_college_hockey"):
                    self._send_json(400, {"ok": False, "error": "Unsupported card animation"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                favorite = str(payload.get("team", "")).strip().upper()
                if not favorite:
                    for card in device.get("cards", []):
                        if isinstance(card, dict) and card.get("id") == card_id:
                            favorite = str((card.get("options") or {}).get("favoriteTeam", "")).strip().upper()
                            break
                defaults = {
                    "college_baseball": "BC",
                    "college_softball": "OU",
                    "mens_college_hockey": "BC",
                }
                favorite = favorite or defaults.get(card_id, "BC")
                module = (CARD_REGISTRY.get(card_id) or {}).get("module")
                if not module:
                    self._send_json(500, {"ok": False, "error": f"{card_id} is not loaded"})
                    return
                is_baseball_card = card_id in ("college_baseball", "college_softball")
                kind = kind or ("run" if is_baseball_card else "goal")
                if kind == "run" and is_baseball_card:
                    renderer_name = "_render_run_animation"
                    color, alt = ("75E7D6", "FFFFFF")
                elif kind == "goal" and not is_baseball_card:
                    renderer_name = "_render_goal_animation"
                    color, alt = ("50DCFF", "FFFFFF")
                elif kind == "win":
                    renderer_name = "_render_run_animation" if is_baseball_card else "_render_goal_animation"
                    color, alt = (("75E7D6", "FFFFFF") if is_baseball_card else ("50DCFF", "FFFFFF"))
                else:
                    self._send_json(400, {"ok": False, "error": "Unsupported animation kind"})
                    return
                renderer = getattr(module, renderer_name, None)
                if not renderer:
                    self._send_json(500, {"ok": False, "error": f"{card_id} animation renderer is not loaded"})
                    return
                team = {
                    "abbreviation": favorite,
                    "color": color,
                    "alternateColor": alt,
                    "logo": f"https://a.espncdn.com/i/teamlogos/ncaa/500/{favorite.lower()}.png",
                }
                mode = str(payload.get("mode") or payload.get("target") or "device").strip().lower()
                group_id = str(payload.get("groupId") or payload.get("group") or "").strip()
                if mode in ("group", "group_wall", "wall") or group_id:
                    group = group_for_id(group_id) if group_id else group_for_device_id(device_id)
                    frame_renderer = "_render_run_animation_frames" if is_baseball_card else "_render_goal_animation_frames"
                    queued_wall = queue_sports_moment_wall(group, module, frame_renderer, team, kind=kind, dwell_secs=7 if kind == "win" else 6, source="test", label=f"{card_id}-{kind}") if group else None
                    if not queued_wall:
                        self._send_json(404, {"ok": False, "error": "Group not found or has no devices"})
                        return
                    log(f"[test] queued {card_id} {kind} wall animation for {group.get('id')} ({favorite})")
                    self._send_json(200, {"ok": True, "queued": True, "mode": "wall", "device": device_id, "group": group.get("id"), "cardId": card_id, "team": favorite, "kind": kind, **queued_wall})
                    return

                team["_width"] = device_width(device)
                body = renderer(team, kind)
                current = NEXT_STATE.get(device_id, {})
                NEXT_STATE[device_id] = {
                    "index": current.get("index", 0),
                    "until": datetime.min.replace(tzinfo=timezone.utc),
                    "body": None,
                    "dwell": current.get("dwell", 10),
                    "custom_dwell": 7 if kind == "win" else 6,
                    "frames": [{"body": body, "dwell_secs": 7 if kind == "win" else 6, "no_replay": True}],
                }
                log(f"[test] queued {card_id} {kind} animation for {device_id} ({favorite})")
                self._send_json(200, {"ok": True, "queued": True, "device": device_id, "cardId": card_id, "team": favorite, "kind": kind})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/test-launch-animation":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                device_id = str(payload.get("id", "")).strip()
                phase = str(payload.get("phase") or "liftoff").strip().lower()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                module = (CARD_REGISTRY.get("launch_countdown") or {}).get("module")
                if not module:
                    self._send_json(500, {"ok": False, "error": "Launch card is not loaded"})
                    return
                mode = str(payload.get("mode") or payload.get("target") or "device").strip().lower()
                group_id = str(payload.get("groupId") or payload.get("group") or "").strip()
                if mode in ("group", "group_wall", "wall") or group_id:
                    group = group_for_id(group_id) if group_id else group_for_device_id(device_id)
                    queued_wall = queue_sports_moment_wall(
                        group,
                        module,
                        "_render_launch_animation_frames",
                        {"phase": phase},
                        kind=phase,
                        dwell_secs=4,
                        source="test",
                        label="launch",
                    ) if group else None
                    if not queued_wall:
                        self._send_json(404, {"ok": False, "error": "Group not found or has no devices"})
                        return
                    log(f"[test] queued launch wall animation for {group.get('id')}")
                    self._send_json(200, {"ok": True, "queued": True, "mode": "wall", "device": device_id, "group": group.get("id"), "cardId": "launch_countdown", **queued_wall})
                    return

                renderer = getattr(module, "render_launch_test", None)
                if not renderer:
                    self._send_json(500, {"ok": False, "error": "Launch test renderer is not loaded"})
                    return
                body = renderer(device_width(device), phase)
                current = NEXT_STATE.get(device_id, {})
                NEXT_STATE[device_id] = {
                    "index": current.get("index", 0),
                    "until": datetime.min.replace(tzinfo=timezone.utc),
                    "body": None,
                    "dwell": current.get("dwell", 10),
                    "custom_dwell": 4,
                    "frames": [{"body": body, "dwell_secs": 4, "no_replay": True}],
                }
                log(f"[test] queued launch animation for {device_id}")
                self._send_json(200, {"ok": True, "queued": True, "device": device_id, "cardId": "launch_countdown"})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/test-mlb-run":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                device_id = str(payload.get("id", "")).strip()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                kind = str(payload.get("kind", "run")).strip().lower()
                if kind not in ("run", "home_run", "grand_slam", "win"):
                    kind = "run"
                favorite = str(payload.get("team", "")).strip().upper()
                if not favorite:
                    for card in device.get("cards", []):
                        if isinstance(card, dict) and card.get("id") == "mlb":
                            favorite = str((card.get("options") or {}).get("favoriteTeam", "")).strip().upper()
                            break
                favorite = (favorite or "BOS")[:3]
                mlb = (CARD_REGISTRY.get("mlb") or {}).get("module")
                if not mlb or not hasattr(mlb, "_render_run_animation"):
                    self._send_json(500, {"ok": False, "error": "MLB animation renderer is not loaded"})
                    return
                team_colors = {
                    "BOS": ("BD3039", "0C2340"),
                    "NYY": ("0C2340", "C4CED4"),
                    "BAL": ("DF4601", "000000"),
                    "TB": ("092C5C", "8FBCE6"),
                    "TOR": ("134A8E", "E8291C"),
                }
                color, alt = team_colors.get(favorite, ("75E7D6", "FFFFFF"))
                team = {
                    "abbreviation": favorite,
                    "color": color,
                    "alternateColor": alt,
                    "logo": f"https://a.espncdn.com/i/teamlogos/mlb/500/{favorite.lower()}.png",
                }
                mode = str(payload.get("mode") or payload.get("target") or "device").strip().lower()
                group_id = str(payload.get("groupId") or payload.get("group") or "").strip()
                if mode in ("group", "group_wall", "wall") or group_id:
                    group = group_for_id(group_id) if group_id else group_for_device_id(device_id)
                    if not group:
                        self._send_json(404, {"ok": False, "error": "Group not found for this device"})
                        return
                    queued_wall = queue_sports_moment_wall(group, mlb, "_render_run_animation_frames", team, kind=kind, dwell_secs=7 if kind == "win" else 6, source="test", label=f"mlb-{kind}")
                    if not queued_wall:
                        self._send_json(400, {"ok": False, "error": "No devices in this group"})
                        return
                    log(f"[test] queued MLB {kind} wall animation for {group.get('id')} ({favorite})")
                    self._send_json(200, {"ok": True, "queued": True, "mode": "wall", "device": device_id, "group": group.get("id"), "team": favorite, "kind": kind, **queued_wall})
                    return

                team["_width"] = device_width(device)
                body = mlb._render_run_animation(team, kind)
                current = NEXT_STATE.get(device_id, {})
                NEXT_STATE[device_id] = {
                    "index": current.get("index", 0),
                    "until": datetime.min.replace(tzinfo=timezone.utc),
                    "body": None,
                    "dwell": current.get("dwell", 10),
                    "custom_dwell": 7 if kind == "win" else 6,
                    "frames": [{"body": body, "dwell_secs": 7 if kind == "win" else 6, "no_replay": True}],
                }
                log(f"[test] queued MLB {kind} animation for {device_id} ({favorite})")
                self._send_json(200, {"ok": True, "queued": True, "device": device_id, "team": favorite, "kind": kind})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/test-nhl-goal":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                device_id = str(payload.get("id", "")).strip()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                kind = str(payload.get("kind", "goal")).strip().lower()
                if kind not in ("goal", "win"):
                    kind = "goal"
                favorite = str(payload.get("team", "")).strip().upper()
                if not favorite:
                    for card in device.get("cards", []):
                        if isinstance(card, dict) and card.get("id") == "nhl":
                            favorite = str((card.get("options") or {}).get("favoriteTeam", "")).strip().upper()
                            break
                favorite = (favorite or "BOS")[:3]
                nhl = (CARD_REGISTRY.get("nhl") or {}).get("module")
                if not nhl or not hasattr(nhl, "_render_goal_animation"):
                    self._send_json(500, {"ok": False, "error": "NHL animation renderer is not loaded"})
                    return
                team_colors = {
                    "BOS": ("FFB81C", "000000"),
                    "MTL": ("AF1E2D", "192168"),
                    "TOR": ("00205B", "FFFFFF"),
                    "NYR": ("0038A8", "CE1126"),
                    "TBL": ("002868", "FFFFFF"),
                }
                color, alt = team_colors.get(favorite, ("64B4FF", "FFFFFF"))
                team = {
                    "abbreviation": favorite,
                    "color": color,
                    "alternateColor": alt,
                    "logo": f"https://a.espncdn.com/i/teamlogos/nhl/500/{favorite.lower()}.png",
                }
                mode = str(payload.get("mode") or payload.get("target") or "device").strip().lower()
                group_id = str(payload.get("groupId") or payload.get("group") or "").strip()
                if mode in ("group", "group_wall", "wall") or group_id:
                    group = group_for_id(group_id) if group_id else group_for_device_id(device_id)
                    queued_wall = queue_sports_moment_wall(group, nhl, "_render_goal_animation_frames", team, kind=kind, dwell_secs=7 if kind == "win" else 6, source="test", label=f"nhl-{kind}") if group else None
                    if not queued_wall:
                        self._send_json(404, {"ok": False, "error": "Group not found or has no devices"})
                        return
                    log(f"[test] queued NHL {kind} wall animation for {group.get('id')} ({favorite})")
                    self._send_json(200, {"ok": True, "queued": True, "mode": "wall", "device": device_id, "group": group.get("id"), "team": favorite, "kind": kind, **queued_wall})
                    return

                team["_width"] = device_width(device)
                body = nhl._render_goal_animation(team, kind)
                current = NEXT_STATE.get(device_id, {})
                NEXT_STATE[device_id] = {
                    "index": current.get("index", 0),
                    "until": datetime.min.replace(tzinfo=timezone.utc),
                    "body": None,
                    "dwell": current.get("dwell", 10),
                    "custom_dwell": 7 if kind == "win" else 6,
                    "frames": [{"body": body, "dwell_secs": 7 if kind == "win" else 6, "no_replay": True}],
                }
                log(f"[test] queued NHL {kind} animation for {device_id} ({favorite})")
                self._send_json(200, {"ok": True, "queued": True, "device": device_id, "team": favorite, "kind": kind})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/test-soccer-goal":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                device_id = str(payload.get("id", "")).strip()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                kind = str(payload.get("kind", "goal")).strip().lower()
                if kind not in ("goal", "win"):
                    kind = "goal"
                favorite = str(payload.get("team", "")).strip().upper()
                league = str(payload.get("league", "")).strip()
                if not favorite:
                    for card in device.get("cards", []):
                        if isinstance(card, dict) and card.get("id") == "soccer":
                            card_options = card.get("options") or {}
                            favorite = str(card_options.get("favoriteTeam", "")).strip().upper()
                            league = league or str(card_options.get("league", "")).strip()
                            break
                if not league:
                    for card in device.get("cards", []):
                        if isinstance(card, dict) and card.get("id") == "soccer":
                            league = str((card.get("options") or {}).get("league", "")).strip()
                            break
                favorite = (favorite or "ARS")[:3]
                league = league or "eng.1"
                soccer = (CARD_REGISTRY.get("soccer") or {}).get("module")
                if not soccer or not hasattr(soccer, "_render_goal_animation"):
                    self._send_json(500, {"ok": False, "error": "Soccer animation renderer is not loaded"})
                    return
                if hasattr(soccer, "_resolve_team_for_test"):
                    team = soccer._resolve_team_for_test(favorite, league)
                else:
                    team = {"abbreviation": favorite, "color": "46DC7D", "alternateColor": "FFFFFF", "logo": ""}
                mode = str(payload.get("mode") or payload.get("target") or "device").strip().lower()
                group_id = str(payload.get("groupId") or payload.get("group") or "").strip()
                if mode in ("group", "group_wall", "wall") or group_id:
                    group = group_for_id(group_id) if group_id else group_for_device_id(device_id)
                    queued_wall = queue_sports_moment_wall(group, soccer, "_render_goal_animation_frames", team, kind=kind, dwell_secs=7 if kind == "win" else 6, source="test", label=f"soccer-{kind}") if group else None
                    if not queued_wall:
                        self._send_json(404, {"ok": False, "error": "Group not found or has no devices"})
                        return
                    log(f"[test] queued soccer {kind} wall animation for {group.get('id')} ({favorite}, {league})")
                    self._send_json(200, {"ok": True, "queued": True, "mode": "wall", "device": device_id, "group": group.get("id"), "team": favorite, "league": league, "kind": kind, **queued_wall})
                    return

                team["_width"] = device_width(device)
                body = soccer._render_goal_animation(team, kind)
                current = NEXT_STATE.get(device_id, {})
                NEXT_STATE[device_id] = {
                    "index": current.get("index", 0),
                    "until": datetime.min.replace(tzinfo=timezone.utc),
                    "body": None,
                    "dwell": current.get("dwell", 10),
                    "custom_dwell": 7 if kind == "win" else 6,
                    "frames": [{"body": body, "dwell_secs": 7 if kind == "win" else 6, "no_replay": True}],
                }
                log(f"[test] queued soccer {kind} animation for {device_id} ({favorite}, {league})")
                self._send_json(200, {"ok": True, "queued": True, "device": device_id, "team": favorite, "league": league, "kind": kind})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/test-nfl-score":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                device_id = str(payload.get("id", "")).strip()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                favorite = str(payload.get("team", "")).strip().upper()
                if not favorite:
                    for card in device.get("cards", []):
                        if isinstance(card, dict) and card.get("id") == "nfl":
                            favorite = str((card.get("options") or {}).get("favoriteTeam", "")).strip().upper()
                            break
                favorite = (favorite or "NE")[:3]
                kind = str(payload.get("kind", "touchdown")).strip().lower()
                if kind not in ("touchdown", "field_goal", "safety", "score", "win"):
                    kind = "touchdown"
                nfl = (CARD_REGISTRY.get("nfl") or {}).get("module")
                if not nfl or not hasattr(nfl, "_render_score_animation"):
                    self._send_json(500, {"ok": False, "error": "NFL animation renderer is not loaded"})
                    return
                team_colors = {
                    "NE": ("002244", "C60C30"),
                    "KC": ("E31837", "FFB81C"),
                    "PHI": ("004C54", "A5ACAF"),
                    "DAL": ("003594", "869397"),
                    "BUF": ("00338D", "C60C30"),
                    "GB": ("203731", "FFB612"),
                    "SF": ("AA0000", "B3995D"),
                }
                color, alt = team_colors.get(favorite, ("64DC50", "FFFFFF"))
                team = {
                    "abbreviation": favorite,
                    "color": color,
                    "alternateColor": alt,
                    "logo": f"https://a.espncdn.com/i/teamlogos/nfl/500/{favorite.lower()}.png",
                }
                mode = str(payload.get("mode") or payload.get("target") or "device").strip().lower()
                group_id = str(payload.get("groupId") or payload.get("group") or "").strip()
                if mode in ("group", "group_wall", "wall") or group_id:
                    group = group_for_id(group_id) if group_id else group_for_device_id(device_id)
                    queued_wall = queue_sports_moment_wall(group, nfl, "_render_score_animation_frames", team, kind=kind, dwell_secs=7 if kind == "win" else 6, source="test", label=f"nfl-{kind}") if group else None
                    if not queued_wall:
                        self._send_json(404, {"ok": False, "error": "Group not found or has no devices"})
                        return
                    log(f"[test] queued NFL {kind} wall animation for {group.get('id')} ({favorite})")
                    self._send_json(200, {"ok": True, "queued": True, "mode": "wall", "device": device_id, "group": group.get("id"), "team": favorite, "kind": kind, **queued_wall})
                    return

                team["_width"] = device_width(device)
                body = nfl._render_score_animation(team, kind)
                current = NEXT_STATE.get(device_id, {})
                NEXT_STATE[device_id] = {
                    "index": current.get("index", 0),
                    "until": datetime.min.replace(tzinfo=timezone.utc),
                    "body": None,
                    "dwell": current.get("dwell", 10),
                    "custom_dwell": 7 if kind == "win" else 6,
                    "frames": [{"body": body, "dwell_secs": 7 if kind == "win" else 6, "no_replay": True}],
                }
                log(f"[test] queued NFL {kind} animation for {device_id} ({favorite})")
                self._send_json(200, {"ok": True, "queued": True, "device": device_id, "team": favorite, "kind": kind})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/test-ufl-score":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                device_id = str(payload.get("id", "")).strip()
                if not device_id or not re.match(r"^[a-zA-Z0-9_-]+$", device_id):
                    self._send_json(400, {"ok": False, "error": "Invalid device ID"})
                    return
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                favorite = str(payload.get("team", "")).strip().upper()
                if not favorite:
                    for card in device.get("cards", []):
                        if isinstance(card, dict) and card.get("id") == "ufl":
                            favorite = str((card.get("options") or {}).get("favoriteTeam", "")).strip().upper()
                            break
                favorite = (favorite or "DC")[:5]
                kind = str(payload.get("kind", "touchdown")).strip().lower()
                if kind not in ("touchdown", "field_goal", "safety", "score", "win"):
                    kind = "touchdown"
                ufl = (CARD_REGISTRY.get("ufl") or {}).get("module")
                if not ufl or not hasattr(ufl, "_render_score_animation"):
                    self._send_json(500, {"ok": False, "error": "UFL animation renderer is not loaded"})
                    return
                team_colors = {
                    "BHAM": ("D1B06B", "111111"),
                    "CLB": ("5A8DEE", "FFFFFF"),
                    "DAL": ("C41230", "FFFFFF"),
                    "DC": ("D71920", "FFFFFF"),
                    "HOU": ("F58220", "FFFFFF"),
                    "LOU": ("592C82", "FFFFFF"),
                    "ORL": ("00A3E0", "FFFFFF"),
                    "STL": ("004B8D", "FFFFFF"),
                }
                color, alt = team_colors.get(favorite, ("50BEFF", "FFFFFF"))
                team = {
                    "abbreviation": favorite,
                    "color": color,
                    "alternateColor": alt,
                    "logo": f"https://a.espncdn.com/i/teamlogos/ufl/500/{favorite.lower()}.png",
                }
                mode = str(payload.get("mode") or payload.get("target") or "device").strip().lower()
                group_id = str(payload.get("groupId") or payload.get("group") or "").strip()
                if mode in ("group", "group_wall", "wall") or group_id:
                    group = group_for_id(group_id) if group_id else group_for_device_id(device_id)
                    queued_wall = queue_sports_moment_wall(group, ufl, "_render_score_animation_frames", team, kind=kind, dwell_secs=7 if kind == "win" else 6, source="test", label=f"ufl-{kind}") if group else None
                    if not queued_wall:
                        self._send_json(404, {"ok": False, "error": "Group not found or has no devices"})
                        return
                    log(f"[test] queued UFL {kind} wall animation for {group.get('id')} ({favorite})")
                    self._send_json(200, {"ok": True, "queued": True, "mode": "wall", "device": device_id, "group": group.get("id"), "team": favorite, "kind": kind, **queued_wall})
                    return

                team["_width"] = device_width(device)
                body = ufl._render_score_animation(team, kind)
                current = NEXT_STATE.get(device_id, {})
                NEXT_STATE[device_id] = {
                    "index": current.get("index", 0),
                    "until": datetime.min.replace(tzinfo=timezone.utc),
                    "body": None,
                    "dwell": current.get("dwell", 10),
                    "custom_dwell": 7 if kind == "win" else 6,
                    "frames": [{"body": body, "dwell_secs": 7 if kind == "win" else 6, "no_replay": True}],
                }
                log(f"[test] queued UFL {kind} animation for {device_id} ({favorite})")
                self._send_json(200, {"ok": True, "queued": True, "device": device_id, "team": favorite, "kind": kind})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if re.match(r"^/api/devices/[^/]+/quiet-hours$", self.path):
            try:
                device_id = self.path.split("/")[3]
                content_length = int(self.headers.get("Content-Length", "0"))
                qh = json.loads(self.rfile.read(content_length).decode("utf-8"))
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                qh = {
                    "enabled": bool(qh.get("enabled", False)) if isinstance(qh, dict) else False,
                    "start": _valid_time_text(qh.get("start") if isinstance(qh, dict) else None, "22:00"),
                    "end": _valid_time_text(qh.get("end") if isinstance(qh, dict) else None, "06:00"),
                }
                device["quietHours"] = qh
                save_device(device)
                queue_device_quiet_hours_sync(device, qh=qh, push=True)
                self._send_json(200, {"ok": True, "quietHours": qh})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if re.match(r"^/[^/?#]+/message$", self.path):
            try:
                path_segment = self.path.strip("/").split("/")[0]
                _dev = device_for_path(path_segment)
                device_id = _dev.get("id") if _dev else path_segment
                content_length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_length)
                log(f"[message] POST /{path_segment}/message  content_length={content_length}  raw={raw[:120]}")
                payload = json.loads(raw.decode("utf-8"))
                if "message" not in payload and "text" in payload:
                    payload["message"] = payload.get("text")
                payload["deviceId"] = device_id
                payload["_source"] = "message"
                status, result = queue_home_assistant_message(payload)
                if status >= 400:
                    log(f"[message] rejected: {result.get('error', 'message failed')}")
                    self._send_json(status, result)
                    return
                text = str(payload.get("message", "")).strip()
                duration = clamp_int(payload.get("duration", 10), 10, 1, 300)
                mode = str(payload.get("mode", "wrap") or "wrap").lower()
                log(f"[message] queued priority message for '{device_id}': \"{text}\" {duration}s {mode}")
                self._send_json(200, {"ok": True})
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "error": "invalid JSON"})
            except Exception as e:
                log(f"[message] ERROR: {e}")
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/device-sync-quiet-hours":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                device_id  = payload.get("id", "")
                utc_offset = int(payload.get("utc_offset", 0))
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                qh = payload.get("quietHours")
                if isinstance(qh, dict):
                    qh = {
                        "enabled": bool(qh.get("enabled", False)),
                        "start": _valid_time_text(qh.get("start"), "22:00"),
                        "end": _valid_time_text(qh.get("end"), "06:00"),
                    }
                    device["quietHours"] = qh
                    save_device(device)
                else:
                    qh = device.get("quietHours", {})
                result = queue_device_quiet_hours_sync(device, qh=qh, utc_offset=utc_offset, push=True)
                self._send_json(200, {
                    "ok": True,
                    "pushed": result.get("pushed", False),
                    "note": "Synced now" if result.get("pushed") else "Will be delivered on device's next poll",
                    "error": result.get("error", ""),
                })
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/device-sync-color-order":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                device_id = str(payload.get("id", "")).strip()
                device = device_for_id(device_id)
                if not device:
                    self._send_json(404, {"ok": False, "error": "Device not found"})
                    return
                swap_colors = bool(payload.get("swapColors", False))
                device["swapColors"] = swap_colors
                save_device(device)
                SWAP_PENDING[device_id] = "1" if swap_colors else "0"
                self._send_json(200, {"ok": True, "note": "Will be delivered on device's next poll. The display will reboot to apply it."})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/addons/install":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                url = payload.get("url", "")
                if not re.match(r"https://raw\.githubusercontent\.com/", url):
                    self._send_json(400, {"ok": False, "error": "Only raw.githubusercontent.com URLs are allowed."})
                    return
                if not url.endswith(".py"):
                    self._send_json(400, {"ok": False, "error": "Only .py addon files can be installed."})
                    return
                req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read()
                filename = url.split("/")[-1]
                ADDONS_DIR.mkdir(parents=True, exist_ok=True)
                dest = ADDONS_DIR / filename
                dest.write_bytes(content)
                card_id = load_card_file(dest)
                self._send_json(200, {"ok": True, "id": card_id})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/addons/remove":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                card_id = payload.get("id", "")
                if not card_id or not re.match(r"^[a-zA-Z0-9_-]+$", card_id):
                    self._send_json(400, {"ok": False, "error": "Invalid card ID"})
                    return
                path = ADDONS_DIR / f"{card_id}.py"
                if path.exists():
                    path.unlink()
                CARD_REGISTRY.pop(card_id, None)
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/graphics/upload":
            try:
                from PIL import Image
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length > 2_500_000:
                    self._send_json(413, {"ok": False, "error": "Image is too large."})
                    return
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                name = str(payload.get("name") or "Graphic").strip()[:48] or "Graphic"
                data_url = str(payload.get("dataUrl") or "")
                if "," in data_url:
                    data_url = data_url.split(",", 1)[1]
                try:
                    raw = base64.b64decode(data_url, validate=True)
                except (binascii.Error, ValueError):
                    self._send_json(400, {"ok": False, "error": "Invalid image data."})
                    return
                if len(raw) > 1_500_000:
                    self._send_json(413, {"ok": False, "error": "Image is too large."})
                    return
                img = Image.open(BytesIO(raw)).convert("RGBA")
                if img.width < 1 or img.height < 1:
                    self._send_json(400, {"ok": False, "error": "Invalid image."})
                    return
                graphic_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.lower()).strip("-")[:32] or "graphic"
                graphic_id = f"{graphic_id}-{uuid.uuid4().hex[:6]}"
                ensure_user_dirs()
                path = graphic_file_path(graphic_id)
                img.save(path, "PNG")
                custom_graphic_image_by_id.cache_clear()
                items = read_graphics()
                item = {"id": graphic_id, "name": name}
                items.append(item)
                write_graphics(items)
                self._send_json(200, {"ok": True, "graphic": {**item, "url": f"/api/graphics/{graphic_id}.png"}})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/graphics/delete":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                graphic_id = str(payload.get("id") or "").strip()
                path = graphic_file_path(graphic_id)
                if not graphic_id or not path:
                    self._send_json(400, {"ok": False, "error": "Invalid graphic ID."})
                    return
                items = read_graphics()
                kept = [item for item in items if str(item.get("id") or "") != graphic_id]
                if len(kept) == len(items) and not path.exists():
                    self._send_json(404, {"ok": False, "error": "Graphic not found."})
                    return
                if path.exists():
                    path.unlink()
                custom_graphic_image_by_id.cache_clear()
                write_graphics(kept)
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/settings/save":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                settings = read_settings()
                if "registryUrl" in payload:
                    settings["registryUrl"] = normalize_registry_url(payload.get("registryUrl"))
                if "openWeatherApiKey" in payload:
                    settings["openWeatherApiKey"] = str(payload.get("openWeatherApiKey") or "").strip()
                if "defaultZipCode" in payload:
                    settings["defaultZipCode"] = re.sub(r"\D", "", str(payload.get("defaultZipCode") or ""))[:5]
                if "defaultLatitude" in payload:
                    settings["defaultLatitude"] = str(payload.get("defaultLatitude") or "").strip()
                if "defaultLongitude" in payload:
                    settings["defaultLongitude"] = str(payload.get("defaultLongitude") or "").strip()
                if "timeFormat" in payload:
                    settings["timeFormat"] = "24" if str(payload.get("timeFormat") or "").strip() == "24" else "12"
                if "temperatureUnits" in payload:
                    settings["temperatureUnits"] = "C" if str(payload.get("temperatureUnits") or "").strip().upper() == "C" else "F"
                if "defaultLocationName" in payload:
                    settings["defaultLocationName"] = str(payload.get("defaultLocationName") or "").strip()
                if "dateFormat" in payload:
                    value = str(payload.get("dateFormat") or "md").strip()
                    settings["dateFormat"] = value if value in ("md", "dm", "mon_d") else "md"
                if "distanceUnits" in payload:
                    value = str(payload.get("distanceUnits") or "imperial").strip()
                    settings["distanceUnits"] = "metric" if value == "metric" else "imperial"
                if "defaultDwellSeconds" in payload:
                    try:
                        settings["defaultDwellSeconds"] = max(1, min(3600, int(payload.get("defaultDwellSeconds") or 10)))
                    except Exception:
                        settings["defaultDwellSeconds"] = 10
                if "defaultBrightness" in payload:
                    try:
                        settings["defaultBrightness"] = max(1, min(100, int(payload.get("defaultBrightness") or 50)))
                    except Exception:
                        settings["defaultBrightness"] = 50
                if "refreshPolicy" in payload:
                    value = str(payload.get("refreshPolicy") or "balanced").strip()
                    settings["refreshPolicy"] = value if value in ("conservative", "balanced", "frequent") else "balanced"
                if "defaultAnimationSpeed" in payload:
                    value = str(payload.get("defaultAnimationSpeed") or "normal").strip()
                    settings["defaultAnimationSpeed"] = value if value in ("slow", "normal", "fast", "turbo") else "normal"
                if "defaultQuietStart" in payload:
                    settings["defaultQuietStart"] = _valid_time_text(payload.get("defaultQuietStart"), "22:00")
                if "defaultQuietEnd" in payload:
                    settings["defaultQuietEnd"] = _valid_time_text(payload.get("defaultQuietEnd"), "06:00")
                for key in ("favoriteMlbTeam", "favoriteNbaTeam", "favoriteNhlTeam", "favoriteNflTeam"):
                    if key in payload:
                        settings[key] = str(payload.get(key) or "").strip().upper()
                if "quietBrightness" in payload:
                    try:
                        settings["quietBrightness"] = max(0, min(100, int(payload.get("quietBrightness") or 0)))
                    except Exception:
                        settings["quietBrightness"] = 5
                mqtt_changed = any(key in payload for key in (
                    "mqttEnabled", "mqttHost", "mqttPort", "mqttUsername", "mqttPassword",
                    "mqttBaseTopic", "mqttClientId", "mqttTls",
                ))
                if "mqttEnabled" in payload:
                    settings["mqttEnabled"] = mqtt_bool(payload.get("mqttEnabled"))
                if "mqttHost" in payload:
                    settings["mqttHost"] = str(payload.get("mqttHost") or "").strip()
                if "mqttPort" in payload:
                    try:
                        settings["mqttPort"] = max(1, min(65535, int(payload.get("mqttPort") or 1883)))
                    except Exception:
                        settings["mqttPort"] = 1883
                if "mqttUsername" in payload:
                    settings["mqttUsername"] = str(payload.get("mqttUsername") or "").strip()
                if "mqttPassword" in payload:
                    settings["mqttPassword"] = str(payload.get("mqttPassword") or "")
                if "mqttBaseTopic" in payload:
                    settings["mqttBaseTopic"] = mqtt_base_topic({"mqttBaseTopic": payload.get("mqttBaseTopic")})
                if "mqttClientId" in payload:
                    settings["mqttClientId"] = str(payload.get("mqttClientId") or "pixora-server").strip() or "pixora-server"
                if "mqttTls" in payload:
                    settings["mqttTls"] = mqtt_bool(payload.get("mqttTls"))
                if "hubitatHubIp" in payload:
                    settings["hubitatHubIp"] = str(payload.get("hubitatHubIp") or "").strip()
                if "hubitatAppId" in payload:
                    settings["hubitatAppId"] = str(payload.get("hubitatAppId") or "").strip()
                if "hubitatToken" in payload:
                    settings["hubitatToken"] = str(payload.get("hubitatToken") or "").strip()
                startup_result = None
                if "windowsStartupEnabled" in payload:
                    startup_result = set_windows_startup_enabled(bool(payload.get("windowsStartupEnabled")))
                quiet_sync_changed = any(key in payload for key in (
                    "quietBrightness", "defaultQuietStart", "defaultQuietEnd",
                ))
                write_settings(settings)
                if quiet_sync_changed:
                    queued = pushed = 0
                    for device in read_devices():
                        result = queue_device_quiet_hours_sync(device, push=True)
                        queued += 1
                        if result.get("pushed"):
                            pushed += 1
                    if queued:
                        log(f"[qh] Refreshed quiet-hours sync for {queued} devices after settings save ({pushed} pushed directly)")
                if mqtt_changed:
                    start_mqtt_client(settings)
                response = {"ok": True}
                if startup_result is not None:
                    response.update({
                        "windowsStartupSupported": startup_result.get("supported", False),
                        "windowsStartupEnabled": startup_result.get("enabled", False),
                        "windowsStartupCommand": startup_result.get("command", ""),
                        "windowsStartupError": startup_result.get("error", ""),
                    })
                self._send_json(200, response)
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/etsy/oauth/start":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                settings = read_settings()
                client_id = str(
                    payload.get("apiKey")
                    or os.environ.get("PIXORA_ETSY_API_KEY")
                    or settings.get("etsyApiKey")
                    or ""
                ).strip()
                if not client_id:
                    self._send_json(400, {"ok": False, "error": "Enter your Etsy API key first."})
                    return
                scopes = str(payload.get("scopes") or "shops_r transactions_r").strip() or "shops_r transactions_r"
                redirect_uri = etsy_redirect_uri(self)
                state = oauth_token_text(32)
                code_verifier = oauth_token_text(48)
                ETSY_OAUTH_STATE[state] = {
                    "client_id": client_id,
                    "code_verifier": code_verifier,
                    "redirect_uri": redirect_uri,
                    "created": datetime.now(timezone.utc),
                }
                params = urllib.parse.urlencode({
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "scope": scopes,
                    "state": state,
                    "code_challenge": pkce_challenge(code_verifier),
                    "code_challenge_method": "S256",
                })
                self._send_json(200, {
                    "ok": True,
                    "url": "https://www.etsy.com/oauth/connect?" + params,
                    "redirectUri": redirect_uri,
                    "scopes": scopes,
                })
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/etsy/oauth/finish":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                state = str(payload.get("state") or "").strip()
                code = str(payload.get("code") or "").strip()
                if not state or not code:
                    self._send_json(400, {"ok": False, "error": "Missing Etsy OAuth code or state."})
                    return
                prune_etsy_oauth_state()
                oauth_state = ETSY_OAUTH_STATE.pop(state, None)
                if not oauth_state:
                    self._send_json(400, {"ok": False, "error": "The Etsy OAuth session expired. Try Connect Etsy again."})
                    return
                token = exchange_etsy_oauth_code(oauth_state, code)
                self._send_json(200, {
                    "ok": True,
                    "accessToken": token.get("access_token") or "",
                    "refreshToken": token.get("refresh_token") or "",
                    "expiresIn": token.get("expires_in") or 3600,
                })
            except urllib.error.HTTPError as error:
                try:
                    raw = error.read().decode("utf-8", errors="ignore")
                except Exception:
                    raw = ""
                self._send_json(error.code if error.code in (400, 401, 403) else 502, {"ok": False, "error": raw or f"Etsy returned HTTP {error.code}"})
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
            return

        if self.path == "/api/fr24/usage":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                token = str(payload.get("token", "")).strip()
                period = str(payload.get("period", "30d")).strip()
                if period not in ("24h", "7d", "30d", "1y"):
                    period = "30d"
                if not token:
                    self._send_json(400, {"ok": False, "error": "Flightradar24 API token is required."})
                    return
                query = urllib.parse.urlencode({"period": period})
                req = urllib.request.Request(
                    f"https://fr24api.flightradar24.com/api/usage?{query}",
                    headers={
                        "User-Agent": "Pixora/0.1",
                        "Accept": "application/json",
                        "Accept-Version": "v1",
                        "Authorization": "Bearer " + token,
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                self._send_json(200, {"ok": True, "usage": raw, "period": period})
            except urllib.error.HTTPError as e:
                msg = "Flightradar24 rejected the token or usage request."
                if e.code == 429:
                    msg = "Flightradar24 rate limit reached."
                self._send_json(e.code if e.code in (400, 401, 403, 429) else 502, {"ok": False, "error": msg})
            except Exception as e:
                self._send_json(502, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/hubitat/devices":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                hub_ip = str(payload.get("hubIp", "")).strip()
                app_id = str(payload.get("appId", "")).strip()
                token = str(payload.get("token", "")).strip()
                if not all([hub_ip, app_id, token]):
                    self._send_json(400, {"ok": False, "error": "Hub IP, Maker API app number, and token are required."})
                    return
                if not re.match(r"^[A-Za-z0-9_.:-]+$", hub_ip):
                    self._send_json(400, {"ok": False, "error": "Invalid Hub IP or hostname."})
                    return
                url = f"http://{hub_ip}/apps/api/{app_id}/devices/all?access_token={urllib.parse.quote(token)}"
                req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                devices = []
                source = raw if isinstance(raw, list) else raw.get("devices", [])

                def hubitat_attributes(item):
                    attributes = []
                    raw_attrs = item.get("attributes", []) if isinstance(item, dict) else []
                    for attr in raw_attrs if isinstance(raw_attrs, list) else []:
                        name = str(attr.get("name") or "").strip() if isinstance(attr, dict) else ""
                        if name and name not in attributes:
                            attributes.append(name)
                    return attributes

                for item in source:
                    device_id = str(item.get("id") or item.get("deviceId") or "").strip()
                    label = str(item.get("label") or item.get("name") or device_id).strip()
                    if device_id:
                        devices.append({"id": device_id, "label": label, "attributes": hubitat_attributes(item)})

                missing = [device for device in devices if not device.get("attributes")]
                if missing:
                    quoted_token = urllib.parse.quote(token)

                    def fetch_device_attributes(device):
                        detail_url = f"http://{hub_ip}/apps/api/{app_id}/devices/{device['id']}?access_token={quoted_token}"
                        detail_req = urllib.request.Request(detail_url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
                        with urllib.request.urlopen(detail_req, timeout=4) as detail_resp:
                            detail = json.loads(detail_resp.read().decode("utf-8"))
                        return device["id"], hubitat_attributes(detail)

                    with ThreadPoolExecutor(max_workers=min(8, max(1, len(missing)))) as pool:
                        future_map = {pool.submit(fetch_device_attributes, device): device for device in missing}
                        for future in as_completed(future_map):
                            device = future_map[future]
                            try:
                                device_id, attributes = future.result()
                                if attributes:
                                    device["attributes"] = attributes
                            except Exception:
                                pass
                devices.sort(key=lambda item: item["label"].lower())
                self._send_json(200, {"ok": True, "devices": devices})
            except Exception as e:
                self._send_json(502, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/smartthings/devices":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                token = str(payload.get("token", "")).strip()
                if not token:
                    self._send_json(400, {"ok": False, "error": "SmartThings PAT token is required."})
                    return
                req = urllib.request.Request(
                    "https://api.smartthings.com/v1/devices",
                    headers={
                        "User-Agent": "Pixora/0.1",
                        "Accept": "application/json",
                        "Authorization": "Bearer " + token,
                    },
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                devices = []
                source = raw.get("items", []) if isinstance(raw, dict) else []
                for item in source:
                    device_id = str(item.get("deviceId") or item.get("id") or "").strip()
                    label = str(item.get("label") or item.get("name") or device_id).strip()
                    capabilities = []
                    for component in item.get("components") or []:
                        for capability in component.get("capabilities") or []:
                            cap_id = str(capability.get("id") or "").strip()
                            if cap_id and cap_id not in capabilities:
                                capabilities.append(cap_id)
                    if device_id:
                        devices.append({"id": device_id, "label": label, "capabilities": capabilities})
                devices.sort(key=lambda item: item["label"].lower())
                self._send_json(200, {"ok": True, "devices": devices})
            except urllib.error.HTTPError as e:
                msg = "SmartThings rejected the token or device request."
                if e.code == 401:
                    msg = "SmartThings token is invalid or expired."
                elif e.code == 403:
                    msg = "SmartThings token does not have device read permission."
                self._send_json(e.code if e.code in (400, 401, 403, 429) else 502, {"ok": False, "error": msg})
            except Exception as e:
                self._send_json(502, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/configure-usb":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                port = str(payload.get("port") or payload.get("usbPort") or "").strip()
                ssid = str(payload.get("ssid") or payload.get("wifiSsid") or "").strip()
                password = str(payload.get("password") or payload.get("wifiPassword") or "")
                remote_url = str(payload.get("remoteUrl") or "").strip()
                if not port:
                    self._send_json(400, {"ok": False, "error": "USB port is required."})
                    return
                if not ssid:
                    self._send_json(400, {"ok": False, "error": "Wi-Fi SSID is required."})
                    return
                if not password:
                    self._send_json(400, {"ok": False, "error": "Wi-Fi password is required."})
                    return
                if not remote_url:
                    self._send_json(400, {"ok": False, "error": "Device endpoint is required."})
                    return

                dev_id = device_id_from_remote_url(remote_url)
                hostname = dev_id[:32]
                command = [
                    POWERSHELL or "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "scripts" / "configure-device-usb.ps1"),
                    "-Port",
                    port,
                    "-WifiSsid",
                    ssid,
                    "-WifiPassword",
                    password,
                    "-RemoteUrl",
                    remote_url,
                    "-Hostname",
                    hostname,
                ]
                if payload.get("swapColors") or payload.get("swap_colors"):
                    command.append("-SwapColors")

                proc = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=clean_env(),
                    text=True,
                    capture_output=True,
                    timeout=45,
                )
                output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
                if proc.returncode != 0:
                    self._send_json(500, {"ok": False, "error": output or "USB Wi-Fi setup failed.", "output": output})
                    return

                existing = device_for_id(dev_id) or {}
                device = {
                    **default_device_fields(),
                    **existing,
                    "id":       dev_id,
                    "name":     existing.get("name") or payload.get("deviceName") or dev_id.replace("-", " ").replace("_", " "),
                    "ssid":     ssid,
                    "password": password,
                    "server":   re.sub(r"/[^/]+/next/?$", "", remote_url),
                    "endpoint": remote_url,
                    "target":   canonical_device_target(existing.get("target") or payload.get("target")) or "matrixportal-s3-64x32",
                    "cards":    existing.get("cards") or ["clock"],
                    "createdAt": existing.get("createdAt") or datetime.now(timezone.utc).isoformat(),
                }
                save_device(device)
                self._send_json(200, {"ok": True, "output": output or "Wi-Fi settings saved. Device is rebooting.", "device": device})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/wifi-ota":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                if content_length > 12_000_000:
                    self._send_json(413, {"ok": False, "error": "Firmware upload is too large."})
                    return
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                if FLASH_JOB["running"]:
                    self._send_json(409, {"ok": False, "error": "A firmware job is already running."})
                    return
                FLASH_JOB.update({"running": True, "done": False, "ok": None, "lines": [], "device": payload.get("deviceId")})
                threading.Thread(target=_run_wifi_ota_job, args=(payload,), daemon=True).start()
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/flash-firmware-file":
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                if content_length > 12_000_000:
                    self._send_json(413, {"ok": False, "error": "Firmware upload is too large."})
                    return
                payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
                if FLASH_JOB["running"]:
                    self._send_json(409, {"ok": False, "error": "A firmware job is already running."})
                    return
                FLASH_JOB.update({"running": True, "done": False, "ok": None, "lines": [], "device": payload.get("target")})
                threading.Thread(target=_run_official_firmware_file_flash, args=(payload,), daemon=True).start()
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/build-and-flash":
            self._send_json(403, {"ok": False, "error": "Firmware flashing is only supported with official release binaries."})
            return

        self.send_error(404)
        return


def main():
    global SERVER_PORT
    if "--pixora-esptool" in sys.argv:
        args = [arg for arg in sys.argv[1:] if arg != "--pixora-esptool"]
        import esptool
        raise SystemExit(esptool.main(args))

    ensure_user_dirs()
    load_cards()
    load_pending_ota_jobs()
    queue_startup_device_syncs()
    args = [arg for arg in sys.argv[1:] if arg]
    open_browser = "--no-browser" not in args
    args = [arg for arg in args if arg != "--no-browser"]
    port = int(args[0]) if args else 8088
    SERVER_PORT = port
    mdns = start_mdns(port)
    start_mqtt_client(read_settings())
    start_priority_graphic_watcher()
    start_update_checker()
    server = ThreadingHTTPServer(("0.0.0.0", port), PixoraHandler)
    url = f"http://pixora.local:{port}/"
    print(f"Pixora is running at {url}")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        PRIORITY_WATCH_STOP.set()
        UPDATE_CHECK_STOP.set()
        stop_mqtt_client()
        stop_mdns(mdns)


if __name__ == "__main__":
    main()
