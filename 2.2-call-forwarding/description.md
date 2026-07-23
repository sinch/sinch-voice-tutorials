# Call Forwarding

## Overview

Call forwarding redirects a call from the originally-dialed party to a different destination: unconditionally, after a failure (no answer, busy, reject), at certain times of day, or mid-conversation via a transfer.

Voice API v2 has **no dedicated `forward` or `transfer` command**. Every variant is built from three primitives:

- **`dial`** creates a new outbound leg in the same session.
- **`bridgeCall`** joins two legs together for two-way audio (the bridge is created on first reference, joined on second).
- **`hangup` with `callName: "…"`** drops a specific named leg (the key to blind transfers and forwarding loops).

For dynamic forwarding rules (per-caller, time-of-day, presence-based), the service-level webhook callback, and mid-call the `webhook` SVAML command, let your backend decide the destination at runtime.

---

## Quick start: your first forward (no-answer fallback)

The fastest end-to-end success is an **outbound CFNA test**: your platform calls *you*, then dials a primary number that you let ring out, and watches it fall through to a fallback. This needs **no inbound number, no server, and no ngrok**, just a single `POST /calls`. Start here, then graduate to the inbound/webhook patterns below.

### 1. Set your environment variables

All the examples in this tutorial read configuration from environment variables. Export them in the shell session where you run the code. Auth is **HTTP Basic** (`KEY_ID:KEY_SECRET`).

```bash
# Auth & project
export PROJECT_ID="your-project-id"           # Sinch dashboard → your project
export KEY_ID="your-key-id"                    # Dashboard → Access keys
export KEY_SECRET="your-key-secret"            # Dashboard → Access keys
export SERVICE_ID="your-service-id"            # Dashboard → Voice services

# Numbers (all E.164)
export SINCH_NUMBER="+15551234567"             # Your Sinch virtual number
export CALLER_NUMBER="+15550009999"            # Your own mobile (answer this leg)
export PRIMARY_NUMBER="+15557770001"           # First destination (let this ring out)
export FALLBACK_NUMBER="+15557770002"          # No-answer fallback (should ring next)

# Time-of-day settings (Pattern 3)
export BUSINESS_START_HOUR_UTC="8"             # Integer 0-23, UTC
export BUSINESS_END_HOUR_UTC="18"              # Integer 0-23, UTC

# Webhook URL (inbound patterns)
export CALLBACK_URL="https://your-ngrok-url"   # ngrok http 3000
```

