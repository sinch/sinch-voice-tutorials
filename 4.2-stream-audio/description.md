# Stream Call Audio in Real-Time

## Overview

The Sinch Voice API v2 can stream live PCM audio from a phone call bidirectionally to a WebSocket server. This unlocks feeding raw audio into AI models, speech-to-text engines, sentiment analysis pipelines, or custom voice bots, and it lets you send synthesized audio back to the caller over the same socket.

When a call leg is routed to a `STREAM` destination, Sinch opens a WebSocket connection to your `endpoint` and exchanges audio as binary frames. To get a working echo loop you only need three things running, in this order:

1. A WebSocket echo server (reads binary PCM, writes it straight back).
2. ngrok exposing that server as a public `wss://` URL.
3. An API call whose SVAML dials a `STREAM` leg pointed at that URL, bridged with a phone leg.

The rest of this document is reference: the PCM/`streamOptions` contract, the inbound (ICE webhook) path, the on-the-wire message protocol, and the other language servers.

> **When to use STREAM vs. Voice Relay.** Use `STREAM` when you want the *raw audio*: you run your own STT/TTS, or you forward the PCM to a third-party agent. If you'd rather have Sinch do the speech-to-text and text-to-speech for you and just exchange **text** turns, use `VOICE_RELAY` instead. See [4.1 Connect an AI Chatbot (Voice Relay)](../4.1-voice-relay/description.md). If you want a fully external agent SDK (e.g. ElevenLabs Conversational AI) on the far end of the stream, see [4.3 ElevenLabs Bridge](../4.3-elevenlabs-bridge/description.md). For a deeper walkthrough of the server side itself, see [4.4 WebSocket Server](../4.4-websocket-server/description.md).

---

## Setup (do this once)

### Get the code

