#include <Arduino.h>
#include "display.h"
#include "settings.h"
#include "pages.h"

// Colours (matching the mockups).
static const unsigned int C_GREEN = 0x81C784;
static const unsigned int C_AMBER = 0xFFD54F;
static const unsigned int C_RED = 0xEF5350;
static const unsigned int C_TRACK = 0x2A2A2A;
static const unsigned int C_WHITE = 0xFFFFFF;
static const unsigned int C_DIM = 0x9A9A9A;
static const unsigned int C_HINT = 0x666666;

// The mockup px targets mapped to the closest built-in font (1-7).
static const int F_11 = 1;  // 9-11 px
static const int F_13 = 2;  // 13-14 px
static const int F_18 = 3;  // 18 px
static const int F_24 = 4;  // 24 px
static const int F_38 = 5;  // 38 px

static const float GAUGE_START = 135.0f;  // gap at the bottom
static const float GAUGE_SWEEP = 270.0f;

// Fixed thresholds (matching the host defaults); the host's custom
// thresholds are not propagated in protocol v1.
static unsigned int status_color(float pct) {
  int mode = settings::color_mode();
  if (pct < 0.0f) return C_DIM;
  if (mode == 1) return C_WHITE;
  if (mode == 2) return C_GREEN;
  if (pct >= 75.0f) return C_RED;
  if (pct >= 50.0f) return C_AMBER;
  return C_GREEN;
}

static unsigned int temp_color(float t) {
  int mode = settings::color_mode();
  if (t < 0.0f) return C_DIM;
  if (mode == 1) return C_WHITE;
  if (mode == 2) return C_GREEN;
  if (t >= 90.0f) return C_RED;
  if (t >= 75.0f) return C_AMBER;
  return C_GREEN;
}

// 270-degree gauge, gap at the bottom: full track, then the value fill.
static void gauge(int cx, int cy, int r, int w, float pct, unsigned int color) {
  display::draw_arc(cx, cy, r, w, GAUGE_START, GAUGE_START + GAUGE_SWEEP, C_TRACK, false);
  if (pct > 0.0f) {
    if (pct > 100.0f) pct = 100.0f;
    display::draw_arc(cx, cy, r, w, GAUGE_START, GAUGE_START + GAUGE_SWEEP * pct / 100.0f, color, true);
  }
}