| Variable | Used by | Where to get it |
| --- | --- | --- |
| `PROJECT_ID` | all | [Sinch dashboard](https://dashboard.sinch.com) → your project |
| `KEY_ID` / `KEY_SECRET` | all (Basic auth) | Dashboard → Access keys |
| `SERVICE_ID` | inbound patterns (service PATCH) | Dashboard → Voice services, or `GET /v2/projects/{projectId}/services` |
| `SINCH_NUMBER` | all (caller-ID on forwarded legs) | Dashboard → your virtual number, E.164 |
| `CALLER_NUMBER` | quick-start (the phone that "rings") | Your own mobile, E.164 |
| `PRIMARY_NUMBER` | CFNA + time-of-day | The first number tried, E.164 |
| `FALLBACK_NUMBER` | CFNA + time-of-day | The no-answer fallback, E.164 |
| `BUSINESS_START_HOUR_UTC` | time-of-day (default `8`) | Integer 0-23, UTC |
| `BUSINESS_END_HOUR_UTC` | time-of-day (default `18`) | Integer 0-23, UTC |
| `CALLBACK_URL` | inbound/webhook patterns | Your public ngrok URL |

### 2. Run the outbound CFNA call

This places an outbound call to your `CALLER_NUMBER`, plays a hold prompt, dials the `PRIMARY_NUMBER`, and on timeout falls through to `FALLBACK_NUMBER`. Both targets join the same bridge as the caller.

#### Bash (curl)

```bash
IDEMPOTENCY_KEY="$(uuidgen 2>/dev/null || date +%s%N)"

curl -s -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d "{
  \"commands\": [
    {
      \"command\": \"dial\",
      \"callName\": \"caller\",
      \"from\": { \"type\": \"PHONE\", \"phone\": { \"number\": \"${SINCH_NUMBER}\" } },
      \"to\":   { \"type\": \"PHONE\", \"phone\": { \"number\": \"${CALLER_NUMBER}\" } },
      \"dialTimeoutDurationSeconds\": 30,
      \"events\": {
        \"onAnswer\": [
          { \"command\": \"messages\", \"messagesName\": \"hold\",
            \"messages\": [ { \"type\": \"SAY\",
              \"say\": { \"text\": \"Connecting your call.\", \"voiceName\": \"Emma\" } } ] },
          {
            \"command\": \"dial\",
            \"callName\": \"primary\",
            \"from\": { \"type\": \"PHONE\", \"phone\": { \"number\": \"${SINCH_NUMBER}\" } },
            \"to\":   { \"type\": \"PHONE\", \"phone\": { \"number\": \"${PRIMARY_NUMBER}\" } },
            \"dialTimeoutDurationSeconds\": 20,
            \"events\": {
              \"onAnswer\": [
                { \"command\": \"stopMessages\", \"messagesName\": \"hold\" },
                { \"command\": \"bridgeCall\",   \"bridgeName\": \"fwd-bridge\" }
              ],
              \"onTimeout\": [
                {
                  \"command\": \"dial\",
                  \"callName\": \"fallback\",
                  \"from\": { \"type\": \"PHONE\", \"phone\": { \"number\": \"${SINCH_NUMBER}\" } },
                  \"to\":   { \"type\": \"PHONE\", \"phone\": { \"number\": \"${FALLBACK_NUMBER}\" } },
                  \"dialTimeoutDurationSeconds\": 20,
                  \"events\": {
                    \"onAnswer\": [
                      { \"command\": \"stopMessages\", \"messagesName\": \"hold\" },
                      { \"command\": \"bridgeCall\",   \"bridgeName\": \"fwd-bridge\" }
                    ],
                    \"onTimeout\": [ { \"command\": \"hangup\", \"callName\": \"caller\" } ]
                  }
                }
              ]
            }
          }
        ],
        \"onHangup\": [ { \"command\": \"hangup\" } ]
      }
    }
  ]
}" | jq '.'
```

#### Python (requests)

```python
import os
import uuid
import requests

PROJECT_ID     = os.environ["PROJECT_ID"]
KEY_ID         = os.environ["KEY_ID"]
KEY_SECRET     = os.environ["KEY_SECRET"]
SINCH_NUMBER   = os.environ["SINCH_NUMBER"]
CALLER_NUMBER  = os.environ.get("CALLER_NUMBER", os.environ.get("DESTINATION_NUMBER"))
PRIMARY_NUMBER = os.environ["PRIMARY_NUMBER"]
FALLBACK_NUMBER = os.environ["FALLBACK_NUMBER"]

body = {
    "commands": [
        {
            "command": "dial",
            "callName": "caller",
            "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
            "to":   {"type": "PHONE", "phone": {"number": CALLER_NUMBER}},
            "dialTimeoutDurationSeconds": 30,
            "events": {
                "onAnswer": [
                    {
                        "command": "messages",
                        "messagesName": "hold",
                        "messages": [{"type": "SAY", "say": {"text": "Connecting your call.", "voiceName": "Emma"}}],
                    },
                    {
                        "command": "dial",
                        "callName": "primary",
                        "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                        "to":   {"type": "PHONE", "phone": {"number": PRIMARY_NUMBER}},
                        "dialTimeoutDurationSeconds": 20,
                        "events": {
                            "onAnswer": [
                                {"command": "stopMessages", "messagesName": "hold"},
                                {"command": "bridgeCall",   "bridgeName": "fwd-bridge"},
                            ],
                            "onTimeout": [
                                {
                                    "command": "dial",
                                    "callName": "fallback",
                                    "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                                    "to":   {"type": "PHONE", "phone": {"number": FALLBACK_NUMBER}},
                                    "dialTimeoutDurationSeconds": 20,
                                    "events": {
                                        "onAnswer": [
                                            {"command": "stopMessages", "messagesName": "hold"},
                                            {"command": "bridgeCall",   "bridgeName": "fwd-bridge"},
                                        ],
                                        "onTimeout": [{"command": "hangup", "callName": "caller"}],
                                    },
                                }
                            ],
                        },
                    },
                ],
                "onHangup": [{"command": "hangup"}],
            },
        }
    ]
}

resp = requests.post(
    f"https://voice.api.sinch.com/v2/projects/{PROJECT_ID}/calls",
    auth=(KEY_ID, KEY_SECRET),
    headers={
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    },
    json=body,
)

print(resp.status_code, resp.json())
```

#### Node.js (fetch)

```javascript
import { randomUUID } from "crypto";

const PROJECT_ID      = process.env.PROJECT_ID;
const KEY_ID          = process.env.KEY_ID;
const KEY_SECRET      = process.env.KEY_SECRET;
const SINCH_NUMBER    = process.env.SINCH_NUMBER;
const CALLER_NUMBER   = process.env.CALLER_NUMBER || process.env.DESTINATION_NUMBER;
const PRIMARY_NUMBER  = process.env.PRIMARY_NUMBER;
const FALLBACK_NUMBER = process.env.FALLBACK_NUMBER;

const body = {
  commands: [
    {
      command: "dial",
      callName: "caller",
      from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
      to:   { type: "PHONE", phone: { number: CALLER_NUMBER } },
      dialTimeoutDurationSeconds: 30,
      events: {
        onAnswer: [
          {
            command: "messages", messagesName: "hold",
            messages: [{ type: "SAY", say: { text: "Connecting your call.", voiceName: "Emma" } }],
          },
          {
            command: "dial",
            callName: "primary",
            from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
            to:   { type: "PHONE", phone: { number: PRIMARY_NUMBER } },
            dialTimeoutDurationSeconds: 20,
            events: {
              onAnswer: [
                { command: "stopMessages", messagesName: "hold" },
                { command: "bridgeCall",   bridgeName: "fwd-bridge" },
              ],
              onTimeout: [
                {
                  command: "dial",
                  callName: "fallback",
                  from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
                  to:   { type: "PHONE", phone: { number: FALLBACK_NUMBER } },
                  dialTimeoutDurationSeconds: 20,
                  events: {
                    onAnswer: [
                      { command: "stopMessages", messagesName: "hold" },
                      { command: "bridgeCall",   bridgeName: "fwd-bridge" },
                    ],
                    onTimeout: [{ command: "hangup", callName: "caller" }],
                  },
                },
              ],
            },
          },
        ],
        onHangup: [{ command: "hangup" }],
      },
    },
  ],
};

const authHeader = "Basic " + Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString("base64");

const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/calls`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: authHeader,
      "Idempotency-Key": randomUUID(),
    },
    body: JSON.stringify(body),
  }
);

