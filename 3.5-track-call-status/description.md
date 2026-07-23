# Track Call Status

## Overview

Voice API v2 gives you two complementary ways to know what is happening with a call:

- **Webhook events (recommended for real-time).** Sinch pushes lifecycle events
  (`call.incoming`, `call.answered`, `call.hangup`, and so on) to your HTTPS
  endpoint as they happen. This is the right choice whenever you need to *react*
  to a call: update a dashboard, log an SLA timestamp, or write a CRM record the
  moment a call ends.
- **Polling endpoints (fallback / on-demand).** `GET /calls/{callId}`,
  `GET /sessions/{sessionId}`, `GET /calls` (list & filter), and
  `GET /batches/{batchId}` (batch summary) let you read the platform's
  authoritative state on demand. Use them when you *cannot* run a public webhook
  receiver, for reconciliation and reporting jobs, or to back-fill state you may
  have missed (webhooks are at-most-once, as described below).

If you can run a public endpoint, use webhooks. Reach for polling only when you
can't, or for after-the-fact reporting.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with API credentials.
- A Sinch virtual phone number.
- (Webhooks only) A publicly accessible HTTPS URL. ngrok works during development.
- A way to start a call so there is something to track. The examples below start
  one for you; if you want to start calls separately, see
  [1.1 Outbound Call](../1.1-outbound-call/description.md).
- A runtime for the code examples: Node.js 18+ (built-in `fetch`), or Python 3.9+
  with `requests`, or PHP 8+ with the cURL extension.

## Setup

All requests use **HTTP Basic auth** with your access key as username and secret
as password. Instead of a config file, export the values into your shell so both
the `curl` commands and the code examples can read them from the environment:

```bash
export PROJECT_ID='...'            # your project UUID
export KEY_ID='...'                # access key ID  (Basic auth username)
export KEY_SECRET='...'            # access key secret (Basic auth password)
export SERVICE_ID='...'            # your voice service UUID
export SINCH_NUMBER='+1...'        # your Sinch virtual number (E.164)
export DESTINATION_NUMBER='+1...'  # number to call (E.164)
```

Every `curl` below authenticates with `-u "$KEY_ID:$KEY_SECRET"`. The Node.js,
Python, and PHP examples read the same variables via `process.env`,
`os.environ`, and `getenv()` respectively, so export them once in the terminal
where you run the code.

> **Chicken-and-egg note.** Tracking needs a `sessionId` (or `callId`) from a
> call that already exists. The tracking recipe below starts a call and captures
> its `sessionId` in one step. If you already started a call from
> [1.1 Outbound Call](../1.1-outbound-call/description.md), grab the `sessionId`
> from the `POST /calls` response and run `export SESSION_ID=...` before polling.

## First success: track a call in real time with webhooks (recommended)

This is the recommended path. Run a small receiver, point your service at it, and
start a call; Sinch streams the lifecycle to your terminal.

### 1. Run the receiver

The receiver below logs every webhook event with its CloudEvents headers and
acknowledges correctly. It answers `call.incoming` with a short goodbye and acks
every other event with `commands: []`. Use it to learn exactly what Sinch sends
for your flows. Note that there is no `accept` command in v2: you return the call
flow directly, typically starting with `answer`.

Pick one language, save the file, and run it.

#### Node.js

Save as `server.mjs`, then run `npm install express` and `node server.mjs`.

