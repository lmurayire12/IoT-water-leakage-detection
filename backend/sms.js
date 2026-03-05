/**
 * sms.js — Africa's Talking SMS gateway for leak alerts
 * Docs: https://developers.africastalking.com/docs/sms/sending
 */

'use strict';

require('dotenv').config();
const AfricasTalking = require('africastalking');

const at = AfricasTalking({
  apiKey   : process.env.AT_API_KEY,
  username : process.env.AT_USERNAME || 'sandbox',
});

const sms = at.SMS;

/**
 * Send a leak alert SMS to all configured phone numbers
 * @param {object} payload  - sensor reading that triggered the alert
 * @param {string} confidence - e.g. "80.2%"
 * @param {string} alertType  - e.g. "BURST_PIPE" | "SLOW_DRIP"
 */
async function sendLeakAlert(payload, confidence, alertType = 'LEAK_DETECTED') {
  try {
    const numbers = (process.env.ALERT_PHONE_NUMBERS || '')
      .split(',')
      .map(n => n.trim())
      .filter(Boolean);

    if (numbers.length === 0) {
      console.warn('[SMS] No phone numbers configured in ALERT_PHONE_NUMBERS');
      return;
    }

    const time = new Date().toLocaleString('en-RW', { timeZone: 'Africa/Kigali' });

    const message =
      `🚨 WATER LEAK ALERT\n` +
      `Time     : ${time}\n` +
      `Type     : ${alertType}\n` +
      `Pressure : ${payload.Pressure ?? 'N/A'} bar\n` +
      `Flow Rate: ${payload.Flow_Rate ?? 'N/A'} L/min\n` +
      `Zone     : ${payload.Zone ?? 'N/A'}\n` +
      `Location : ${payload.Location_Code ?? 'N/A'}\n` +
      `Confidence: ${confidence}\n` +
      `Action   : Check your pipes immediately.`;

    const result = await sms.send({
      to      : numbers,
      message : message,
    });

    console.log(`[SMS] ✅ Alert sent to ${numbers.join(', ')}`);
    console.log(`[SMS] Response:`, JSON.stringify(result.SMSMessageData.Recipients));
  } catch (err) {
    console.error('[SMS] ❌ Failed to send alert:', err.message);
  }
}

module.exports = { sendLeakAlert };
