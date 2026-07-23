#!/bin/bash
# 3.4.5 AI IVR — simulate an inbound call without a spare DID.
# Places an OUTBOUND call to DESTINATION_NUMBER (your own phone) and, once you
# answer, bridges in the Voice Relay leg exactly as the inbound STATIC behavior
# would. Answer the call and talk to the AI; it will patch in an agent.
#
# Usage:  bash test-callout.sh            # uses WS_ENDPOINT from .env
#         bash test-callout.sh wss://abc123.ngrok-free.app
#
# Reads the tutorial-folder .env (../.env relative to this scripts/ folder).

set -e

. "$(dirname "$0")/../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set (your phone, the 'caller').}"

WS_ENDPOINT="${1:-${WS_ENDPOINT:?ERROR: pass a wss:// URL or set WS_ENDPOINT in .env}}"

BASE_URL="https://voice.api.sinch.com/v2"

# Same shape as the inbound STATIC behavior, but the "caller" leg is an outbound
# dial to your phone so you can test end to end.
BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "callName": "caller",
      "from": { "type": "PHONE", "phone": { "number": "%s" } },
      "to":   { "type": "PHONE", "phone": { "number": "%s" } },
      "maxCallDurationSeconds": 600,
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "ivr-bridge" },
          {
            "command": "dial",
            "callName": "voice_relay_call",
            "to": {
              "type": "VOICE_RELAY",
              "voiceRelay": {
                "endpoint": "%s",
                "ttsVoice": "Tiffany",
                "sttLanguage": "en-US"
              }
            },
            "events": {
              "onAnswer": [ { "command": "bridgeCall", "bridgeName": "ivr-bridge" } ]
            }
          }
        ],
        "onHangup": [ { "command": "hangup", "callName": "voice_relay_call" } ]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${DESTINATION_NUMBER}" "${WS_ENDPOINT}")

echo "Calling ${DESTINATION_NUMBER} and bridging in the relay (${WS_ENDPOINT}) ..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "${BASE_URL}/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -d "${BODY}")

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 201 ]; then
  echo "Call created (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
