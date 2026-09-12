#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include "config.h"
#include "settings.h"

static WebServer server;

// Self-contained settings page: inline CSS + JS, no external assets.
static const char* PAGE = R"HTML(<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>resmon-lite ESP32</title>
<style>
body { background:#000; color:#ccc; font-family:system-ui,sans-serif; margin:0; padding:24px; }
h1 { color:#81C784; font-size:20px; margin:0 0 4px; }
#status { margin:8px 0 20px; color:#81C784; }
section { margin:16px 0; }
h2 { font-size:14px; color:#81C784; margin:0 0 10px; }
label { display:block; font-size:12px; margin:10px 0 4px; color:#888; }
input, select { width:100%; box-sizing:border-box; background:#111; color:#ccc; border:1px solid #333; border-radius:6px; padding:8px; }
input[type=range] { padding:0; }
.row { display:flex; gap:12px; }
.row > div { flex:1; }
#brightval { color:#ccc; }
button { margin-top:20px; width:100%; background:#81C784; color:#000; border:0; border-radius:6px; padding:12px; font-size:16px; font-weight:600; }
</style>
</head>
<body>
<h1>resmon-lite ESP32</h1>
<div id="status">…</div>
<section>
<h2>Wi-Fi</h2>
<label>Network SSID</label>
<input id="ssid" name="ssid" placeholder="network SSID" autocomplete="off">
<label>Network password</label>
<input id="pass" name="pass" type="password" placeholder="network password">
</section>
<section>
<h2>Display</h2>
<label>Brightness <span id="brightval">70%</span></label>
<input id="bright" name="bright" type="range" min="0" max="100" value="70">
<div class="row">
<div>
<label>Colour mode</label>
<select id="color" name="color">
<option value="0">RGB</option>
<option value="1">White</option>
<option value="2">Green</option>
</select>
</div>
<div>
<label>Auto-advance</label>
<select id="auto" name="auto">
<option value="0">Off</option>
<option value="1">5 s</option>
<option value="2">10 s</option>
<option value="3">30 s</option>
</select>
</div>
</div>
</section>
<button id="save">Save</button>
<script>
async function refreshStatus() {
  var el = document.getElementById('status');
  try {
    var r = await fetch('/status');
    var s = await r.json();
    el.textContent = s.connected ? ('Connected to ' + s.ssid + ' (' + s.ip + ')') : 'Not connected';
  } catch (e) {
    el.textContent = 'Not connected';
  }
}
refreshStatus();
setInterval(refreshStatus, 2000);
async function loadConfig() {
  try {
    var r = await fetch('/config');
    var c = await r.json();
    document.getElementById('bright').value = c.bright;
    document.getElementById('brightval').textContent = c.bright + '%';
    document.getElementById('color').value = c.color;
    document.getElementById('auto').value = c.auto;
  } catch (e) {}
}
loadConfig();
document.getElementById('bright').addEventListener('input', function () {
  document.getElementById('brightval').textContent = this.value + '%';
});
document.getElementById('save').addEventListener('click', async function () {
  var body = new URLSearchParams({
    ssid: document.getElementById('ssid').value,
    pass: document.getElementById('pass').value,
    bright: document.getElementById('bright').value,
    color: document.getElementById('color').value,
    auto: document.getElementById('auto').value
  });
  var r = await fetch('/save', { method: 'POST', body: body });
  var msg = await r.text();
  document.getElementById('status').textContent = r.ok ? 'Saved — rebooting…' : msg;
});
</script>
</body>
</html>)HTML";

namespace web {

void init() {
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(AP_SSID);
  server.on("/", HTTP_GET, []() {
    server.send(200, "text/html", PAGE);
  });
  server.on("/config", HTTP_GET, []() {
    String s = "{\"bright\":";
    s += settings::bright();
    s += ",\"color\":";
    s += settings::color_mode();
    s += ",\"auto\":";
    s += settings::auto_adv();
    s += "}";
    server.send(200, "application/json", s);
  });
  server.on("/status", HTTP_GET, []() {
    if (WiFi.status() == WL_CONNECTED) {
      String s = "{\"connected\":true,\"ssid\":\"";
      s += WiFi.SSID();
      s += "\",\"ip\":\"";
      s += WiFi.localIP().toString();
      s += "\"}";
      server.send(200, "application/json", s);
    } else {
      server.send(200, "application/json", "{\"connected\":false}");
    }
  });
  server.on("/save", HTTP_POST, []() {
    String ssid = server.arg("ssid");
    ssid.trim();
    if (ssid.length() == 0) {
      server.send(400, "text/plain", "ssid is required");
      return;
    }
    settings::set_wifi(ssid.c_str(), server.arg("pass").c_str());
    settings::set_bright(server.arg("bright").toInt());
    settings::set_color(server.arg("color").toInt());
    settings::set_auto(server.arg("auto").toInt());
    settings::save();
    server.send(200, "text/plain", "saved — rebooting");
    delay(100);  // let the response flush before the reboot
    ESP.restart();
  });
  server.begin();
}

void poll() {
  server.handleClient();
}

}
