# Call Forwarding

## Overview

Voice API v2 has no dedicated "forward" or "transfer" command. Instead, you build forwarding from three primitives:

- **`dial`** creates a new outbound call leg within the same session.
- **`bridgeCall`** joins two legs together so both sides hear each other. The bridge is created when the first leg references it, and the second leg joins it.
- **`hangup`** drops a specific named leg.

Every forwarding pattern, whether it's unconditional, no-answer fallback, time-of-day routing, or a mid-call transfer, is just a combination of these three commands with different event triggers.

## The basic pattern: forward on no answer

This is the most common scenario. A caller dials in, you try a primary number, and if nobody picks up within a timeout, you try a fallback number instead. Both the primary and the fallback use the same bridge name, so whichever one answers ends up connected to the caller.

Here's what happens step by step:

1. The caller leg is answered and hears a hold prompt.
2. The caller joins a named bridge (creating it).
3. The platform dials the **primary** number.
4. If the primary answers, the hold prompt stops and the primary joins the same bridge. Two-way audio begins. Done.
5. If the primary doesn't answer within the timeout, the platform dials the **fallback** number.
6. If the fallback answers, the hold prompt stops and the fallback joins the bridge with the caller.
7. If the fallback also times out, the caller is hung up.

## How the SVAML expresses this

The structure is nested: the fallback `dial` lives inside the primary's `onTimeout` event. That nesting *is* the forwarding logic.

```
caller dial
  └─ onAnswer
       ├─ play hold prompt
       ├─ bridgeCall "fwd-bridge"      ← caller joins the bridge
       └─ primary dial
            ├─ onAnswer  → stop hold, bridgeCall "fwd-bridge"
            └─ onTimeout → fallback dial
                              ├─ onAnswer  → stop hold, bridgeCall "fwd-bridge"
                              └─ onTimeout → hang up caller
```

Both the caller and the destination explicitly join the same `bridgeName`. The caller joins first (creating the bridge); whichever destination answers joins the same one, and two-way audio begins.

## Minimal working example (outbound test call)

This places an outbound call to your own phone, then tries a primary number (let it ring out), and falls through to a fallback. No webhook server needed.

Set your environment variables first:

```bash
export PROJECT_ID="your-project-id"
export KEY_ID="your-key-id"
export KEY_SECRET="your-key-secret"
export SINCH_NUMBER="+15551234567"       # Your Sinch virtual number
export CALLER_NUMBER="+15550009999"      # Your mobile (answer this one)
export PRIMARY_NUMBER="+15557770001"     # Let this ring out
export FALLBACK_NUMBER="+15557770002"    # Should ring after primary times out
```

### Python

```python
import os, uuid, requests

body = {
    "commands": [{
        "command": "dial",
        "callName": "caller",
        "from": {"type": "PHONE", "phone": {"number": os.environ["SINCH_NUMBER"]}},
        "to":   {"type": "PHONE", "phone": {"number": os.environ["CALLER_NUMBER"]}},
        "dialTimeoutDurationSeconds": 30,
        "events": {
            "onAnswer": [
                # Step 1: play hold music while we try the primary
                {"command": "messages", "messagesName": "hold",
                 "messages": [{"type": "SAY",
                   "say": {"text": "Connecting your call.", "voiceName": "Emma"}}]},

                # Step 2: caller joins the bridge (created on first reference)
                {"command": "bridgeCall", "bridgeName": "fwd-bridge"},

                # Step 3: dial the primary number
                {"command": "dial",
                 "callName": "primary",
                 "from": {"type": "PHONE", "phone": {"number": os.environ["SINCH_NUMBER"]}},
                 "to":   {"type": "PHONE", "phone": {"number": os.environ["PRIMARY_NUMBER"]}},
                 "dialTimeoutDurationSeconds": 20,
                 "events": {
                     # Primary answered: stop hold, bridge them
                     "onAnswer": [
                         {"command": "stopMessages", "messagesName": "hold"},
                         {"command": "bridgeCall", "bridgeName": "fwd-bridge"},
                     ],
                     # Primary didn't answer: try the fallback
                     "onTimeout": [{
                         "command": "dial",
                         "callName": "fallback",
                         "from": {"type": "PHONE", "phone": {"number": os.environ["SINCH_NUMBER"]}},
                         "to":   {"type": "PHONE", "phone": {"number": os.environ["FALLBACK_NUMBER"]}},
                         "dialTimeoutDurationSeconds": 20,
                         "events": {
                             "onAnswer": [
                                 {"command": "stopMessages", "messagesName": "hold"},
                                 {"command": "bridgeCall", "bridgeName": "fwd-bridge"},
                             ],
                             "onTimeout": [
                                 {"command": "hangup", "callName": "caller"},
                             ],
                         },
                     }],
                 }},
            ],
            "onHangup": [
                {"command": "hangup", "callName": "primary"},
                {"command": "hangup", "callName": "fallback"},
            ],
        },
    }]
}

resp = requests.post(
    f"https://voice.api.sinch.com/v2/projects/{os.environ['PROJECT_ID']}/calls",
    auth=(os.environ["KEY_ID"], os.environ["KEY_SECRET"]),
    headers={
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    },
    json=body,
)
print(resp.status_code, resp.json())
```

