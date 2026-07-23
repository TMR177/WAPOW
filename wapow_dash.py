#!/usr/bin/env python3
"""
WAPOW — adaptive racing dash, v0.1
The real product software. Data sources are swappable:
  - Sim engine (built in): the scripted drive from the concept demo
  - LSM6DSOX IMU (auto-detected): REAL G-forces drive the G-circle + modes
  - CAN / OBD sources plug in here later, nothing else changes.

Run on the Pi:   DISPLAY=:0 python3 wapow_dash.py
Run on desktop:  WAPOW_WINDOWED=1 python3 wapow_dash.py   (dev mode, real
                 window instead of grabbing the whole screen)
Keys / touch:    1-4 jump to Parked/Cruise/Canyon/Track, 5 = failure demo
                 tap KNOCK chip = knock log, ESC = quit
                 To quit by touch: tap the top-right corner, then tap the EXIT
                 button that appears (two taps — the panel can't do reliable
                 press-and-hold, and one tap alone would be too easy to hit)
                 tap SETUP chip (PARKED only) = sensor/alarm settings,
                 saved to settings.json next to this file
Data logging:    auto-records at SPIRITED+ (matches the LOG indicator) to a
                 timestamped CSV per run under logs/
"""

import csv
import glob
import json
import math
import os
import random
import signal
import socket
import subprocess
import sys
import threading
import time

SNAPSHOT = os.environ.get("WAPOW_SNAPSHOT")          # headless frame-render mode
if SNAPSHOT:
    os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

W, H = 1024, 600
DUR = 70.0

# ----- palette (same as the concept demo) ----------------------------------
BG      = (11, 14, 19)
PANEL   = (19, 25, 38)
TEAL    = (55, 224, 192)
DIM     = (107, 118, 136)
TEXT    = (238, 242, 248)
AMBER   = (255, 182, 72)
RED     = (255, 84, 98)
RED_HI  = (255, 141, 153)
BLUE    = (74, 168, 255)
PINK    = (255, 79, 163)
PURPLE  = (201, 165, 255)
GREEN   = (61, 220, 104)
YELLOW  = (255, 221, 51)
MODE_COLOR = {"PARKED": (139, 147, 167), "CRUISING": BLUE,
              "SPIRITED": AMBER, "RACING": RED}

def lerp(a, b, k): return a + (b - a) * k
def clamp(v, a, b): return max(a, min(b, v))
def ease(p): return p * p * (3 - 2 * p)
def fade(col, a):
    """simulate globalAlpha by blending toward the background"""
    return tuple(int(BG[i] + (col[i] - BG[i]) * a) for i in range(3))

# ============================ sensor profiles + settings ====================

# Every aftermarket wideband / pressure sender on the market is a linear
# ratiometric device: volts in, straight-line-scaled units out. One profile
# table covers all of them.
# CUSTOM is a stub for now — it just holds placeholder numbers, there's no
# UI yet to edit them. Build a per-sensor editor (4 stepper fields: min/max
# volts, min/max value) if/when a real sensor shows up that doesn't fit a
# preset.
SENSOR_PROFILES = dict(
    afr=dict(
        AEM_XSERIES=dict(label="AEM X-Series",        v_lo=0.0, v_hi=5.0, val_lo=10.0, val_hi=20.0),
        INNOVATE_LC2=dict(label="Innovate LC2/MTXL/ECF1", v_lo=0.0, v_hi=5.0, val_lo=7.35, val_hi=22.39),
        ZEITRONIX=dict(label="Zeitronix Zt-2/Zt-3",   v_lo=0.0, v_hi=5.0, val_lo=9.6,  val_hi=19.6),
        AFR500_STD=dict(label="Ballenger AFR500 std", v_lo=0.0, v_hi=5.0, val_lo=9.0,  val_hi=16.0),
        AFR500_WIDE=dict(label="Ballenger AFR500 wide", v_lo=0.0, v_hi=5.0, val_lo=6.0, val_hi=20.0),
        CUSTOM=dict(label="Custom",                    v_lo=0.0, v_hi=5.0, val_lo=10.0, val_hi=20.0),
    ),
    press=dict(
        PSI_100=dict(label="0-100 PSI", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=100.0),
        PSI_150=dict(label="0-150 PSI", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=150.0),
        PSI_145=dict(label="0-145 PSI (ECF-1)", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=145.0),
        PSI_200=dict(label="0-200 PSI", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=200.0),
        CUSTOM=dict(label="Custom",     v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=100.0),
    ),
    # MAP sensors: output absolute pressure (PSIA); dash derives boost as
    # abs - 14.7. Values are full-scale PSIA at v_hi.
    map=dict(
        BAR_2=dict(label="2-bar MAP", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=29.4),
        BAR_3=dict(label="3-bar MAP", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=44.1),
        BAR_4=dict(label="4-bar MAP", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=58.8),
        GM_3BAR=dict(label="GM 3-bar", v_lo=0.0, v_hi=5.0, val_lo=0.16, val_hi=45.76),
        AEM_50PSIA=dict(label="AEM 50 PSIa", v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=50.0),
        CUSTOM=dict(label="Custom",   v_lo=0.5, v_hi=4.5, val_lo=0.0, val_hi=44.1),
    ),
)

def scale_sensor(group, key, volts):
    """Raw sender volts -> engineering units for the selected profile.
    The Teensy will send raw volts over CAN; scaling lives on the Pi so
    swapping a sensor is a settings change, not a firmware reflash."""
    p = SENSOR_PROFILES[group][key]
    frac = clamp((volts - p["v_lo"]) / (p["v_hi"] - p["v_lo"]), 0, 1)
    return p["val_lo"] + frac * (p["val_hi"] - p["val_lo"])


# Engine-type presets (config menu, 7/19): a preset is a STARTING POINT, not
# a cage — it stamps sweep ranges and alarm defaults, and any manual edit of
# a stamped value forks the preset name to CUSTOM without losing the change.
PRESET_KEYS = ("rpm_redline", "rpm_max", "boost_lo", "boost_hi",
               "afr_target", "oil_temp_alarm", "water_temp_alarm")
PRESETS = dict(
    NA=dict(rpm_redline=7600, rpm_max=9000, boost_lo=-20, boost_hi=0,
            afr_target=13.2, oil_temp_alarm=260, water_temp_alarm=230),
    TURBO=dict(rpm_redline=7000, rpm_max=9000, boost_lo=-15, boost_hi=25,
               afr_target=12.0, oil_temp_alarm=260, water_temp_alarm=230),
    SUPERCHARGED=dict(rpm_redline=6800, rpm_max=8500, boost_lo=0, boost_hi=18,
                      afr_target=12.5, oil_temp_alarm=260, water_temp_alarm=230),
)

class Settings:
    """User-selected sensors + alarm thresholds, persisted to settings.json
    next to the script so the driver never has to reselect them."""
    FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
    DEFAULTS = dict(
        preset="TURBO",
        wideband_sensor="AEM_XSERIES",
        oil_press_sensor="PSI_100",
        fuel_press_sensor="PSI_100",
        map_sensor="BAR_3",            # decided 7/15: 4-bar for the on-board;
                                       # 3-bar default matches the bench sim
        fuel_press_base=43.0,          # PSI at zero boost
        oil_press_dev_alarm=12.0,      # PSI below expected before OILP alerts
        fuel_press_dev_alarm=8.0,      # PSI below expected before FUELP alerts
        rpm_redline=7000.0,            # sweep + alarm values: preset-stamped,
        rpm_max=9000.0,                # individually tunable after
        boost_lo=-15.0,
        boost_hi=25.0,
        afr_target=12.0,               # the AFR tile's elbow
        oil_temp_alarm=260.0,
        water_temp_alarm=230.0,
    )

    def __init__(self):
        self.values = dict(self.DEFAULTS)
        try:
            with open(self.FILE) as f:
                saved = json.load(f)
            for k in self.DEFAULTS:
                if k in saved:
                    self.values[k] = saved[k]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def save(self):
        with open(self.FILE, "w") as f:
            json.dump(self.values, f, indent=2)

    def __getattr__(self, name):
        if name in self.DEFAULTS:
            return self.values[name]
        raise AttributeError(name)

    def set(self, key, value):
        self.values[key] = value
        # Editing a preset-stamped value forks you to CUSTOM (keeps the edit).
        if key in PRESET_KEYS and self.values.get("preset") != "CUSTOM":
            self.values["preset"] = "CUSTOM"
        self.save()

    def apply_preset(self, name):
        self.values.update(PRESETS[name])
        self.values["preset"] = name
        self.save()

    def reset(self):
        self.values = dict(self.DEFAULTS)
        self.save()


SETTINGS = Settings()


# ============================ data sources ==================================

class SimEngine:
    """The scripted drive — identical math to the concept demo."""
    def raw(self, t):
        rpm = spd = gx = gy = 0.0
        if t < 3:
            pass
        elif t < 6:
            rpm = 900 + 700 * math.exp(-(t - 3) * 2.5)
        elif t < 14:
            p = ease((t - 6) / 8)
            spd = 45 * p
            rpm = 900 + 2300 * p + 300 * math.sin(t * 3) * p
            gy = 0.18 * p
        elif t < 26:
            spd = 63 + 3 * math.sin(t * 0.4)
            rpm = 2300 + 150 * math.sin(t * 0.7)
            gx = 0.08 * math.sin(t * 0.5)
        elif t < 44:
            s = t - 26
            spd = 68 + 16 * math.sin(s * 0.5)
            gx = 0.85 * math.sin(s * 0.95) * (0.65 + 0.35 * math.sin(s * 0.23))
            gy = 0.45 * math.sin(s * 0.5 + 1.2)
            rpm = 4300 + 1800 * math.sin(s * 1.25) + 350 * math.sin(s * 5)
        elif t < 62:
            s = t - 44
            spd = 86 + 30 * math.sin(s * 0.55)
            gx = 1.12 * math.sin(s * 1.05)
            gy = 0.95 * math.sin(s * 0.8 + 2.1)
            rpm = 5300 + 2050 * math.sin(s * 1.55) + 250 * math.sin(s * 7)
        else:
            p = ease(clamp((t - 62) / 6, 0, 1))
            spd = lerp(90, 62, p)
            rpm = lerp(5000, 2350, p)
            gx = 0.5 * (1 - p) * math.sin(t * 0.9)
        return clamp(rpm, 0, 7600), spd, gx, gy


class ImuSource:
    """LSM6DSOX — real G-forces, if the sensor is wired up."""
    def __init__(self):
        self.ok = False
        if SNAPSHOT:
            return
        try:
            import board
            from adafruit_lsm6ds.lsm6dsox import LSM6DSOX
            self.sensor = LSM6DSOX(board.I2C())
            self.ok = True
            print("IMU detected: real G-forces active")
        except Exception:
            print("No IMU found: simulated G-forces")

    def read(self):
        ax, ay, az = self.sensor.acceleration
        return ax / 9.81, ay / 9.81


