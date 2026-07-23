# Text-to-Speech & Available Voices

## Overview

The Sinch Voice API v2 can synthesize speech on the fly inside any call. You don't need to host audio files or run a separate TTS service -- drop a `SAY` item inside a `messages` command and Sinch generates the audio using one of its neural voices.

Three things to know about TTS in v2:

1. **`messages` is non-blocking.** The call continues executing the next SVAML command while the message plays; use `events.onFinish` if you need to act after playback completes.
2. **`SAY` and `PLAY` mix freely.** A single `messages` array can interleave TTS (`SAY`) items with `PLAY` items that point at pre-recorded MP3/WAV URLs.
3. **TEXT vs SSML.** The default `format` is `TEXT`. Set `format: "SSML"` to use prosody, breaks, emphasis, character spelling, and the rest of the SSML feature set.

## Setup

You'll need credentials and numbers from the [Sinch dashboard](https://dashboard.sinch.com). Authentication is **HTTP Basic** (`KEY_ID:KEY_SECRET`).

Export these variables before running any example:

```bash
export PROJECT_ID='your-project-id'
export KEY_ID='your-access-key-id'
export KEY_SECRET='your-access-key-secret'   # required for Basic auth -- must be present
export SINCH_NUMBER='+1...'                   # your Sinch virtual number, E.164
export DESTINATION_NUMBER='+1...'             # number you want to call, E.164
```

Note: every example in this tutorial authenticates with `KEY_ID:KEY_SECRET`. If your environment only contains a `SERVICE_ID` and no `KEY_SECRET`, the requests will fail -- add the access key secret before running.

## First success -- one SAY call you can run now

This single request dials `DESTINATION_NUMBER` and, when answered, speaks one line of TTS in the `Emma` voice, then hangs up.

### Bash

```bash
curl -s -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "commands": [
      {
        "command": "dial",
        "callName": "tts-hello",
        "from": { "type": "PHONE", "phone": { "number": "'"${SINCH_NUMBER}"'" } },
        "to":   { "type": "PHONE", "phone": { "number": "'"${DESTINATION_NUMBER}"'" } },
        "dialTimeoutDurationSeconds": 30,
        "maxCallDurationSeconds": 120,
        "events": {
          "onAnswer": [
            {
              "command": "messages",
              "messagesName": "hello",
              "messages": [
                {
                  "type": "SAY",
                  "say": {
                    "text": "Hello. This is text to speech from the Sinch Voice API.",
                    "voiceName": "Emma"
                  }
                }
              ],
              "events": { "onFinish": [ { "command": "hangup" } ] }
            }
          ],
          "onHangup": [ { "command": "hangup" } ]
        }
      }
    ]
  }'
```

### Python

```python
import os, uuid, requests

project_id = os.environ["PROJECT_ID"]
key_id     = os.environ["KEY_ID"]
key_secret = os.environ["KEY_SECRET"]

body = {
    "commands": [
        {
            "command": "dial",
            "callName": "tts-hello",
            "from": {"type": "PHONE", "phone": {"number": os.environ["SINCH_NUMBER"]}},
            "to":   {"type": "PHONE", "phone": {"number": os.environ["DESTINATION_NUMBER"]}},
            "dialTimeoutDurationSeconds": 30,
            "maxCallDurationSeconds": 120,
            "events": {
                "onAnswer": [
                    {
                        "command": "messages",
                        "messagesName": "hello",
                        "messages": [
                            {
                                "type": "SAY",
                                "say": {
                                    "text": "Hello. This is text to speech from the Sinch Voice API.",
                                    "voiceName": "Emma",
                                },
                            }
                        ],
                        "events": {"onFinish": [{"command": "hangup"}]},
                    }
                ],
                "onHangup": [{"command": "hangup"}],
            },
        }
    ]
}

resp = requests.post(
    f"https://voice.api.sinch.com/v2/projects/{project_id}/calls",
    json=body,
    auth=(key_id, key_secret),
    headers={"Idempotency-Key": str(uuid.uuid4())},
)

print(resp.status_code, resp.json())
```

### Node.js

