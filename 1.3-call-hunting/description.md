# Call Hunting

## Overview

**Call hunting** is the pattern where the Voice API tries to reach a person at one of several phone numbers and stops as soon as someone answers. There is no dedicated `hunt` command: you build the pattern by chaining a `dial` command's lifecycle events (`onAnswer`, `onTimeout`, `onBusy`, `onReject`, `onFailure`) and using `bridgeCall` to connect the answering leg back to the caller.

Three flavors of hunt are covered here:

| Pattern | Description | When to use |
| --- | --- | --- |
| **Sequential hunt** | Try agent A; if no answer, try B; if no answer, try C. | Skill-based routing, cost-sensitive dispatch, on-call escalation. |
| **Simultaneous ring (sim-ring)** | Ring all agents at once; first to answer wins, others cancelled. | Time-critical alerts, smallest pool, "first available" lead distribution. |
| **Hybrid (groups in sequence)** | Sim-ring tier 1; if all tier-1 miss, sim-ring tier 2. | Tiered support, follow-the-sun teams. |

All three patterns are pure SVAML; no proprietary extension is needed.

**Start here:** the fastest path to a working hunt is **Pattern 1 (sequential hunt, static SVAML)**. It runs from one `curl` with no backend server, no public URL, and no service configuration. Get that working first, then reach for the webhook-driven and tiered variants when you need a dynamic agent pool.

## Real-life examples

- **Sales lead dispatch**: a new inbound web lead triggers an outbound campaign; the API hunts through a list of sales reps until one picks up, then bridges the lead in.
- **On-call escalation**: a monitoring alert triggers an outbound call that hunts primary → secondary → manager until acknowledged.
- **Field-service dispatch**: a customer requests a callback; the platform hunts available technicians by region until one accepts.
- **Personal find-me**: one published number is hunted across an employee's desk, mobile, and home line.

## Setup

Every example below reads its configuration from environment variables. Export them in the shell session you'll run the examples from (or put the `export` lines in a file you `source`):

```bash
# Credentials and project (Sinch Dashboard: https://dashboard.sinch.com)
export PROJECT_ID="your-project-id"
export KEY_ID="your-access-key-id"
export KEY_SECRET="your-access-key-secret"

# Numbers (E.164)
export SINCH_NUMBER="+15551234567"        # Sinch virtual number, caller ID on every outbound leg
export CUSTOMER_NUMBER="+15559876543"     # the customer/target you connect the agent to
export AGENT_NUMBERS="+15551110001,+15551110002,+15551110003"

# Patterns 2 and 4 only (webhook-driven)
export SERVICE_ID="your-voice-service-id"
export CALLBACK_URL="https://<your-ngrok-subdomain>.ngrok.io"   # public HTTPS base URL
export PORT=3000                                                # webhook server port
```