class CanSource:
    """Live data from the Teensy over can0. Frame map: see wapow_spec.md.

    Same deal as ImuSource — auto-detected, and if it isn't there the sim
    just keeps running. A background thread drains frames into `latest` so a
    slow or silent bus can never stall the 50 fps draw loop.

    Bring the bus up first (doesn't survive reboot yet):
        sudo ip link set can0 up type can bitrate 500000
    """
    STALE_S = 0.5          # no FAST frame for this long => treat CAN as dead

    def __init__(self):
        self.ok = False
        self.latest = {}
        self.last_rx = -99.0
        self._lock = threading.Lock()
        if SNAPSHOT:
            return
        try:
            import can
            self.bus = can.interface.Bus(channel="can0", interface="socketcan")
            self.ok = True
            t = threading.Thread(target=self._reader, daemon=True)
            t.start()
            print("CAN detected: live Teensy data on can0")
        except Exception as e:
            print(f"No CAN ({e.__class__.__name__}): simulated data")

    def _u16(self, b, at):
        return b[at] | (b[at + 1] << 8)          # little-endian, matches Teensy

    def _reader(self):
        while True:
            try:
                msg = self.bus.recv(timeout=1.0)
            except Exception:
                continue
            if msg is None:
                continue
            b, d = msg.data, {}
            if msg.arbitration_id == 0x100 and len(b) >= 6:
                d["rpm"] = self._u16(b, 0)
                d["map_mv"] = self._u16(b, 2)
                d["seq"] = self._u16(b, 4)
            elif msg.arbitration_id == 0x120 and len(b) >= 8:
                d["oilp_mv"] = self._u16(b, 0)
                d["fuelp_mv"] = self._u16(b, 2)
                d["afr_mv"] = self._u16(b, 4)
                d["oilt_mv"] = self._u16(b, 6)
            elif msg.arbitration_id == 0x140 and len(b) >= 4:
                d["fuel_mv"] = self._u16(b, 0)
                d["eth_pct"] = self._u16(b, 2) / 10.0
            elif msg.arbitration_id == 0x160 and len(b) >= 1:
                d["flags"] = b[0]
            if not d:
                continue
            with self._lock:
                self.latest.update(d)
                if msg.arbitration_id == 0x100:
                    self.last_rx = time.monotonic()

    def read(self):
        """Latest values, or {} if the bus has gone quiet."""
        with self._lock:
            if time.monotonic() - self.last_rx > self.STALE_S:
                return {}
            return dict(self.latest)


class ObdSource:
    """Slow engine data from the car's ECU via the OBDLink MX+ (Bluetooth
    RFCOMM, ELM327 command set). Proven bench chain 7/18: water temp, speed,
    and MIL over ISO 9141-2 from the daily driver.

    Same contract as CanSource: auto-detected, background thread, read()
    returns {} when stale so the sim fills in. The K-line is SLOW (~150-300ms
    per PID) which is exactly why OBD only carries the slow channels — water
    temp, speed, CEL — while the Teensy owns everything fast.

    The MX+ must be paired+trusted first (it is; see CLAUDE.md for the
    pairing lessons). MAC is fixed for now — becomes a setting when the
    config menu lands.
    """
    MAC = "00:04:3E:8C:23:9F"
    STALE_S = 5.0

    def __init__(self):
        self.ok = False                 # link up and ECU answering
        self.latest = {}
        self.last_rx = -99.0
        self.sock = None                # live socket, for graceful shutdown
        self._lock = threading.Lock()
        if SNAPSHOT or not hasattr(socket, "AF_BLUETOOTH"):
            if not SNAPSHOT:
                print("No OBD (no bluetooth sockets on this OS): simulated data")
            return
        threading.Thread(target=self._run, daemon=True).start()

    # ---- link management ----------------------------------------------------
    def _run(self):
        first = True
        while True:
            try:
                self._connect_and_poll(first)
            except Exception as e:
                if first:
                    print(f"No OBD yet ({e.__class__.__name__}): simulated data, retrying quietly")
                    first = False
                self.ok = False
            time.sleep(5)               # reconnect cadence — MX+ may be asleep/away

    def _connect_and_poll(self, first):
        # The MX+ serves ONE host at a time, so a leaked socket from a failed
        # attempt blocks every future attempt — always close on the way out.
        # Worse: it WEDGES (baseband-deaf until power-cycled) if its host
        # vanishes mid-conversation, so the dash also closes this socket in a
        # SIGTERM handler — killing the process must still say goodbye.
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                          socket.BTPROTO_RFCOMM)
        s.settimeout(10)
        self.sock = s                   # visible to the shutdown handler
        try:
            self._session(s, first)
        finally:
            self.sock = None
            try:
                s.close()
            except Exception:
                pass

    def _session(self, s, first):
        s.connect((self.MAC, 1))

        def cmd(c, wait=0.6):
            """Send one command, sleep a fixed beat, then drain EVERYTHING.
            Deliberately dumb: returning at the first '>' desyncs the whole
            session after ATZ (the MX+ eats the next command mid-reset and
            every response then pairs with the previous command — cost an
            hour on 7/18). Fixed-wait-and-drain is slower and bulletproof,
            and the per-PID prefix parsing is order-tolerant anyway."""
            s.send((c + "\r").encode())
            time.sleep(wait)
            out = b""
            s.setblocking(False)
            try:
                while True:
                    out += s.recv(4096)
            except (BlockingIOError, socket.timeout):
                pass
            except OSError:
                pass
            s.setblocking(True)
            s.settimeout(10)
            return out.decode(errors="replace")

        cmd("ATZ", 4.0)                 # reset the ELM (it needs the full beat)
        cmd("ATE0")                     # echo off
        cmd("ATS0")                     # spaces off — easier parsing
        cmd("ATSP0")                    # auto protocol
        probe = cmd("0100", 10.0)       # forces protocol negotiation (SEARCHING...)
        if "41" not in probe.replace(" ", ""):
            raise ConnectionError("ECU not answering (ignition off?)")
        if first:
            print("OBD detected: live engine data via OBDLink MX+")
        self.ok = True

        # Poll rotation. Speed every cycle (most dynamic), water every 3rd
        # (thermal mass), MIL every 10th (changes ~never). K-line budget
        # is ~3-5 PIDs/s, so one PID per loop pass, politely.
        n = 0
        while True:
            n += 1
            got = {}
            r = cmd("010C")                          # rpm — warm fallback for
            v = self._val(r, "410C", 2)              # the Teensy's fast path
            if v is not None:
                got["rpm"] = (v[0] * 256 + v[1]) / 4.0
            r = cmd("010D")                          # speed
            v = self._val(r, "410D", 1)
            if v is not None:
                got["speed_mph"] = v[0] * 0.621371
            if n % 3 == 0:
                r = cmd("0105")                      # coolant
                v = self._val(r, "4105", 1)
                if v is not None:
                    got["coolant_f"] = (v[0] - 40) * 9 / 5 + 32
            if n % 10 == 0:
                r = cmd("0101")                      # MIL + DTC count
                v = self._val(r, "4101", 1)
                if v is not None:
                    got["mil"] = bool(v[0] & 0x80)
                    got["dtc_count"] = v[0] & 0x7F
            if got:
                with self._lock:
                    self.latest.update(got)
                    self.last_rx = time.monotonic()
            elif "STOPPED" in r or "UNABLE" in r:
                raise ConnectionError("lost the ECU")
            time.sleep(0.15)

    @staticmethod
    def _val(resp, prefix, nbytes):
        """Pull data bytes out of an ELM response like '410D00' (spaces off)."""
        clean = "".join(resp.split()).replace(">", "")
        i = clean.find(prefix)
        if i < 0:
            return None
        try:
            return [int(clean[i + len(prefix) + 2 * k: i + len(prefix) + 2 * k + 2], 16)
                    for k in range(nbytes)]
        except ValueError:
            return None

    def read(self):
        with self._lock:
            if time.monotonic() - self.last_rx > self.STALE_S:
                return {}
            return dict(self.latest)


class Telemetry:
    """Smoothed vehicle state. Sim engine, with real IMU / CAN overlaid on top
    of it wherever those sources are actually present."""
    def __init__(self):
        self.sim = SimEngine()
        self.imu = ImuSource()
        self.can = CanSource()
        self.obd = ObdSource()
        self.rpm = self.spd = self.gx = self.gy = 0.0
        self.load = 0.0
        self.coolant, self.oilT = 178.0, 198.0
        self.oilP = self.oilExp = self.oilDev = 0.0
        self.fp = self.fpExp = self.fpDev = 0.0
        self.boost, self.afr, self.eth, self.fuel = -12.0, 14.7, 63.0, 78.0
        self.flags = 0                              # turn signals etc. from CAN
        self.can_live = False                       # is real CAN data arriving?
        self.mil = False                            # real check-engine light (OBD)
        self.fault = set()                          # channels reading impossible volts
        self.fail_until = -1.0                      # drive-time failure window

    def update(self, t, dt):
        raw_rpm, raw_spd, raw_gx, raw_gy = self.sim.raw(t)
        # Live CAN overrides the sim per-channel. Anything the Teensy doesn't
        # send yet (speed, water temp) keeps running on the sim, so the dash is
        # always fully populated no matter how much real hardware exists.
        can = self.can.read()
        obd = self.obd.read()
        failing = t < self.fail_until
        # Source priority (Ty 7/18): take ANY real source, prefer the fastest.
        # rpm: Teensy CAN (50Hz) > OBD (~2Hz, laggy but real) > sim. The OBD
        # rpm stays polled even when CAN is healthy, so if the Teensy ever
        # drops mid-drive the gauge degrades to slow-real instead of fake.
        if "rpm" in can:
            raw_rpm = can["rpm"]
        elif "rpm" in obd:
            raw_rpm = obd["rpm"]
        if "speed_mph" in obd:
            raw_spd = obd["speed_mph"]              # REAL speed wins
        k = 1 - math.pow(0.0015, dt)
        self.rpm = lerp(self.rpm, raw_rpm, k)
        self.spd = lerp(self.spd, raw_spd, k)
        if self.imu.ok:
            try:
                rx, ry = self.imu.read()
                raw_gx, raw_gy = rx, ry             # REAL G wins
            except Exception:
                pass
        kg = min(1.0, k * 1.6)
        self.gx = lerp(self.gx, raw_gx, kg)
        self.gy = lerp(self.gy, raw_gy, kg)

        load = 0.0 if self.rpm < 900 else clamp((self.rpm - 1200) / 6400, 0, 1)
        self.load = load
        cool_t = obd.get("coolant_f", 182 + 22 * load)   # REAL water temp wins
        self.coolant = lerp(self.coolant, cool_t, dt * (0.6 if "coolant_f" in obd else 0.05))
        self.mil = obd.get("mil", False)                 # real CEL state

        heat = 0.0
        if 48 <= t < 62:
            heat = 45 * ease(clamp((t - 48) / 9, 0, 1))
        elif t >= 62:
            heat = 45 * (1 - ease(clamp((t - 62) / 6, 0, 1)))
        if failing:
            heat = 85
        oilt_t = 200 + 42 * load + heat
        if "oilt_mv" in can:
            # TODO: real senders are thermistors (non-linear). Linear stand-in
            # until we have one on the bench to characterise.
            oilt_t = 140 + can["oilt_mv"] / 5000.0 * 160
        self.oilT = lerp(self.oilT, oilt_t, dt * 0.12)

        # 0.5-4.5V senders can't legitimately read near 0V or 5V — that's an
        # open or shorted wire. Flag SENSOR FAULT instead of trusting it: a
        # $2 connector must not fake an oil-pressure emergency (Ty 7/17).
        self.fault = set()
        op_t = 0 if self.rpm < 200 else (24 + 48 * load) * (0.62 if failing else 1)
        if "oilp_mv" in can:
            if 250 <= can["oilp_mv"] <= 4750:
                op_t = scale_sensor("press", SETTINGS.oil_press_sensor,
                                    can["oilp_mv"] / 1000.0)
            else:
                self.fault.add("oilP")
        self.oilP = lerp(self.oilP, op_t, k)
        self.oilExp = 0 if self.rpm < 200 else 24 + 48 * load
        self.oilDev = lerp(self.oilDev, self.oilP - self.oilExp,
                           1 - math.pow(0.3, dt))

        b_t = 0 if self.rpm < 400 else -13 + 33 * ease(clamp((load - 0.15) / 0.75, 0, 1))
        if "map_mv" in can:
            # MAP profile is user-selectable (2/3/4-bar) since 7/19 —
            # settings page 2. Boost = absolute pressure minus atmosphere.
            abs_psi = scale_sensor("map", SETTINGS.map_sensor,
                                   can["map_mv"] / 1000.0)
            b_t = abs_psi - 14.7
        self.boost = lerp(self.boost, b_t, k)

        self.fpExp = 0 if self.rpm < 400 else SETTINGS.fuel_press_base + max(0, self.boost)
        fp_t = self.fpExp
        if "fuelp_mv" in can:
            if 250 <= can["fuelp_mv"] <= 4750:
                fp_t = scale_sensor("press", SETTINGS.fuel_press_sensor,
                                    can["fuelp_mv"] / 1000.0)
            else:
                self.fault.add("fuelP")
        self.fp = lerp(self.fp, fp_t, k)
        self.fpDev = lerp(self.fpDev, self.fp - self.fpExp, 1 - math.pow(0.3, dt))

        if load > 0.5:
            a_t = 13.9 if failing else 11.4 + 0.3 * math.sin(t * 3)
        else:
            a_t = 14.7 + 0.12 * math.sin(t * 1.7)
        if "afr_mv" in can:
            a_t = scale_sensor("afr", SETTINGS.wideband_sensor,
                               can["afr_mv"] / 1000.0)
        self.afr = lerp(self.afr, a_t, 1 - math.pow(0.05, dt))

        # Can we actually measure motion? Decides settings lockout: with real
        # speed present, SETUP is PARKED-only (the car rule); without it (the
        # bench), SETUP stays available — sim "speed" shouldn't lock anyone out.
        self.real_speed = "speed_mph" in obd
        self.eth = can.get("eth_pct", 63.0)
        fuel_t = 78 - (t / DUR) * 6
        if "fuel_mv" in can:
            # TODO: GC sender is noisy + non-linear; calibration curve is an
            # open item in the spec. Linear stand-in for now.
            fuel_t = can["fuel_mv"] / 5000.0 * 100
        self.fuel = fuel_t
        self.flags = can.get("flags", 0)      # turn signals; display not wired yet
        self.can_live = bool(can)
        if SIM_RIG and SIM_RIG.alive:
            try:
                SIM_RIG.apply(self)     # desktop sim rig sliders override all
            except Exception:
                PANEL.alive = False   # a rig bug must never take down the dash