console.log(resp.status, await resp.json());
```

### 3. What success looks like

Answer the call to your `CALLER_NUMBER`. You'll hear *"Connecting your call."* The platform dials `PRIMARY_NUMBER`; let it ring out (20 s). When it times out, `FALLBACK_NUMBER` rings and, if answered, joins you in the `fwd-bridge`.

- Your phone (`CALLER_NUMBER`) rings; you answer and hear the hold prompt.
- `PRIMARY_NUMBER` rings for ~20 s with no answer.
- Within ~1 s of the timeout, `FALLBACK_NUMBER` rings.
- Answer the fallback and you get two-way audio with the caller leg.

Inspect the session to confirm the chronology (caller, primary, fallback), each with its own `callResult`:

**Bash (curl)**

```bash
curl -s -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/sessions/$SESSION_ID" \
  | jq '.calls[] | {callName, callResult, callReason, answerTime, endTime}'
```

**Python**

```python
resp = requests.get(
    f"https://voice.api.sinch.com/v2/projects/{PROJECT_ID}/sessions/{SESSION_ID}",
    auth=(KEY_ID, KEY_SECRET),
)
for call in resp.json().get("calls", []):
    print({k: call.get(k) for k in ("callName", "callResult", "callReason", "answerTime", "endTime")})
```

**Node.js**

```javascript
const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/sessions/${SESSION_ID}`,
  { headers: { Authorization: authHeader } }
);
const data = await resp.json();
for (const call of data.calls || []) {
  console.log({ callName: call.callName, callResult: call.callResult,
                 callReason: call.callReason, answerTime: call.answerTime, endTime: call.endTime });
}
```

`callResult` values you'll see: `NO_ANSWER` on the primary, `COMPLETED`/`IN_PROGRESS` on the answered fallback.


---

## How forwarding works

A forwarded call always has at least two legs inside one session:

- **Caller leg**: the party that initiated (inbound) or was called by your platform (outbound).
- **Destination leg(s)**: the primary target you first try, plus any fallback targets you reach on a failure event.

Which `dial` event you hook the fallback into decides the behaviour. These are the events on the `dial` command's `events` block:

| Event | Fires when | Forwarding use |
| --- | --- | --- |
| `onAnswer` | Primary picked up | Bridge them in. **Do not forward.** |
| `onTimeout` | Rang `dialTimeoutDurationSeconds` without answer | Forward (CFNA). |
| `onBusy` | Primary returned busy | Forward (CFB). |
| `onReject` | Primary actively rejected | Forward. |
| `onFailure` | Call setup failed (carrier, unreachable) | Forward (CFNR). |
| `onHangup` | A leg dropped | Clean up the session; usually not a forward trigger. |


**One bridge per session.** Use a single `bridgeName` across primary and fallback so whichever leg answers joins the caller in the same bridge. The first call to enter creates it; the second joins.

## Forwarding variants at a glance

| Variant | Trigger |
| --- | --- |
| **On no-answer (CFNA), outbound** | Primary times out, then falls through to fallback |
| **On no-answer (CFNA), inbound** | Same logic, triggered by inbound webhook |
| **Time-of-day** (inbound webhook) | Office hours vs. after-hours |
| **Unconditional (CFU)** | Always forward |
| **Warm transfer** (mid-call) | Agent consults specialist, then merges |
| **Blind transfer** (mid-call) | Agent transfers without consulting |

## Real-life examples

- **Personal find-me-follow-me**: desk, then mobile, then voicemail depending on availability.
- **Office-hours routing**: support team during business hours, answering service overnight (Pattern 3).
- **Out-of-office cover**: vacation forwards to a colleague, then reverts.
- **Call-center transfer**: tier-1 agent escalates to a tier-2 specialist, with an optional whisper consult first (Pattern 4).
- **Compliance forwarding**: calls to a legacy number forwarded to a recorded line for archival.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project, API key, and API secret.
- A Sinch virtual phone number (caller ID on forwarded legs; for inbound forwarding, the published number callers dial).
- Destination numbers in E.164 format.
- For inbound/dynamic patterns: a publicly reachable webhook URL. `ngrok http 3000` works during development.
- Familiarity with SVAML v2: `dial`, `bridgeCall`, `hangup`, `messages`, `webhook`, and the `events` block.

---

## Pattern 1: Unconditional forward

All calls to your Sinch number are forwarded to a single fixed destination. Useful for departing-employee redirects, compliance archival lines, or vacation cover.

### Static SVAML version