| Variable | Used by | Where to get it |
| --- | --- | --- |
| `PROJECT_ID` | all | [Sinch Dashboard](https://dashboard.sinch.com) → your project. |
| `KEY_ID` / `KEY_SECRET` | all (HTTP Basic auth) | Dashboard → Access Keys. Sent as `-u "$KEY_ID:$KEY_SECRET"`. |
| `SINCH_NUMBER` | all | A Sinch virtual number (E.164) provisioned on the project. Used as the caller ID (`from`) on every outbound leg. |
| `CUSTOMER_NUMBER` | all | The customer/target you connect the agent to. |
| `AGENT_NUMBERS` | all | Comma-separated E.164 list of agent destinations. The shell examples read the first three; the Node server reads the whole list. |
| `SERVICE_ID` | Patterns 2/4 only | Dashboard → your voice service. Needed to configure the webhook. |
| `CALLBACK_URL` | Patterns 2/4 only | Your publicly reachable webhook base URL. During development run `ngrok http $PORT` and use the HTTPS URL it prints. |
| `PORT` | Patterns 2/4 Node server | The port the webhook server listens on; defaults to `3000` if unset. Point ngrok at the same port. |

**Tools:** `bash`, `curl`, and (optional but recommended) `jq` and `uuidgen` for the shell patterns; `node` (ES modules) + `npm install express` and `ngrok` for the webhook server.

Required environment for the first-success path (Pattern 1): `PROJECT_ID`, `KEY_ID`, `KEY_SECRET`, `SINCH_NUMBER`, `CUSTOMER_NUMBER`, `AGENT_NUMBERS`. **No webhook server or `CALLBACK_URL` is needed for Pattern 1.**

## Prerequisites knowledge

- Familiarity with the SVAML v2 command reference, specifically `dial`, `bridgeCall`, `hangup`, `messages`/`stopMessages`, and the `events` block.
- Auth is **HTTP Basic** (`KEY_ID:KEY_SECRET`).

## How it works

A hunt always involves **two roles** inside one call session:

- **Target**: the customer/lead you ultimately want connected. Often this is the *first* leg you dial. (For hunts that begin with an inbound call, the inbound leg plays this role.)
- **Agent pool**: the list of internal numbers the platform tries until one answers.

Three SVAML primitives carry the pattern:

1. **`dialTimeoutDurationSeconds`** decides how long each ring attempt lasts before moving on. When it expires, the `onTimeout` event fires.
2. **`events.onAnswer`** is where you `stopMessages` and `bridgeCall` the winning agent to the target.
3. **`events.onTimeout` / `onBusy` / `onReject` / `onFailure`** are where you issue the *next* `dial` in the hunt chain.

`events.onHangup` is what tears the session down once any leg drops.

---

## Pattern 1 — Sequential hunt (static SVAML, no backend required) ← start here

Call the customer, and on answer try Agent A → B → C until someone picks up. Because the hunt list is static, you send the entire flow inline with the initial `POST /v2/projects/{projectId}/calls` request: **no webhook server, no public URL, no service configuration**. This is the fastest way to see a hunt work end to end.

### Run it

Paste this into a shell where the [Setup](#setup) variables are exported. It splits `AGENT_NUMBERS` into three agent variables, builds the SVAML body with your numbers substituted, and posts it:

```bash
IFS=',' read -r A1 A2 A3 <<< "$AGENT_NUMBERS"
A2="${A2:-$A1}"; A3="${A3:-$A2}"

BODY=$(cat <<EOF
{
  "commands": [
    {
      "command": "dial",
      "callName": "customer",
      "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
      "to":   { "type": "PHONE", "phone": { "number": "${CUSTOMER_NUMBER}" } },
      "dialTimeoutDurationSeconds": 30,
      "events": {
        "onAnswer": [
          { "command": "messages", "messagesName": "hold",
            "messages": [ { "type": "SAY",
              "say": { "text": "Please hold while we connect you to an agent.", "voiceName": "Emma" } } ] },

          { "command": "dial", "callName": "agent-1",
            "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
            "to":   { "type": "PHONE", "phone": { "number": "${A1}" } },
            "dialTimeoutDurationSeconds": 20,
            "events": {
              "onAnswer": [
                { "command": "stopMessages", "messagesName": "hold" },
                { "command": "bridgeCall",   "bridgeName": "hunt-bridge" }
              ],
              "onTimeout": [
                { "command": "dial", "callName": "agent-2",
                  "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
                  "to":   { "type": "PHONE", "phone": { "number": "${A2}" } },
                  "dialTimeoutDurationSeconds": 20,
                  "events": {
                    "onAnswer": [
                      { "command": "stopMessages", "messagesName": "hold" },
                      { "command": "bridgeCall",   "bridgeName": "hunt-bridge" }
                    ],
                    "onTimeout": [
                      { "command": "dial", "callName": "agent-3",
                        "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
                        "to":   { "type": "PHONE", "phone": { "number": "${A3}" } },
                        "dialTimeoutDurationSeconds": 20,
                        "events": {
                          "onAnswer": [
                            { "command": "stopMessages", "messagesName": "hold" },
                            { "command": "bridgeCall",   "bridgeName": "hunt-bridge" }
                          ],
                          "onTimeout": [
                            { "command": "hangup", "callName": "customer" }
                          ]
                        }
                      }
                    ]
                  }
                }
              ]
            }
          }
        ],
        "onHangup": [ { "command": "hangup" } ]
      }
    }
  ]
}
EOF
)

curl -s -X POST \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/calls" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d "$BODY" | jq '.'
```

**Key points**

- Each nested `dial` is independent: when `onTimeout` fires on `agent-1`, that leg has already been torn down, so the next `dial` opens a fresh channel. (Per the spec: "Commands that appear inside event handlers form independent sequences and execute in their own context.")
- `bridgeCall` with a shared `bridgeName` connects the answering agent to `customer`. The first call to enter the bridge creates it; the second joins (auto-created on first reference, per the `bridgeCall` schema).
- The `customer` leg keeps playing the `hold` messages (`messages` is non-blocking) until the answering agent issues `stopMessages` + `bridgeCall`.

### What success looks like

- The `customer` number rings; on answer the caller hears "Please hold…".
- `agent-1` rings. Answer it → the hold message stops and the two legs are bridged into a single conversation.
- Let `agent-1` ring out (or use a number you can leave unanswered) → after `dialTimeoutDurationSeconds`, `agent-2` rings, and so on.
- If all three time out, the caller hears the apology message and the call hangs up.

### When *not* to use static SVAML

- The hunt list changes per call (skill matching, agent presence, geolocation).
- You need to record the result of each leg in your own systems before deciding the next number.
- You need to retry the same agent later in the day.

Use the webhook pattern below in those cases.

---

## Pattern 2 — Sequential hunt (webhook-driven, dynamic agent pool)

Here the platform calls *your* backend on every lifecycle event, and your backend decides the next number. This costs an HTTP round-trip per hop but gives you full control over the agent list.

### 1. Configure the service for webhooks

```bash
curl -X PATCH \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/services/$SERVICE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "callBehavior": {
      "type": "WEBHOOK",
      "webhook": {
        "url": "'"$CALLBACK_URL"'/voice/events",
        "fallbackUrl": "'"$CALLBACK_URL"'/voice/events"
      }
    }
  }'
```

### 2. Initiate the customer call without inline `events`

When the `events` property is **omitted** on a `dial`, Sinch falls back to the service-level webhook for that leg's lifecycle events, which is exactly what we want.

```bash
curl -s -X POST \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/calls" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "commands": [
      {
        "command": "dial",
        "callName": "customer",
        "from": { "type": "PHONE", "phone": { "number": "'"$SINCH_NUMBER"'" } },
        "to":   { "type": "PHONE", "phone": { "number": "'"$CUSTOMER_NUMBER"'" } },
        "dialTimeoutDurationSeconds": 30
      }
    ]
  }' | jq '.'
```


### 3. The webhook request/response contract

Webhook delivery uses **CloudEvents 1.0 HTTP binary mode**. CloudEvent metadata travels in `ce-*` headers (`ce-type` is `com.sinch.voice.webhook.v2`); the JSON body is the event payload with **two** properties: `event` and `call`.

```http
POST /voice/events
ce-specversion: 1.0
ce-type: com.sinch.voice.webhook.v2
ce-source: projects/<projectId>/services/<serviceId>
ce-id: <uuid>
ce-time: 2026-04-01T12:00:00Z
content-type: application/json

{
  "event": "call.answered",
  "call": { "callId": "...", "sessionId": "01BX...", "direction": "OUTBOUND", "callResult": "...", ... }
}
```

The `event` enum (verified) includes: `call.incoming`, `call.answered`, `call.busy`, `call.rejected`, `call.timeout`, `call.hangup`, `call.failed`, plus `call.amd.*`, `call.message.*`, `call.recording.*`.

Respond with HTTP `200` and a `{ "commands": [...] }` body. An empty `commands` array means "take no action."


### 4. The webhook server

The server maintains an in-memory hunt cursor keyed by `sessionId` (a restart wipes in-flight hunts; persist the cursor in a real store for production). Its flow:

1. `call.answered` for the customer leg → respond with the `hold` message plus the first agent `dial` (no `events`, so its events also flow back to the webhook).
2. `call.timeout` / `call.busy` / `call.rejected` / `call.failed` for an agent leg → look up the hunt cursor for that `sessionId`, advance it, and respond with the next agent `dial`, or a `messages` + `hangup` if the list is exhausted.
3. `call.answered` for an agent leg → respond with `stopMessages` + `bridgeCall`.
4. `call.hangup` → clear the cursor and respond with an empty `commands` array; the platform tears the session down.

Save this as `server.js` (it reads `SINCH_NUMBER`, `AGENT_NUMBERS`, and `PORT` from the exported environment):

```javascript
// Sinch Voice API v2 — Webhook-driven sequential hunt (Pattern 2).
// Maintains an in-memory cursor keyed by sessionId. Restart wipes state.
//
// Requirements: npm install express
// Run:  node server.js
// Expose: ngrok http $PORT  (then set the service's callBehavior.webhook.url)

import express from "express";

const SINCH_NUMBER = process.env.SINCH_NUMBER || (() => { throw new Error("SINCH_NUMBER not set"); })();
const AGENT_LIST = (process.env.AGENT_NUMBERS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
if (AGENT_LIST.length === 0) throw new Error("AGENT_NUMBERS not set");
const PORT = process.env.PORT || 3000;

// In-memory hunt cursor: sessionId -> { index }
const cursors = new Map();

function dialAgent(number, name) {
  return {
    command: "dial",
    callName: name,
    from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
    to:   { type: "PHONE", phone: { number } },
    dialTimeoutDurationSeconds: 20,
    // No `events` => fall back to the service webhook for lifecycle events.
  };
}

const app = express();
app.use(express.json());

app.post("/voice/events", (req, res) => {
  const { event, call } = req.body || {};
  if (!event || !call) return res.status(200).json({ commands: [] });

  const sessionId = call.sessionId;
  const callName  = call.callName;

  console.log(`event=${event} sessionId=${sessionId} callName=${callName}`);

  // Inbound call arrives — the inbound leg IS the customer; jump straight
  // to dialing agent 1. The inbound leg joins the bridge here; the
  // answering agent joins it too.
  if (event === "call.incoming") {
    cursors.set(sessionId, { index: 0 });
    return res.status(200).json({
      commands: [
        { command: "answer" },
        { command: "messages", messagesName: "hold",
          messages: [{ type: "SAY", say: { text: "Please hold while we find an agent.", voiceName: "Emma" } }] },
        { command: "bridgeCall", bridgeName: "hunt-bridge" },
        dialAgent(AGENT_LIST[0], "agent-0"),
      ],
      events: { onHangup: [{ command: "hangup" }] },
    });
  }

  // Outbound call answered (customer leg picked up after we dialed them).
  if (event === "call.answered" && callName === "customer") {
    cursors.set(sessionId, { index: 0 });
    return res.status(200).json({
      commands: [
        { command: "messages", messagesName: "hold",
          messages: [{ type: "SAY", say: { text: "Please hold while we find an agent.", voiceName: "Emma" } }] },
        dialAgent(AGENT_LIST[0], "agent-0"),
      ],
    });
  }

  // Agent leg answered — bridge them in and stop the hold message.
  if (event === "call.answered" && callName?.startsWith("agent-")) {
    return res.status(200).json({
      commands: [
        { command: "stopMessages", messagesName: "hold" },
        { command: "bridgeCall",   bridgeName: "hunt-bridge" },
      ],
    });
  }

  // Agent leg failed to connect — advance the cursor and try the next agent.
  const failed = ["call.timeout", "call.busy", "call.rejected", "call.failed"].includes(event);
  if (failed && callName?.startsWith("agent-")) {
    const cursor = cursors.get(sessionId) || { index: 0 };
    cursor.index += 1;
    cursors.set(sessionId, cursor);

    if (cursor.index >= AGENT_LIST.length) {
      // No more agents — apologise and hang up.
      cursors.delete(sessionId);
      return res.status(200).json({
        commands: [
          { command: "messages", messagesName: "noanswer",
            messages: [{ type: "SAY",
              say: { text: "We are sorry, no agent is available. Please try again later.",
                     voiceName: "Emma" } }],
            events: { onFinish: [{ command: "hangup" }] } },
        ],
      });
    }
    return res.status(200).json({
      commands: [dialAgent(AGENT_LIST[cursor.index], `agent-${cursor.index}`)],
    });
  }

  // Cleanup on hangup of the customer leg.
  if (event === "call.hangup") {
    cursors.delete(sessionId);
  }

  return res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`Hunt webhook server listening on :${PORT}`);
  console.log(`Configure service callBehavior.webhook.url -> https://<your-ngrok>/voice/events`);
});
```

When `call.answered` fires for an agent leg, the response it sends is:

```json
HTTP/1.1 200 OK
{
  "commands": [
    { "command": "stopMessages", "messagesName": "hold" },
    { "command": "bridgeCall",   "bridgeName": "hunt-bridge" }
  ]
}
```

### 5. Run the server

```bash
npm install express
node server.js               # logs the port it is listening on
ngrok http $PORT             # in a second terminal
# Then run step 1 with CALLBACK_URL set to the ngrok HTTPS URL,
# and step 2 to start the customer call.
```

---

## Pattern 3 — Simultaneous ring (sim-ring)

For a "first available wins" hunt, fan out multiple `dial` commands in parallel from the customer leg, and let the first `onAnswer` race the others to `bridgeCall`. Because `dial` is non-blocking, all three calls start within a few milliseconds of each other.

### Run it

Paste this into a shell where the [Setup](#setup) variables are exported:

```bash
IFS=',' read -r A1 A2 A3 <<< "$AGENT_NUMBERS"
A2="${A2:-$A1}"; A3="${A3:-$A2}"

