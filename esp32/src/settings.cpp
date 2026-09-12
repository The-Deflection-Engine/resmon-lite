#include <Preferences.h>
#include "settings.h"
#include "display.h"

static Preferences prefs;
static int s_bright = 70;
static int s_color = 0;
static int s_auto = 2;
static char s_buf[16];

namespace settings {

void load() {
  prefs.begin("resmon", true);  // read-only
  s_bright = prefs.getUChar("bright", 70);
  s_color = prefs.getUChar("color", 0);
  s_auto = prefs.getUChar("auto", 2);
  prefs.end();
}

void save() {
  prefs.begin("resmon", false);
  prefs.putUChar("bright", s_bright);
  prefs.putUChar("color", s_color);
  prefs.putUChar("auto", s_auto);
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
