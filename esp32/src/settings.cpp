#include <Preferences.h>
#include "settings.h"
#include "display.h"

static Preferences prefs;
static int s_bright = 70;
static int s_color = 0;
static int s_auto = 2;
static char s_ssid[33];
static char s_pass[64];
static char s_buf[16];

namespace settings {

void load() {
  prefs.begin("resmon", true);  // read-only
  s_bright = prefs.getUChar("bright", 70);
  s_color = prefs.getUChar("color", 0);
  s_auto = prefs.getUChar("auto", 2);
  prefs.getString("ssid", s_ssid, sizeof(s_ssid));
  prefs.getString("pass", s_pass, sizeof(s_pass));
  prefs.end();
}

void save() {
  prefs.begin("resmon", false);
  prefs.putUChar("bright", s_bright);
  prefs.putUChar("color", s_color);
  prefs.putUChar("auto", s_auto);
  prefs.putString("ssid", s_ssid);
  prefs.putString("pass", s_pass);
  prefs.end();
}

int bright() {
  return s_bright;
}

int color_mode() {
  return s_color;
}

int auto_adv() {
  return s_auto;
}

int auto_adv_ms() {
  switch (s_auto) {
    case 1:
      return 5000;
    case 2:
      return 10000;
    case 3:
      return 30000;
    default:
      return 0;
  }
}

const char* ssid() {
  return s_ssid;
}

const char* pass() {
  return s_pass;
}

void set_wifi(const char* ssid, const char* pass) {
  strncpy(s_ssid, ssid, sizeof(s_ssid) - 1);
  s_ssid[sizeof(s_ssid) - 1] = 0;
  strncpy(s_pass, pass, sizeof(s_pass) - 1);
  s_pass[sizeof(s_pass) - 1] = 0;
}

void set_bright(int v) {
  s_bright = v < 0 ? 0 : (v > 100 ? 100 : v);
}

void set_color(int v) {
  s_color = v < 0 ? 0 : (v > 2 ? 2 : v);
}

void set_auto(int v) {
  s_auto = v < 0 ? 0 : (v > 3 ? 3 : v);
}

const char* cycle(int i) {
  switch (i) {
    case 0:
      s_bright = ((s_bright / 10) + 1) % 11 * 10;
      display::set_backlight(s_bright);
      snprintf(s_buf, sizeof(s_buf), "%d%%", s_bright);
      save();
      return s_buf;
    case 1:
      s_color = (s_color + 1) % 3;
      save();
      return s_color == 0 ? "RGB" : (s_color == 1 ? "WHITE" : "GRN");
    case 2:
      s_auto = (s_auto + 1) % 4;
      save();
      switch (s_auto) {
        case 1:
          return "5S";
        case 2:
          return "10S";
        case 3:
          return "30S";
        default:
          return "OFF";
      }
    default:
      return "";
  }
}

}
