# 4.1 Connect an AI Chatbot (Voice Relay)

## Overview

The Sinch Voice API's **Voice Relay** destination type connects a live phone call to a WebSocket server that speaks a simple text-in / text-out protocol. Unlike the raw PCM streaming in [4.2 Stream Call Audio](../4.2-stream-audio/description.md), Voice Relay performs speech-to-text and text-to-speech **on the Sinch side**, so your server only sends and receives plain text. Wiring a language model into a real phone call is therefore mostly a matter of forwarding text turns to your LLM provider.

This tutorial uses a Python WebSocket server backed by [LangChain](https://www.langchain.com/), so the same code works with OpenAI, Anthropic Claude, or Google Gemini by changing one environment variable.

### Real-life examples

- **AI receptionist:** answer inbound calls 24/7, handle FAQs, route or escalate based on the conversation.
- **Product demo bot:** let prospects call a number and talk to an AI that explains your product.
- **Internal helpdesk:** staff call a number to ask an LLM about internal tools, runbooks, or HR policies.
- **Voice-first prototyping:** validate a conversational AI design over a real phone call before building a full IVR.

---

## Get the code

All files for this tutorial live in the [`sinch/sinch-voice-tutorials`](https://github.com/sinch/sinch-voice-tutorials) repository, under `4.1-voice-relay`. Clone it first:

```bash
git clone https://github.com/sinch/sinch-voice-tutorials.git
cd sinch-voice-tutorials
```

Every path in this guide is relative to the repo. The tutorial folder has its **own** `.env.example` and `requirements.txt`, separate from the tutorials-root `.env`.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project, API credentials, and a virtual phone number.
- Python 3.10 or newer.
- An API key for one LLM provider: OpenAI, Anthropic Claude, or Google Gemini.
- [ngrok](https://ngrok.com) (or another way to expose a local port over `wss://`) for development.

---

## Fastest path to first success

You will: install deps → set one LLM key → expose the server with ngrok → point a `VOICE_RELAY` destination at it → call the number and talk to the bot.

### 1. Install dependencies

```bash
cd tutorials/4.1-voice-relay
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

`requirements.txt` pulls in `websockets`, `python-dotenv`, `langchain-core`, and one provider package per LLM (`langchain-openai`, `langchain-anthropic`, `langchain-google-genai`). You only need the package for the provider you choose, but installing all three is harmless.

### 2. Set your LLM key

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Provider: openai | claude | gemini
PROVIDER=claude
API_KEY=sk-ant-...
```

`API_KEY` is the key for whichever `PROVIDER` you pick. Where to get one:

| `PROVIDER` | Get a key at | Default model |
| --- | --- | --- |
| `openai` | <https://platform.openai.com/api-keys> | `gpt-4o` |
| `claude` | <https://console.anthropic.com/settings/keys> | `claude-haiku-4-5` |
| `gemini` | <https://aistudio.google.com/apikey> | `gemini-2.0-flash` |

Optional overrides: `MODEL`, `TEMPERATURE` (default `0.7`), `MAX_TOKENS` (default `1024`), `GREETING` (default `Hello!`), `PORT` (default `8765`).

> **Early local check (before any phone call).** You can confirm the server starts and the LLM key works without placing a call:
> ```bash
> python server.py
> ```
> On startup it prints the provider, model, max tokens, and that it loaded `system_prompt.md`. If the key is bad you will see an authentication error from the provider as soon as the first turn runs. Stop here and fix `.env` before going further, since a broken key produces a silent, unresponsive bot on the call that is much harder to debug.

### 3. Start the server and expose it with ngrok

In one terminal:

```bash
python server.py
# [*] Provider: claude  Model: claude-haiku-4-5  Temp: 0.7  MaxTokens: 1024
# [*] Agent Relay listening on ws://0.0.0.0:8765
```

In a second terminal:

```bash
ngrok http 8765
```

Copy the **Forwarding** URL (e.g. `https://abc123.ngrok-free.app`). For the Voice Relay endpoint you must use the **`wss://`** form of it: `wss://abc123.ngrok-free.app`.

> **About `WS_ENDPOINT` / `WS_URL`.** The tutorials-root `.env.example` defines a shared `WS_ENDPOINT` variable, but **`server.py` does not read it**. The relay server only reads `PROVIDER`, `API_KEY`, `MODEL`, `TEMPERATURE`, `MAX_TOKENS`, `GREETING`, and `PORT`. The ngrok `wss://` URL is configured on the Sinch side (in the SVAML `voiceRelay.endpoint`, below), not in any `.env`. There is no `WS_URL` variable anywhere in this tutorial; ignore both names for the relay server itself.

### 4. Point a VOICE_RELAY destination at your server

A Voice Relay destination is a `dial` target of type `VOICE_RELAY`. The minimal destination object is:

```json
{
  "type": "VOICE_RELAY",
  "voiceRelay": {
    "endpoint": "wss://abc123.ngrok-free.app",
    "ttsVoice": "Emma",
    "sttLanguage": "en-US"
  }
}
```

Verified against the OpenAPI spec (`voiceRelay` schema): `endpoint`, `ttsVoice`, and `sttLanguage` are **required**. `sttLanguage` is a BCP-47 tag (`en-US`). Optional fields are `enableInterruptions` (boolean, default `true`) and `callHeaders[]` (up to 16 key/value objects, each value/key ≤ 255 chars).

The simplest way to make every inbound call reach the bot is a **STATIC** call behavior on your Sinch service: a fixed SVAML script the platform runs for every inbound call, with no webhook server of your own. Configure it on the [dashboard](https://dashboard.sinch.com/voice/services) or via the API:

```bash
curl -X PATCH \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/services/$SERVICE_ID" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "callBehavior": {
    "type": "STATIC",
    "static": {
      "callName": "caller",
      "commands": [
        { "command": "answer" },
        { "command": "bridgeCall", "bridgeName": "main-bridge" },
        {
          "command": "dial",
          "callName": "voice_relay_call",
          "to": {
            "type": "VOICE_RELAY",
            "voiceRelay": {
              "endpoint":    "wss://abc123.ngrok-free.app",
              "ttsVoice":    "Emma",
              "sttLanguage": "en-US"
            }
          },
          "events": {
            "onAnswer": [
              { "command": "bridgeCall", "bridgeName": "main-bridge" }
            ]
          }
        }
      ],
      "events": {
        "onHangup": [
          { "command": "hangup", "callName": "voice_relay_call" }
        ]
      }
    }
  }
}
JSON
```

Auth is **HTTP Basic** with your project key (`KEY_ID:KEY_SECRET`). Set `KEY_ID`, `KEY_SECRET`, `PROJECT_ID`, and `SERVICE_ID` from the tutorials-root `.env` (or your shell). Replace `endpoint` with your current `wss://` ngrok URL. It changes every time you restart ngrok on the free tier.

> **`ttsVoice` value.** `Emma` is the example voice from the spec; `Tiffany` (shipped in `static.txt`) is another. For the full list of supported voices see the [Text-to-Speech Voices reference](https://developer.sinch.com/docs/voice/api-reference/text-to-speech-voices). If a voice name is wrong the platform falls back or errors at call time, so verify the name against that list.

> **Spec note: `static.events`.** The OpenAPI `staticCallBehavior.events` schema documents only `onHangup` at the top level (used above). The per-leg `dial.events` block supports the full call-event set (`onAnswer`, etc.).

### 5. Call the number and talk to the bot

Dial your Sinch virtual number from any phone. The flow:

1. The platform answers, opens a WebSocket to your `wss://` endpoint, and sends a `connect` message.
2. Your server replies `answer` and an optional greeting, which Sinch's TTS speaks to you.
3. You talk; Sinch transcribes your speech and forwards it as text; the server sends it to the LLM and returns the reply as text; Sinch speaks it back.

### What success looks like

- The phone is answered and you hear the greeting (default `Hello!`).
- You speak; the bot answers in a natural voice.
- In the `python server.py` terminal you see the live transcript:
  ```
  [+] Connected: ('…', …)
    WS << {"command":"connect", ...}
    connect  callId=…  serviceId=…
    WS >> {"command": "answer"}
    WS >> {"command": "text", "text": "Hello!", ...}
    STT → 'what can you do'
    LLM ← 'I can answer questions over the phone…'
    WS >> {"command": "text", "text": "...", "isLast": true, ...}
  ```
- When you hang up, the session ends and history is discarded.

---

## How it works

### The Voice Relay protocol (text only)

Once Sinch dials the relay leg it opens a WebSocket and exchanges JSON messages. Your server never handles audio; STT and TTS happen on the Sinch side.

| Direction | `command` | Description |
| --- | --- | --- |
| Sinch → Server | `connect` | Session start; carries `callId`, `serviceId`, and any `callHeaders` from the SVAML. |
| Server → Sinch | `answer` | Accept the relay session. |
| Server → Sinch | `text` (`isLast: true`) | Text for Sinch to read to the caller via TTS. |
| Sinch → Server | `text` / `prompt` | Transcribed speech from the caller. |
| Sinch → Server | `interrupt` | Caller spoke during TTS playback (barge-in). |
| Sinch → Server | `dtmf` | Keypad digits pressed by the caller. |
| Sinch → Server | `textPlaybackStart` / `Stop` / `Cancel` | TTS playback lifecycle events. |

> **Contract caveat: verify before relying on it.** This on-the-wire protocol is **not part of the OpenAPI/SVAML REST contract**. The spec defines only the `VOICE_RELAY` destination shape (`endpoint`, `ttsVoice`, `sttLanguage`, `enableInterruptions`, `callHeaders`). The message names and fields above (`connect`/`answer`/`text`/`prompt`/`interrupt`/`dtmf`/`textPlayback*`, `isLast`, `isInterruptible`) reflect the shipped `server.py` and its comment referencing an `agent-relay.asyncapi.yml` that is **not present in this repo**. Treat the exact framing as "what the example assumes," and confirm it against the current Voice Relay product documentation before building on it. If a field name has drifted, the symptom is a silent or one-sided call.

### How the agent handles a turn

On `connect`, `server.py` sends `answer` plus an optional greeting (`GREETING`, default `Hello!`). On each `text` / `prompt`:

1. The transcribed text is appended to an in-memory conversation history.
2. The full history plus the system prompt from `system_prompt.md` is sent to the LLM via LangChain (`LLM.ainvoke`).
3. The reply is returned as `{"command": "text", "text": "…", "isLast": true, "isInterruptible": true}`.
4. The reply is appended to history so context persists across turns.

History is per-connection and in memory; it resets when the call ends. `interrupt`, `dtmf`, and `textPlayback*` events are logged and otherwise ignored.

### Robustness in the example (and its limits)

- **Socket close** is handled: `websockets.exceptions.ConnectionClosed` is caught and logged with its code/reason.
- **LLM errors** are caught per-turn and logged, but the example does **not** send a fallback message to the caller, so a provider failure leaves the caller in silence. For production, send a short apology `text` message in the `except` branch.
- **No reconnection logic** is needed on the server side. Sinch opens the socket; if it drops, the session simply ends.
- The reply is sent as a single `text` with `isLast: true`. Streaming token-by-token (multiple `text` messages with `isLast: false` then a final `isLast: true`) would lower perceived latency; the example keeps it simple with one full reply.

### Customise the agent

Edit `system_prompt.md` to change persona, domain, and behaviour. It is read once at startup, so restart `server.py` after editing. The shipped persona is **RELAY**, a witty Sinch demo agent. To switch providers, change `PROVIDER` + `API_KEY` in `.env` and restart.

---

## Recommended path vs. fallback

- **Headline provider:** any of the three works. For phone conversations, **latency dominates the experience**, so pick a fast model (`claude-haiku-4-5`, `gpt-4o-mini`, `gemini-2.0-flash`) over a slow flagship.
- **Voice Relay vs. Stream:** use **Voice Relay** (this tutorial) when you want text in/out and let Sinch own STT/TTS. It is the simplest way to put an LLM on a call. Use **Stream** when you need raw bidirectional PCM audio.

---

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Latency budget** | Aim for sub-~1.5 s round-trip per turn. Use fast models; consider streaming the reply in chunks. |
| **LLM errors** | Add a fallback `text` reply in the `except` branch so a provider failure doesn't leave the caller in silence. |
| **Barge-in** | Leave `enableInterruptions: true` (default) for natural turn-taking; set `false` only when reading legal disclaimers etc. (an interrupt signal is still delivered so you can choose to stop playback). |
| **Conversation history** | The example keeps history in memory and loses it on disconnect. For production, persist by `callId`. |
| **PII / safety** | LLM output goes straight to the caller. Add moderation/guardrails before forwarding TTS. |
| **Custom metadata** | Use `voiceRelay.callHeaders[]` (≤ 16 pairs) to pass tenant/campaign IDs into the `connect` event instead of URL params. |
| **Static vs. webhook** | STATIC suits "every inbound call gets the same agent." For per-DID routing, use a webhook service that returns `commands` computed per request. |

---

## Voice Relay config reference

- `VOICE_RELAY` is one of the `to` destination types, alongside `PHONE`, `SIP`, and `STREAM`.
- `voiceRelay` required fields: `endpoint` (`wss://` URI, `format: uri`), `ttsVoice` (string), `sttLanguage` (BCP-47, pattern `^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|[0-9]{3}))?$`).
- Optional: `enableInterruptions` (boolean, default `true`), `callHeaders[]` (array, `maxItems: 16`; each item `{ key, value }`, each ≤ 255 chars).
- The text-in/text-out WebSocket protocol between Sinch and your server is **not** part of the REST/SVAML contract; see the contract caveat above.

---

## Files in this tutorial

Find these files in [repository](https://github.com/sinch/sinch-voice-tutorials).

| File | Purpose |
| --- | --- |
| `server.py` | LangChain-backed Voice Relay WebSocket server (port 8765). |
| `requirements.txt` | `websockets`, `python-dotenv`, `langchain-core`, and per-provider LangChain packages. |
| `.env.example` | `PROVIDER`, `API_KEY`, optional `MODEL`/`TEMPERATURE`/`MAX_TOKENS`/`PORT`. Copy to `.env`. |
| `system_prompt.md` | The agent persona, loaded at startup. |
| `static.txt` | A ready-made STATIC SVAML body (with a sample ngrok endpoint and `ttsVoice: Tiffany`) you can paste into the dashboard or the PATCH request. |