# 4.3 Integrate an AI Agent with a Bridge (ElevenLabs)

## Overview

This tutorial bridges a Sinch voice call into an external AI agent's WebSocket, here an [ElevenLabs](https://elevenlabs.io) Conversational AI ("Eleven Agents") agent, using a small relay server in the middle. The relay accepts the Sinch `STREAM` connection (raw PCM audio in and out) and shuttles that audio to and from the ElevenLabs WebSocket, plus a couple of control messages.

All the code referenced here lives in the [`sinch/sinch-voice-tutorials`](https://github.com/sinch/sinch-voice-tutorials) repository, in this tutorial's folder. Clone it before you start (see [Get the code](#1-get-the-code)).

You call your Sinch number's flow, it dials a phone, and the answered call talks to an ElevenLabs voice agent. If you're new to Sinch audio streaming, read [4.2 Stream Call Audio](../4.2-stream-audio/description.md) first for the underlying `STREAM` mechanics.

## Files in this tutorial

- [`bridge.py`](./bridge.py) — WebSocket server that accepts the Sinch stream on one side and connects to ElevenLabs on the other; pipes audio both directions and translates ElevenLabs `interruption` events into a Sinch `clear` command (barge-in).
- [`stream.py`](./stream.py) — one-shot script that calls `POST /v2/projects/{projectId}/calls` to dial a destination and tell Sinch to stream the call audio to `bridge.py`.
- [`requirements.txt`](./requirements.txt) — Python dependencies.
- [`.env.example`](./.env.example) — template for the environment variables both scripts read.

**When to use this vs Voice Relay:** Use this bridge when you want a third-party voice-agent SDK (ElevenLabs, OpenAI Realtime, Deepgram Voice Agent, and so on) to run the whole conversation: STT, the LLM, and TTS all live in that vendor. If instead you want Sinch to do speech-to-text and text-to-speech for you and you only exchange plain text with your own backend, use [4.1 Voice Relay](../4.1-voice-relay/description.md); it is simpler and you never touch raw audio. This bridge is the right tool only when the agent platform owns the voice.

## What success looks like

You run the bridge, run `stream.py`, your phone (the `DESTINATION_NUMBER`) rings, you answer, and you can hold a spoken back-and-forth with the ElevenLabs agent. The bridge logs show `ConnectRequest`, `Answered`, `ElevenLabs WebSocket connected`, then alternating `Agent :` / `User :` transcript lines.

---

## Quick start (minimal first-success path)

Order matters: the ElevenLabs credentials and the public WebSocket URL must be in place **before** you place the call, and the bridge must be running **before** `stream.py` dials.

### 0. Get your ElevenLabs credentials first

You need two things from the [ElevenLabs dashboard](https://elevenlabs.io):

- **`ELEVENLABS_API_KEY`** — your account API key. In the dashboard, open your profile menu and choose **API Keys** (or go to Settings → API Keys), then create or copy a key.
- **`ELEVENLABS_AGENT_ID`** — create a Conversational AI agent under **Agents** (formerly "Conversational AI"), open it, and copy its **Agent ID**. Configure the agent's voice, system prompt, and first message there; the bridge only moves audio, it does not configure the agent.

> The agent's input/output audio format is configured **on the agent** in the ElevenLabs dashboard (see [Audio format](#audio-format) below). Make sure it matches the sample rate you use in `stream.py`.

### 1. Get the code

Clone the tutorials repository and change into this tutorial's folder:

```bash
git clone https://github.com/sinch/sinch-voice-tutorials.git
cd sinch-voice-tutorials/4.3-integrate-ai-agent-bridge   # this tutorial's folder
```

All commands below are run from that folder, which holds `bridge.py`, `stream.py`, `requirements.txt`, and `.env.example`. If you prefer not to clone the whole repository, you can download just this folder from GitHub, but keeping the repo lets you follow the sibling links to [4.2 Stream Call Audio](../4.2-stream-audio/description.md) and [4.1 Voice Relay](../4.1-voice-relay/description.md).

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

This installs `websockets`, `python-dotenv`, and `requests`.

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description |
| --- | --- |
| `PORT` | Bridge WebSocket listen port (default `8765`) |
| `CONNECT_TIMEOUT_SECONDS` | How long to wait for the Sinch `ConnectRequest` before dropping (default `10`) |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `ELEVENLABS_API_KEY` | ElevenLabs API key (see step 0) |
| `ELEVENLABS_AGENT_ID` | ElevenLabs agent ID (see step 0) |
| `PROJECT_ID` | Sinch Voice project ID |
| `KEY_ID` / `KEY_SECRET` | Sinch API credentials (HTTP Basic) |
| `SINCH_NUMBER` | Sinch provisioned phone number (E.164) |
| `DESTINATION_NUMBER` | Phone number to call |
| `WS_URL` | Public WebSocket URL pointing at `bridge.py` (e.g. via ngrok) |

> **Naming note:** this tutorial's code uses `WS_URL`. The sibling tutorial [4.2 Stream Call Audio](../4.2-stream-audio/description.md) uses `WS_ENDPOINT` for the same concept. They are not interchangeable here: `stream.py` reads `WS_URL`. If you copied an `.env` from 4.2, rename the variable.

### 4. Start the bridge server

```bash
python3 bridge.py
```

It refuses to start unless `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID` are set. You should see `Bridge listening on ws://0.0.0.0:8765`.

### 5. Expose the bridge publicly with ngrok

In another terminal:

```bash
ngrok http 8765
# Forwarding  https://abc123.ngrok-free.app -> http://localhost:8765
```

Convert the HTTPS forwarding URL to a `wss://` WebSocket URL and put it in `.env`:

```
WS_URL=wss://abc123.ngrok-free.app
```

Sinch requires `wss://` (TLS) reachable from the public internet; a plain `http`/`ws` localhost URL will not work.

### 6. Place the call

In a third terminal:

```bash
python3 stream.py
```

Sinch dials `DESTINATION_NUMBER`. When it answers, the audio is bridged to your ElevenLabs agent through `bridge.py`. Pick up and start talking.

---

## How it works

1. `stream.py` posts a `POST /v2/projects/{projectId}/calls` with a `dial` to `DESTINATION_NUMBER` and an `onAnswer` that (a) bridges the phone leg into a bridge named `bridge`, and (b) issues a second `dial` to a `STREAM` `to`, pointing at `WS_URL`, joining the same `bridge`.
2. Sinch dials the destination phone. When answered, both legs (phone and stream) share the bridge name `bridge`, so audio flows bidirectionally.
3. Sinch opens a WebSocket to `bridge.py` and sends a `ConnectRequest`: `{"command":"connect","callId":"...", ...}`. *(Sinch contract, confirmed against the spec and 4.2.)*
4. `bridge.py` replies with `{"command":"answer"}`, then opens a second WebSocket to ElevenLabs.
5. Two asyncio tasks ferry audio:
   - `sinch_to_el` — binary PCM frames from Sinch to base64-wrapped `{"user_audio_chunk": "..."}` JSON to ElevenLabs.
   - `el_to_sinch` — ElevenLabs `audio` events to decoded PCM bytes written back to Sinch as binary frames.
6. ElevenLabs `interruption` events are translated into `{"command":"clear"}` on the Sinch socket; Sinch flushes any audio it had queued so the caller can talk over the agent (barge-in).
7. When either side closes, `asyncio.wait(..., FIRST_COMPLETED)` returns, the other task is cancelled, and the session tears down.

> **ElevenLabs protocol, verify against ElevenLabs docs.** The message shapes the code relies on (`user_audio_chunk` to send; `audio` with `audio_event.audio_base_64`, `ping` with `ping_event.event_id`, `agent_response`, `user_transcript`, `interruption`, `conversation_initiation_metadata` received) match the publicly documented [Agent WebSocket](https://elevenlabs.io/docs/eleven-agents/api-reference/eleven-agents/websocket) message model at the time of writing, but ElevenLabs evolves this API (it was recently rebranded from "Conversational AI" to "Eleven Agents"). Treat these shapes, and the audio-format query parameters discussed below, as **verify against current ElevenLabs docs**, not Sinch facts.

## The SVAML `stream.py` posts

For reference, this is the payload `stream.py` sends:

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "origin",
      "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
      "to":   { "type": "PHONE", "phone": { "number": "<DESTINATION_NUMBER>" } },
      "dialTimeoutDurationSeconds": 30,
      "maxCallDurationSeconds": 180,
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "bridge" },
          {
            "command": "dial",
            "callName": "connect_stream",
            "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
            "to": {
              "type": "STREAM",
              "stream": {
                "endpoint": "<WS_URL>",
                "streamOptions": { "version": 1, "codec": "PCM", "sampleRate": 8000 },
                "callHeaders": [ { "key": "X-Timeout-Seconds", "value": "10" } ]
              }
            },
            "events": {
              "onAnswer": [ { "command": "bridgeCall", "bridgeName": "bridge" } ]
            }
          }
        ],
        "onHangup": [
          { "command": "hangup", "callName": "connect_stream" }
        ]
      }
    }
  ]
}
```

## Audio format

Sinch streams linear PCM at the `sampleRate` you set in `streamOptions`; the spec accepts `8000`, `16000`, `24000`, `44100`, `48000`, `96000`, and `codec` is fixed to `PCM`. PSTN calls are typically 8 kHz, so 8 kHz is the sensible default and gains nothing from a higher rate on a PSTN-only path.

The two sides must agree on sample rate, or you get chipmunked (too fast) or slowed-down (too slow) audio. Two things must line up:

1. `streamOptions.sampleRate` in `stream.py` (Sinch side).
2. The ElevenLabs **agent's** configured input and output audio format (set in the ElevenLabs dashboard). ElevenLabs supports `pcm_8000`, `pcm_16000`, `pcm_22050`, `pcm_24000`, `pcm_44100`, `pcm_48000`, and `ulaw_8000`.

To run at 16 kHz, set `streamOptions.sampleRate` to `16000` in `stream.py` and set the agent's input/output format to `pcm_16000` in the ElevenLabs dashboard.

> **Suspected-wrong, verify against ElevenLabs docs.** `bridge.py` builds the ElevenLabs URL as
> `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=...&output_format=...&input_audio_format=...`, defaulting both format query params to `pcm_8000` (they are not part of `.env.example`).
> The current ElevenLabs Agent WebSocket reference lists **`agent_id`** as a query parameter but does **not** document `output_format` or `input_audio_format` as query parameters; audio format is configured **on the agent** and negotiated via the `conversation_initiation_metadata` event. These query params may be ignored by the server. **Configure the format on the agent itself, and verify whether these query overrides are still honored.** If audio sounds wrong, the agent-side format is the source of truth. *(The base URL `wss://api.elevenlabs.io/v1/convai/conversation` and the `xi-api-key` auth header are the conventional ElevenLabs values; both should be verified against current docs.)*

