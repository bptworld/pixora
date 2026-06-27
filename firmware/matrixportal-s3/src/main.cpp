#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Adafruit_Protomatter.h>
#include <Update.h>

#ifndef PIXORA_VERSION
#define PIXORA_VERSION "2.0.0-rebuild"
#endif

#ifndef PIXORA_DEVICE_TARGET
#define PIXORA_DEVICE_TARGET "matrixportal-s3"
#endif

#ifndef PIXORA_PANEL_WIDTH
#define PIXORA_PANEL_WIDTH 64
#endif

#ifndef PIXORA_PANEL_HEIGHT
#define PIXORA_PANEL_HEIGHT 32
#endif

#ifndef PIXORA_PANEL_CHAIN
#define PIXORA_PANEL_CHAIN 1
#endif

#ifndef PIXORA_RESET_CONFIG_ON_BOOT
#define PIXORA_RESET_CONFIG_ON_BOOT 0
#endif

#ifndef PIXORA_RESET_CONFIG_MARKER
#define PIXORA_RESET_CONFIG_MARKER "none"
#endif

// Adafruit MatrixPortal S3 HUB75 pin mapping.
// These names are supplied by the Adafruit board package.
static uint8_t rgbPins[] = {42, 41, 40, 38, 39, 37};
static uint8_t addrPins[] = {45, 36, 48, 35, 21};
static constexpr uint8_t addrPinCount = 4;
static constexpr uint8_t clockPin = 2;
static constexpr uint8_t latchPin = 47;
static constexpr uint8_t oePin = 14;

Adafruit_Protomatter matrix(
    PIXORA_PANEL_WIDTH,
    4,
    1,
    rgbPins,
    addrPinCount,
    addrPins,
    clockPin,
    latchPin,
    oePin,
    true);

Preferences prefs;

struct Config {
  String wifiSsid;
  String wifiPassword;
  String imageUrl;
  String serviceMode;
  String hostname;
  bool swapColors = false;
};

Config config;
String deviceId;
uint32_t lastPollMs = 0;
uint32_t dwellMs = 10000;
uint8_t brightnessPercent = 70;
bool hasDisplayedFrame = false;

String trimSlashes(String value) {
  value.trim();
  while (value.endsWith("/")) {
    value.remove(value.length() - 1);
  }
  return value;
}

String normalizeBaseUrl(String url) {
  url.trim();
  if (url.endsWith("/next")) {
    url.remove(url.length() - 5);
  }
  int nextIndex = url.indexOf("/next?");
  if (nextIndex >= 0) {
    url = url.substring(0, nextIndex);
  }
  return trimSlashes(url);
}

String urlEncode(const String &value) {
  const char *hex = "0123456789ABCDEF";
  String out;
  out.reserve(value.length());
  for (size_t i = 0; i < value.length(); i++) {
    uint8_t ch = (uint8_t)value[i];
    bool unreserved =
        (ch >= 'A' && ch <= 'Z') ||
        (ch >= 'a' && ch <= 'z') ||
        (ch >= '0' && ch <= '9') ||
        ch == '-' || ch == '_' || ch == '.' || ch == '~';
    if (unreserved) {
      out += (char)ch;
    } else {
      out += '%';
      out += hex[(ch >> 4) & 0x0F];
      out += hex[ch & 0x0F];
    }
  }
  return out;
}

String cloudDeviceId() {
  String id = config.hostname;
  id.trim();
  return id.isEmpty() ? deviceId : id;
}

uint16_t color565(uint8_t r, uint8_t g, uint8_t b) {
  return matrix.color565(r, g, b);
}

uint8_t scaleChannel(uint8_t value) {
  return (uint16_t)value * brightnessPercent / 100;
}

uint16_t scaleColor565(uint16_t pixel) {
  uint8_t r = ((pixel >> 11) & 0x1F) << 3;
  uint8_t g = ((pixel >> 5) & 0x3F) << 2;
  uint8_t b = (pixel & 0x1F) << 3;
  return color565(scaleChannel(r), scaleChannel(g), scaleChannel(b));
}

