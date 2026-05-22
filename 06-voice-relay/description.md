# Connect Inbound Calls to an AI Chatbot via Voice Relay

## Overview

The Sinch Voice API's **Voice Relay** destination type lets you connect a live phone call to a WebSocket server that speaks a simple text-in/text-out protocol. Unlike the raw PCM streaming in tutorial 03, Voice Relay handles speech-to-text and text-to-speech on the Sinch side — your server only sends and receives plain text. This makes it straightforward to wire a language model into a real phone call: the caller speaks, Sinch transcribes, your server asks the LLM, and Sinch reads the reply back in a natural TTS voice.

This tutorial configures the call behavior as a **Static** rule on the Sinch dashboard, so no webhook server is required for call setup. When someone dials your Sinch number, the platform immediately accepts the call, dials a Voice Relay leg pointing at your WebSocket server, and bridges the two legs together. Your Python server connects to LangChain and can be backed by OpenAI, Anthropic Claude, or Google Gemini.

## Real-life examples

- **AI receptionist**: Answer inbound calls 24/7, handle FAQs, and route or escalate based on the conversation.
- **Product demo bot**: Let prospects call a number and interact with an AI that explains your product — no sales rep required.
- **Internal helpdesk**: Staff call a number to ask an LLM questions about internal tools, runbooks, or HR policies.
- **Voice-first prototyping**: Quickly validate a conversational AI design over a real phone call before building a full IVR.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project, API credentials, and a virtual phone number.
- A publicly accessible WebSocket endpoint. Use [ngrok](https://ngrok.com) during development:
  ```bash
  ngrok http 8765    # exposes ws://localhost:8765 as wss://<id>.ngrok-free.app
  ```
- Python 3.10+ with dependencies from `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```
  This installs `websockets`, `python-dotenv`, `langchain-core`, and all three provider packages (`langchain-openai`, `langchain-anthropic`, `langchain-google-genai`). Only the one matching your `PROVIDER` setting is actually used at runtime.
- An API key for your chosen LLM provider.

## Step-by-step instructions

### 1. Configure the Static call behavior on the Sinch dashboard

Rather than running a webhook server to handle the incoming call event, this tutorial uses a **Static** call behavior — a fixed SVAML response that the platform applies automatically to every inbound call.

In the [Sinch Dashboard](https://dashboard.sinch.com/voice/services), set your service's **Call Behavior** to `STATIC` and paste the contents of `static.txt`:

```json
{
  "command": "accept",
  "commands": [
    {
      "command": "answer"
    },
    {
      "command": "bridgeCall",
      "name": "main-bridge"
    },
    {
      "command": "dial",
      "name": "voice_relay_call",
      "to": {
        "type": "VOICE_RELAY",
        "voiceRelay": {
          "endpoint": "wss://<your-ngrok-id>.ngrok-free.app",
          "ttsVoice": "Emma",
          "sttLanguage": "en-US"
        }
      },
      "events": {
        "onAnswer": [
          {
            "command": "bridgeCall",
            "name": "main-bridge"
          }
        ]
      }
    }
  ],
  "events": {
    "onHangup": [
      {
        "command": "hangup",
        "callName": "voice_relay_call"
      }
    ]
  }
}
```

Replace the `endpoint` value with your current ngrok URL. The `ttsVoice` and `sttLanguage` fields control the voice and language Sinch uses for TTS/STT on the relay leg.

### 2. Configure your environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Set `PROVIDER` to `openai`, `claude`, or `gemini`, and set `API_KEY` to the corresponding key. Optionally override `MODEL`, `TEMPERATURE`, `MAX_TOKENS`, and `PORT`.

### 3. Start the WebSocket server

```bash
python server.py
```

The server listens on port `8765` by default. On startup it logs the active provider, model, and loaded system prompt.

### 4. Expose your server with ngrok

```bash
ngrok http 8765
```

Copy the Forwarding URL (e.g. `https://abc123.ngrok-free.app`) and update the `endpoint` in your Static call behavior on the dashboard. Use the plain `ws://` or `wss://` form:

```
wss://abc123.ngrok-free.app
```

### 5. How the Voice Relay protocol works

Once the bridge is established, Sinch opens a WebSocket connection to your server and exchanges JSON messages:

| Direction | Command | Description |
|-----------|---------|-------------|
| Sinch → Server | `connect` | Session start; carries `callId`, `serviceId`, metadata |
| Server → Sinch | `answer` | Accept the relay session |
| Server → Sinch | `text` + `isLast: true` | Send TTS text to be read to the caller |
| Sinch → Server | `text` / `prompt` | Transcribed speech from the caller |
| Sinch → Server | `interrupt` | Caller spoke while TTS was playing |
| Sinch → Server | `dtmf` | Keypad digits pressed by the caller |
| Sinch → Server | `textPlaybackStart/Stop/Cancel` | TTS playback lifecycle events |

Your server never handles raw audio — Sinch's STT turns speech into text before it arrives, and your text replies are converted to speech by Sinch's TTS engine before reaching the caller.

### 6. How the agent handles a turn

On each `connect` event the server sends `answer` and then an optional greeting message. On each `text`/`prompt` event:

1. The transcribed user text is appended to the in-memory conversation history.
2. The full history (plus the system prompt from `system_prompt.md`) is sent to the LLM via LangChain.
3. The LLM reply is sent back as a `{"command": "text", "text": "...", "isLast": true}` message.
4. The reply is appended to history so subsequent turns maintain context.

The conversation history is per-connection and lives in memory — it resets when the call ends.

### 7. Customise the agent

Edit `system_prompt.md` to change the agent's persona, knowledge domain, and behaviour. The file is loaded at server startup. The default persona is **RELAY**, a Sinch demo agent with a fondness for telecom dad jokes.

To swap LLM providers without restarting, change `PROVIDER` and `API_KEY` in `.env` and restart the server.