## Robustness — what the code does and does not handle

`bridge.py` is a working demo, not production-hardened. Current behavior:

- **Sinch socket close / ElevenLabs socket close:** handled. Whichever forwarding task finishes first cancels the other and the session ends cleanly. `ConnectionClosedOK` / `ConnectionClosedError` are caught and logged.
- **`ConnectRequest` timeout:** handled (`CONNECT_TIMEOUT_SECONDS`).
- **ElevenLabs `ping`:** answered with `pong` (keepalive).
- **No reconnect / failover:** if the ElevenLabs socket drops mid-call or the service is degraded, the bridge tears the call down; there is **no bounded reconnect** and no fallback to Voice Relay or TTS. Add one if you need resilience.
- **No backpressure / underrun handling:** audio frames are forwarded as fast as they arrive with no buffering policy. Under load you must drop, not buffer indefinitely.
- **Sinch `clear` to ElevenLabs:** when Sinch sends `{"command":"clear"}` to the bridge, it is logged as a no-op; ElevenLabs has no documented buffer-clear command in this direction. Barge-in flows the other way (ElevenLabs `interruption` to Sinch `clear`), which is the case that matters.

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Auth for the relay WebSocket** | `bridge.py` accepts any WS connection on its port. In production, validate a token in the URL query string or in `callHeaders` (surfaced in the `ConnectRequest`) before answering. |
| **Per-call state** | The bridge keeps no state across calls. If you need it (analytics, billing, hand-off history), key it by `callId` from the `ConnectRequest`. |
| **ElevenLabs costs** | Agent billing is per minute. Cap calls with `maxCallDurationSeconds` on the SVAML `dial` to bound exposure (it is set to 180 s here). |
| **Failover** | If ElevenLabs is degraded, the bridge currently drops the call. Consider failing over to [Voice Relay](../4.1-voice-relay/description.md) or a TTS-only message. |
| **Audio quality** | If PSTN delivers narrowband audio, 8 kHz is fine. Bump to 16 kHz only when the downstream agent benefits and all three format settings agree. |
| **Barge-in** | ElevenLabs sends `interruption` when the user talks over the agent; the bridge maps it to Sinch `{"command":"clear"}` to flush queued audio. Keep it on. |

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project, API credentials (`KEY_ID` / `KEY_SECRET`), and a Sinch virtual number.
- An ElevenLabs account with an API key and a configured agent (see [Quick start step 0](#0-get-your-elevenlabs-credentials-first)).
- Python 3.x.
- Git, to clone the [tutorials repository](https://github.com/sinch/sinch-voice-tutorials).
- A publicly accessible `wss://` URL pointing at `bridge.py` (use [ngrok](https://ngrok.com) during development).

## What the OpenAPI spec says — at a glance

*(Sinch facts, confirmed against `voice-api-v2.openapi.latest.yml`.)*

- `to: { type: STREAM, stream: { endpoint, streamOptions, callHeaders } }` is the destination type used here. `endpoint` is required and must be `ws://` or `wss://`.
- `streamOptions.codec` is fixed to `PCM`; `streamOptions.sampleRate` is one of `8000 | 16000 | 24000 | 44100 | 48000 | 96000`, default `8000`; `streamOptions.version` defaults to `1`.
- `callHeaders[]` is a list of up to 16 `{key, value}` pairs (each value up to 255 chars), surfaced to your WebSocket in the `ConnectRequest`.
- The on-the-wire WebSocket protocol (`ConnectRequest` / `{"command":"answer"}` / binary PCM / `{"command":"clear"}` / `{"command":"heartbeat"}`) is part of the Sinch Streams product surface, documented alongside [4.2 Stream Call Audio](../4.2-stream-audio/description.md), not in the OpenAPI schema itself.
- The ElevenLabs side is documented by ElevenLabs, not Sinch; see the **verify against ElevenLabs docs** notes above.

