#include "message_server.h"

#include <cJSON.h>
#include <esp_heap_caps.h>
#include <esp_http_server.h>
#include <esp_log.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <mdns.h>  // espressif/mdns managed component
#include <nvs.h>
#include <string.h>
#include <time.h>

#include "display.h"
#include "gfx.h"
#include "nvs_settings.h"
#include "version.h"

static const char *TAG = "msg";

static const char *reset_reason_name(esp_reset_reason_t reason) {
    switch (reason) {
        case ESP_RST_POWERON:   return "POWERON";
        case ESP_RST_EXT:       return "EXT";
        case ESP_RST_SW:        return "SW";
        case ESP_RST_PANIC:     return "PANIC";
        case ESP_RST_INT_WDT:   return "INT_WDT";
        case ESP_RST_TASK_WDT:  return "TASK_WDT";
        case ESP_RST_WDT:       return "WDT";
        case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
        case ESP_RST_BROWNOUT:  return "BROWNOUT";
        case ESP_RST_SDIO:      return "SDIO";
        default:                return "UNKNOWN";
    }
}

// ── Types ─────────────────────────────────────────────────────────────────────

typedef enum { MODE_WRAP, MODE_SCROLL, MODE_FLASH } msg_mode_t;

typedef struct {
    char      text[256];
    uint8_t   r, g, b;
    msg_mode_t mode;
    int64_t   expires;   // esp_timer_get_time() µs
} msg_t;

// ── Message queue (3 slots, FIFO) ─────────────────────────────────────────────

#define QUEUE_CAP 3
static msg_t          s_queue[QUEUE_CAP];
static int            s_q_head  = 0;
static int            s_q_count = 0;
static portMUX_TYPE   s_q_mux   = portMUX_INITIALIZER_UNLOCKED;

// ── Quiet-hours state (persisted in NVS namespace "pixora_msg") ────────────────

#define QUIET_DEFAULT_BRIGHTNESS 5

static volatile bool  s_qh_enabled = false;
static volatile int16_t s_qh_start_min = 22 * 60;  // local minute of day (0-1439)
static volatile int16_t s_qh_end_min   = 7 * 60;
static volatile int8_t s_utc_off   = 0;    // local = UTC + s_utc_off
static volatile uint8_t s_qh_brightness = QUIET_DEFAULT_BRIGHTNESS;

// ── NVS helpers ───────────────────────────────────────────────────────────────

static void qh_load(void) {
    nvs_handle_t h;
    if (nvs_open("pixora_msg", NVS_READONLY, &h) != ESP_OK) return;
    uint8_t en = 0, st = 22, en2 = 7, bright = QUIET_DEFAULT_BRIGHTNESS;
    uint16_t st_min = 0xffff, en_min = 0xffff;
    int8_t  off = 0;
    nvs_get_u8(h, "qh_en",    &en);
    nvs_get_u8(h, "qh_start", &st);
    nvs_get_u8(h, "qh_end",   &en2);
    nvs_get_u16(h, "qh_st_min", &st_min);
    nvs_get_u16(h, "qh_end_min", &en_min);
    nvs_get_i8(h, "qh_off",   &off);
    if (nvs_get_u8(h, "qh_bright", &bright) != ESP_OK) {
        bright = QUIET_DEFAULT_BRIGHTNESS;
    }
    s_qh_enabled = (bool)en;
    s_qh_start_min = st_min <= 1439 ? (int16_t)st_min : (int16_t)st * 60;
    s_qh_end_min   = en_min <= 1439 ? (int16_t)en_min : (int16_t)en2 * 60;
    s_utc_off    = off;
    s_qh_brightness = bright <= DISPLAY_MAX_BRIGHTNESS ? bright : 0;
    nvs_close(h);
}