```js
// server.mjs — minimal Sinch Voice v2 webhook receiver
import express from "express";

const app = express();
app.use(express.json());

app.post("/voice/events", (req, res) => {
  const ce = {
    type:        req.header("ce-type"),
    source:      req.header("ce-source"),
    id:          req.header("ce-id"),
    time:        req.header("ce-time"),
    specversion: req.header("ce-specversion"),
  };
  const { event, call } = req.body || {};
  console.log(JSON.stringify({ ce, event, call }, null, 2));

  if (event === "call.incoming") {
    // Return the call flow directly. events.onHangup is honored on the
    // response to call.incoming.
    return res.status(200).json({
      commands: [
        { command: "answer" },
        {
          command: "messages",
          messages: [
            { type: "SAY", say: { text: "Thank you for calling. Goodbye.", voiceName: "Emma" } },
          ],
          events: { onFinish: [{ command: "hangup" }] },
        },
      ],
      events: { onHangup: [{ command: "hangup" }] },
    });
  }

  return res.status(200).json({ commands: [] });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Webhook receiver on :${PORT}`);
  console.log("Point callBehaviors.webhook.url -> https://<your-ngrok>/voice/events");
});
```

#### Python

Save as `server.py`, then run `pip install flask` and `python server.py`.

```python
# server.py — minimal Sinch Voice v2 webhook receiver
import os
import json
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.post("/voice/events")
def voice_events():
    ce = {
        "type":        request.headers.get("ce-type"),
        "source":      request.headers.get("ce-source"),
        "id":          request.headers.get("ce-id"),
        "time":        request.headers.get("ce-time"),
        "specversion": request.headers.get("ce-specversion"),
    }
    body = request.get_json(silent=True) or {}
    event = body.get("event")
    call = body.get("call")
    print(json.dumps({"ce": ce, "event": event, "call": call}, indent=2))

    if event == "call.incoming":
        # Return the call flow directly; events.onHangup is honored here.
        return jsonify({
            "commands": [
                {"command": "answer"},
                {
                    "command": "messages",
                    "messages": [
                        {"type": "SAY", "say": {"text": "Thank you for calling. Goodbye.", "voiceName": "Emma"}}
                    ],
                    "events": {"onFinish": [{"command": "hangup"}]},
                },
            ],
            "events": {"onHangup": [{"command": "hangup"}]},
        })

    return jsonify({"commands": []})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"Webhook receiver on :{port}")
    print("Point callBehaviors.webhook.url -> https://<your-ngrok>/voice/events")
    app.run(port=port)
```

#### PHP

Save as `server.php`, then run `php -S 0.0.0.0:3000 server.php`.

```php
<?php
// server.php — minimal Sinch Voice v2 webhook receiver

$path = parse_url($_SERVER["REQUEST_URI"], PHP_URL_PATH);
if ($_SERVER["REQUEST_METHOD"] !== "POST" || $path !== "/voice/events") {
    http_response_code(404);
    exit;
}

// Custom headers arrive as HTTP_CE_* in $_SERVER.
$ce = [
    "type"        => $_SERVER["HTTP_CE_TYPE"] ?? null,
    "source"      => $_SERVER["HTTP_CE_SOURCE"] ?? null,
    "id"          => $_SERVER["HTTP_CE_ID"] ?? null,
    "time"        => $_SERVER["HTTP_CE_TIME"] ?? null,
    "specversion" => $_SERVER["HTTP_CE_SPECVERSION"] ?? null,
];

$body  = json_decode(file_get_contents("php://input"), true) ?: [];
$event = $body["event"] ?? null;
$call  = $body["call"] ?? null;
error_log(json_encode(["ce" => $ce, "event" => $event, "call" => $call], JSON_PRETTY_PRINT));

header("Content-Type: application/json");

if ($event === "call.incoming") {
    // Return the call flow directly; events.onHangup is honored here.
    echo json_encode([
        "commands" => [
            ["command" => "answer"],
            [
                "command"  => "messages",
                "messages" => [
                    ["type" => "SAY", "say" => ["text" => "Thank you for calling. Goodbye.", "voiceName" => "Emma"]],
                ],
                "events" => ["onFinish" => [["command" => "hangup"]]],
            ],
        ],
        "events" => ["onHangup" => [["command" => "hangup"]]],
    ]);
    exit;
}

echo json_encode(["commands" => []]);
```

Once the receiver is running, expose it during development:

```bash
ngrok http 3000    # in another terminal
```

### 2. Point your service at it

Configure the service's `callBehaviors.webhook.url` to
`https://<your-ngrok>/voice/events`. A `dial` whose `events` property is **omitted** falls back to
this service-level webhook for its lifecycle events.

### 3. Start a call and watch the events arrive

Start an outbound call, or place an inbound call to `$SINCH_NUMBER`. You'll see events like:

```json
{ "event": "call.answered",
  "call": { "callId": "01ARZ...", "sessionId": "01BX5...", "callResult": "IN_PROGRESS" } }
```
```json
{ "event": "call.hangup",
  "call": { "callId": "01ARZ...", "sessionId": "01BX5...", "callResult": "COMPLETED", "callReason": "CALLEE_HANGUP" } }
```

When `call.hangup` arrives with a final `callResult`, the call is done. That's
your signal to write the outcome to your CRM, dashboard, or log.

### Events you'll receive

