# Sinch Voice API Tutorials

A collection of runnable, copy-paste-ready tutorials covering the most common use cases for the [Sinch Voice API v2](https://developers.sinch.com/docs/voice/). Each tutorial includes a detailed description and working code examples in 6 languages and tools.

---

## Prerequisites

| Requirement | Details |
|---|---|
| Sinch account | Sign up at [dashboard.sinch.com](https://dashboard.sinch.com) |
| Sinch virtual number | Provision from the dashboard under **Numbers** |
| API credentials | Create a key pair under **Settings → Access Keys** |
| Runtime (choose one) | Node.js 18+, Python 3.8+, PHP 8+, Java 11+ |
| ngrok | Required for tutorials that use webhook callbacks |
| jq (optional) | Pretty-prints JSON output in shell scripts |

---

## Quick Start

```bash
# 1. Clone or download this repository
git clone https://github.com/your-org/sinch-voice-tutorials.git
cd sinch-voice-tutorials

# 2. Copy the example environment file and fill in your credentials
cp .env.example .env
# Edit .env — add your PROJECT_ID, KEY_ID, KEY_SECRET, SINCH_NUMBER, DESTINATION_NUMBER

# 3. Pick a tutorial and run it
cd 01-tts-callout/scripts
bash callout.sh          # Shell
python callout.py        # Python
node callout.node.js     # Node.js
```

---

## Tutorials Overview

| # | Use Case | Description | Guide |
|---|---|---|---|
| 01 | **TTS Callout** | Dial a number and play a text-to-speech message | [description.md](./01-tts-callout/description.md) |
| 02 | **Number Masking** | Bridge two parties anonymously via a Sinch virtual number | [description.md](./02-number-masking/description.md) |
| 03 | **WebSocket Agent** | Stream live call audio to a WebSocket server for AI/STT processing | [description.md](./03-websocket-agent/description.md) |
| 04 | **Recording & Transcription** | Record calls and auto-transcribe to S3, GCS, or Azure | [description.md](./04-recording-transcription/description.md) |
| 05 | **AMD** | Detect live humans vs. voicemail machines and react accordingly | [description.md](./05-amd/description.md) |

---

## Environment Variables Reference

All tutorials read credentials from a `.env` file at the project root. Copy `.env.example` and fill in the values.

| Variable | Required by | Description |
|---|---|---|
| `PROJECT_ID` | All | Your Sinch project UUID (from the dashboard) |
| `KEY_ID` | All | API key ID (used as the Basic Auth username) |
| `KEY_SECRET` | All | API key secret (used as the Basic Auth password) |
| `SINCH_NUMBER` | All | Your Sinch virtual phone number in E.164 format (e.g. `+14045001000`) |
| `DESTINATION_NUMBER` | All | The phone number to dial in E.164 format |
| `CALLBACK_URL` | 02, 03, 04, 05 | Your publicly accessible server URL (e.g. from ngrok) |
| `WS_ENDPOINT` | 03 | Your WebSocket endpoint URL (e.g. `wss://abc.ngrok-free.app`) |
| `STORAGE_DESTINATION_URL` | 04 | Cloud storage bucket path (e.g. `s3://my-bucket/recordings/`) |
| `STORAGE_CREDENTIALS` | 04 | Storage access credentials (`ACCESS_KEY:SECRET:REGION` for AWS) |

---

## Common Setup: ngrok

Several tutorials require a publicly accessible HTTP server to receive Sinch webhook events. [ngrok](https://ngrok.com) creates a secure tunnel from the internet to your local machine.

### Install ngrok

```bash
# macOS (Homebrew)
brew install ngrok/ngrok/ngrok

# Linux
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# Windows
# Download from https://ngrok.com/download
```

### Authenticate

```bash
ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN
```

### Expose your local server

```bash
# Expose HTTP port 3000 for webhook servers
ngrok http 3000

# Expose WebSocket port 8765 for the WebSocket agent tutorial
ngrok http 8765
```

After running ngrok you'll see output like:

```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:3000
```

- For **webhook servers**: set `CALLBACK_URL=https://abc123.ngrok-free.app` and configure this URL in the Sinch Dashboard under your service's Call Behavior → Webhook URL.
- For **WebSocket servers**: convert `https://` → `wss://` → `WS_ENDPOINT=wss://abc123.ngrok-free.app`.

---

## Authentication

All Sinch Voice API requests use **HTTP Basic Authentication**:

- **Username**: your `KEY_ID`
- **Password**: your `KEY_SECRET`

The credentials are base64-encoded and sent in the `Authorization: Basic <base64(KEY_ID:KEY_SECRET)>` header.

In curl:
```bash
curl -u "$KEY_ID:$KEY_SECRET" https://voice.api.sinch.com/v2/projects/$PROJECT_ID/calls
```

In Python:
```python
requests.post(url, auth=(key_id, key_secret))
```

In Node.js:
```js
const authHeader = "Basic " + Buffer.from(`${keyId}:${keySecret}`).toString("base64");
fetch(url, { headers: { Authorization: authHeader } });
```

---

## Tutorial File Map

```
sinch-voice-tutorials/
├── README.md                         ← this file
├── .env.example                      ← copy to .env and fill in credentials
├── 01-tts-callout/
│   ├── description.md
│   └── scripts/
│       ├── callout.sh                curl
│       ├── callout.js                Browser fetch
│       ├── callout.node.js           Node.js fetch
│       ├── callout.py                Python requests
│       ├── callout.php               PHP curl
│       └── callout.java              Java HttpClient
├── 02-number-masking/
│   ├── description.md
│   └── scripts/
│       ├── server.node.js            Express.js webhook server
│       ├── server.py                 Flask webhook server
│       ├── server.php                Slim PHP webhook server
│       ├── Server.java               Spring Boot webhook server
│       ├── test-call.sh              curl programmatic bridge call
│       └── test-call.js              Browser JS bridge call
├── 03-websocket-agent/
│   ├── description.md
│   └── scripts/
│       ├── ws-server.node.js         Node.js WebSocket server (ws)
│       ├── ws-server.py              Python WebSocket server (websockets)
│       ├── ws-server.php             PHP WebSocket server (Ratchet)
│       ├── WsServer.java             Java WebSocket server (Tyrus)
│       ├── ice-callback.node.js      Express.js ICE callback → STREAM SVAML
│       ├── ice-callback.py           Flask ICE callback → STREAM SVAML
│       ├── trigger-call.sh           curl outbound call → stream
│       └── trigger-call.js           Browser JS outbound call → stream
├── 04-recording-transcription/
│   ├── description.md
│   └── scripts/
│       ├── server.node.js            Express.js webhook server with startRecording
│       ├── server.py                 Flask webhook server with startRecording
│       ├── server.php                Slim PHP webhook server with startRecording
│       ├── Server.java               Spring Boot webhook server with startRecording
│       ├── trigger-call.sh           curl outbound call with inline recording
│       └── trigger-call.js           Browser JS outbound call with inline recording
└── 05-amd/
    ├── description.md
    └── scripts/
        ├── amd-callout.sh            curl AMD callout
        ├── amd-callout.js            Browser JS AMD callout
        ├── amd-callout.node.js       Node.js AMD callout
        ├── amd-callout.py            Python AMD callout
        ├── amd-callout.php           PHP AMD callout
        ├── amd-callout.java          Java AMD callout
        ├── callback-server.node.js   Express.js AMD webhook server
        └── callback-server.py        Flask AMD webhook server
```

---

## Links

- [Sinch Dashboard](https://dashboard.sinch.com) — manage projects, numbers, and API keys
- [Sinch Voice API Documentation](https://developers.sinch.com/docs/voice/)
- [Sinch Voice API Reference (OpenAPI)](https://developers.sinch.com/docs/voice/api-reference/)
- [SVAML Command Reference](https://developers.sinch.com/docs/voice/api-reference/svaml)
- [Sinch Support](https://support.sinch.com)
