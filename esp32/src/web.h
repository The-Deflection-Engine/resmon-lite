#pragma once

namespace web {

// Bring up the "Resmon" soft-AP (always on, open) and the web server:
// the settings page at http://192.168.4.1 stores the home Wi-Fi
// credentials + display settings in NVS and reboots the board.
void init();
// Handle one web client — non-blocking; call once per loop().
void poll();

}