BODY=$(cat <<EOF
{
  "commands": [
    {
      "command": "dial",
      "callName": "customer",
      "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
      "to":   { "type": "PHONE", "phone": { "number": "${CUSTOMER_NUMBER}" } },
      "dialTimeoutDurationSeconds": 30,
      "events": {
        "onAnswer": [
          { "command": "messages", "messagesName": "hold",
            "messages": [ { "type": "SAY",
              "say": { "text": "Connecting you now.", "voiceName": "Emma" } } ] },

          { "command": "dial", "callName": "agent-A",
            "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
            "to":   { "type": "PHONE", "phone": { "number": "${A1}" } },
            "dialTimeoutDurationSeconds": 25,
            "events": {
              "onAnswer": [
                { "command": "stopMessages", "messagesName": "hold" },
                { "command": "hangup",       "callName":     "agent-B" },
                { "command": "hangup",       "callName":     "agent-C" },
                { "command": "bridgeCall",   "bridgeName":   "hunt-bridge" }
              ]
            }
          },
          { "command": "dial", "callName": "agent-B",
            "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
            "to":   { "type": "PHONE", "phone": { "number": "${A2}" } },
            "dialTimeoutDurationSeconds": 25,
            "events": {
              "onAnswer": [
                { "command": "stopMessages", "messagesName": "hold" },
                { "command": "hangup",       "callName":     "agent-A" },
                { "command": "hangup",       "callName":     "agent-C" },
                { "command": "bridgeCall",   "bridgeName":   "hunt-bridge" }
              ]
            }
          },
          { "command": "dial", "callName": "agent-C",
            "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
            "to":   { "type": "PHONE", "phone": { "number": "${A3}" } },
            "dialTimeoutDurationSeconds": 25,
            "events": {
              "onAnswer": [
                { "command": "stopMessages", "messagesName": "hold" },
                { "command": "hangup",       "callName":     "agent-A" },
                { "command": "hangup",       "callName":     "agent-B" },
                { "command": "bridgeCall",   "bridgeName":   "hunt-bridge" }
              ]
            }
          }
        ],
        "onHangup": [ { "command": "hangup" } ]
      }
    }
  ]
}
EOF
)

