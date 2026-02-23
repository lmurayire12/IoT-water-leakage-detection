/**
 * index.js — Water Leak Detection MQTT Server
 * ─────────────────────────────────────────────
 * Subscribes to ESP32 sensor readings, runs ML inference,
 * publishes leak alerts, and serves a real-time dashboard.
 *
 * Flow:
 *   ESP32 → MQTT publish (wasac/sensor/water)
 *       → Node.js receives JSON payload
 *       → Python inference.py called via child_process
 *       → If LEAK: publish alert to (wasac/alerts/leak)
 *       → All results streamed to browser dashboard via Socket.io
 */

require('dotenv').config();
const mqtt       = require('mqtt');
const { spawn }  = require('child_process');
const path       = require('path');
const express    = require('express');
const http       = require('http');
const { Server } = require('socket.io');
const chalk      = require('chalk');
const fs         = require('fs');

// ── Config ────────────────────────────────────────────────────────────────────
const BROKER       = process.env.MQTT_BROKER       || 'mqtt://broker.hivemq.com:1883';
const CLIENT_ID    = process.env.MQTT_CLIENT_ID    || 'wasac-leak-server-001';
const TOPIC_SENSOR = process.env.TOPIC_SENSOR      || 'wasac/sensor/water';
const TOPIC_ALERTS = process.env.TOPIC_ALERTS      || 'wasac/alerts/leak';
const TOPIC_RESULTS= process.env.TOPIC_RESULTS     || 'wasac/results';
const PYTHON_CMD   = process.env.PYTHON_CMD        || 'python';
const THRESHOLD    = parseFloat(process.env.LEAK_THRESHOLD || '0.5');
const PORT         = parseInt(process.env.PORT     || '3000');
const INFERENCE_PY = path.join(__dirname, 'inference.py');
const LOG_FILE     = path.join(__dirname, 'alerts.log');

// ── Express + Socket.io dashboard ────────────────────────────────────────────
const app    = express();
const server = http.createServer(app);
const io     = new Server(server);

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Simple REST endpoint — latest N results
const recentResults = [];
app.get('/api/results', (_req, res) => res.json(recentResults.slice(-100)));
app.get('/api/alerts',  (_req, res) => {
  const alerts = recentResults.filter(r => r.result === 'LEAK DETECTED');
  res.json(alerts);
});

// ── MQTT client ───────────────────────────────────────────────────────────────
const client = mqtt.connect(BROKER, {
  clientId: CLIENT_ID,
  clean: true,
  reconnectPeriod: 5000,
});

client.on('connect', () => {
  console.log(chalk.green(`✔ Connected to MQTT broker: ${BROKER}`));
  client.subscribe(TOPIC_SENSOR, { qos: 1 }, (err) => {
    if (err) {
      console.error(chalk.red('✘ Subscribe error:'), err.message);
    } else {
      console.log(chalk.cyan(`👂 Subscribed to: ${TOPIC_SENSOR}`));
      console.log(chalk.cyan(`📡 Publishing alerts to: ${TOPIC_ALERTS}`));
      console.log(chalk.yellow(`🌐 Dashboard at: http://localhost:${PORT}`));
    }
  });
});

client.on('reconnect', () =>
  console.log(chalk.yellow('⟳ Reconnecting to broker...'))
);

client.on('error', (err) =>
  console.error(chalk.red('✘ MQTT error:'), err.message)
);

// ── Message handler ───────────────────────────────────────────────────────────
client.on('message', async (topic, payload) => {
  if (topic !== TOPIC_SENSOR) return;

  let reading;
  try {
    reading = JSON.parse(payload.toString());
  } catch {
    console.warn(chalk.yellow('⚠ Malformed payload — not valid JSON, skipping.'));
    return;
  }

  console.log(chalk.blue(`\n📥 Sensor reading received:`), reading);

  // ── Run Python inference ──────────────────────────────────────────────────
  let inferenceResult;
  try {
    inferenceResult = await runInference(reading);
  } catch (err) {
    console.error(chalk.red('✘ Inference error:'), err);
    return;
  }

  // ── Merge timestamp + location into result ────────────────────────────────
  const enriched = {
    ...inferenceResult,
    timestamp: new Date().toISOString(),
    sensor:    reading,
    threshold: THRESHOLD,
  };

  // ── Publish result to MQTT results topic ──────────────────────────────────
  client.publish(TOPIC_RESULTS, JSON.stringify(enriched), { qos: 1 });

  // ── Leak alert path ───────────────────────────────────────────────────────
  if (inferenceResult.probability >= THRESHOLD) {
    console.log(chalk.red.bold(
      `🚨 LEAK DETECTED — Confidence: ${inferenceResult.confidence} | Action: ${inferenceResult.action}`
    ));

    const alert = { ...enriched, alertId: `ALT-${Date.now()}` };

    // Publish to MQTT alert topic
    client.publish(TOPIC_ALERTS, JSON.stringify(alert), { qos: 2, retain: true });

    // Append to log file
    fs.appendFileSync(LOG_FILE, JSON.stringify(alert) + '\n');

    // Emit to dashboard
    io.emit('leak_alert', alert);
  } else {
    console.log(chalk.green(
      `✔ Normal — Confidence: ${inferenceResult.confidence}`
    ));
  }

  // Store + broadcast to dashboard
  recentResults.push(enriched);
  if (recentResults.length > 500) recentResults.shift();  // rolling window
  io.emit('reading', enriched);
});

// ── Python inference helper ───────────────────────────────────────────────────
function runInference(reading) {
  return new Promise((resolve, reject) => {
    const py     = spawn(PYTHON_CMD, [INFERENCE_PY]);
    let stdout   = '';
    let stderr   = '';

    py.stdout.on('data', (d) => (stdout += d.toString()));
    py.stderr.on('data', (d) => (stderr += d.toString()));

    py.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Python exited with code ${code}: ${stderr}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout.trim()));
      } catch {
        reject(new Error(`Could not parse Python output: ${stdout}`));
      }
    });

    py.stdin.write(JSON.stringify(reading));
    py.stdin.end();
  });
}

// ── Start HTTP server ─────────────────────────────────────────────────────────
server.listen(PORT, () => {
  console.log(chalk.green(`\n🚀 Water Leak Backend started`));
  console.log(`   Dashboard : http://localhost:${PORT}`);
  console.log(`   MQTT broker: ${BROKER}`);
  console.log(`   Sensor topic: ${TOPIC_SENSOR}\n`);
});
