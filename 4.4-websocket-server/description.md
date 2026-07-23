# WebSocket Server

## Overview

A WebSocket server is the runtime piece on *your* side that the Sinch Voice API talks to whenever a call leg is routed to a `STREAM` (raw PCM audio) or `VOICE_RELAY` (text-in/text-out) destination. The other tutorials in this section focus on the *Sinch* side: the SVAML payload that points a call at your server. This tutorial is the server-side reference: what messages you must handle, in what order, how to reply with audio or text, and how to ship the thing to production.

The fastest way to understand it is to run an echo server and connect a tiny WebSocket client to it locally. No phone call, no ngrok, and no Sinch account required. You see the exact frames a real call would send, echoed straight back. Start there (below), then read the protocol reference and the production checklist.

There are two distinct WebSocket protocols, picked by `to.type` in your SVAML:

- **`STREAM`**: raw PCM audio frames interleaved with JSON control messages. Pairs with [4.2 Stream Call Audio in Real-Time](../4.2-stream-audio/description.md).
- **`VOICE_RELAY`**: text-only protocol; Sinch does STT and TTS for you. Pairs with [4.1 Connect an AI Chatbot (Voice Relay)](../4.1-voice-relay/description.md).

This tutorial ships minimal echo servers for both, in Node.js and Python.

## Get the code

