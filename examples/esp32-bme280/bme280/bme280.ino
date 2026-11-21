
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BME280.h>

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;

Adafruit_BME280 sensor;
bool ready = false;

void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);
}

void loop() {
  if (!ready) {
    ready = sensor.begin(BME280_ADDRESS, &Wire);
  }
  if (!ready) {
    Serial.println("HARDWHERE_ERROR BME280 not detected at 0x77");
  } else {
    const float temp = sensor.readTemperature();
    if (isfinite(temp)) {
      Serial.print("HARDWHERE_OK temp_c=");
      Serial.println(temp, 2);
    } else {
      Serial.println("HARDWHERE_ERROR invalid temperature");
      ready = false;
    }
  }
  delay(1000);
}
