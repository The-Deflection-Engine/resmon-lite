#pragma once

// One event per button action.
enum class BtnEvent { None, Next, Prev, Settings, Cycle, Exit };

namespace buttons {

// Configure the button pins (active-low, INPUT_PULLUP).
void init();

// Non-blocking; call once per loop. Returns the event for this poll, or
// None. settings_mode selects the mapping:
//   main mode:     B1 short = Next, B2 short = Prev, B3 short = Settings,
//                  B3 long = Exit (ignored), B2 long = Settings (TWO_BUTTONS)
//   settings mode: B1 short = Next, B2 short = Prev, B3 short = Cycle,
//                  B3 long = Exit;
//                  TWO_BUTTONS: B1 short = Cycle, B2 short = Prev (move),
//                  B2 long = Exit
BtnEvent poll(bool settings_mode);

}
