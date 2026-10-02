"""
main.py — ADU temperature monitor.

Reads a DS18B20 on GPIO 33 (4.7k pull-up to 3.3V) and reports the temperature
to the same Railway backend as the garage door monitor. Railway owns the
alert decision and sends the Telegram message — this device never talks to
Telegram directly.
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

SENSOR_PIN = 33             # DS18B20 data line
POLL_INTERVAL_S = 60        # read the sensor once a minute
HEARTBEAT_INTERVAL_S = 300  # report at least every 5 min (keeps silence alert quiet)
CHANGE_THRESHOLD_F = 1.0    # report early if temp moves this much since last report
ERROR_LOG_FILE = "error_log.txt"

ow = onewire.OneWire(machine.Pin(SENSOR_PIN))
ds = ds18x20.DS18X20(ow)
wlan = network.WLAN(network.STA_IF)


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
    roms = ds.scan()
    if not roms:
        log_error("no DS18B20 found on GPIO {} — check wiring and pull-up".format(SENSOR_PIN))
        return None
    print("Found DS18B20:", roms[0])
    return roms[0]


def read_temp_f(rom):
    """Returns temperature in °F, or None if the read looks bad."""
    try:
        ds.convert_temp()
        time.sleep_ms(750)  # 12-bit conversion takes up to 750 ms
        c = ds.read_temp(rom)
    except Exception as e:
        # CRC error / probe unplugged — report as sensor_error, don't go silent
        log_error("temp read failed: " + str(e))
        return None
    # 85.0 C is the power-on reset value; it usually means a bad/early read.
    if c is None or c == 85.0 or c < -55 or c > 125:
        log_error("suspicious reading: {}".format(c))
        return None
    return round(c * 9 / 5 + 32, 1)


def report_status(temp_f):
    if not ensure_wifi():
        return False

    payload = {
        "device": config.DEVICE_NAME,
        "state": "ok" if temp_f is not None else "sensor_error",
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

    if not ensure_wifi():
        log_error("Cannot proceed without WiFi connection")
        return

    rom = find_sensor()
    last_reported = None
    last_heartbeat = 0

    while True:
        try:
            if rom is None:
                rom = find_sensor()

            temp_f = read_temp_f(rom) if rom is not None else None
            print("Temp:", temp_f, "F")
            now = time.time()

            moved = (
                temp_f is not None and last_reported is not None
                and abs(temp_f - last_reported) >= CHANGE_THRESHOLD_F
            )
            heartbeat_due = (now - last_heartbeat) >= HEARTBEAT_INTERVAL_S

            if moved or heartbeat_due or last_reported is None:
                if report_status(temp_f):
                    last_reported = temp_f
                    last_heartbeat = now

            gc.collect()
            time.sleep(POLL_INTERVAL_S)

        except Exception as e:
            log_error("main loop error: " + str(e))
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
