/**
 * simulator.js — ESP32 Sensor Simulator
 * ──────────────────────────────────────
 * Simulates the ESP32 publishing sensor readings to the MQTT broker.
 * Use this to test the full pipeline before the physical hardware arrives.
 *
 * Run:  node simulator.js
 * Publishes to: wasac/sensor/water  every 5 seconds
 *
 * Every ~10th reading is a simulated LEAK (low pressure + high flow).
 */

require('dotenv').config();
const mqtt = require('mqtt');

const BROKER       = process.env.MQTT_BROKER    || 'mqtt://broker.hivemq.com:1883';
const TOPIC_SENSOR = process.env.TOPIC_SENSOR   || 'wasac/sensor/water';
const INTERVAL_MS  = 5000;  // 5 seconds — same as real ESP32

const client = mqtt.connect(BROKER, {
  clientId: `esp32-simulator-${Math.random().toString(16).slice(2, 6)}`,
  clean: true,
});

// Fixed GIS coordinates — Kigali pipes
const ZONES   = [0, 1, 2, 3];
const BLOCKS  = [0, 1, 2];
const PIPES   = [0, 1, 2, 3, 4];
const LAT     = -1.9441;
const LON     = 30.0619;

let readingCount = 0;

function normalReading() {
  return {
    Pressure:          55 + (Math.random() * 20 - 10),   // 45–75 bar
    Flow_Rate:         70 + (Math.random() * 20 - 10),   // 60–90 L/min
    Temperature:       95 + (Math.random() * 6  - 3),    // 92–98 °C
    Vibration:          2.5 + (Math.random() * 1  - 0.5),// 2.0–3.0
    RPM:             2000 + (Math.random() * 200 - 100), // 1900–2100
    Operational_Hours: 4000 + Math.floor(readingCount),
    Latitude:          LAT + (Math.random() * 0.01 - 0.005),
    Longitude:         LON + (Math.random() * 0.01 - 0.005),
    Zone_enc:          ZONES[Math.floor(Math.random() * ZONES.length)],
    Block_enc:         BLOCKS[Math.floor(Math.random() * BLOCKS.length)],
    Pipe_enc:          PIPES[Math.floor(Math.random() * PIPES.length)],
  };
}

function leakReading() {
  // Classic leak signature: pressure drop + flow spike
  return {
    Pressure:          22 + (Math.random() * 10 - 5),    // 17–32 bar  (LOW)
    Flow_Rate:        118 + (Math.random() * 15 - 7),    // 111–133 L/min (HIGH)
    Temperature:       98 + (Math.random() * 2  - 1),
    Vibration:          4.8 + (Math.random() * 1),
    RPM:             1100 + (Math.random() * 200 - 100),
    Operational_Hours: 8000 + Math.floor(readingCount),
    Latitude:          LAT + (Math.random() * 0.01 - 0.005),
    Longitude:         LON + (Math.random() * 0.01 - 0.005),
    Zone_enc:          ZONES[Math.floor(Math.random() * ZONES.length)],
    Block_enc:         BLOCKS[Math.floor(Math.random() * BLOCKS.length)],
    Pipe_enc:          PIPES[Math.floor(Math.random() * PIPES.length)],
  };
}

client.on('connect', () => {
  console.log(`✔ Simulator connected to ${BROKER}`);
  console.log(`📡 Publishing to: ${TOPIC_SENSOR} every ${INTERVAL_MS / 1000}s`);
  console.log('   Every 10th reading will be a simulated LEAK.\n');

  setInterval(() => {
    readingCount++;
    const isLeak  = readingCount % 10 === 0;  // 10% leak rate
    const reading = isLeak ? leakReading() : normalReading();

    // Round all numbers to 2 decimal places
    Object.keys(reading).forEach(k => {
      reading[k] = Math.round(reading[k] * 100) / 100;
    });

    const payload = JSON.stringify(reading);
    client.publish(TOPIC_SENSOR, payload, { qos: 1 });

    const tag = isLeak ? '🚨 LEAK  ' : '✔ Normal';
    console.log(`[${new Date().toLocaleTimeString()}] ${tag} | P=${reading.Pressure} bar | F=${reading.Flow_Rate} L/min`);
  }, INTERVAL_MS);
});

client.on('error', (err) => console.error('Simulator error:', err.message));
