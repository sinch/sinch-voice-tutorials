#!/bin/bash
# Sinch Recording & Transcription — trigger an outbound call with inline recording SVAML.
# The call is recorded immediately when answered; the file is uploaded to cloud storage.

set -e

. "$(dirname "$0")/../../.env" 2>/dev/null || true

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"
: "${STORAGE_DESTINATION_URL:?ERROR: STORAGE_DESTINATION_URL is not set (e.g. s3://my-bucket/recordings/).}"
: "${STORAGE_CREDENTIALS:?ERROR: STORAGE_CREDENTIALS is not set (e.g. ACCESS_KEY:SECRET:REGION).}"

# Detect storage provider from the destination URL prefix
if echo "${STORAGE_DESTINATION_URL}" | grep -q "^s3://"; then
  STORAGE_DESTINATION="AWS"
elif echo "${STORAGE_DESTINATION_URL}" | grep -q "^gs://"; then
  STORAGE_DESTINATION="GCP"
else
  STORAGE_DESTINATION="AZURE"
fi

BASE_URL="https://voice.api.sinch.com/v2"

echo "Calling ${DESTINATION_NUMBER} with recording enabled (${STORAGE_DESTINATION}) ..."

BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "name": "recorded-call",
      "from": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "to": {
        "type": "PHONE",
        "phone": { "number": "%s" }
      },
      "dialTimeout": "30s",
      "maxDuration": "1h",
      "events": {
        "onAnswer": [
          {
            "command": "startRecording",
            "name": "main-recording",
            "recordingOptions": {
              "format": "MP3",
              "recordingType": "COMBINED",
              "destination": "%s",
              "destinationUrl": "%s",
              "credentials": "%s",
              "transcriptionOptions": {
                "isEnabled": true,
                "locale": "en-US"
              }
            }
          },
          {
            "command": "messages",
            "name": "recording-notice",
            "messages": [
              {
                "type": "SAY",
                "say": {
                  "text": "This call is being recorded.",
                  "voiceName": "Emma"
                }
              }
            ]
          }
        ],
        "onHangup": [
          { "command": "stopRecording", "name": "main-recording" }
        ]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${DESTINATION_NUMBER}" \
   "${STORAGE_DESTINATION}" "${STORAGE_DESTINATION_URL}" "${STORAGE_CREDENTIALS}")

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "${BASE_URL}/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -d "${BODY}")

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 201 ]; then
  echo "Call created with recording (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
  echo ""
  echo "Recording will be uploaded to: ${STORAGE_DESTINATION_URL}"
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
