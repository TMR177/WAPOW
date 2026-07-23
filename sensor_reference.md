# Sensor Reference — analog scalings for the profile menu

Compiled 7/19 from manufacturer docs and the MegaSquirt/DIYAutoTune canon.
Rule: only ship a profile whose transfer function is CONFIRMED from a
manufacturer document or the well-established DIY-EFI references. Anything
marked VERIFY needs a datasheet check before it goes in the menu.

## Widebands (0–5 V analog out → AFR, gasoline)

| Controller | 0 V | 5 V | Formula | Status |
|---|---|---|---|---|
| AEM X-Series (30-0300/0310) | 10.0 | 20.0 | AFR = 2V + 10 | ✅ shipped (`AEM_XSERIES`) |
| AEM Classic (30-4110) | 10.0 | 20.0 | same | ✅ covered by `AEM_XSERIES` |
| Innovate LC-2 / MTX-L | 7.35 | 22.39 | AFR = 3.008V + 7.35 | ✅ shipped (`INNOVATE_LC2`); also fits the ECF-1's AFR channel |
| Zeitronix Zt-2 / Zt-3 | 9.6 | 19.6 | AFR = 2V + 9.6 | ✅ added (`ZEITRONIX`) — [source](https://www.zeitronix.com/Products/zt2/widebandoutput.shtml) |
| Ballenger AFR500 (standard) | 9.0 | 16.0 | AFR = 1.4V + 9 | ✅ added (`AFR500_STD`) |
| Ballenger AFR500 (wide) | 6.0 | 20.0 | AFR = 2.8V + 6 | ✅ added (`AFR500_WIDE`) |
| PLX SM-AFR | 10.0 | 20.0 | reportedly AFR = 2V + 10 | ⚠ VERIFY against PLX manual before shipping |
| 14Point7 Spartan 2/3 | 10.0 | 20.0 | default reportedly 2V + 10 | ⚠ VERIFY (configurable units) |

Note: most controllers are user-reprogrammable — the menu ships DEFAULTS,
and the Custom slot (editor TBD) covers reprogrammed outputs.

## Pressure senders (0.5–4.5 V ratiometric)

The generic 0.5–4.5 V family covers nearly every aftermarket sender; the
branded parts below are electrically IDENTICAL to our generic profiles:

| Part | Range | Transfer | Menu profile |
|---|---|---|---|
| AEM 30-2130-100 (and 30-2131) | 0–100 PSIg | PSI = 25V − 12.5 | = `PSI_100` ✅ ([AEM doc](https://www.bmotorsports.com/download/pdf/aem_pressure_sensor_specifications.pdf)) |
| AEM 30-2130-150 | 0–150 PSIg | PSI = 37.5V − 18.75 | = `PSI_150` ✅ |
| Honeywell PX3 100 psi | 0–100 PSIg | 10%–90% of supply | = `PSI_100` ✅ |
| Generic eBay/Amazon "0-100psi 0-5V" | 0–100 | 0.5–4.5 V | = `PSI_100` ✅ (Ty's spares) |
| OBDLink/Innovate ECF-1 fuel pressure | 0–145 PSI (10 bar) | configurable analog out | `PSI_145` ✅ added |

VDO / Autometer classic senders are RESISTIVE (10-180Ω, 240-33Ω etc.), not
0-5V — they'd need a pull-up conditioning circuit and different profile
math. Out of scope until someone actually shows up with one.

## MAP sensors

| Part | Transfer | Menu profile |
|---|---|---|
| Generic 2/3/4-bar (0.5–4.5 V) | linear to full scale | `BAR_2/3/4` ✅ shipped |
| GM 3-bar (12223861 style) | 1.1 kPa @ 0 V → 315.5 kPa @ 5 V | `GM_3BAR` ✅ added ([megamanual](http://www.megamanual.com/v22manual/3bar.htm)) |
| GM 2-bar | commonly cited 8.8→208 kPa | ⚠ VERIFY before shipping |
| GM 1-bar | commonly cited ~10→105 kPa | ⚠ VERIFY |
| AEM 30-2130-50 (50 PSIa) | PSI = 12.5V − 6.25 (0.5–4.5 V family) | `AEM_50PSIA` ✅ added |

## Temperature senders (future — needs the thermistor build)

All of these are NON-LINEAR thermistors; the profile system needs curve
support (pull-up resistor + published R-vs-T table) before any ship:

- **GM CTS/IAT (12146312 family)** — the most-published curve in DIY EFI;
  ships as a preset in MegaSquirt/Speeduino references. Grab the exact
  table from the MS reference during the thermistor build.
- **AEM 30-2012** (water/oil, 1/8" NPT) — the sender Ty's buying for the
  IAG pan; AEM publishes the calibration table in the sensor doc.
- **Bosch 0280130026 style NTC** — common European standalone choice.

## Sources
DIYAutoTune sensor collection and tech articles, AEM pressure sensor spec
sheet, Zeitronix output docs, AEM X-Series manual, Ballenger AFR500 specs,
megamanual 3-bar reference. Links inline above.
