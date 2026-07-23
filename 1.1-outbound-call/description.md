# Make an Outbound Call

## Overview

The Sinch Voice API lets you programmatically dial any phone number from your project. You issue a single `POST /v2/projects/{projectId}/calls` request carrying SVAML (Sinch Voice Application Markup Language) commands that describe what happens during the call. For example: dial a phone number and, once the call is answered, play a recorded audio file, synthesize a Text-to-Speech message, then hang up.

The simplest outbound call is a single `dial` command with an `onAnswer` event that plays a `messages` block. No webhook server is needed because the full call flow is included inline in the request.

## What you'll build

In under five minutes you'll place a real outbound call that plays an audio clip and a Text-to-Speech message to a phone you control, then hangs up. You'll see an `HTTP 201` response carrying a `sessionId` you can later use to track the call.

## Real-life examples

- **Appointment reminders**: "Hello, this is a reminder that your dentist appointment is tomorrow at 2 PM."
- **One-time passcodes (OTP)**: "Your verification code is 4 8 3 7. Do not share this code with anyone."
- **Delivery notifications**: "Your package has arrived at the locker. Your pickup code is 1 2 3 4."
- **Outage alerts**: "We are experiencing a service disruption in your area."

## Setup

Before running anything, gather these values. You'll set them as environment variables with `export` (covered in the next section).

