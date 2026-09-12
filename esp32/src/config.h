// Hardware configuration — adjust to your wiring.
//
// GC9A01 240x240 SPI panel
#define PIN_MOSI 23
#define PIN_SCK  18
#define PIN_CS   5
#define PIN_DC   17
#define PIN_RST  16
#define PIN_BL   4      // backlight, PWM
// Buttons: active-low, pulled to 3V3 via 10k
#define PIN_BTN1 34
#define PIN_BTN2 35
#define PIN_BTN3 39
// Wi-Fi — fill in before flashing
#define WIFI_SSID "your-ssid"
#define WIFI_PASS "your-password"
#define MDNS_HOST "resmon"
#define UDP_PORT 8266
#define SERIAL_BAUD 115200
#define TWO_BUTTONS 0   // set 1 if only B1+B2 are wired (B2 long-press = settings)
