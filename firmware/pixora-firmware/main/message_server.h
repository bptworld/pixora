#pragma once

#include <stdbool.h>
#include <stdint.h>

// Start the HTTP server (:80) with /message, /status, /quiet-hours endpoints,
// and advertise the device via mDNS (<hostname>.local).
void message_server_start(void);

// Returns true if a message is queued and not yet expired.
bool message_is_pending(void);

// Display and animate the next queued message, blocking until it expires.
void message_display_and_wait(void);

// Returns true if the current local time falls within configured quiet hours.
bool message_is_quiet_hours(void);

// Returns the configured display brightness to use during quiet hours.
uint8_t message_quiet_brightness(void);

// Apply quiet-hours settings received via Pixora-Quiet-Hours response header.
// Format: enabled, start_hour, end_hour, utc_offset[, start_min, end_min, quiet_brightness].
void message_server_apply_quiet_hours(bool enabled, int16_t start_min, int16_t end_min, int8_t utc_offset, uint8_t quiet_brightness);