uint16_t color565Scaled(uint8_t r, uint8_t g, uint8_t b) {
  return color565(scaleChannel(r), scaleChannel(g), scaleChannel(b));
}

void setBrightnessPercent(uint8_t percent) {
  brightnessPercent = constrain(percent, 1, 100);
}

int16_t centeredX(const char *text, uint8_t textSize) {
  int16_t x1 = 0;
  int16_t y1 = 0;
  uint16_t w = 0;
  uint16_t h = 0;
  matrix.setTextSize(textSize);
  matrix.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  return max<int16_t>(0, (PIXORA_PANEL_WIDTH - w) / 2);
}

void showStatus(const char *line1, const char *line2, uint16_t color = 0) {
  if (!color) {
    color = color565Scaled(34, 217, 242);
  }
  matrix.fillScreen(0);
  matrix.setTextWrap(false);
  matrix.setTextColor(color);
  matrix.setTextSize(1);
  matrix.setCursor(centeredX(line1, 1), 7);
  matrix.print(line1);
  matrix.setCursor(centeredX(line2, 1), 18);
  matrix.print(line2);
  matrix.show();
}

void showProgressStatus(const char *line1, const char *line2, uint8_t percent, uint16_t color = 0) {
  if (!color) {
    color = color565Scaled(255, 210, 80);
  }
  uint8_t clamped = constrain(percent, 0, 100);
  uint16_t dim = color565Scaled(28, 38, 48);
  uint16_t fill = color;
  int barX = 4;
  int barY = PIXORA_PANEL_HEIGHT - 6;
  int barW = PIXORA_PANEL_WIDTH - 8;
  int fillW = (barW - 2) * clamped / 100;

  matrix.fillScreen(0);
  matrix.setTextWrap(false);
  matrix.setTextColor(color);
  matrix.setTextSize(1);
  matrix.setCursor(centeredX(line1, 1), 1);
  matrix.print(line1);
  matrix.setCursor(centeredX(line2, 1), 11);
  matrix.print(line2);
  matrix.drawRect(barX, barY, barW, 5, dim);
  if (fillW > 0) {
    matrix.fillRect(barX + 1, barY + 1, fillW, 3, fill);
  }
  matrix.show();
}

void showWifiStatus() {
  showStatus("WAITING", "FOR WIFI", color565Scaled(34, 217, 242));
}

void showCloudStatus() {
  showStatus("WAITING", "ON CLOUD", color565Scaled(20, 184, 166));
}

void showFirstCardStatus() {
  showStatus("FETCHING", "FIRST CARD", color565Scaled(20, 184, 166));
}

void showSetupStatus() {
  uint16_t color = color565Scaled(255, 210, 80);
  matrix.fillScreen(0);
  matrix.setTextWrap(false);
  matrix.setTextColor(color);
  matrix.setTextSize(1);
  matrix.setCursor(centeredX("SETUP WIFI", 1), 7);
  matrix.print("SETUP WIFI");
  matrix.setCursor(centeredX("OVER USB", 1), 21);
  matrix.print("OVER USB");
  matrix.show();
}

void makeDeviceId() {
  uint64_t mac = ESP.getEfuseMac();
  char buffer[32];
  snprintf(buffer, sizeof(buffer), "matrix-%u-%04x%08x", PIXORA_PANEL_WIDTH, (uint16_t)(mac >> 32), (uint32_t)mac);
  deviceId = buffer;
}

void loadConfig() {
  prefs.begin("pixora", true);
  config.wifiSsid = prefs.getString("ssid", "");
  config.wifiPassword = prefs.getString("pass", "");
  config.imageUrl = prefs.getString("url", "");
  config.serviceMode = prefs.getString("mode", "cloud");
  config.hostname = prefs.getString("host", "");
  config.swapColors = prefs.getBool("swap", false);
  prefs.end();
}

