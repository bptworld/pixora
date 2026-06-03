#include <esp_crt_bundle.h>
#include <esp_heap_caps.h>
#include <esp_http_client.h>
#include <esp_log.h>
#include <esp_netif.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <esp_tls.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "gfx.h"
#include "message_server.h"
#include "nvs_settings.h"
#include "sdkconfig.h"
#include "version.h"

static const char* TAG = "remote";

static const char* reset_reason_name(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON: return "POWERON";
    case ESP_RST_EXT: return "EXT";
    case ESP_RST_SW: return "SW";
    case ESP_RST_PANIC: return "PANIC";
    case ESP_RST_INT_WDT: return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT: return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_SDIO: return "SDIO";
    default: return "UNKNOWN";
  }
}

struct remote_state {
  void* buf;
  size_t len;
  size_t size;
  size_t max;
  int32_t brightness;
  int32_t dwell_secs;
  int32_t start_delay_ms;
  int64_t start_delay_received_us;
  char* ota_url;
  bool oversize_detected;
  bool reboot_after_response;
};

#define MAX(a, b) (((a) > (b)) ? (a) : (b))
#define MIN(a, b) (((a) < (b)) ? (a) : (b))

static esp_err_t _httpCallback(esp_http_client_event_t* event) {
  esp_err_t err = ESP_OK;
  struct remote_state* state = (struct remote_state*)event->user_data;

  switch (event->event_id) {
    case HTTP_EVENT_ERROR:
      ESP_LOGE(TAG, "HTTP_EVENT_ERROR");
      break;

    case HTTP_EVENT_ON_CONNECTED:
      ESP_LOGD(TAG, "HTTP_EVENT_ON_CONNECTED");
      break;

    case HTTP_EVENT_HEADER_SENT:
      ESP_LOGD(TAG, "HTTP_EVENT_HEADER_SENT");
      break;

    case HTTP_EVENT_ON_HEADER:
      ESP_LOGD(TAG, "HTTP_EVENT_ON_HEADER, key=%s, value=%s", event->header_key,
               event->header_value);

      // Check for the Content-Length header
      if (strcasecmp(event->header_key, "Content-Length") == 0) {
        size_t content_length = (size_t)atoi(event->header_value);
        if (content_length > state->max) {
          ESP_LOGE(TAG,
                   "Content-Length (%d bytes) exceeds allowed max (%d bytes)",
                   content_length, state->max);
          // Display the oversize graphic
          if (gfx_display_asset("oversize") != 0) {
            ESP_LOGE(TAG, "Failed to display oversize graphic");
          }
          state->oversize_detected = true;
          err = ESP_ERR_NO_MEM;
          esp_http_client_close(event->client);  // Abort the HTTP request
        } else {
          ESP_LOGI(TAG, "Content-Length Header : %d", content_length);
        }
      }

      // Check for the specific header key
      if (strcasecmp(event->header_key, "Pixora-Brightness") == 0) {
        state->brightness =
            (uint8_t)atoi(event->header_value);  // API spec: 0-100
        ESP_LOGD(TAG, "Pixora-Brightness value: %d%%", state->brightness);
      } else if (strcasecmp(event->header_key, "Pixora-Dwell-Secs") == 0) {
        state->dwell_secs = (int)atoi(event->header_value);
        // ESP_LOGI(TAG, "Pixora-Dwell-Secs value: %i", dwell_secs_value);
      } else if (strcasecmp(event->header_key, "Pixora-Start-Delay-Ms") == 0) {
        state->start_delay_ms = (int32_t)atoi(event->header_value);
        state->start_delay_received_us = esp_timer_get_time();
        ESP_LOGD(TAG, "Pixora-Start-Delay-Ms value: %ld",
                 (long)state->start_delay_ms);
      } else if (strcasecmp(event->header_key, "Pixora-OTA-URL") == 0) {
        if (state->ota_url != NULL) free(state->ota_url);
        state->ota_url = strdup(event->header_value);
        ESP_LOGI(TAG, "Found OTA URL: %s", state->ota_url);
      } else if (strcasecmp(event->header_key, "Pixora-Quiet-Hours") == 0) {
        int en = 0, st = 22, nd = 7, off = 0, st_min = -1, nd_min = -1, bright = message_quiet_brightness();
        int parsed = sscanf(event->header_value, "%d,%d,%d,%d,%d,%d,%d",
                            &en, &st, &nd, &off, &st_min, &nd_min, &bright);
        if (parsed >= 4) {
            if (parsed < 6) {
              st_min = st * 60;
              nd_min = nd * 60;
            }
            if (parsed < 7) bright = message_quiet_brightness();
            message_server_apply_quiet_hours((bool)en, (int16_t)st_min,
                                             (int16_t)nd_min, (int8_t)off,
                                             (uint8_t)bright);
            ESP_LOGI(TAG, "Quiet hours applied: en=%d %02d:%02d-%02d:%02d UTC%+d brightness=%d",
                     en, st_min / 60, st_min % 60, nd_min / 60, nd_min % 60, off, bright);
        }
      } else if (strcasecmp(event->header_key, "Pixora-Swap-Colors") == 0) {
        bool swap_colors = atoi(event->header_value) != 0;
        if (nvs_get_swap_colors() != swap_colors) {
          nvs_set_swap_colors(swap_colors);
          nvs_save_settings();
          state->reboot_after_response = true;
          ESP_LOGI(TAG, "Updated swap_colors to %s; reboot queued",
                   swap_colors ? "true" : "false");
        }
      }
      break;

    case HTTP_EVENT_ON_DATA:

      if (event->user_data == NULL) {
        ESP_LOGW(TAG, "Discarding HTTP response due to missing state");
        break;
      }

      // If oversize was detected, don't process any data
      if (state->oversize_detected) {
        ESP_LOGD(TAG, "Discarding HTTP data due to oversize detection");
        break;
      }

      // if (event->data_len > max_data_size) {
      //   ESP_LOGW(TAG, "Discarding HTTP response due to missing state");
      //   break;
      // }

      // If needed, resize the buffer to fit the new data
      if (event->data_len + state->len > state->size) {
        // Determine new size
        size_t next_size = state->size > 0
                               ? MIN(state->size * 2, state->max)
                               : CONFIG_HTTP_BUFFER_SIZE_DEFAULT;
        state->size = MAX(next_size, state->len + event->data_len);
        if (state->size > state->max) {
          ESP_LOGE(TAG, "Response size exceeds allowed max (%d bytes)",
                   state->max);
          // Display the oversize graphic
          if (gfx_display_asset("oversize") != 0) {
            ESP_LOGE(TAG, "Failed to display oversize graphic");
          }
          free(state->buf);
          state->buf = NULL;
          state->oversize_detected = true;
          err = ESP_ERR_NO_MEM;
          esp_http_client_close(event->client);  // Abort the HTTP request
          break;
        }

        // And reallocate
        void* new =
            heap_caps_realloc(state->buf, state->size, MALLOC_CAP_SPIRAM);
        if (new == NULL) {
          ESP_LOGE(TAG, "Resizing response buffer failed");
          free(state->buf);
          state->buf = NULL;
          err = ESP_ERR_NO_MEM;
          break;
        }
        state->buf = new;
      }

      // Copy over the new data
      memcpy(state->buf + state->len, event->data, event->data_len);
      state->len += event->data_len;
      break;

    case HTTP_EVENT_ON_FINISH:
      ESP_LOGD(TAG, "HTTP_EVENT_ON_FINISH");
      break;

    case HTTP_EVENT_DISCONNECTED:
      ESP_LOGD(TAG, "HTTP_EVENT_DISCONNECTED");

      int mbedtlsErr = 0;
      esp_err_t err =
          esp_tls_get_and_clear_last_error(event->data, &mbedtlsErr, NULL);
      if (err != ESP_OK) {
        ESP_LOGE(TAG, "HTTP error - %s (mbedtls: 0x%x)", esp_err_to_name(err),
                 mbedtlsErr);
      }
      break;

    case HTTP_EVENT_REDIRECT:
      ESP_LOGD(TAG, "HTTP_EVENT_REDIRECT");
      esp_http_client_set_redirection(event->client);
      break;
  }

  return err;
}

