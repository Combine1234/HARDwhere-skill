
# Read temperature from a BME280 over I²C

Use an ESP32-DevKitC V4 with an ESP32-WROOM-32-series module, the Adafruit BME280 breakout with the pin labels below, a USB data cable, and four jumpers. If using a different breakout, confirm both its pinout and voltage before using this wiring.

| ESP32 board label | Adafruit BME280 label | Function |
|---|---|---|
| 3V3 | VIN | 3.3 V supply |
| GND | GND | Common ground |
| IO21 (GPIO21) | SDI | SDA, data |
| IO22 (GPIO22) | SCK | SCL, clock |

Use the board pinout's top view to locate the header positions. Connect the jumpers with USB unplugged. Keep the default address at 0x77 for the sketch supplied here. The breakout has I²C pull-ups. Check the breakout guide for the CS connection on an original non-STEMMA revision if it intermittently selects SPI.

[Espressif DevKitC I/O and power](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html#header-block) · [Adafruit breakout I²C wiring](https://learn.adafruit.com/adafruit-bme280-humidity-barometric-pressure-temperature-sensor-breakout/arduino-test) · [Bosch BME280 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf)

From the project root, render both views from the wiring data and build with the supported core.

```sh
hardwhere wiring examples/esp32-bme280/wiring.json
hardwhere doctor --board esp32-devkitc-v4
hardwhere install --board esp32-devkitc-v4 --core --library "Adafruit BME280 Library" --apply
hardwhere build --board esp32-devkitc-v4 --sketch examples/esp32-bme280/bme280 --output build/bme280
hardwhere discover --json
```

Match the candidate port to the physical board, then replace `YOUR_TARGET` with its target ID. If an earlier build exists, choose a new artifact directory. If Windows reports a missing CP210x driver without a serial port, use the [driver instructions](../../README.md#what-you-can-run) first.

```sh
hardwhere flash --board esp32-devkitc-v4 --target YOUR_TARGET --artifact build/bme280 --apply
hardwhere verify --board esp32-devkitc-v4 --target YOUR_TARGET --expect 'HARDWHERE_OK temp_c=-?[0-9]+[.][0-9]+' --json
```

A matching line is a sample reported by the running sketch. Check that the value is plausible and rises when you bring a warm hand near the sensor. If upload succeeds and the sample still fails, run `monitor` at 115200 for eight seconds. A BME280 initialization error points to power, SDA/SCL, address, or module identification. Boot output without an application line calls for checking the sketch and boot status first.

For a follow-up session save a project checkpoint with the exact module, wiring file, the observed result and the next action. Use `hardwhere context save <file.json>` and `hardwhere context show`.