All scripts for this tutorial live in the [`sinch/sinch-voice-tutorials`](https://github.com/sinch/sinch-voice-tutorials) repository. Clone it and move into this tutorial's folder:

```bash
git clone https://github.com/sinch/sinch-voice-tutorials.git
cd sinch-voice-tutorials/4.2-stream-audio
```

The layout you'll be working with:

```
sinch-voice-tutorials/
├── .env                       # shared credentials (repository / tutorials root)
├── 4.2-stream-audio/
│   ├── description.md          # this document
│   └── scripts/
│       ├── ws-server.py
│       ├── ws-server.node.js
│       ├── ws-server.php
│       ├── WsServer.java
│       ├── ice-callback.py
│       ├── ice-callback.node.js
│       ├── trigger-call.sh
│       └── trigger-call.js
└── ...                         # sibling tutorials (4.1, 4.3, 4.4)
```

Every command below assumes your working directory is `sinch-voice-tutorials/4.2-stream-audio`, so the `scripts/...` paths resolve. The scripts read the shared `.env` two levels up at the repository root (`../../.env`).

### Credentials and `.env`

All scripts read the shared `.env` at the repository root (`sinch-voice-tutorials/.env`). Auth is HTTP Basic (`KEY_ID:KEY_SECRET`). Create the file at the repo root (copy `.env.example` if the repo ships one) and fill in:

```bash
PROJECT_ID=...            # Sinch project
KEY_ID=...                # API key id  (Basic auth username)
KEY_SECRET=...            # API key secret (Basic auth password)
SINCH_NUMBER=+1...        # your Sinch virtual number (E.164)
DESTINATION_NUMBER=+1...  # the phone that will ring (E.164)
WS_ENDPOINT=wss://...     # public WebSocket URL from ngrok (see below); must be wss:// or ws://
PORT=...                  # port for the ICE webhook server (inbound path only; optional)
```

`WS_ENDPOINT` **must** be a WebSocket URL (`wss://` recommended, `ws://` allowed) and reachable from the public internet. It is *not* an `https://` URL. Convert your ngrok forwarding URL (see step 2 below).

### What about `ice-callback`?

`ice-callback.{node.js,py}` is **only needed for the inbound path**: when a caller dials *your* Sinch number and you want Sinch to route that call into your WebSocket server. It is an HTTP webhook server that handles the `call.incoming` event and replies with SVAML that bridges the inbound PSTN leg to a `STREAM` leg.

**For the first-success path below you do NOT need `ice-callback`.** The outbound trigger (`trigger-call.{sh,js}`) embeds the SVAML inline and calls the API directly. Skip ahead to "Inbound calls" only when you want callers to reach your stream.

### Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with API credentials and a Sinch virtual number.
- The [`sinch/sinch-voice-tutorials`](https://github.com/sinch/sinch-voice-tutorials) repository cloned (see "Get the code" above).
- [ngrok](https://ngrok.com) (or any public tunnel) for development.
- One server runtime: Node.js 18+ (`ws`), Python 3.8+ (`websockets`), PHP 8+ (Ratchet), or Java 11+ (Tyrus).

---

## First success: hear your own voice echoed back

This is the shortest loop that proves the stream works end to end. The Python server below echoes every binary PCM frame straight back, so when the call connects you should hear yourself.

### 1. Start the echo WebSocket server

```bash
pip install websockets
python scripts/ws-server.py
```

It listens on port `8765` (override with `WS_PORT`). The Python server in this tutorial already echoes audio back (`await websocket.send(message)`), so it doubles as an echo demo. The Node, PHP, and Java servers in `scripts/` log/record audio but do **not** echo by default. See "Sending audio back" for the one-line change.

### 2. Expose it with ngrok

```bash
ngrok http 8765
```

Copy the Forwarding URL and convert the scheme to a WebSocket URL:

- `https://abc123.ngrok-free.app` becomes `wss://abc123.ngrok-free.app`

Set it in `.env` (or export it):

```bash
export WS_ENDPOINT=wss://abc123.ngrok-free.app
```

### 3. Trigger the call

```bash
bash scripts/trigger-call.sh
```

This dials `DESTINATION_NUMBER` from `SINCH_NUMBER`; when the phone answers it bridges the phone leg with a `STREAM` leg pointed at `WS_ENDPOINT`. Answer the phone and speak, and you should hear your own voice echoed back, while the server console prints frame/byte counts.

> **Order matters.** The server and ngrok must be running *before* you trigger the call. If `WS_ENDPOINT` points at a dead tunnel, the `STREAM` leg fails to connect and `onHangup` tears the call down, so you'll hear nothing.

(There is also `scripts/trigger-call.js`, the same payload in browser/Node `fetch` form. Note: calling the Sinch API directly from a browser hits CORS, so proxy it through a backend in production.)

### What success looks like

- **Server console:** `New WebSocket connection ...`, then `ConnectRequest — callId: ... appId: ...`, then `Sent ConnectResponse: answer`, then periodic `Audio frames: 100 | Bytes: ...`.
- **Your phone:** you hear your own voice echoed back (Python server) or silence (the other servers, which only record).
- **API call:** `trigger-call.sh` prints `Call created successfully (HTTP 201)`.
- **On disk:** a `call-<timestamp>.pcm` file grows. Play it back to confirm encoding (see "PCM format" below).

---

## The SVAML: how the legs bridge

The outbound trigger sends this shape. Two `bridgeCall` commands (same `bridgeName`) connect the phone leg and the stream leg so audio flows both ways. This mirrors the spec's own `dialToStream` / echo examples.

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "phone-leg",
      "from": { "type": "PHONE", "phone": { "number": "+1SINCH_NUMBER" } },
      "to":   { "type": "PHONE", "phone": { "number": "+1DESTINATION" } },
      "dialTimeoutDurationSeconds": 30,
      "maxCallDurationSeconds": 1800,
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "stream-bridge" },
          {
            "command": "dial",
            "callName": "stream-leg",
            "to": {
              "type": "STREAM",
              "stream": {
                "endpoint": "wss://abc123.ngrok-free.app",
                "streamOptions": {
                  "version":    1,
                  "codec":      "PCM",
                  "sampleRate": 8000
                },
                "callHeaders": [
                  { "key": "X-Tutorial", "value": "sinch-ws-agent" }
                ]
              }
            },
            "dialTimeoutDurationSeconds": 10,
            "events": {
              "onAnswer": [{ "command": "bridgeCall", "bridgeName": "stream-bridge" }],
              "onHangup": [{ "command": "hangup", "callName": "phone-leg" }]
            }
          }
        ],
        "onHangup": [{ "command": "hangup", "callName": "stream-leg" }]
      }
    }
  ]
}
```

Use `callHeaders` (max 16 pairs, key/value up to 255 chars each) to pass identifying metadata your server can read on connect.

---

## The on-the-wire WebSocket protocol

> **Heads up: not in the OpenAPI spec.** The spec defines the *SVAML* shape (`endpoint`, `streamOptions`, `callHeaders`) but does **not** document the messages exchanged over the WebSocket itself (`ConnectRequest`, the `answer` reply, `heartbeat`/`StreamControl`). The protocol below reflects the Streams product behavior the example servers implement; treat the exact JSON field names as **unverified against the spec** and confirm them against the current Sinch Streams documentation before relying on them in production.

| Direction | Format | Description |
| --- | --- | --- |
| Sinch to Server | JSON (text) | `ConnectRequest`: `{"command":"connect","callId":"…","applicationId":"…","headers":{…}}` |
| Server to Sinch | JSON (text) | `ConnectResponse`: `{"command":"answer"}` (accept). |
| Sinch and Server | Binary | Raw PCM audio frames (codec `PCM`, negotiated `sampleRate`). |
| Server to Sinch | JSON (text) | Control messages such as `{"command":"heartbeat"}` during silence. |

The example servers all follow the same lifecycle: on the text `connect` message they record `callId`/`applicationId`/`headers`, reply `{"command":"answer"}`, then treat every binary frame as PCM audio and (optionally) write PCM back.

---

## PCM format

- **Codec:** `PCM` only (the spec fixes `codec` to the constant `PCM`). If you need Opus or G.711-µ, transcode to PCM on your own gateway before the WebSocket hop.
- **Sample rate:** one of `8000 | 16000 | 24000 | 44100 | 48000 | 96000` Hz; default `8000`. For PSTN calls audio is typically sampled at 8 kHz, so a higher rate does not improve perceived quality on a PSTN-only path; it just increases bandwidth and processing load. Higher rates help on non-PSTN (SIP/streaming) paths or when a downstream STT model prefers wideband.
- **Sample encoding / framing:** The spec says "uncompressed raw audio" but does **not** state the bit depth, endianness, or channel count of each frame. The example servers treat frames as opaque bytes (write to file, echo back), which works regardless. **Before decoding the PCM yourself, confirm the format.** It is almost certainly **16-bit signed little-endian, mono**, but this is *not stated in the OpenAPI spec*. To verify, play a recorded `call-*.pcm` with the assumed parameters, e.g.:
  ```bash
  ffplay -f s16le -ar 8000 -ac 1 call-<timestamp>.pcm
  ```
  Adjust `-ar` to match the `sampleRate` you negotiated. If it sounds correct, your assumptions hold.

Audio you send **back** must match the negotiated `codec` and `sampleRate`, in the same frame encoding.

---

## Sending audio back

Write raw PCM binary frames to the same connection. The Python server already does this (echo); to turn the other servers into echo servers, send the received binary frame straight back:

- **Node.js** (`scripts/ws-server.node.js`, in the binary branch): `ws.send(data);`
- **PHP** (`scripts/ws-server.php`, in the binary branch): `$from->send($msg);`
- **Java** (`scripts/WsServer.java`, in `onBinaryMessage`): `session.getBasicRemote().sendBinary(ByteBuffer.wrap(bytes));`

In a real bot you'd replace the echo with: STT, then LLM, then TTS, then send the synthesized PCM back. Each server marks the spot with a `--- HERE: plug in your AI / STT processing ---` comment.

---

## Inbound calls (the ICE webhook path)

To route calls that come *into* your Sinch number to the stream, run the ICE webhook server instead of the outbound trigger.

```bash
# Node.js
npm install express
node scripts/ice-callback.node.js     # listens on PORT (default 3001)

