# Handle Inbound PSTN Calls

## Overview

When someone dials a Sinch virtual number assigned to your project, the Voice API v2 sends a **`call.incoming`** webhook to the URL configured on the *service* that owns the number. Your backend answers with the SVAML commands to run for that call: greet the caller, gather input, bridge to an agent, route to an AI assistant, anything.

A service can handle inbound calls in one of three ways (its `callBehavior.type`):

- **`WEBHOOK`**: Sinch POSTs every event to your URL and you decide what to do at runtime. This is the dynamic option and the focus of this tutorial.
- **`STATIC`**: Sinch executes a fixed SVAML script stored on the service (`callBehavior.static.commands`). No backend needed. Static services do **not** trigger the incoming webhook.
- **`NONE`**: Incoming calls are not handled (outbound calls can still be created via the API).

## What you'll build

A webhook server that, on `call.incoming`, answers the call, plays a greeting, and bridges the caller to an agent phone number. By the end you'll place a real call to your Sinch number and watch it get answered.

Every example in this tutorial is shown in three languages: **bash** (curl / ncat), **Python** (requests / Flask), and **Node.js** (fetch / Express). Pick one column and stick with it, or mix freely; they are functionally identical.


---

## Setup

Export the following variables in every shell you use for this tutorial (the one running the server, and the one running the API-call examples). The Python and Node.js examples read the same variables from the environment, so the exports work for all three languages:

```bash
# API credentials - Sinch Dashboard (https://dashboard.sinch.com) -> Access keys
export PROJECT_ID="your-project-id"
export KEY_ID="your-key-id"
export KEY_SECRET="your-key-secret"

# The service that owns your Sinch number - Dashboard -> Voice -> Services
# (or GET /v2/projects/{projectId}/services). This is the service whose
# callBehavior you'll switch to WEBHOOK.
export SERVICE_ID="your-service-id"

# Your Sinch virtual number, E.164, routed to the service above
export SINCH_NUMBER="+14045001000"

# The agent number the call bridges to, E.164 - any phone you can answer
export DESTINATION_NUMBER="+14155559876"

# Local server port
export PORT=3000
```


Tools and dependencies per language:

| Language | Server | API-call examples |
| --- | --- | --- |
| **bash** | `ncat` (from the nmap package) + `jq`; demo/dev only | `curl` |
| **Python 3.8+** | Flask: `pip install flask` | `pip install requests` |
| **Node.js 18+** | Express (ES modules): `npm install express` | Built-in `fetch`, no install |

You'll also need **[ngrok](https://ngrok.com)** (or any tunnel) to expose your local server during development. All API calls authenticate with HTTP Basic auth using `KEY_ID` / `KEY_SECRET`.

---

## Step 0 - Smoke-test your SVAML (no phone needed)

Before any tunneling, confirm the SVAML you intend to return is valid. `POST /svaml/validate` checks a payload using the same rules as a live call and returns `{ "isValid": true | false, "errors": [...] }`.

**bash**

```bash
curl -s -X POST \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/svaml/validate" \
  -H "Content-Type: application/json" \
  -d '{
          "svaml": {"commands":[
            { "command": "answer" },
            { "command": "messages",
              "messages": [
                { "type": "SAY", "say": { "text": "Welcome to Acme.", "voiceName": "Emma" } }
              ] }
          ]}
  }'
```

**Python** (`validate.py`)

```python
import os
import requests

resp = requests.post(
    f"https://voice.api.sinch.com/v2/projects/{os.environ['PROJECT_ID']}/svaml/validate",
    auth=(os.environ["KEY_ID"], os.environ["KEY_SECRET"]),
    json = {
      "svaml": {
        "commands": [{
            "command": "answer"
          }, {
            "command": "messages",
            "messages": [{
                "type": "SAY",
                "say": {
                  "text": "Welcome to Acme.",
                  "voiceName": "Emma"
                }
              }
            ]
          },
        ]
      }
    },
)
print(resp.status_code, resp.json())
```

**Node.js** (`validate.js`)

