#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <ESPmDNS.h>
#include <ArduinoJson.h>
#include "config.h"
#include "display.h"
#include "pages.h"
#include "buttons.h"
#include "settings.h"

static WiFiUDP wifi_udp;

static Telemetry cur;
static uint32_t last_data = 0;
static uint32_t last_btn = 0;
static uint32_t last_advance = 0;
static bool dirty = true;
static bool showing_lost = true;
static bool in_settings = false;
static int page = 0;  // 0..n_gpu-1 = GPU pages, n_gpu = the CPU/RAM page
static int sel = 0;   // settings selection
static char line_buf[512];
static int line_len = 0;

static int total_pages() {
  return cur.n_gpu + 1;
}

// Parse one protocol v1 line; a bad line is ignored.
static void parse(const char* line) {
  JsonDocument doc;
  if (deserializeJson(doc, line)) return;  // operator! is true on error
  Telemetry t;
  t.cpu = doc["cpu"] | -1.0f;
  t.cpu_temp = doc["ct"] | -1.0f;
  t.ram_used = doc["ru"] | -1;
  t.ram_total = doc["rt"] | -1;
  t.n_gpu = 0;
  JsonArray arr = doc["g"];
  for (JsonObject o : arr) {
    if (t.n_gpu >= 4) break;
    GpuT& g = t.gpu[t.n_gpu];
    g.name[0] = 0;
    strncpy(g.name, o["n"] | "", sizeof(g.name) - 1);
    g.name[sizeof(g.name) - 1] = 0;
    g.util = o["u"] | -1.0f;
    int v = o["v"] | -1;
    int vt = o["vt"] | -1;
    g.vram_used = v;
    g.vram_total = vt;
    g.vram_pct = (v > 0 && vt > 0) ? 100.0f * v / vt : -1.0f;
    g.temp = o["t"] | -1.0f;
    g.power = o["p"] | -1.0f;
    t.n_gpu++;
  }
  cur = t;
  last_data = millis();
  dirty = true;
}

static void apply_event(BtnEvent ev) {
  if (in_settings) {
    switch (ev) {
      case BtnEvent::Next:
        sel = (sel + 1) % 4;
        dirty = true;
        break;
      case BtnEvent::Prev:
        sel = (sel + 3) % 4;
        dirty = true;
        break;
      case BtnEvent::Cycle:
        settings::cycle(sel);  // applies + saves; the page reads the new value
        dirty = true;
        break;
      case BtnEvent::Exit:
        in_settings = false;
        dirty = true;
        break;
      default:
        break;
    }
  } else {
    switch (ev) {
      case BtnEvent::Next:
        page = (page + 1) % total_pages();
        dirty = true;
        break;
      case BtnEvent::Prev:
        page = (page - 1 + total_pages()) % total_pages();
        dirty = true;
        break;
      case BtnEvent::Settings:
        in_settings = true;
        sel = 0;
        dirty = true;
        break;
      default:  // Cycle/Exit in main mode: ignore
        break;
    }
  }
}

void setup() {
  display::init();
  settings::load();
  Serial.begin(SERIAL_BAUD);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  MDNS.begin(MDNS_HOST);
  wifi_udp.begin(UDP_PORT);
  buttons::init();
  display::set_backlight(settings::bright());
  last_advance = millis();
  display::fill_screen(0x000000);
  pages::draw_link_lost();
}

void loop() {
  // 1. UDP.
  int len = wifi_udp.parsePacket();
  if (len > 0) {
    len = wifi_udp.read((uint8_t*)line_buf, sizeof(line_buf) - 1);
    if (len > 0) {
      line_buf[len] = 0;
      parse(line_buf);
    }
  }
  // 2. Serial (one JSON object per \n-terminated line).
  while (Serial.available()) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\n' || c == '\r') {
      if (line_len > 0) {
        line_buf[line_len] = 0;
        parse(line_buf);
        line_len = 0;
      }
    } else if (line_len < (int)sizeof(line_buf) - 1) {
      line_buf[line_len++] = (char)c;
    }
  }
  // 3. Buttons.
  BtnEvent ev = buttons::poll(in_settings);
  if (ev != BtnEvent::None) {
    last_btn = millis();
    apply_event(ev);
  }
  // 4. Auto-advance.
  int adv = settings::auto_adv_ms();
  if (adv > 0 && !in_settings) {
    if (millis() - last_btn >= (uint32_t)adv && millis() - last_advance >= (uint32_t)adv) {
      page = (page + 1) % total_pages();
      last_advance = millis();
      dirty = true;
    }
  }
  // 5. Link lost / recovered.
  bool lost = (millis() - last_data > 10000);
  if (lost != showing_lost) {
    showing_lost = lost;
    if (lost) in_settings = false;
    dirty = true;
  }
  // 6. Redraw on new data or a page/settings change (0.5 Hz is fine).
  if (page >= total_pages()) page = 0;
  if (dirty) {
    display::fill_screen(0x000000);
    if (showing_lost)
      pages::draw_link_lost();
    else if (in_settings)
      pages::draw_settings(sel);
    else if (page < cur.n_gpu)
      pages::draw_gpu(cur, page);
    else
      pages::draw_cpu_ram(cur);
    dirty = false;
  }
  delay(5);
}
