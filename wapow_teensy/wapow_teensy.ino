// wapow_teensy.ino — WAPOW acquisition firmware v0.1
//
// Broadcasts the CAN frame map in wapow_spec.md (500 kbps, CAN1,
// TX=22 RX=23 -> SN65HVD230 #1).
//
// *** SYNTHETIC DATA ***
// No senders are wired yet, so every channel is faked with a scripted drive
// loop. This exists to prove the whole pipe end to end — Teensy -> CAN -> Pi
// -> gauges — before any hardware exists to argue with. When a real sender
// lands, replace exactly one line in sampleSynthetic(): the mV channels
// become analogRead(pin) * 3300 / 1023 (or whatever the divider gives), and
// nothing else in this file or on the Pi has to change.
//
// Analog channels are sent as RAW MILLIVOLTS on purpose. The Pi applies the
// user's sensor profile, so swapping a wideband never means reflashing this.

#include <FlexCAN_T4.h>

FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> can1;

// ---- frame map (must match wapow_spec.md) ----------------------------
const uint32_t ID_FAST   = 0x100;   // 50 Hz
const uint32_t ID_SENSE  = 0x120;   // 20 Hz
const uint32_t ID_SLOW   = 0x140;   //  5 Hz
const uint32_t ID_STATUS = 0x160;   // 10 Hz

const uint32_t MS_FAST   = 20;
const uint32_t MS_SENSE  = 50;
const uint32_t MS_SLOW   = 200;
const uint32_t MS_STATUS = 100;

uint32_t tFast = 0, tSense = 0, tSlow = 0, tStatus = 0;
uint16_t seq = 0;

// ---- real analog input -----------------------------------------------------
// A potentiometer standing in for an oil-pressure sender, now read THROUGH A
// DIVIDER so it exercises the real 0-5V signal path safely. This is the
// template every real 0-5V channel (AFR, oil/fuel press, MAP) copies.
//
// WIRING (divider test):
//   pot: outer legs -> Teensy VIN (~5V on USB) and GND; wiper = the 0-5V signal
//   divider: wiper -> R_TOP -> node -> R_BOT -> GND
//   node -> pin 14 (A0)
// The node sees wiper * R_BOT/(R_TOP+R_BOT) = wiper * 0.6, so a 5V wiper lands
// at ~3.0V on the pin — safely under the 3.3V limit.
//
// *** A real 0-5V sender must ALWAYS go through this divider. *** Teensy 4.1
// analog pins are 3.3V max and NOT 5V tolerant — 5V straight in kills the chip.
//
// The divider math lives HERE, not in the Pi's sensor profiles: we undo the
// divider and broadcast TRUE sender millivolts, so a profile (which describes
// the sender) never needs to know how we wired it. Get this backwards and
// every profile silently reads 0.6x.
const int PIN_OILP = A0;           // = pin 14
const float ADC_VREF_MV = 3300.0;  // Teensy analog reference
const float R_TOP = 2200.0;        // sender -> node
const float R_BOT = 3300.0;        // node -> GND   (ratio 3.3/5.5 = 0.6)

// Left turn signal — a real DIGITAL input, the bench proof of the digital path
// (in the car this is a 12V blinker tap through a protection circuit). Active
// low with the internal pull-up: idle = HIGH (off); jumper pin 2 to GND = ON.
// A digital pin is 3.3V-only too, but a bare jumper to GND/3.3V can't exceed
// that, so it's safe on the bench exactly like the pot was.
const int PIN_TURN_L = 2;

// ---- the values we broadcast ----------------------------------------------
struct Sample {
  uint16_t rpm;
  uint16_t map_mv, oilp_mv, fuelp_mv, afr_mv, oilt_mv, fuel_mv;
  uint16_t eth_pct_x10;
  uint8_t  flags;
};
Sample s;

// Reads the real channels. Must come after `s` is declared. Runs AFTER
// sampleSynthetic() each loop, so it overwrites the fake value.
void sampleReal() {
  uint32_t counts = analogRead(PIN_OILP);          // 12-bit, 0..4095
  float node_mv = counts * ADC_VREF_MV / 4095.0;   // volts at the pin
  float sender_mv = node_mv * (R_TOP + R_BOT) / R_BOT;  // undo the divider
  s.oilp_mv = (uint16_t)(sender_mv + 0.5);         // TRUE sender millivolts

  // Left turn signal: active-low. Jumper pin 2 to GND => bit set.
  if (digitalRead(PIN_TURN_L) == LOW) s.flags |= 0x01;
  else                                s.flags &= ~0x01;
}

// Little-endian u16 into a frame — matches the Pi's struct '<H' unpack.
inline void putU16(CAN_message_t &m, uint8_t at, uint16_t v) {
  m.buf[at]     = v & 0xFF;
  m.buf[at + 1] = (v >> 8) & 0xFF;
}