| Event | When |
| --- | --- |
| `call.incoming` | Inbound call arrived on a service with webhook behaviour. Respond with the call-flow `commands` directly (typically starting with `answer`). |
| `call.answered` | Outbound call answered by the recipient. |
| `call.busy` | Outbound call recipient was busy. |
| `call.rejected` | Outbound call rejected by the recipient. |
| `call.timeout` | Outbound call not answered within `dialTimeoutDurationSeconds`. |
| `call.hangup` | Call disconnected. |
| `call.failed` | Call could not be set up. |
| `call.webhook.<name>` | Dynamic event triggered by a `webhook` SVAML command (`webhookName` is prepended with `call.webhook.`). |

### Request format

Delivery uses CloudEvents binary mode. Each request looks like:

```http
POST /voice/events
ce-specversion: 1.0
ce-type:        com.sinch.voice.webhook.v2
ce-source:      projects/<projectId>/services/<serviceId>
ce-id:          <uuid>
ce-time:        2026-04-01T12:00:00Z
content-type:   application/json

{ "event": "call.answered",
  "call": { "callId": "...", "sessionId": "...", "callResult": "IN_PROGRESS" } }
```

### Webhook contract (from the spec)

- **5-second response timeout.** Slow responses may affect call quality, so do
  any heavy work asynchronously and respond quickly.
- **At-most-once delivery.** Each event is sent once and **never retried on
  failure**. Persist any critical state from the event before you return your
  response, and design your handler to tolerate missed events. This is exactly
  why polling is a useful back-fill, as described below.
- **`fallbackUrl`.** If a `fallbackUrl` is configured on the service and the
  primary URL starts returning errors, Sinch switches **future** requests to the
  fallback. The fallback is *not* called for the same request that failed.

> The "Webhooks overview" prose elsewhere in the API docs mentions retries; the
> authoritative "Timeouts and failover" section of the spec specifies
> at-most-once with no retries. We follow the authoritative section here.

### Suppressing webhooks per command

When you embed inline `events` on a `dial`, those events are handled directly and
**no webhook fires** for them:

- **No `events` key** means all lifecycle events go to the service webhook.
- **`events: {}` (empty object)** means no webhook fires *and* no inline handling
  occurs. Use sparingly; it's an easy trap that silently drops events.

## Fallback / on-demand: polling

Use polling when you can't run a public webhook endpoint, for reconciliation and
reporting, or to recover state you may have missed. Polling reads the platform's
authoritative state, so it's also the source of truth for post-call reporting.

The `curl` snippets below show the raw request and response for each endpoint.
The same Basic-auth pattern (`KEY_ID` / `KEY_SECRET`) used in the code recipe at
the end applies if you call these from Node.js, Python, or PHP.

### Fetch one call by id

```bash
curl -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/calls/$CALL_ID" | jq
```

Returns a `call` resource:

```json
{
  "callId":          "01ARZ3NDEKTSV4RRFFQ69G5FAA",
  "projectId":       "...",
  "serviceId":       "...",
  "sessionId":       "01BX5ZZKBKACTAV9WEVGEMMVRB",
  "direction":       "OUTBOUND",
  "originationType": "SERVER",
  "callType":        "PHONE",
  "callResult":      "COMPLETED",
  "callReason":      "CALLEE_HANGUP",
  "startTime":       "2025-02-10T09:00:00Z",
  "answerTime":      "2025-02-10T09:00:05Z",
  "endTime":         "2025-02-10T09:00:47Z",
  "callDurationSeconds": 42,
  "from": { "type": "PHONE", "phone": { "number": "+15551234567" } },
  "to":   { "type": "PHONE", "phone": { "number": "+15559876543" } },
  "callRate": { "currencyCode": "USD", "amount": "0.0123" },
  "callResourceUrl": "https://voice.api.sinch.com/v2/projects/.../calls/01ARZ3..."
}
```

The key state field is **`callResult`** (verified against the spec; these are the
only valid values):

| Value | Meaning | Kind |
| --- | --- | --- |
| `QUEUED` | Queued for initiation. | transitional |
| `INITIATED` | Connecting; recipient has not yet answered. | transitional |
| `IN_PROGRESS` | Answered and in progress. | transitional |
| `COMPLETED` | Answered and ended. | final |
| `REJECTED` | Rejected by the recipient. | final |
| `NO_ANSWER` | Not answered by the recipient. | final |
| `CANCEL` | Cancelled. | final |
| `BUSY` | Recipient was busy. | final |
| `FAILED` | Could not be completed. | final |