# ============================ mode + alerts =================================

RANK = {"PARKED": 0, "CRUISING": 1, "SPIRITED": 2, "RACING": 3}
ORDER = ["PARKED", "CRUISING", "SPIRITED", "RACING"]

class ModeEngine:
    """Ty's rule: escalate instantly, de-escalate after 6 s of sustained calm."""
    def __init__(self):
        self.g_env = 0.0
        self.mode = "PARKED"
        self.calm = 0.0

    def update(self, tel, dt, force=False):
        g = math.hypot(tel.gx, tel.gy)
        self.g_env = max(self.g_env * math.pow(0.72, dt), g)
        if tel.spd < 3 and tel.rpm < 1200:
            target = "PARKED"
        elif self.g_env > 0.95 or tel.rpm > 6600:
            target = "RACING"
        elif self.g_env > 0.50 or tel.rpm > 4300:
            target = "SPIRITED"
        else:
            target = "CRUISING"
        if force:
            self.mode, self.calm = target, 0.0
            return
        if RANK[target] > RANK[self.mode]:
            self.mode, self.calm = target, 0.0
        elif RANK[target] < RANK[self.mode]:
            self.calm += dt
            if self.calm > 6:
                self.mode = ORDER[RANK[self.mode] - 1]
                self.calm = 0.0
        else:
            self.calm = 0.0


ALERTS = [  # severity order — most critical first
    # Pressure alarms are gated on sensor health: a faulted sender can
    # neither raise nor sustain an alarm (the tile shows SENSOR FAULT).
    dict(id="OILP",  label="OIL PRESS",  w="oilP",
         on=lambda s: "oilP" not in s.fault
                      and s.oilDev < -SETTINGS.oil_press_dev_alarm,
         off=lambda s: "oilP" in s.fault
                       or s.oilDev > -SETTINGS.oil_press_dev_alarm + 4),
    dict(id="FUELP", label="FUEL PRESS", w="fuelP",
         on=lambda s: "fuelP" not in s.fault
                      and s.fpDev < -SETTINGS.fuel_press_dev_alarm,
         off=lambda s: "fuelP" in s.fault
                       or s.fpDev > -SETTINGS.fuel_press_dev_alarm + 3),
    dict(id="OILT",  label="OIL TEMP",   w="oilT",
         on=lambda s: s.oilT >= SETTINGS.oil_temp_alarm,
         off=lambda s: s.oilT <= SETTINGS.oil_temp_alarm - 10),
    dict(id="WATER", label="WATER TEMP",  w="coolant",
         on=lambda s: s.coolant >= SETTINGS.water_temp_alarm,
         off=lambda s: s.coolant <= SETTINGS.water_temp_alarm - 10),
    dict(id="AFR",   label="AFR LEAN",   w="afr",
         on=lambda s: s.load > 0.55 and s.afr > 13.2,
         off=lambda s: s.afr < 12.9 or s.load < 0.5,
         dwell=0.25),  # sustained-lean required; rejects boost-ramp AFR blips
]

class AlertEngine:
    def __init__(self):
        self.on = {}
        self.pending = {}

    def update(self, tel, dt):
        for a in ALERTS:
            dwell = a.get("dwell", 0)
            if not self.on.get(a["id"]):
                if a["on"](tel):
                    self.pending[a["id"]] = self.pending.get(a["id"], 0) + dt
                    if self.pending[a["id"]] >= dwell:
                        self.on[a["id"]] = True
                else:
                    self.pending[a["id"]] = 0
            elif a["off"](tel):
                self.on[a["id"]] = False
                self.pending[a["id"]] = 0

    def active(self):
        return [a for a in ALERTS if self.on.get(a["id"])]


# ============================ adaptive layout ===============================

def R(x, y, w, h, a): return dict(x=x, y=y, w=w, h=h, a=a)

# Corner-sweep tiles want wide cells (~2.2:1), not the squares the old round
# gauges used. Sentinel home row: three wide small tiles, fixed positions.
SENT = dict(oilP=R(472, 486, 176, 96, 0), afr=R(656, 486, 176, 96, 0),
            fuelP=R(840, 486, 176, 96, 0))
def sent_row(a):
    return {k: dict(v, a=a) for k, v in SENT.items()}
def sent_row_no_afr(a):
    """oilP + fuelP only — SPIRITED/RACING promote AFR out of the sentinel
    row into a full priority gauge, so it isn't placed twice."""
    return {k: dict(v, a=a) for k, v in SENT.items() if k != "afr"}

LAYOUTS = {
    # PARKED keeps the RPM bar fully visible — a parked car can still be
    # idling/revving, and a live tach must never look suppressed (Ty 7/18).
    "PARKED": dict(
        rpm=R(32, 20, 960, 38, 1),      speed=R(312, 150, 400, 260, 0),
        gcircle=R(60, 130, 300, 300, 0), fuel=R(120, 250, 300, 70, 1),
        eth=R(120, 340, 300, 70, 0.9),  coolant=R(540, 170, 230, 110, 1),
        oilT=R(540, 300, 230, 110, 1),  boost=R(300, 400, 140, 140, 0),
        **sent_row(0.45)),
    # CRUISING: MPH holds the left column (a lone boost tile there looked
    # orphaned — Ty 7/17); boost lives with the other gauges on the right.
    "CRUISING": dict(
        rpm=R(32, 20, 960, 38, 1),      speed=R(70, 150, 360, 280, 1),
        gcircle=R(60, 180, 220, 220, 0),
        coolant=R(744, 150, 250, 100, 1), oilT=R(744, 262, 250, 100, 1),
        boost=R(744, 374, 250, 100, 1),
        fuel=R(70, 450, 250, 60, 1),    eth=R(70, 522, 250, 60, 1),
        **sent_row(1)),
    # SPIRITED/RACING: rule-of-thirds grid below the fixed RPM bar. Left
    # column = G-force, center column = temps (water/oil stacked), right
    # column = performance (boost/AFR stacked), bottom band = secondary
    # readouts. Priority is signaled by size and position only — nothing
    # is dimmed here; only the alert-triage view changes color/brightness.
    # Performance modes fill the screen (Ty 7/17): big tiles wall-to-wall,
    # sentinels grow to full tiles on the bottom row (still their home row).
    "SPIRITED": dict(
        rpm=R(32, 16, 960, 56, 1),      gcircle=R(60, 130, 190, 190, 1),
        coolant=R(290, 140, 340, 132, 1), oilT=R(290, 286, 340, 132, 1),
        boost=R(650, 140, 340, 132, 1), afr=R(650, 286, 340, 132, 1),
        oilP=R(290, 432, 340, 128, 1),  fuelP=R(650, 432, 340, 128, 1),
        speed=R(70, 332, 170, 100, 1),
        fuel=R(45, 444, 215, 58, 1),    eth=R(45, 514, 215, 58, 1)),
    "RACING": dict(
        rpm=R(16, 10, 992, 88, 1),      gcircle=R(45, 155, 180, 180, 1),
        coolant=R(270, 152, 360, 140, 1), oilT=R(270, 306, 360, 140, 1),
        boost=R(646, 152, 360, 140, 1), afr=R(646, 306, 360, 140, 1),
        oilP=R(270, 460, 360, 126, 1),  fuelP=R(646, 460, 360, 126, 1),
        speed=R(55, 347, 160, 95, 1),
        fuel=R(40, 454, 220, 60, 1),    eth=R(40, 526, 220, 60, 1)),
}

# ---- alert triage layout: computed, never hand-placed ----------------------
# Hand-tuned alert positions couldn't cover every mode x alert-count x
# which-gauge combination — untuned combos overlapped (found 7/17). Instead
# the alert view is DEALT onto a 12-column x 3-row grid: alerted gauges get
# big 2-row spans across the top (1 alert = half width, 2 = halves, 3 =
# thirds), every surviving gauge flows into the remaining cells. Overlap is
# impossible by construction, every combination fills the screen, and the
# noise (g-circle, fuel, eth) hides per rule 8.

ALERT_ORDER = ("oilP", "fuelP", "oilT", "afr", "boost", "coolant")