| Variable | Where to find it |
| --- | --- |
| `PROJECT_ID` | Your Sinch project UUID, shown in the [Sinch dashboard](https://dashboard.sinch.com). |
| `KEY_ID` | API key ID. Create a key pair under **Settings -> Access Keys** in the dashboard. Used as the Basic Auth username. |
| `KEY_SECRET` | API key secret, shown once when you create the key pair. Used as the Basic Auth password. |
| `SINCH_NUMBER` | A Sinch virtual phone number assigned to your project, in E.164 format (e.g. `+14045001000`). Provision one under **Numbers** in the dashboard. Used as the caller ID. |
| `DESTINATION_NUMBER` | The number you want to call, in E.164 format (e.g. `+14155551234`). For your first test, use a phone you can answer. |

Authentication is HTTP Basic using `KEY_ID:KEY_SECRET`. The API base URL is `https://voice.api.sinch.com` (regional hosts such as `https://us1.voice.api.sinch.com`, `eu1`, `br1`, `sg1`, and `au1` are also available).

**Tooling per language:**

- **Shell**: `curl` (and optionally `jq` for pretty output).
- **Python**: `pip install requests`.
- **Node.js**: Node 18+ (built-in `fetch`); no dependencies. Run as an ES module (`"type": "module"` in `package.json`, or use a `.mjs` extension). On Node < 18, `npm install node-fetch`.
- **PHP**: PHP 8+ with the `curl` extension.
- **Java**: JDK 11+ (uses `java.net.http.HttpClient`); no external dependencies.

## First success: place a call now

### 1. Export your credentials

Each example reads its configuration from environment variables. Set them once in your shell with `export`. Because `export` marks the variables for the environment, any program you launch from that same shell (Python, Node, PHP, Java, or `curl`) inherits them automatically.

```bash
export PROJECT_ID="your-project-uuid"
export KEY_ID="your-key-id"
export KEY_SECRET="your-key-secret"
export SINCH_NUMBER="+14045001000"
export DESTINATION_NUMBER="+14155551234"
```

These last only for the current shell session. Open a new terminal and you'll need to export them again. To make them persistent, add the lines to your shell profile (`~/.bashrc`, `~/.zshrc`, or similar). On Windows PowerShell, use `$env:PROJECT_ID = "..."` instead.

Verify they're set before continuing:

```bash
echo "$PROJECT_ID $SINCH_NUMBER $DESTINATION_NUMBER"
```

### 2. Place the call (pick your language)

Run any of the examples below from the same shell where you exported the variables.

#### Shell (curl)

Paste this directly into your terminal, or save it as `callout.sh` and run `bash callout.sh`.

```bash
#!/bin/bash
set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set. Run: export PROJECT_ID=...}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"

echo "Placing callout from ${SINCH_NUMBER} to ${DESTINATION_NUMBER} ..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "commands": [
    {
      "command": "dial",
      "callName": "audio-notification",
      "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
      "to":   { "type": "PHONE", "phone": { "number": "${DESTINATION_NUMBER}" } },
      "dialTimeoutDurationSeconds": 30,
      "maxCallDurationSeconds": 300,
      "events": {
        "onAnswer": [
          {
            "command": "messages",
            "messagesName": "notification",
            "messages": [
              { "type": "PLAY", "play": { "url": "https://samplelib.com/mp3/sample-12s.mp3" } },
              { "type": "SAY",  "say": {
                  "text": "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                  "voiceName": "Emma"
              } }
            ],
            "events": { "onFinish": [ { "command": "hangup" } ] }
          }
        ]
      }
    }
  ]
}
EOF
)

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 201 ]; then
  echo "Call created successfully (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
```

#### Python

Save as `callout.py`, then run `python callout.py`.

```python
# Requirements: pip install requests
import json
import os
import sys

import requests


def env(name):
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: {name} is not set. Run: export {name}=...", file=sys.stderr)
        sys.exit(1)
    return value


project_id         = env("PROJECT_ID")
key_id             = env("KEY_ID")
key_secret         = env("KEY_SECRET")
sinch_number       = env("SINCH_NUMBER")
destination_number = env("DESTINATION_NUMBER")

url = f"https://voice.api.sinch.com/v2/projects/{project_id}/calls"

# SVAML payload: dial -> on answer play audio file then TTS -> hangup
payload = {
    "commands": [
        {
            "command": "dial",
            "callName": "audio-notification",
            "from": {"type": "PHONE", "phone": {"number": sinch_number}},
            "to":   {"type": "PHONE", "phone": {"number": destination_number}},
            "dialTimeoutDurationSeconds": 30,
            "maxCallDurationSeconds": 300,
            "events": {
                "onAnswer": [
                    {
                        "command": "messages",
                        "messagesName": "notification",
                        "messages": [
                            {"type": "PLAY", "play": {"url": "https://samplelib.com/mp3/sample-12s.mp3"}},
                            {"type": "SAY", "say": {
                                "text": "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                                "voiceName": "Emma",
                            }},
                        ],
                        "events": {"onFinish": [{"command": "hangup"}]},
                    }
                ]
            },
        }
    ]
}

print(f"Placing callout from {sinch_number} to {destination_number} ...")

try:
    response = requests.post(url, json=payload, auth=(key_id, key_secret))
    data = response.json()

    if response.status_code == 201:
        print("Call created successfully:")
        print(json.dumps(data, indent=2))
    else:
        print(f"ERROR {response.status_code}:", file=sys.stderr)
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)
except requests.RequestException as e:
    print(f"Request failed: {e}", file=sys.stderr)
    sys.exit(1)
```

#### Node.js

Save as `callout.mjs` (the `.mjs` extension enables ES module syntax), then run `node callout.mjs`. Uses the built-in `fetch` from Node 18+; no dependencies.

```javascript
function env(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`ERROR: ${name} is not set. Run: export ${name}=...`);
    process.exit(1);
  }
  return value;
}

const projectId         = env("PROJECT_ID");
const keyId             = env("KEY_ID");
const keySecret         = env("KEY_SECRET");
const sinchNumber       = env("SINCH_NUMBER");
const destinationNumber = env("DESTINATION_NUMBER");

const url = `https://voice.api.sinch.com/v2/projects/${projectId}/calls`;

// Basic Auth: base64("keyId:keySecret")
const authHeader = "Basic " + Buffer.from(`${keyId}:${keySecret}`).toString("base64");

// SVAML payload: dial -> on answer play audio file then TTS -> hangup
const payload = {
  commands: [
    {
      command: "dial",
      callName: "audio-notification",
      from: { type: "PHONE", phone: { number: sinchNumber } },
      to:   { type: "PHONE", phone: { number: destinationNumber } },
      dialTimeoutDurationSeconds: 30,
      maxCallDurationSeconds: 300,
      events: {
        onAnswer: [
          {
            command: "messages",
            messagesName: "notification",
            messages: [
              { type: "PLAY", play: { url: "https://samplelib.com/mp3/sample-12s.mp3" } },
              { type: "SAY", say: {
                  text: "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                  voiceName: "Emma",
              } },
            ],
            events: { onFinish: [ { command: "hangup" } ] },
          },
        ],
      },
    },
  ],
};

console.log(`Placing callout from ${sinchNumber} to ${destinationNumber} ...`);

const response = await fetch(url, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: authHeader },
  body: JSON.stringify(payload),
});