Stored on the service via `PATCH /v2/projects/{projectId}/services/{serviceId}` with `callBehavior.type: "STATIC"`. The `static` object takes `commands` and an optional `events.onHangup`.

#### Bash (curl)

```bash
curl -X PATCH \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/services/$SERVICE_ID" \
  -H "Content-Type: application/json" \
  -d '{
  "callBehavior": {
    "type": "STATIC",
    "static": {
      "commands": [
        { "command": "answer" },
        {
          "command": "messages",
          "messagesName": "hold",
          "messages": [ { "type": "SAY",
            "say": { "text": "Please hold while we redirect your call.", "voiceName": "Emma" } } ]
        },
        { "command": "bridgeCall", "bridgeName": "forward-bridge" },
        {
          "command": "dial",
          "callName": "forward-target",
          "from": { "type": "PHONE", "phone": { "number": "+15551234567" } },
          "to":   { "type": "PHONE", "phone": { "number": "+15559998888" } },
          "dialTimeoutDurationSeconds": 30,
          "events": {
            "onAnswer": [
              { "command": "stopMessages", "messagesName": "hold" },
              { "command": "bridgeCall",   "bridgeName": "forward-bridge" }
            ],
            "onHangup":  [ { "command": "hangup" } ],
            "onTimeout": [ { "command": "hangup" } ]
          }
        }
      ],
      "events": { "onHangup": [ { "command": "hangup" } ] }
    }
  }
}'
```

#### Python (requests)

```python
import os
import requests

PROJECT_ID  = os.environ["PROJECT_ID"]
KEY_ID      = os.environ["KEY_ID"]
KEY_SECRET  = os.environ["KEY_SECRET"]
SERVICE_ID  = os.environ["SERVICE_ID"]

payload = {
    "callBehavior": {
        "type": "STATIC",
        "static": {
            "commands": [
                {"command": "answer"},
                {
                    "command": "messages",
                    "messagesName": "hold",
                    "messages": [{"type": "SAY", "say": {"text": "Please hold while we redirect your call.", "voiceName": "Emma"}}],
                },
                {"command": "bridgeCall", "bridgeName": "forward-bridge"},
                {
                    "command": "dial",
                    "callName": "forward-target",
                    "from": {"type": "PHONE", "phone": {"number": "+15551234567"}},
                    "to":   {"type": "PHONE", "phone": {"number": "+15559998888"}},
                    "dialTimeoutDurationSeconds": 30,
                    "events": {
                        "onAnswer": [
                            {"command": "stopMessages", "messagesName": "hold"},
                            {"command": "bridgeCall",   "bridgeName": "forward-bridge"},
                        ],
                        "onHangup":  [{"command": "hangup"}],
                        "onTimeout": [{"command": "hangup"}],
                    },
                },
            ],
            "events": {"onHangup": [{"command": "hangup"}]},
        },
    }
}

resp = requests.patch(
    f"https://voice.api.sinch.com/v2/projects/{PROJECT_ID}/services/{SERVICE_ID}",
    auth=(KEY_ID, KEY_SECRET),
    json=payload,
)
print(resp.status_code, resp.json())
```

#### Node.js (fetch)

