#!/usr/bin/env bash
# flash_teensy.sh — build and flash the Teensy firmware IN PLACE, on the Pi.
# No button press, no unplugging: soft-reboots the Teensy into its bootloader
# and programs it over the USB cable that already powers it.
#
# Usage (on the Pi):  ./flash_teensy.sh
# Expects the sketch at ~/wapow_teensy (scp'd from the repo).
set -e
echo "== compiling =="
~/bin/arduino-cli compile --fqbn teensy:avr:teensy41 ~/wapow_teensy \
    --output-dir ~/teensy_build
echo "== flashing (soft reboot) =="
teensy_loader_cli --mcu=TEENSY41 -s -v ~/teensy_build/wapow_teensy.ino.hex
echo "== done — firmware live =="