### Node.js

```javascript
import { randomUUID } from "crypto";

const { PROJECT_ID, KEY_ID, KEY_SECRET,
        SINCH_NUMBER, CALLER_NUMBER, PRIMARY_NUMBER, FALLBACK_NUMBER } = process.env;

const body = {
  commands: [{
    command: "dial",
    callName: "caller",
    from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
    to:   { type: "PHONE", phone: { number: CALLER_NUMBER } },
    dialTimeoutDurationSeconds: 30,
    events: {
      onAnswer: [
        // Step 1: play hold music while we try the primary
        { command: "messages", messagesName: "hold",
          messages: [{ type: "SAY", say: { text: "Connecting your call.", voiceName: "Emma" } }] },

        // Step 2: caller joins the bridge (created on first reference)
        { command: "bridgeCall", bridgeName: "fwd-bridge" },

        // Step 3: dial the primary number
        { command: "dial",
          callName: "primary",
          from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
          to:   { type: "PHONE", phone: { number: PRIMARY_NUMBER } },
          dialTimeoutDurationSeconds: 20,
          events: {
            // Primary answered: stop hold, bridge them
            onAnswer: [
              { command: "stopMessages", messagesName: "hold" },
              { command: "bridgeCall", bridgeName: "fwd-bridge" },
            ],
            // Primary didn't answer: try the fallback
            onTimeout: [{
              command: "dial",
              callName: "fallback",
              from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
              to:   { type: "PHONE", phone: { number: FALLBACK_NUMBER } },
              dialTimeoutDurationSeconds: 20,
              events: {
                onAnswer: [
                  { command: "stopMessages", messagesName: "hold" },
                  { command: "bridgeCall", bridgeName: "fwd-bridge" },
                ],
                onTimeout: [{ command: "hangup", callName: "caller" }],
              },
            }],
          },
        },
      ],
      onHangup: [
        { command: "hangup", callName: "primary" },
        { command: "hangup", callName: "fallback" },
      ],
    },
  }],
};

const auth = "Basic " + Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString("base64");

const resp = await fetch(
  `https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/calls`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: auth, "Idempotency-Key": randomUUID() },
    body: JSON.stringify(body),
  }
);
console.log(resp.status, await resp.json());
```

## What to expect when you run it

1. Your phone (`CALLER_NUMBER`) rings. Answer it and you'll hear "Connecting your call."
2. `PRIMARY_NUMBER` rings for ~20 seconds with no answer.
3. Within about a second, `FALLBACK_NUMBER` rings.
4. Answer the fallback and you get two-way audio with the caller leg.

## Key concepts to remember

**Every leg needs a `callName`.** This is how you reference a specific leg later, for example when hanging up just the agent without dropping the caller.

**Both sides must join the bridge.** The caller joins the bridge explicitly via `bridgeCall` (which creates it on first reference). Whichever destination answers also calls `bridgeCall` with the same `bridgeName`, joining the existing bridge. Using the same name across primary and fallback is what makes the handoff seamless.

**Events drive the forwarding logic.** The `events` block on a `dial` command gives you hooks for what happens next. The ones relevant to forwarding:

| Event | When it fires | Typical action |
|---|---|---|
| `onAnswer` | Destination picked up | Bridge the legs together |
| `onTimeout` | Rang for the full timeout, no answer | Dial the next number |
| `onBusy` | Destination returned busy | Dial the next number |
| `onReject` | Destination actively declined | Dial the next number |
| `onFailure` | Call setup failed (carrier error, unreachable) | Dial the next number |
| `onHangup` | A leg disconnected | Clean up the session |

**Always send an `Idempotency-Key`** on `POST /calls` so a retried request doesn't accidentally place a duplicate call.

## Adapting this pattern

To handle busy, reject, or carrier failure in addition to no-answer, add the same fallback `dial` block under `onBusy`, `onReject`, and `onFailure` on the primary leg. SVAML doesn't support references, so each event handler needs its own copy of the fallback commands.

To make the routing dynamic (time-of-day, per-caller lookup, agent availability), switch from a static outbound call to an inbound webhook. Your server receives a `call.incoming` event and returns the same SVAML structure, but you choose the destination at runtime based on whatever your backend knows.