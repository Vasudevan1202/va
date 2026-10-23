# Hardware Wiring & Interface Specification

This document details the direct I²C connection between the **Raspberry Pi 3 Model B+** and the **GY-BMP280** breakout module.

---

## 1. Raspberry Pi 3 Model B+ GPIO Pinout Reference

The Raspberry Pi 3 Model B+ features a 40-pin header. Looking at the board with the GPIO header on the right and USB ports pointing down:

```
                      Physical Pin 1  (3.3V) [●] [●] Physical Pin 2  (5V)
                      Physical Pin 3  (SDA1) [●] [●] Physical Pin 4  (5V)
                      Physical Pin 5  (SCL1) [●] [●] Physical Pin 6  (GND)
                      Physical Pin 7  (GPIO4)[●] [●] Physical Pin 8  (TXD)
                                      ...    [●] [●] ...
```

---

## 2. Pin-to-Pin Connection Diagram

```
+---------------------------+                +-------------------------+
|     GY-BMP280 Breakout    |                |  Raspberry Pi 3B+ GPIO  |
|                           |                |                         |
|  [VCC] -------------------|----------------| Physical Pin 1 (3.3V)   |
|  [GND] -------------------|----------------| Physical Pin 6 (GND)    |
|  [SDA] -------------------|----------------| Physical Pin 3 (SDA1)   |
|  [SCL] -------------------|----------------| Physical Pin 5 (SCL1)   |
|                           |                |                         |
|  [CSB] (Tie to VCC/3.3V)  |                | (Selects I2C Mode)      |
|  [SDO] (Tie to GND: 0x76) |                | (Selects 0x76 Address)  |
+---------------------------+                +-------------------------+
```

---

## 3. Pin Function Descriptions

### 1. VCC / VIN (Supply Voltage)
- Connect to **Pin 1 (3.3V)**.
- **Warning:** Do not connect to 5V! BMP280 sensors run internally on 1.71V–3.6V.

### 2. GND (Ground)
- Connect to **Pin 6 (GND)** (or any other ground pin: Pins 9, 14, 20, 25, 30, 34, 39).

### 3. SDA (Serial Data)
- Connect to **Physical Pin 3 (GPIO 2 / BCM2)**.
- Hardware I²C data line with internal 1.8kΩ pull-up resistor to 3.3V on the Raspberry Pi board.

### 4. SCL (Serial Clock)
- Connect to **Physical Pin 5 (GPIO 3 / BCM3)**.
- Hardware I²C clock line with internal 1.8kΩ pull-up resistor to 3.3V on the Raspberry Pi board.

### 5. CSB (Chip Select)
- Many 6-pin breakout boards include a CSB pin.
- To enable **I²C mode**, CSB must be pulled **HIGH** (to 3.3V / VCC). Most GY-BMP280 modules have an on-board pull-up resistor to VCC, so it can be left floating or tied to VCC.

### 6. SDO (Serial Data Out / Address Select)
- Sets the 7-bit slave I²C address:
  - **Tied to GND (or left open on most GY modules):** Address is **`0x76`** (118 decimal).
  - **Tied to VCC (3.3V):** Address is **`0x77`** (119 decimal).
- Virtual Atmosphere automatically checks both `0x76` and `0x77`.

---

## 4. Hardware Verification
Run:
```bash
sudo i2cdetect -y 1
```
If properly connected, address `76` or `77` will be displayed. If nothing appears, check wire integrity and ensure headers are firmly seated.