def alert_layout(mode, active):
    base = LAYOUTS[mode]
    rpm = base["rpm"]
    y0 = rpm["y"] + rpm["h"] + 12 + 40        # clear of the indicator row
    G, X0, X1, Y1 = 14, 20, 1004, 592
    cw = (X1 - X0 - 11 * G) / 12
    rh = (Y1 - y0 - 2 * G) / 3

    def cell(c, cs, r, rs):
        return R(X0 + c * (cw + G), y0 + r * (rh + G),
                 cs * cw + (cs - 1) * G, rs * rh + (rs - 1) * G, 1)

    tgt = {k: dict(v, a=0) for k, v in base.items()}   # default: hidden in place
    tgt["rpm"] = dict(rpm)                             # RPM bar never moves
    n = min(len(active), 3)
    alerted = [al["w"] for al in active[:3]]
    others = [w for w in ALERT_ORDER if w not in alerted]
    if n == 1:
        tgt[alerted[0]] = cell(0, 6, 0, 2)             # 1 large...
        tgt[others[0]] = cell(6, 6, 0, 1)
        tgt[others[1]] = cell(6, 6, 1, 1)
        for i, w in enumerate(others[2:5]):
            tgt[w] = cell(i * 3, 3, 2, 1)
        tgt["speed"] = cell(9, 3, 2, 1)
    elif n == 2:
        tgt[alerted[0]] = cell(0, 6, 0, 2)             # ...2 medium...
        tgt[alerted[1]] = cell(6, 6, 0, 2)
        for i, w in enumerate(others[:4]):
            tgt[w] = cell(i * 3, 3, 2, 1)
    else:
        for i, w in enumerate(alerted):                # ...3 smaller (rule 8)
            tgt[w] = cell(i * 4, 4, 0, 2)
        for i, w in enumerate(others):
            tgt[w] = cell(i * 4, 4, 2, 1)
    return tgt

class Layout:
    def __init__(self):
        self.cur = {k: dict(v) for k, v in LAYOUTS["PARKED"].items()}

    def update(self, dt, mode, active):
        k = 1 - math.pow(0.03, dt)
        if active:
            tgt = alert_layout(mode, active)
        else:
            tgt = LAYOUTS[mode]
        for w, cur in self.cur.items():
            t = tgt[w]
            for p in ("x", "y", "w", "h", "a"):
                cur[p] = lerp(cur[p], t[p], k)


# ============================ rendering =====================================

WINDOWED = os.environ.get("WAPOW_WINDOWED")           # desktop dev mode: real window, no fullscreen grab


class DemoPanel(threading.Thread):
    """Desktop-only "sim rig": a second window of EQ-style sliders that
    override any sensor channel live, plus a restart button to replay the
    whole boot (splash included). Tkinter runs in its own thread; the two
    threads share only plain dicts of floats/bools, which Python updates
    atomically — no locks needed. Enable a channel's checkbox and its
    slider value wins over the sim; uncheck and the sim takes it back.
    """
    # (attr on Telemetry, label, slider min, max, step, start)
    CHANNELS = [
        ("rpm",     "RPM",      0,    9000, 50,   800),
        ("spd",     "MPH",      0,    160,  1,    0),
        ("gx",      "LAT G",    -1.5, 1.5,  0.05, 0),
        ("oilP",    "OIL PSI",  0,    120,  1,    45),
        ("fp",      "FUEL PSI", 0,    100,  1,    43),
        ("afr",     "AFR",      8.0,  20.0, 0.1,  14.7),
        ("boost",   "BOOST",    -15,  30,   0.5,  0),
        ("oilT",    "OIL F",    140,  320,  1,    210),
        ("coolant", "WATER F",  140,  260,  1,    185),
        ("fuel",    "FUEL %",   0,    100,  1,    78),
        ("eth",     "ETH %",    0,    100,  1,    63),
    ]

    def __init__(self):
        super().__init__(daemon=True)   # daemon: dies with the dash, no cleanup
        self.val = {c[0]: float(c[5]) for c in self.CHANNELS}
        self.live = {c[0]: False for c in self.CHANNELS}
        self.restart_requested = False
        self.alive = True
        self.start()

    def run(self):
        try:
            import tkinter as tk
        except ImportError:
            self.alive = False          # no tkinter = no panel, dash unaffected
            return
        root = tk.Tk()
        root.title("WAPOW SIM RIG")
        root.configure(bg="#101420")
        for i, (key, label, lo, hi, step, start) in enumerate(self.CHANNELS):
            frame = tk.Frame(root, bg="#101420")
            frame.grid(row=0, column=i, padx=4, pady=6)
            tk.Label(frame, text=label, fg="#9fb0c8", bg="#101420",
                     font=("Segoe UI", 8, "bold")).pack()
            # closure trick: key=key freezes THIS channel's name into the
            # callback (otherwise every slider would edit the last channel)
            scale = tk.Scale(frame, from_=hi, to=lo, resolution=step,
                             length=210, orient="vertical",
                             bg="#101420", fg="#e8eefc", troughcolor="#1c2436",
                             highlightthickness=0,
                             command=lambda s, key=key: self.val.__setitem__(key, float(s)))
            scale.set(start)
            scale.pack()
            var = tk.BooleanVar(value=False)
            tk.Checkbutton(frame, text="LIVE", variable=var,
                           fg="#57e6b4", bg="#101420", selectcolor="#1c2436",
                           activebackground="#101420", font=("Segoe UI", 8),
                           command=lambda v=var, key=key:
                               self.live.__setitem__(key, v.get())).pack()
        tk.Button(root, text="RESTART DASH\n(replay splash)", bg="#3a1420",
                  fg="#ff6a7a", font=("Segoe UI", 9, "bold"), relief="flat",
                  padx=10, pady=8,
                  command=lambda: setattr(self, "restart_requested", True)
                  ).grid(row=0, column=len(self.CHANNELS), padx=10)

        def closed():
            self.alive = False          # releases all overrides back to sim
            root.destroy()
        root.protocol("WM_DELETE_WINDOW", closed)
        root.mainloop()

    def apply(self, tel):
        """Stomp panel values onto the freshly-computed telemetry. Runs at
        the end of every Telemetry.update. Deviations are recomputed so the
        oil/fuel pressure alarms respond honestly to slider abuse."""
        v, on = self.val, self.live
        for key in ("rpm", "spd", "gx", "afr", "oilT", "coolant", "fuel", "eth"):
            if on[key]:
                setattr(tel, key, v[key])
        if on["boost"]:
            tel.boost = v["boost"]
            tel.fpExp = 0 if tel.rpm < 400 else \
                SETTINGS.fuel_press_base + max(0, tel.boost)
        if on["fp"]:
            tel.fp = v["fp"]
        if on["fp"] or on["boost"]:
            tel.fpDev = tel.fp - tel.fpExp
        if on["oilP"]:
            tel.oilP = v["oilP"]
            tel.oilDev = tel.oilP - tel.oilExp


SIM_RIG = DemoPanel() if WINDOWED else None

pygame.init()
if SNAPSHOT or WINDOWED:
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("WAPOW (dev)")
else:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    if screen.get_size() != (W, H):
        screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
clock = pygame.time.Clock()


