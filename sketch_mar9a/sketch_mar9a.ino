/**
 * ESP32 Water Leak Detection — 4 Sensors + MQTT
 * ───────────────────────────────────────────────
 * Sensors:
 *   1. YF-S201 Water Flow Sensor     → GPIO 19
 *   2. DS18B20 Temperature Sensor    → GPIO 4 (via adapter module)
 *   3. ADXL345 Accelerometer         → I2C (SDA=GPIO 21, SCL=GPIO 22)
 *   4. HX710B Pressure Sensor        → OUT=GPIO 32, SCK=GPIO 33
 *
 * Libraries required (install via Arduino Library Manager):
 *   - WiFi             (built into ESP32 core)
 *   - PubSubClient     (by Nick O'Leary)
 *   - ArduinoJson      (by Benoit Blanchon)
 *   - OneWire          (by Jim Studt)
 *   - DallasTemperature (by Miles Burton)
 *   - Adafruit ADXL345 (by Adafruit)
 *   - Adafruit Unified Sensor (by Adafruit)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>

// ── WiFi credentials ────────────────────────────────────────────────────────
const char* WIFI_SSID     = "CANALBOX-6CC2-2G";
const char* WIFI_PASSWORD = "fkukfqr2z7U9";

// ── MQTT broker ─────────────────────────────────────────────────────────────
const char* MQTT_SERVER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;
const char* MQTT_TOPIC    = "iot/sensor/water";
const char* MQTT_CLIENT   = "esp32-node-001";
const char* SHUTOFF_TOPIC = "iot/commands/shutoff";

// ── Flow Sensor config ─────────────────────────────────────────────────────
const int   SENSOR_PIN        = 19;
const float CALIBRATION_FACTOR = 7.5;
const unsigned long SEND_INTERVAL = 2000;

// ── DS18B20 Temperature Sensor ──────────────────────────────────────────────
#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);
float temperature = 0.0;

// ── ADXL345 Accelerometer ───────────────────────────────────────────────────
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);
bool adxlConnected = false;

// ── HX710B Pressure Sensor ─────────────────────────────────────────────────
const int PRESSURE_OUT_PIN = 32;   // OUT → GPIO 32
const int PRESSURE_SCK_PIN = 33;   // SCK → GPIO 33
bool pressureSensorConnected = false;
long pressureOffset = 0;           // baseline offset for calibration

// ── GIS location (Kigali) ──────────────────────────────────────────────────
const float LATITUDE  = -1.9441;
const float LONGITUDE = 30.0619;

// ── Globals ─────────────────────────────────────────────────────────────────
volatile long pulseCount = 0;
float flowRate           = 0;
unsigned long lastSend   = 0;
unsigned long opHours    = 0;

WiFiClient   espClient;
PubSubClient mqttClient(espClient);

// ── Interrupt ───────────────────────────────────────────────────────────────
void IRAM_ATTR pulseCounter() {
  pulseCount++;
}

// ── WiFi ────────────────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi connected — IP: ");
  Serial.println(WiFi.localIP());
}

// ── MQTT ────────────────────────────────────────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.print("MQTT received ["); Serial.print(topic); Serial.print("]: ");
  Serial.println(msg);
}

void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT...");
    if (mqttClient.connect(MQTT_CLIENT)) {
      Serial.println(" connected!");
      mqttClient.subscribe(SHUTOFF_TOPIC);
      Serial.print("Subscribed to: "); Serial.println(SHUTOFF_TOPIC);
    } else {
      Serial.print(" failed (rc=");
      Serial.print(mqttClient.state());
      Serial.println(") — retrying in 3s");
      delay(3000);
    }
  }
}

// ── Calculate vibration magnitude from ADXL345 ─────────────────────────────
float getVibration() {
  if (!adxlConnected) return 2.5;

  sensors_event_t event;
  accel.getEvent(&event);

  float vibration = sqrt(
    event.acceleration.x * event.acceleration.x +
    event.acceleration.y * event.acceleration.y +
    event.acceleration.z * event.acceleration.z
  );

  return vibration;
}

// ── Read raw value from HX710B pressure sensor ─────────────────────────────
long readHX710B() {
  // Wait for the sensor to be ready (OUT goes LOW when data is ready)
  unsigned long timeout = millis();
  while (digitalRead(PRESSURE_OUT_PIN) == HIGH) {
    if (millis() - timeout > 100) return 0;  // timeout after 100ms
  }

  // Read 24 bits of data
  long value = 0;
  for (int i = 0; i < 24; i++) {
    digitalWrite(PRESSURE_SCK_PIN, HIGH);
    delayMicroseconds(1);
    value = (value << 1) | digitalRead(PRESSURE_OUT_PIN);
    digitalWrite(PRESSURE_SCK_PIN, LOW);
    delayMicroseconds(1);
  }

  // 25th clock pulse — sets next conversion to temperature (default mode)
  digitalWrite(PRESSURE_SCK_PIN, HIGH);
  delayMicroseconds(1);
  digitalWrite(PRESSURE_SCK_PIN, LOW);
  delayMicroseconds(1);

  // Convert from 24-bit two's complement
  if (value & 0x800000) {
    value |= 0xFF000000;  // sign extend for negative values
  }

  return value;
}

// ── Get pressure reading in kPa ────────────────────────────────────────────
float getPressure() {
  if (!pressureSensorConnected) return 55.0;  // fallback default

  long rawValue = readHX710B();
  if (rawValue == 0) return 55.0;  // timeout fallback

  // Subtract baseline offset and convert to kPa
  // The HX710B gives relative readings — we use the startup baseline as zero
  long adjusted = rawValue - pressureOffset;

  // Convert to kPa (approximate scaling factor — adjust based on your sensor)
  // Positive values = pressure above atmospheric
  float pressure_kPa = adjusted / 100.0;

  return pressure_kPa;
}

// ── Calibrate pressure sensor (take baseline reading at startup) ───────────
void calibratePressureSensor() {
  Serial.print("Calibrating pressure sensor...");
  long total = 0;
  int readings = 10;

  for (int i = 0; i < readings; i++) {
    total += readHX710B();
    delay(50);
  }

  pressureOffset = total / readings;
  Serial.print(" baseline offset: ");
  Serial.println(pressureOffset);
}

// ── Setup ───────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.println("\n============================================");
  Serial.println("  Water Leak Detection System — 4 Sensors");
  Serial.println("============================================\n");

  // Flow sensor interrupt
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(SENSOR_PIN), pulseCounter, FALLING);
  Serial.println("✓ Flow sensor ready on GPIO 19");

  // Temperature sensor
  tempSensor.begin();
  int sensorCount = tempSensor.getDeviceCount();
  Serial.print("Found ");
  Serial.print(sensorCount);
  Serial.println(" DS18B20 sensor(s)");
  if (sensorCount == 0) {
    Serial.println("⚠️ No DS18B20 found! Check wiring on GPIO 4");
  }

  // ADXL345 Accelerometer
  if (accel.begin()) {
    adxlConnected = true;
    accel.setRange(ADXL345_RANGE_16_G);
    Serial.println("✓ ADXL345 Accelerometer detected!");
  } else {
    adxlConnected = false;
    Serial.println("⚠️ ADXL345 NOT detected — using default vibration value");
  }

  // HX710B Pressure Sensor
  pinMode(PRESSURE_OUT_PIN, INPUT);
  pinMode(PRESSURE_SCK_PIN, OUTPUT);
  digitalWrite(PRESSURE_SCK_PIN, LOW);

  // Test if sensor responds
  unsigned long testTimeout = millis();
  bool sensorReady = false;
  while (millis() - testTimeout < 500) {
    if (digitalRead(PRESSURE_OUT_PIN) == LOW) {
      sensorReady = true;
      break;
    }
    delay(10);
  }

  if (sensorReady) {
    pressureSensorConnected = true;
    calibratePressureSensor();
    Serial.println("✓ HX710B Pressure sensor detected and calibrated!");
  } else {
    pressureSensorConnected = false;
    Serial.println("⚠️ HX710B NOT detected — using default pressure value");
  }

  // Network
  connectWiFi();
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  connectMQTT();

  lastSend = millis();
  Serial.println("\n🚀 Ready — publishing to: " + String(MQTT_TOPIC));
}

// ── Loop ────────────────────────────────────────────────────────────────────
void loop() {
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  if (millis() - lastSend >= SEND_INTERVAL) {
    detachInterrupt(digitalPinToInterrupt(SENSOR_PIN));

    // 1. Flow Rate
    float elapsed = (millis() - lastSend) / 1000.0;
    flowRate = (pulseCount / CALIBRATION_FACTOR) / elapsed * 60.0;
    opHours++;

    // 2. Temperature
    tempSensor.requestTemperatures();
    temperature = tempSensor.getTempCByIndex(0);
    if (temperature == DEVICE_DISCONNECTED_C || temperature == -127.0) {
      temperature = 25.0;
      Serial.println("⚠️ DS18B20 disconnected — using default 25°C");
    }

    // 3. Vibration
    float vibration = getVibration();

    // 4. Pressure
    float pressure = getPressure();

    // Build JSON
    StaticJsonDocument<512> doc;
    doc["Flow_Rate"]         = round(flowRate * 100.0) / 100.0;
    doc["Temperature"]       = round(temperature * 100.0) / 100.0;
    doc["Vibration"]         = round(vibration * 100.0) / 100.0;
    doc["Pressure"]          = round(pressure * 100.0) / 100.0;  // REAL sensor data
    doc["RPM"]               = 2000.0;  // default — no RPM sensor
    doc["Operational_Hours"] = (int)opHours;

    // GIS / location data
    doc["Latitude"]          = LATITUDE;
    doc["Longitude"]         = LONGITUDE;
    doc["Zone_enc"]          = 0;
    doc["Block_enc"]         = 0;
    doc["Pipe_enc"]          = 0;

    // Serialize and publish
    char payload[512];
    serializeJson(doc, payload);

    if (mqttClient.publish(MQTT_TOPIC, payload)) {
      Serial.println("─────────────────────────────────");
      Serial.printf("💧 Flow Rate:    %.2f L/min (pulses: %ld)\n", flowRate, pulseCount);
      Serial.printf("🌡️  Temperature: %.2f °C\n", temperature);
      Serial.printf("📳 Vibration:    %.2f m/s²\n", vibration);
      Serial.printf("💨 Pressure:     %.2f kPa\n", pressure);
      Serial.println("📡 Data sent to MQTT!");
    } else {
      Serial.println("[FAIL] MQTT publish failed");
    }

    // Reset for next interval
    pulseCount = 0;
    lastSend   = millis();
    attachInterrupt(digitalPinToInterrupt(SENSOR_PIN), pulseCounter, FALLING);
  }
}