#!/bin/bash
# 3.4.5 AI IVR — patch a LIVE call to dial a human agent and bridge them in.
# This is the request the relay server sends automatically after it classifies
# the caller's intent; run it by hand to understand the PATCH in isolation.
#
# Usage:  bash patch-call.sh <callId> <sales|support>
#
# Reads the tutorial-folder .env (../.env relative to this scripts/ folder).

set -e

. "$(dirname "$0")/../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${SALES_NUMBER:?ERROR: SALES_NUMBER is not set.}"
: "${SUPPORT_NUMBER:?ERROR: SUPPORT_NUMBER is not set.}"

CALL_ID="${1:?Usage: patch-call.sh <callId> <sales|support>}"
INTENT="$(echo "${2:?Usage: patch-call.sh <callId> <sales|support>}" | tr '[:upper:]' '[:lower:]')"

case "${INTENT}" in
  sales)   AGENT_NUMBER="${SALES_NUMBER}";   LABEL="Sales" ;;
  support) AGENT_NUMBER="${SUPPORT_NUMBER}"; LABEL="Support" ;;
  *) echo "ERROR: intent must be 'sales' or 'support', got '${INTENT}'." >&2; exit 1 ;;
esac

BASE_URL="https://voice.api.sinch.com/v2"

BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "callName": "agent_call",
      "from": { "type": "PHONE", "phone": { "number": "%s" } },
      "to":   { "type": "PHONE", "phone": { "number": "%s" } },
      "dialTimeoutDurationSeconds": 20,
      "maxCallDurationSeconds": 3600,
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "ivr-bridge" },
          {
            "command": "messages",
            "messagesName": "agent-intro",
            "messages": [
              {
                "type": "SAY",
                "say": {
                  "format": "TEXT",
                  "text": "Connecting you to a customer. Intent: %s.",
                  "voiceName": "Tiffany"
                }
              }
            ]
          }
        ],
        "onHangup": [ { "command": "hangup", "callName": "caller" } ]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${AGENT_NUMBER}" "${LABEL}")

echo "Patching call ${CALL_ID}: dialing ${LABEL} agent ${AGENT_NUMBER} ..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X PATCH \
  -u "${KEY_ID}:${KEY_SECRET}" \
  -H "Idempotency-Key: ${CALL_ID}-${INTENT}" \
  "${BASE_URL}/projects/${PROJECT_ID}/calls/${CALL_ID}" \
  -H "Content-Type: application/json" \
  -d "${BODY}")

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 202 ]; then
  echo "Patch accepted (HTTP ${HTTP_CODE})."
  [ -n "${HTTP_BODY}" ] && echo "${HTTP_BODY}"
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
