# WAPOW — Product Spec (Living Document)

*v0.5 — July 14, 2026. This document changes as decisions are made. Nothing here is final until it ships.*

> **Product name (decided 7/19, Ty): WAPOW** — *Windowed Adaptive
> Performance Optimization Widget*, pronounced "Wah Pow!". Supersedes the
> TrackDancer working name; the full rename (files, repo, Pi paths, env
> vars) was executed 7/19. All public-facing material (channel, handles,
> hardware branding) uses WAPOW. Handle/domain plan: see
> `content_playbook.md`.

## Vision

An adaptive racing dashboard that works like a co-driver, not a gauge cluster. Traditional dashes treat all data equally; driver attention doesn't work that way. WAPOW senses driving context (G-forces, RPM patterns, speed) and reprioritizes the display so the right information is prominent at the right moment — calm and minimal on the commute, focused and data-rich when driving gets serious, and alarmed only when something is genuinely wrong.

Open source (GPL v3). Revenue from selling assembled, tested units. Target retail $799–1,099.

### Who the open-source build is for (Ty, 7/22 - the docs' north star)

> "This is not for the faint of heart, but it IS for the inexperienced.
> I want people who never thought they could do this - like me - to do it."

Every build sheet, warning, and guide chapter is written to that standard:
nothing assumed, nothing abbreviated when it matters, mistakes documented
honestly (the failures are the best teachers). A first-timer with a
multimeter, patience, and this documentation should succeed.

### Product line — two models (direction set 7/20, Ty)

- **Base**: 7" 1024x600 touch, core adaptive gauge set, OBD + IMU + one
  DAQ node's worth of analog inputs. For buyers who won't use every
  input. Entry price point (lower end of / below the target range).
