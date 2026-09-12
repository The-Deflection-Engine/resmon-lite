#pragma once

// Thin wrapper around the panel driver so the display library can be
// swapped (e.g. LovyanGFX -> Arduino_GFX) without touching the pages.

namespace display {

// Initialise the GC9A01 240x240 round panel and the backlight PWM.
void init();

// Backlight brightness, 0-100.
void set_backlight(int pct);

// Fill the whole screen (start of a full redraw).
void fill_screen(unsigned int color);

// Arc: degrees, 0 = right, clockwise (y axis down).
// fill = solid arc, otherwise an outline.
void draw_arc(int cx, int cy, int radius, int width,
              float start_deg, float end_deg, unsigned int color, bool fill);

// Text. align: 0 = left, 1 = centred, 2 = right (relative to x).
void draw_string(const char* s, int x, int y, int font, unsigned int color, int align);

void set_text_font(int font);
int text_width(const char* s, int font);
void fill_rounded_rect(int x, int y, int w, int h, int r, unsigned int color);

}
