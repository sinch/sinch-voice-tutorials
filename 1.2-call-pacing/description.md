# 1.2 Call Pacing (Batch Calls)

## Overview

The Voice API v2 supports **batch calling** for any scenario where you dial many recipients with the same call flow, such as appointment reminders, outage notifications, outbound campaigns, or survey waves. Instead of hand-writing one `POST /v2/projects/{projectId}/calls` request per recipient, you drive the same flow from a small list. This tutorial uses **two destinations** to keep things concrete. Each request carries:

- A `commands` array describing the call flow (with `@placeholder` references).
- A `parameters` object that fills the placeholders.
- A `batchOptions` object that controls **pacing**: `maxCps` (max calls per second) and `ttlSeconds` (how long the platform keeps trying to start queued calls).

Providing `parameters` puts the request into **batch mode**; `batchOptions` are only valid in that mode. Each request returns a `sessionId` plus a `batchId` you use to poll progress or stop the batch. Sinch initiates calls in the background, honoring `maxCps` so you don't overload your trunk or trip carrier rate limits.

## Setup

Export your credentials and the two destinations into the shell you'll run the examples from. Nothing here reads a `.env` file; the examples pick everything up from the environment.

```bash
export PROJECT_ID="your-project-id"
export KEY_ID="your-access-key-id"
export KEY_SECRET="your-access-key-secret"
export SINCH_NUMBER="+1XXXXXXXXXX"

# The two destinations to dial (E.164)
export DEST_1="+15551110001"
export DEST_2="+15551110002"

# Optional pacing (defaults shown)
export MAX_CPS=5
export TTL_SECONDS=1800
```

