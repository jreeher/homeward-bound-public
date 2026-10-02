"""
main.py — ADU temperature monitor.

Reads a DS18B20 probe and reports the temperature to the Railway backend
every minute. Railway owns the alert decision (above 60°F after 9pm,
September–May), same as the garage door — this device just reports.
"""

import machine
import network
import onewire
import ds18x20
import urequests
import ujson
import time
import gc
import config

DS18B20_PIN = 4             # data line, with 4.7kΩ pull-up to 3.3V
POLL_INTERVAL_S = 60        # report every minute so alerts land quickly
CONVERT_WAIT_MS = 750       # DS18B20 12-bit conversion time
ERROR_LOG_FILE = "error_log.txt"

ds = ds18x20.DS18X20(onewire.OneWire(machine.Pin(DS18B20_PIN)))
wlan = network.WLAN(network.STA_IF)
rom = None


def log_error(msg):
    print("ERROR:", msg)
    try:
        with open(ERROR_LOG_FILE, "a") as f:
            f.write("{}: {}\n".format(time.time(), msg))
    except Exception as e:
        print("Could not write to error log:", e)


def ensure_wifi():
    if wlan.isconnected():
        return True
    try:
        wlan.active(True)
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > 15:
                log_error("wifi reconnect timed out")
                return False
            time.sleep(0.5)
        print("WiFi connected:", wlan.ifconfig())
        return True
    except Exception as e:
        log_error("wifi reconnect failed: " + str(e))
        return False


def find_sensor():
    global rom
    roms = ds.scan()
    if not roms:
        rom = None
        log_error("no DS18B20 found on pin {}".format(DS18B20_PIN))
        return False
    rom = roms[0]
    print("Found DS18B20:", rom)
    return True


def read_temp_f():
    """Returns temperature in °F rounded to 0.1, or None on a bad read."""
    if rom is None and not find_sensor():
        return None
    try:
        ds.convert_temp()
        time.sleep_ms(CONVERT_WAIT_MS)
        c = ds.read_temp(rom)
    except Exception as e:
        # CRC error or probe unplugged — rescan on the next loop
        log_error("temp read failed: " + str(e))
        find_sensor()
        return None
    # 85°C is the DS18B20 power-on value, i.e. no real conversion happened
    if c is None or c == 85.0 or c < -55 or c > 125:
        log_error("bad temp reading: {}".format(c))
        return None
    return round(c * 9 / 5 + 32, 1)


def report_status(temp_f):
    if not ensure_wifi():
        return False

    payload = {
        "device": config.DEVICE_NAME,
        "state": "ok",
        "temperature_f": temp_f,
        "timestamp": time.time(),
        "wifi_rssi": wlan.status("rssi") if hasattr(wlan, "status") else None,
        "free_mem": gc.mem_free(),
    }

    try:
        resp = urequests.post(
            config.RAILWAY_STATUS_URL,
            headers={
                "Content-Type": "application/json",
                "X-Device-Secret": config.DEVICE_SECRET,
            },
            data=ujson.dumps(payload),
            timeout=10,
        )
        ok = resp.status_code == 200
        if not ok:
            log_error("status report got HTTP {}: {}".format(resp.status_code, resp.text))
        resp.close()
        return ok
    except Exception as e:
        log_error("status report failed: " + str(e))
        return False


def main():
    print("ADU Temperature Sensor Starting...")

    find_sensor()

    if not ensure_wifi():
        log_error("Cannot proceed without WiFi connection")
        return

    print("Monitoring started...")

    while True:
        try:
            temp_f = read_temp_f()
            if temp_f is not None:
                print("Temperature: {}°F".format(temp_f))
                report_status(temp_f)
            # On a bad read we skip the report; if it keeps failing, the
            # backend's silence alert will flag the device after 15 min.

            gc.collect()
            time.sleep(POLL_INTERVAL_S)

        except Exception as e:
            log_error("main loop error: " + str(e))
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