const data = await response.json();

if (response.status === 201) {
  console.log("Call created successfully:", JSON.stringify(data, null, 2));
} else {
  console.error(`ERROR ${response.status}:`, JSON.stringify(data, null, 2));
  process.exit(1);
}
```

#### PHP

Save as `callout.php`, then run `php callout.php`. Requires PHP 8+ with the `curl` extension.

```php
<?php
// Requirements: PHP 8+ with the curl extension enabled.

function env(string $name): string {
    $value = getenv($name);
    if ($value === false || $value === '') {
        fwrite(STDERR, "ERROR: {$name} is not set. Run: export {$name}=...\n");
        exit(1);
    }
    return $value;
}

$projectId         = env('PROJECT_ID');
$keyId             = env('KEY_ID');
$keySecret         = env('KEY_SECRET');
$sinchNumber       = env('SINCH_NUMBER');
$destinationNumber = env('DESTINATION_NUMBER');

$url = "https://voice.api.sinch.com/v2/projects/{$projectId}/calls";

// SVAML payload: dial -> on answer play audio file then TTS -> hangup
$payload = [
    'commands' => [
        [
            'command'  => 'dial',
            'callName' => 'audio-notification',
            'from'     => ['type' => 'PHONE', 'phone' => ['number' => $sinchNumber]],
            'to'       => ['type' => 'PHONE', 'phone' => ['number' => $destinationNumber]],
            'dialTimeoutDurationSeconds' => 30,
            'maxCallDurationSeconds'     => 300,
            'events' => [
                'onAnswer' => [
                    [
                        'command'      => 'messages',
                        'messagesName' => 'notification',
                        'messages' => [
                            ['type' => 'PLAY', 'play' => ['url' => 'https://samplelib.com/mp3/sample-12s.mp3']],
                            ['type' => 'SAY',  'say'  => [
                                'text'      => 'Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.',
                                'voiceName' => 'Emma',
                            ]],
                        ],
                        'events' => ['onFinish' => [['command' => 'hangup']]],
                    ],
                ],
            ],
        ],
    ],
];

echo "Placing callout from {$sinchNumber} to {$destinationNumber} ...\n";

$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
    CURLOPT_USERPWD        => "{$keyId}:{$keySecret}",
    CURLOPT_POSTFIELDS     => json_encode($payload),
    CURLOPT_RETURNTRANSFER => true,
]);

$responseBody = curl_exec($ch);
$httpCode     = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curlError    = curl_error($ch);
curl_close($ch);

if ($curlError) {
    fwrite(STDERR, "curl error: {$curlError}\n");
    exit(1);
}

$data = json_decode($responseBody, true);

if ($httpCode === 201) {
    echo "Call created successfully:\n";
    echo json_encode($data, JSON_PRETTY_PRINT) . "\n";
} else {
    fwrite(STDERR, "ERROR {$httpCode}:\n");
    fwrite(STDERR, json_encode($data, JSON_PRETTY_PRINT) . "\n");
    exit(1);
}
```

#### Java

Save as `Callout.java`, then compile and run:

```bash
javac -d out Callout.java && java -cp out com.sinch.tutorials.ttscallout.Callout
```

Requires JDK 11+ (uses `java.net.http.HttpClient`); no external dependencies.

```java
package com.sinch.tutorials.ttscallout;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Base64;

public class Callout {