For ended calls, **`callReason`** explains *why* (verified against the spec;
these are the only valid values): `OK`, `NOT_AVAILABLE`, `CALLER_HANGUP`,
`CALLEE_HANGUP`, `MANAGER_HANGUP`, `DID_NOT_FOUND`, `INVALID_SCRIPT`,
`UNKNOWN_PRODUCT`, `NO_MORE_ROUTES`, `ERROR`.

### Fetch a session (all legs)

A session can contain multiple call legs: the original call plus any nested
`dial`s or transfers. To inspect them together:

```bash
curl -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/sessions/$SESSION_ID" | jq
```

```json
{
  "sessionId":  "01BX5ZZKBKACTAV9WEVGEMMVRB",
  "projectId":  "...",
  "serviceId":  "...",
  "state":      "COMPLETED",
  "createTime": "2025-02-10T09:00:00Z",
  "updateTime": "2025-02-10T09:00:47Z",
  "endTime":    "2025-02-10T09:00:47Z",
  "calls": [
    { "callId": "...", "callResult": "COMPLETED", "callReason": "CALLEE_HANGUP" },
    { "callId": "...", "callResult": "NO_ANSWER" }
  ]
}
```

The session-level `state` (`sessionStates`, verified against the spec) is one of:

| Value | Meaning | Kind |
| --- | --- | --- |
| `QUEUED` | Queued; no calls initiated yet. | transitional |
| `IN_PROGRESS` | At least one call initiated or received. | transitional |
| `COMPLETED` | Session completed; no more events. | final |

`COMPLETED` is the only final state, so that's your stop condition when polling.
Inspect `calls[]` for per-leg results; this is the right view for hunt or
forwarding flows where the question is "which leg won?".

> **Field note.** Each entry in `calls[]` is a `call` resource, which carries
> `callId`, `callResult`, `callReason`, `callDurationSeconds`, `answerTime`, and
> similar. It does **not** carry `callName`. That property exists only on the
> `dial` command you sent and as the path segment in
> `GET /sessions/{sessionId}/calls/{callName}`. Don't expect `callName` in this
> response.

### List & filter calls

`GET /v2/projects/{projectId}/calls` accepts query parameters:

| Parameter | Use |
| --- | --- |
| `serviceId` | Restrict to one service. |
| `from`, `to` | E.164 number filters. |
| `callType` | `PHONE`, `SIP`, or `STREAM`. |
| `callResult` | One of the `callResult` enum values above. |
| `callReason` | One of the `callReason` enum values above. |
| `startTime` | Include calls that started **at or after** this RFC 3339 timestamp. |
| `endTime` | Include calls that ended **before** this RFC 3339 timestamp (exclusive). |
| `pageSize`, `pageNumber` | Page size and 1-based page number. |

Example, listing all `FAILED` calls since midnight UTC:

```bash
curl -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/calls?callResult=FAILED&startTime=$(date -u +%Y-%m-%dT00:00:00Z)&pageSize=50" \
  | jq '.calls[] | {callId, callResult, callReason, from: .from.phone.number, to: .to.phone.number}'
```

Pagination uses the standard RFC 8288 `Link` header (relations such as `first`,
`prev`, `next`, `last`):

```
Link: <.../calls?pageNumber=2&pageSize=50>; rel="next",
      <.../calls?pageNumber=4&pageSize=50>; rel="last"
```

### Batch summary

For batch operations:

```bash
curl -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/batches/$BATCH_ID" | jq
```

The response includes counts (`callCount`, `completed`, `failed`, `inProgress`,
`queued`) and a per-session `callSessions[]` array, each entry having an `id` and
a `status` of `QUEUED`, `IN_PROGRESS`, or `COMPLETED`.

### Recipe: start a call and poll to completion (bounded)

This recipe starts an outbound call, captures its `sessionId`, then polls the
session until it reaches the `COMPLETED` final state. It uses a **bounded**
number of attempts and **backoff** so it can never loop forever, and it stops
immediately on the terminal state. Note that `callName` is not returned by the
API, so the final output does not include it.

Pick one language and run it in the same shell where you exported the variables.

#### Node.js

Save as `track-session.mjs`, then run `node track-session.mjs` (Node.js 18+).

