# 4.5 Build an AI IVR (Voice Relay + call patching)

## Overview

This tutorial builds an **AI-powered IVR** (Interactive Voice Response): a caller
reaches an AI agent that *understands* what they want, in their own words, and
then **patches a human agent into the live call**. No DTMF menus ("press 1 for
sales"), no fixed scripts.

It combines two Voice API v2 capabilities:

1. **Voice Relay** ([4.1](../4.1-voice-relay/description.md)): the call is
   bridged to a WebSocket server that exchanges *text* with Sinch. Sinch does the
   speech-to-text and text-to-speech; your server only sees transcribed turns and
   replies with text. We use it here to run an LLM-driven intent classifier.
2. **Live call patching** is the new idea in this tutorial. While the call is
   running, your server sends a `PATCH /v2/projects/{projectId}/calls/{callId}`
   with fresh SVAML to **dial a human agent and bridge them into the existing
   call**. The AI then drops out and the caller is talking to a person.

The worked example is a house-selling company's call centre. The AI greets the
caller, classifies the intent as **Sales** or **Support**, tells the caller it's
connecting them, and patches the matching agent into the call.

### Call flow

```
   ┌──────────┐   incoming call    ┌─────────────────────────────────────────┐
   │  Caller  │ ─────────────────► │  Sinch Voice API v2                      │
   └──────────┘                    │                                          │
                                   │  answer → bridge("ivr-bridge")           │
                                   │        → dial VOICE_RELAY → bridge        │
                                   └───────────────┬──────────────────────────┘
                                                   │  wss:// (text protocol)
                                                   ▼
                                   ┌──────────────────────────────────────────┐
                                   │  Your relay server (this tutorial)        │
                                   │  1. greet the caller                      │
                                   │  2. classify each turn with an LLM        │
                                   │  3. once classified → PATCH the call:     │
                                   │       dial Sales/Support + bridge in      │
                                   │  4. close the socket (AI leaves)          │
                                   └───────────────┬──────────────────────────┘
                                                   │  PATCH /calls/{callId}
                                                   ▼
              ┌──────────┐  bridged   ┌─────────────────────────┐
              │  Caller  │ ◄────────► │  Sales / Support agent   │
              └──────────┘            └─────────────────────────┘
```

The bridge named `ivr-bridge` is the key. The caller leg and the relay leg are
both bridged into it on the way in. The PATCH dials the agent and bridges them
into **the same** named bridge, so when the relay socket closes, the caller and
the agent remain connected.

---

## Get the code

All the scripts for this tutorial live in the
[`sinch/sinch-voice-tutorials`](https://github.com/sinch/sinch-voice-tutorials)
repository, under `4.5-ai-ivr/`. Clone it and move into the tutorial folder:

```bash
git clone https://github.com/sinch/sinch-voice-tutorials.git
cd sinch-voice-tutorials/4.5-ai-ivr
```

### Repository layout

This tutorial is **self-contained**: its `.env`, `.env.example`, `system_prompt.md`,
and dependency manifests all live in the tutorial folder, and every script reads
them from there. Two paths are resolved by convention (both relative to `scripts/`):
`system_prompt.md` and `.env` sit one level up, at the tutorial folder root.

```
4.5-ai-ivr/                     this tutorial (self-contained)
├── description.md              this file
├── .env.example                template listing every variable
├── .env                        you create this (cp .env.example .env)
├── system_prompt.md            the intent-classifier prompt
├── requirements.txt            Python deps (websockets, requests)
├── package.json                Node dep (ws)
├── composer.json               PHP dep (cboden/ratchet)
└── scripts/
    ├── relay-server.py         relay server (Python)
    ├── relay-server.node.js    relay server (Node.js)
    ├── relay-server.php        relay server (PHP)
    ├── configure-service.sh    set the STATIC inbound behavior
    ├── test-callout.sh         simulate an inbound call
    └── patch-call.sh           patch a live call by hand
```

Run the shell commands below from the tutorial folder (`4.5-ai-ivr/`) unless a
step says otherwise.

---

## Quick start (minimal end-to-end first success)

This is the shortest path from nothing to "I called, said *sales*, and a phone
rang." Reference material (PATCH mechanics, prompt tuning, provider switching)
follows further down. There is a lot of setup here (service config, a `wss://`
tunnel, a relay server, and an LLM key), so do the steps **in order**; each one
depends on the previous.

```bash
# 0. From the tutorial folder (after cloning; see "Get the code")
cd sinch-voice-tutorials/4.5-ai-ivr
cp .env.example .env

# 1. Fill in .env in this folder (see the Setup table below) — at minimum:
#    PROJECT_ID, KEY_ID, KEY_SECRET, SERVICE_ID, SINCH_NUMBER,
#    SALES_NUMBER, SUPPORT_NUMBER, LLM_API_KEY (+ LLM_BASE_URL/LLM_MODEL)

# 2. Install one runtime's dependency
pip install -r requirements.txt        # Python:  websockets, requests
# or  npm install                       # Node:    ws
# or  composer install                  # PHP:     cboden/ratchet

# 3. Start the relay server (verifies your config locally before any call routes)
python scripts/relay-server.py          # logs the model + listening port
# or  node scripts/relay-server.node.js
# or  php scripts/relay-server.php

# 4. In a second terminal, expose it and capture the wss:// URL
ngrok http 8765
#    -> set WS_ENDPOINT=wss://<id>.ngrok-free.app in .env

# 5. Point the service's STATIC behavior at that URL
bash scripts/configure-service.sh       # reads WS_ENDPOINT from .env
#    (or: bash scripts/configure-service.sh wss://<id>.ngrok-free.app)

# 6. Trigger a call — dial your Sinch number, OR simulate it:
bash scripts/test-callout.sh            # calls DESTINATION_NUMBER, bridges relay
```

> **Why start the server (step 3) before configuring the service (step 5)?**
> Starting the relay server is the only *local* check you have: it loads `.env`,
> exits immediately with a clear `ERROR: <VAR> is not set` if anything is
> missing, and prints the LLM model it will use. Catch credential and dependency
> problems here, on your machine, before a real call is silently failing on the
> wire. The default port is `8765`; the `ngrok` command and the server must agree
> on it (set `PORT` in `.env` to change both; see the note in Step 4 of the
> detailed walkthrough).

### What success looks like

You dial the Sinch number (or answer the `test-callout.sh` call). You hear:

> "Hello, this is the call centre. How can I help you?"

You say *"I'd like to buy a house"*. After a short pause you hear:

> "Please wait, connecting you to Sales."

…and the `SALES_NUMBER` phone rings. When that agent answers they hear
*"Connecting you to a customer. Intent: Sales."* and are bridged to you; the AI
has dropped off the line. The relay server log shows:

```
[+] connected
  << {"command":"connect","callId":"01ARZ..."}
  >> {"command":"answer"}
  >> {"command":"text","text":"Hello, this is the call centre. How can I help you?","isLast":true}
  << {"command":"text","text":"I'd like to buy a house"}
  >> {"command":"text","text":"Please wait, connecting you to Sales.","isLast":true}
[*] patched Sales into call 01ARZ...
[-] session ended  callId=01ARZ...
```

Saying *"my heating is broken"* routes to `SUPPORT_NUMBER` instead. Saying
something ambiguous (*"I have a question"*) gets a spoken follow-up question
rather than a transfer.

---

## Setup

### Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project, API credentials,
  a virtual number, and a Voice **service**.
- A publicly reachable WebSocket endpoint. Use [ngrok](https://ngrok.com) in dev:
  ```bash
  ngrok http 8765    # exposes localhost:8765 as wss://<id>.ngrok-free.app
  ```
- One runtime for the relay server: **Python 3.10+** (with `pip`), **Node.js 18+**
  (global `fetch` is used, so 18+ is required), or **PHP 8.1+** (with the `curl`
  extension).
- An LLM API key. The classifier talks to any **OpenAI-compatible**
  `/chat/completions` endpoint, so it is model-agnostic; point it at OpenAI,
  at Anthropic's compatibility endpoint for Claude, or at a local gateway.

### Environment variables

The relay server, `configure-service.sh`, `patch-call.sh`, and `test-callout.sh`
all read this tutorial's own `.env`, which lives at the **tutorial folder root**
(`../.env` relative to `scripts/`). Copy the example and fill in the values:

```bash
cp .env.example .env
```

| Variable | Used for | Where to get it |
| --- | --- | --- |
| `PROJECT_ID`, `KEY_ID`, `KEY_SECRET` | Sinch auth (HTTP Basic) for the service PATCH and the live-call PATCH. | [Sinch dashboard](https://dashboard.sinch.com) → Access keys. |
| `SERVICE_ID` | The service whose call behavior you configure (Step 1). | `GET /v2/projects/{projectId}/services` or the dashboard. |
| `SINCH_NUMBER` | Caller-ID (`from`) used when dialing the agent and (for testing) the customer. | Your provisioned virtual number, E.164. |
| `WS_ENDPOINT` | Public `wss://` URL of your relay server (goes in the SVAML). | The `ngrok` forwarding URL (Step 3/4). |
| `SALES_NUMBER`, `SUPPORT_NUMBER` | The two human queues the call can be patched into. | Any reachable phones, E.164. |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | The OpenAI-compatible model that classifies intent. | See the provider note below. |
| `DESTINATION_NUMBER` | Only for `test-callout.sh`: your own phone, to simulate an inbound call. | Your phone, E.164. |
| `PORT` *(optional)* | Port the relay server listens on (default `8765`). | Must match the port you pass to `ngrok http`. |

> **Heads-up.** This tutorial ships its own `.env.example` (listing every
> variable above), so a fresh `cp .env.example .env` has all the keys. The relay
> server still fails fast with a clear message if a required key is missing;
> separately, make sure `WS_ENDPOINT` is **`wss://`** (Sinch requires TLS for
> Voice Relay), not a plain `ws://` URL.

> **Where do `sessionId` / `callName` come from for `patch-call.sh`?**
> You don't need them for the automatic flow: the relay server patches by
> `callId`, which it reads from the `connect` frame. `patch-call.sh` also takes a
> `callId` (its only positional argument besides the intent). If you want to use
> the session-keyed PATCH endpoint instead, both `sessionId` and the leg's
> `callName` are available: `sessionId` is returned by the outbound call
> (`test-callout.sh` prints the full call object) and appears in the relay
> `connect` metadata, and the `callName` of the inbound/caller leg is `caller`
> (set in the STATIC behavior). See *Patching by session + call name* below.

> **Choosing and configuring the LLM (provider switch).**
> The classifier is model-agnostic; only three variables change between providers.
> A fast, cheap model is the right call here: classification is a one-word answer
> and every round-trip is silence the caller hears.
>
> | Provider | `LLM_BASE_URL` | `LLM_MODEL` | `LLM_API_KEY` |
> | --- | --- | --- | --- |
> | OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | from platform.openai.com |
> | Claude (Anthropic) | `https://api.anthropic.com/v1` | `claude-haiku-4-5-20251001` | from console.anthropic.com |
> | Local gateway | `http://localhost:<port>/v1` | gateway-specific | gateway-specific |
>
> Anthropic exposes an OpenAI-compatible `/chat/completions` route, so pointing
> `LLM_BASE_URL` at it needs **no code changes**. Defaults if unset:
> `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_MODEL=gpt-4o-mini`
> (`LLM_API_KEY` is always required).

---

## Step-by-step instructions

### 1. Configure the inbound call behavior

When a call comes in, Sinch must answer it, bridge it, and dial the Voice
Relay leg. Because that SVAML is the same for every inbound call, the simplest
setup is a **STATIC** call behavior on the service. No webhook server is needed
for call setup (the relay WebSocket server is the only thing you run).

```bash
bash scripts/configure-service.sh
```

This PATCHes your service (`PATCH /v2/projects/{projectId}/services/{serviceId}`)
with the SVAML below (filled in from `.env`):

```jsonc
{
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
              "endpoint":    "wss://<your-ngrok-id>.ngrok-free.app",
              "ttsVoice":    "Tiffany",
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
}
```

> **Why `callName: "caller"`.** Naming the inbound leg lets the PATCH later hang
> it up cleanly (`{"command":"hangup","callName":"caller"}` when the agent ends
> the call). The relay leg is named `voice_relay_call` so the `onHangup` can tear
> it down if the caller drops first.

### 2. Start the relay server

Pick one implementation. Each listens on `PORT` (default `8765`) and speaks the
Voice Relay text protocol. Run from the **tutorial folder root**: the relay
servers locate `system_prompt.md` and `.env` at the tutorial folder root
(`../system_prompt.md` and `../.env` relative to `scripts/`).

```bash
# Python — pip install -r requirements.txt
python scripts/relay-server.py

# Node.js — npm install (installs ws)
node scripts/relay-server.node.js

# PHP — composer install (installs cboden/ratchet)
php scripts/relay-server.php
```

On startup it logs the LLM model in use and the listening port, e.g.
`[*] AI IVR relay  model=gpt-4o-mini  listening on ws://0.0.0.0:8765`. If a
required variable is missing it exits immediately with
`ERROR: <NAME> is not set in the environment / .env`.

### 3. Expose it and point the SVAML at it

```bash
ngrok http 8765      # use the same number as PORT
```

Copy the forwarding URL, set `WS_ENDPOINT=wss://<id>.ngrok-free.app` in `.env`,
and re-run `bash scripts/configure-service.sh` so the STATIC SVAML uses the new
URL. (You can also pass it as an argument:
`bash scripts/configure-service.sh wss://<id>.ngrok-free.app`.)

### 4. Call your Sinch number — or simulate it

Dial your Sinch number from any phone. You should hear the greeting, and after
you state your intent ("I'd like to buy a house" / "my heating is broken") the AI
says it's connecting you and the agent's phone rings.

No spare inbound number? Simulate the whole flow with an outbound self-callout
that dials *you* as the "caller" and bridges in the relay leg exactly as the
inbound behavior would (`POST /v2/projects/{projectId}/calls`):

```bash
bash scripts/test-callout.sh        # dials DESTINATION_NUMBER, bridges in the relay
```

This prints the created call object (including `sessionId` and `callId`) on
HTTP 201.

### 5. (Optional) Patch a call by hand

To understand the PATCH in isolation, separate from the LLM, grab a live
`callId` (from the relay server logs, or `GET /v2/projects/{projectId}/calls`)
and run:

```bash
bash scripts/patch-call.sh <callId> sales      # or: support
```

This is exactly the request the relay server sends automatically once it has
classified the intent. It expects HTTP **202 Accepted** and exits non-zero on
anything else.

---

## How it works

### The Voice Relay text protocol

Once Sinch dials the relay leg it opens a WebSocket to your server and exchanges
JSON text frames (raw audio never reaches you):

| Direction | Command | Meaning |
| --- | --- | --- |
| Sinch → Server | `connect` | Session start; carries `callId` (the relay leg) and metadata. |
| Server → Sinch | `answer` | Accept the relay session. |
| Server → Sinch | `text` + `isLast:true` | Text for Sinch to speak (TTS) to the caller. |
| Sinch → Server | `text` / `prompt` | The caller's transcribed speech (STT). |
| Sinch → Server | `interrupt`, `dtmf`, `textPlayback*` | Barge-in, keypad, and playback lifecycle (logged, not needed here). |

> The Voice Relay on-the-wire text protocol is **not** part of the OpenAPI spec;
> it is documented separately as part of the Voice Relay product surface. The
> field names above (`connect`/`callId`, `text`/`prompt`, `isLast`) are what the
> example servers send and expect; verify them against the current Voice Relay
> protocol docs before going to production.

### The classify-then-patch loop

1. On `connect`, capture `callId`, send `answer`, then greet the caller with a
   `text` frame.
2. On each `text`/`prompt`, send the caller's words to the LLM with the
   classification prompt from `system_prompt.md`.
3. The model replies with a single word (`Sales`/`Support`) when it is confident,
   or a short sentence asking the caller to clarify. The server uses a simple
   rule: **a one-word reply that matches a known intent is a routing decision;
   anything else is spoken back** to the caller as a follow-up question.
4. On a routing decision, the server speaks "Please wait, connecting you to
   Sales/Support", waits briefly (~2.5 s) so the TTS is heard, then PATCHes the
   call:

   ```jsonc
   PATCH /v2/projects/{projectId}/calls/{callId}
   {
     "commands": [
       {
         "command": "dial",
         "callName": "agent_call",
         "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
         "to":   { "type": "PHONE", "phone": { "number": "<SALES_or_SUPPORT>" } },
         "dialTimeoutDurationSeconds": 20,
         "maxCallDurationSeconds": 3600,
         "events": {
           "onAnswer": [
             { "command": "bridgeCall", "bridgeName": "ivr-bridge" },
             { "command": "messages", "messagesName": "agent-intro",
               "messages": [ { "type": "SAY",
                 "say": { "format": "TEXT",
                          "text": "Connecting you to a customer. Intent: Sales.",
                          "voiceName": "Tiffany" } } ] }
           ],
           "onHangup": [ { "command": "hangup", "callName": "caller" } ]
         }
       }
     ]
   }
   ```

   The request body is a `callPatchRequest` (`{ "commands": [...] }`) and the API
   returns **202 Accepted**. The `dial` command's fields (`callName`, `from`,
   `to`, `dialTimeoutDurationSeconds`, `maxCallDurationSeconds`, `events`), the
   `bridgeCall.bridgeName`, and the `messages`/`SAY` shape all match the spec
   exactly. An optional `Idempotency-Key` header is sent (see below).
5. The server closes the WebSocket. The relay leg leaves `ivr-bridge`; the caller
   and the freshly-dialed agent stay bridged.

> **Which `callId` do you patch?** The `callId` from the `connect` frame is the
> relay leg. Patching it adds the new `dial` to the *same session*, and
> `bridgeCall` with the existing `bridgeName` drops the agent into the bridge the
> caller is already in.

### Patching by session + call name

The spec offers an equivalent endpoint keyed by session and call name:

```
PATCH /v2/projects/{projectId}/sessions/{sessionId}/calls/{callName}
```

It takes the same `callPatchRequest` body and returns 202. Use it when you have
the `sessionId` (from the call object or the relay metadata) and a stable leg
name rather than a `callId`; for example, to target the inbound `caller` leg
by name. The example servers and `patch-call.sh` use the `callId` form because
the `callId` arrives directly in the `connect` frame.

---

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Latency budget** | Every classifier round-trip is silence on the line. Use a fast, cheap model and `temperature: 0` (the examples set both). Keep the system prompt short. |
| **One patch per call** | The examples guard with a per-connection `patched` flag so a second transcribed turn can't dial a second agent. (The PHP server sets the flag *before* the timer fires, closing a small race the others leave open by closing the socket synchronously.) |
| **Classifier errors / timeouts** | The examples wrap the LLM call in try/catch with a 10 s timeout; on failure they speak "Sorry, please try again." and keep the line open rather than crashing or hanging up. |
| **Ambiguous intent** | A reply that isn't a known one-word route is spoken back verbatim as a clarifying question, so the caller can refine, with no silent mis-route. |
| **Agent doesn't answer** | The example dials with `dialTimeoutDurationSeconds: 20`. Add an `onTimeout` branch on the `dial` to fall back to voicemail or another queue (see [2.2 Call Forwarding](../2.2-call-forwarding/description.md)). The example does **not** yet handle this; add it before production. |
| **Idempotency** | The PATCH endpoint accepts an `Idempotency-Key` header; the examples send `${callId}-${intent}` so a retried PATCH can't create two agent legs. |
| **Classifier guardrails** | LLM output is parsed with a strict "one word that matches a known intent = route" rule and an allow-list (`{sales, support}`). Never feed model text straight into a phone-number lookup. |
| **Secrets** | The relay server holds your Sinch *and* LLM credentials. Load them from the environment (the examples read `../.env`); never hard-code keys. |
| **Per-DID routing** | STATIC applies the same SVAML to every inbound call. For different agents per inbound number, use a WEBHOOK service that returns the same `commands` (plus `callName`/`events`) per request (see [2.1 Inbound PSTN](../2.1-inbound-pstn/description.md)). |

---

## Real-life examples

- **Smart call routing**: replace a multi-level DTMF phone tree with one AI that
  routes on intent ("I want to book a viewing" → Sales).
- **Tier-0 triage**: the AI handles FAQs and only patches in a human when it
  decides the caller needs one.
- **Overflow / after-hours**: the AI qualifies the caller, then patches in
  whichever queue is staffed.
- **Warm transfer with context**: the PATCH plays an intro message to the agent
  ("Connecting a customer interested in buying") before bridging the caller.

## What the OpenAPI spec says at a glance

- `PATCH /v2/projects/{projectId}/calls/{callId}` takes a `callPatchRequest`
  (`{ "commands": [...] }`) and returns **202 Accepted**. It accepts an optional
  `Idempotency-Key` header. *(Verified.)*
- `PATCH /v2/projects/{projectId}/sessions/{sessionId}/calls/{callName}` is the
  equivalent keyed by session + call name; same body, same 202. *(Verified.)*
- An inbound call is configured by setting the service's `callBehavior`. A
  **STATIC** behavior is `{ "type": "STATIC", "static": { "commands": [...],
  "callName"?, "events"?: { "onHangup": [...] } } }`; there is no `accept`
  command. *(Verified.)*
- `voiceRelay` (a `to` discriminator value, `type: VOICE_RELAY`) requires
  `endpoint`, `ttsVoice`, and `sttLanguage`; `enableInterruptions` defaults to
  `true`. *(Verified.)*
- `dial` requires `command` + `to`; `callName`, `from`,
  `dialTimeoutDurationSeconds`, `maxCallDurationSeconds`, and `events`
  (`onAnswer`/`onTimeout`/`onHangup`) are all valid. *(Verified.)*
- `bridgeCall` adds the current leg to a named bridge; bridging multiple legs
  into the same `bridgeName` is what connects the parties. *(Verified.)*
- `messages` carries a `messagesName` and a list of `SAY`/`PLAY` items; `SAY`
  requires `say.text` and `say.voiceName`, with `say.format` of `TEXT` (default)
  or `SSML`. *(Verified.)*
- The Voice Relay on-the-wire text protocol is **not** part of the OpenAPI spec;
  it is documented separately as part of the Voice Relay product surface.