void resetConfigIfRequested() {
#if PIXORA_RESET_CONFIG_ON_BOOT
  prefs.begin("pixora", false);
  String marker = prefs.getString("resetMarker", "");
  if (marker != PIXORA_RESET_CONFIG_MARKER) {
    prefs.clear();
    prefs.putString("resetMarker", PIXORA_RESET_CONFIG_MARKER);
    Serial.println("Pixora settings cleared by this firmware image");
  }
  prefs.end();
#endif
}

bool saveConfig(const Config &next) {
  prefs.begin("pixora", false);
  bool ok = true;
  ok &= prefs.putString("ssid", next.wifiSsid) > 0 || next.wifiSsid.isEmpty();
  ok &= prefs.putString("pass", next.wifiPassword) > 0 || next.wifiPassword.isEmpty();
  ok &= prefs.putString("url", normalizeBaseUrl(next.imageUrl)) > 0 || next.imageUrl.isEmpty();
  ok &= prefs.putString("mode", next.serviceMode) > 0 || next.serviceMode.isEmpty();
  ok &= prefs.putString("host", next.hostname) > 0 || next.hostname.isEmpty();
  ok &= prefs.putBool("swap", next.swapColors);
  prefs.end();
  return ok;
}

bool applyUsbConfig(const String &line) {
  if (!line.startsWith("PIXORA_CONFIG ")) {
    return false;
  }
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, line.substring(14));
  if (error) {
    Serial.println("PIXORA_CONFIG_ERROR invalid-json");
    return true;
  }

  Config next = config;
  next.wifiSsid = doc["ssid"] | "";
  next.wifiPassword = doc["pass"] | "";
  next.imageUrl = doc["url"] | "";
  next.serviceMode = doc["mode"] | "cloud";
  next.hostname = doc["host"] | "";
  next.swapColors = doc["swapColors"] | false;

  if (next.wifiSsid.isEmpty() || next.imageUrl.isEmpty()) {
    Serial.println("PIXORA_CONFIG_ERROR missing-required");
    return true;
  }
  if (!saveConfig(next)) {
    Serial.println("PIXORA_CONFIG_SAVE_FAILED");
    return true;
  }
  Serial.println("PIXORA_CONFIG_SAVED");
  delay(250);
  ESP.restart();
  return true;
}

void serviceUsbConfig() {
  static String line;
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') {
      continue;
    }
    if (ch == '\n') {
      line.trim();
      if (line.length()) {
        applyUsbConfig(line);
      }
      line = "";
    } else if (line.length() < 2048) {
      line += ch;
    } else {
      line = "";
      Serial.println("PIXORA_CONFIG_ERROR line-too-long");
    }
  }
}

bool connectWifi() {
  if (config.wifiSsid.isEmpty()) {
    showSetupStatus();
    return false;
  }
  showWifiStatus();
  WiFi.mode(WIFI_STA);
  if (!config.hostname.isEmpty()) {
    WiFi.setHostname(config.hostname.c_str());
  }
  WiFi.begin(config.wifiSsid.c_str(), config.wifiPassword.c_str());
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 30000) {
    serviceUsbConfig();
    delay(100);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi connected: %s\n", WiFi.localIP().toString().c_str());
    showCloudStatus();
    return true;
  }
  showWifiStatus();
  return false;
}

String nextUrl() {
  String base = normalizeBaseUrl(config.imageUrl);
  String separator = base.indexOf('?') >= 0 ? "&" : "?";
  return base + "/next" + separator + "device=" + urlEncode(cloudDeviceId()) + "&target=" + PIXORA_DEVICE_TARGET + "-" + String(PIXORA_PANEL_WIDTH) + "x32&format=rgb565";
}

void applyResponseHeaders(HTTPClient &http) {
  int dwell = http.header("Pixora-Dwell-Secs").toInt();
  if (dwell > 0) {
    dwellMs = constrain(dwell, 1, 300) * 1000UL;
  }
  int brightness = http.header("Pixora-Brightness").toInt();
  if (brightness > 0) {
    setBrightnessPercent((uint8_t)brightness);
  }
  String reboot = http.header("Pixora-Reboot");
  String command = http.header("Pixora-Command");
  if (reboot == "1" || command == "reboot") {
    Serial.println("Reboot requested by cloud");
    delay(250);
    ESP.restart();
  }
}