```javascript
const https = require("https");

const projectId = process.env.PROJECT_ID;
const keyId     = process.env.KEY_ID;
const keySecret = process.env.KEY_SECRET;

const body = JSON.stringify({
  commands: [
    {
      command: "dial",
      callName: "tts-hello",
      from: { type: "PHONE", phone: { number: process.env.SINCH_NUMBER } },
      to:   { type: "PHONE", phone: { number: process.env.DESTINATION_NUMBER } },
      dialTimeoutDurationSeconds: 30,
      maxCallDurationSeconds: 120,
      events: {
        onAnswer: [
          {
            command: "messages",
            messagesName: "hello",
            messages: [
              {
                type: "SAY",
                say: {
                  text: "Hello. This is text to speech from the Sinch Voice API.",
                  voiceName: "Emma",
                },
              },
            ],
            events: { onFinish: [{ command: "hangup" }] },
          },
        ],
        onHangup: [{ command: "hangup" }],
      },
    },
  ],
});

const auth = Buffer.from(`${keyId}:${keySecret}`).toString("base64");

const req = https.request(
  `https://voice.api.sinch.com/v2/projects/${projectId}/calls`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Basic ${auth}`,
      "Idempotency-Key": crypto.randomUUID(),
    },
  },
  (res) => {
    let data = "";
    res.on("data", (chunk) => (data += chunk));
    res.on("end", () => console.log(res.statusCode, JSON.parse(data)));
  }
);

req.write(body);
req.end();
```

**What success looks like:** the API returns `201` with a JSON body containing a `callId` (and `callResourceUrl`). Your `DESTINATION_NUMBER` rings; on answer you hear "Hello. This is text to speech from the Sinch Voice API." spoken by the `Emma` voice, then the call hangs up.

## Real-life examples

- **Verification codes**: read a code character-by-character -- `Your verification code is <say-as interpret-as='characters'>4837</say-as>. Do not share this code.`
- **Multi-language alerts**: send the same notification with locale-appropriate voices based on the customer's locale. (Pick the matching `voiceName` from the live voice list -- see below.)
- **Brand voice**: choose a voice that matches your brand -- calm and slow for healthcare, upbeat for retail.
- **Dynamic pacing**: use SSML `<break time="500ms"/>` to insert deliberate pauses between key facts.

## Where TTS appears in SVAML

`SAY` is one of the two message item types in the `messages` array (`PLAY` is the other). Schema (from the spec, `messageSay`):

```yaml
messageSay:
  required: [type, say]
  additionalProperties: false
  properties:
    type: { const: SAY }
    say:
      required: [text, voiceName]
      additionalProperties: false
      properties:
        text:      { type: string }
        format:    { enum: [TEXT, SSML], default: TEXT }
        voiceName: { type: string, example: Emma }