def play_splash():
    """Boot splash, played by the dash itself.

    The old way ran a separate video player (mpv) fullscreen on top of the
    dash — two fullscreen apps fighting over one screen, which froze and
    crashed on the Pi. Now the launcher pre-extracts the splash video into
    JPEG frames once (ffmpeg, see wapow_start.sh) and we simply flip
    through them here at 25 fps. One app owns the screen from the very
    first pixel, so there is nothing to hand off, cover, or reveal.
    Any tap or key skips straight to the gauges. No frames dir = no splash.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    frames = sorted(glob.glob(os.path.join(here, "splash_frames", "*.jpg")))
    if not frames:
        return
    # Soundtrack: the glitch + synthwave audio, rebuilt from the two source
    # videos into one ogg (the combined mp4 itself carries no audio track).
    # Best-effort — no audio file or no audio device just means a silent
    # splash, never a crash.
    sound = False
    audio = os.path.join(here, "wapow_splash_audio.ogg")
    if os.path.exists(audio):
        try:
            pygame.mixer.music.load(audio)
            pygame.mixer.music.play()
            sound = True
        except pygame.error:
            pass
    try:
        for path in frames:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or \
                   ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                    return              # tap/key skips (finally stops the music)
            try:
                img = pygame.image.load(path).convert()
            except pygame.error:
                return                  # unreadable frame: just start driving
            screen.fill((0, 0, 0))      # frames are 1024x576 — thin letterbox
            screen.blit(img, img.get_rect(center=(W // 2, H // 2)))
            pygame.display.flip()
            clock.tick(25)              # frames were extracted at 25 fps
    finally:
        if sound:
            pygame.mixer.music.stop()


_fonts = {}
def font(px, bold=False):
    px = max(10, int(px))              # (size, weight) key — one Font per combo
    if (px, bold) not in _fonts:
        _fonts[(px, bold)] = pygame.font.SysFont(None, px, bold=bold)
    return _fonts[(px, bold)]

def text(surf, s, px, col, center=None, topleft=None, midleft=None, bold=False):
    img = font(px, bold).render(s, True, col)
    r = img.get_rect()
    if center: r.center = center
    if topleft: r.topleft = topleft
    if midleft: r.midleft = midleft
    surf.blit(img, r)
    return r

def arc_brush(surf, cx, cy, rad, a0, a1, width, col):
    steps = max(8, int(rad * (a1 - a0) / 4))
    for i in range(steps + 1):
        a = a0 + (a1 - a0) * i / steps
        p = (cx + math.cos(a) * rad, cy + math.sin(a) * rad)
        pygame.draw.circle(surf, col, p, width / 2)

# ---- corner-sweep tile (spec "Gauge Tile Design", decided 7/17) ------------
# The new gauge skin, prototyped on oil pressure first. A thick bar runs up
# the tile's left edge and bends through a rounded corner across the top;
# the NOMINAL zone rides the bend, so a healthy gauge is a fill parked at
# the corner. Same brush trick as arc_brush: stamp circles along a path.

def _lpath(r):
    """Geometry for a tile's L-path. Returns (point_at(dist), total_len,
    bend_len) where bend_len is the distance to the middle of the curve —
    the spot pct=45 (nominal center) maps to."""
    h = r["h"]
    sw = max(7.0, h * 0.10)                   # bar thickness scales with tile
    rad = max(12.0, h * 0.18)                 # bend radius
    ins = max(6.0, h * 0.06) + sw / 2
    x0, y0 = r["x"] + ins, r["y"] + ins       # top-left of the path
    xe, yb = r["x"] + r["w"] - ins, r["y"] + r["h"] - ins
    seg1 = yb - (y0 + rad)                    # vertical run
    arc = math.pi * rad / 2                   # quarter-circle bend
    total = seg1 + arc + (xe - (x0 + rad))
    cx, cy = x0 + rad, y0 + rad               # bend center

    def point_at(d):
        if d <= seg1:
            return x0, yb - d
        if d <= seg1 + arc:
            a = math.pi + (d - seg1) / rad    # 180deg..270deg around the bend
            return cx + rad * math.cos(a), cy + rad * math.sin(a)
        return x0 + rad + (d - seg1 - arc), y0

    return point_at, total, seg1 + arc / 2, sw

def _tile_dist(pct, total, bend):
    """Bar travel is non-linear on purpose: 0-45% of scale fills the left
    edge, 45-100% wraps the top — so nominal always lands mid-bend."""
    pct = clamp(pct, 0, 100)
    if pct <= 45:
        return pct / 45 * bend
    return bend + (pct - 45) / 55 * (total - bend)

def _stroke(surf, point_at, d0, d1, width, col):
    steps = max(2, int((d1 - d0) / 2))
    for i in range(steps + 1):
        surf and pygame.draw.circle(surf, col, point_at(d0 + (d1 - d0) * i / steps), width / 2)

def draw_tile(surf, r, value, label, unit, pct, now, hot=False,
              peak_pct=None, peek=False, dec=0, nom=True, fault=False):
    """One corner-sweep gauge tile. peek=True renders the PEAK state (amber).
    nom=False skips the nominal band (linear readouts like ETH have no
    "healthy corner"). fault=True renders SENSOR FAULT: no number, no fill,
    no alarm — a dead sender must never impersonate a dead engine."""
    if r["a"] < 0.02: return
    rect = pygame.Rect(r["x"], r["y"], r["w"], r["h"])
    pygame.draw.rect(surf, PANEL, rect, border_radius=10)
    border = AMBER if fault else (RED if hot else (33, 44, 60))
    pygame.draw.rect(surf, border, rect, width=2, border_radius=10)
    point_at, total, bend, sw = _lpath(r)
    _stroke(surf, point_at, 0, total, sw, (34, 44, 60))                 # track
    if nom and not fault:                                               # nominal band
        _stroke(surf, point_at, _tile_dist(36, total, bend),
                _tile_dist(58, total, bend), sw, (32, 92, 80))
    if fault:
        text(surf, "— —", r["h"] * 0.40, DIM, bold=True,
             midleft=(r["x"] + sw + r["h"] * 0.14, r["y"] + r["h"] * 0.44))
        text(surf, "SENSOR FAULT", max(11, r["h"] * 0.13), AMBER,
             topleft=(r["x"] + sw + r["h"] * 0.14,
                      r["y"] + r["h"] - max(11, r["h"] * 0.13) - r["h"] * 0.07))
        text(surf, label, max(12, r["h"] * 0.16), DIM,
             topleft=(r["x"] + r["w"] - r["h"] * 0.95, r["y"] + r["h"] * 0.22))
        return
    col = AMBER if peek else (RED if hot else TEAL)
    _stroke(surf, point_at, 0, _tile_dist(pct, total, bend), sw, col)   # fill
    if peak_pct is not None:                                            # peak dot
        pygame.draw.circle(surf, TEXT, point_at(_tile_dist(peak_pct, total, bend)),
                           max(2.5, sw * 0.22))
    vcol = AMBER if peek else (RED if hot else TEXT)
    vs = f"{value:.{dec}f}"
    vr = text(surf, vs, r["h"] * 0.44, vcol, bold=True,
              midleft=(r["x"] + sw + r["h"] * 0.14, r["y"] + r["h"] * 0.46))
    text(surf, unit, max(11, r["h"] * 0.14), DIM, midleft=(vr.right + 7, vr.centery + r["h"] * 0.09))
    text(surf, label, max(12, r["h"] * 0.16), RED if hot else DIM,
         topleft=(r["x"] + sw + r["h"] * 0.14, r["y"] + r["h"] - max(12, r["h"] * 0.16) - r["h"] * 0.07))
    if peek:
        text(surf, "PEAK", max(11, r["h"] * 0.13), AMBER,
             topleft=(r["x"] + r["w"] - r["h"] * 0.55, r["y"] + r["h"] * 0.24))


class Peaks:
    """Session peak store. Resets when the car leaves PARKED (Ty 7/17 —
    revisit the reset policy later)."""
    def __init__(self):
        self.v = {}

    def update(self, **kw):
        for k, val in kw.items():
            if val > self.v.get(k, -1e9):
                self.v[k] = val

    def get(self, k, default=0.0):
        return self.v.get(k, default)

    def reset(self):
        self.v = {}


# ---- tach: segment ladder (restyled 7/18, Ty's pick) -----------------------
# 48 thin tall cells. Scale: 400-4000 rpm owns the first 1/3 of the ladder,
# 4001-9000 owns the last 2/3 — the shift-decision band gets the real estate.
# Colors are anchored to RPM VALUES, not bar position, so when sweep limits
# become preset-configurable the colors stay honest automatically.
RPM_MIN, RPM_KNEE = 400, 4000
RPM_SEGS = 48

def rpm_frac(rpm):
    if rpm <= RPM_MIN:
        return 0.0
    if rpm <= RPM_KNEE:
        return (rpm - RPM_MIN) / (RPM_KNEE - RPM_MIN) / 3
    return 1 / 3 + clamp((rpm - RPM_KNEE) / (SETTINGS.rpm_max - RPM_KNEE), 0, 1) * 2 / 3

def _rpm_at_frac(z):
    if z <= 1 / 3:
        return RPM_MIN + z * 3 * (RPM_KNEE - RPM_MIN)
    return RPM_KNEE + (z - 1 / 3) * 1.5 * (SETTINGS.rpm_max - RPM_KNEE)

def _rpm_color(rpm, stops):
    for i in range(1, len(stops)):
        r1, c1 = stops[i]
        if rpm <= r1:
            r0, c0 = stops[i - 1]
            f = (rpm - r0) / max(1, r1 - r0)
            return tuple(int(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
    return RED

# Segment colors depend on redline/max, which are SETTINGS now (config menu):
# color stops ride relative to the redline, so a 7,600 NA redline keeps the
# same teal->red story as a 6,800 blower. Rebuilt only when values change.
_tach_cache = dict(key=None, colors=[], rpms=[])

def _tach_segments():
    rl, mx = SETTINGS.rpm_redline, SETTINGS.rpm_max
    if _tach_cache["key"] != (rl, mx):
        stops = [(RPM_MIN, TEAL), (rl - 2000, TEAL),
                 (rl - 1200, (170, 230, 110)), (rl - 700, YELLOW),
                 (rl - 300, AMBER), (rl - 100, (255, 120, 60)),
                 (rl, RED), (mx, RED)]
        rpms = [_rpm_at_frac(i / (RPM_SEGS - 1)) for i in range(RPM_SEGS)]
        _tach_cache.update(key=(rl, mx),
                           colors=[_rpm_color(r, stops) for r in rpms],
                           rpms=rpms)
    return _tach_cache["colors"], _tach_cache["rpms"]

def draw_rpm(surf, r, tel, now, peak=None, peek=False):
    """The tach ladder. peak: session-max rpm -> white tell-tale marker.
    peek: 3s amber recall — ladder AND digits jump to the peak (same
    double-tap contract as the tiles)."""
    if r["a"] < 0.02: return
    a = r["a"]
    show_rpm = peak if (peek and peak) else tel.rpm
    show_digits = r["h"] > 34
    dig_w = r["h"] * 2.4 if show_digits else 0
    lx, lw = r["x"] + dig_w, r["w"] - dig_w
    pitch = lw / RPM_SEGS
    gap = max(1, pitch * 0.22)
    lit_frac = rpm_frac(show_rpm)
    redline = SETTINGS.rpm_redline
    seg_colors, seg_rpms = _tach_segments()
    flash = (not peek) and tel.rpm > redline - 500 and int(now * 8) % 2 == 0
    for i in range(RPM_SEGS):
        z = i / (RPM_SEGS - 1)
        lit = z <= lit_frac
        if lit:
            col = AMBER if peek else (RED if flash else seg_colors[i])
        else:
            col = (42, 22, 28) if seg_rpms[i] >= redline else (26, 34, 48)
        pygame.draw.rect(surf, fade(col, a),
                         (lx + i * pitch, r["y"], pitch - gap, r["h"]),
                         border_radius=2)
    if peak and peak > RPM_MIN:                       # peak-hold tell-tale
        px = lx + rpm_frac(peak) * (RPM_SEGS - 1) / RPM_SEGS * lw
        pygame.draw.rect(surf, fade(TEXT, a), (px, r["y"] - 2, 3, r["h"] + 4))
    if show_digits:
        dcol = AMBER if peek else (RED if show_rpm >= redline else YELLOW)
        text(surf, f"{int(show_rpm)}", r["h"], fade(dcol, a),
             midleft=(r["x"] + 8, r["y"] + r["h"] / 2))
        if peek:
            text(surf, "PEAK", max(11, r["h"] * 0.28), AMBER,
                 topleft=(r["x"] + 8, r["y"] + r["h"] + 4))

def draw_speed(surf, r, tel):
    if r["a"] < 0.02: return
    a = r["a"]
    text(surf, str(int(tel.spd)), r["h"] * 0.85, fade(TEXT, a),
         center=(r["x"] + r["w"] / 2, r["y"] + r["h"] * 0.42))
    text(surf, "MPH", max(14, r["h"] * 0.15), fade(DIM, a),
         center=(r["x"] + r["w"] / 2, r["y"] + r["h"] * 0.88))

def draw_gcircle(surf, r, tel, trail):
    if r["a"] < 0.02: return
    a = r["a"]
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    rad = min(r["w"], r["h"]) / 2 - 8
    MAXG = 1.4
    for g in (0.5, 1.0):
        pygame.draw.circle(surf, fade((40, 48, 62), a), (cx, cy), rad * g / MAXG, 2)
    pygame.draw.circle(surf, fade((60, 70, 88), a), (cx, cy), rad, 2)
    pygame.draw.line(surf, fade((34, 41, 54), a), (cx - rad, cy), (cx + rad, cy))
    pygame.draw.line(surf, fade((34, 41, 54), a), (cx, cy - rad), (cx, cy + rad))
    n = len(trail)
    for i, (tx, ty) in enumerate(trail):
        f = (i + 1) / n
        pygame.draw.circle(surf, fade(TEAL, f * 0.5 * a),
                           (cx + tx / MAXG * rad, cy + ty / MAXG * rad), 3 + f * 3)
    pygame.draw.circle(surf, fade(TEAL, a),
                       (cx + tel.gx / MAXG * rad, cy + tel.gy / MAXG * rad), 8)
    text(surf, f"{math.hypot(tel.gx, tel.gy):.2f} g", max(15, rad * 0.18),
         fade((170, 180, 196), a), center=(cx, r["y"] + r["h"] - 6))

def draw_gauge(surf, r, val, lo, hi, warn, label, unit, now, opts=None):
    if r["a"] < 0.02: return
    a = r["a"]
    o = opts or {}
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    rad = min(r["w"], r["h"]) / 2 - 6
    a0, a1 = math.pi * 0.75, math.pi * 2.25
    step = o.get("step", 1)
    dec = o.get("dec", 0)
    frac = clamp(o["frac"], 0, 1) if "frac" in o else clamp((val - lo) / (hi - lo), 0, 1)
    hot = o["hot"] if "hot" in o else val >= warn
    if hot:
        pulse = 0.30 + 0.30 * math.sin(now * 7)
        arc_brush(surf, cx, cy, rad * 1.14, 0, math.tau,
                  max(3, rad * 0.09), fade(RED, pulse * a))
    wid = max(5, rad * 0.14)
    arc_brush(surf, cx, cy, rad, a0, a1, wid, fade((26, 33, 48), a))
    col = RED if hot else TEAL
    arc_brush(surf, cx, cy, rad, a0, a0 + (a1 - a0) * frac, wid, fade(col, a))
    shown = round(val / step) * step
    text(surf, f"{shown:.{dec}f}", rad * 0.52, fade(RED_HI if hot else TEXT, a),
         center=(cx, cy - rad * 0.05))
    small = max(13, rad * 0.20)
    lab_col = fade(RED if hot else DIM, a)
    text(surf, unit, small, lab_col, center=(cx, cy + rad * 0.32))
    text(surf, label, small, lab_col, center=(cx, cy + rad * 0.78))

def draw_fuel(surf, r, tel):
    if r["a"] < 0.02: return
    a = r["a"]
    rect = pygame.Rect(r["x"], r["y"], r["w"], r["h"])
    pygame.draw.rect(surf, fade(PANEL, a), rect, border_radius=int(r["h"] / 3))
    frac = tel.fuel / 100
    col = RED if frac < 0.15 else BLUE
    fr = pygame.Rect(r["x"] + 3, r["y"] + 3, (r["w"] - 6) * frac, r["h"] - 6)
    pygame.draw.rect(surf, fade(col, a), fr, border_radius=int((r["h"] - 6) / 3))
    text(surf, f"FUEL {int(tel.fuel)}%", max(14, r["h"] * 0.5),
         fade((170, 180, 196), a), midleft=(r["x"] + 10, r["y"] + r["h"] / 2))

def draw_eth(surf, r, tel):
    if r["a"] < 0.02: return
    a = r["a"]
    rect = pygame.Rect(r["x"], r["y"], r["w"], r["h"])
    pygame.draw.rect(surf, fade(PANEL, a), rect, border_radius=8)
    pygame.draw.rect(surf, fade((35, 43, 56), a), rect, width=2, border_radius=8)
    text(surf, f"E{int(tel.eth)}", r["h"] * 0.62, fade(PURPLE, a),
         center=(r["x"] + r["w"] * 0.35, r["y"] + r["h"] / 2))
    text(surf, "ETH", max(11, r["h"] * 0.34), fade(DIM, a),
         center=(r["x"] + r["w"] * 0.78, r["y"] + r["h"] / 2))

# ---- fixed indicator row + knock log ---------------------------------------

def ind_chip(surf, x, y, w, label, on, col):
    rect = pygame.Rect(x, y, w, 28)
    pygame.draw.rect(surf, fade(col, 0.2) if on else (16, 20, 29), rect,
                     border_radius=14)
    pygame.draw.rect(surf, col if on else (28, 35, 48), rect, width=2,
                     border_radius=14)
    text(surf, label, 17, col if on else (57, 66, 79),
         center=(x + w / 2, y + 14))
    return rect

def arrow(surf, x, y, d, on):
    col = GREEN if on else (28, 35, 48)
    if d < 0: pts = [(x, y + 9), (x + 16, y), (x + 16, y + 18)]
    else:     pts = [(x + 16, y + 9), (x, y), (x, y + 18)]
    pygame.draw.polygon(surf, col, pts)

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

class Logger:
    """CSV data logger. Auto-starts/stops with the LOG indicator (SPIRITED+,
    same rule as the spec's datalog trigger) — one file per contiguous
    recording run, written incrementally so a crash doesn't lose the data."""
    FIELDS = ["session_s", "sim_s", "mode", "rpm", "spd", "gx", "gy", "load",
              "coolant", "oilT", "oilP", "oilExp", "oilDev",
              "boost", "afr", "eth", "fuel", "fp", "fpExp", "fpDev"]
    RATE_HZ = 20   # samples/sec written to disk; bump if you need finer resolution

    def __init__(self):
        self.file = None
        self.writer = None
        self.since_sample = 99.0

    def update(self, recording, now, t, mode, tel, dt):
        if recording and self.file is None:
            self._open()
        elif not recording and self.file is not None:
            self._close()
        if self.file is None:
            return
        self.since_sample += dt
        if self.since_sample < 1.0 / self.RATE_HZ:
            return
        self.since_sample = 0.0
        self.writer.writerow([
            f"{now:.2f}", f"{t:.2f}", mode,
            round(tel.rpm, 1), round(tel.spd, 1), round(tel.gx, 3), round(tel.gy, 3),
            round(tel.load, 3), round(tel.coolant, 1), round(tel.oilT, 1),
            round(tel.oilP, 1), round(tel.oilExp, 1), round(tel.oilDev, 1),
            round(tel.boost, 2), round(tel.afr, 2), round(tel.eth, 1), round(tel.fuel, 1),
            round(tel.fp, 1), round(tel.fpExp, 1), round(tel.fpDev, 1),
        ])

    KEEP = 100     # newest logs kept; the bench demo makes one per lap forever

    def _open(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        # Retention: prune oldest beyond KEEP (found 7/19: 1,300+ files /
        # 152MB of sim laps — an SD card killer left unchecked).
        try:
            old = sorted(f for f in os.listdir(LOG_DIR) if f.endswith(".csv"))
            for f in old[:-(self.KEEP - 1) or None] if len(old) >= self.KEEP else []:
                os.remove(os.path.join(LOG_DIR, f))
        except OSError:
            pass
        fname = os.path.join(LOG_DIR, time.strftime("wapow_log_%Y%m%d_%H%M%S.csv"))
        self.file = open(fname, "w", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(self.FIELDS)
        self.since_sample = 99.0
        print("logging to", fname)

    def _close(self):
        self.file.close()
        self.file = None
        self.writer = None

    def close(self):
        if self.file:
            self._close()


class Knock:
    def __init__(self):
        self.evt_t = -99.0
        self.evt = (0.0, 0.0)          # rpm, load
        self.log = []                  # newest first: (session s, rpm, load)
        self.seen = 0
        self.open = False

    def maybe_fire(self, mode, tel, now, dt, failing):
        p = 0.3 if failing else 0.09
        if mode == "RACING" and tel.load > 0.6 and random.random() < dt * p:
            self.evt_t = now
            self.evt = (tel.rpm, tel.load)
            self.log.insert(0, (now, tel.rpm, tel.load))
            del self.log[20:]

def draw_indicators(surf, y, t, now, mode, knock, tel):
    bulb = 3 < t < 4.6
    blink = int(now * 2.8) % 2 == 0
    if tel.can_live:                        # real turn-signal bits off the CAN flags byte
        left_on  = bool(tel.flags & 0x01)
        right_on = bool(tel.flags & 0x02)
    else:                                   # no CAN: fall back to the sim script
        left_on  = 7 < t < 12
        right_on = 63 < t < 67
    arrow(surf, 24, y + 5, -1, (left_on or bulb) and blink)
    arrow(surf, 52, y + 5, 1, (right_on or bulb) and blink)
    ind_chip(surf, 84, y, 56, "CEL", bulb or tel.mil, AMBER)   # real MIL via OBD
    rec = RANK[mode] >= 2 or bulb
    lab = "● LOG" if (rec and int(now * 1.5) % 2 == 0) else "LOG"
    ind_chip(surf, 148, y, 60, lab, rec, RED)
    k_age = now - knock.evt_t
    kchip = ind_chip(surf, 216, y, 74, "KNOCK", k_age < 1.0 or bulb, AMBER)
    unread = len(knock.log) - knock.seen
    if unread > 0 and not bulb:
        pygame.draw.circle(surf, RED, (288, y + 2), 9)
        text(surf, "9+" if unread > 9 else str(unread), 14, (255, 255, 255),
             center=(288, y + 2))
    if k_age < 6 and not bulb:
        text(surf, f"{int(knock.evt[0]):,} rpm · {int(knock.evt[1]*100)}% load",
             17, fade(AMBER, 0.9), midleft=(302, y + 14))
    return kchip

def draw_knock_log(surf, knock):
    if not knock.open: return
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((5, 7, 10, 200))
    surf.blit(veil, (0, 0))
    px, py, pw, ph = 262, 80, 500, 440
    pygame.draw.rect(surf, (16, 20, 29), (px, py, pw, ph), border_radius=14)
    pygame.draw.rect(surf, AMBER, (px, py, pw, ph), width=2, border_radius=14)
    text(surf, "KNOCK LOG", 26, AMBER, topleft=(px + 24, py + 22))
    text(surf, f"{len(knock.log)} events", 17, DIM, topleft=(px + pw - 120, py + 28))
    for i, h in enumerate(("TIME", "RPM", "LOAD")):
        text(surf, h, 16, DIM, topleft=(px + 24 + (0, 146, 296)[i], py + 60))
    pygame.draw.line(surf, (35, 43, 56), (px + 20, py + 82), (px + pw - 20, py + 82))
    for i, (s, rpm, load) in enumerate(knock.log[:10]):
        col = (255, 217, 161) if i < len(knock.log) - knock.seen else (139, 147, 167)
        ry = py + 98 + i * 30
        text(surf, f"{int(s // 60)}:{int(s % 60):02d}", 19, col, topleft=(px + 24, ry))
        text(surf, f"{int(rpm):,}", 19, col, topleft=(px + 170, ry))
        text(surf, f"{int(load * 100)}%", 19, col, topleft=(px + 320, ry))
    if not knock.log:
        text(surf, "No knock events this session.", 19, DIM,
             topleft=(px + 24, py + 100))
    text(surf, "tap anywhere to close", 16, DIM, center=(px + pw / 2, py + ph - 22))

# ---- settings panel (sensor selection + alarm thresholds) ------------------

class SettingsUI:
    def __init__(self):
        self.open = False
        self.page = 0

GEAR_X = 340   # fixed indicator row, clear of CEL/LOG/KNOCK and the alert-chip zone

# Settings are paged: 6 rows per screen (the panel's max), < > chips to move.
# Page 1 = the config-menu core (preset + sweeps), 2 = alarms, 3 = sensors.
SETTINGS_PAGES = [
    [
        dict(key="preset",               label="ENGINE PRESET",        kind="preset"),
        dict(key="rpm_redline",          label="RPM REDLINE",          kind="number", unit="RPM", step=100, lo=4000, hi=9000),
        dict(key="rpm_max",              label="RPM MAX (LADDER TOP)", kind="number", unit="RPM", step=250, lo=6000, hi=11000),
        dict(key="boost_lo",             label="BOOST SWEEP LOW",      kind="number", unit="PSI", step=1,   lo=-20,  hi=0),
        dict(key="boost_hi",             label="BOOST SWEEP HIGH",     kind="number", unit="PSI", step=1,   lo=5,    hi=45),
        dict(key="afr_target",           label="AFR TARGET (ELBOW)",   kind="number", unit="A/F", step=0.1, lo=10.5, hi=14.7),
    ],
    [
        dict(key="oil_temp_alarm",       label="OIL TEMP ALARM",       kind="number", unit="°F", step=5, lo=220, hi=300),
        dict(key="water_temp_alarm",     label="WATER TEMP ALARM",     kind="number", unit="°F", step=5, lo=200, hi=260),
        dict(key="oil_press_dev_alarm",  label="OIL PRESS ALARM DEV",  kind="number", unit="PSI", step=1,   lo=4,  hi=30),
        dict(key="fuel_press_dev_alarm", label="FUEL PRESS ALARM DEV", kind="number", unit="PSI", step=1,   lo=2,  hi=20),
        dict(key="fuel_press_base",      label="BASE FUEL PRESSURE",   kind="number", unit="PSI", step=0.5, lo=20, hi=80),
    ],
    [
        dict(key="wideband_sensor",      label="WIDEBAND SENSOR",      kind="choice", group="afr"),
        dict(key="oil_press_sensor",     label="OIL PRESS SENSOR",     kind="choice", group="press"),
        dict(key="fuel_press_sensor",    label="FUEL PRESS SENSOR",    kind="choice", group="press"),
        dict(key="map_sensor",           label="MAP SENSOR",           kind="choice", group="map"),
    ],
]
SET_PANEL = dict(x=170, y=48, w=684, h=506)
SET_PANEL_RECT = pygame.Rect(SET_PANEL["x"], SET_PANEL["y"], SET_PANEL["w"], SET_PANEL["h"])
ROW_H = 62
ROW_Y0 = SET_PANEL["y"] + 76
CLOSE_BTN = pygame.Rect(SET_PANEL["x"] + SET_PANEL["w"] - 96, SET_PANEL["y"] + 18, 76, 36)
RESET_BTN = pygame.Rect(SET_PANEL["x"] + 24, SET_PANEL["y"] + SET_PANEL["h"] - 56, 160, 36)
PG_PREV = pygame.Rect(SET_PANEL["x"] + SET_PANEL["w"] // 2 - 110, SET_PANEL["y"] + SET_PANEL["h"] - 58, 64, 40)
PG_NEXT = pygame.Rect(SET_PANEL["x"] + SET_PANEL["w"] // 2 + 46, SET_PANEL["y"] + SET_PANEL["h"] - 58, 64, 40)

def settings_row_rect(i):
    return pygame.Rect(SET_PANEL["x"] + 24, ROW_Y0 + i * ROW_H, SET_PANEL["w"] - 48, ROW_H - 10)

def settings_btn_rects(i):
    row = settings_row_rect(i)
    return (pygame.Rect(row.right - 220, row.y, 50, row.h),
            pygame.Rect(row.right - 50,  row.y, 50, row.h))

def cycle_choice(group, current):
    keys = list(SENSOR_PROFILES[group].keys())
    i = keys.index(current) if current in keys else 0
    return keys[(i + 1) % len(keys)]

def draw_settings(surf, settings, ui):
    if not ui.open: return
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((5, 7, 10, 200))
    surf.blit(veil, (0, 0))
    p = SET_PANEL
    pygame.draw.rect(surf, (16, 20, 29), (p["x"], p["y"], p["w"], p["h"]), border_radius=14)
    pygame.draw.rect(surf, TEAL, (p["x"], p["y"], p["w"], p["h"]), width=2, border_radius=14)
    text(surf, "SETTINGS", 26, TEAL, topleft=(p["x"] + 24, p["y"] + 22))
    pygame.draw.rect(surf, (28, 35, 48), CLOSE_BTN, border_radius=8)
    text(surf, "CLOSE", 17, TEXT, center=CLOSE_BTN.center)

    for i, row in enumerate(SETTINGS_PAGES[ui.page]):
        r = settings_row_rect(i)
        pygame.draw.rect(surf, (22, 28, 40), r, border_radius=8)
        text(surf, row["label"], 18, TEXT, midleft=(r.x + 16, r.centery))
        if row["kind"] == "preset":
            chip = pygame.Rect(r.right - 260, r.y + 6, 244, r.h - 12)
            name = settings.values["preset"]
            pygame.draw.rect(surf, (35, 43, 56), chip, border_radius=8)
            text(surf, name, 17, AMBER if name == "CUSTOM" else TEAL,
                 center=chip.center)
        elif row["kind"] == "choice":
            key = settings.values[row["key"]]
            val = SENSOR_PROFILES[row["group"]][key]["label"]
            chip = pygame.Rect(r.right - 260, r.y + 6, 244, r.h - 12)
            pygame.draw.rect(surf, (35, 43, 56), chip, border_radius=8)
            text(surf, val, 17, TEAL, center=chip.center)
            if key == "CUSTOM":       # editor not built yet — don't imply it's live
                text(surf, "uses default range — not editable yet", 12, DIM,
                     topleft=(chip.x, r.bottom + 1))
        else:
            minus, plus = settings_btn_rects(i)
            for btn, lab in ((minus, "-"), (plus, "+")):
                pygame.draw.rect(surf, (35, 43, 56), btn, border_radius=8)
                text(surf, lab, 20, TEXT, center=btn.center)
            vs = f"{settings.values[row['key']]:g} {row['unit']}"
            text(surf, vs, 18, TEAL, center=(r.right - 135, r.centery))

    pygame.draw.rect(surf, (35, 43, 56), RESET_BTN, border_radius=8)
    text(surf, "RESET DEFAULTS", 15, DIM, center=RESET_BTN.center)
    pygame.draw.rect(surf, (35, 43, 56), PG_PREV, border_radius=8)
    text(surf, "<", 24, TEXT if ui.page > 0 else (57, 66, 79), center=PG_PREV.center)
    pygame.draw.rect(surf, (35, 43, 56), PG_NEXT, border_radius=8)
    text(surf, ">", 24, TEXT if ui.page < len(SETTINGS_PAGES) - 1 else (57, 66, 79),
         center=PG_NEXT.center)
    text(surf, f"{ui.page + 1}/{len(SETTINGS_PAGES)}", 17, DIM,
         center=(SET_PANEL["x"] + SET_PANEL["w"] / 2, PG_PREV.centery))

def settings_touch(settings, ui, mx, my):
    """Handles a tap while the settings panel is open. Always returns True
    if the panel was open, so the caller knows not to fall through to
    other hit-tests underneath the panel."""
    if CLOSE_BTN.collidepoint(mx, my):
        ui.open = False
        return True
    if RESET_BTN.collidepoint(mx, my):
        settings.reset()
        return True
    if PG_PREV.collidepoint(mx, my):
        ui.page = max(0, ui.page - 1)
        return True
    if PG_NEXT.collidepoint(mx, my):
        ui.page = min(len(SETTINGS_PAGES) - 1, ui.page + 1)
        return True
    for i, row in enumerate(SETTINGS_PAGES[ui.page]):
        if row["kind"] == "preset":
            r = settings_row_rect(i)
            chip = pygame.Rect(r.right - 260, r.y + 6, 244, r.h - 12)
            if chip.collidepoint(mx, my):
                order = list(PRESETS.keys())
                cur = settings.values["preset"]
                nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else order[0]
                settings.apply_preset(nxt)
                return True
        elif row["kind"] == "choice":
            r = settings_row_rect(i)
            chip = pygame.Rect(r.right - 260, r.y + 6, 244, r.h - 12)
            if chip.collidepoint(mx, my):
                settings.set(row["key"], cycle_choice(row["group"], settings.values[row["key"]]))
                return True
        else:
            minus, plus = settings_btn_rects(i)
            val = settings.values[row["key"]]
            if minus.collidepoint(mx, my):
                settings.set(row["key"], round(clamp(val - row["step"], row["lo"], row["hi"]), 2))
                return True
            if plus.collidepoint(mx, my):
                settings.set(row["key"], round(clamp(val + row["step"], row["lo"], row["hi"]), 2))
                return True
    return SET_PANEL_RECT.collidepoint(mx, my)   # swallow taps on empty panel space

# ---- tap-to-arm, tap-to-exit ------------------------------------------------
# Two discrete taps, deliberately NOT a hold. This panel's driver only reports
# touch while it CHANGES — a finger held still stops emitting events entirely,
# so a press-and-hold gesture can never work here no matter how forgiving the
# timing is (tried it; the ring just flickers). Taps are the one thing the
# hardware does reliably. Two of them, on two different targets, is still far
# too deliberate to ever fire by accident in the car.
EXIT_CORNER = pygame.Rect(W - 110, 0, 110, 110)   # tap 1: arms
EXIT_PANEL = pygame.Rect(W - 250, 6, 242, 184)
EXIT_BTN = pygame.Rect(W - 238, 116, 218, 54)     # tap 2: confirms
EXIT_ARM_S = 5.0                                  # auto-cancel if ignored

def draw_exit_confirm(surf, armed_s, now):
    if armed_s is None:
        return
    left = max(0.0, EXIT_ARM_S - armed_s)
    pygame.draw.rect(surf, (16, 20, 29), EXIT_PANEL, border_radius=12)
    pygame.draw.rect(surf, RED, EXIT_PANEL, width=2, border_radius=12)
    text(surf, "EXIT DEMO?", 24, RED_HI, center=(EXIT_PANEL.centerx, EXIT_PANEL.y + 30))
    text(surf, "tap the button below", 15, DIM,
         center=(EXIT_PANEL.centerx, EXIT_PANEL.y + 58))
    pulse = 0.30 + 0.22 * math.sin(now * 6)
    pygame.draw.rect(surf, fade(RED, pulse), EXIT_BTN, border_radius=10)
    pygame.draw.rect(surf, RED, EXIT_BTN, width=2, border_radius=10)
    text(surf, "EXIT", 26, (255, 255, 255), center=EXIT_BTN.center)
    text(surf, f"tap anywhere else to cancel · {left:.0f}s", 13, DIM,
         center=(EXIT_PANEL.centerx, EXIT_PANEL.bottom - 16))


_ip_cache = ["", 0.0]
def local_ip():
    """This machine's LAN IP, cached, re-checked every 10s (hotspots deal new
    ones). Shown on the PARKED screen so field SSH never needs a hunt."""
    t = time.monotonic()
    if t - _ip_cache[1] > 10:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))          # no packet sent; just picks a route
            _ip_cache[0] = s.getsockname()[0]
            s.close()
        except Exception:
            _ip_cache[0] = "no network"
        _ip_cache[1] = t
    return _ip_cache[0]


def draw_chrome(surf, y, mode, active, now):
    col = MODE_COLOR[mode]
    rect = pygame.Rect(866, y, 136, 32)
    pygame.draw.rect(surf, fade(col, 0.18), rect, border_radius=16)
    pygame.draw.rect(surf, col, rect, width=2, border_radius=16)
    text(surf, mode, 19, col, center=(934, y + 16))
    for i, al in enumerate(active):
        bx = 866 - (i + 1) * 158
        pulse = 0.5 + 0.5 * math.sin(now * 7 + i)
        br = pygame.Rect(bx, y, 148, 32)
        pygame.draw.rect(surf, fade(RED, 0.12 + 0.25 * pulse), br, border_radius=16)
        pygame.draw.rect(surf, RED, br, width=2, border_radius=16)
        text(surf, "! " + al["label"], 17, RED_HI, center=(bx + 74, y + 16))
    text(surf, "WAPOW", 16, (60, 68, 84), topleft=(20, H - 22))


# ============================ main ==========================================

def main():
    tel = Telemetry()

    def _graceful(sig, frm):
        # SIGTERM (our own pkill-heavy dev loop included) must close the OBD
        # socket: the MX+ wedges baseband-deaf if its host vanishes silently,
        # and only a power-cycle un-wedges it. Say goodbye, then exit.
        try:
            if tel.obd.sock:
                tel.obd.sock.close()
        except Exception:
            pass
        os._exit(0)
    signal.signal(signal.SIGTERM, _graceful)

    if not SNAPSHOT:
        play_splash()               # 10 s of splash = 10 s for CAN/OBD to warm up

    modes = ModeEngine()
    alerts = AlertEngine()
    layout = Layout()
    knock = Knock()
    settings_ui = SettingsUI()
    logger = Logger()
    peaks = Peaks()
    prev_mode = "PARKED"
    tap_t = {}                  # per-tile last tap time (double-tap detect)
    peek_until = {}             # per-tile peak-peek deadline
    # peak-store key -> layout rect key, for tap hit-testing
    TILES = dict(oilP="oilP", fp="fuelP", coolant="coolant",
                 oilT="oilT", boost="boost", afr="afr",
                 fuel="fuel", eth="eth", rpm="rpm")
    trail = []
    trail_tick = 0.0

    start = time.monotonic()
    session0 = time.monotonic()
    force_next = False
    last_t = 0.0
    exit_armed = None           # when the corner was tapped; None = not armed
    setup_ok = True             # settings access; recomputed every frame

    def jump(sec, fail=False):
        nonlocal start, force_next
        start = time.monotonic() - sec
        tel.fail_until = sec + 16 if fail else -1.0
        force_next = True

    snap_times = []
    if SNAPSHOT:
        random.seed(3)
        snap_times = sorted(float(x) for x in SNAPSHOT.split(","))
        fail_wanted = any(x > 48 for x in snap_times)
        sim_t = 0.0

    running = True
    while running:
        if SNAPSHOT:
            dt = 1 / 50
            sim_t += dt
            t = sim_t % DUR
            now = sim_t
            if fail_wanted and sim_t >= 46 and tel.fail_until < 0:
                tel.fail_until = 62
            if not snap_times:
                break
        else:
            dt = clamp(clock.tick(50) / 1000, 0.001, 0.1)
            now = time.monotonic() - session0
            t = (time.monotonic() - start) % DUR

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        running = False
                    if e.key == pygame.K_1: jump(0.5)
                    if e.key == pygame.K_2: jump(17)
                    if e.key == pygame.K_3: jump(30)
                    if e.key == pygame.K_4: jump(48)
                    if e.key == pygame.K_5: jump(46, fail=True)
                if e.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = e.pos
                    # Exit is checked first, so it works even with a panel open.
                    if exit_armed is not None:
                        if EXIT_BTN.collidepoint(mx, my):
                            running = False
                        else:
                            exit_armed = None     # anything else = cancel
                    elif EXIT_CORNER.collidepoint(mx, my):
                        exit_armed = now
                    elif settings_ui.open:
                        settings_touch(SETTINGS, settings_ui, mx, my)
                    elif knock.open:
                        knock.open = False
                        knock.seen = len(knock.log)
                    else:
                        iy = layout.cur["rpm"]["y"] + layout.cur["rpm"]["h"] + 12
                        if 216 <= mx <= 298 and iy - 6 <= my <= iy + 34:
                            knock.open = True
                        elif (setup_ok and GEAR_X <= mx <= GEAR_X + 70
                              and iy - 6 <= my <= iy + 34):
                            settings_ui.open = True
                        else:
                            # Double-tap any gauge tile -> 3s peak peek. The
                            # 0.08-0.45s window rejects the panel's tap bursts
                            # (sub-100ms) and slow re-taps alike.
                            for gk, rk in TILES.items():
                                gr = layout.cur.get(rk)
                                if (gr and gr["a"] > 0.1
                                        and gr["x"] <= mx <= gr["x"] + gr["w"]
                                        and gr["y"] <= my <= gr["y"] + gr["h"]):
                                    if 0.08 < now - tap_t.get(gk, -99) < 0.45:
                                        peek_until[gk] = now + 3.0
                                    tap_t[gk] = now
                                    break

            if exit_armed is not None and now - exit_armed > EXIT_ARM_S:
                exit_armed = None                 # ignored — forget about it

        wrapped = t < last_t
        last_t = t
        if not SNAPSHOT:
            # Every demo lap includes the failure episode (Ty 7/17 — the
            # triage should show itself off without needing a key press).
            if wrapped:
                tel.fail_until = -1.0
            if t >= 46 and tel.fail_until < 0:
                tel.fail_until = 62.0
        tel.update(t, dt)
        failing = t < tel.fail_until
        modes.update(tel, dt, force=(wrapped or force_next))
        force_next = False
        alerts.update(tel, dt)
        act = alerts.active()
        layout.update(dt, modes.mode, act)
        knock.maybe_fire(modes.mode, tel, now, dt, failing)
        if prev_mode == "PARKED" and modes.mode != "PARKED":
            peaks.reset()                     # new drive session -> fresh peaks
        prev_mode = modes.mode
        peaks.update(oilP=tel.oilP, boost=tel.boost, coolant=tel.coolant,
                     oilT=tel.oilT, afr=tel.afr, fp=tel.fp, rpm=tel.rpm,
                     fuel=tel.fuel, eth=tel.eth)
        if not SNAPSHOT:
            recording = RANK[modes.mode] >= 2         # matches the LOG indicator's own rule
            logger.update(recording, now, t, modes.mode, tel, dt)

        trail_tick += dt
        if trail_tick > 0.06:
            trail_tick = 0.0
            trail.append((tel.gx, tel.gy))
            del trail[:-42]

        # ---- draw ----
        screen.fill(BG)
        cur = layout.cur
        draw_rpm(screen, cur["rpm"], tel, now,
                 peak=peaks.get("rpm", 0), peek=now < peek_until.get("rpm", -99))
        draw_gcircle(screen, cur["gcircle"], tel, trail)
        draw_speed(screen, cur["speed"], tel)
        # Fixed-range gauges: nominal value pinned at the bend (pct 45).
        def _rng_pct(v, lo, nom, hi):
            if v <= nom:
                return 45 * clamp((v - lo) / max(1e-6, nom - lo), 0, 1)
            return 45 + 55 * clamp((v - nom) / max(1e-6, hi - nom), 0, 1)
        # Deviation gauges: nominal = whatever is expected right now.
        def _dev_pct(v, exp):
            if exp < 5:
                return clamp(v, 0, 100) * 0.45
            if v <= exp:
                return 45 * v / exp
            return 45 + 55 * (v - exp) / max(5.0, 100 - exp)
        def tile(key, rkey, val, label, unit, pct_fn, hot, dec=0, nom=True):
            """Draw one gauge tile, handling peak-peek and fault state."""
            if rkey in tel.fault:
                draw_tile(screen, cur[rkey], 0, label, unit, 0, now, fault=True)
                return
            pkv = peaks.get(key, val)
            peeking = now < peek_until.get(key, -99)
            v = pkv if peeking else val
            draw_tile(screen, cur[rkey], v, label, unit, pct_fn(v), now,
                      hot=hot, peak_pct=pct_fn(pkv), peek=peeking, dec=dec, nom=nom)
        tile("coolant", "coolant", tel.coolant, "WATER", "°F",
             lambda v: _rng_pct(v, 120, 190, 260),
             tel.coolant >= SETTINGS.water_temp_alarm)
        tile("oilT", "oilT", tel.oilT, "OIL TEMP", "°F",
             lambda v: _rng_pct(v, 140, 215, 300),
             tel.oilT >= SETTINGS.oil_temp_alarm)
        # Oil press: the BAR sweeps RAW psi (Ty 7/18 — deviation-as-position
        # is a math channel for log analysis, not a driver aid; the driver's
        # bar shows where the value actually is). Deviation still drives the
        # ALARM. Bend = fixed typical-healthy 50 psi until presets land.
        tile("oilP", "oilP", tel.oilP, "OIL PRESS", "PSI",
             lambda v: _rng_pct(v, 0, 50, 100),
             tel.oilDev < -SETTINGS.oil_press_dev_alarm)
        # Fuel press: raw bar too; bend = base pressure, so boost-referenced
        # rise wraps visibly along the top. Alarm stays deviation-driven.
        tile("fp", "fuelP", tel.fp, "FUEL PRESS", "PSI",
             lambda v: _rng_pct(v, 0, SETTINGS.fuel_press_base, 100),
             tel.fpDev < -SETTINGS.fuel_press_dev_alarm)
        # Boost: the bend = atmospheric (0 psi). Vacuum lives on the left
        # edge, boost wraps the top — the corner is the spool-over point.
        tile("boost", "boost", tel.boost, "BOOST", "PSI",
             lambda v: _rng_pct(v, SETTINGS.boost_lo, 0,
                                max(SETTINGS.boost_hi, SETTINGS.boost_lo + 1)),
             tel.boost > max(1.0, SETTINGS.boost_hi), dec=1)
        # AFR: bend = 12.0, Ty's target under load (7/17) — parked at the
        # corner mid-pull means on target. Leaner wraps past the bend toward
        # the lean alarm; cruise stoich sits well along the top, teal.
        tile("afr", "afr", tel.afr, "AFR", "A/F",
             lambda v: _rng_pct(v, 10, SETTINGS.afr_target, 18),
             tel.load > 0.55 and tel.afr > 13.2, dec=1)
        # Fuel + ETH: same tile style at ~0.45x scale (Ty asked ~1/3;
        # 0.45 keeps the digits arm's-length legible). Fuel's bend = the
        # reserve line (25%): a full tank rides the top edge and retreats
        # toward the corner as it burns — below the bend means reserve.
        tile("fuel", "fuel", tel.fuel, "FUEL", "%",
             lambda v: _rng_pct(v, 0, 25, 100), tel.fuel < 10)
        # ETH is a composition readout, not health-vs-nominal — it sweeps
        # LINEARLY along the whole path, no nominal band (Ty 7/17).
        tile("eth", "eth", tel.eth, "ETH", "%",
             lambda v: clamp(v, 0, 100), False, nom=False)
        iy = cur["rpm"]["y"] + cur["rpm"]["h"] + 12
        draw_indicators(screen, iy, t, now, modes.mode, knock, tel)
        draw_chrome(screen, iy, modes.mode, act, now)
        setup_ok = modes.mode == "PARKED" or not tel.real_speed
        if setup_ok:
            ind_chip(screen, GEAR_X, iy, 70, "SETUP", True, DIM)
        if modes.mode == "PARKED":
            text(screen, local_ip(), 15, DIM, topleft=(W - 150, H - 22))
        draw_knock_log(screen, knock)
        draw_settings(screen, SETTINGS, settings_ui)
        draw_exit_confirm(screen, None if exit_armed is None else now - exit_armed, now)
        pygame.display.flip()

        if SIM_RIG and SIM_RIG.restart_requested:
            # Sim-rig restart: relaunch this same script as a fresh process
            # (full boot, splash and all), then vanish. subprocess handles
            # the quoting that os.execv fumbles on Windows paths with spaces.
            logger.close()
            try:
                if tel.obd.sock:
                    tel.obd.sock.close()
            except Exception:
                pass
            pygame.quit()
            kw = {}
            if os.name == "nt":
                # The new dash must NOT share this console: when the
                # launching .bat exits it closes the console window, and
                # Windows kills every process still attached to it — the
                # restarted dash included (crashed exactly that way 7/20).
                kw["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen([sys.executable, os.path.abspath(__file__)], **kw)
            os._exit(0)

        if SNAPSHOT and snap_times and sim_t >= snap_times[0]:
            fname = f"wapow_frame_{snap_times.pop(0):.0f}.png"
            pygame.image.save(screen, fname)
            print("saved", fname)

    logger.close()
    pygame.quit()

if __name__ == "__main__":
    main()
