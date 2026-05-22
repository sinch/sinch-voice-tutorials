#!/bin/bash
# Sinch AMD Callout — makes an outbound call with Answering Machine Detection (AMD).
# AMD detects human vs. machine and fires different SVAML commands for each outcome.

set -e

. "$(dirname "$0")/../../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"

BASE_URL="https://voice.api.sinch.com/v2"

echo "Placing AMD callout from ${SINCH_NUMBER} to ${DESTINATION_NUMBER} ..."

BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "name": "amd-call",
      "from": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "to": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "dialTimeout": "45s",
      "maxDuration": "5m",
      "events": {
        "onAnswer": [
          {
            "command": "amd",
            "events": {
              "onHuman": [
                {
                  "command": "messages",
                  "name": "human-greeting",
                  "messages": [
                    {
                      "type": "SAY",
                      "say": {
                        "text": "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                        "voiceName": "Emma"
                      }
                    }
                  ],
                  "events": {
                    "onFinish": [{ "command": "hangup" }]
                  }
                }
              ],
              "onMachine": [
                { "command": "hangup" }
              ],
              "onBeep": [
                {
                  "command": "messages",
                  "name": "voicemail-message",
                  "messages": [
                    {
                      "type": "SAY",
                      "say": {
                        "text": "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                        "voiceName": "Emma"
                      }
                    }
                  ],
                  "events": {
                    "onFinish": [{ "command": "hangup" }]
                  }
                }
              ],
              "onUnknown": [
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
  echo "AMD call created successfully (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
