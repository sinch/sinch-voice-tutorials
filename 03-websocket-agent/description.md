# Connect Calls to an AI Agent via WebSocket (Real-time Audio Streaming)

## Overview

The Sinch Voice API can stream live PCM audio from a phone call bidirectionally to a WebSocket server. This enables you to feed real-time call audio into AI models, speech-to-text engines, sentiment analysis pipelines, or custom voice bots. When a call is routed to a `STREAM` destination, Sinch establishes a WebSocket connection to your server, sends a `ConnectRequest` JSON message (carrying the call ID and metadata), and waits for a `ConnectResponse`. Once your server replies with `{"command": "answer"}`, raw PCM audio frames begin flowing as binary WebSocket messages in both directions. You can send synthesized audio back to the caller by writing binary frames to the WebSocket.

## Real-life examples

- **AI Voice Bot**: Feed the PCM stream into a speech recognition service (e.g., Whisper or Google STT), process the transcript with an LLM, synthesize a response with TTS, and stream it back.
- **Live transcription and captioning**: Pipe inbound audio to a real-time transcription service and display captions in a dashboard.
- **Sentiment analysis**: Analyze caller tone in real time for agent assist or quality monitoring.
- **Custom IVR**: Build a fully custom interactive voice response system driven by your own NLP logic.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with API credentials.
- A Sinch virtual phone number.
- A publicly accessible WebSocket endpoint. Use [ngrok](https://ngrok.com) during development:
  ```bash
  ngrok http 8765    # exposes ws://localhost:8765 as wss://<id>.ngrok-free.app
  ```
- Node.js 18+ (`ws` library), Python 3.8+ (`websockets` library), PHP 8+ (Ratchet), or Java 11+ (Tyrus).

## Step-by-step instructions

### 1. Understand the WebSocket protocol

Sinch uses a simple text/binary protocol on the WebSocket connection:

| Direction | Format | Description |
|-----------|--------|-------------|
| Sinch → Server | JSON (text) | `ConnectRequest`: `{"command":"connect","callId":"...","applicationId":"...","headers":{...}}` |
| Server → Sinch | JSON (text) | `ConnectResponse`: `{"command":"answer"}` (or `"busy"` / `"reject"`) |
| Sinch ↔ Server | Binary | Raw PCM audio frames (codec: PCM, sample rate: 8000–96000 Hz) |
| Server → Sinch | JSON (text) | `StreamControl`: `{"command":"clear"}` or `{"command":"heartbeat"}` |

### 2. Start the WebSocket server

```bash
# Node.js (ws library)
npm install ws
node scripts/ws-server.node.js

# Python (websockets library)
pip install websockets
python scripts/ws-server.py
```

The server listens on port `8765` by default.

### 3. Expose your server with ngrok

```bash
ngrok http 8765
```

Copy the Forwarding URL (e.g. `https://abc123.ngrok-free.app`) and convert it to a WebSocket URL:
- `https://abc123.ngrok-free.app` → `wss://abc123.ngrok-free.app`

### 4. Trigger a call that streams to your WebSocket server

Use the `trigger-call.sh` or `trigger-call.js` scripts to make an outbound call that connects to your WebSocket server once answered:

```bash
export WS_ENDPOINT=wss://abc123.ngrok-free.app
bash scripts/trigger-call.sh
```

Or, if you want inbound calls to be routed to your WebSocket server automatically, configure your Sinch service with a webhook and use the `ice-callback` server — which handles `call.incoming` events and responds with SVAML to connect to the stream.

### 5. How the SVAML payload for streaming looks

The `dial` command with a `STREAM` destination type routes audio to your WebSocket:

```json
{
  "commands": [
    {
      "command": "dial",
      "name": "phone-leg",
      "from": { "type": "PHONE", "phone": { "number": "+1SINCH_NUMBER" } },
      "to":   { "type": "PHONE", "phone": { "number": "+1DESTINATION" } },
      "dialTimeout": "30s",
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "name": "audio-bridge" },
          {
            "command": "dial",
            "name": "stream-leg",
            "to": {
              "type": "STREAM",
              "stream": {
                "endpoint": "wss://abc123.ngrok-free.app",
                "streamOptions": {
                  "version": 1,
                  "codec": "PCM",
                  "sampleRate": 8000
                }
              }
            },
            "events": {
              "onAnswer": [{ "command": "bridgeCall", "name": "audio-bridge" }]
            }
          }
        ]
      }
    }
  ]
}
```

The `bridgeCall` commands connect the phone leg and the stream leg so audio flows bidirectionally.

### 6. Send audio back to the caller

From your WebSocket server, write raw PCM binary frames to the connection. The audio must match the `sampleRate` and `codec` negotiated in the SVAML (`PCM`, 8000 Hz for PSTN calls). Use the `{"command":"heartbeat"}` StreamControl message during silent periods to keep the connection alive.