```javascript
const PROJECT_ID = process.env.PROJECT_ID;
const KEY_ID     = process.env.KEY_ID;
const KEY_SECRET = process.env.KEY_SECRET;
const SERVICE_ID = process.env.SERVICE_ID;

const payload = {
  callBehavior: {
    type: "STATIC",
    static: {
      commands: [
        { command: "answer" },
        {
          command: "messages", messagesName: "hold",
          messages: [{ type: "SAY", say: { text: "Please hold while we redirect your call.", voiceName: "Emma" } }],
        },
        { command: "bridgeCall", bridgeName: "forward-bridge" },
        {
          command: "dial",
          callName: "forward-target",
          from: { type: "PHONE", phone: { number: "+15551234567" } },
          to:   { type: "PHONE", phone: { number: "+15559998888" } },
          dialTimeoutDurationSeconds: 30,
          events: {
            onAnswer: [
              { command: "stopMessages", messagesName: "hold" },
              { command: "bridgeCall",   bridgeName: "forward-bridge" },
            ],
            onHangup:  [{ command: "hangup" }],
            onTimeout: [{ command: "hangup" }],
          },
        },
      ],
      events: { onHangup: [{ command: "hangup" }] },
    },
  },
};

const authHeader = "Basic " + Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString("base64");

const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/services/${SERVICE_ID}`,
  {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: authHeader },
    body: JSON.stringify(payload),
  }
);
console.log(resp.status, await resp.json());
```

**Key points**

- `from` on the outbound leg is your Sinch number, not the caller's. This masks the caller's identity. To pass the original caller-ID through, set `from` to the caller's number, subject to your carrier's acceptance of caller-ID spoofing.
- The `messages` command plays while the forward leg rings; `stopMessages` ends it the moment the target answers.

---

## Pattern 2: Forward on no-answer (CFNA), inbound

The most common conditional forward: try the primary first; if it rings out, busy-signals, or is rejected, forward to a fallback. The webhook handler replies with commands at the top level (`answer`, then the primary `dial` and its fallback chain). Top-level `events.onHangup` handles session teardown.

Your webhook server receives a `call.incoming` event and returns the following SVAML. Below is the response body your handler should return, followed by complete server implementations that serve it.

### SVAML response body

```json
{
  "commands": [
    { "command": "answer" },
    { "command": "messages", "messagesName": "hold",
      "messages": [ { "type": "SAY",
        "say": { "text": "Please hold.", "voiceName": "Emma" } } ] },
    {
      "command": "dial",
      "callName": "primary",
      "from": { "type": "PHONE", "phone": { "number": "+15551234567" } },
      "to":   { "type": "PHONE", "phone": { "number": "+15557770001" } },
      "dialTimeoutDurationSeconds": 20,
      "events": {
        "onAnswer": [
          { "command": "stopMessages", "messagesName": "hold" },
          { "command": "bridgeCall",   "bridgeName": "fwd-bridge" }
        ],
        "onTimeout": [
          {
            "command": "dial",
            "callName": "fallback",
            "from": { "type": "PHONE", "phone": { "number": "+15551234567" } },
            "to":   { "type": "PHONE", "phone": { "number": "+15557770002" } },
            "dialTimeoutDurationSeconds": 20,
            "events": {
              "onAnswer": [
                { "command": "stopMessages", "messagesName": "hold" },
                { "command": "bridgeCall",   "bridgeName": "fwd-bridge" }
              ],
              "onTimeout": [
                { "command": "messages", "messagesName": "vm",
                  "messages": [ { "type": "SAY",
                    "say": { "text": "We are sorry, no one is available. Please leave a message.",
                             "voiceName": "Emma" } } ],
                  "events": { "onFinish": [ { "command": "hangup" } ] } }
              ]
            }
          }
        ]
      }
    }
  ],
  "events": { "onHangup": [ { "command": "hangup" } ] }
}
```

To also cover busy/reject/failure, repeat the same fallback `dial` inline under `onBusy`, `onReject`, and `onFailure`. SVAML does not resolve `$ref`, so each handler must carry its own copy.


### Inbound webhook server

The server listens for `call.incoming` and returns the CFNA SVAML shown above:

#### Python (Flask)

```python
# pip install flask
import os
from flask import Flask, request, jsonify

SINCH_NUMBER    = os.environ["SINCH_NUMBER"]
PRIMARY_NUMBER  = os.environ["PRIMARY_NUMBER"]
FALLBACK_NUMBER = os.environ["FALLBACK_NUMBER"]

app = Flask(__name__)

@app.post("/voice/events")
def voice_events():
    data = request.get_json(silent=True) or {}
    event = data.get("event")
    call  = data.get("call", {})
    print(f"event={event} sessionId={call.get('sessionId')}")

    if event != "call.incoming":
        return jsonify({"commands": []})

    print(f"Routing {call.get('from', {}).get('phone', {}).get('number')} -> {PRIMARY_NUMBER} (CFNA)")

    return jsonify({
        "commands": [
            {"command": "answer"},
            {"command": "messages", "messagesName": "hold",
             "messages": [{"type": "SAY", "say": {"text": "Please hold.", "voiceName": "Emma"}}]},
            {
                "command": "dial",
                "callName": "primary",
                "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                "to":   {"type": "PHONE", "phone": {"number": PRIMARY_NUMBER}},
                "dialTimeoutDurationSeconds": 20,
                "events": {
                    "onAnswer": [
                        {"command": "stopMessages", "messagesName": "hold"},
                        {"command": "bridgeCall",   "bridgeName": "fwd-bridge"},
                    ],
                    "onTimeout": [{
                        "command": "dial",
                        "callName": "fallback",
                        "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                        "to":   {"type": "PHONE", "phone": {"number": FALLBACK_NUMBER}},
                        "dialTimeoutDurationSeconds": 20,
                        "events": {
                            "onAnswer": [
                                {"command": "stopMessages", "messagesName": "hold"},
                                {"command": "bridgeCall",   "bridgeName": "fwd-bridge"},
                            ],
                            "onTimeout": [
                                {"command": "messages", "messagesName": "vm",
                                 "messages": [{"type": "SAY",
                                   "say": {"text": "We are sorry, no one is available. Please leave a message.",
                                           "voiceName": "Emma"}}],
                                 "events": {"onFinish": [{"command": "hangup"}]}},
                            ],
                        },
                    }],
                },
            },
        ],
        "events": {"onHangup": [{"command": "hangup"}]},
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"CFNA webhook server on :{port}")
    app.run(host="0.0.0.0", port=port)
```

#### Node.js (Express)

```javascript
// npm install express
import express from "express";

const SINCH_NUMBER    = process.env.SINCH_NUMBER;
const PRIMARY_NUMBER  = process.env.PRIMARY_NUMBER;
const FALLBACK_NUMBER = process.env.FALLBACK_NUMBER;
const PORT            = process.env.PORT || 3000;

const app = express();
app.use(express.json());

app.post("/voice/events", (req, res) => {
  const { event, call } = req.body || {};
  console.log(`event=${event} sessionId=${call?.sessionId}`);

  if (event !== "call.incoming") return res.json({ commands: [] });

  console.log(`Routing ${call?.from?.phone?.number} -> ${PRIMARY_NUMBER} (CFNA)`);

  res.json({
    commands: [
      { command: "answer" },
      { command: "messages", messagesName: "hold",
        messages: [{ type: "SAY", say: { text: "Please hold.", voiceName: "Emma" } }] },
      {
        command: "dial",
        callName: "primary",
        from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
        to:   { type: "PHONE", phone: { number: PRIMARY_NUMBER } },
        dialTimeoutDurationSeconds: 20,
        events: {
          onAnswer: [
            { command: "stopMessages", messagesName: "hold" },
            { command: "bridgeCall",   bridgeName: "fwd-bridge" },
          ],
          onTimeout: [{
            command: "dial",
            callName: "fallback",
            from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
            to:   { type: "PHONE", phone: { number: FALLBACK_NUMBER } },
            dialTimeoutDurationSeconds: 20,
            events: {
              onAnswer: [
                { command: "stopMessages", messagesName: "hold" },
                { command: "bridgeCall",   bridgeName: "fwd-bridge" },
              ],
              onTimeout: [
                { command: "messages", messagesName: "vm",
                  messages: [{ type: "SAY",
                    say: { text: "We are sorry, no one is available. Please leave a message.",
                           voiceName: "Emma" } }],
                  events: { onFinish: [{ command: "hangup" }] } },
              ],
            },
          }],
        },
      },
    ],
    events: { onHangup: [{ command: "hangup" }] },
  });
});

app.listen(PORT, () => console.log(`CFNA webhook server on :${PORT}`));
```

### Outbound entry

The same SVAML shape works for outbound calls started from `POST /calls`. The outermost `dial` is the caller leg your system calls; its `onAnswer` kicks off the primary, whose `onTimeout` falls through to the fallback. This is exactly the quick-start example above.

---

## Pattern 3: Time-of-day forwarding (webhook-driven)

The destination depends on context the platform doesn't know: office hours, on-call rota, agent presence. Let your backend choose in response to `call.incoming`.

### 1. Switch the service to WEBHOOK behavior

#### Bash (curl)

```bash
curl -X PATCH \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/services/$SERVICE_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"callBehavior\": {
      \"type\": \"WEBHOOK\",
      \"webhook\": {
        \"url\":         \"${CALLBACK_URL}/voice/events\",
        \"fallbackUrl\": \"${CALLBACK_URL}/voice/events\"
      }
    }
  }"