static void qh_save(void) {
    nvs_handle_t h;
    if (nvs_open("pixora_msg", NVS_READWRITE, &h) != ESP_OK) return;
    nvs_set_u8(h, "qh_en",    s_qh_enabled ? 1 : 0);
    nvs_set_u8(h, "qh_start", (uint8_t)(s_qh_start_min / 60));
    nvs_set_u8(h, "qh_end",   (uint8_t)(s_qh_end_min / 60));
    nvs_set_u16(h, "qh_st_min", (uint16_t)s_qh_start_min);
    nvs_set_u16(h, "qh_end_min", (uint16_t)s_qh_end_min);
    nvs_set_i8(h, "qh_off",   s_utc_off);
    nvs_set_u8(h, "qh_bright", s_qh_brightness);
    nvs_commit(h);
    nvs_close(h);
}

static int16_t clamp_minute_of_day(int value, int fallback) {
    if (value < 0 || value > 1439) return (int16_t)fallback;
    return (int16_t)value;
}

// ── Color parsing ─────────────────────────────────────────────────────────────

static void parse_color(const char *c, uint8_t *r, uint8_t *g, uint8_t *b) {
    *r = *g = *b = 255;
    if (!c || !*c) return;
    if (c[0] == '#' && strlen(c) == 7) {
        unsigned rv = 255, gv = 255, bv = 255;
        sscanf(c + 1, "%02x%02x%02x", &rv, &gv, &bv);
        *r = (uint8_t)rv; *g = (uint8_t)gv; *b = (uint8_t)bv;
        return;
    }
    if (strcasecmp(c, "red")    == 0) { *r=238; *g=80;  *b=80;  return; }
    if (strcasecmp(c, "green")  == 0) { *r=80;  *g=220; *b=120; return; }
    if (strcasecmp(c, "blue")   == 0) { *r=100; *g=180; *b=255; return; }
    if (strcasecmp(c, "yellow") == 0) { *r=255; *g=220; *b=50;  return; }
    if (strcasecmp(c, "orange") == 0) { *r=255; *g=150; *b=40;  return; }
    if (strcasecmp(c, "cyan")   == 0) { *r=50;  *g=220; *b=210; return; }
    if (strcasecmp(c, "purple") == 0) { *r=180; *g=80;  *b=220; return; }
    if (strcasecmp(c, "pink")   == 0) { *r=255; *g=100; *b=180; return; }
}

// ── Display helpers ───────────────────────────────────────────────────────────

#define LINE_CHARS 10
#define LINE_H     8
#define MAX_LINES  4

static void draw_wrapped(const msg_t *m) {
    char lines[MAX_LINES][LINE_CHARS + 1];
    int  lc = 0;
    const char *p = m->text;
    while (*p && lc < MAX_LINES) {
        int take = 0, last_sp = -1;
        while (take < LINE_CHARS && p[take]) {
            if (p[take] == ' ') last_sp = take;
            take++;
        }
        if (p[take] && last_sp > 0 && take == LINE_CHARS) take = last_sp;
        strncpy(lines[lc], p, take);
        lines[lc][take] = '\0';
        p += take;
        if (*p == ' ') p++;
        lc++;
    }
    int y = (32 - lc * LINE_H) / 2;
    display_clear();
    for (int i = 0; i < lc; i++) {
        int lw = (int)strlen(lines[i]) * 6;
        display_text(lines[i], (64 - lw) / 2, y + i * LINE_H, m->r, m->g, m->b, 1);
    }
    display_flip();
}

static void run_message(const msg_t *m) {
    if (m->mode == MODE_SCROLL) {
        int text_px = (int)strlen(m->text) * 6;
        int x   = 64;
        int end = -text_px;
        int y   = (32 - LINE_H) / 2;
        while (esp_timer_get_time() < m->expires && x > end) {
            display_clear();
            display_text(m->text, x, y, m->r, m->g, m->b, 1);
            display_flip();
            vTaskDelay(pdMS_TO_TICKS(33));
            x -= 2;
        }
        display_clear();
        display_flip();
        while (esp_timer_get_time() < m->expires)
            vTaskDelay(pdMS_TO_TICKS(100));

    } else if (m->mode == MODE_FLASH) {
        bool      on          = true;
        int64_t   next_toggle = esp_timer_get_time();
        draw_wrapped(m);
        while (esp_timer_get_time() < m->expires) {
            if (esp_timer_get_time() >= next_toggle) {
                if (on) {
                    draw_wrapped(m);
                    next_toggle = esp_timer_get_time() + 500000LL;
                } else {
                    display_clear();
                    display_flip();
                    next_toggle = esp_timer_get_time() + 250000LL;
                }
                on = !on;
            }
            vTaskDelay(pdMS_TO_TICKS(20));
        }

    } else {
        draw_wrapped(m);
        while (esp_timer_get_time() < m->expires)
            vTaskDelay(pdMS_TO_TICKS(100));
    }
}

