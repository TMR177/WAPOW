# WAPOW — Adaptive Racing Display

**The best racing dash you can build yourself.**

Every race dash shows you everything, all the time. Your eyes don't
work that way — at speed you get glances, not looks. WAPOW watches how
you're driving (G-forces, RPM, speed) and reprioritizes the screen:
calm on a cruise, focused when you're pushing, loud only when
something's actually wrong.

Free to build, forever. GPL-3.0. Built in a garage, documented as it
happens.

## How it works

Four driving modes — **PARKED / CRUISING / SPIRITED / RACING** — with
two rules that drive everything:

- **Escalate fast, de-escalate slow.** Mode upgrades are instant (the
  driver is busy); downgrades take sustained calm. The layout never
  moves unless you need to look.
- **Sentinel gauges.** Readings that only matter when they're wrong
  (oil pressure, fuel pressure) live small and quiet — and seize the
  screen the moment they leave normal. Multiple alerts triage
  automatically by severity.

Full design rules and decisions: [`wapow_spec.md`](wapow_spec.md).

## Hardware

| Part | Role |
|---|---|
| Raspberry Pi 5 + 7" 1024×600 touchscreen | display + logic (pygame, 50 fps) |
| Teensy 4.1 | fast acquisition: RPM from ignition, 0–5 V analog senders |
| CAN bus (SN65HVD230 transceivers, 500 kbps) | Teensy → Pi data link |
| LSM6DSOX IMU | G-forces → driving-context detection |
| OBD-II Bluetooth (ELM/STN) | slow engine data from the stock ECU |

Data sources are swappable classes — the display never knows where data
comes from, and everything falls back to a scripted sim so you can run
the full dash on any PC with zero hardware:

    py -3.10 wapow_dash.py        (Windows: run wapow_demo.bat)

Build documents: [`materials_list.md`](materials_list.md) ·
[`wapow_board_sheet.pdf`](wapow_board_sheet.pdf) ·
[`wapow_can_wiring.pdf`](wapow_can_wiring.pdf) ·
[`wapow_shopping_list.pdf`](wapow_shopping_list.pdf) ·
[`sensor_reference.md`](sensor_reference.md)

## Status

Bench prototype is alive: dash + sim + IMU + CAN + OBD all working;
soldered car-install boards are mid-build; first in-car install is
next. The build is documented on
[YouTube](https://youtube.com/@wapowlabs) and in the
[Build Log](https://wapowlabs.com/#build-log) (email, sent when the
build earns an issue).

## Links

- Site + live lap demo: [wapowlabs.com](https://wapowlabs.com)
- Full parts list: [wapowlabs.com/parts](https://wapowlabs.com/parts)
- Videos: [youtube.com/@wapowlabs](https://youtube.com/@wapowlabs)
- Found value in this? Tip jar:
  [ko-fi.com/wapowlabs](https://ko-fi.com/wapowlabs) ·
  [GitHub Sponsors](https://github.com/sponsors/TMR177)

## Contributing

The plan is for WAPOW to grow with its community — more vehicles, more
CAN profiles, eventually community-designed hardware. Issues and PRs
welcome; if you build one, show us.

## License

[GPL-3.0](LICENSE). The build is free, forever — sell of assembled
units by the project funds development; the plans never go behind a
paywall.