    public static void main(String[] args) throws Exception {
        String projectId         = requireEnv("PROJECT_ID");
        String keyId             = requireEnv("KEY_ID");
        String keySecret         = requireEnv("KEY_SECRET");
        String sinchNumber       = requireEnv("SINCH_NUMBER");
        String destinationNumber = requireEnv("DESTINATION_NUMBER");

        String url = "https://voice.api.sinch.com/v2/projects/" + projectId + "/calls";

        // Basic Auth header: base64("keyId:keySecret")
        String credentials = Base64.getEncoder()
                .encodeToString((keyId + ":" + keySecret).getBytes());

        // SVAML payload: dial -> on answer play audio file then TTS -> hangup
        String body = String.format("""
            {
              "commands": [
                {
                  "command": "dial",
                  "callName": "audio-notification",
                  "from": { "type": "PHONE", "phone": { "number": "%s" } },
                  "to":   { "type": "PHONE", "phone": { "number": "%s" } },
                  "dialTimeoutDurationSeconds": 30,
                  "maxCallDurationSeconds": 300,
                  "events": {
                    "onAnswer": [
                      {
                        "command": "messages",
                        "messagesName": "notification",
                        "messages": [
                          { "type": "PLAY", "play": { "url": "https://samplelib.com/mp3/sample-12s.mp3" } },
                          { "type": "SAY",  "say": {
                              "text": "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                              "voiceName": "Emma"
                          } }
                        ],
                        "events": { "onFinish": [ { "command": "hangup" } ] }
                      }
                    ]
                  }
                }
              ]
            }
            """, sinchNumber, destinationNumber);

        System.out.println("Placing callout from " + sinchNumber + " to " + destinationNumber + " ...");

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .header("Authorization", "Basic " + credentials)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() == 201) {
            System.out.println("Call created successfully:");
            System.out.println(response.body());
        } else {
            System.err.println("ERROR " + response.statusCode() + ":");
            System.err.println(response.body());
            System.exit(1);
        }
    }

    // Reads a variable from the environment (set it with `export NAME=...`).
    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            System.err.println("ERROR: " + name + " is not set. Run: export " + name + "=...");
            System.exit(1);
        }
        return value;
    }
}
```

> Browser note: a browser `fetch` version is also possible, but browsers have no environment variables, so `export` does not apply. You would inject the values at build time and, because calling the Sinch API directly from a browser hits CORS restrictions, route the request through your own backend proxy in production.

### 3. What success looks like

The destination phone rings. When answered, it plays the sample audio clip followed by the TTS message "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7." then hangs up.

On the console you'll see an `HTTP 201` response:

```json
{
  "projectId": "5c5bf2b1-35ae-4825-ab89-457e07bb60e6",
  "serviceId": "6e124178-c29d-46a5-943c-5c2ae544aade",
  "sessionId": "01BX5ZZKBKACTAV9WEVGEMMVRB"
}
```

If you get a non-201 status, check the [Troubleshooting](#troubleshooting) section below.

## Reference

### The SVAML payload

The request body sent to `POST /v2/projects/{projectId}/calls` is:

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "audio-notification",
      "from": {
        "type": "PHONE",
        "phone": { "number": "+1XXXXXXXXXX" }
      },
      "to": {
        "type": "PHONE",
        "phone": { "number": "+1YYYYYYYYYY" }
      },
      "dialTimeoutDurationSeconds": 30,
      "maxCallDurationSeconds": 300,
      "events": {
        "onAnswer": [
          {
            "command": "messages",
            "messagesName": "notification",
            "messages": [
              {
                "type": "PLAY",
                "play": { "url": "https://samplelib.com/mp3/sample-12s.mp3" }
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
              "onFinish": [ { "command": "hangup" } ]
            }
          }
        ]
      }
    }
  ]
}
```

Key fields (cross-referenced with the OpenAPI spec):

