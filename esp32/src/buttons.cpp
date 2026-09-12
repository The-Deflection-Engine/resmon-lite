#include <Arduino.h>
#include "config.h"
#include "buttons.h"

// Per-button state machine: the pin must be stable for DEBOUNCE_MS to
// count as pressed; a release within LONG_MS is a short event, a hold
// past LONG_MS is a long event.
static const uint32_t DEBOUNCE_MS = 20;
static const uint32_t LONG_MS = 1500;

struct Btn {
  int pin = -1;
  bool raw = false;
  bool pressed = false;
  bool long_fired = false;
  bool pending_short = false;
  uint32_t stable_ms = 0;
  uint32_t press_ms = 0;
};

static Btn b1;
static Btn b2;
#if !TWO_BUTTONS
static Btn b3;
#endif
static Btn* btns[3] = {&b1, &b2,
#if TWO_BUTTONS
                      nullptr
#else
                      &b3
#endif
                     };

static void step(Btn& b) {
  uint32_t now = millis();
  bool level = (digitalRead(b.pin) == LOW);  // active-low
  if (level != b.raw) {
    if (b.pressed && !b.long_fired)
      b.pending_short = true;  // released before LONG_MS
    b.raw = level;
    b.stable_ms = now;
    b.pressed = false;
    b.long_fired = false;
  } else if (level && !b.pressed && now - b.stable_ms >= DEBOUNCE_MS) {
    b.pressed = true;
    b.press_ms = now;
  }
}

static BtnEvent map_short(int pin, bool settings_mode) {
  if (!settings_mode) {
    if (pin == PIN_BTN1) return BtnEvent::Next;
    if (pin == PIN_BTN2) return BtnEvent::Prev;
#if !TWO_BUTTONS
    if (pin == PIN_BTN3) return BtnEvent::Settings;
#endif
  } else if (TWO_BUTTONS) {
    if (pin == PIN_BTN1) return BtnEvent::Cycle;  // change the selected value
    if (pin == PIN_BTN2) return BtnEvent::Prev;  // move the selection
  } else {
    if (pin == PIN_BTN1) return BtnEvent::Next;
    if (pin == PIN_BTN2) return BtnEvent::Prev;
    if (pin == PIN_BTN3) return BtnEvent::Cycle;
  }
  return BtnEvent::None;
}

static BtnEvent map_long(int pin, bool settings_mode) {
  if (pin == PIN_BTN3) return BtnEvent::Exit;
  if (TWO_BUTTONS && pin == PIN_BTN2)
    return settings_mode ? BtnEvent::Exit : BtnEvent::Settings;
  return BtnEvent::None;
}

namespace buttons {

void init() {
  b1.pin = PIN_BTN1;
  b2.pin = PIN_BTN2;
#if !TWO_BUTTONS
  b3.pin = PIN_BTN3;
#endif
  pinMode(PIN_BTN1, INPUT_PULLUP);
  pinMode(PIN_BTN2, INPUT_PULLUP);
#if !TWO_BUTTONS
  pinMode(PIN_BTN3, INPUT_PULLUP);
#endif
}

BtnEvent poll(bool settings_mode) {

  BtnEvent ev = BtnEvent::None;
  for (int i = 0; i < 3; i++) {
    Btn* b = btns[i];
    if (b == nullptr) continue;
    step(*b);
    if (ev == BtnEvent::None) {
      if (b->pressed && !b->long_fired && millis() - b->press_ms >= LONG_MS) {
        b->long_fired = true;
        ev = map_long(b->pin, settings_mode);
      } else if (b->pending_short) {
        b->pending_short = false;
        ev = map_short(b->pin, settings_mode);
      }
    }
  }
  return ev;
}

}
