# config.example.py — copy to config.py on the ESP32 and fill in the values
# from the garage door's config.py. Do NOT commit the real config.py: this
# repo is public.

WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"

RAILWAY_STATUS_URL = "https://homeward-bound-production-2510.up.railway.app/api/status"
DEVICE_SECRET = "same-secret-as-garage"

DEVICE_NAME = "adu_temp"

# Only needed if you set up over-the-air updates (boot.py + ota_updater.py)
OTA_MANIFEST_URL = "https://raw.githubusercontent.com/jreeher/homeward-bound-public/refs/heads/main/ota/adu_temp/manifest.json"
