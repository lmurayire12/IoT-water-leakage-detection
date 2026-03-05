/**
 * index.js — Water Leak Detection MQTT Server
 * ─────────────────────────────────────────────
 * Subscribes to ESP32 sensor readings, runs ML inference,
 * saves to MySQL, sends SMS alerts, triggers auto-shutoff,
 * and serves a real-time dashboard via Socket.io.
 */

require('dotenv').config();
const mqtt            = require('mqtt');
const { spawn }       = require('child_process');
const path            = require('path');
const express         = require('express');
const http            = require('http');
const { Server }      = require('socket.io');
const chalk           = require('chalk');
const fs              = require('fs');
const db              = require('./db');
const { sendLeakAlert } = require('./sms');

// ── Config ────────────────────────────────────────────────────────────────────
const BROKER         = process.env.MQTT_BROKER    || 'mqtt://broker.hivemq.com:1883';
const CLIENT_ID      = process.env.MQTT_CLIENT_ID || 'leak-server-001';
const TOPIC_SENSOR   = process.env.TOPIC_SENSOR   || 'iot/sensor/water';
const TOPIC_ALERTS   = process.env.TOPIC_ALERTS   || 'iot/alerts/leak';
const TOPIC_RESULTS  = process.env.TOPIC_RESULTS  || 'iot/results';
const TOPIC_SHUTOFF  = process.env.TOPIC_SHUTOFF  || 'iot/commands/shutoff';
const PYTHON_CMD     = process.env.PYTHON_CMD     || 'python';
const THRESHOLD      = parseFloat(process.env.LEAK_THRESHOLD || '0.5');
const PORT           = parseInt(process.env.PORT  || '3000');
const INFERENCE_PY   = path.join(__dirname, 'inference.py');
const LOG_FILE       = path.join(__dirname, 'alerts.log');
const DEFAULT_NODE   = 1;  // household_node.id used when device_id not in payload

// ── Express + Socket.io ───────────────────────────────────────────────────────
const app    = express();
const server = http.createServer(app);
const io     = new Server(server);

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Runtime cache for dashboard (lost on restart — DB is the source of truth)
const recentResults = [];

// ── REST API ──────────────────────────────────────────────────────────────────

// Latest 100 readings (from DB if available, else runtime cache)
app.get('/api/results', async (_req, res) => {
  try {
    const rows = await db.getRecentReadings(100);
    res.json(rows);
  } catch {
    res.json(recentResults.slice(-100));
  }
});

// Active (unresolved) alerts
app.get('/api/alerts', async (_req, res) => {
  try {
    const rows = await db.getAlerts(false);
    res.json(rows);
  } catch {
    res.json(recentResults.filter(r => r.result === 'LEAK DETECTED').slice(-50));
  }
});

// Resolve an alert — PATCH /api/alerts/:alertId/resolve
app.patch('/api/alerts/:alertId/resolve', async (req, res) => {
  const { alertId } = req.params;
  const { notes }   = req.body;
  try {
    await db.resolveAlert(alertId, notes || '');
    io.emit('alert_resolved', { alertId });
    res.json({ success: true, alertId });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
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
      console.log(chalk.cyan(`👂 Subscribed to  : ${TOPIC_SENSOR}`));
      console.log(chalk.cyan(`📡 Alerts topic   : ${TOPIC_ALERTS}`));
      console.log(chalk.cyan(`🔌 Shutoff topic  : ${TOPIC_SHUTOFF}`));
      console.log(chalk.yellow(`🌐 Dashboard      : http://localhost:${PORT}`));
    }
  });
});

client.on('reconnect', () => console.log(chalk.yellow('⟳ Reconnecting to broker...')));
client.on('error',     (err) => console.error(chalk.red('✘ MQTT error:'), err.message));

