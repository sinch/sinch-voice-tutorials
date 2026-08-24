# Record Calls & Transcribe Audio

## Overview

The Voice API v2 can record a call and upload the audio file directly to your own cloud storage bucket (AWS S3, Google Cloud Storage, or Azure Blob Storage) as soon as the recording stops. Optionally it can also transcribe the recording to text and deliver a transcript file alongside the audio. Recording is controlled by the `startRecording` and `stopRecording` SVAML commands, which you can include inline in an outbound call payload or return from a webhook for inbound calls.

You specify the destination provider, the storage credentials, the recording format (`MP3` or `WAV`), the recording direction (`COMBINED` / `INBOUND` / `OUTBOUND`), and whether transcription is enabled.

> **Heads-up: recording needs storage configured before anything works.** Unlike most tutorials in this series, you cannot see a useful result until a real bucket and credentials exist, because Sinch uploads straight to your storage. Budget 10 to 15 minutes for the AWS setup in [Setup](#setup) before you run anything. Once that is done, the first-success path below is a single script.

## Real-life examples

- **Compliance and quality assurance**: Record all customer service calls and store them in S3 for regulatory review.
- **Sales coaching**: Record sales calls, transcribe them, and feed the transcripts into an AI coaching tool.
- **Dispute resolution**: Maintain an auditable record of conversations for insurance claims or legal disputes.
- **Inbound-only recording**: Capture only the caller's audio (consent reasons) by setting `recordingType: INBOUND`.

## Setup

This tutorial reads its configuration from environment variables. Export them in the shell session you will run the examples from. Exports last for the current shell only, so re-export them (or add them to your shell profile) if you open a new terminal.

### 1. Sinch credentials

You need a [Sinch account](https://dashboard.sinch.com), a Voice-enabled virtual number, and an API key. Export them:

```bash
export PROJECT_ID=your-project-id
export KEY_ID=your-key-id
export KEY_SECRET=your-key-secret
export SINCH_NUMBER=+1XXXXXXXXXX          # your Sinch virtual number, E.164
export DESTINATION_NUMBER=+1YYYYYYYYYY    # the number to call (for the outbound trigger)
```

Auth to the Voice API is **HTTP Basic** with `KEY_ID:KEY_SECRET`.

### 2. Storage bucket + credentials (the part that takes the most time)

Recording uploads go to **your** bucket, so you must create one and a write-scoped credential. AWS S3 is the recommended/headline path for this tutorial. It is the spec default (`destination: AWS`) and has the simplest credential format. GCS and Azure are covered under [Other storage providers](#other-storage-providers).

**AWS S3 (recommended):**

1. Create an S3 bucket, e.g. `my-voice-recordings`, in a region you control (e.g. `eu-central-1`).
2. Create an IAM user with programmatic access and a policy granting at least `s3:PutObject` on `arn:aws:s3:::my-voice-recordings/*`. Grant the minimum, and do not attach full S3 access.
3. Copy the **Access key ID** and **Secret access key**.

Then export both storage variables:

```bash
export STORAGE_DESTINATION_URL=s3://my-voice-recordings/recordings/
export STORAGE_CREDENTIALS=AKIAIOSFODNN7EXAMPLE:wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY:eu-central-1
```

The credential format for AWS is exactly **`ACCESS_KEY:SECRET_KEY:REGION`**, three colon-separated fields. This is the same format the spec uses in its `recordingOptions` example (`accessKeyId:secretAccessKey:eu-central-1`). The examples in this tutorial **infer the provider from the URL scheme**: `s3://` maps to `AWS`, `gs://` maps to `GCP`, anything else maps to `AZURE`. So set `STORAGE_DESTINATION_URL` to match your provider and the `destination` field is filled in for you.

### 3. (Inbound only) a public callback URL

The outbound trigger does **not** need a public URL. The webhook servers do, because Sinch must reach them. Expose your local server with ngrok and export:

```bash
export CALLBACK_URL=https://your-ngrok-url.ngrok-free.app
export PORT=8081
```

Configure the `CALLBACK_URL` as your service's webhook in the Sinch dashboard. See [2.1 Handle Inbound PSTN Calls](../2.1-inbound-pstn/description.md) for the full inbound webhook contract (CloudEvents headers, body shape, signature verification).

## First success: record one outbound call (fastest path)

Once you have exported the Sinch credentials, `SINCH_NUMBER`, `DESTINATION_NUMBER`, `STORAGE_DESTINATION_URL`, and `STORAGE_CREDENTIALS`, save the script below as `trigger-call.sh` and run `bash trigger-call.sh`:

```bash
#!/bin/bash
# Sinch Recording & Transcription: trigger an outbound call with inline recording SVAML.
# The call is recorded immediately when answered; the file is uploaded to cloud storage.

set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"
: "${STORAGE_DESTINATION_URL:?ERROR: STORAGE_DESTINATION_URL is not set (e.g. s3://my-bucket/recordings/).}"
: "${STORAGE_CREDENTIALS:?ERROR: STORAGE_CREDENTIALS is not set (e.g. ACCESS_KEY:SECRET:REGION).}"

# Detect storage provider from the destination URL prefix
if echo "${STORAGE_DESTINATION_URL}" | grep -q "^s3://"; then
  STORAGE_DESTINATION="AWS"
elif echo "${STORAGE_DESTINATION_URL}" | grep -q "^gs://"; then
  STORAGE_DESTINATION="GCP"
else
  STORAGE_DESTINATION="AZURE"
fi

BASE_URL="https://voice.api.sinch.com/v2"

echo "Calling ${DESTINATION_NUMBER} with recording enabled (${STORAGE_DESTINATION}) ..."

BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "callName": "recorded-call",
      "from": { "type": "PHONE", "phone": { "number": "%s" } },
      "to":   { "type": "PHONE", "phone": { "number": "%s" } },
      "dialTimeoutDurationSeconds": 30,
      "maxCallDurationSeconds": 3600,
      "events": {
        "onAnswer": [
          {
            "command": "startRecording",
            "recordingName": "main-recording",
            "recordingOptions": {
              "format": "MP3",
              "recordingType": "COMBINED",
              "destination": "%s",
              "destinationUrl": "%s",
              "credentials": "%s",
              "transcriptionOptions": { "isEnabled": true, "locale": "en-US" }
            }
          },
          {
            "command": "messages",
            "messagesName": "recording-notice",
            "messages": [
              { "type": "SAY", "say": { "text": "This call is being recorded.", "voiceName": "Emma" } }
            ]
          }
        ],
        "onHangup": [
          { "command": "stopRecording", "recordingName": "main-recording" }
        ]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${DESTINATION_NUMBER}" \
   "${STORAGE_DESTINATION}" "${STORAGE_DESTINATION_URL}" "${STORAGE_CREDENTIALS}")

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "${BASE_URL}/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -d "${BODY}")

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 201 ]; then
  echo "Call created with recording (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
  echo ""
  echo "Recording will be uploaded to: ${STORAGE_DESTINATION_URL}"
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
```

This places an outbound call to `DESTINATION_NUMBER`. The moment it is answered:

1. `startRecording` begins recording (combined audio, MP3, transcription on).
2. A short "This call is being recorded." message plays.
3. When the call ends, `stopRecording` finalizes the recording and Sinch uploads it.

**What success looks like:**

- The API returns **HTTP 201** with a call/session id (printed by the script).
- A few seconds after you hang up, an `.mp3` file appears in `s3://my-voice-recordings/recordings/`. The filename includes the call/session identifier for traceability.
- Because transcription is enabled, a JSON transcript file lands alongside the audio.

If nothing shows up in the bucket, the credentials or bucket permissions are almost certainly wrong. Recording failures are **silent by default**, so wire `events.onFailure` (see [Recording lifecycle events](#recording-lifecycle-events)) so a misconfigured bucket surfaces instead of being swallowed.

### Browser trigger (quick local testing only)

The same flow can run from the browser console. Calling the Sinch API directly from a browser hits CORS and exposes your key secret, so this is for quick local testing only. In production, proxy through your backend.

```javascript
// Sinch Recording & Transcription: browser JS to trigger an outbound call with recording.
// Note: calling the Sinch API directly from a browser will hit CORS restrictions,
// and exposes your key secret. In production, proxy these calls through your backend.

(async function sinchRecordingCall() {
  const projectId             = "YOUR_PROJECT_ID";
  const keyId                 = "YOUR_KEY_ID";
  const keySecret             = "YOUR_KEY_SECRET";
  const sinchNumber           = "+1XXXXXXXXXX";
  const destinationNumber     = "+1YYYYYYYYYY";
  const storageDestinationUrl = "s3://my-bucket/recordings/";
  const storageCredentials    = "ACCESS_KEY:SECRET_KEY:REGION";

  // Infer storage provider from the URL scheme
  const storageDestination = storageDestinationUrl.startsWith("gs://") ? "GCP"
    : storageDestinationUrl.startsWith("s3://") ? "AWS"
    : "AZURE";

  const baseUrl    = "https://voice.api.sinch.com/v2";
  const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

  const payload = {
    commands: [
      {
        command: "dial",
        callName: "recorded-call",
        from: { type: "PHONE", phone: { number: sinchNumber } },
        to:   { type: "PHONE", phone: { number: destinationNumber } },
        dialTimeoutDurationSeconds: 30,
        maxCallDurationSeconds: 3600,
        events: {
          onAnswer: [
            {
              command: "startRecording",
              recordingName: "main-recording",
              recordingOptions: {
                format: "MP3",
                recordingType: "COMBINED",
                destination: storageDestination,
                destinationUrl: storageDestinationUrl,
                credentials: storageCredentials,
                transcriptionOptions: { isEnabled: true, locale: "en-US" }
              }
            },
            {
              command: "messages",
              messagesName: "recording-notice",
              messages: [
                { type: "SAY", say: { text: "This call is being recorded.", voiceName: "Emma" } }
              ]
            }
          ],
          onHangup: [
            { command: "stopRecording", recordingName: "main-recording" }
          ]
        }
      }
    ]
  };

  console.log(`Calling ${destinationNumber} with recording enabled (${storageDestination}) ...`);

  const response = await fetch(
    `${baseUrl}/projects/${projectId}/calls`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: authHeader },
      body: JSON.stringify(payload)
    }
  );

  const data = await response.json();

  if (response.status === 201) {
    console.log("Call created with recording:", data);
    console.log("Recording will be uploaded to:", storageDestinationUrl);
  } else {
    console.error(`ERROR ${response.status}:`, data);
  }
})();
```

## The `startRecording` command

```json
{
  "command": "startRecording",
  "recordingName": "main-recording",
  "recordingOptions": {
    "format": "MP3",
    "recordingType": "COMBINED",
    "destination": "AWS",
    "destinationUrl": "s3://my-voice-recordings/recordings/",
    "credentials": "ACCESS_KEY:SECRET_KEY:REGION",
    "transcriptionOptions": {
      "isEnabled": true,
      "locale": "en-US"
    }
  }
}
```

Fields, verified against the spec's `startRecording` / `recordingOptions` schemas:

- `recordingName` (optional): identifier for this recording in the session, 1 to 32 chars, no whitespace. Other commands (`stopRecording`) reference it to target a specific recording.
- `recordingOptions` (**required**). Within it, **`destination`, `destinationUrl`, and `credentials` are required**:
  - `format`: `MP3` (default) or `WAV`.
  - `recordingType`: `COMBINED` (both directions, default), `INBOUND` (inbound stream only), or `OUTBOUND` (outbound stream only).
  - `destination`: `AWS` (default), `GCP`, or `AZURE`.
  - `destinationUrl`: bucket path where files are uploaded.
  - `credentials`: storage credentials in the destination-specific format.
  - `transcriptionOptions` (optional): if present, `isEnabled` is **required**; `locale` is a BCP-47 code (e.g. `en-US`, `es-ES`), default `en-US`.

`startRecording` is **non-blocking**, so the next SVAML command runs immediately. Recording continues until `stopRecording` is issued or the call ends.

## Recording from a webhook (inbound calls)

For inbound calls you return `startRecording` from your webhook instead of putting it in the outbound payload. Pick the server in your language (all four behave identically). On a `call.incoming` event the server answers, starts recording, and plays a recording notice.

Each server reads its configuration from the exported environment variables (`SINCH_NUMBER`, `STORAGE_DESTINATION_URL`, `STORAGE_CREDENTIALS`, and optionally `PORT`). Export them first, then start the server and expose it with `ngrok http <PORT>`. Set that URL as the service webhook (see [2.1 Handle Inbound PSTN Calls](../2.1-inbound-pstn/description.md)).

### Node.js (Express, default PORT 3000)

Requirements: `npm install express`. Run with `node server.js`. Use `"type": "module"` in your `package.json`.

```javascript
// Sinch Recording & Transcription: Express.js webhook server.
// Handles call events and starts recording when the call is answered.

import express from "express";

const sinchNumber           = process.env.SINCH_NUMBER            || (() => { throw new Error("SINCH_NUMBER not set"); })();
const storageDestinationUrl = process.env.STORAGE_DESTINATION_URL || (() => { throw new Error("STORAGE_DESTINATION_URL not set"); })();
const storageCredentials    = process.env.STORAGE_CREDENTIALS     || (() => { throw new Error("STORAGE_CREDENTIALS not set"); })();
const PORT = process.env.PORT || 3000;

// Infer storage provider from URL scheme
const storageDestination = storageDestinationUrl.startsWith("gs://") ? "GCP"
  : storageDestinationUrl.startsWith("s3://") ? "AWS"
  : "AZURE";

const app = express();
app.use(express.json());

// POST /webhook: handles call events from Sinch
app.post("/webhook", (req, res) => {
  const event = req.body?.event;
  const call  = req.body?.call;

  console.log(`Received event: ${event}`, call?.callId);

  if (event === "call.incoming") {
    // Inbound call: answer, start recording, play notice, then bridge to agent or hang up
    const svamlResponse = {
      commands: [
        // Answer the inbound call
        { command: "answer" },

        // Start recording immediately when the inbound call is answered
        {
          command: "startRecording",
          recordingName: "main-recording",
          recordingOptions: {
            format: "MP3",
            recordingType: "COMBINED",        // Record both parties
            destination: storageDestination,
            destinationUrl: storageDestinationUrl,
            credentials: storageCredentials,
            transcriptionOptions: {
              isEnabled: true,                // Generate a transcription file
              locale: "en-US"
            }
          }
        },

        // Tell the caller the call is being recorded (legal requirement in many jurisdictions)
        {
          command: "messages",
          messagesName: "recording-notice",
          messages: [
            {
              type: "SAY",
              say: {
                text: "This call may be recorded for quality and compliance purposes.",
                voiceName: "Emma"
              }
            }
          ]
        }

        // Add your additional SVAML commands here, e.g.:
        // { command: "bridgeCall", bridgeName: "agent-bridge" }
        // { command: "dial", callName: "agent", to: { ... } }
      ],
      events: { onHangup: [{ command: "stopRecording", recordingName: "main-recording" }] }
    };

    return res.status(200).json(svamlResponse);
  }

  console.log(`Unhandled event: ${event}`);
  res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`Recording webhook server listening on port ${PORT}`);
  console.log(`Storage: ${storageDestination} -> ${storageDestinationUrl}`);
  console.log(`(Use ngrok: ngrok http ${PORT})`);
});
```

### Python (Flask, default PORT 8081)

Requirements: `pip install flask`. Run with `python server.py`.

```python
# Sinch Recording & Transcription: Flask webhook server.
# Starts recording when a call is answered and uploads to cloud storage.

import os
import sys
from flask import Flask, request, jsonify

sinch_number            = os.environ.get("SINCH_NUMBER")
storage_destination_url = os.environ.get("STORAGE_DESTINATION_URL")
storage_credentials     = os.environ.get("STORAGE_CREDENTIALS")

for var, name in [
    (sinch_number, "SINCH_NUMBER"),
    (storage_destination_url, "STORAGE_DESTINATION_URL"),
    (storage_credentials, "STORAGE_CREDENTIALS"),
]:
    if not var:
        print(f"ERROR: {name} is not set.", file=sys.stderr)
        sys.exit(1)

# Infer storage provider from URL scheme
if storage_destination_url.startswith("gs://"):
    storage_destination = "GCP"
elif storage_destination_url.startswith("s3://"):
    storage_destination = "AWS"
else:
    storage_destination = "AZURE"

port = int(os.environ.get("PORT", 8081))
app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handles Sinch call events and starts recording on answer."""
    body  = request.json
    event = body.get("event")
    call  = body.get("call", {})

    print(f"Received event: {event}, callId: {call.get('callId')}")

    if event == "call.incoming":
        # Inbound call: answer, start recording, play notice
        svaml_response = {
            "commands": [
                # Answer the inbound call
                {"command": "answer"},

                # Start recording immediately on answer
                {
                    "command": "startRecording",
                    "recordingName": "main-recording",
                    "recordingOptions": {
                        "format": "MP3",
                        "recordingType": "COMBINED",    # Both parties recorded
                        "destination": storage_destination,
                        "destinationUrl": storage_destination_url,
                        "credentials": storage_credentials,
                        "transcriptionOptions": {
                            "isEnabled": True,          # Generate transcript alongside audio
                            "locale": "en-US"
                        }
                    }
                },

                # Inform the caller the call is being recorded
                {
                    "command": "messages",
                    "messagesName": "recording-notice",
                    "messages": [
                        {
                            "type": "SAY",
                            "say": {
                                "text": "This call may be recorded for quality and compliance purposes.",
                                "voiceName": "Emma"
                            }
                        }
                    ]
                }

                # Add further SVAML commands here:
                # {"command": "bridgeCall", "bridgeName": "agent-bridge"},
                # {"command": "dial", "callName": "agent", "to": {...}}
            ],
            "events": {"onHangup": [{"command": "stopRecording", "recordingName": "main-recording"}]},
        }
        return jsonify(svaml_response), 200

    print(f"Unhandled event: {event}")
    return jsonify({"commands": []}), 200


if __name__ == "__main__":
    print(f"Recording webhook server listening on port {port}")
    print(f"Storage: {storage_destination} -> {storage_destination_url}")
    print(f"(Use ngrok: ngrok http {port})")
    app.run(host="0.0.0.0", port=port)
```

### PHP (Slim 4, default PORT 3000)

Requirements: `composer require slim/slim slim/psr7 nyholm/psr7`. Run with `php -S 0.0.0.0:3000 server.php`. Slim reads config via `getenv`, which picks up your exported variables directly.

```php
<?php
// Sinch Recording & Transcription: Slim Framework 4 webhook server.
// Starts recording when a call is answered and uploads to cloud storage.

use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Factory\AppFactory;

require __DIR__ . '/vendor/autoload.php';

$sinchNumber           = getenv('SINCH_NUMBER')            ?: die("ERROR: SINCH_NUMBER not set.\n");
$storageDestinationUrl = getenv('STORAGE_DESTINATION_URL') ?: die("ERROR: STORAGE_DESTINATION_URL not set.\n");
$storageCredentials    = getenv('STORAGE_CREDENTIALS')     ?: die("ERROR: STORAGE_CREDENTIALS not set.\n");

// Infer storage provider from URL scheme
if (str_starts_with($storageDestinationUrl, 'gs://')) {
    $storageDestination = 'GCP';
} elseif (str_starts_with($storageDestinationUrl, 's3://')) {
    $storageDestination = 'AWS';
} else {
    $storageDestination = 'AZURE';
}

$app = AppFactory::create();
$app->addBodyParsingMiddleware();

$app->post('/webhook', function (Request $request, Response $response)
    use ($sinchNumber, $storageDestination, $storageDestinationUrl, $storageCredentials) {

    $body  = $request->getParsedBody();
    $event = $body['event'] ?? null;
    $call  = $body['call']  ?? [];

    error_log("Received event: {$event}, callId: " . ($call['callId'] ?? ''));

    if ($event === 'call.incoming') {
        $svaml = [
            'commands' => [
                // Answer the inbound call
                ['command' => 'answer'],

                // Start recording immediately when the call is answered
                [
                    'command'       => 'startRecording',
                    'recordingName' => 'main-recording',
                    'recordingOptions' => [
                        'format'        => 'MP3',
                        'recordingType' => 'COMBINED',      // Both parties
                        'destination'   => $storageDestination,
                        'destinationUrl' => $storageDestinationUrl,
                        'credentials'   => $storageCredentials,
                        'transcriptionOptions' => [
                            'isEnabled' => true,            // Auto-transcribe the recording
                            'locale'    => 'en-US',
                        ],
                    ],
                ],

                // Inform the caller the call is being recorded
                [
                    'command'       => 'messages',
                    'messagesName'  => 'recording-notice',
                    'messages' => [
                        [
                            'type' => 'SAY',
                            'say'  => [
                                'text'      => 'This call may be recorded for quality and compliance purposes.',
                                'voiceName' => 'Emma',
                            ],
                        ],
                    ],
                ],

                // Add your routing SVAML here:
                // ['command' => 'bridgeCall', 'bridgeName' => 'agent-bridge'],
            ],
            'events' => ['onHangup' => [['command' => 'stopRecording', 'recordingName' => 'main-recording']]],
        ];

        $response->getBody()->write(json_encode($svaml));
        return $response->withHeader('Content-Type', 'application/json')->withStatus(200);
    }

    error_log("Unhandled event: {$event}");
    $response->getBody()->write(json_encode(['commands' => []]));
    return $response->withHeader('Content-Type', 'application/json')->withStatus(200);
});

$port = (int)(getenv('PORT') ?: 3000);
echo "Recording webhook server listening on port {$port}\n";
echo "Storage: {$storageDestination} -> {$storageDestinationUrl}\n";
echo "(Use ngrok: ngrok http {$port})\n";

$app->run();
```

### Java (Spring Boot, default PORT 3000)

Add `spring-boot-starter-web` to your `pom.xml` and run with `mvn spring-boot:run`. Spring reads config via `System.getenv`, which picks up your exported variables directly.

```java
// Sinch Recording & Transcription: Spring Boot webhook server.
// Starts recording when a call is answered and uploads to cloud storage.

package com.sinch.tutorials.recording;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@SpringBootApplication
@RestController
public class Server {

    private final String storageDestination;
    private final String storageDestinationUrl;
    private final String storageCredentials;

    public Server() {
        String sinchNumber         = requireEnv("SINCH_NUMBER");
        this.storageDestinationUrl = requireEnv("STORAGE_DESTINATION_URL");
        this.storageCredentials    = requireEnv("STORAGE_CREDENTIALS");

        // Infer provider from URL scheme
        if (storageDestinationUrl.startsWith("gs://")) {
            this.storageDestination = "GCP";
        } else if (storageDestinationUrl.startsWith("s3://")) {
            this.storageDestination = "AWS";
        } else {
            this.storageDestination = "AZURE";
        }
    }

    public static void main(String[] args) {
        String port = System.getenv().getOrDefault("PORT", "3000");
        System.setProperty("server.port", port);
        SpringApplication.run(Server.class, args);
        System.out.println("Recording webhook server started on port " + port);
    }

    /** POST /webhook: handles Sinch call events and starts recording on answer */
    @PostMapping("/webhook")
    public ResponseEntity<Map<String, Object>> webhook(@RequestBody Map<String, Object> body) {
        String event = (String) body.getOrDefault("event", "");
        @SuppressWarnings("unchecked")
        Map<String, Object> call = (Map<String, Object>) body.getOrDefault("call", Map.of());

        System.out.println("Received event: " + event + ", callId: " + call.get("callId"));

        if ("call.incoming".equals(event)) {
            Map<String, Object> svaml = Map.of(
                "commands", List.of(
                    // Answer the inbound call
                    Map.of("command", "answer"),

                    // Start recording immediately when the call is answered
                    Map.of(
                        "command", "startRecording",
                        "recordingName", "main-recording",
                        "recordingOptions", Map.of(
                            "format", "MP3",
                            "recordingType", "COMBINED",       // Both parties recorded
                            "destination", storageDestination,
                            "destinationUrl", storageDestinationUrl,
                            "credentials", storageCredentials,
                            "transcriptionOptions", Map.of(
                                "isEnabled", true,             // Generate transcript
                                "locale", "en-US"
                            )
                        )
                    ),

                    // Inform the caller the call is being recorded
                    Map.of(
                        "command", "messages",
                        "messagesName", "recording-notice",
                        "messages", List.of(
                            Map.of(
                                "type", "SAY",
                                "say", Map.of(
                                    "text", "This call may be recorded for quality and compliance purposes.",
                                    "voiceName", "Emma"
                                )
                            )
                        )
                    )

                    // Add routing commands here, e.g.:
                    // Map.of("command", "bridgeCall", "bridgeName", "agent-bridge")
                ),
                "events", Map.of("onHangup", List.of(Map.of("command", "stopRecording", "recordingName", "main-recording")))
            );

            return ResponseEntity.ok(svaml);
        }

        System.out.println("Unhandled event: " + event);
        return ResponseEntity.ok(Map.of("commands", List.of()));
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            System.err.println("ERROR: " + name + " is not set.");
            System.exit(1);
        }
        return value;
    }
}
```

> The webhook body is `{ event, call }`; read identifiers off the nested `call` object (e.g. `call.callId`, `call.sessionId`), consistent with [2.1 Handle Inbound PSTN Calls](../2.1-inbound-pstn/description.md). The servers here log `call.callId`.

The equivalent SVAML the server returns on `call.incoming` looks like this:

```json
{
  "commands": [
    { "command": "answer" },
    {
      "command": "startRecording",
      "recordingName": "main-recording",
      "recordingOptions": {
        "format": "MP3",
        "recordingType": "COMBINED",
        "destination": "AWS",
        "destinationUrl": "s3://my-voice-recordings/recordings/",
        "credentials": "ACCESS_KEY:SECRET_KEY:REGION",
        "transcriptionOptions": { "isEnabled": true, "locale": "en-US" }
      }
    },
    {
      "command": "messages",
      "messagesName": "recording-notice",
      "messages": [
        { "type": "SAY", "say": { "text": "This call may be recorded for quality and compliance purposes.", "voiceName": "Emma" } }
      ]
    }
  ],
  "events": { "onHangup": [{ "command": "stopRecording", "recordingName": "main-recording" }] }
}
```

## Stopping a recording mid-call

Issue `stopRecording` referencing the `recordingName` (the only required field besides `command`):

```json
{ "command": "stopRecording", "recordingName": "main-recording" }
```

You can record multiple distinct streams in one session by giving them distinct `recordingName` values, then stop them independently.

## After the call ends

Sinch uploads the recording to your bucket. The filename includes the call/session identifier. If transcription is enabled, a JSON transcript file is uploaded alongside the audio.

## Recording lifecycle events

`startRecording` accepts an optional `events` block (`recordingEvents` schema). The spec defines exactly two handlers:

| Event | When it fires |
| --- | --- |
| `onFinish` | The recording was successfully stopped. Note: this does **not** mean the file has been delivered to your bucket yet; it may still be in transit. |
| `onFailure` | The recording failed to start (auth error, missing bucket, bad credentials, etc.). **If omitted, failures are silently ignored and the call flow continues.** |

Announce a problem on the call instead of recording silently failing:

```json
{
  "command": "startRecording",
  "recordingName": "compliance",
  "recordingOptions": { "destination": "AWS", "destinationUrl": "s3://...", "credentials": "..." },
  "events": {
    "onFailure": [
      {
        "command": "messages",
        "messages": [
          { "type": "SAY", "say": { "text": "We are unable to record this call. Goodbye.", "voiceName": "Emma" } }
        ],
        "events": { "onFinish": [{ "command": "hangup" }] }
      }
    ]
  }
}
```

The example servers in this tutorial do **not** wire `onFailure`. Add it for any production flow that legally requires a recording.

## Other storage providers

The credential string is provider-specific. AWS is shown above. For the others, set `STORAGE_DESTINATION_URL` so the examples infer the right `destination`:

```bash
# Google Cloud Storage  (destination inferred: GCP)
export STORAGE_DESTINATION_URL=gs://my-gcs-bucket/recordings/
export STORAGE_CREDENTIALS=<service-account credential>   # e.g. base64-encoded service-account JSON

# Azure Blob Storage     (destination inferred: AZURE)
export STORAGE_DESTINATION_URL=https://myaccount.blob.core.windows.net/recordings/
export STORAGE_CREDENTIALS=<Azure storage credential>     # e.g. connection string or SAS token
```

- **GCS**: a service account with the `Storage Object Creator` role on the bucket.
- **Azure**: a storage account with a Blob container plus an access key or SAS token.

> The exact credential encoding for GCP and Azure (base64-JSON vs. raw JSON, connection string vs. SAS token) is not specified in the OpenAPI document. The spec only types `credentials` as a free-form string and gives an AWS-only example. Confirm the GCP/Azure formats against current Sinch product docs before relying on them.

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Consent** | In many jurisdictions you must announce recording *before* `startRecording` runs. Play a `SAY` message first (the examples play one right after, which may be too late for strict regimes). |
| **Bucket permissions** | Grant the minimum (`s3:PutObject` etc.), not full bucket access. Rotate keys periodically. |
| **Lifecycle / cost** | Apply a bucket lifecycle policy to age recordings to cheaper storage and delete after your retention period. |
| **Multiple recordings** | Each `recordingName` produces a separate output. Use distinct names per leg. |
| **Inbound-only vs combined** | If only one party consented, use `recordingType: INBOUND` or `OUTBOUND`. Default `COMBINED` captures both. |
| **Transcription locale** | Default `en-US`. Set explicitly for non-English calls, since a wrong locale yields a wrong transcript. |
| **Failure handling** | Wire `events.onFailure` so a misconfigured bucket doesn't silently swallow a recording. |
| **Secrets in the shell** | Exported variables live in your shell environment and can appear in shell history. Use a secrets manager or a restricted, non-committed profile file in production. |

## Command reference

- `startRecording`: non-blocking; requires `recordingOptions`. Optional `recordingName` (1 to 32 chars, no whitespace) and `events`.
- `recordingOptions`: requires `destination`, `destinationUrl`, `credentials`. Optional `format`, `recordingType`, `transcriptionOptions`.
- `format`: `MP3` (default) / `WAV`.
- `recordingType`: `COMBINED` (default) / `INBOUND` / `OUTBOUND`.
- `destination`: `AWS` (default) / `GCP` / `AZURE`.
- `transcriptionOptions`: `isEnabled` required when present; `locale` defaults to `en-US`.
- `stopRecording`: non-blocking; requires `recordingName`.
- `recordingEvents`: `onFinish`, `onFailure` (both optional).