#!/bin/bash
# Sinch Number Masking — trigger a programmatic bridge call via the API.
# This dials both Party A and Party B and bridges them, masking each other's real number.

set -e

. "$(dirname "$0")/../../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"

# PARTY_A_NUMBER: the number to dial first (Party A). Override via env or set below.
PARTY_A_NUMBER="${PARTY_A_NUMBER:-${DESTINATION_NUMBER}}"
PARTY_B_NUMBER="${PARTY_B_NUMBER:-${SINCH_NUMBER}}"

BASE_URL="https://voice.api.sinch.com/v2"

echo "Initiating masked bridge call between ${PARTY_A_NUMBER} and ${PARTY_B_NUMBER} ..."
echo "(Both parties will see ${SINCH_NUMBER} as the caller ID)"

BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "name": "party-a",
      "from": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "to": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "dialTimeout": "30s",
      "events": {
        "onAnswer": [
          {
            "command": "messages",
            "name": "greeting",
            "messages": [
              {
                "type": "SAY",
                "say": {
                  "text": "Please hold while we connect the other party.",
                  "voiceName": "Emma"
                }
              }
            ]
          },
          { "command": "bridgeCall", "name": "masked-bridge" },
          {
            "command": "dial",
            "name": "party-b",
            "from": {
              "type": "PHONE",
              "phone": { "number": "%s" }
            },
            "to": {
              "type": "PHONE",
              "phone": { "number": "%s" }
            },
            "dialTimeout": "30s",
            "events": {
              "onAnswer": [{ "command": "bridgeCall", "name": "masked-bridge" }],
              "onHangup": [{ "command": "hangup", "callName": "party-a" }]
            }
          }
        ],
        "onHangup": [{ "command": "hangup", "callName": "party-b" }]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${PARTY_A_NUMBER}" "${SINCH_NUMBER}" "${PARTY_B_NUMBER}")

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "${BASE_URL}/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -d "${BODY}")

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 201 ]; then
  echo "Bridge call created successfully (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
