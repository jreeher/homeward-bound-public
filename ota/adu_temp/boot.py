"""
boot.py — runs before main.py on every power-up/reset.

Connects to WiFi and checks GitHub for a newer main.py (see ota_updater.py).
Any failure here is caught so main.py always gets to run.
"""

import network
import time
import config

try:
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        start = time.time()
        while not wlan.isconnected() and time.time() - start < 15:
            time.sleep(0.5)

    if wlan.isconnected() and getattr(config, "OTA_MANIFEST_URL", None):
        import ota_updater
        ota_updater.check_and_apply(config.OTA_MANIFEST_URL)
    else:
        print("boot: skipping OTA check (no WiFi or no OTA_MANIFEST_URL)")
except Exception as e:
    print("boot: OTA check failed:", e)