```javascript
const auth = Buffer.from(`${process.env.KEY_ID}:${process.env.KEY_SECRET}`).toString("base64");

const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${process.env.PROJECT_ID}/svaml/validate`,
  {
    method: "POST",
    headers: { Authorization: `Basic ${auth}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      svaml: {commands: [
        { command: "answer" },
        { command: "messages",
          messages: [
            { type: "SAY", say: { text: "Welcome to Acme.", voiceName: "Emma" } },
          ] },
      ] },
    }),
  }
);
console.log(resp.status, await resp.json());
```

Expected: `{"isValid":true}`. A `200` here means validation *ran*, not that the payload passed; always read `isValid`. 

---

## Step 1 - Write and start the webhook server

All three servers behave identically. They read `SINCH_NUMBER` and `DESTINATION_NUMBER` from the environment (the variables you exported above), exit with an error if either is missing, and listen on `PORT` (default `3000`) at `POST /voice/events`:

- On **`call.incoming`**: answer, play a greeting, then dial `DESTINATION_NUMBER` and bridge the two legs.
- On **any other event**: acknowledge with `200` and `{"commands": []}` (take no action).

**bash** (`server.sh`)


```bash
#!/usr/bin/env bash
# Sinch Voice API v2 - Inbound PSTN webhook server (bash + ncat, demo only).
# Handles call.incoming by greeting the caller, then dialing an agent and bridging.
#
# Requirements: ncat (nmap package), jq
# Run:    bash server.sh   (with SINCH_NUMBER / DESTINATION_NUMBER exported)
# Expose: ngrok http 3000

set -euo pipefail

: "${SINCH_NUMBER:?ERROR: export SINCH_NUMBER first}"
: "${DESTINATION_NUMBER:?ERROR: export DESTINATION_NUMBER first}"
PORT="${PORT:-3000}"

# ncat re-invokes this script with --handle for each connection.
if [ "${1:-}" = "--handle" ]; then
  content_length=0
  while IFS= read -r line; do
    line="${line%$'\r'}"
    [ -z "$line" ] && break
    case "$line" in
      [Cc]ontent-[Ll]ength:*) content_length="${line#*: }" ;;
    esac
  done

  body=""
  [ "$content_length" -gt 0 ] && body=$(head -c "$content_length")

  event=$(printf '%s' "$body" | jq -r '.event // empty' 2>/dev/null || true)
  session=$(printf '%s' "$body" | jq -r '.call.sessionId // empty' 2>/dev/null || true)
  echo "event=$event sessionId=$session" >&2

  if [ "$event" = "call.incoming" ]; then
    response=$(jq -n --arg sinch "$SINCH_NUMBER" --arg dest "$DESTINATION_NUMBER" '{
      commands: [
        { command: "answer" },
        { command: "messages", messagesName: "greeting",
          messages: [
            { type: "SAY",
              say: { text: "Welcome to Acme. Please hold while we connect your call.",
                     voiceName: "Emma" } }
          ] },
        { command: "bridgeCall", bridgeName: "inbound-bridge" },
        { command: "dial", callName: "agent",
          from: { type: "PHONE", phone: { number: $sinch } },
          to:   { type: "PHONE", phone: { number: $dest } },
          dialTimeoutDurationSeconds: 30,
          events: {
            onAnswer:  [ { command: "bridgeCall", bridgeName: "inbound-bridge" } ],
            onHangup:  [ { command: "hangup" } ],
            onTimeout: [
              { command: "messages", messagesName: "noanswer",
                messages: [
                  { type: "SAY",
                    say: { text: "We are sorry, our agents are unavailable. Goodbye.",
                           voiceName: "Emma" } }
                ],
                events: { onFinish: [ { command: "hangup" } ] } }
            ]
          } }
      ],
      events: { onHangup: [ { command: "hangup" } ] }
    }')
  else
    response='{"commands":[]}'
  fi

  len=$(printf '%s' "$response" | wc -c | tr -d ' ')
  printf 'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s' \
    "$len" "$response"
  exit 0
fi

echo "Inbound PSTN webhook server (bash/ncat) on :$PORT" >&2
exec ncat -lk "$PORT" --sh-exec "bash $0 --handle"
```

Run it:

```bash
bash server.sh
```

**Python** (`server.py`)

```python
# Sinch Voice API v2 - Inbound PSTN webhook server (Flask).
# Handles call.incoming by greeting the caller, then dialing an agent and bridging.
#
# Requirements: pip install flask
# Run:    python server.py   (with SINCH_NUMBER / DESTINATION_NUMBER exported)
# Expose: ngrok http 3000

import os
import sys

from flask import Flask, jsonify, request

SINCH_NUMBER       = os.environ.get("SINCH_NUMBER")
DESTINATION_NUMBER = os.environ.get("DESTINATION_NUMBER")
PORT               = int(os.environ.get("PORT", "3000"))

if not SINCH_NUMBER or not DESTINATION_NUMBER:
    print("ERROR: export SINCH_NUMBER and DESTINATION_NUMBER first.", file=sys.stderr)
    sys.exit(1)

app = Flask(__name__)


@app.post("/voice/events")
def voice_events():
    payload = request.get_json(silent=True) or {}
    event = payload.get("event")
    call  = payload.get("call") or {}
    print(
        f"event={event} sessionId={call.get('sessionId')} "
        f"from={(call.get('from') or {}).get('phone', {}).get('number')} "
        f"to={(call.get('to')   or {}).get('phone', {}).get('number')}"
    )

    if event == "call.incoming":
        return jsonify({
            "commands": [
                {"command": "answer"},
                {
                    "command": "messages",
                    "messagesName": "greeting",
                    "messages": [
                        {"type": "SAY",
                         "say": {"text": "Welcome to Acme. Please hold while we connect your call.",
                                 "voiceName": "Emma"}}
                    ],
                },
                {"command": "bridgeCall", "bridgeName": "inbound-bridge"},
                {
                    "command": "dial",
                    "callName": "agent",
                    "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                    "to":   {"type": "PHONE", "phone": {"number": DESTINATION_NUMBER}},
                    "dialTimeoutDurationSeconds": 30,
                    "events": {
                        "onAnswer":  [{"command": "bridgeCall", "bridgeName": "inbound-bridge"}],
                        "onHangup":  [{"command": "hangup"}],
                        "onTimeout": [
                            {"command": "messages",
                             "messagesName": "noanswer",
                             "messages": [
                                 {"type": "SAY",
                                  "say": {"text": "We are sorry, our agents are unavailable. Goodbye.",
                                          "voiceName": "Emma"}}
                             ],
                             "events": {"onFinish": [{"command": "hangup"}]}}
                        ],
                    },
                },
            ],
            "events": {"onHangup": [{"command": "hangup"}]},
        })

    return jsonify({"commands": []})


if __name__ == "__main__":
    print(f"Inbound PSTN webhook server on :{PORT}")
    app.run(host="0.0.0.0", port=PORT)
```

Run it:

```bash
python server.py
```

**Node.js** (`server.js`)

```javascript
// Sinch Voice API v2 - Inbound PSTN webhook server (Express).
// Handles call.incoming by greeting the caller, then dialing an agent and bridging.
//
// Requirements: npm install express
// Run:    node server.js   (with SINCH_NUMBER / DESTINATION_NUMBER exported)
// Expose: ngrok http 3000

import express from "express";

const SINCH_NUMBER       = process.env.SINCH_NUMBER       || (() => { throw new Error("SINCH_NUMBER not set, export it first"); })();
const DESTINATION_NUMBER = process.env.DESTINATION_NUMBER || (() => { throw new Error("DESTINATION_NUMBER not set, export it first"); })();
const PORT = process.env.PORT || 3000;

const app = express();
app.use(express.json());

app.post("/voice/events", (req, res) => {
  const { event, call } = req.body || {};
  console.log(`event=${event} sessionId=${call?.sessionId} from=${call?.from?.phone?.number} to=${call?.to?.phone?.number}`);

  if (event === "call.incoming") {
    return res.status(200).json({
      commands: [
        { command: "answer" },
        {
          command: "messages",
          messagesName: "greeting",
          messages: [
            {
              type: "SAY",
              say: { text: "Welcome to Acme. Please hold while we connect your call.", voiceName: "Emma" },
            },
          ],
        },
        { command: "bridgeCall", bridgeName: "inbound-bridge" },
        {
          command: "dial",
          callName: "agent",
          from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
          to:   { type: "PHONE", phone: { number: DESTINATION_NUMBER } },
          dialTimeoutDurationSeconds: 30,
          events: {
            onAnswer: [{ command: "bridgeCall", bridgeName: "inbound-bridge" }],
            onHangup: [{ command: "hangup" }],
            onTimeout: [
              {
                command: "messages",
                messagesName: "noanswer",
                messages: [
                  { type: "SAY",
                    say: { text: "We are sorry, our agents are unavailable. Goodbye.",
                           voiceName: "Emma" } },
                ],
                events: { onFinish: [{ command: "hangup" }] },
              },
            ],
          },
        },
      ],
      events: { onHangup: [{ command: "hangup" }] },
    });
  }

  // For all other events, acknowledge with no commands.
  return res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`Inbound PSTN webhook server on :${PORT}`);
  console.log(`Configure service callBehavior.webhook.url -> https://<your-ngrok>/voice/events`);
});
```

Run it:

```bash
node server.js
```

### Smoke-test the server locally

Before exposing it, confirm it responds to a simulated event. You should get back the SVAML JSON and see a log line on the server.

**bash**

```bash
curl -s -X POST http://localhost:3000/voice/events \
  -H "Content-Type: application/json" \
  -d '{"event":"call.incoming","call":{"sessionId":"test","from":{"phone":{"number":"+15551112222"}},"to":{"phone":{"number":"+14045001000"}}}}'