int remote_get(const char* url, uint8_t** buf, size_t* len,
               uint8_t* brightness_pct, int32_t* dwell_secs,
               int* return_status_code, char** ota_url,
               int32_t* start_delay_ms) {
  bool is_interrupt_request = strstr(url, "/interrupt") != NULL;
  size_t initial_size =
      is_interrupt_request ? 0 : CONFIG_HTTP_BUFFER_SIZE_DEFAULT;
  // State for processing the response
  struct remote_state state = {
      .buf = initial_size > 0
                 ? heap_caps_malloc(initial_size, MALLOC_CAP_SPIRAM)
                 : NULL,
      .len = 0,
      .size = initial_size,
      .max = CONFIG_HTTP_BUFFER_SIZE_MAX,
      .brightness = -1,
      .dwell_secs = -1,
      .start_delay_ms = -1,
      .start_delay_received_us = 0,
      .ota_url = NULL,
      .oversize_detected = false,
      .reboot_after_response = false,
  };

  if (initial_size > 0 && state.buf == NULL) {
    ESP_LOGE(TAG, "couldn't allocate HTTP receive buffer");
    return 1;
  }

  // Set up http client
  int timeout_ms = 20 * 1000;
  if (is_interrupt_request) {
    timeout_ms = 1500;
  } else if (strstr(url, "/next") != NULL) {
    timeout_ms = 12 * 1000;
  }

  esp_http_client_config_t config = {
      .url = url,
      .event_handler = _httpCallback,
      .user_data = &state,
      .timeout_ms = timeout_ms,
      .crt_bundle_attach = esp_crt_bundle_attach,
  };

  esp_http_client_handle_t http = esp_http_client_init(&config);
  if (http == NULL) {
    ESP_LOGE(TAG, "HTTP client initialization failed for URL: %s", url);
    free(state.buf);
    return 1;
  }

  if (esp_http_client_set_header(http, "X-Firmware-Version",
                                 FIRMWARE_VERSION) != ESP_OK) {
    ESP_LOGE(TAG, "Failed to set firmware version header");
  }
  char uptime_header[24];
  snprintf(uptime_header, sizeof(uptime_header), "%lld",
           (long long)(esp_timer_get_time() / 1000000LL));
  esp_http_client_set_header(http, "X-Pixora-Uptime", uptime_header);
  esp_http_client_set_header(http, "X-Pixora-Reset-Reason",
                             reset_reason_name(esp_reset_reason()));
  esp_http_client_set_header(http, "Connection", "close");

  char api_key[MAX_API_KEY_LEN + 1];
  if (nvs_get_api_key(api_key, sizeof(api_key)) == ESP_OK &&
      strlen(api_key) > 0) {
    char auth_header[64 + MAX_API_KEY_LEN];
    snprintf(auth_header, sizeof(auth_header), "Bearer %s", api_key);
    ESP_LOGD(TAG, "Using Authorization Bearer header");
    if (esp_http_client_set_header(http, "Authorization", auth_header) !=
        ESP_OK) {
      ESP_LOGE(TAG, "Failed to set Authorization header");
    }
  }

  // Do the request
  esp_err_t err = esp_http_client_perform(http);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "couldn't reach %s: %s", url, esp_err_to_name(err));
    if (state.buf != NULL) {
      free(state.buf);
    }
    esp_http_client_cleanup(http);
    return 1;
  }

  // Check if oversize was detected during the request
  if (state.oversize_detected) {
    ESP_LOGI(TAG, "Request aborted due to oversize content");
    if (state.buf != NULL) {
      free(state.buf);
    }
    if (state.ota_url != NULL) {
      free(state.ota_url);
    }
    esp_http_client_cleanup(http);
    *return_status_code = 413;  // HTTP 413 Payload Too Large
    return 1;  // Return error so main loop doesn't process the result
  }

  int status_code = esp_http_client_get_status_code(http);
  *return_status_code = status_code;
  if (status_code != 200) {
    ESP_LOGE(TAG, "Server returned HTTP status %d", status_code);
    if (state.buf != NULL) {
      free(state.buf);
    }
    if (state.ota_url != NULL) {
      free(state.ota_url);
    }
    esp_http_client_cleanup(http);
    return 1;
  }

  // Write back the results.
  *buf = state.buf;
  *len = state.len;
  if (state.brightness >= 0 && state.brightness <= 100) {
    *brightness_pct = (uint8_t)state.brightness;  // API provides 0-100.
  }
  if (state.dwell_secs > -1 && state.dwell_secs < 300)
    *dwell_secs = state.dwell_secs;  // 5 minute max ?
  *ota_url = state.ota_url;
  if (start_delay_ms != NULL && state.start_delay_ms >= 0) {
    int32_t adjusted_delay_ms = state.start_delay_ms;
    if (state.start_delay_received_us > 0) {
      int64_t elapsed_ms =
          (esp_timer_get_time() - state.start_delay_received_us) / 1000LL;
      adjusted_delay_ms =
          elapsed_ms >= state.start_delay_ms
              ? 0
              : state.start_delay_ms - (int32_t)elapsed_ms;
    }
    *start_delay_ms = adjusted_delay_ms;
  }

  esp_http_client_cleanup(http);
  if (state.reboot_after_response) {
    ESP_LOGI(TAG, "Rebooting to apply display color-order change");
    esp_restart();
  }
  // ESP_LOGI(TAG,"fetched new webp");
  return 0;
}