```

The enclosing `messages` command requires `command` and `messages`; `messagesName` is optional but you need it if you later want to target the sequence with `stopMessages`.

A minimal `messages` block:

```json
{
  "command": "messages",
  "messagesName": "verification",
  "messages": [
    {
      "type": "SAY",
      "say": {
        "text": "Your verification code is 4 8 3 7.",
        "voiceName": "Emma"
      }
    }
  ],
  "events": { "onFinish": [ { "command": "hangup" } ] }
}
```

## Picking a voice

`voiceName` is the only required style knob. Sinch offers neural voices across many languages and locales.

For the complete, current list (including non-English voices and their characteristics), see the [Text-to-Speech Voices page in the Voice API docs](https://developers.sinch.com/docs/voice/api-reference/text-to-speech-voices).

## SSML -- for everything beyond plain text

Set `format: "SSML"` and wrap your text in a `<speak>` document. Commonly supported elements include `<break>`, `<prosody>`, `<emphasis>`, `<say-as>`, `<phoneme>`, and `<sub>`. (Element support can vary by voice -- verify against the voice list / SSML reference when in doubt.)

### Verification code with character-by-character spelling

```json
{
  "type": "SAY",
  "say": {
    "format": "SSML",
    "voiceName": "Emma",
    "text": "<speak>Your verification code is <say-as interpret-as='characters'>4837</say-as>. <break time='500ms'/> Do not share this code with anyone.</speak>"
  }
}
```

### Slow, calm delivery for a healthcare reminder

```json
{
  "type": "SAY",
  "say": {
    "format": "SSML",
    "voiceName": "Emma",
    "text": "<speak><prosody rate='slow' pitch='-1st'>Hello. This is a reminder that your appointment with Dr. Patel is on <break time='200ms'/> Tuesday, the third of March, at <emphasis level='moderate'>two p.m.</emphasis></prosody></speak>"
  }
}
```

### Quieter audible signature at the start

```json
{
  "type": "SAY",
  "say": {
    "format": "SSML",
    "voiceName": "Brian",
    "text": "<speak><prosody volume='-6dB'>Welcome to Acme.</prosody> How can I help you today?</speak>"
  }
}
```

## Mixing `SAY` and `PLAY`

`messages` is an ordered array. Combine recorded audio (a music sting, a brand jingle) with dynamic TTS. `PLAY` requires only a `url`:

```json
{
  "command": "messages",
  "messagesName": "intro",
  "messages": [
    { "type": "PLAY", "play": { "url": "https://example.com/audio/sting.mp3" } },
    { "type": "SAY",  "say":  { "text": "Welcome back. Please hold.", "voiceName": "Emma" } },
    { "type": "PLAY", "play": { "url": "https://example.com/audio/hold-music.mp3" } }
  ]
}
```

## Stopping TTS mid-playback

Use `stopMessages` to interrupt a sequence -- useful when a downstream event lets you skip a hold prompt. `messagesName` targets a specific sequence (if omitted, all active sequences on the call are stopped):

```json
{ "command": "stopMessages", "messagesName": "hold", "flags": "ALL_FROM_NOW_ON" }
```

`flags` choices (default is `ALL_FROM_NOW_ON`):

- `ALL_FROM_NOW_ON` -- stop the currently playing message and cancel all queued items.
- `ONLY_PLAYING` -- stop only the currently playing item; queued items continue to play.

## Events you can hook

`messages.events` (schema `messageEvents`) supports:

| Event | When it fires |
| --- | --- |
| `onFinish` | All items in the sequence have finished playing. |
| `onFailure` | Message playback failed (TTS synthesis error or a `PLAY` URL could not be fetched). If omitted, failures are silently ignored and the call flow continues. |

Common pattern -- hang up after the message:

```json
{
  "command": "messages",
  "messagesName": "vm",
  "messages": [
    { "type": "SAY", "say": { "text": "We could not reach an agent. Goodbye.", "voiceName": "Emma" } }
  ],
  "events": { "onFinish": [ { "command": "hangup" } ] }
}
```

## Full sampler -- plain TEXT, PLAY, and SSML in one call

This example dials `DESTINATION_NUMBER` and, on answer, plays three items in sequence: a plain-text `SAY`, a short `PLAY` clip, and an SSML `SAY`. Then it hangs up. Voices default to `Emma` (plain) and `Brian` (SSML); override them with environment variables if you want to compare options.

### Bash

```bash
# Override voices:  export VOICE_PLAIN=Emma  VOICE_SSML=Brian

VOICE1="${VOICE_PLAIN:-Emma}"
VOICE2="${VOICE_SSML:-Brian}"

curl -s -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen || date +%s%N)" \
  -d '{
    "commands": [
      {
        "command": "dial",
        "callName": "tts-sampler",
        "from": { "type": "PHONE", "phone": { "number": "'"${SINCH_NUMBER}"'" } },
        "to":   { "type": "PHONE", "phone": { "number": "'"${DESTINATION_NUMBER}"'" } },
        "dialTimeoutDurationSeconds": 30,
        "maxCallDurationSeconds": 120,
        "events": {
          "onAnswer": [
            {
              "command": "messages",
              "messagesName": "sampler",
              "messages": [
                {
                  "type": "SAY",
                  "say": {
                    "text": "Hello, this is a plain text message with the '"${VOICE1}"' voice.",
                    "voiceName": "'"${VOICE1}"'"
                  }
                },
                {
                  "type": "PLAY",
                  "play": { "url": "https://samplelib.com/mp3/sample-3s.mp3" }
                },
                {
                  "type": "SAY",
                  "say": {
                    "format": "SSML",
                    "voiceName": "'"${VOICE2}"'",
                    "text": "<speak><prosody rate='"'"'slow'"'"'>Now hear an S S M L example. Your code is <say-as interpret-as='"'"'characters'"'"'>4837</say-as>.</prosody><break time='"'"'400ms'"'"'/>Goodbye.</speak>"
                  }
                }
              ],
              "events": { "onFinish": [ { "command": "hangup" } ] }
            }
          ],
          "onHangup": [ { "command": "hangup" } ]
        }
      }
    ]
  }'
```

### Python

```python
import os, uuid, requests

project_id = os.environ["PROJECT_ID"]
key_id     = os.environ["KEY_ID"]
key_secret = os.environ["KEY_SECRET"]

# Override voices:  export VOICE_PLAIN=Emma  VOICE_SSML=Brian
voice_plain = os.environ.get("VOICE_PLAIN", "Emma")
voice_ssml  = os.environ.get("VOICE_SSML", "Brian")

