-- ============================================================
-- Smart IoT Water Leak Detection System — Database Schema
-- Run this once against your MySQL server to set up the DB
-- Usage: mysql -u root -p < schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS wasac_leakdetection
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE wasac_leakdetection;

-- ── USER ──────────────────────────────────────────────────────────────────────
-- Homeowner accounts. One user can own multiple nodes.
CREATE TABLE IF NOT EXISTS user (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(80)  NOT NULL UNIQUE,
  email         VARCHAR(150) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  phone_number  VARCHAR(20)  NOT NULL,
  created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- ── HOUSEHOLD_NODE ────────────────────────────────────────────────────────────
-- One row per physical ESP32 device installed in the field.
CREATE TABLE IF NOT EXISTS household_node (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  user_id     INT          NOT NULL,
  device_id   VARCHAR(60)  NOT NULL UNIQUE,
  location    VARCHAR(200),
  latitude    DOUBLE,
  longitude   DOUBLE,
  status      ENUM('online','offline','error') DEFAULT 'offline',
  last_seen   DATETIME,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
);

-- ── SENSOR_READING ────────────────────────────────────────────────────────────
-- Every sensor packet received — this table grows large (one row per reading).
CREATE TABLE IF NOT EXISTS sensor_reading (
  id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
  node_id             INT     NOT NULL,
  timestamp           DATETIME NOT NULL,
  pressure            DOUBLE,
  flow_rate           DOUBLE,
  temperature         DOUBLE,
  vibration           DOUBLE,
  rpm                 DOUBLE,
  operational_hours   INT,
  latitude            DOUBLE,
  longitude           DOUBLE,
  ml_result           VARCHAR(30),
  ml_probability      DOUBLE,
  ml_confidence       VARCHAR(10),
  FOREIGN KEY (node_id) REFERENCES household_node(id) ON DELETE CASCADE,
  INDEX idx_node_time (node_id, timestamp)
);

-- ── ALERT_EVENT ───────────────────────────────────────────────────────────────
-- Logged every time an ML leak is detected. Tracks resolution.
CREATE TABLE IF NOT EXISTS alert_event (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  alert_id        VARCHAR(30)  NOT NULL UNIQUE,
  node_id         INT          NOT NULL,
  reading_id      BIGINT,
  triggered_at    DATETIME     NOT NULL,
  leak_type       ENUM('burst','drip','unknown') DEFAULT 'unknown',
  probability     DOUBLE,
  confidence      VARCHAR(10),
  action_taken    VARCHAR(200),
  sms_sent        TINYINT(1)   DEFAULT 0,
  shutoff_sent    TINYINT(1)   DEFAULT 0,
  is_resolved     TINYINT(1)   DEFAULT 0,
  resolved_at     DATETIME,
  notes           TEXT,
  FOREIGN KEY (node_id)    REFERENCES household_node(id) ON DELETE CASCADE,
  FOREIGN KEY (reading_id) REFERENCES sensor_reading(id) ON DELETE SET NULL
);

-- ── Default test user & node (used during development) ───────────────────────
-- Password: 'password123' — change this immediately in production
INSERT IGNORE INTO user (username, email, password_hash, phone_number)
VALUES ('lievin', 'l.murayire@alustudent.com',
        '$2b$10$placeholder_change_this_before_prod', '+250780000000');

INSERT IGNORE INTO household_node (user_id, device_id, location, latitude, longitude, status)
VALUES (1, 'esp32-node-001', 'Kigali - Kicukiro', -1.9441, 30.0619, 'online');
