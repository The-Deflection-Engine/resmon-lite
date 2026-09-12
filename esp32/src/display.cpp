#include <LovyanGFX.hpp>
#include "config.h"
#include "display.h"

// GC9A01 240x240 round panel on the SPI bus (LovyanGFX device pattern:
// the device class doubles as the graphics object).
class GfxDevice : public lgfx::LGFX_Device {
  lgfx::Panel_GC9A01 _panel_instance;
  lgfx::Bus_SPI _bus_instance;

public:
  GfxDevice() {
    {
      auto cfg = _bus_instance.config();
      cfg.spi_host = VSPI_HOST;
      cfg.spi_mode = 0;
      cfg.freq_write = 20000000;
      cfg.freq_read = 16000000;
      cfg.use_lock = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk = PIN_SCK;
      cfg.pin_mosi = PIN_MOSI;
      cfg.pin_miso = -1;
      cfg.pin_dc = PIN_DC;
      _bus_instance.config(cfg);
      _panel_instance.setBus(&_bus_instance);
    }
    {
      auto cfg = _panel_instance.config();
      cfg.pin_cs = PIN_CS;
      cfg.pin_rst = PIN_RST;
      cfg.panel_width = 240;
      cfg.panel_height = 240;
      cfg.memory_width = 240;
      cfg.memory_height = 240;
      _panel_instance.config(cfg);
    }
    setPanel(&_panel_instance);
  }
};

static GfxDevice gfx;

namespace display {

void init() {
  gfx.init();
  // Backlight: 5 kHz PWM, off until the settings are applied.
  ledcSetup(0, 5000, 8);
  ledcAttachPin(PIN_BL, 0);
  ledcWrite(0, 0);
}

void set_backlight(int pct) {
  if (pct < 0) pct = 0;
  if (pct > 100) pct = 100;
  ledcWrite(0, 255L * pct / 100);
}

void fill_screen(unsigned int color) {
  gfx.fillScreen(color);
}

void draw_arc(int cx, int cy, int radius, int width,
              float start_deg, float end_deg, unsigned int color, bool fill) {
  int r0 = radius - width / 2;
  int r1 = radius + (width - 1) / 2;
  if (fill)
    gfx.fillArc(cx, cy, r0, r1, start_deg, end_deg, color);
  else
    gfx.drawArc(cx, cy, r0, r1, start_deg, end_deg, color);
}

void draw_string(const char* s, int x, int y, int font, unsigned int color, int align) {
  // y is the top of the text (matching the mockups).
  gfx.setTextFont(font);
  gfx.setTextColor(color);
  gfx.setTextDatum(align == 1 ? lgfx::textdatum_t::top_center
                             : (align == 2 ? lgfx::textdatum_t::top_right
                                          : lgfx::textdatum_t::top_left));
  gfx.drawString(s, x, y, font);
}

void set_text_font(int font) {
  gfx.setTextFont(font);
}

int text_width(const char* s, int font) {
  gfx.setTextFont(font);
  return gfx.textWidth(s);
}

void fill_rounded_rect(int x, int y, int w, int h, int r, unsigned int color) {
  gfx.fillRoundRect(x, y, w, h, r, color);
}

}