# Python
pip install flask python-dotenv
python scripts/ice-callback.py        # listens on PORT (default 8081)
```

> **Note:** the two ice-callback scripts have *different* built-in default ports (Node 3001, Python 8081). If `PORT` is set in `.env`, it overrides both. Pick one runtime and expose its port with a second ngrok tunnel; set your Sinch service webhook URL to `https://<that-ngrok>.ngrok-free.app/webhook`.

On `call.incoming`, the server answers the inbound leg, bridges it, dials a `STREAM` leg to `WS_ENDPOINT`, and bridges that into the same `stream-bridge`. When either side hangs up, the other is torn down.

> **Couldn't verify: inbound event shape.** The scripts read the caller number from `body.call.from.phone.number`. The spec's prose webhook example (`call.answered`) shows a *flat* shape (`"from": "+1234567890"`), and the `call.incoming` payload is not formally schematized in the OpenAPI file. Log the raw request body once and confirm the actual nesting for your account before depending on `call.from.phone.number`.

---

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Authenticate inbound WS** | The `endpoint` is open by default. Embed a token query param (`?token=…`) or pass it via `callHeaders`, then validate on `ConnectRequest`. |
| **Heartbeat / keepalive** | The example servers send `{"command":"heartbeat"}` every 5 s; tune to keep proxies alive during long silences. |
| **Backpressure** | If you can't process incoming audio fast enough, **drop** frames rather than buffer indefinitely. Buffering inflates latency. |
| **Disconnect handling** | When the caller hangs up, Sinch closes the WS. Handle the close (free STT/TTS sessions, flush PCM files). All four servers do this in their close handler. |
| **Partial / non-JSON frames** | Each server tolerates a non-JSON text frame and treats anything binary as audio; verify your STT layer is robust to short final frames. |
| **Logging & PCAP** | Capture the JSON control frames and a sample of binary frames during dev; most bugs are "which side stopped sending audio first." |
| **Codec** | Only `PCM` is supported. Terminate other codecs on your gateway and re-encode to PCM before the WS hop. |

