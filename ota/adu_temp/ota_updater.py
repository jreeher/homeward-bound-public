"""
ota_updater.py — simple OTA update checker for ESP32 MicroPython projects.

How it works:
1. boot.py calls check_and_apply() with the manifest URL after wifi connects.
2. Fetches manifest.json from GitHub: {"version": N, "url": "<raw main.py url>"}
3. If N is greater than the locally stored version, downloads the new main.py
   to a temp file, swaps it in, updates the stored version, and reboots.
4. Any failure (wifi hiccup, bad download) just leaves the existing code alone.

Host manifest.json + main.py in a public GitHub repo, e.g.:
  https://raw.githubusercontent.com/<user>/<repo>/main/manifest.json
  https://raw.githubusercontent.com/<user>/<repo>/main/main.py

Bump "version" in manifest.json each time you push new code.
"""

import urequests
import machine
import os
import time

VERSION_FILE = "version.txt"
TARGET_FILE = "main.py"
TARGET_FILE_TMP = "main.py.tmp"


def get_local_version():
    try:
        with open(VERSION_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def set_local_version(v):
    with open(VERSION_FILE, "w") as f:
        f.write(str(v))


def check_for_update(manifest_url):
    try:
        resp = urequests.get(manifest_url, timeout=10)
        manifest = resp.json()
        resp.close()
    except Exception as e:
        print("OTA: manifest fetch failed:", e)
        return False, None

    remote_version = manifest.get("version", 0)
    local_version = get_local_version()
    print("OTA: local version {}, remote version {}".format(local_version, remote_version))

    return remote_version > local_version, manifest


def apply_update(manifest):
    url = manifest["url"]
    try:
        resp = urequests.get(url, timeout=15)
        new_code = resp.text
        resp.close()

        if not new_code or ("def " not in new_code and "import" not in new_code):
            print("OTA: downloaded content looks invalid, aborting update")
            return False

        with open(TARGET_FILE_TMP, "w") as f:
            f.write(new_code)

        try:
            os.remove(TARGET_FILE)
        except OSError:
            pass
        os.rename(TARGET_FILE_TMP, TARGET_FILE)

        set_local_version(manifest["version"])
        print("OTA: update applied, new version =", manifest["version"])
        return True

    except Exception as e:
        print("OTA: update failed:", e)
        return False


def check_and_apply(manifest_url, reboot_on_success=True):
    should_update, manifest = check_for_update(manifest_url)
    if not should_update:
        print("OTA: up to date")
        return False

    print("OTA: new version available, downloading...")
    success = apply_update(manifest)

    if success and reboot_on_success:
        print("OTA: rebooting in 2s to run new code")
        time.sleep(2)
        machine.reset()

    return success