// ── HTTP handlers ─────────────────────────────────────────────────────────────

static esp_err_t post_message(httpd_req_t *req) {
    char buf[512];
    int n = httpd_req_recv(req, buf,
                           req->content_len < sizeof(buf) - 1
                               ? req->content_len : sizeof(buf) - 1);
    if (n <= 0) { httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Empty body"); return ESP_FAIL; }
    buf[n] = '\0';

    cJSON *root = cJSON_Parse(buf);
    if (!root) { httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON"); return ESP_FAIL; }

    msg_t m = {0};
    m.r = m.g = m.b = 255;
    m.mode = MODE_WRAP;

    cJSON *tj = cJSON_GetObjectItem(root, "text");
    strncpy(m.text, cJSON_IsString(tj) ? tj->valuestring : "", sizeof(m.text) - 1);

    int dur = 10;
    cJSON *dj = cJSON_GetObjectItem(root, "duration");
    if (cJSON_IsNumber(dj)) { dur = dj->valueint; if (dur < 1) dur = 1; if (dur > 300) dur = 300; }

    cJSON *cj = cJSON_GetObjectItem(root, "color");
    parse_color(cJSON_IsString(cj) ? cj->valuestring : "white", &m.r, &m.g, &m.b);

    cJSON *mj = cJSON_GetObjectItem(root, "mode");
    if (cJSON_IsString(mj)) {
        if (strcasecmp(mj->valuestring, "scroll") == 0) m.mode = MODE_SCROLL;
        else if (strcasecmp(mj->valuestring, "flash") == 0) m.mode = MODE_FLASH;
    }
    cJSON_Delete(root);

    m.expires = esp_timer_get_time() + (int64_t)dur * 1000000LL;

    // Enqueue (drop oldest if full)
    taskENTER_CRITICAL(&s_q_mux);
    if (s_q_count < QUEUE_CAP) {
        s_queue[(s_q_head + s_q_count) % QUEUE_CAP] = m;
        s_q_count++;
    } else {
        // Full: overwrite oldest slot
        s_queue[s_q_head] = m;
        s_q_head = (s_q_head + 1) % QUEUE_CAP;
    }
    taskEXIT_CRITICAL(&s_q_mux);

    isAnimating = -1;

    ESP_LOGI(TAG, "Queued: \"%s\" %ds mode=%d (queue=%d)", m.text, dur, (int)m.mode, s_q_count);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{\"ok\":true}");
    return ESP_OK;
}

static esp_err_t get_status(httpd_req_t *req) {
    int rssi_raw = 0;
    int8_t rssi = 0;
    if (esp_wifi_sta_get_rssi(&rssi_raw) == ESP_OK) rssi = (int8_t)rssi_raw;

    uint32_t heap     = esp_get_free_heap_size();
    uint32_t min_heap = heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT);
    int64_t  uptime   = esp_timer_get_time() / 1000000LL;
    esp_reset_reason_t reset_reason = esp_reset_reason();

    int q_pending;
    taskENTER_CRITICAL(&s_q_mux);
    q_pending = s_q_count;
    taskEXIT_CRITICAL(&s_q_mux);

    char json[448];
    snprintf(json, sizeof(json),
        "{\"firmware\":\"%s\",\"rssi\":%d,\"free_heap\":%lu,\"min_free_heap\":%lu,"
        "\"uptime_s\":%lld,\"reset_reason\":\"%s\",\"msg_queued\":%d,\"swap_colors\":%s,"
        "\"quiet_hours\":{\"enabled\":%s,\"start\":%d,\"end\":%d,\"start_min\":%d,\"end_min\":%d,\"utc_offset\":%d,\"brightness\":%u}}",
        FIRMWARE_VERSION, rssi, (unsigned long)heap, (unsigned long)min_heap,
        (long long)uptime, reset_reason_name(reset_reason), q_pending,
        nvs_get_swap_colors() ? "true" : "false",
        s_qh_enabled ? "true" : "false", s_qh_start_min / 60, s_qh_end_min / 60,
        s_qh_start_min, s_qh_end_min, s_utc_off, s_qh_brightness);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, json);
    return ESP_OK;
}

