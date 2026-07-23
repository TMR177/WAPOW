// wapow_can_test.ino
// Teensy 4.1 CAN bench test — proves the bus before any real firmware.
// Sends a heartbeat frame twice a second and prints anything it receives.
//
// Wiring: FlexCAN CAN1, TX = pin 22, RX = pin 23, to SN65HVD230 #1.
// Bus: 500 kbps (matches the Pi's `ip link ... bitrate 500000`).
// Needs the FlexCAN_T4 library (Arduino IDE: Library Manager -> "FlexCAN_T4").

#include <FlexCAN_T4.h>

FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> can1;

uint32_t last = 0;
uint16_t counter = 0;

void printFrame(const CAN_message_t &msg) {
  Serial.print("RX  id=0x");
  Serial.print(msg.id, HEX);
  Serial.print(" len=");
  Serial.print(msg.len);
  Serial.print(" data=");
  for (uint8_t i = 0; i < msg.len; i++) {
    if (msg.buf[i] < 0x10) Serial.print('0');
    Serial.print(msg.buf[i], HEX);
    Serial.print(' ');
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  can1.begin();
  can1.setBaudRate(500000);
  can1.enableFIFO();
  Serial.println("WAPOW CAN test: CAN1 @ 500k, TX=22 RX=23");
}

void loop() {
  CAN_message_t rx;
  while (can1.read(rx)) printFrame(rx);      // drain anything received

  if (millis() - last >= 500) {              // heartbeat every 500 ms
    last = millis();
    CAN_message_t tx;
    tx.id  = 0x100;
    tx.len = 4;
    tx.buf[0] = counter & 0xFF;
    tx.buf[1] = (counter >> 8) & 0xFF;
    tx.buf[2] = 0xDA;                         // "DA5C" marker so it's easy to
    tx.buf[3] = 0x5C;                         // spot in candump output
    if (can1.write(tx)) {
      Serial.print("TX  heartbeat #");
      Serial.println(counter);
      counter++;
    } else {
      Serial.println("TX  FAILED (bus not up? check wiring/termination)");
    }
  }
}