All sample code lives in the [`sinch/sinch-voice-tutorials`](https://github.com/sinch/sinch-voice-tutorials) repository. Clone it and change into this tutorial's folder:

```bash
git clone https://github.com/sinch/sinch-voice-tutorials.git
cd sinch-voice-tutorials/4.4-websocket-server
```

The scripts for this tutorial are under `scripts/`. Every relative link in this page (`../4.1-voice-relay/`, `../4.2-stream-audio/`, and so on) resolves against the same repo when you browse it on GitHub or on your own clone, so you can follow the cross-references without leaving the tree.

## Setup

You need **one** of these runtimes:

| Runtime | Install the WebSocket library |
| --- | --- |
| Node.js 18+ | `npm install ws` (the scripts use ES modules; add `"type": "module"` to `package.json`) |
| Python 3.8+ | `pip install websockets` |

For the local first-success test below, that is all you need. To drive a server from a **real call** you additionally need:

- A [Sinch account](https://dashboard.sinch.com) with API credentials and a virtual number (see [1.1 Outbound Call](../1.1-outbound-call/description.md) or [2.1 Inbound PSTN](../2.1-inbound-pstn/description.md)).
- A publicly reachable `wss://` endpoint. [ngrok](https://ngrok.com) gives you one for free: `ngrok http 8765`.

The scripts default to **port 8765** (override with the `PORT` environment variable). Note: the shared `.env` at the repository root sets `PORT=8081` for other tutorials, so either unset it for this one or pass `PORT=8765` explicitly so the port matches the `ngrok http 8765` commands below.

## First success: see frames echoed, no call required (start here)

You can validate the entire WebSocket contract on your laptop before touching Sinch. Run an echo server, point a local client at it, and watch the frames come back.

### 1. Start the STREAM echo server

```bash
# Python
pip install websockets
python scripts/ws-stream-server.py        # listens on ws://localhost:8765

# ...or Node.js
npm install ws
node scripts/ws-stream-server.node.js
```

You should see `STREAM echo server on :8765`.

### 2. Connect a local client and send a fake call

Save this as `test-stream.py` and run it in a second terminal (`pip install websockets` if you haven't):

```python
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://localhost:8765") as ws:
        # Pretend to be Sinch opening the call:
        await ws.send(json.dumps({"command": "connect", "callId": "test-1", "applicationId": "app-1"}))
        print("server replied:", await ws.recv())     # expect {"command":"answer"}
        # Pretend to be the caller's audio (4 bytes of fake PCM):
        await ws.send(b"\x01\x02\x03\x04")
        echo = await ws.recv()
        print("audio echoed back:", echo)              # expect b'\x01\x02\x03\x04'

asyncio.run(main())
```

```
server replied: {"command": "answer"}
audio echoed back: b'\x01\x02\x03\x04'
```

That is the complete STREAM handshake: you sent `connect`, the server answered, you sent a binary PCM frame, and it came straight back. On a real call those binary frames are the caller's voice and the echo is what the caller hears.

### 3. (Optional) Do the same for VOICE_RELAY

```bash
python scripts/ws-relay-server.py          # or: node scripts/ws-relay-server.node.js
```

```python
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://localhost:8765") as ws:
        await ws.send(json.dumps({"command": "connect", "callId": "test-1"}))
        print(await ws.recv())   # {"command":"answer"}
        print(await ws.recv())   # greeting text
        await ws.send(json.dumps({"command": "text", "text": "hello world"}))
        print(await ws.recv())   # {"command":"text","text":"You said: hello world","isLast":true}

asyncio.run(main())
```

Once both pass, the plumbing is proven correct for these echo cases. Everything after this is wiring the same server up to a live call and replacing the echo with real STT/LLM/TTS.

### 4. Go live with a real call

1. Expose the running server: `ngrok http 8765`, then copy the `wss://<id>.ngrok-free.app` Forwarding URL.
2. Put that URL in the `endpoint` of a `STREAM` or `VOICE_RELAY` destination. See [4.2](../4.2-stream-audio/description.md) (STREAM, outbound trigger) or [4.1](../4.1-voice-relay/description.md) (VOICE_RELAY, inbound via dashboard).
3. Place the call. A STREAM server will echo your voice back to you; a VOICE_RELAY server will read back whatever you say.

> The shared `.env` field `WS_ENDPOINT` holds the `wss://` URL used by the call-trigger scripts in 4.1/4.2. Update it to your current ngrok URL each session (ngrok URLs change on restart unless you have a reserved domain).

## Real-life examples

- **Custom STT/TTS pipeline**: You run your own ASR (for example Whisper) and TTS (for example Coqui). Use `STREAM` so Sinch never touches the audio's meaning.
- **Embedded LLM with off-the-shelf voice**: You do not want to host ASR/TTS. Use `VOICE_RELAY` and keep your server in pure text.
- **Hybrid agent**: Most turns go through `VOICE_RELAY`; rare "play this exact recording" turns hand off via a separate SVAML branch.
- **Auditing or wiretap**: Stream a copy of the audio to an auditing service alongside the live conversation (set up two `STREAM` legs on one call).

## The STREAM protocol: PCM in, PCM out

When Sinch dials `to: { type: "STREAM", stream: { endpoint: "wss://..." } }`, it opens a WebSocket to your `endpoint` and exchanges these messages:

| Direction | Format | Message | When |
| --- | --- | --- | --- |
| Sinch to server | JSON (text) | `ConnectRequest`: `{"command":"connect","callId":"...","applicationId":"...","headers":{…}}` | Once, immediately after the WS handshake. |
| Server to Sinch | JSON (text) | `ConnectResponse`: `{"command":"answer"}` (or `"busy"` / `"reject"`) | Server's reply that opens the audio path. |
| Sinch and server | Binary | Raw PCM audio frames | Continuous bidirectional flow until the WS closes. |
| Server to Sinch | JSON (text) | `StreamControl`: `{"command":"clear"}` | Cancel any audio Sinch had queued; used for barge-in. |
| Server to Sinch | JSON (text) | `StreamControl`: `{"command":"heartbeat"}` | Optional; keeps idle connections alive. |

The audio is **linear PCM**, codec fixed to `PCM`, at the sample rate negotiated in `streamOptions.sampleRate` (one of `8000 / 16000 / 24000 / 44100 / 48000 / 96000` Hz; default `8000`). Frame size is implementation-defined: write whatever PCM bytes you have, when you have them.

> **Verify:** the field and command names above (`connect`, `answer`, `busy`, `reject`, `clear`, `heartbeat`, `headers`, `callId`, `applicationId`) come from the 4.2 tutorial and the working sample servers, not from the OpenAPI spec. The spec defines only the SVAML side (`endpoint`, `streamOptions.codec`, `streamOptions.sampleRate`, `streamOptions.version`, `callHeaders[]`). The on-the-wire JSON protocol is documented in the Streams product docs. Confirm exact names there before relying on `busy` / `reject` / `clear`.

### Minimal STREAM server (Node.js)

[`scripts/ws-stream-server.node.js`](scripts/ws-stream-server.node.js), requires `npm install ws`:

```js
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT || 8765);
const wss = new WebSocketServer({ port: PORT });
console.log(`STREAM echo server on :${PORT}`);

wss.on("connection", (ws, req) => {
  console.log(`new connection from ${req.socket.remoteAddress}`);

  // Keepalive so corporate proxies don't drop an idle connection.
  const heartbeat = setInterval(() => {
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ command: "heartbeat" }));
  }, 30_000);

  ws.on("message", (data, isBinary) => {
    if (!isBinary) {
      let msg;
      try { msg = JSON.parse(data.toString()); } catch { return; }  // ignore malformed JSON
      console.log("text frame", msg);
      if (msg.command === "connect") ws.send(JSON.stringify({ command: "answer" }));
      return;
    }
    // Binary frame == raw PCM from the caller. Echo it back.
    ws.send(data, { binary: true });
  });

  ws.on("close", () => { clearInterval(heartbeat); console.log("connection closed"); });
});
```

### Minimal STREAM server (Python)

[`scripts/ws-stream-server.py`](scripts/ws-stream-server.py), requires `pip install websockets`:

```python
import asyncio, json, os
import websockets

PORT = int(os.environ.get("PORT", "8765"))

async def heartbeat(ws):
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send(json.dumps({"command": "heartbeat"}))
    except websockets.exceptions.ConnectionClosed:
        return

async def handler(ws):
    print(f"new connection from {ws.remote_address}")
    hb = asyncio.create_task(heartbeat(ws))
    try:
        async for msg in ws:
            if isinstance(msg, (bytes, bytearray)):
                await ws.send(bytes(msg))   # echo PCM
                continue
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                continue                    # ignore malformed JSON
            print("text frame", payload)
            if payload.get("command") == "connect":
                await ws.send(json.dumps({"command": "answer"}))
    finally:
        hb.cancel()
        print("connection closed")

async def main():
    async with websockets.serve(handler, "0.0.0.0", PORT):
        print(f"STREAM echo server on :{PORT}")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
```

Both servers handle the connection lifecycle (heartbeat cancelled on close), ignore malformed JSON instead of crashing, and never busy-loop.

## The VOICE_RELAY protocol: text in, text out

When `to.type` is `VOICE_RELAY`, Sinch does STT and TTS on its end. Your server only ever sees and sends text:

| Direction | Command | When |
| --- | --- | --- |
| Sinch to server | `connect` | Session start; carries `callId`, metadata, and any `callHeaders` from the SVAML. |
| Server to Sinch | `answer` | Accept the relay session. |
| Server to Sinch | `text` (+ `isLast`, optional `isInterruptible`) | TTS text to read to the caller. Send `isLast: true` on the final chunk of a turn. |
| Sinch to server | `text` / `prompt` | Transcribed speech from the caller. |
| Sinch to server | `interrupt` | Caller spoke during TTS playback (barge-in). |
| Sinch to server | `dtmf` | DTMF digits pressed by the caller. |
| Sinch to server | `textPlaybackStart` / `textPlaybackStop` / `textPlaybackCancel` | TTS playback lifecycle. |

> **Verify:** as with STREAM, these command names are not in the OpenAPI spec. The spec defines only the SVAML `voiceRelay` object (`endpoint`, `ttsVoice`, `sttLanguage`, `enableInterruptions`, `callHeaders[]`). The JSON message shapes come from the Voice Relay product docs (an AsyncAPI definition) and the working reference server. The full reference implementation in [4.1 Voice Relay](../4.1-voice-relay/description.md) (`../4.1-voice-relay/server.py`) handles every command above.

### Minimal VOICE_RELAY server (Node.js)

[`scripts/ws-relay-server.node.js`](scripts/ws-relay-server.node.js), requires `npm install ws`:

```js
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT || 8765);
const wss = new WebSocketServer({ port: PORT });
console.log(`VOICE_RELAY echo server on :${PORT}`);

wss.on("connection", (ws) => {
  ws.on("message", (data) => {
    let msg;
    try { msg = JSON.parse(data.toString()); } catch { return; }
    console.log("rx", msg);

    if (msg.command === "connect") {
      ws.send(JSON.stringify({ command: "answer" }));                                   // accept
      ws.send(JSON.stringify({ command: "text", text: "Hi! Anything you say I will repeat back.", isLast: true }));
      return;
    }
    // Sinch delivers transcribed user speech as `text` (or `prompt`).
    if ((msg.command === "text" || msg.command === "prompt") && msg.text) {
      ws.send(JSON.stringify({ command: "text", text: `You said: ${msg.text}`, isLast: true }));
    }
  });

  ws.on("close", () => console.log("connection closed"));
});
```

### Minimal VOICE_RELAY server (Python)

[`scripts/ws-relay-server.py`](scripts/ws-relay-server.py), requires `pip install websockets`:

```python
import asyncio, json, os
import websockets

PORT = int(os.environ.get("PORT", "8765"))

async def handler(ws):
    print("new connection")
    try:
        async for msg in ws:
            if isinstance(msg, (bytes, bytearray)):
                continue                    # Voice Relay is text-only; ignore stray binary
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                continue
            print("rx", payload)
            cmd = payload.get("command")
            if cmd == "connect":
                await ws.send(json.dumps({"command": "answer"}))
                await ws.send(json.dumps({"command": "text",
                                          "text": "Hi! Anything you say I will repeat back.",
                                          "isLast": True}))
                continue
            if cmd in ("text", "prompt") and payload.get("text"):
                await ws.send(json.dumps({"command": "text",
                                          "text": f"You said: {payload['text']}",
                                          "isLast": True}))
    finally:
        print("connection closed")

async def main():
    async with websockets.serve(handler, "0.0.0.0", PORT):
        print(f"VOICE_RELAY echo server on :{PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
```

Both echo servers reply to `connect`, greet the caller, and read back each transcribed turn. That is enough to confirm the relay plumbing before you swap the echo for a real LLM call (see 4.1 for a LangChain-backed version supporting OpenAI, Claude, and Gemini).

## Choosing between STREAM and VOICE_RELAY

| Question | STREAM | VOICE_RELAY |
| --- | --- | --- |
| Do you control STT? | Yes, your problem | No, Sinch handles it |
| Do you control TTS? | Yes, your problem | No, Sinch handles it |
| Audio format | PCM only (codec fixed) | N/A, text only |
| Bandwidth | Audio: sampleRate × bytes/sec | Tiny (just JSON) |
| Latency floor | Sub-second possible | Sinch STT/TTS + your model per turn |
| LLM provider lock-in | None | None |
| Use when... | Custom voice agent, audio-to-audio model | Standard LLM + Sinch voices |

Rule of thumb: reach for **VOICE_RELAY** (4.1) unless you specifically need to own the audio path; reach for **STREAM** (4.2) when you run your own ASR/TTS or an audio-to-audio model.

## Production checklist

| Concern | What to do |
| --- | --- |
| **TLS** | Always run behind `wss://`. `ws://` is local dev only. ngrok gives you `wss://` for free during development. |
| **Auth** | The endpoint URL is on the open internet. Validate a token from the query string, a header on the upgrade request, or a value in `callHeaders` / the `connect` message. Drop the connection if it doesn't match. |
| **Resource limits** | Each call = one WS connection = some memory + CPU. Set per-process connection caps and decide your horizontal-scale strategy up front. |
| **Backpressure** | When the downstream model can't keep up, drop frames. Never buffer indefinitely; buffers inflate perceived latency. |
| **Heartbeat / keepalive** | Send `{"command":"heartbeat"}` (STREAM) or rely on WS pings (VOICE_RELAY) every ~30 s so corporate proxies don't kill idle connections. |
| **Observability** | Log `callId` + `applicationId` (STREAM) or `callId` (VOICE_RELAY) on every message. They are your join key with [3.6 Track Call Status](../3.6-track-call-status/description.md). |
| **Reconnect strategy** | Sinch does not reconnect on its own. If your server drops mid-call, the call leg ends. Crash-only design plus supervised process restarts beat fragile reconnection logic. |

## What the OpenAPI spec actually defines

The spec covers only the **SVAML side**: how you point a call at your server, not the bytes exchanged afterward.

- **`STREAM`** (`stream` schema): requires `stream.endpoint` (`ws://` or `wss://`, public). `streamOptions.codec` is fixed to `PCM`. `streamOptions.sampleRate` is in `{8000, 16000, 24000, 44100, 48000, 96000}`, default `8000`. `streamOptions.version` default `1`. Optional `callHeaders[]` (max 16, key/value up to 255 chars).
- **`VOICE_RELAY`** (`voiceRelay` schema): requires `voiceRelay.endpoint` (URI), `ttsVoice`, and `sttLanguage` (BCP-47, for example `en-US`). Optional `enableInterruptions` (default `true`) and `callHeaders[]` (max 16).
- The on-the-wire JSON/binary protocols between Sinch and your WebSocket server are out of band of the OpenAPI spec; they live in the Streams / Voice Relay product docs. Every command name in this tutorial is marked "verify" above for that reason.

## Sample code in this tutorial

| File | What it does |
| --- | --- |
| [`scripts/ws-stream-server.node.js`](scripts/ws-stream-server.node.js) | Minimal echo `STREAM` server (Node.js + `ws`). |
| [`scripts/ws-stream-server.py`](scripts/ws-stream-server.py) | Minimal echo `STREAM` server (Python + `websockets`). |
| [`scripts/ws-relay-server.node.js`](scripts/ws-relay-server.node.js) | `VOICE_RELAY` text-echo server (Node.js). |
| [`scripts/ws-relay-server.py`](scripts/ws-relay-server.py) | `VOICE_RELAY` text-echo server (Python). |

Each echoes back what it receives so you can sanity-check the WebSocket plumbing, using the local client snippets above or a live call, before plugging in a real LLM / ASR / TTS.