```

#### Python (requests)

```python
import os
import requests

resp = requests.patch(
    f"https://voice.api.sinch.com/v2/projects/{os.environ['PROJECT_ID']}/services/{os.environ['SERVICE_ID']}",
    auth=(os.environ["KEY_ID"], os.environ["KEY_SECRET"]),
    json={
        "callBehavior": {
            "type": "WEBHOOK",
            "webhook": {
                "url":         f"{os.environ['CALLBACK_URL']}/voice/events",
                "fallbackUrl": f"{os.environ['CALLBACK_URL']}/voice/events",
            },
        }
    },
)
print(resp.status_code, resp.json())
```

#### Node.js (fetch)

```javascript
const authHeader = "Basic " + Buffer.from(
  `${process.env.KEY_ID}:${process.env.KEY_SECRET}`
).toString("base64");

const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${process.env.PROJECT_ID}/services/${process.env.SERVICE_ID}`,
  {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: authHeader },
    body: JSON.stringify({
      callBehavior: {
        type: "WEBHOOK",
        webhook: {
          url:         `${process.env.CALLBACK_URL}/voice/events`,
          fallbackUrl: `${process.env.CALLBACK_URL}/voice/events`,
        },
      },
    }),
  }
);
console.log(resp.status, await resp.json());
```

### 2. Run the webhook server

The server reads `BUSINESS_START_HOUR_UTC` and `BUSINESS_END_HOUR_UTC` from the environment. On `call.incoming` it picks the target by UTC wall-clock hour and returns a bridge + dial flow.

#### Python (Flask)

