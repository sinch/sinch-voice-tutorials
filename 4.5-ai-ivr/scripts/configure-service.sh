#!/bin/bash
# 3.4.5 AI IVR — set the service's STATIC call behavior so every inbound call is
# answered, bridged, and dialed out to the Voice Relay leg (your relay server).
#
# Usage:  bash configure-service.sh            # uses WS_ENDPOINT from .env
#         bash configure-service.sh wss://abc123.ngrok-free.app
#
# Reads the tutorial-folder .env (../.env relative to this scripts/ folder).

set -e

. "$(dirname "$0")/../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SERVICE_ID:?ERROR: SERVICE_ID is not set (the service that owns your Sinch number).}"

WS_ENDPOINT="${1:-${WS_ENDPOINT:?ERROR: pass a wss:// URL or set WS_ENDPOINT in .env}}"

BASE_URL="https://voice.api.sinch.com/v2"

BODY=$(printf '{
  "callBehavior": {
    "type": "STATIC",
    "static": {
      "callName": "caller",
      "commands": [
        { "command": "answer" },
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
      "events": {
        "onHangup": [ { "command": "hangup", "callName": "voice_relay_call" } ]
      }
    }
  }
}' "${WS_ENDPOINT}")

echo "Setting STATIC AI-IVR behavior on service ${SERVICE_ID} (relay -> ${WS_ENDPOINT}) ..."

curl -s -X PATCH \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "${BASE_URL}/projects/${PROJECT_ID}/services/${SERVICE_ID}" \
  -H "Content-Type: application/json" \
  -d "${BODY}" | (command -v jq > /dev/null && jq '.' || cat)
  