bool beginHttp(HTTPClient &http, WiFiClientSecure &secureClient, WiFiClient &plainClient, const String &url) {
  if (url.startsWith("https://")) {
    secureClient.setInsecure();
    return http.begin(secureClient, url);
  }
  return http.begin(plainClient, url);
}

void performOta(const String &otaUrl) {
  if (otaUrl.isEmpty()) {
    return;
  }
  showProgressStatus("UPDATING", "FIRMWARE", 0, color565Scaled(255, 210, 80));
  Serial.printf("Starting OTA: %s\n", otaUrl.c_str());

  WiFiClientSecure secureClient;
  WiFiClient plainClient;
  HTTPClient ota;
  if (!beginHttp(ota, secureClient, plainClient, otaUrl)) {
    Serial.println("OTA begin failed");
    showCloudStatus();
    return;
  }
  ota.setTimeout(30000);
  int code = ota.GET();
  int length = ota.getSize();
  if (code != 200 || length <= 0) {
    Serial.printf("OTA download failed: HTTP %d length=%d\n", code, length);
    ota.end();
    showCloudStatus();
    return;
  }
  if (!Update.begin((size_t)length)) {
    Serial.printf("OTA Update.begin failed: %s\n", Update.errorString());
    ota.end();
    showCloudStatus();
    return;
  }
  WiFiClient *stream = ota.getStreamPtr();
  uint8_t buffer[1024];
  size_t written = 0;
  int lastPercent = -1;
  uint32_t lastPaint = 0;
  while (written < (size_t)length) {
    serviceUsbConfig();
    size_t available = stream->available();
    if (!available) {
      delay(1);
      continue;
    }
    size_t toRead = min(available, sizeof(buffer));
    toRead = min(toRead, (size_t)length - written);
    int readCount = stream->readBytes(buffer, toRead);
    if (readCount <= 0) {
      delay(1);
      continue;
    }
    size_t chunk = Update.write(buffer, readCount);
    if (chunk != (size_t)readCount) {
      Serial.printf("OTA write short: %u/%d error=%s\n", (unsigned)chunk, readCount, Update.errorString());
      break;
    }
    written += chunk;
    int percent = (int)((written * 100UL) / (size_t)length);
    if (percent != lastPercent && (percent == 100 || millis() - lastPaint > 150)) {
      showProgressStatus("UPDATING", "FIRMWARE", (uint8_t)percent, color565Scaled(255, 210, 80));
      lastPercent = percent;
      lastPaint = millis();
    }
  }
  bool ok = written == (size_t)length && Update.end(true);
  ota.end();
  if (!ok) {
    Serial.printf("OTA failed written=%u length=%d error=%s\n", (unsigned)written, length, Update.errorString());
    showCloudStatus();
    return;
  }
  Serial.println("OTA complete; rebooting");
  showStatus("UPDATE", "COMPLETE", color565Scaled(90, 230, 140));
  delay(3000);
  ESP.restart();
}