```python
# pip install flask
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify

SINCH_NUMBER       = os.environ["SINCH_NUMBER"]
DAY_TARGET         = os.environ.get("PRIMARY_NUMBER", os.environ.get("DESTINATION_NUMBER"))
AFTER_HOURS_TARGET = os.environ.get("FALLBACK_NUMBER", DAY_TARGET)
BUSINESS_START     = int(os.environ.get("BUSINESS_START_HOUR_UTC", "8"))
BUSINESS_END       = int(os.environ.get("BUSINESS_END_HOUR_UTC", "18"))

app = Flask(__name__)

@app.post("/voice/events")
def voice_events():
    data  = request.get_json(silent=True) or {}
    event = data.get("event")
    call  = data.get("call", {})
    print(f"event={event} sessionId={call.get('sessionId')}")

    if event != "call.incoming":
        return jsonify({"commands": []})

    hour = datetime.now(timezone.utc).hour
    is_business_hours = BUSINESS_START <= hour < BUSINESS_END
    target = DAY_TARGET if is_business_hours else AFTER_HOURS_TARGET

    caller = call.get("from", {}).get("phone", {}).get("number", "unknown")
    print(f"Routing {caller} -> {target} (businessHours={is_business_hours}, UTC {hour}h)")

    return jsonify({
        "commands": [
            {"command": "answer"},
            {"command": "messages", "messagesName": "hold",
             "messages": [{"type": "SAY", "say": {"text": "One moment please.", "voiceName": "Emma"}}]},
            {"command": "bridgeCall", "bridgeName": "tod-bridge"},
            {
                "command": "dial",
                "callName": "forward-target",
                "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                "to":   {"type": "PHONE", "phone": {"number": target}},
                "dialTimeoutDurationSeconds": 30,
                "events": {
                    "onAnswer": [
                        {"command": "stopMessages", "messagesName": "hold"},
                        {"command": "bridgeCall",   "bridgeName": "tod-bridge"},
                    ],
                    "onTimeout": [{"command": "hangup"}],
                    "onHangup":  [{"command": "hangup"}],
                },
            },
        ],
        "events": {"onHangup": [{"command": "hangup"}]},
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    print(f"Time-of-day webhook server on :{port}")
    print(f"Business hours: {BUSINESS_START}:00-{BUSINESS_END}:00 UTC")
    print(f"Day target={DAY_TARGET} | After-hours target={AFTER_HOURS_TARGET}")
    app.run(host="0.0.0.0", port=port)
```

#### Node.js (Express)

```javascript
// npm install express
import express from "express";

const SINCH_NUMBER       = process.env.SINCH_NUMBER;
const DAY_TARGET         = process.env.PRIMARY_NUMBER || process.env.DESTINATION_NUMBER;
const AFTER_HOURS_TARGET = process.env.FALLBACK_NUMBER || DAY_TARGET;
const BUSINESS_START     = Number(process.env.BUSINESS_START_HOUR_UTC || 8);
const BUSINESS_END       = Number(process.env.BUSINESS_END_HOUR_UTC   || 18);
const PORT               = process.env.PORT || 3000;

const app = express();
app.use(express.json());

app.post("/voice/events", (req, res) => {
  const { event, call } = req.body || {};
  console.log(`event=${event} sessionId=${call?.sessionId}`);

  if (event !== "call.incoming") return res.json({ commands: [] });

  const hour = new Date().getUTCHours();
  const isBusinessHours = hour >= BUSINESS_START && hour < BUSINESS_END;
  const target = isBusinessHours ? DAY_TARGET : AFTER_HOURS_TARGET;

  console.log(`Routing ${call?.from?.phone?.number} -> ${target} (businessHours=${isBusinessHours}, UTC ${hour}h)`);

  res.json({
    commands: [
      { command: "answer" },
      { command: "messages", messagesName: "hold",
        messages: [{ type: "SAY", say: { text: "One moment please.", voiceName: "Emma" } }] },
      { command: "bridgeCall", bridgeName: "tod-bridge" },
      {
        command: "dial",
        callName: "forward-target",
        from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
        to:   { type: "PHONE", phone: { number: target } },
        dialTimeoutDurationSeconds: 30,
        events: {
          onAnswer: [
            { command: "stopMessages", messagesName: "hold" },
            { command: "bridgeCall",   bridgeName: "tod-bridge" },
          ],
          onTimeout: [{ command: "hangup" }],
          onHangup:  [{ command: "hangup" }],
        },
      },
    ],
    events: { onHangup: [{ command: "hangup" }] },
  });
});

app.listen(PORT, () => {
  console.log(`Time-of-day webhook server on :${PORT}`);
  console.log(`Business hours: ${BUSINESS_START}:00-${BUSINESS_END}:00 UTC`);
  console.log(`Day target=${DAY_TARGET} | After-hours target=${AFTER_HOURS_TARGET}`);
});
```

#### Bash (curl one-liner to test)

The webhook server must be a long-running process, so bash isn't practical as the server itself. However, you can test an inbound call by calling the webhook endpoint directly:

```bash
curl -s -X POST http://localhost:3000/voice/events \
  -H "Content-Type: application/json" \
  -d '{
    "event": "call.incoming",
    "call": {
      "sessionId": "test-123",
      "from": { "phone": { "number": "+15550001111" } }
    }
  }' | jq '.'
```

Then expose the server publicly with `ngrok http 3000` and set the resulting HTTPS URL as your `CALLBACK_URL` in the service PATCH above.