namespace pages {

void draw_gpu(const Telemetry& t, int i) {
  const GpuT& g = t.gpu[i];
  char buf[32];

  // Name: 13 px, white, centred at y=22.
  display::draw_string(g.name, 120, 22, F_13, C_WHITE, 1);
  // Outer gauge (utilisation), inner gauge (VRAM %).
  gauge(120, 120, 80, 14, g.util, status_color(g.util));
  gauge(120, 120, 58, 10, g.vram_pct, status_color(g.vram_pct));
  // Utilisation number: 38 px, white, centred at y=88.
  if (g.util >= 0.0f)
    snprintf(buf, sizeof(buf), "%.0f%%", g.util);
  else
    snprintf(buf, sizeof(buf), "n/a");
  display::draw_string(buf, 120, 88, F_38, C_WHITE, 1);
  // VRAM line: 11 px, dim, centred at y=148.
  if (g.vram_used > 0 && g.vram_total > 0)
    snprintf(buf, sizeof(buf), "VRAM %.1f/%.1f GiB", g.vram_used / 1024.0f, g.vram_total / 1024.0f);
  else
    snprintf(buf, sizeof(buf), "VRAM n/a");
  display::draw_string(buf, 120, 148, F_11, C_DIM, 1);
  // Temperature: 13 px, left-aligned at x=52, y=206, temp-coloured.
  if (g.temp >= 0.0f)
    snprintf(buf, sizeof(buf), "%.0fC", g.temp);
  else
    snprintf(buf, sizeof(buf), "n/a");
  display::draw_string(buf, 52, 206, F_13, temp_color(g.temp), 0);
  // Power: 13 px, right-aligned ending at x=188, y=206, dim.
  if (g.power >= 0.0f)
    snprintf(buf, sizeof(buf), "%.0f W", g.power);
  else
    snprintf(buf, sizeof(buf), "n/a");
  display::draw_string(buf, 188 - display::text_width(buf, F_13), 206, F_13, C_DIM, 0);
}

void draw_cpu_ram(const Telemetry& t) {
  char buf[40];

  // Labels: 13 px, dim.
  display::draw_string("CPU", 62, 38, F_13, C_DIM, 1);
  display::draw_string("RAM", 178, 38, F_13, C_DIM, 1);
  // Gauges: r=48, width 12.
  float rp = (t.ram_used > 0 && t.ram_total > 0) ? 100.0f * t.ram_used / t.ram_total : -1.0f;
  gauge(62, 120, 48, 12, t.cpu, status_color(t.cpu));
  gauge(178, 120, 48, 12, rp, status_color(rp));
  // Numbers: 24 px, white.
  if (t.cpu >= 0.0f)
    snprintf(buf, sizeof(buf), "%.0f%%", t.cpu);
  else
    snprintf(buf, sizeof(buf), "n/a");
  display::draw_string(buf, 62, 104, F_24, C_WHITE, 1);
  if (rp >= 0.0f)
    snprintf(buf, sizeof(buf), "%.0f%%", rp);
  else
    snprintf(buf, sizeof(buf), "n/a");
  display::draw_string(buf, 178, 104, F_24, C_WHITE, 1);
  // Bottom line: 11 px, dim, centred at y=204.
  char temp_part[16], ram_part[24];
  if (t.cpu_temp >= 0.0f)
    snprintf(temp_part, sizeof(temp_part), "%.0fC", t.cpu_temp);
  else
    snprintf(temp_part, sizeof(temp_part), "n/a");
  if (t.ram_used > 0 && t.ram_total > 0)
    snprintf(ram_part, sizeof(ram_part), "%.1f/%.1f GiB", t.ram_used / 1024.0f, t.ram_total / 1024.0f);
  else
    snprintf(ram_part, sizeof(ram_part), "n/a");
  snprintf(buf, sizeof(buf), "%s - %s", temp_part, ram_part);
  display::draw_string(buf, 120, 204, F_11, C_DIM, 1);
}

void draw_settings(int sel) {
  char rows[4][24];
  const int ys[4] = {78, 108, 138, 168};

  // Title: 18 px bold, white, centred at y=36.
  display::draw_string("SETTINGS", 120, 36, F_18, C_WHITE, 1);
  snprintf(rows[0], sizeof(rows[0]), "BRIGHT  %d%%", settings::bright());
  const char* cm = settings::color_mode() == 0 ? "RGB" : (settings::color_mode() == 1 ? "WHITE" : "GRN");
  snprintf(rows[1], sizeof(rows[1]), "COLOR   %s", cm);
  const int av = settings::auto_adv();
  const char* av_s = av == 1 ? "5S" : (av == 2 ? "10S" : (av == 3 ? "30S" : "OFF"));
  snprintf(rows[2], sizeof(rows[2]), "AUTO    %s", av_s);
  snprintf(rows[3], sizeof(rows[3]), "B3 EXIT");
  for (int i = 0; i < 4; i++) {
    if (i == sel) {
      // Selected: rounded-rect background (text width + 16, height 27,
      // radius 6) + amber text.
      int w = display::text_width(rows[i], F_13);
      display::fill_rounded_rect(120 - w / 2 - 8, ys[i] - 5, w + 16, 27, 6, C_TRACK);
      display::draw_string(rows[i], 120, ys[i], F_13, C_AMBER, 1);
    } else {
      display::draw_string(rows[i], 120, ys[i], F_13, C_DIM, 1);
    }
  }
  // Hint: 9 px, centred at y=202.
  display::draw_string("B1/B2 SELECT - B3 CHANGE", 120, 202, F_11, C_HINT, 1);
}

void draw_link_lost() {
  // Track-only gauge.
  gauge(120, 120, 80, 14, -1.0f, C_TRACK);
  display::draw_string("LINK LOST", 120, 100, F_18, C_DIM, 1);
  display::draw_string("waiting for data", 120, 132, F_11, C_HINT, 1);
}

}
