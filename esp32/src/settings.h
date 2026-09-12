#pragma once

namespace settings {

// Load from NVS (namespace "resmon"); missing keys use the defaults.
void load();
// Save to NVS (called on every change).
void save();

int bright();       // 0-100, default 70
int color_mode();   // 0 = rgb, 1 = white, 2 = green; default 0
int auto_adv();     // 0 = off, 1 = 5 s, 2 = 10 s, 3 = 30 s; default 2
int auto_adv_ms();  // the auto-advance interval in ms (0 when off)

const char* ssid();
const char* pass();
void set_wifi(const char* ssid, const char* pass);  // strncpy into the buffers, NUL-terminate
void set_bright(int v);  // clamps 0-100
void set_color(int v);   // clamps 0-2
void set_auto(int v);    // clamps 0-3

// Advance one setting by one step, apply it (backlight PWM, etc.),
// save it to NVS and return the display string for the settings page.
// i: 0 = bright, 1 = colour, 2 = auto-advance, 3 = none (no-op).
const char* cycle(int i);

}
