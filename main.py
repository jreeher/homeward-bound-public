"""
main.py — garage door monitor.

Reads the A112x Hall sensor (same pin/logic as the original working version)
and reports state to the Railway backend. Railway now owns the alert
decision — including the "only alert if open after 9pm" logic — so this
device no longer talks to Telegram directly and no longer needs to track
local time.
"""

import machine
import network
import urequests
import ujson
import time
import gc
import config
from machine import Pin

HALL_SENSOR_PIN = 32        # unchanged from the original working setup
POLL_INTERVAL_S = 60        # matches original CHECK_INTERVAL
HEARTBEAT_INTERVAL_S = 300  # send a status ping even with no change, every 5 min
ERROR_LOG_FILE = "error_log.txt"

# Same pin config and polarity as the original: value() == 0 means open.
hall_sensor = Pin(HALL_SENSOR_PIN, Pin.IN, Pin.PULL_DOWN)
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


def read_hall_sensor():
    """Returns True if door is open. Same polarity as the original:
    value() == 0 -> open."""
    return hall_sensor.value() == 0


def report_status(state):
    if not ensure_wifi():
        return False

    payload = {
        "device": config.DEVICE_NAME,
        "state": state,
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
    print("Garage Door Sensor Starting...")

    if not ensure_wifi():
        log_error("Cannot proceed without WiFi connection")
        return

    last_state = None
    last_heartbeat = 0

    print("Monitoring started...")

    while True:
        try:
            is_open = read_hall_sensor()
            state = "open" if is_open else "closed"
            print("Door state:", state)
            now = time.time()

            state_changed = state != last_state
            heartbeat_due = (now - last_heartbeat) >= HEARTBEAT_INTERVAL_S

            if state_changed or heartbeat_due:
                success = report_status(state)
                if success:
                    last_state = state
                    last_heartbeat = now
                # if it failed, last_state stays unchanged so a real state
                # change keeps retrying to report next loop

            gc.collect()
            time.sleep(POLL_INTERVAL_S)

        except Exception as e:
            log_error("main loop error: " + str(e))
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