```js
// track-session.mjs — start an outbound call, then poll to completion.
import { randomUUID } from "node:crypto";

const BASE = `https://voice.api.sinch.com/v2/projects/${process.env.PROJECT_ID}`;
const auth =
  "Basic " + Buffer.from(`${process.env.KEY_ID}:${process.env.KEY_SECRET}`).toString("base64");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const body = {
  commands: [
    {
      command: "dial",
      callName: "tracked",
      from: { type: "PHONE", phone: { number: process.env.SINCH_NUMBER } },
      to:   { type: "PHONE", phone: { number: process.env.DESTINATION_NUMBER } },
      dialTimeoutDurationSeconds: 30,
      events: {
        onAnswer: [
          {
            command: "messages",
            messages: [
              { type: "SAY", say: { text: "This call is being tracked. Goodbye.", voiceName: "Emma" } },
            ],
            events: { onFinish: [{ command: "hangup" }] },
          },
        ],
        onHangup: [{ command: "hangup" }],
      },
    },
  ],
};

// 1. Start the call. Inline events play a short message and hang up.
const startRes = await fetch(`${BASE}/calls`, {
  method: "POST",
  headers: {
    Authorization: auth,
    "Content-Type": "application/json",
    "Idempotency-Key": randomUUID(),
  },
  body: JSON.stringify(body),
});
const { sessionId } = await startRes.json();
if (!sessionId) throw new Error("No sessionId in response");
console.log(`Started sessionId=${sessionId}`);

// 2. Poll until COMPLETED (the only final session state), bounded with backoff.
let delay = 2000, maxDelay = 15000, attempt = 0, maxAttempts = 40, state;
while (attempt < maxAttempts) {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, { headers: { Authorization: auth } });
  ({ state } = await res.json());
  console.log(`state=${state}`);
  if (state === "COMPLETED") break; // terminal state -> stop
  attempt++;
  await sleep(delay);
  delay = Math.min(delay * 2, maxDelay);
}

// 3. Print per-leg results (callName is NOT returned by the API).
const finalRes = await fetch(`${BASE}/sessions/${sessionId}`, { headers: { Authorization: auth } });
const { calls = [] } = await finalRes.json();
for (const c of calls) {
  const { callId, callResult, callReason, callDurationSeconds, answerTime } = c;
  console.log(JSON.stringify({ callId, callResult, callReason, callDurationSeconds, answerTime }));
}
```

#### Python

Save as `track_session.py`, then run `pip install requests` and
`python track_session.py`.

```python
# track_session.py — start an outbound call, then poll to completion.
import os
import sys
import time
import json
import uuid
import requests

BASE = f"https://voice.api.sinch.com/v2/projects/{os.environ['PROJECT_ID']}"
AUTH = (os.environ["KEY_ID"], os.environ["KEY_SECRET"])

body = {
    "commands": [
        {
            "command": "dial",
            "callName": "tracked",
            "from": {"type": "PHONE", "phone": {"number": os.environ["SINCH_NUMBER"]}},
            "to":   {"type": "PHONE", "phone": {"number": os.environ["DESTINATION_NUMBER"]}},
            "dialTimeoutDurationSeconds": 30,
            "events": {
                "onAnswer": [
                    {
                        "command": "messages",
                        "messages": [
                            {"type": "SAY", "say": {"text": "This call is being tracked. Goodbye.", "voiceName": "Emma"}}
                        ],
                        "events": {"onFinish": [{"command": "hangup"}]},
                    }
                ],
                "onHangup": [{"command": "hangup"}],
            },
        }
    ]
}

# 1. Start the call. Inline events play a short message and hang up.
start = requests.post(
    f"{BASE}/calls",
    auth=AUTH,
    headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())},
    json=body,
)
session_id = start.json().get("sessionId")
if not session_id:
    sys.exit(f"No sessionId in response: {start.text}")
print(f"Started sessionId={session_id}")

# 2. Poll until COMPLETED (the only final session state), bounded with backoff.
delay, max_delay, attempt, max_attempts = 2, 15, 0, 40
while attempt < max_attempts:
    state = requests.get(f"{BASE}/sessions/{session_id}", auth=AUTH).json().get("state")
    print(f"state={state}")
    if state == "COMPLETED":  # terminal state -> stop
        break
    attempt += 1
    time.sleep(delay)
    delay = min(delay * 2, max_delay)