- `command: "dial"`: initiates a new outbound call leg. Non-blocking: the next command runs in parallel while the call is being established. Only `command` and `to` are required.
- `callName`: identifier for this call leg within the session (1 to 32 chars, no whitespace). Must be unique across active legs. Other commands (e.g. `hangup`) can reference it.
- `from`: your Sinch virtual number, used as the caller ID. Requires a `type` discriminator. Supports `PHONE` or `SIP` only. Note that `from` does **not** support `STREAM`/`VOICE_RELAY`.
- `to`: the destination. Requires a `type` discriminator: `PHONE`, `SIP`, `STREAM`, or `VOICE_RELAY`. For PSTN this is `PHONE` with an E.164 number.
- `dialTimeoutDurationSeconds`: how long to wait for the recipient to answer (integer, seconds). On expiry the `onTimeout` event fires.
- `maxCallDurationSeconds`: hard ceiling on the duration of the answered call (integer, seconds). The call is terminated automatically when reached.
- `events.onAnswer`: SVAML commands executed once the call is answered. Other call lifecycle events available on `dial`: `onBusy`, `onReject`, `onTimeout`, `onHangup`, `onFailure`.
- `command: "messages"`: non-blocking; queues one or more messages and continues. `messagesName` (1 to 32 chars, no whitespace) names the sequence so it can be targeted by `stopMessages`. Each item is `SAY` (TTS) or `PLAY` (audio URL).
- `events.onFinish` on `messages`: fires when all queued items have finished playing. Hanging up here ends the call cleanly. The `messages` command also supports `onFailure` (fires on TTS synthesis or media-fetch failure; if omitted, failures are silently ignored and the flow continues).

**Message item types** (`type` discriminator):

- `SAY`: requires `say.text` and `say.voiceName`. Optional `say.format` is `TEXT` (default) or `SSML`.
- `PLAY`: requires `play.url`, the URL of the media to play.

### Handling unanswered and failed calls

The example above only handles the happy path (`onAnswer`). A production flow should handle the other outcomes so a call that is never answered doesn't silently disappear. Add sibling handlers under the `dial` command's `events`:

```json
"events": {
  "onAnswer":  [ { "command": "messages", "messages": [ /* ... */ ] } ],
  "onTimeout": [ { "command": "hangup" } ],
  "onBusy":    [ { "command": "hangup" } ],
  "onReject":  [ { "command": "hangup" } ],
  "onFailure": [ { "command": "hangup" } ]
}
```

### Safe retries with an Idempotency-Key

`createCall` accepts an optional `Idempotency-Key` header (16 to 128 characters; a random UUID v4 is strongly recommended). If a request with the same key is received within 10 minutes, the server returns the cached response from the original request instead of placing a second call, which makes retries on network errors safe.

```bash
curl -H "Idempotency-Key: $(uuidgen)" ...
```

Because a dropped connection can leave you unsure whether a call was actually created, **generate the key once before the first attempt and reuse the same key for every retry of that call.** Generating a new key per attempt defeats the purpose.

### The response

A successful response is `HTTP 201` with body:

```json
{
  "projectId": "...",
  "serviceId": "...",
  "sessionId": "..."
}
```

For a batch of calls, the response additionally includes a `batchId`. Use the `sessionId` to inspect the call legs via `GET /v2/projects/{projectId}/sessions/{sessionId}`. See [3.6 Track Call Status](../3.6-track-call-status/description.md) for details.

### Troubleshooting

`createCall` can return these error statuses; the response body describes the problem:

| Status | Likely cause |
| --- | --- |
| `400` | Malformed SVAML (e.g. missing destination, invalid field). |
| `401` | Bad or missing Basic Auth credentials (`KEY_ID`/`KEY_SECRET`). |
| `402` | Billing/payment issue on the account. |
| `403` | Credentials valid but not authorized for this project/action. |
| `404` | Unknown `projectId`. |
| `429` | Rate limited. Back off and retry (reuse the same `Idempotency-Key`). |
| `500` | Server error. Retry with backoff. |

If a script reports that a variable is not set, confirm you exported it in the same shell you're running from. Run `echo "$PROJECT_ID"` to check, and remember that `export` does not carry over to new terminal windows unless you added it to your shell profile.

### Customise the messages

**Swap the audio file**: replace `play.url` with any publicly accessible MP3 or WAV:

```json
{ "type": "PLAY", "play": { "url": "https://example.com/your-audio.mp3" } }
```

**Change the TTS voice or text**: `voiceName` accepts values such as `Emma` and `Brian`.

**Reorder or remove messages**: `messages` is a plain array; entries play sequentially:

```json
"messages": [
  { "type": "SAY",  "say":  { "text": "Welcome.", "voiceName": "Emma" } },
  { "type": "PLAY", "play": { "url": "https://example.com/hold-music.mp3" } }
]
```