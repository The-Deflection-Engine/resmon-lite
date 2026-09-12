#pragma once

// Protocol v1 telemetry (one JSON object per datagram/line).
// Null metrics arrive as JSON null and are stored as -1; GPU names are
// truncated to 24 chars. RAM/VRAM values are in MiB.
struct GpuT {
  char name[25];
  float util;     // % or -1
  float vram_pct; // % or -1
  float temp;     // deg C or -1
  float power;    // W or -1
  int vram_used;  // MiB or -1
  int vram_total; // MiB or -1
};

struct Telemetry {
  float cpu;      // % or -1
  float cpu_temp; // deg C or -1
  int ram_used;   // MiB or -1
  int ram_total;  // MiB or -1
  GpuT gpu[4];
  int n_gpu;
};

namespace pages {

// One draw function per page; each assumes a black screen (the caller
// does the full-redraw fillScreen first).
void draw_gpu(const Telemetry& t, int i);
void draw_cpu_ram(const Telemetry& t);
void draw_settings(int sel);
void draw_link_lost();

}
