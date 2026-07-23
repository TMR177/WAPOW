# Materials List — two-board build + enclosure (v2 sheet)

Compiled 7/19. Companion to `wapow_board_sheet.pdf`. Enclosure prints
in Fibreon PA612-CF15 (heat-set inserts are the fastener strategy).

**ORDERED 7/20 (Ty)** — the build shopping list below is purchased.
**IN HAND 7/20 (local shop run, photo-verified):** 4x perfboard (A, B,
2 spares), female header strips x7, 2x20 IDC box header, screw
terminals (2-pos + 3-pos), ceramic cap tape, M2.5x10 + M3x14.5
standoffs. Bonus pickups: **6x 1N5818 Schottky** (use: reverse-polarity
protection ahead of the Pololu buck, and/or input clamps) and a
**DL507 7-segment display** (unassigned). Still shipping: hookup wire,
heat-set inserts, Pi 5 active cooler, fuse holder/XT30/ring terminals.
While the rest ships: bench-test the UNTESTED Pololu buck.

## Already owned — verify on the bench before shopping

- [ ] Pi 5 (4GB) + 7" 1024x600 touchscreen
- [ ] Teensy 4.1
- [ ] MCP2515 module (the transplant, with tack wires) + 2x SN65HVD230
- [ ] LSM6DSOX IMU breakout
- [ ] Resistor kit (2.2k / 3.3k for dividers) + zener kit (future clamps)
- [ ] Potentiometer (bench stand-in sender)
- [ ] Cobbler RIBBON cable (the cobbler PCB itself retires)
- [x] Pololu D24V50F5 buck (12V -> 5V 5A) — TESTED 7/20: 5.02V rock-steady no-load AND under full dash load (M12 pack input, 11.9V). Breadboard/cobbler path drops 0.52V (Pi saw 4.5V + undervolt warning) — the soldered build is the fix, buck itself is car-worthy
- [ ] OBDLink MX+ (stays in the car, wireless)
- [ ] USB micro cable Pi -> Teensy (the one in use)

## Buy now — board build (~$45-65 total)

| item | qty | ~$ | notes |
|---|---|---|---|
| FR-4 perfboard, double-sided plated-through, ~7x9cm | 3-pack | 8 | Board A, Board B, one spare/mistake |
| Screw terminal blocks, PCB-mount, 3.5mm or 5.08mm pitch | ~20 positions | 8 | interlocking 2/3-pos strips; Board B needs 12+, CAN bus 2 per board |
| Female header socket strips (2.54mm, cuttable) | 10-strip kit | 8 | SOCKET the Teensy, MCP2515 module, and both SN65HVD230s — nothing expensive gets soldered directly |
| 2x20 IDC box header (ribbon landing, Board A) | 1 | 2 | or skip and solder the ~9 ribbon cores direct (free) |
| Hookup wire, 22-24 AWG solid (board) + stranded (pigtails) | assortment | 10 | skip if the bins have it; twist own CAN pair from stranded |
| Brass standoff/screw kit, M2.5 + M3 | kit | 10 | Pi mounts M2.5; boards + Teensy M3 |
| Heat-set threaded inserts, M3 (+ some M2.5) | kit | 12 | THE fastener for PA612-CF15; install with soldering iron (insert tip optional) |
| Pi 5 official active cooler | 1 | 6-10 | non-negotiable in a sealed box in a car |
| 100nF ceramic caps | 10+ | 3 | one per divider output — cheap insurance, might as well now |

## Buy now or very soon — power + car interface (~$15-25)

| item | qty | ~$ | notes |
|---|---|---|---|
| Inline blade fuse holder + 5A fuses | 1 + spares | 6 | between car 12V and the Pololu |
| Connector for 12V input (XT30, or barrel pair) | 1 pair | 4 | bench PSU today, car harness later, same plug |
| Ring terminals / crimp assortment | small kit | 6 | 12V pickup + grounds at install |
| Zip ties, adhesive tie mounts, heat shrink | — | — | probably owned; strain relief is a checklist item |

## Deferred — buy when its build starts

- AEM 30-2012 oil temp sender (~$45) — thermistor/curve build
- u-blox GPS module, 10-25Hz (~$40) — GpsSource / lap timing / track map
- Deutsch DT 12-pin bulkhead kit — car harness phase (pin map already reserved on the board sheet)
- UVC camera with onboard H.264 — video phase
- Ignition-sense / clean-shutdown parts — decide circuit first (before real driving)
- ~~deferred~~ **PROMOTED to this build 7/20** (Ty's call, correct: this
  build IS the in-car build, and clamps exist for in-car failure modes —
  a sender wire chafed onto 12V puts 7.2V through the divider onto a
  3.3V-max pin). **Input-clamp diodes: BAT85 × 12** — two per channel
  (node→3.3V rail, node→GND) for 5 sensor channels + the 5V-rail ref.
  Counter-shop ask: **"BAT85, small-signal Schottky, axial glass
  package — like a 1N4148 but Schottky."** (Alt: 1N5711.) Do NOT ask
  for BAT54S — that's the SMD version; counters sub power schottkys and
  confusion ensues (proven 7/20; the subbed 1N5818s were reassigned to
  reverse-polarity duty). Board B layout reserves the 12 positions so
  assembly needn't wait on the diodes — solder them in when they arrive,
  before the car install.

## Enclosure design notes (PA612-CF15)

- Heat-set M3 inserts for lids and board mounts; no self-tapping into CF nylon
- Pi 5 + active cooler needs intake/exhaust vents — grille the print, don't seal it
- IMU (Board A) mounts flat and rigid to the enclosure floor; mark orientation on the print
- Connector face: terminal-block access now, a blank panel area sized for the future Deutsch DT bulkhead
- Screen is a separate mounting problem from the electronics box — cable between them
- SD card and both USB runs reachable without full disassembly
