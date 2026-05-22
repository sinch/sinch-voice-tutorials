# Answering Machine Detection (AMD)

## Overview

Answering Machine Detection (AMD) lets you automatically distinguish between a live human and a voicemail machine or IVR when making outbound calls. The Sinch Voice API runs AMD analysis on the call audio after it is answered, then fires SVAML event handlers based on the detection result: `onHuman`, `onMachine`, `onBeep`, or `onUnknown`. You can define completely different call flows for each outcome — for example, immediately connecting a human to a live agent, or playing a pre-recorded voicemail message when a beep is detected. AMD is controlled by the `amd` SVAML command, which can be included inline in the call payload or returned from a webhook.

## Real-life examples

- **Outreach campaigns**: Skip unanswered calls and leave tailored voicemail messages only when a beep is detected, maximizing agent productivity.
- **Appointment reminders**: Connect to a live agent when a human answers; leave a reminder message on voicemail systems.
- **Debt collection**: Route live answer calls to a specialist; leave a callback number on answering machines.
- **Survey calls**: Only launch the survey IVR when a real human is detected; abort silently on machine answers.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with API credentials.
- A Sinch virtual phone number.
- For the callback server: a publicly accessible URL (use ngrok during development).

## Step-by-step instructions

### 1. Understand the `amd` SVAML command

The `amd` command must be placed in the `onAnswer` event of a `dial` command:

```json
{
  "command": "amd",
  "events": {
    "onHuman": [
      {
        "command": "messages",
        "name": "human-message",
        "messages": [{ "type": "SAY", "say": { "text": "Hello! Press 1 to speak to an agent.", "voiceName": "Emma" } }],
        "events": { "onFinish": [{ "command": "hangup" }] }
      }
    ],
    "onMachine": [
      { "command": "hangup" }
    ],
    "onBeep": [
      {
        "command": "messages",
        "name": "voicemail-message",
        "messages": [{ "type": "SAY", "say": { "text": "Hi, this is a reminder about your appointment tomorrow. Please call us back at 555-1234.", "voiceName": "Emma" } }],
        "events": { "onFinish": [{ "command": "hangup" }] }
      }
    ],
    "onUnknown": [
      { "command": "hangup" }
    ]
  }
}
```

AMD event types:
- `onHuman` — a live person picked up. Connect to an agent or start a conversation.
- `onMachine` — an answering machine greeting is playing (beep not yet detected). Usually hang up or wait.
- `onBeep` — a beep was detected (voicemail ready to record). Leave your voicemail message now.
- `onUnknown` — detection was inconclusive. Safe default: hang up or treat as human.

### 2. Run the callout scripts (inline AMD — no callback server needed)

```bash
bash scripts/amd-callout.sh

python scripts/amd-callout.py

node scripts/amd-callout.node.js
```

### 3. Run the callback server (dynamic AMD via webhook)

For more dynamic control, configure your Sinch service with a webhook URL. The callback server receives the `call.incoming` or answer event, then responds with SVAML including the `amd` command:

```bash
node scripts/callback-server.node.js
python scripts/callback-server.py
```

### 4. Tips for AMD accuracy

- Allow `dialTimeout` of at least `30s` — machines may take a few seconds to answer.
- The `amd` command should be the first command in `onAnswer` — do not play messages before AMD runs.
- If you want to play music or hold tones during AMD analysis, use a separate call leg.
- `onBeep` is the right moment to start your voicemail message — not `onMachine`.