// ── Message handler ───────────────────────────────────────────────────────────
client.on('message', async (topic, payload) => {
  if (topic !== TOPIC_SENSOR) return;

  let reading;
  try {
    reading = JSON.parse(payload.toString());
  } catch {
    console.warn(chalk.yellow('⚠ Malformed JSON payload — skipping.'));
    return;
  }

  console.log(chalk.blue(`\n📥 Sensor reading:`), reading);

  // ── ML Inference ─────────────────────────────────────────────────────────
  let result;
  try {
    result = await runInference(reading);
  } catch (err) {
    console.error(chalk.red('✘ Inference error:'), err.message);
    return;
  }

  const enriched = {
    ...result,
    timestamp: new Date().toISOString(),
    sensor:    reading,
    threshold: THRESHOLD,
  };

  // ── Persist reading to MySQL ──────────────────────────────────────────────
  let readingId = null;
  try {
    readingId = await db.saveReading(reading, result, DEFAULT_NODE);
    await db.updateNodeStatus(reading.device_id || 'esp32-node-001', 'online');
  } catch (err) {
    console.warn(chalk.yellow('⚠ DB save failed (running without DB):'), err.message);
  }

  // ── Publish result to MQTT ────────────────────────────────────────────────
  client.publish(TOPIC_RESULTS, JSON.stringify(enriched), { qos: 1 });

  // ── Leak path ─────────────────────────────────────────────────────────────
  if (result.probability >= THRESHOLD) {
    const alertId = `ALT-${Date.now()}`;
    const alert   = { ...enriched, alertId };

    console.log(chalk.red.bold(
      `🚨 LEAK — Confidence: ${result.confidence} | ${result.action}`
    ));

    // 1) MQTT alert topic
    client.publish(TOPIC_ALERTS, JSON.stringify(alert), { qos: 2, retain: true });

    // 2) Auto-shutoff command to ESP32
    const shutoffCmd = JSON.stringify({ command: 'SHUTOFF', alertId, timestamp: enriched.timestamp });
    client.publish(TOPIC_SHUTOFF, shutoffCmd, { qos: 2 });
    console.log(chalk.red(`🔌 Shutoff command sent → ${TOPIC_SHUTOFF}`));

    // 3) Persist alert to MySQL
    try {
      await db.saveAlert(alertId, DEFAULT_NODE, readingId, result);
      await db.markShutoffSent(alertId);
    } catch (err) {
      console.warn(chalk.yellow('⚠ DB alert save failed:'), err.message);
    }

    // 4) SMS via Africa's Talking
    try {
      const smsSent = await sendLeakAlert(reading, result, alertId);
      if (smsSent) await db.markSmsSent(alertId);
    } catch (err) {
      console.warn(chalk.yellow('⚠ SMS failed:'), err.message);
    }

    // 5) Append to flat log file (backup)
    fs.appendFileSync(LOG_FILE, JSON.stringify(alert) + '\n');

    // 6) Push to dashboard
    io.emit('leak_alert', alert);

  } else {
    console.log(chalk.green(`✔ Normal — ${result.confidence}`));
  }

  // ── Broadcast reading to dashboard ────────────────────────────────────────
  recentResults.push(enriched);
  if (recentResults.length > 500) recentResults.shift();
  io.emit('reading', enriched);
});

// ── Python inference helper ───────────────────────────────────────────────────
function runInference(reading) {
  return new Promise((resolve, reject) => {
    const py   = spawn(PYTHON_CMD, [INFERENCE_PY]);
    let stdout = '';
    let stderr = '';

    py.stdout.on('data', (d) => (stdout += d.toString()));
    py.stderr.on('data', (d) => (stderr += d.toString()));

    py.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Python exited ${code}: ${stderr}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout.trim()));
      } catch {
        reject(new Error(`Bad Python output: ${stdout}`));
      }
    });

    py.stdin.write(JSON.stringify(reading));
    py.stdin.end();
  });
}

// ── Start server ──────────────────────────────────────────────────────────────
server.listen(PORT, async () => {
  console.log(chalk.green(`\n🚀 Water Leak Backend running`));
  console.log(`   Dashboard  : http://localhost:${PORT}`);
  console.log(`   Broker     : ${BROKER}`);

  const dbOk = await db.testConnection();
  if (dbOk) {
    console.log(chalk.green('   Database   : ✔ MySQL connected'));
  } else {
    console.log(chalk.yellow('   Database   : ⚠ MySQL not connected — running without persistence'));
    console.log(chalk.yellow('   → Set DB_* vars in .env and run: mysql -u root -p < schema.sql'));
  }
  console.log('');
});