static esp_err_t post_quiet_hours(httpd_req_t *req) {
    char buf[256];
    int n = httpd_req_recv(req, buf,
                           req->content_len < sizeof(buf) - 1
                               ? req->content_len : sizeof(buf) - 1);
    if (n <= 0) { httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Empty body"); return ESP_FAIL; }
    buf[n] = '\0';

    cJSON *root = cJSON_Parse(buf);
    if (!root) { httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON"); return ESP_FAIL; }

    cJSON *ej = cJSON_GetObjectItem(root, "enabled");
    cJSON *sj = cJSON_GetObjectItem(root, "start");
    cJSON *nj = cJSON_GetObjectItem(root, "end");
    cJSON *smj = cJSON_GetObjectItem(root, "start_min");
    cJSON *emj = cJSON_GetObjectItem(root, "end_min");
    cJSON *oj = cJSON_GetObjectItem(root, "utc_offset");
    cJSON *bj = cJSON_GetObjectItem(root, "brightness");

    if (cJSON_IsBool(ej))   s_qh_enabled = cJSON_IsTrue(ej);
    if (cJSON_IsNumber(smj)) {
        s_qh_start_min = clamp_minute_of_day(smj->valueint, s_qh_start_min);
    } else if (cJSON_IsNumber(sj)) {
        s_qh_start_min = clamp_minute_of_day(sj->valueint * 60, s_qh_start_min);
    }
    if (cJSON_IsNumber(emj)) {
        s_qh_end_min = clamp_minute_of_day(emj->valueint, s_qh_end_min);
    } else if (cJSON_IsNumber(nj)) {
        s_qh_end_min = clamp_minute_of_day(nj->valueint * 60, s_qh_end_min);
    }
    if (cJSON_IsNumber(oj)) s_utc_off    = (int8_t)oj->valueint;
    if (cJSON_IsNumber(bj)) {
        int value = bj->valueint;
        if (value < DISPLAY_MIN_BRIGHTNESS) value = DISPLAY_MIN_BRIGHTNESS;
        if (value > DISPLAY_MAX_BRIGHTNESS) value = DISPLAY_MAX_BRIGHTNESS;
        s_qh_brightness = (uint8_t)value;
    }
    cJSON_Delete(root);

    qh_save();
    ESP_LOGI(TAG, "Quiet hours: en=%d %02d:%02d-%02d:%02d UTC%+d brightness=%u",
             s_qh_enabled, s_qh_start_min / 60, s_qh_start_min % 60,
             s_qh_end_min / 60, s_qh_end_min % 60, s_utc_off, s_qh_brightness);
    if (message_is_quiet_hours()) {
        display_set_brightness(s_qh_brightness);
    }

    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{\"ok\":true}");
    return ESP_OK;
}

static esp_err_t post_reboot(httpd_req_t *req) {
    ESP_LOGI(TAG, "Reboot requested over HTTP");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{\"ok\":true}");
    vTaskDelay(pdMS_TO_TICKS(250));
    esp_restart();
    return ESP_OK;
}

// ── Public API ────────────────────────────────────────────────────────────────

void message_server_start(void) {
    // Load persisted quiet-hours settings
    qh_load();

    // mDNS — device reachable as <hostname>.local
    char hostname[33] = {0};
    if (nvs_get_hostname(hostname, sizeof(hostname)) != ESP_OK || !hostname[0])
        strncpy(hostname, "pixora", sizeof(hostname) - 1);
    esp_err_t mdns_err = mdns_init();
    if (mdns_err == ESP_OK) {
        mdns_hostname_set(hostname);
        mdns_instance_name_set("Pixora Display");
        mdns_service_add(NULL, "_pixora", "_tcp", 80, NULL, 0);
        ESP_LOGI(TAG, "mDNS: %s.local", hostname);
    } else {
        ESP_LOGI(TAG, "mDNS already active for %s.local", hostname);
    }

    // HTTP server
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port    = 80;
    cfg.max_uri_handlers = 6;

    httpd_handle_t srv = NULL;
    if (httpd_start(&srv, &cfg) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTP server");
        return;
    }

    httpd_uri_t uris[] = {
        { .uri="/message",     .method=HTTP_POST, .handler=post_message     },
        { .uri="/status",      .method=HTTP_GET,  .handler=get_status       },
        { .uri="/quiet-hours", .method=HTTP_POST, .handler=post_quiet_hours },
        { .uri="/reboot",      .method=HTTP_POST, .handler=post_reboot      },
    };
    int uri_count = sizeof(uris) / sizeof(uris[0]);
    for (int i = 0; i < uri_count; i++)
        httpd_register_uri_handler(srv, &uris[i]);

    ESP_LOGI(TAG, "HTTP server on :80  (mDNS: %s.local)", hostname);
}

bool message_is_pending(void) {
    bool pending;
    taskENTER_CRITICAL(&s_q_mux);
    // Drop any expired messages at the head
    while (s_q_count > 0 && esp_timer_get_time() >= s_queue[s_q_head].expires) {
        s_q_head  = (s_q_head + 1) % QUEUE_CAP;
        s_q_count--;
    }
    pending = (s_q_count > 0);
    taskEXIT_CRITICAL(&s_q_mux);
    return pending;
}

void message_display_and_wait(void) {
    msg_t m;

    taskENTER_CRITICAL(&s_q_mux);
    if (s_q_count == 0) { taskEXIT_CRITICAL(&s_q_mux); return; }
    m = s_queue[s_q_head];          // copy out
    s_q_head  = (s_q_head + 1) % QUEUE_CAP;
    s_q_count--;
    taskEXIT_CRITICAL(&s_q_mux);

    if (esp_timer_get_time() >= m.expires) return;  // already expired

    gfx_stop();
    run_message(&m);
    gfx_start();
    isAnimating = 1;
}

void message_server_apply_quiet_hours(bool enabled, int16_t start_min, int16_t end_min, int8_t utc_offset, uint8_t quiet_brightness) {
    s_qh_enabled = enabled;
    s_qh_start_min = clamp_minute_of_day(start_min, 22 * 60);
    s_qh_end_min   = clamp_minute_of_day(end_min, 7 * 60);
    s_utc_off    = utc_offset;
    s_qh_brightness = quiet_brightness <= DISPLAY_MAX_BRIGHTNESS ? quiet_brightness : 0;
    qh_save();
    ESP_LOGI(TAG, "Quiet hours applied via header: en=%d %02d:%02d-%02d:%02d UTC%+d brightness=%u",
             enabled, s_qh_start_min / 60, s_qh_start_min % 60,
             s_qh_end_min / 60, s_qh_end_min % 60, utc_offset, s_qh_brightness);
}

uint8_t message_quiet_brightness(void) {
    return s_qh_brightness;
}

bool message_is_quiet_hours(void) {
    if (!s_qh_enabled) return false;

    time_t now_utc;
    time(&now_utc);
    if (now_utc < 100000) return false;  // SNTP not yet synced

    // Convert UTC to local minute of day.
    int local_min = (int)(((now_utc / 60) + (s_utc_off * 60) + (24 * 60)) % (24 * 60));

    int start = s_qh_start_min, end = s_qh_end_min;
    if (start < end)
        return local_min >= start && local_min < end;
    else  // wraps midnight
        return local_min >= start || local_min < end;
}

#undef LINE_CHARS
#undef LINE_H
#undef MAX_LINES