---

## Language coverage

All files live under [`4.2-stream-audio/scripts/`](https://github.com/sinch/sinch-voice-tutorials/tree/main/4.2-stream-audio/scripts) in the repository.

| File | Runtime | Echoes by default? |
| --- | --- | --- |
| [`ws-server.py`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/ws-server.py) | Python (`websockets`) | **Yes** (use this for the first-success demo) |
| [`ws-server.node.js`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/ws-server.node.js) | Node.js (`ws`) | No (records + heartbeats) |
| [`ws-server.php`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/ws-server.php) | PHP (Ratchet) | No (records) |
| [`WsServer.java`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/WsServer.java) | Java (Tyrus) | No (records + heartbeats) |
| [`ice-callback.node.js`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/ice-callback.node.js) | Node/Express | Inbound webhook |
| [`ice-callback.py`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/ice-callback.py) | Python/Flask | Inbound webhook |
| [`trigger-call.sh`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/trigger-call.sh) | bash + curl | Outbound trigger |
| [`trigger-call.js`](https://github.com/sinch/sinch-voice-tutorials/blob/main/4.2-stream-audio/scripts/trigger-call.js) | browser/Node fetch | Outbound trigger |

---

## Some specification details

- `STREAM` is one of `to`'s three discriminator values (`PHONE`, `STREAM`, `VOICE_RELAY`).
- `stream.endpoint` is **required**; it must be a valid `ws://` or `wss://` URL reachable from the public internet.
- `stream.streamOptions.codec` is the constant `PCM`.
- `stream.streamOptions.sampleRate` is one of `{8000, 16000, 24000, 44100, 48000, 96000}`, default `8000`.
- `stream.streamOptions.version` defaults to `1`.
- `stream.callHeaders[]` allows up to 16 `{key, value}` pairs, each field up to 255 chars.
- The **WebSocket wire protocol** (`ConnectRequest`, `answer`, `heartbeat`) and the **PCM sample encoding** (bit depth/endianness/channels) are **not** in the OpenAPI spec; verify them against the Sinch Streams product docs.