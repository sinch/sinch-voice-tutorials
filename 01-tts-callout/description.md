# Voice Callout (Audio Playback & Text-to-Speech)

## Overview

The Sinch Voice API lets you programmatically dial any phone number and play audio when the recipient answers. The call flow is defined entirely with SVAML (Sinch Voice Application Markup Language) commands sent inline with the API request — no callback server is needed. When all messages finish playing, the call is automatically hung up.

SVAML supports two message types for in-call audio:

- **`PLAY`** — streams a pre-recorded audio file from a public URL (MP3, WAV, etc.). No server-side synthesis — just point to your file.
- **`SAY`** — synthesizes speech on the fly from a text string using a named neural voice (e.g. `"Emma"`). Supports plain text and SSML markup for prosody control.

The `messages` array accepts any combination of `PLAY` and `SAY` entries, played back sequentially in order.

## Real-life examples

- **Appointment reminders**: "Hello, this is a reminder that your dentist appointment is tomorrow at 2 PM."
- **One-time passcodes (OTP)**: "Your verification code is 4 8 3 7. Do not share this code with anyone."
- **Delivery notifications**: "Your package has arrived at the locker. Your pickup code is 1 2 3 4."
- **Outage alerts**: "We are experiencing a service disruption in your area. Our team is working on a fix."

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project and API credentials (Key ID + Key Secret).
- A Sinch virtual phone number assigned to your project (used as the caller ID).
- The destination number you want to call (E.164 format, e.g. `+14155551234`).
- For shell/Python/Node.js scripts: the `.env` file filled in with your credentials (copy `.env.example` at the project root).

## Step-by-step instructions

### 1. Copy and fill in credentials

```bash
cp ../../.env.example ../../.env
# Edit .env and set PROJECT_ID, KEY_ID, KEY_SECRET, SINCH_NUMBER, DESTINATION_NUMBER
```

### 2. Understand the SVAML payload

The request body sent to `POST /v2/projects/{projectId}/calls` is:

```json
{
  "commands": [
    {
      "command": "dial",
      "name": "notification",
      "from": {
        "type": "PHONE",
        "phone": { "number": "+1XXXXXXXXXX" }
      },
      "to": {
        "type": "PHONE",
        "phone": { "number": "+1YYYYYYYYYY" }
      },
      "dialTimeout": "30s",
      "maxDuration": "5m",
      "events": {
        "onAnswer": [
          {
            "command": "messages",
            "name": "notification",
            "messages": [
              {
                "type": "PLAY",
                "play": {
                  "url": "https://samplelib.com/mp3/sample-12s.mp3"
                }
              },
              {
                "type": "SAY",
                "say": {
                  "text": "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                  "voiceName": "Emma"
                }
              }
            ],
            "events": {
              "onFinish": [
                { "command": "hangup" }
              ]
            }
          }
        ]
      }
    }
  ]
}
```

Key fields:
- `from` — your Sinch virtual number (shown as caller ID).
- `to` — the destination phone number.
- `dialTimeout` — how long to wait for the recipient to answer (e.g., `30s`).
- `maxDuration` — maximum allowed call duration.
- `events.onAnswer` — SVAML commands to execute once the call is answered.
- `command: "messages"` — plays one or more messages in sequence.
- `type: "PLAY"` — streams a pre-recorded audio file; `play.url` is the public URL of the file.
- `type: "SAY"` — synthesizes speech from text; `say.text` is the message and `say.voiceName` selects the neural voice.
- `events.onFinish` + `hangup` — ends the call after all messages have played.

### 3. Run the script

Pick the language of your choice from the `scripts/` folder:

```bash
# Shell (curl)
bash scripts/callout.sh

# Python
python scripts/callout.py

# Node.js
node scripts/callout.node.js
```

### 4. Check the response

A successful response (`HTTP 201`) returns:

```json
{
  "projectId": "...",
  "serviceId": "...",
  "sessionId": "..."
}
```

The `sessionId` can be used to fetch session details via `GET /v2/projects/{projectId}/sessions/{sessionId}`.

### 5. Customise the messages

**Swap the audio file** — replace `play.url` with any publicly accessible MP3 or WAV:

```json
{ "type": "PLAY", "play": { "url": "https://example.com/your-audio.mp3" } }
```

**Change the TTS voice or text** — update `say.text` and `say.voiceName` (e.g. `"Brian"`, `"Joanna"`):

```json
{ "type": "SAY", "say": { "text": "Your package has arrived.", "voiceName": "Brian" } }
```

**Reorder or remove messages** — `messages` is a plain array; add, remove, or reorder entries freely:

```json
"messages": [
  { "type": "SAY", "say": { "text": "Welcome.", "voiceName": "Emma" } },
  { "type": "PLAY", "play": { "url": "https://example.com/hold-music.mp3" } }
]
```

**Advanced TTS prosody** — use SSML by setting `format: "SSML"` on a `SAY` message:

```json
{
  "type": "SAY",
  "say": {
    "text": "<speak><prosody rate='slow'>Your code is <say-as interpret-as='characters'>4837</say-as></prosody></speak>",
    "format": "SSML",
    "voiceName": "Emma"
  }
}
```