// ---- synthetic drive -------------------------------------------------------
// A ~70 s loop that sweeps through idle / cruise / hard driving, so the dash's
// mode logic and alerts actually have something to react to.
void sampleSynthetic() {
  float t = (millis() % 70000) / 1000.0f;   // 0..70 s
  float load;                                // 0..1

  if (t < 6)        { s.rpm = 850;                    load = 0.0f; }
  else if (t < 26)  { s.rpm = 2300 + 200 * sinf(t);   load = 0.25f; }
  else if (t < 44)  { s.rpm = 4300 + 1800 * sinf(t * 1.25f); load = 0.6f; }
  else if (t < 62)  { s.rpm = 5300 + 2000 * sinf(t * 1.55f); load = 0.9f; }
  else              { s.rpm = 2350;                   load = 0.15f; }

  // ONE boost number drives both MAP and fuel pressure. They used to be
  // modelled separately, which made the Pi's decoded boost disagree with the
  // fuel pressure we sent and tripped a phantom FUEL PRESS alert. Fake data
  // still has to be self-consistent or you spend the evening chasing it.
  float boost_psi = -13 + 33 * load;

  // MAP, encoded so the Pi's 3-bar decode returns exactly boost_psi back:
  //   abs = boost + 14.7 ; mv = 500 + abs/44.1 * 4000
  float abs_psi = boost_psi + 14.7f;
  s.map_mv = 500 + (uint16_t)(abs_psi / 44.1f * 4000);

  // Oil pressure is REAL now — read from the pot in sampleReal(), which runs
  // after this and overwrites s.oilp_mv. Left here for reference / to fall
  // back to if the pot is unplugged.
  //   float oilp_psi = 24 + 48 * load;
  //   s.oilp_mv = 500 + (uint16_t)(oilp_psi / 100.0f * 4000);

  // Fuel pressure = base + boost (manifold-referenced). Same 0-100 PSI sender.
  // Base must match SETTINGS.fuel_press_base on the Pi (default 43) or the
  // deviation alarm fires on healthy data.
  float fuelp_psi = 43 + (boost_psi > 0 ? boost_psi : 0);
  s.fuelp_mv = 500 + (uint16_t)(fuelp_psi / 100.0f * 4000);

  // AFR on an AEM X-Series: 0-5 V = 10-20 AFR. Rich under load, ~14.7 off it.
  float afr = load > 0.5f ? 11.6f : 14.7f;
  s.afr_mv = (uint16_t)((afr - 10.0f) / 10.0f * 5000);

  // Oil temp climbing with load. Sender curve is a TODO — linear stand-in.
  float oilt_f = 200 + 60 * load;
  s.oilt_mv = (uint16_t)((oilt_f - 140.0f) / 160.0f * 5000);

  s.fuel_mv = 3000;              // ~3/4 tank, flat
  s.eth_pct_x10 = 630;           // E63
  s.flags = 0;
  // Left blinker is now a real input (set in sampleReal). Right stays
  // synthetic so there's still an auto-demo of that bit each loop.
  if (t > 63 && t < 67) s.flags |= 0x02;   // right blinker
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);       // 0..4095 over the 3.3V reference
  analogReadAveraging(16);        // hardware averaging — kills ADC jitter
  pinMode(PIN_TURN_L, INPUT_PULLUP);   // left turn signal, active-low
  can1.begin();
  can1.setBaudRate(500000);
  can1.enableFIFO();
  Serial.println("WAPOW Teensy v0.4 — oil press (A0 divider) + left turn (pin 2), rest synthetic");
}

void loop() {
  sampleSynthetic();
  sampleReal();                   // real channels overwrite the fakes
  uint32_t now = millis();
  CAN_message_t m;

  if (now - tFast >= MS_FAST) {
    tFast = now;
    m.id = ID_FAST; m.len = 8;
    memset(m.buf, 0, 8);
    putU16(m, 0, s.rpm);
    putU16(m, 2, s.map_mv);
    putU16(m, 4, seq++);
    can1.write(m);
  }
  if (now - tSense >= MS_SENSE) {
    tSense = now;
    m.id = ID_SENSE; m.len = 8;
    putU16(m, 0, s.oilp_mv);
    putU16(m, 2, s.fuelp_mv);
    putU16(m, 4, s.afr_mv);
    putU16(m, 6, s.oilt_mv);
    can1.write(m);
  }
  if (now - tSlow >= MS_SLOW) {
    tSlow = now;
    m.id = ID_SLOW; m.len = 8;
    memset(m.buf, 0, 8);
    putU16(m, 0, s.fuel_mv);
    putU16(m, 2, s.eth_pct_x10);
    can1.write(m);
  }
  if (now - tStatus >= MS_STATUS) {
    tStatus = now;
    m.id = ID_STATUS; m.len = 8;
    memset(m.buf, 0, 8);
    m.buf[0] = s.flags;
    uint32_t up = millis();
    m.buf[1] = up & 0xFF; m.buf[2] = (up >> 8) & 0xFF;
    m.buf[3] = (up >> 16) & 0xFF; m.buf[4] = (up >> 24) & 0xFF;
    can1.write(m);

    // one line a second so the serial monitor shows it's alive
    static uint32_t tPrint = 0;
    if (now - tPrint >= 1000) {
      tPrint = now;
      // oilp is TRUE sender mV (divider undone) — should match a multimeter on
      // the pot wiper, NOT the lower voltage measured at the pin.
      Serial.printf("rpm=%u map=%umV oilp=%umV afr=%umV flags=0x%02X seq=%u\n",
                    s.rpm, s.map_mv, s.oilp_mv, s.afr_mv, s.flags, seq);
    }
  }
}
