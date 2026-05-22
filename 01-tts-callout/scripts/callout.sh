#!/bin/bash
# Sinch Voice Callout — dials a phone number, plays an audio file, then a TTS message via the Sinch Voice API.

set -e

# Load environment variables from .env if present (look two levels up for the project root .env)
. "$(dirname "$0")/../../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set. Copy .env.example to .env and fill in your credentials.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"

BASE_URL="https://voice.api.sinch.com/v2"

echo "Placing callout from ${SINCH_NUMBER} to ${DESTINATION_NUMBER} ..."

# Build the JSON body with shell variable expansion via printf
BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "name": "audio-notification",
      "from": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "to": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "dialTimeout": "30s",
      "maxDuration": "5m",
      "events": {
        "onAnswer": [
          {
            "command": "messages",
            "name": "notification",
            "messages": [
              {
                "type": "PLAY",
                "play": {
                  "url": "https://samplelib.com/mp3/sample-12s.mp3"
                }
              },
              {
                "type": "SAY",
                "say": {
                  "text": "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                  "voiceName": "Emma"
                }
              }
            ],
            "events": {
              "onFinish": [
                { "command": "hangup" }
              ]
            }
          }
        ]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${DESTINATION_NUMBER}")

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