```

**Python** (`smoke_test.py`)

```python
import requests

resp = requests.post(
    "http://localhost:3000/voice/events",
    json={
        "event": "call.incoming",
        "call": {
            "sessionId": "test",
            "from": {"phone": {"number": "+15551112222"}},
            "to":   {"phone": {"number": "+14045001000"}},
        },
    },
)
print(resp.status_code, resp.json())
```

**Node.js** (`smoke-test.js`)

```javascript
const resp = await fetch("http://localhost:3000/voice/events", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    event: "call.incoming",
    call: {
      sessionId: "test",
      from: { phone: { number: "+15551112222" } },
      to:   { phone: { number: "+14045001000" } },
    },
  }),
});
console.log(resp.status, await resp.json());
```

## Step 2 - Expose it with ngrok

```bash
ngrok http 3000
```

Copy the `https://<id>.ngrok-free.app` URL ngrok prints. Your webhook URL is that base **plus the `/voice/events` path** the server listens on. Export it for the next step:

```bash
export WEBHOOK_URL="https://<id>.ngrok-free.app/voice/events"
```

## Step 3 - Point the service webhook at your server

PATCH the service to set `callBehavior.type = WEBHOOK` with your **full webhook URL including the path**:

**bash**

```bash
curl -s -X PATCH \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/services/$SERVICE_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"callBehavior\": {
      \"type\": \"WEBHOOK\",
      \"webhook\": {
        \"url\":         \"$WEBHOOK_URL\",
        \"fallbackUrl\": \"$WEBHOOK_URL\"
      }
    }
  }"
```