- **Pro**: panoramic screen (12.3"-class automotive ultrawide), full
  input complement, GPS/track map, camera sync, expansion nodes (shock
  pots, tire temps). The MoTeC/AIM competitor. Upper price point.
- **One codebase, two hardware bundles — never a software fork.** The
  layout dealer computes against screen size, and signal suppression
  means fewer inputs simply deal fewer gauges. The same distributed-CAN
  design makes the upgrade path real: a Base owner adds nodes (and
  eventually the bigger screen) and grows toward Pro — hardware
  expansion, not license unlocks. That's the open-source counterpunch to
  the MoTeC model where features ship dark and cost thousands to enable.

### Publicity & monetization (decided 7/23, Ty)

- **The DIY build is free, forever** (GPL v3 + the free build guide) -
  that IS the marketing. DIYers evangelize; non-builders buy assembled
  units. The two personas don't cannibalize.
- **Tip rails**: GitHub Sponsors (FUNDING.yml on the repos - the maker
  tip jar) + Ko-fi (zero-fee tips for everyone else). Public framing is
  **"if you found value in this"** (Ty's wording 7/23 - the canonical
  CTA phrase, used verbatim in buildlog_style.md); expected to be beer
  money - their real value is social proof and community.
  Memberships/Patreon: only if demand appears later.
- **Newsletter: "WAPOW Build Log"** - prose version of the build's
  standup board (what shipped, what broke, what's next). Cadence
  (Ty, revised 7/23): **earned, not scheduled** - no public frequency
  promise anywhere; public phrase is "issues go out when the build
  earns one." Internal goals only: ~monthly at build pace, plus a short
  subscriber check-in if ~8 weeks go quiet (keeps the list warm). The
  email list is the only owned audience channel; collect from now so
  launch lands on warm inboxes. Website dept owns platform + signup;
  content dept owns voice + issues + video CTAs.
- Tax note: tips are personal taxable income until a WAPOW Labs entity
  exists; keep records.

## Display Principles (the rules everything obeys)

1. **Motion means meaning.** The layout never moves unless the driver needs to look. Unnecessary movement is a distraction.
2. **Escalate fast, de-escalate slow.** Entering a more aggressive mode is instant (the driver is busy — surface the info now). Dropping back down requires sustained calm driving (currently 6 s per level, to be tuned from the driver's seat).
3. **Deviation drives the alarms; the driver's bar shows the raw value.** *(Amended 7/18, Ty's call — supersedes the original "show deviation, not raw values" visual.)* Oil pressure normally tracks RPM, so the ALARM fires on deviation-from-expected-at-this-RPM, never on a fixed number — that logic stands. But deviation-as-bar-position turned out to be "a math channel for investigating in a data log program, not a driver aid": on the bench a steady real pressure made the bar dance as expected-RPM swept, and mid-drive a driver needs the needle where the value is. So the bar sweeps the raw value (bend = a fixed nominal, e.g. 50 psi oil, base pressure for fuel), while the deviation math runs invisibly underneath and seizes the display only when it trips.
4. **Alerts outrank everything.** A critical vital seizes screen priority in any mode, with hysteresis (e.g., oil temp trips at 260°F, clears at 250°F) so alerts don't flicker.
5. **RPM stays peripheral-readable.** Full-width tach at top; recognized without focusing on it. *(Restyled again 7/18, Ty's call: a **48-segment ladder** — thin tall cells whose discreteness reads in pure peripheral vision. Scale: 400–4,000 rpm owns the first ⅓ of the ladder, 4,001–9,000 the remaining ⅔, so the shift-decision band gets the real estate. Colors are anchored to rpm values (teal to 5,000, bending through lime/yellow/amber, red at 7,000) — not bar position — so preset-configurable sweep limits can't break their meaning. Unlit redline cells keep a dark red tint. Shift light: above 6,500 the whole lit ladder slams red at 4 Hz. Digits stand alone left of the ladder, yellow, going red at redline; no "RPM" label.)*
6. **Indicators live in fixed positions.** Turn signals, CEL, knock, logging status never move — glanceable by habit.
7. **Sentinel gauges.** Gauges whose reading is only interesting when abnormal (oil pressure, fuel pressure) live small in a fixed home row. They enter the main view only when the reading leaves expected operation. *(Amended 7/13: AFR was a sentinel, but is promoted to a full priority gauge in SPIRITED and RACING — under load is exactly when AFR matters. It stays a sentinel in PARKED/CRUISING.)*
8. **Multi-alert triage.** Multiple simultaneous alerts each claim a main-view slot (1 large / 2 medium / 3 smaller), ordered by severity (oil pressure > fuel pressure > oil temp > AFR lean). Non-critical info dims or hides — when things go wrong, remove noise. Every active alert also gets a banner chip; alerts beyond three stay bannered until a slot frees up. Alert triggers use hysteresis plus a short dwell where transients cause false blips (AFR lean requires 0.25 s sustained, so a boost-ramp blip doesn't fire it; oil/fuel pressure alerts stay instant).
9. **Touch is taps only.** (Hardware constraint, found 7/14.) The panel reports touch only while it changes — a still finger emits nothing — so press-and-hold gestures are unbuildable on this display. Any touch interaction must be discrete taps. Where an action needs to be deliberate (e.g. quitting), use two taps on two separate targets rather than a hold.
10. **Size and location signal priority — not brightness.** (Decided 7/13.) Nothing is dimmed in normal driving; every visible gauge renders at full brightness, and importance is communicated by how big it is and where it sits. Alert mode is the one exception: color and brightness escalate there. SPIRITED/RACING arrange on a rule-of-thirds grid — G-circle left, temps (water/oil) stacked center, performance (boost/AFR) stacked right, secondary readouts (MPH, ETH%, fuel) in a bottom band. MPH is dominant in CRUISING but drops to the bottom band in SPIRITED+. *(PARKED still uses the old dim-based styling — conversion not yet decided.)*

## Gauge Tile Design — corner-sweep tiles (decided 7/17)

Replaces the circular arc gauges (Ty: round faces waste their centers and corners). Every gauge is a **rectangular tile**; the RPM bar keeps its full-width top-bar treatment per rule 5.

- **The bar:** a thick (~13 px at 1×, rounded caps) sweep bar runs **up the tile's left edge and bends through a rounded corner (~22 px radius) across the top edge**. One continuous stroke; the fill advances along it like fluid in a channel.
- **Nominal rides the bend.** A brighter track segment straddling the corner marks the normal operating zone. Healthy = fill parked at the corner, motionless (rule 1). Below nominal = fill partway up the left edge; above = wrapped along the top. **Deviation-from-nominal is the geometry itself** — the distance past the bend is the severity, readable peripherally (rule 3 made visual).
- **Scale mapping:** each gauge pins its nominal zone at ~45% of bar travel. The ranges on either side are per-gauge config (ties into presets/sweep-limits). Deviation gauges (oil/fuel press) center the bend on *expected*; fixed-range gauges (temps) place their normal band there.
- **Typography:** digits dominate the tile (~88 px at 1×, tight tracking), label bottom-left (~24 px), units small and muted. Everything legible at arm's length.
- **Alarm state:** fill and digits and label go red, tile border reddens; the fill wrapped deep past the bend shows *how far* out of range, not just that it is.
- **Peak hold:** a small white dot sits on the track at the session peak. **Double-tap a tile** → bar *and* digits jump to the peak state in **amber** (not red — amber = information) with a PEAK tag for 3 s, then auto-return to live. Amber chosen so peek can never be mistaken for an alarm. Double-tap detection needs an 80–450 ms window between taps (the panel fires sub-100 ms tap bursts; see rule 9).
- **Peak reset:** when the car leaves PARKED (session-based). *Ty: fine for now, revisit.*
- **Adaptive layout unchanged underneath:** tiles are the *skin*; mode layouts, sentinel promotion, and multi-alert triage still drive size/position. A promoted gauge is the same tile spanning a larger cell with scaled-up bar and digits.
- **Alert triage is computed, never hand-placed (7/17).** Alerted gauges (up to 3, severity order) are dealt 2-row spans across the top of a 12-column grid — half-width for one, halves for two, thirds for three — and surviving gauges flow into the remaining cells; noise (G-circle, fuel, ETH) hides. Overlap is impossible by construction; all 56 mode × alert combinations are verified programmatically. The demo loop triggers a failure episode every lap so the triage demonstrates itself.
- **Linear readouts skip the bend semantics (7/17).** ETH sweeps linearly with no nominal band — composition isn't health. Fuel keeps a bend at the reserve line (25%): full rides the top edge, burning retreats toward the corner, below the bend = reserve. Fuel + ETH render as mini tiles at ~0.45× of the main tiles.
- **SENSOR FAULT state (7/17).** A 0.5–4.5 V sender reading below ~0.25 V or above ~4.75 V is an open or shorted wire, not data. The tile renders amber-bordered "— —" with a SENSOR FAULT tag, and the reading is gated out of the pressure alarms in both directions — a failed sender can neither raise an alarm nor hold a real one frozen. A $2 connector must never impersonate a dead engine, and must never train the driver to distrust the alarms. *(Limitation: full-range 0–5 V outputs like the wideband's analog can't be fault-detected this way — 0 V is a legitimate reading. One more argument for MTS serial.)*

## Driving Modes

| Mode | Trigger (current values — tune from seat time) |
|---|---|
| PARKED | speed < 3 mph and RPM < 1,200 |
| CRUISING | default |
| SPIRITED | recent-G envelope > 0.50 g or RPM > 4,300 |
| RACING | recent-G envelope > 0.95 g or RPM > 6,600 |

G envelope: decaying max of combined lateral/longitudinal G, ~2 s memory.

## Gauge Spec (v0.2 gauge set)

| Gauge | Data source | Notes |
|---|---|---|
| Water temp | OBDLink MX+ | standard PID |
| Speed (MPH) | OBDLink MX+ | GPS later for accuracy |
| Check engine light | OBDLink MX+ | MIL status PID |
| RPM + shift light | Teensy ← ignition signal | fast path; OBD too slow |
| Vac/Boost | On-board 4-bar sensor (hose) **or** external MAP → Teensy analog | user-selectable source, see below; OBD MAP too slow for boost |
| Oil temp | Dedicated sender → Teensy analog | no stock sender on GC chassis |
| Oil pressure | Dedicated sender → Teensy analog | displayed as deviation-from-expected |
| Fuel level | Car's sender → Teensy analog | noisy; heavy software smoothing |
| Ethanol % | Flex fuel sensor (GM) → Teensy | frequency output, ~$60 part |
| AFR | Wideband controller → 0–5 V → Teensy | AEM/Innovate class, ~$200; sentinel in PARKED/CRUISING, full gauge in SPIRITED+ |
| Fuel pressure | Dedicated sender → Teensy analog | sentinel gauge; expected = base + boost (manifold-referenced) |
| Knock light | Subaru-specific OBD (knock correction) | instant flash + event tagged with RPM + load; tappable knock log with unread-count badge |
| Datalog indicator | Software | auto-log at SPIRITED and above — implemented: CSV at 20 Hz, all channels, one file per run, `logs/` next to the app |
| Turn signals | 12 V taps → protection circuit → Teensy digital | fixed position |

## Sensors On Hand (Ty's inventory, 7/15)

The Impreza is **already instrumented** — most of what earlier drafts listed as "still to buy" already exists on the car. Ty expects it running around when the dash is ready for in-car testing.

**Innovate ECF-1** — a 52 mm 4-in-1 gauge doing **wideband AFR, ethanol content, fuel pressure, and fuel temp**. Two ways to get data out of it:
- **4 configurable analog outputs (0–5 V)** — works with the architecture already built (divider → profile → gauge). Each output's channel and range is programmable on the gauge.
- **MTS serial** (Innovate's own bus) — one wire, all four channels, digital. No dividers, no ADC, no double conversion (their DAC → our ADC), and better accuracy. Costs implementing the MTS protocol on the Teensy.

ECF-1 ranges: AFR 7.4–22.4 (0.5–1.5 λ) · ethanol 0–100% · fuel pressure **0–145 PSI (10 bar)** · fuel temp −40 to 257 °F.

Notes:
- **The existing `INNOVATE_LC2` profile already fits the ECF-1's AFR** (7.35–22.39 vs 7.4–22.4 — it's Innovate's standard 0–5 V mapping). No work needed for that channel on the analog path.
- **Fuel pressure at 0–145 PSI matches no current profile.** Either program the gauge's analog out to a range we have, or add a 145 PSI profile.
- **The ECF-1 reads the ethanol sensor itself**, so we don't need the Teensy to frequency-count a GM flex-fuel sensor — that requirement disappears on this car.
- **Fuel temp is a channel with no gauge** — see Open Items.

**Linear pressure senders, 0–100 PSI 0–5 V** — Ty has spares. `PSI_100` already covers these exactly. Earmarked for **oil pressure**; a spare could do coolant pressure.

**Oil pressure sending unit** — already on the car, model not yet identified. Needs checking (see Open Items).

Still genuinely to buy: oil temp sender, MAP (or the on-board sensor), **analog input conditioning parts** (resistor kit ordered 7/15), signal-tap protection parts.

## Analog Input Conditioning (decided 7/15)

**The problem:** Teensy 4.1 analog inputs are **3.3 V max and are NOT 5 V tolerant**, but every analog sender in the gauge table above (wideband, oil press, fuel press, MAP) outputs 0–5 V. Wiring one straight to an analog pin destroys the chip. Found 7/15 while adding the first real analog input — before any sender was bought.

**The decision: a resistor divider per channel.** Two resistors, acting as a volume knob: the sender's 5 V is turned down to ~3 V so the Teensy can read it safely.

Rejected alternatives: an external 5 V ADC (MCP3208 puts 5 V on its SPI lines — that just moves the level-shift problem to the digital side, the same trap the CAN transceiver taught us; the ADS1115 avoids that but is slow and adds a chip + firmware + failure point), and op-amp buffers (solve a source-impedance problem we don't have — the senders already drive from low-impedance outputs). The Teensy has 18 unused ADC channels. Dividers are also what production motorsport ECUs do, so this stays correct on the PCB.

**Values (per channel):** `R_top = 2.2k`, `R_bot = 3.3k` → ratio exactly **0.6**, so 5.0 V → 3.00 V, leaving 0.3 V of headroom under the limit. Thévenin ~1.3 k, which the ADC is happy with. Size for the full 0–5 V a *faulted* sender could put out, not the 0.5–4.5 V it should.

**⚠ Ratiometric — the part that actually matters.** These senders don't report "50 PSI", they report *a fraction of their own 5 V supply*. If the 5 V rail sags, the sender's output sags with it and the Teensy — referenced to its own 3.3 V — reads a pressure drop that never happened. **On the oil-pressure channel a drifting rail looks exactly like an oil-pressure fault**, i.e. the highest-severity alarm in the system telling the driver to shut down for nothing.

Fix: run **one spare ADC channel through an identical divider to the 5 V rail itself**, and compute `sensor ÷ rail` rather than `sensor ÷ 3.3 V`. Supply drift cancels. Costs one pin and two resistors.

**For the PCB / in-car, add per channel:** 100 nF to GND after the divider (noise filtering + ADC charge reservoir), and a clamp (BAT54S dual schottky to 3.3 V/GND, or a 3.3 V TVS). The top resistor already limits fault current — short the line to 12 V and it's `(12−3.3)/2.2k ≈ 4 mA` into the clamp instead of into a dead i.MX RT. The production path puts the i.MX RT on the carrier board directly, so the same 3.3 V limit applies and this network just moves from breadboard to copper.

**Where the divider math lives:** in the **Teensy firmware's** mV conversion, **not** in the Pi's sensor profiles. The profiles describe the *sender* (an AEM X-Series is 0–5 V = 10–20 AFR regardless of our wiring), so the Teensy must undo its own divider and report **true sender volts** on the bus. Get this backwards and every profile silently reads half-scale.

## Boost Source — on-board sensor or external MAP (decided 7/15)

Two ways to get boost, **user-selectable in settings**. Same philosophy as the sender profiles: the hardware is the customer's choice, the software adapts.

**A. On-board sensor (the integrated option).** A 4-bar absolute digital pressure sensor soldered to the board, with a barbed port; the customer runs a vacuum hose from the intake manifold to the dash. Not exotic — every mechanical boost gauge ever made works this way. Talks I²C/SPI at 3.3 V, so **no divider, no ADC, no ratiometric concern** for this channel. Best story for a sold unit: it's already in the box.

**B. External MAP sender (the flexible option).** A standard automotive 0–5 V MAP in the engine bay, wired to a Teensy analog pin through the usual divider. For customers who'd rather run a wire than a hose, or who already have a MAP fitted. Profile-selectable (2/3/4-bar) like any other sender.

**Why 4-bar:** 400 kPa absolute ≈ 58 psi abs ≈ **43 psi of boost headroom**. Ty's STI motor runs ~20–25, so this leaves room for a customer with a bigger turbo rather than making us the ceiling. Costs nothing in resolution — a digital sensor's native precision (14-bit+) is far finer than the gauge needs.

**Part requirements (PCB phase):** 4-bar (≈400 kPa) **absolute**, digital output, 3.3 V, barbed port, and either oil-tolerant or protected by an inline filter/restrictor — **manifold air carries oil vapour from the PCV**, which a proper automotive MAP eats for 200k miles but a bare MEMS chip will not. Part selection happens at PCB design.

**Note it does NOT remove the divider network** — AFR, oil pressure and fuel pressure are still external 0–5 V senders. On-board MAP saves one channel, not the problem.

**Software impact:** adds a MAP-source setting (on-board / external) plus the external profile choice. The settings panel can't fit these rows without a layout change — see Open Items.

## Settings & Sensor Profiles (added 7/13)

Users pick their sensors from presets instead of editing code — the Teensy sends raw volts over CAN and the Pi applies the selected linear scaling, so swapping a sensor never needs a firmware reflash.

- **Profiles:** widebands (AEM X-Series 0–5 V = 10–20 AFR, Innovate LC-2/MTX-L 0–5 V = 7.35–22.39 AFR), pressure senders (0–100 / 0–150 / 0–200 PSI, all 0.5–4.5 V), plus a Custom slot per sensor *(currently a stub with fixed default numbers — editor UI deferred until a real odd sensor shows up)*.
- **Tunable alarms:** base fuel pressure (default 43 PSI) and the oil/fuel pressure deviation-alarm thresholds are user-settable; the same values drive both the alert triggers and the gauges' red highlight.
- **Persistence:** everything saves immediately to `settings.json` next to the app — survives power cycles, no reselect at startup.
- **Access:** SETUP chip in the fixed indicator row, visible and tappable only in PARKED (no settings access while moving). Tap-to-cycle choices, +/− steppers, reset-to-defaults.

## Datalogging (added 7/13)

Auto-records whenever the mode is SPIRITED or above (same rule as the LOG indicator): CSV, 20 Hz, all telemetry channels (rpm, speed, G, load, temps, pressures with expected/deviation, boost, AFR, eth, fuel, mode), one timestamped file per contiguous run, written incrementally so a crash loses nothing. Target viewer: MegaLogViewer HD. **Open:** how files get off the Pi — leading candidates are an SMB share for the bench era and USB-stick auto-export for trackside; decision pending.

## Architecture

- **Raspberry Pi 5** — display, mode logic, alerts, logging (Python/pygame)
- **Teensy 4.1** — timing-critical + analog/digital acquisition (RPM, boost, oil, fuel, ethanol, AFR, signals)
- **Private CAN bus** — Teensy → Pi data pipe. **Working & bench-tested 7/14** (500 kbps, bidirectional, zero bus errors). Both ends use an SN65HVD230 (3.3V transceiver). Teensy side: native FlexCAN (CAN1: TX=22, RX=23) → SN65HVD230 #1. Pi side: MCP2515 SPI controller with its onboard TJA1050 removed and replaced by SN65HVD230 #2; whole module runs at 3.3V, so SPI is native to the Pi and no level shifting is required. *(Lesson learned 7/11: clone TJA1050 transceivers do NOT reliably work at 3.3V — chip inits over SPI but bus signaling fails → bus-off; cost an evening. Fix 7/14: rather than run the MCP2515 at 5V and level-shift the SPI lines back down — which is marginal on the MCP2515's VIH — swap the transceiver so the whole bus is 3.3V. This is also the production-PCB approach. Wiring: `wapow_can_wiring.pdf` v3.)*
- **OBDLink MX+** (Bluetooth) — slow/standard engine data
- **LSM6DSOX** IMU — G-forces and yaw (mode detection)
- **VEML7700** — ambient light → display dimming
- **Distributed node architecture (decided 7/19, Ty).** The Teensy is a *satellite DAQ node*, not part of the dash box: it mounts near the sensors (engine bay side) with short analog pigtails, and only a CAN pair + power runs to the dash. Expansion = more nodes on the same bus, each with an ID block (dash DAQ: 0x100-0x1FF; node 2: 0x200-0x2FF; ...): shock-pot node (4 corners at 200 Hz ≈ +3% bus), tire-temp IR node, etc. This is the MoTeC/AIM topology — display unit + distributed I/O over CAN — and it maps 1:1 onto the product line: a dash PCB (CM5 + power + IMU + GPS + CAN) and DAQ-node PCBs (i.MX RT + conditioning + CAN) sold as expansion modules, compatible with sourceable high-grade sensors. Termination rule: 120 Ω at the two physical ENDS of the bus only; middle nodes disable theirs. Satellite nodes need local 12 V→5 V power; firmware updates via laptop-at-the-node until a CAN bootloader lands (PCB generation).
- **Cameras: USB to the Pi, never CAN.** The Pi 5 has NO hardware video encoder — camera choice must be UVC units with onboard H.264/MJPEG so the Pi only muxes compressed streams to disk. Video + high-rate logs write to USB storage, never the SD. MVP video path stays: timestamped recording, data overlay in post from the CSV; live overlay later.
- **GPS (u-blox class, 10-25 Hz, ~$40) becomes `GpsSource`** — better speed than OBD, lap timing via start/finish crossing, track position for the track map, and the sync spine for video + G-ball + datalog overlay. The single cheapest step toward the AIM/MoTeC feature set.
- Production path: custom carrier PCB + Raspberry Pi Compute Module 5; Teensy's i.MX RT processor on the DAQ-node PCB via PJRC bootloader chip. Dash PCB carries power, CAN, IMU, GPS, and the **on-board 4-bar MAP sensor + hose port** (see Boost Source); DAQ-node PCB carries the analog conditioning network (dividers + filter + clamp per channel, plus the 5 V-rail reference).

## CAN Frame Map (v1 — added 7/15)

The contract between the Teensy firmware and the dash's `CanSource`. There is no shared header between C++ and Python, so **this table is the single source of truth** — change it here first, then both sides.

Teensy → Pi broadcast, 500 kbps, standard 11-bit IDs, **little-endian**. Lower ID = higher arbitration priority.

| ID | Name | Rate | Payload |
|---|---|---|---|
| `0x100` | FAST | 50 Hz | `0-1` rpm u16 · `2-3` map_mv u16 · `4-5` seq u16 · `6-7` rsvd |
| `0x120` | SENSE | 20 Hz | `0-1` oilp_mv · `2-3` fuelp_mv · `4-5` afr_mv · `6-7` oilt_mv (all u16) |
| `0x140` | SLOW | 5 Hz | `0-1` fuel_mv u16 · `2-3` eth_pct×10 u16 · `4-7` rsvd |
| `0x160` | STATUS | 10 Hz | `0` flags · `1-4` uptime_ms u32 · `5-7` rsvd |

`flags` byte: bit0 = turn-left, bit1 = turn-right, bits 2-7 reserved.

**Analog channels carry raw millivolts, not engineering units.** The Pi applies the user's selected sensor profile (see Settings & Sensor Profiles). This is the whole reason swapping a wideband or a pressure sender is a settings change and never a firmware reflash — the Teensy doesn't know or care what's plugged in.

Exceptions that are already units, because no user-selectable sensor is involved: `rpm` (counted off the ignition signal), `eth_pct` (GM flex-fuel sensor is a frequency, 50-150 Hz = 0-100%), and `flags` (digital taps).

**Staleness:** if no `0x100` arrives for 500 ms the Pi marks CAN dead and falls back to the sim engine, so a Teensy reboot or an unplugged bus degrades to a working display instead of frozen gauges.

**Bus load:** ~11 kbit/s of 500 kbit/s (~2%). Deliberately roomy — OBD-sourced and future channels get added here without re-planning.

## Source Priority & Signal Suppression (decided 7/18)

- **Every gauge takes ANY available source, preferring the fastest.** Example — RPM: Teensy CAN (50 Hz) > OBD (~2 Hz over K-line) > sim. Slower sources stay polled as *warm standbys* even while a faster one is healthy, so losing the fast path mid-drive degrades to slow-but-real data instead of nothing. Implemented for RPM 7/18; the same chain applies to any channel with multiple sources.
- **A gauge with NO real source suppresses — it does not simulate.** (Product mode.) Showing invented oil temp on a race dash is a trust-killer, same family as the SENSOR FAULT rule: never render data that isn't real. Suppressed gauges disappear and the layout re-deals around the hole — this rides on generalizing the computed alert-grid dealer to normal modes, and lands with the config-menu/presets work. On the bench, demo mode keeps the sim filling everything so the product can be shown.

## Open Items

- Tune all thresholds and the de-escalation dwell from real seat time (incl. the 0.25 s AFR dwell)
- Confirm knock-correction data availability from the 2006 WRX ECU over SSM
- Fuel sender calibration curve for the GC chassis
- Trademark search/filing for "WAPOW" before public launch
- Test car for OBD development until the Impreza runs (warranty replacement MX+ pending)
- **Decide how to read the ECF-1: 4 analog outs vs MTS serial** (see Sensors On Hand). Analog works with what's already built; MTS is one wire, all four channels, digital, no dividers/ADC/double-conversion — but needs Innovate's protocol implemented on the Teensy. Product-wise we likely want both (an AEM customer uses analog).
- **Fuel temp has no gauge.** The ECF-1 provides it and nothing in the gauge table uses it. Decide whether it earns screen space, feeds a fuel-density correction, or is log-only.
- **Identify the oil pressure sending unit** already on the car (Ty doesn't recall the model). If it's a 0–100 PSI 0.5–4.5 V type, `PSI_100` already covers it.
- Timeline: Ty expects the car to be running around when the dash is ready for in-car testing (7/15). Plan the OBD + real-sender work to land with it.
- CAN frame map (IDs, scaling, rates) — design next, then Teensy firmware + `CanSource` in the dash
- `can0` auto bring-up at boot on the Pi (systemd; manual `ip link` for now)
- Log-file export path off the Pi (SMB vs USB stick vs scp)
- PARKED layout still uses the old dim styling — decide whether to convert to the no-dim rule
- Log timestamps depend on the Pi's clock; in the car (no network, no RTC) they'll be wrong — needs a plan before car install
- Custom sensor profile editor (stub today)
- **Settings panel is full at 6 rows** — it can't fit the MAP source + MAP profile rows without a layout change (needs paging, scrolling, or a second page). This now blocks **three** decided features (MAP source, MAP profile, oil temp alarm point), so it's the next settings work.
- **Oil temp alarm is hardcoded at 260 °F / clears 250 °F**, unlike the oil and fuel pressure alarms which are user-settable. Ty expects to run it lower in reality (7/15), so it should be a setting, not a code edit. Blocked on the settings panel above.
- **Oil temp sender not yet chosen** — depends on the thread in the IAG pan's temp bung (checking 7/16). 3/8" NPT → GM CTS (12146312, ~$15, curve is preset in every aftermarket ECU). 1/8" NPT → AEM 30-2012 (~$45, reads to 200 °C where the cheap senders quit at 130 °C ≈ 266 °F). Note the alarm point and the sensor range are separate concerns: even with a lower alarm, the gauge should still show how far past it you are rather than pegging.
- Concept demo HTML has drifted from the dash (no-dim, rule-of-thirds, RPM restyle) — re-sync or formally mark it historic