| Variable | Required | Where to get it | Notes |
| --- | --- | --- | --- |
| `PROJECT_ID` | yes | [Sinch Dashboard](https://dashboard.sinch.com) → your Voice project | |
| `KEY_ID` | yes | Dashboard → Access Keys | HTTP Basic username |
| `KEY_SECRET` | yes | Dashboard → Access Keys (shown once at creation) | HTTP Basic password |
| `SINCH_NUMBER` | yes | Dashboard → Numbers (a number assigned to the project) | Caller ID (`from`) |
| `DEST_1` | yes | Your own list | First destination, E.164 |
| `DEST_2` | yes | Your own list | Second destination, E.164 |
| `MAX_CPS` | optional | n/a | Defaults to `5` in the examples |
| `TTL_SECONDS` | optional | n/a | Defaults to `1800` in the examples |

Dependencies:
- **curl** (and optionally **jq** for pretty output) for the shell example.
- **Python**: `pip install requests` for the Python example.
- **Node 18+** for the Node example (uses built-in `fetch` and `crypto.randomUUID`).

## Create a batch call

Each example reads the exported variables and submits one batch request per destination, so you end up with two `batchId` values.

### Bash + curl

```bash
#!/bin/bash
# Submit one batch request per destination (two here) with pacing controls.
set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DEST_1:?ERROR: DEST_1 is not set.}"
: "${DEST_2:?ERROR: DEST_2 is not set.}"

BASE_URL="https://voice.api.sinch.com/v2"
MAX_CPS="${MAX_CPS:-5}"
TTL_SECONDS="${TTL_SECONDS:-1800}"

for RECIPIENT in "$DEST_1" "$DEST_2"; do
  BODY=$(printf '{
    "commands": [
      {
        "command": "dial",
        "callName": "batch-reminder",
        "from": { "type": "PHONE", "phone": { "number": "%s" } },
        "to":   { "type": "PHONE", "phone": { "number": "@toNumber" } },
        "dialTimeoutDurationSeconds": 30,
        "maxCallDurationSeconds": 120,
        "events": {
          "onAnswer": [
            {
              "command": "messages",
              "messages": [
                { "type": "SAY",
                  "say": { "text": "Hello, this is an automated reminder from Sinch. Goodbye.",
                           "voiceName": "Emma" } }
              ],
              "events": { "onFinish": [ { "command": "hangup" } ] }
            }
          ],
          "onHangup": [ { "command": "hangup" } ]
        }
      }
    ],
    "parameters": {
      "toNumber": "%s"
    },
    "batchOptions": {
      "maxCps": %d,
      "ttlSeconds": %d
    }
  }' "${SINCH_NUMBER}" "${RECIPIENT}" "${MAX_CPS}" "${TTL_SECONDS}")

  IDEMPOTENCY_KEY="$(command -v uuidgen >/dev/null && uuidgen || date +%s%N)"

  echo "Submitting batch to ${RECIPIENT} (maxCps=${MAX_CPS}, ttlSeconds=${TTL_SECONDS}) ..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -u "${KEY_ID}:${KEY_SECRET}" \
    "${BASE_URL}/projects/${PROJECT_ID}/calls" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
    -d "${BODY}")

  HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
  HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

  if [ "${HTTP_CODE}" -eq 201 ]; then
    echo "Batch created (HTTP ${HTTP_CODE}):"
    echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
  else
    echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
    echo "${HTTP_BODY}" >&2
    exit 1
  fi
done
```

### Python

```python
# Submit one batch request per destination (two here) with pacing controls.
# Requires: pip install requests

import json
import os
import sys
import uuid

import requests

PROJECT_ID   = os.environ.get("PROJECT_ID")
KEY_ID       = os.environ.get("KEY_ID")
KEY_SECRET   = os.environ.get("KEY_SECRET")
SINCH_NUMBER = os.environ.get("SINCH_NUMBER")

required = {
    "PROJECT_ID": PROJECT_ID, "KEY_ID": KEY_ID, "KEY_SECRET": KEY_SECRET,
    "SINCH_NUMBER": SINCH_NUMBER,
    "DEST_1": os.environ.get("DEST_1"), "DEST_2": os.environ.get("DEST_2"),
}
missing = [k for k, v in required.items() if not v]
if missing:
    print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)

recipients  = [os.environ["DEST_1"], os.environ["DEST_2"]]
max_cps     = int(os.environ.get("MAX_CPS", "5"))
ttl_seconds = int(os.environ.get("TTL_SECONDS", "1800"))

url = f"https://voice.api.sinch.com/v2/projects/{PROJECT_ID}/calls"

for recipient in recipients:
    payload = {
        "commands": [
            {
                "command": "dial",
                "callName": "batch-reminder",
                "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                "to":   {"type": "PHONE", "phone": {"number": "@toNumber"}},
                "dialTimeoutDurationSeconds": 30,
                "maxCallDurationSeconds": 120,
                "events": {
                    "onAnswer": [
                        {
                            "command": "messages",
                            "messages": [
                                {"type": "SAY",
                                 "say": {"text": "Hello, this is an automated reminder from Sinch. Goodbye.",
                                         "voiceName": "Emma"}}
                            ],
                            "events": {"onFinish": [{"command": "hangup"}]}
                        }
                    ],
                    "onHangup": [{"command": "hangup"}]
                }
            }
        ],
        # `parameters` is a single object of string->string, so each request
        # creates one queued call. Submit one request per destination.
        "parameters": {"toNumber": recipient},
        "batchOptions": {"maxCps": max_cps, "ttlSeconds": ttl_seconds},
    }

    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    }

    print(f"Submitting batch to {recipient} (maxCps={max_cps}, ttlSeconds={ttl_seconds}) ...")

    response = requests.post(url, json=payload, headers=headers, auth=(KEY_ID, KEY_SECRET))
    data = response.json()

    if response.status_code == 201:
        print("Batch created:")
        print(json.dumps(data, indent=2))
    else:
        print(f"ERROR {response.status_code}:", file=sys.stderr)
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)
```

### Node.js (18+)

```javascript
// Submit one batch request per destination (two here) with pacing controls.
// Node.js 18+ (built-in fetch and crypto.randomUUID).

import { randomUUID } from "crypto";

const required = ["PROJECT_ID", "KEY_ID", "KEY_SECRET", "SINCH_NUMBER", "DEST_1", "DEST_2"];
for (const name of required) {
  if (!process.env[name]) {
    console.error(`ERROR: ${name} is not set. Run the export commands above.`);
    process.exit(1);
  }
}

const { PROJECT_ID, KEY_ID, KEY_SECRET, SINCH_NUMBER } = process.env;
const recipients = [process.env.DEST_1, process.env.DEST_2];
const maxCps     = Number(process.env.MAX_CPS     || 5);
const ttlSeconds = Number(process.env.TTL_SECONDS || 1800);

const url = `https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/calls`;
const authHeader = "Basic " + Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString("base64");

for (const recipient of recipients) {
  const payload = {
    commands: [
      {
        command: "dial",
        callName: "batch-reminder",
        from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
        to:   { type: "PHONE", phone: { number: "@toNumber" } },
        dialTimeoutDurationSeconds: 30,
        maxCallDurationSeconds: 120,
        events: {
          onAnswer: [
            {
              command: "messages",
              messages: [
                { type: "SAY",
                  say: { text: "Hello, this is an automated reminder from Sinch. Goodbye.",
                         voiceName: "Emma" } }
              ],
              events: { onFinish: [{ command: "hangup" }] }
            }
          ],
          onHangup: [{ command: "hangup" }]
        }
      }
    ],
    // `parameters` is a single object of string->string, so each request
    // creates one queued call. Submit one request per destination.
    parameters: { toNumber: recipient },
    batchOptions: { maxCps, ttlSeconds }
  };

  console.log(`Submitting batch to ${recipient} (maxCps=${maxCps}, ttlSeconds=${ttlSeconds}) ...`);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: authHeader,
      "Content-Type": "application/json",
      "Idempotency-Key": randomUUID(),
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();

  if (response.status === 201) {
    console.log("Batch created:");
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`ERROR ${response.status}:`);
    console.error(JSON.stringify(data, null, 2));
    process.exit(1);
  }
}
```

### What success looks like

Each of the two `POST /v2/projects/{projectId}/calls` requests returns `201 Created` with its own `sessionId` and `batchId`:

```json
{
  "projectId": "5c5bf2b1-35ae-4825-ab89-457e07bb60e6",
  "serviceId": "6e124178-c29d-46a5-943c-5c2ae544aade",
  "sessionId": "01BX5ZZKBKACTAV9WEVGEMMVRB",
  "batchId":   "01BX5ZZKBKACTAV9WEVGEMMVRC"
}
```

The second request returns the same shape with a different `sessionId` and `batchId`. Copy both `batchId` values; you'll poll each one.

## Poll until a batch finishes

You now have two `batchId` values, one per destination. Poll each by exporting it in turn, then running the loop below. It reads `PROJECT_ID`, `KEY_ID`, `KEY_SECRET`, and `BATCH_ID` from the environment and prints the summary every 5 seconds until the batch reaches a final state.

```bash
export BATCH_ID=01BX5ZZKBKACTAV9WEVGEMMVRC   # first destination's batchId
```

```bash
#!/bin/bash
# Poll a batch summary every 5s until all calls reach a final state.
set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${BATCH_ID:?ERROR: BATCH_ID is not set. Run: export BATCH_ID=01...}"

URL="https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/batches/${BATCH_ID}"

while true; do
  BODY=$(curl -s -u "${KEY_ID}:${KEY_SECRET}" "${URL}")
  if command -v jq > /dev/null; then
    echo "$BODY" | jq '{batchId, callCount, completed, failed, inProgress, queued, endTime}'
    DONE=$(echo "$BODY" | jq -r 'if .queued==0 and .inProgress==0 then "yes" else "no" end')
  else
    echo "$BODY"
    DONE="no"
  fi
  if [ "$DONE" = "yes" ]; then
    echo "All calls finished."
    break
  fi
  sleep 5
done
```

Each batch here holds a single call, so the summary is small:

```json
{
  "batchId":     "01BX5ZZKBKACTAV9WEVGEMMVRC",
  "callCount":   1,
  "queued":      0,
  "inProgress":  0,
  "completed":   1,
  "failed":      0,
  "endTime":     "2025-02-10T09:05:00Z"
}
```

When `queued` and `inProgress` both reach `0`, `endTime` is set and the poll loop exits. Re-export `BATCH_ID` with the second value and run it again to check the other destination.

## How it works

### 1. Placeholders

`commands` is a normal SVAML payload, except any string value can reference a parameter with `@name` syntax. The API replaces each placeholder with the value from the matching `parameters` key before initiating the call.

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "reminder",
      "from": { "type": "PHONE", "phone": { "number": "+1XXXXXXXXXX" } },
      "to":   { "type": "PHONE", "phone": { "number": "@toNumber" } },
      "dialTimeoutDurationSeconds": 30,
      "events": {
        "onAnswer": [
          {
            "command": "messages",
            "messages": [
              { "type": "SAY",
                "say": { "text": "Hi @firstName, this is a reminder that your appointment is on @date.",
                         "voiceName": "Emma" } }
            ],
            "events": { "onFinish": [ { "command": "hangup" } ] }
          }
        ],
        "onHangup": [ { "command": "hangup" } ]
      }
    }
  ],
  "parameters": {
    "toNumber":  "+15551110001",
    "firstName": "Ada",
    "date":      "Tuesday March 5"
  },
  "batchOptions": {
    "maxCps": 5,
    "ttlSeconds": 1800
  }
}
```

`parameters` is a map of string keys (1-255 chars) to string values, each referenced in `commands` as `@key`. This is why each destination gets its own request: one `parameters` object per call. To personalize per destination (a different `firstName` or `date`), fill in that destination's values in its request.

### 2. Pacing (`batchOptions`)

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `maxCps` | integer (1-1000) | 1000 | Requested maximum call-initiation rate, in calls per second. Actual CPS may be lower depending on routing, carrier capacity, and account limits. |
| `ttlSeconds` | integer (1-10800) | 10800 (3 h) | How long the platform keeps trying to start queued calls. After TTL expires, queued (not-yet-initiated) calls are dropped; in-progress calls continue. |

Pick `maxCps` based on what your trunk and downstream agent pool can handle; pick `ttlSeconds` based on how time-sensitive the message is. (Verified against the `batchOptions` schema in the spec: field names, ranges, and defaults match.)

### 3. Monitor batch progress

`GET /v2/projects/{projectId}/batches/{batchId}` returns a `batchSummary`:

```bash
curl -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/batches/$BATCH_ID" | jq
```

```json
{
  "batchId":      "01BX5ZZKBKACTAV9WEVGEMMVRC",
  "callCount":    1,
  "queued":       0,
  "inProgress":   1,
  "completed":    0,
  "failed":       0,
  "requestedCps": 5,
  "ttlSeconds":   1800,
  "endTime":      null,
  "callSessions": [
    { "id": "01F8...", "status": "IN_PROGRESS" }
  ]
}
```

All fields above are verified against the `batchSummary` schema. Note `requestedCps` (not `maxCps`) is the field name in the summary. The per-session `status` enum is limited to `QUEUED`, `IN_PROGRESS`, `COMPLETED` (the top-level counts also include `failed`). The summary is populated incrementally; poll on a sensible cadence (for example, every 10 s for short batches, once a minute for hour-long ones).

> **Endpoint note (assumption to verify):** Two description strings in the spec call this `/batches/{batchId}/summary`, but the actual OpenAPI **path object** is `GET /v2/projects/{projectId}/batches/{batchId}`. This tutorial uses the path object, since that is what the API formally exposes. Confirm with the Voice team if a `/summary` suffix is also valid.

### 4. Stop the batch (optional)

```bash
curl -X DELETE -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/batches/$BATCH_ID"
```

`DELETE /v2/projects/{projectId}/batches/{batchId}` returns `202 Accepted` with a JSON body confirming the stop:

```json
{ "result": "Batch calls stopped successfully, unprocessed calls will not be initiated" }
```

It stops any queued (not-yet-initiated) calls. **Calls already in progress are not affected**; they continue until they end naturally. Each `batchId` is stopped independently, so cancel both if you need to abort both destinations.

### 5. Inspect individual sessions

For each `id` in `callSessions[]`, fetch session details:

```bash
curl -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/sessions/$SESSION_ID" | jq
```

The response includes a `calls[]` array, one entry per call leg, with fields like `callResult`, `callReason`, `startTime`, `answerTime`, and `endTime`. See [3.6 Track Call Status](../3.6-track-call-status/description.md) for a deeper walkthrough.

## Real-life examples

- **Appointment reminders**: TTS reminder to every patient with an appointment tomorrow. Set `maxCps: 5` so reminders trickle out over the morning instead of dialing 500 numbers in one second.
- **Outage notifications**: Notify all impacted customers in a region. Use a short `ttlSeconds` so calls that didn't reach anyone within the outage window aren't placed an hour later.
- **Survey waves**: Dispatch follow-up surveys after a release.
- **Dunning / collection campaigns**: Pace outbound attempts to comply with collection-call cadence regulations.

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Idempotency** | Always send the `Idempotency-Key` header on each request. A network retry must not double-dial a destination. UUID v4 recommended; the key must be 16-128 chars. All three examples set it automatically, and use a fresh key per destination. |
| **CPS choice** | Pick `maxCps` based on trunk capacity AND any downstream agent pool. If your IVR bridges to live agents, sustained CPS above agent availability just produces abandoned calls. |
| **TTL choice** | For time-sensitive messages (outage alerts), use a TTL just slightly longer than the relevance window. For non-urgent batches (reminders), longer TTLs absorb temporary carrier slowness. |
| **AMD / voicemail** | Insert an `amd` command before the `messages` block when the recipient might be a mobile that goes to voicemail. See [3.2 AMD](../3.2-amd/description.md). |
| **Recording compliance** | If recordings are required, insert `startRecording` inside `onAnswer`. The recording is per-session. See [3.3 Recording & Transcription](../3.3-recording-transcription/description.md). |
| **Failure observability** | Persist each `batchId` and `sessionId` to your CRM keyed by destination. After a batch ends, join `sessionId` back to the destination to report which messages reached whom. |
| **Per-recipient personalization** | `parameters` applies to the call created by that request. For per-destination text, fill in that destination's values in its own request (as the loop already does). |

## API reference (at a glance)

- `POST /v2/projects/{projectId}/calls`: body is `callRequest`, made of `commands` (required) plus optional `parameters` plus optional `batchOptions`. Providing `parameters` enables batch mode; `batchOptions` are only valid then. Returns `201` with `callResponse` (`projectId`, `serviceId`, `sessionId`, and `batchId` when batched).
- `parameters` (`requestParameters`): an **object** mapping string keys (1-255 chars) to string values, referenced in `commands` as `@key`. One object per request, so one queued call per request. (Spec narrative shows an array, flagged above as needing verification.)
- `batchOptions.maxCps`: integer 1-1000, default 1000.
- `batchOptions.ttlSeconds`: integer 1-10800, default 10800.
- `GET /v2/projects/{projectId}/batches/{batchId}`: returns `batchSummary` with `callCount`, `queued`, `inProgress`, `completed`, `failed`, `requestedCps`, `ttlSeconds`, `endTime`, and `callSessions[]` (`id`, `status` in {`QUEUED`, `IN_PROGRESS`, `COMPLETED`}).
- `DELETE /v2/projects/{projectId}/batches/{batchId}`: stops processing of queued calls; `202 Accepted` with a `{ "result": ... }` body.