**Python** (`configure_service.py`)

```python
import os
import requests

webhook_url = os.environ["WEBHOOK_URL"]

resp = requests.patch(
    f"https://voice.api.sinch.com/v2/projects/{os.environ['PROJECT_ID']}"
    f"/services/{os.environ['SERVICE_ID']}",
    auth=(os.environ["KEY_ID"], os.environ["KEY_SECRET"]),
    json={
        "callBehavior": {
            "type": "WEBHOOK",
            "webhook": {"url": webhook_url, "fallbackUrl": webhook_url},
        }
    },
)
print(resp.status_code, resp.json())
```

**Node.js** (`configure-service.js`)

```javascript
const webhookUrl = process.env.WEBHOOK_URL;
const auth = Buffer.from(`${process.env.KEY_ID}:${process.env.KEY_SECRET}`).toString("base64");

const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${process.env.PROJECT_ID}/services/${process.env.SERVICE_ID}`,
  {
    method: "PATCH",
    headers: { Authorization: `Basic ${auth}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      callBehavior: {
        type: "WEBHOOK",
        webhook: { url: webhookUrl, fallbackUrl: webhookUrl },
      },
    }),
  }
);
console.log(resp.status, await resp.json());
```

`fallbackUrl` is optional but recommended: once the primary `url` starts returning errors, Sinch switches **future** requests to the fallback (it does not retry the *same* failed request against it).


## Step 4 - Dial your Sinch number

Call `SINCH_NUMBER` from any phone.

### What success looks like

Your terminal logs the incoming event, e.g.:

```
event=call.incoming sessionId=01AN4Z07BY79KA1307SR9X4MV2 from=+14155552671 to=+14045001000
```

You should hear "Welcome to Acme. Please hold while we connect your call," then `DESTINATION_NUMBER` rings. Answer it and the two legs are bridged. If the agent doesn't answer within 30 seconds, the caller hears the "agents are unavailable" message and the call hangs up.

---

## Reference: the webhook request

Sinch delivers webhooks in **CloudEvents 1.0, HTTP binary content mode**. CloudEvents metadata travels as `ce-*` headers; the JSON body carries the event:

```http
POST /voice/events
ce-specversion: 1.0
ce-type:        com.sinch.voice.webhook.v2
ce-source:      projects/<projectId>/services/<serviceId>
ce-id:          <uuid>
ce-time:        2026-04-01T12:00:00+00:00
content-type:   application/json

{
  "event": "call.incoming",
  "call": {
    "callId":          "01AN4Z07BY79KA1307SR9X4MV3",
    "projectId":       "...",
    "serviceId":       "...",
    "sessionId":       "01AN4Z07BY79KA1307SR9X4MV2",
    "direction":       "INBOUND",
    "originationType": "PHONE",
    "callType":        "PHONE",
    "from":   { "type": "PHONE", "phone": { "number": "+14155552671" } },
    "to":     { "type": "PHONE", "phone": { "number": "+46735224800" } },
    "callResult": "INITIATED",
    "startTime":  "2025-06-01T10:00:00Z"
  }
}
```

The body has two top-level fields: `event` (the event name) and `call` (the call state). `call.from.phone.number` is the calling party (the customer); `call.to.phone.number` is the Sinch number they dialed. Use `to` to route; most deployments have several Sinch numbers, one per persona or region.


### `ce-id` for deduplication

`ce-id` is a unique per-event UUID; combined with `ce-source` it identifies a single delivery. The example servers don't validate headers, but production code should (see the checklist).

---

## Reference: the webhook response (SVAML)

For a `call.incoming` event, return SVAML commands **directly at the top level**; there is no wrapper command. Start with `answer`, then add the call flow. Optional top-level `callName` and `events` are honored **only** in responses to `call.incoming`; in responses to other events they're ignored.

```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "commands": [
    { "command": "answer" },
    {
      "command": "messages",
      "messagesName": "greeting",
      "messages": [
        { "type": "SAY",
          "say": { "text": "Welcome to Acme. Please hold while we connect you.",
                   "voiceName": "Emma" } }
      ]
    },
    { "command": "bridgeCall", "bridgeName": "inbound-bridge" },
    {
      "command": "dial",
      "callName": "agent",
      "from": { "type": "PHONE", "phone": { "number": "+1SINCH_NUMBER" } },
      "to":   { "type": "PHONE", "phone": { "number": "+1AGENT_NUMBER" } },
      "dialTimeoutDurationSeconds": 30,
      "events": {
        "onAnswer": [ { "command": "bridgeCall", "bridgeName": "inbound-bridge" } ],
        "onHangup": [ { "command": "hangup" } ],
        "onTimeout": [
          { "command": "messages", "messagesName": "noanswer",
            "messages": [ { "type": "SAY",
              "say": { "text": "Our agents are unavailable. Goodbye.", "voiceName": "Emma" } } ],
            "events": { "onFinish": [ { "command": "hangup" } ] } }
        ]
      }
    }
  ],
  "events": {
    "onHangup": [ { "command": "hangup" } ]
  }
}
```

Things to know:

- `commands` is a normal SVAML sequence, the same primitives as any outbound flow.
- The inbound leg is answered explicitly with `answer`; `bridgeCall` creates the named bridge on first use and the agent leg joins the same bridge in its `onAnswer`.
- Returning `{"commands": []}` is valid and means "take no action."
- Top-level `events.onHangup` runs cleanup when the call ends.

## Reference: subsequent events

After `call.incoming` you'll typically receive (for the outbound agent leg you dialed):

- `call.answered`: the agent leg was answered.
- `call.busy` / `call.rejected` / `call.timeout` / `call.failed`: the leg ended without being answered.
- `call.hangup`: the call terminated.

**Inline events suppress the webhook.** If a `dial` (or other) command defines an `events` block, the platform runs that block and **no webhook fires** for those lifecycle events. If you omit `events` entirely, you'll get the webhook instead. An explicit empty `events: {}` *suppresses* the webhook without running anything, useful to ignore a leg's lifecycle. Because the example `dial` defines `events` inline, you won't see `call.answered`/`call.timeout` webhooks for the agent leg.

---

## Common patterns

| Want to... | Drop-in change in the response `commands` |
| --- | --- |
| Just play a message and hang up | A `messages` block with `events.onFinish: [{ "command": "hangup" }]`. |
| Read DTMF and route | Use the `webhook` SVAML command to call back into your backend after a prompt, then return a new sequence. |
| Record the call | Insert `startRecording` after the bridge; see [3.3 Recording & Transcription](../3.3-recording-transcription/description.md). |
| Detect voicemail before bridging | Insert `amd`; see [3.2 AMD](../3.2-amd/description.md). |
| Send to an AI agent | Replace the agent `dial` `to` with `{ "type": "VOICE_RELAY", ... }`; see [4.1 Voice Relay](../4.1-voice-relay/description.md). |
| Stream audio to a custom WS server | Use a `dial` with `to: { "type": "STREAM", ... }`; see [4.2 Stream Audio](../4.2-stream-audio/description.md). |
| Route a call to another number | See [2.2 Call Forwarding](../2.2-call-forwarding/description.md). |

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Latency** | Sinch enforces a **5-second response timeout** per webhook. Cache routing rules in memory and respond fast. |
| **Delivery semantics** | See the note below; the spec is inconsistent on whether webhooks retry. Treat your handler as needing to be both fast (in case of no retry) and idempotent (in case of retry). |
| **Header validation** | Check the CloudEvents headers (`ce-type` = `com.sinch.voice.webhook.v2`) and verify the request signature in the `Authorization` header against your service key/secret before acting. |
| **Persist critical state** | Persist anything you need from the `call.incoming` payload (e.g. for analytics or routing decisions) before responding. |
| **Fallback URL** | Configure `fallbackUrl` so a transient outage of your primary endpoint doesn't drop future calls. |
| **Static behavior for simple cases** | If the SVAML is fixed (always the same), switch the service to `STATIC` and embed the commands in `callBehavior.static`; no server needed. |
| **Number routing** | When several numbers point at one service, use `call.to.phone.number` to look up the routing target. |
| **Real HTTP stack** | The bash/ncat server is for local demos only; deploy the Python or Node.js version (or any real HTTP framework) behind TLS in production. |
| **Secrets management** | `export`-ing credentials is fine for local development; in production, inject them via your platform's secret manager or environment configuration instead of shell profiles. |


## What the OpenAPI spec says - at a glance

- `PATCH /v2/projects/{projectId}/services/{serviceId}` (`updateService`) sets `callBehavior`, one of `NONE`, `WEBHOOK`, `STATIC`.
- `POST /v2/projects/{projectId}/svaml/validate` validates a SVAML payload (`{ "svaml": {"commands":[ ...commands ]} }`) and returns `{ "isValid", "errors" }`.
- The incoming webhook is delivered with CloudEvents `ce-*` headers plus a JSON body containing `event` + `call` (`webhookRequest`).
- The response (`webhookResponse`) is `{ "commands": [...], "callName"?, "events"?: { "onHangup": [...] } }`. Commands run directly, no wrapper command. `callName` and `events` are honored only in responses to `call.incoming`.
- Authentication is HTTP Basic with your `KEY_ID` / `KEY_SECRET`.
