/**
 * db.js — MySQL connection pool
 * All database interactions go through this module.
 */

const mysql = require('mysql2/promise');

const pool = mysql.createPool({
  host: process.env.DB_HOST || 'localhost',
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || 'leakdetection',
  port: process.env.DB_PORT || 3306,
  waitForConnections: true,
  connectionLimit: 10,
  ssl: process.env.DB_HOST && process.env.DB_HOST !== 'localhost'
    ? { rejectUnauthorized: true }
    : undefined,
});

// ── Helpers ───────────────────────────────────────────────────────────────────

async function saveReading(reading, result, nodeId = 1) {
  const sql = `
    INSERT INTO sensor_reading
      (node_id, timestamp, pressure, flow_rate, temperature, vibration,
       rpm, operational_hours, latitude, longitude,
       ml_result, ml_probability, ml_confidence)
    VALUES (?, NOW(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `;
  const [res] = await pool.execute(sql, [
    nodeId,
    reading.Pressure        ?? null,
    reading.Flow_Rate       ?? null,
    reading.Temperature     ?? null,
    reading.Vibration       ?? null,
    reading.RPM             ?? null,
    reading.Operational_Hours ?? null,
    reading.Latitude        ?? null,
    reading.Longitude       ?? null,
    result.result           ?? null,
    result.probability      ?? null,
    result.confidence       ?? null,
  ]);
  return res.insertId;
}

async function saveAlert(alertId, nodeId, readingId, result) {
  const prob = result.probability ?? 0;
  const leakType = prob >= 0.8 ? 'burst' : 'drip';

  const sql = `
    INSERT INTO alert_event
      (alert_id, node_id, reading_id, triggered_at, leak_type,
       probability, confidence, action_taken)
    VALUES (?, ?, ?, NOW(), ?, ?, ?, ?)
  `;
  await pool.execute(sql, [
    alertId, nodeId, readingId, leakType,
    result.probability ?? null,
    result.confidence  ?? null,
    result.action      ?? null,
  ]);
}

async function markSmsSent(alertId) {
  await pool.execute(
    'UPDATE alert_event SET sms_sent = 1 WHERE alert_id = ?', [alertId]
  );
}

async function markShutoffSent(alertId) {
  await pool.execute(
    'UPDATE alert_event SET shutoff_sent = 1 WHERE alert_id = ?', [alertId]
  );
}

async function resolveAlert(alertId, notes = '') {
  await pool.execute(
    'UPDATE alert_event SET is_resolved = 1, resolved_at = NOW(), notes = ? WHERE alert_id = ?',
    [notes, alertId]
  );
}

async function getRecentReadings(limit = 100) {
  const [rows] = await pool.execute(
    `SELECT * FROM sensor_reading ORDER BY timestamp DESC LIMIT ?`,
    [limit]
  );
  return rows;
}

async function getAlerts(resolvedOnly = false) {
  const where = resolvedOnly
    ? 'WHERE is_resolved = 1'
    : 'WHERE is_resolved = 0';
  const [rows] = await pool.execute(
    `SELECT * FROM alert_event ${where} ORDER BY triggered_at DESC LIMIT 200`
  );
  return rows;
}

async function updateNodeStatus(deviceId, status) {
  await pool.execute(
    'UPDATE household_node SET status = ?, last_seen = NOW() WHERE device_id = ?',
    [status, deviceId]
  );
}

async function testConnection() {
  try {
    await pool.query('SELECT 1');
    return true;
  } catch {
    return false;
  }
}

module.exports = {
  pool,
  saveReading,
  saveAlert,
  markSmsSent,
  markShutoffSent,
  resolveAlert,
  getRecentReadings,
  getAlerts,
  updateNodeStatus,
  testConnection,
};