# 3. Print per-leg results (callName is NOT returned by the API).
calls = requests.get(f"{BASE}/sessions/{session_id}", auth=AUTH).json().get("calls", [])
fields = ("callId", "callResult", "callReason", "callDurationSeconds", "answerTime")
for c in calls:
    print(json.dumps({k: c.get(k) for k in fields}))
```

#### PHP

Save as `track-session.php`, then run `php track-session.php` (PHP 8+ with cURL).

```php
<?php
// track-session.php — start an outbound call, then poll to completion.

$base = "https://voice.api.sinch.com/v2/projects/" . getenv("PROJECT_ID");
$auth = getenv("KEY_ID") . ":" . getenv("KEY_SECRET");

function api(string $method, string $url, string $auth, ?array $body = null, array $extraHeaders = []): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_CUSTOMREQUEST  => $method,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_USERPWD        => $auth,
        CURLOPT_HTTPHEADER     => array_merge(["Content-Type: application/json"], $extraHeaders),
    ]);
    if ($body !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($body));
    }
    $resp = curl_exec($ch);
    curl_close($ch);
    return json_decode($resp, true) ?: [];
}

$body = [
    "commands" => [[
        "command"  => "dial",
        "callName" => "tracked",
        "from" => ["type" => "PHONE", "phone" => ["number" => getenv("SINCH_NUMBER")]],
        "to"   => ["type" => "PHONE", "phone" => ["number" => getenv("DESTINATION_NUMBER")]],
        "dialTimeoutDurationSeconds" => 30,
        "events" => [
            "onAnswer" => [[
                "command"  => "messages",
                "messages" => [
                    ["type" => "SAY", "say" => ["text" => "This call is being tracked. Goodbye.", "voiceName" => "Emma"]],
                ],
                "events" => ["onFinish" => [["command" => "hangup"]]],
            ]],
            "onHangup" => [["command" => "hangup"]],
        ],
    ]],
];

// 1. Start the call. Inline events play a short message and hang up.
$idem = bin2hex(random_bytes(16));
$start = api("POST", "$base/calls", $auth, $body, ["Idempotency-Key: $idem"]);
$sessionId = $start["sessionId"] ?? null;
if (!$sessionId) {
    fwrite(STDERR, "No sessionId in response\n");
    exit(1);
}
echo "Started sessionId=$sessionId\n";

// 2. Poll until COMPLETED (the only final session state), bounded with backoff.
$delay = 2; $maxDelay = 15; $attempt = 0; $maxAttempts = 40;
while ($attempt < $maxAttempts) {
    $state = api("GET", "$base/sessions/$sessionId", $auth)["state"] ?? null;
    echo "state=$state\n";
    if ($state === "COMPLETED") break; // terminal state -> stop
    $attempt++;
    sleep($delay);
    $delay = min($delay * 2, $maxDelay);
}

// 3. Print per-leg results (callName is NOT returned by the API).
$calls = api("GET", "$base/sessions/$sessionId", $auth)["calls"] ?? [];
$fields = ["callId", "callResult", "callReason", "callDurationSeconds", "answerTime"];
foreach ($calls as $c) {
    echo json_encode(array_intersect_key($c, array_flip($fields))) . "\n";
}
```

## What success looks like

Polling a healthy outbound call typically walks the session through
`QUEUED -> IN_PROGRESS -> COMPLETED`, and step 3 prints something like:

```json
{ "callId": "01ARZ...", "callResult": "COMPLETED", "callReason": "CALLEE_HANGUP", "callDurationSeconds": 42, "answerTime": "2025-02-10T09:00:05Z" }
```

If nobody answered, you'd instead see `"callResult": "NO_ANSWER"` (no
`callReason`), and the session would still reach `COMPLETED`.

## Real-life examples

- **CRM activity log**: write each call's final `callResult` to the customer
  record when `call.hangup` fires.
- **Operational dashboards**: poll `GET /sessions/{sessionId}` while a hunt is in
  progress to show which leg is currently ringing.
- **Reconciliation jobs**: a nightly job lists
  `GET /calls?startTime=...&endTime=...&callResult=FAILED` and re-triggers failed
  reminders. This is also how you back-fill any webhooks you missed.
- **SLA reporting**: log the delta between `call.incoming` and `call.answered` on
  the agent leg for every bridged call.