bool drawRgb565Stream(WiFiClient *stream, int length) {
  const int expected = PIXORA_PANEL_WIDTH * PIXORA_PANEL_HEIGHT * 2;
  if (length >= 0 && length != expected) {
    Serial.printf("Unexpected rgb565 length: %d expected %d\n", length, expected);
    showStatus("BAD FRAME", "SIZE", color565Scaled(255, 90, 90));
    return false;
  }

  uint8_t *frame = (uint8_t *)malloc(expected);
  if (!frame) {
    Serial.println("Failed to allocate rgb565 frame buffer");
    showStatus("FRAME", "NO MEM", color565Scaled(255, 90, 90));
    return false;
  }

  stream->setTimeout(15000);
  int received = 0;
  uint32_t lastDataMs = millis();
  while (received < expected) {
    serviceUsbConfig();
    int readCount = stream->readBytes(frame + received, expected - received);
    if (readCount > 0) {
      received += readCount;
      lastDataMs = millis();
      continue;
    }
    if (millis() - lastDataMs > 15000) {
      break;
    }
    delay(1);
  }

  if (received != expected) {
    Serial.printf("Short rgb565 frame: %d expected %d\n", received, expected);
    free(frame);
    showStatus("FRAME", "SHORT", color565Scaled(255, 90, 90));
    return false;
  }

  int index = 0;
  for (int y = 0; y < PIXORA_PANEL_HEIGHT; y++) {
    for (int x = 0; x < PIXORA_PANEL_WIDTH; x++) {
      uint8_t lo = frame[index++];
      uint8_t hi = frame[index++];
      uint16_t pixel = (uint16_t)lo | ((uint16_t)hi << 8);
      matrix.drawPixel(x, y, scaleColor565(pixel));
    }
  }
  free(frame);
  matrix.show();
  return true;
}

void pollNextFrame() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
    return;
  }
  if (config.imageUrl.isEmpty()) {
    showSetupStatus();
    return;
  }

  if (!hasDisplayedFrame) {
    showFirstCardStatus();
  } else {
    showCloudStatus();
  }
  String url = nextUrl();
  WiFiClientSecure secureClient;
  WiFiClient plainClient;
  HTTPClient http;
  const char *headers[] = {
      "Pixora-Dwell-Secs",
      "Pixora-Brightness",
      "Pixora-Reboot",
      "Pixora-Command",
      "Pixora-OTA-URL"};
  http.collectHeaders(headers, 5);
  http.setTimeout(15000);
  http.useHTTP10(true);
  if (!beginHttp(http, secureClient, plainClient, url)) {
    Serial.println("Frame HTTP begin failed");
    showStatus("HTTP", "BEGIN", color565Scaled(255, 90, 90));
    return;
  }
  http.addHeader("X-Firmware-Version", PIXORA_VERSION);
  http.addHeader("X-Pixora-Target", String(PIXORA_DEVICE_TARGET) + "-" + String(PIXORA_PANEL_WIDTH) + "x32");
  http.addHeader("X-Pixora-Accept", "rgb565");
  http.addHeader("X-Pixora-Uptime", String(millis() / 1000));

  int code = http.GET();
  if (code == 200) {
    applyResponseHeaders(http);
    String otaUrl = http.header("Pixora-OTA-URL");
    if (!otaUrl.isEmpty()) {
      http.end();
      performOta(otaUrl);
      return;
    }
    if (!drawRgb565Stream(http.getStreamPtr(), http.getSize())) {
      Serial.println("Failed to draw rgb565 frame");
      showCloudStatus();
    } else {
      hasDisplayedFrame = true;
    }
  } else {
    Serial.printf("Frame fetch failed: HTTP %d\n", code);
    char codeText[12];
    snprintf(codeText, sizeof(codeText), "%d", code);
    showStatus("HTTP", codeText, color565Scaled(255, 90, 90));
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(250);
  LittleFS.begin(true);
  makeDeviceId();
  resetConfigIfRequested();
  loadConfig();

  ProtomatterStatus status = matrix.begin();
  if (status != PROTOMATTER_OK) {
    Serial.printf("Matrix begin failed: %d\n", status);
  }
  setBrightnessPercent(brightnessPercent);
  showStatus("PIXORA", "BOOT");

  Serial.printf("Pixora firmware %s hardware=%s cloud=%s target=%s width=%d\n", PIXORA_VERSION, deviceId.c_str(), cloudDeviceId().c_str(), PIXORA_DEVICE_TARGET, PIXORA_PANEL_WIDTH);
  if (connectWifi()) {
    pollNextFrame();
    lastPollMs = millis();
  }
}

void loop() {
  serviceUsbConfig();
  if (millis() - lastPollMs >= dwellMs) {
    lastPollMs = millis();
    pollNextFrame();
  }
  delay(10);
}