Replace the hour check with whatever your backend knows: an on-call schedule, agent presence, or a per-caller routing table indexed on `call.from.phone.number` (both `call.sessionId` and `call.from.phone.number` are valid fields on the webhook's `call` object).


---

## Pattern 4: Warm transfer, mid-call with whisper

An agent already bridged with the caller brings in a specialist, talks privately first ("whisper"), then adds the caller. Built with `webhook` + `dial` + `bridgeCall`.

### 1. Pull control back with a mid-call webhook

Embed a `webhook` SVAML command in the agent's flow. The platform fires `call.webhook.transfer.request` to your URL; `webhook` is **blocking**, so the call stays bridged while your backend decides.

```json
{
  "command": "webhook",
  "webhookName": "transfer.request",
  "url": "https://fwd.example.com/voice/transfer"
}
```

### 2. Backend returns a dial to the specialist on a separate bridge

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "specialist",
      "from": { "type": "PHONE", "phone": { "number": "+15551234567" } },
      "to":   { "type": "PHONE", "phone": { "number": "+15556660001" } },
      "dialTimeoutDurationSeconds": 25,
      "events": {
        "onAnswer": [ { "command": "bridgeCall", "bridgeName": "whisper-bridge" } ]
      }
    }
  ]
}
```

The agent leg also joins `whisper-bridge`. The caller stays on the original bridge on hold; agent and specialist are now in a private channel.

### 3. Commit (merge bridges) or cancel

Fire a second webhook from the agent leg. To complete the transfer, drop the agent and have the specialist join the caller's bridge:

```json
{
  "commands": [
    { "command": "hangup",     "callName":   "agent" },
    { "command": "bridgeCall", "bridgeName": "fwd-bridge" }
  ]
}
```

To cancel, return `{ "command": "hangup", "callName": "specialist" }` and the agent rejoins the caller's bridge.


---

## Pattern 5: Blind transfer

Transfer the caller to a third party without speaking to them first: drop the agent leg, fire a fresh `dial` into the same bridge.

```json
{
  "commands": [
    { "command": "hangup", "callName": "agent" },
    {
      "command": "dial",
      "callName": "blind-target",
      "from": { "type": "PHONE", "phone": { "number": "+15551234567" } },
      "to":   { "type": "PHONE", "phone": { "number": "+15554443333" } },
      "dialTimeoutDurationSeconds": 25,
      "events": {
        "onAnswer": [ { "command": "bridgeCall", "bridgeName": "fwd-bridge" } ],
        "onTimeout": [
          { "command": "messages", "messagesName": "vm",
            "messages": [ { "type": "SAY",
              "say": { "text": "The party you were transferred to is not available.",
                       "voiceName": "Emma" } } ],
            "events": { "onFinish": [ { "command": "hangup", "callName": "caller" } ] } }
        ]
      }
    }
  ]
}
```


---

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Forwarding-loop prevention** | If the forward target is itself a Sinch number with forwarding, you can build an infinite loop. Track `sessionId` and reject re-entries; set `maxCallDurationSeconds` on every leg as a backstop. |
| **Caller-ID handling** | Decide explicitly: original caller (set `from` to caller's number, subject to carrier acceptance) or your Sinch number (default). Be consistent across patterns. |
| **Voicemail / AMD** | Insert an `amd` command before the `bridgeCall` on each forwarded leg. On `onMachine`/`onBeep`, treat as "no answer" and fall through. (`amd` exposes `onHuman`/`onMachine`/`onBeep`/`onUnknown`.) |
| **Compliance recording** | Insert `startRecording` after the winning `bridgeCall`; the recording stays scoped to the bridged audio. |
| **Idempotency** | Send `Idempotency-Key` on `POST /calls` so a network-retried request doesn't dial twice. |
| **Webhook handler latency** | Pre-fetch routing rules, cache in memory, respond fast. |
| **Hangup propagation** | If the caller hangs up while a target is still ringing, the platform tears down only what you wired. Set `onHangup` on the caller leg or respond to `call.hangup` with an explicit `hangup` for the still-ringing leg. |

## Testing

Use your own mobile as the "primary" with `dialTimeoutDurationSeconds: 10`. Let it ring out and the fallback should ring within a second. Decline the call and the fallback should ring immediately. Answer the call and no forward should happen.

#### Bash

```bash
# 1. Place the outbound CFNA call (see quick-start example above).

# 2. Inspect the session afterward:
curl -s -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/sessions/$SESSION_ID" \
  | jq '.calls[] | {callName, callResult, callReason, answerTime, endTime}'
```

#### Python

```python
import os
import requests

PROJECT_ID = os.environ["PROJECT_ID"]
KEY_ID     = os.environ["KEY_ID"]
KEY_SECRET = os.environ["KEY_SECRET"]
SESSION_ID = os.environ["SESSION_ID"]  # from the POST /calls response

resp = requests.get(
    f"https://voice.api.sinch.com/v2/projects/{PROJECT_ID}/sessions/{SESSION_ID}",
    auth=(KEY_ID, KEY_SECRET),
)
for call in resp.json().get("calls", []):
    print({k: call.get(k) for k in ("callName", "callResult", "callReason", "answerTime", "endTime")})
```

#### Node.js

```javascript
const PROJECT_ID = process.env.PROJECT_ID;
const KEY_ID     = process.env.KEY_ID;
const KEY_SECRET = process.env.KEY_SECRET;
const SESSION_ID = process.env.SESSION_ID; // from the POST /calls response

const authHeader = "Basic " + Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString("base64");

const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/sessions/${SESSION_ID}`,
  { headers: { Authorization: authHeader } }
);
const data = await resp.json();
for (const call of data.calls || []) {
  console.log({
    callName:   call.callName,
    callResult: call.callResult,
    callReason: call.callReason,
    answerTime: call.answerTime,
    endTime:    call.endTime,
  });
}
```

The session's `calls[]` array preserves the chronology of caller, primary, and fallback, with a `callResult` per leg. Use this for forwarding analytics and SLA reporting.
