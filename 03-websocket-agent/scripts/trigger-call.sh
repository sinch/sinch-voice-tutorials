#!/bin/bash
# Sinch WebSocket Agent — trigger an outbound call that streams audio to a WebSocket server.
# Dials DESTINATION_NUMBER; when answered, bridges the call audio to WS_ENDPOINT.

set -e

. "$(dirname "$0")/../../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"
: "${WS_ENDPOINT:?ERROR: WS_ENDPOINT is not set. Run ngrok and set e.g. wss://abc.ngrok-free.app}"

BASE_URL="https://voice.api.sinch.com/v2"

echo "Dialing ${DESTINATION_NUMBER} and streaming audio to ${WS_ENDPOINT} ..."

BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "name": "phone-leg",
      "from": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "to": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "dialTimeout": "30s",
      "maxDuration": "30m",
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "name": "stream-bridge" },
          {
            "command": "dial",
            "name": "stream-leg",
            "to": {
              "type": "STREAM",
              "stream": {
                "endpoint": "%s",
                "streamOptions": {
                  "version": 1,
                  "codec": "PCM",
                  "sampleRate": 8000
                },
                "callHeaders": [
                  { "key": "X-Tutorial", "value": "sinch-ws-agent" }
                ]
              }
            },
            "dialTimeout": "10s",
            "events": {
              "onAnswer": [{ "command": "bridgeCall", "name": "stream-bridge" }],
              "onHangup": [{ "command": "hangup", "callName": "phone-leg" }]
            }
          }
        ],
        "onHangup": [{ "command": "hangup", "callName": "stream-leg" }]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${DESTINATION_NUMBER}" "${WS_ENDPOINT}")

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "${BASE_URL}/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -d "${BODY}")

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 201 ]; then
  echo "Call created successfully (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
