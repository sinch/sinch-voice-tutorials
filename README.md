# Sinch Voice API v2 Tutorials

Runnable, copy-paste-ready examples for the most common [Sinch Voice API v2](https://developers.sinch.com/docs/voice/) use cases.

---

## Prerequisites

| Requirement | Details |
|---|---|
| Sinch account | Sign up at [dashboard.sinch.com](https://dashboard.sinch.com) |
| Sinch virtual number | Provision from the dashboard under **Numbers** |
| API credentials | Create a key pair under **Settings → Access Keys** |
| ngrok | Required for tutorials that use webhooks or WebSocket endpoints |
| jq (optional) | Pretty-prints JSON output in shell scripts |

---

## Setup

```bash
cp .env.example .env
# Fill in PROJECT_ID, KEY_ID, KEY_SECRET, SINCH_NUMBER, DESTINATION_NUMBER
```

Tutorials that need a public URL (webhooks, WebSocket servers) also need ngrok:

```bash
ngrok http 3000    # for webhook servers
ngrok http 8765    # for WebSocket servers
```

Set `CALLBACK_URL=https://<your-id>.ngrok-free.app` for webhooks, or `WS_ENDPOINT=wss://<your-id>.ngrok-free.app` for WebSocket tutorials.

---

## Tutorials

### 1. Outbound Calling

| # | Tutorial | What it covers |
|---|---|---|
| 1.1 | [Make an Outbound Call](./1.1-outbound-call/description.md) | POST a call, play TTS/audio, hang up — the "hello world" of Voice API v2 |
| 1.2 | [Call Pacing (Batch Calls)](./1.2-call-pacing/description.md) | Dial many recipients with `maxCps` and `ttlSeconds`; track progress via the batch summary endpoint |
| 1.3 | [Call Hunting](./1.3-call-hunting/description.md) | Sequential, simultaneous-ring, and tiered hunt patterns using `dial`, `bridgeCall`, and `hangup` |

### 2. Inbound Calling

| # | Tutorial | What it covers |
|---|---|---|
| 2.1 | [Handle Inbound PSTN Calls](./2.1-inbound-pstn/description.md) | `callBehavior`, answering incoming calls, CloudEvents headers, webhook response contract |
| 2.2 | [Call Forwarding](./2.2-call-forwarding/description.md) | Unconditional, no-answer, time-of-day, warm-transfer, and blind-transfer patterns |

### 3. In-Call Features

| # | Tutorial | What it covers |
|---|---|---|
| 3.1 | [Text-to-Speech & Voices](./3.1-tts-voices/description.md) | `SAY` vs `PLAY`, voice catalog, SSML, stopping mid-playback |
| 3.2 | [Detect Voicemail & Beeps (AMD)](./3.2-amd/description.md) | `amd` command with `onHuman` / `onMachine` / `onBeep` / `onUnknown` branches |
| 3.3 | [Record Calls & Transcribe Audio](./3.3-recording-transcription/description.md) | `startRecording` to AWS / GCS / Azure, transcription, recording lifecycle events |
| 3.4 | [Number Masking](./3.4-number-masking/description.md) | Bridge two PSTN legs through a Sinch number so neither party sees the other's real number |
| 3.5 | [Track Call Status](./3.5-track-call-status/description.md) | Polling endpoints, webhook events, `callResult` / `callReason` reference |

### 4. AI, Voice Relay & Streaming

| # | Tutorial | What it covers |
|---|---|---|
| 4.1 | [Connect an AI Chatbot (Voice Relay)](./4.1-voice-relay/description.md) | `VOICE_RELAY` destination + LangChain-backed WebSocket server (OpenAI / Claude / Gemini) |
| 4.2 | [Stream Call Audio in Real-Time](./4.2-stream-audio/description.md) | `STREAM` destination, bidirectional PCM frames, headers and lifecycle |
| 4.3 | [ElevenLabs Bridge](./4.3-elevenlabs-bridge/description.md) | Relay between Sinch `STREAM` and the ElevenLabs Conversational AI WebSocket |
| 4.4 | [WebSocket Server Reference](./4.4-websocket-server/description.md) | Protocols, minimal echo servers, production checklist |
| 4.5 | [AI IVR (Voice Relay + call patching)](./4.5-ai-ivr/description.md) | LLM classifies caller intent over Voice Relay, then `PATCH`es the live call to bridge in a human agent |

---

## Authentication

All requests use HTTP Basic Auth — `KEY_ID` as username, `KEY_SECRET` as password.

```bash
curl -u "$KEY_ID:$KEY_SECRET" https://voice.api.sinch.com/v2/projects/$PROJECT_ID/calls
```

OAuth 2.0 Client Credentials is also supported.

---

## Environment Variables

| Variable | Used by | Description |
|---|---|---|
| `PROJECT_ID` | all | Sinch project UUID |
| `KEY_ID` | all | API key ID (Basic Auth username) |
| `KEY_SECRET` | all | API key secret (Basic Auth password) |
| `SINCH_NUMBER` | all | Your Sinch virtual number in E.164 format |
| `DESTINATION_NUMBER` | outbound tutorials | Phone number to dial |
| `SERVICE_ID` | 2.1, 2.2, 4.1, 4.5 | Voice service to configure via PATCH |
| `CALLBACK_URL` | 2.1, 2.2, 3.3, 3.4 | Public webhook URL (e.g. from ngrok) |
| `WS_ENDPOINT` | 4.x | WebSocket endpoint URL (e.g. `wss://abc.ngrok-free.app`) |
| `STORAGE_DESTINATION_URL` | 3.3 | Cloud storage path (e.g. `s3://my-bucket/recordings/`) |
| `STORAGE_CREDENTIALS` | 3.3 | Storage credentials (`ACCESS_KEY:SECRET:REGION` for AWS) |
| `AGENT_NUMBERS` | 1.3 | Comma-separated agent E.164 list for hunting |
| `MAX_CPS`, `TTL_SECONDS` | 1.2 | Batch pacing options |
| `PRIMARY_NUMBER`, `FALLBACK_NUMBER` | 2.2 | Forwarding targets |
| `BUSINESS_START_HOUR_UTC`, `BUSINESS_END_HOUR_UTC` | 2.2 | Time-of-day forwarding window (UTC) |
| `SALES_NUMBER`, `SUPPORT_NUMBER` | 4.5 | Human-agent queues the AI IVR can patch into |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | 4.5 | Any OpenAI-compatible `/chat/completions` endpoint |

---

## File Map

```
tutorials/
├── README.md
├── .env.example
├── 1.1-outbound-call/          description.md
├── 1.2-call-pacing/            description.md
├── 1.3-call-hunting/           description.md
├── 2.1-inbound-pstn/           description.md
├── 2.2-call-forwarding/        description.md
├── 3.1-tts-voices/             description.md
├── 3.2-amd/                    description.md
├── 3.3-recording-transcription/ description.md
├── 3.4-number-masking/         description.md
├── 3.5-track-call-status/      description.md
├── 4.1-voice-relay/            description.md  server.py  system_prompt.md  requirements.txt
├── 4.2-stream-audio/           description.md  scripts/{ws-server,ice-callback,trigger-call}.{node,py,sh,php,java}
├── 4.3-elevenlabs-bridge/      description.md  bridge.py  stream.py  requirements.txt
├── 4.4-websocket-server/       description.md  scripts/ws-{stream,relay}-server.{node,py}
└── 4.5-ai-ivr/                 description.md  scripts/relay-server.{py,node.js,php}
                                                scripts/{configure-service,test-callout,patch-call}.sh
                                                system_prompt.md  requirements.txt
```