curl -s -X POST \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/calls" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d "$BODY" | jq '.'
```

**Race-condition guards**

- Losing legs are torn down with `hangup callName: "..."` from inside the winner's `onAnswer`. A `hangup` targeted at a leg that has already ended is a no-op (the `hangup` schema permits targeting an ended leg; subsequent media commands simply do not execute), so two near-simultaneous answers cannot deadlock the session.
- Only the *first* leg to enter the bridge is connected to `customer`. Late answers are dropped by the explicit `hangup` calls.


---

## Pattern 4 — Tiered (hybrid) hunt

Combine the two: sim-ring tier 1, then on failure of *all* tier-1 legs, fall through to sim-ring tier 2. The cleanest implementation is **webhook-driven**: your backend keeps a tally of which tier-1 legs have ended, fires tier 2 when the count reaches the tier-1 size, and uses `hangup callName:` to clean up any tier-1 stragglers.

Pseudocode:

```text
on call.answered(customer)              -> commands: hold + fan out tier 1
on call.timeout|busy|rejected|failed(tier1 leg)
                                        -> tier1_done++
                                           if tier1_done == |tier1| -> commands: fan out tier 2
                                           else                     -> commands: []
on call.answered(agent)                 -> commands: stopMessages + hangup-others + bridgeCall
on call.hangup(customer)                -> commands: [] (platform tears session down)
```


---

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **All-miss handling** | Ensure every hunt terminates when no agent answers: `onTimeout`/`onBusy`/`onReject`/`onFailure` on the last sequential leg (or a service-level fallback / `maxCallDurationSeconds` for sim-ring). The static Pattern 1 above only chains on `onTimeout`; add the other three. |
| **Voicemail / AMD** | Insert an `amd` command before `bridgeCall` so a voicemail pickup doesn't count as a successful hunt. AMD events are `onHuman`/`onMachine`/`onBeep`/`onUnknown` (webhook: `call.amd.machine` etc.). On machine/beep, treat the leg as a miss. |
| **Whisper before bridging** | Replace `bridgeCall` in the winner's `onAnswer` with a `messages` ("Incoming lead from Madrid…") followed by a `webhook` SVAML command that bridges only after the agent confirms. |
| **Concurrent hunts to the same agent** | The platform does not deduplicate. Track agent occupancy in your backend and skip busy agents rather than relying on `call.busy`. |
| **Compliance / call recording** | Add `startRecording` immediately after the winning `bridgeCall`. See [3.3 Recording & Transcription](../3.3-recording-transcription/description.md). |
| **Rate / pacing** | For mass outbound (one customer to one of N agents, with M customers in flight) use the [Batch API](../1.2-call-pacing/description.md): set `batchOptions.maxCps` so you don't burst-dial your trunk. |
| **Observability** | Each leg has its own `callId`. Persist these keyed by `sessionId` for post-call reporting. |
| **Cost** | Each `dial` you fan out is a billable attempt even if unanswered. Sequential is cheaper than sim-ring; sim-ring is faster. |
| **Cancellation** | If the customer hangs up during the hunt, wire `onHangup` on the `customer` leg (Patterns 1 and 3 do this) or return a `hangup` from the `call.hangup` webhook event so the remaining agent legs are torn down. |

## Testing

Use a sandboxed project and your own mobile number as a stand-in for "agent 1" with `dialTimeoutDurationSeconds: 10`. Reject the call instead of answering; with full failure-event handling, the next agent should ring immediately. (With the static Pattern 1 as written, only *timeout* advances the hunt; let it ring out to test progression.)

Run the Pattern 1 example, then pull the resulting session to verify which leg won:

```bash
# Note: session calls expose callId/callResult/callReason/answerTime — NOT callName.
curl -s -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/sessions/$SESSION_ID" \
  | jq '.calls[] | {callId, callResult, callReason, answerTime, to}'
```