body = {
    "commands": [
        {
            "command": "dial",
            "callName": "tts-sampler",
            "from": {"type": "PHONE", "phone": {"number": os.environ["SINCH_NUMBER"]}},
            "to":   {"type": "PHONE", "phone": {"number": os.environ["DESTINATION_NUMBER"]}},
            "dialTimeoutDurationSeconds": 30,
            "maxCallDurationSeconds": 120,
            "events": {
                "onAnswer": [
                    {
                        "command": "messages",
                        "messagesName": "sampler",
                        "messages": [
                            {
                                "type": "SAY",
                                "say": {
                                    "text": f"Hello, this is a plain text message with the {voice_plain} voice.",
                                    "voiceName": voice_plain,
                                },
                            },
                            {
                                "type": "PLAY",
                                "play": {"url": "https://samplelib.com/mp3/sample-3s.mp3"},
                            },
                            {
                                "type": "SAY",
                                "say": {
                                    "format": "SSML",
                                    "voiceName": voice_ssml,
                                    "text": (
                                        "<speak>"
                                        "<prosody rate='slow'>"
                                        "Now hear an S S M L example. "
                                        "Your code is <say-as interpret-as='characters'>4837</say-as>."
                                        "</prosody>"
                                        "<break time='400ms'/>"
                                        "Goodbye."
                                        "</speak>"
                                    ),
                                },
                            },
                        ],
                        "events": {"onFinish": [{"command": "hangup"}]},
                    }
                ],
                "onHangup": [{"command": "hangup"}],
            },
        }
    ]
}

resp = requests.post(
    f"https://voice.api.sinch.com/v2/projects/{project_id}/calls",
    json=body,
    auth=(key_id, key_secret),
    headers={"Idempotency-Key": str(uuid.uuid4())},
)

print(resp.status_code, resp.json())
```

### Node.js

```javascript
const https = require("https");

const projectId = process.env.PROJECT_ID;
const keyId     = process.env.KEY_ID;
const keySecret = process.env.KEY_SECRET;

// Override voices:  export VOICE_PLAIN=Emma  VOICE_SSML=Brian
const voicePlain = process.env.VOICE_PLAIN || "Emma";
const voiceSsml  = process.env.VOICE_SSML  || "Brian";

const body = JSON.stringify({
  commands: [
    {
      command: "dial",
      callName: "tts-sampler",
      from: { type: "PHONE", phone: { number: process.env.SINCH_NUMBER } },
      to:   { type: "PHONE", phone: { number: process.env.DESTINATION_NUMBER } },
      dialTimeoutDurationSeconds: 30,
      maxCallDurationSeconds: 120,
      events: {
        onAnswer: [
          {
            command: "messages",
            messagesName: "sampler",
            messages: [
              {
                type: "SAY",
                say: {
                  text: `Hello, this is a plain text message with the ${voicePlain} voice.`,
                  voiceName: voicePlain,
                },
              },
              {
                type: "PLAY",
                play: { url: "https://samplelib.com/mp3/sample-3s.mp3" },
              },
              {
                type: "SAY",
                say: {
                  format: "SSML",
                  voiceName: voiceSsml,
                  text:
                    "<speak>" +
                    "<prosody rate='slow'>" +
                    "Now hear an S S M L example. " +
                    "Your code is <say-as interpret-as='characters'>4837</say-as>." +
                    "</prosody>" +
                    "<break time='400ms'/>" +
                    "Goodbye." +
                    "</speak>",
                },
              },
            ],
            events: { onFinish: [{ command: "hangup" }] },
          },
        ],
        onHangup: [{ command: "hangup" }],
      },
    },
  ],
});

const auth = Buffer.from(`${keyId}:${keySecret}`).toString("base64");

const req = https.request(
  `https://voice.api.sinch.com/v2/projects/${projectId}/calls`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Basic ${auth}`,
      "Idempotency-Key": crypto.randomUUID(),
    },
  },
  (res) => {
    let data = "";
    res.on("data", (chunk) => (data += chunk));
    res.on("end", () => console.log(res.statusCode, JSON.parse(data)));
  }
);

req.write(body);
req.end();
```

**What success looks like:** the API returns `201`. Your phone rings; on answer you hear the plain-text message in the `VOICE_PLAIN` voice, then a short audio clip, then the SSML message in the `VOICE_SSML` voice, followed by an automatic hangup.