/**
 * sms.js — Africa's Talking SMS gateway for leak alerts
 * Docs: https://developers.africastalking.com/docs/sms/sending
 */

const AfricasTalking = require('africastalking');

let smsClient = null;

function getSmsClient() {
  if (!smsClient) {
    const at = AfricasTalking({
      username: process.env.AT_USERNAME || 'sandbox',
      apiKey:   process.env.AT_API_KEY  || '',
    });
    smsClient = at.SMS;
  }
  return smsClient;
}

async function sendLeakAlert(reading, result, alertId) {
  const numbers = (process.env.ALERT_PHONE_NUMBERS || '')
    .split(',')
    .map(n => n.trim())
    .filter(Boolean);

  if (!numbers.length) {
    console.warn('⚠ No phone numbers configured in ALERT_PHONE_NUMBERS — skipping SMS');
    return false;
  }

  const prob = ((result.probability ?? 0) * 100).toFixed(1);
  const message =
    `🚨 WATER LEAK ALERT [${alertId}]\n` +
    `Confidence: ${prob}%\n` +
    `Pressure: ${reading.Pressure} bar | Flow: ${reading.Flow_Rate} L/min\n` +
    `Action: ${result.action}\n` +
    `Time: ${new Date().toLocaleString('en-RW', { timeZone: 'Africa/Kigali' })}`;

  try {
    const res = await getSmsClient().send({
      to:      numbers,
      message,
      from:    undefined,
    });
    console.log(`📱 SMS sent to ${numbers.join(', ')}`);
    return true;
  } catch (err) {
    console.error('✘ SMS send failed:', err.message);
    return false;
  }
}

module.exports = { sendLeakAlert };
