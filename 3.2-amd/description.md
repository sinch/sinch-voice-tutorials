# Detect Voicemail & Beeps (AMD)

## Overview

Answering Machine Detection (AMD) lets you automatically distinguish between a live human and a voicemail machine, IVR, or beep when making outbound calls. The Voice API v2 runs AMD analysis on the call audio after the call is answered, then executes a **different branch of SVAML commands** depending on the result: `onHuman`, `onMachine`, `onBeep`, or `onUnknown`. You can wire a completely different call flow for each outcome, for example connect a human to a live agent, leave a voicemail when a beep is detected, or hang up silently on a machine.

AMD is controlled by the `amd` SVAML command, which you place inline in the call payload or return from a webhook. The command is **non-blocking**: the rest of your sequence keeps executing while detection runs in parallel, and the matching AMD branch fires as soon as a verdict is reached.

There are two ways to observe a result:

- **The AMD branch runs on the call itself.** Whatever commands you put under `onHuman` / `onBeep` / etc. execute on the live call, so the human hears your greeting and the voicemail gets your message. This is audible on the answering phone with **no backend required**.
- **AMD result webhook events.** If your call runs on a service with a webhook URL, Sinch additionally POSTs a `call.amd.human` / `call.amd.machine` / `call.amd.beep` / `call.amd.unknown` event to that URL. This is how you get a **visible log** in your own server of which branch fired (see [3.6 Track Call Status](../3.6-track-call-status/description.md) for consuming call events).

> The fastest path to a first success is the **inline callout** below: place the call, answer it, and hear the AMD branch run. Add the callback server later when you want server-side visibility or dynamic per-call AMD configuration.

## Real-life examples

- **Outreach campaigns**: leave a tailored voicemail only when a beep is detected, and connect a live answer to an agent.
- **Appointment reminders**: connect to a live agent when a human answers, leave a reminder message on voicemail systems.
- **Debt collection**: route live answers to a specialist, leave a callback number on answering machines.
- **Survey calls**: launch the survey IVR only when a real human is detected, abort silently on machine answers.

## Setup (do this first)

All scripts read their configuration from environment variables. **Export** them in the shell you will run from:

```bash
export PROJECT_ID=...            # from https://dashboard.sinch.com
export KEY_ID=...
export KEY_SECRET=...
export SINCH_NUMBER=+1...        # your Sinch virtual number (E.164)
export DESTINATION_NUMBER=+1...  # the number to call (E.164)

# Only needed for the callback-server path:
export CALLBACK_URL=...          # your public ngrok URL
export PORT=3000
```

Notes:

- Auth is **HTTP Basic** using `KEY_ID:KEY_SECRET`.
- These variables live only in the current shell. Open a new terminal and you will need to export them again (or add them to your shell profile).
- For the callback-server path you also need a public URL. Install [ngrok](https://ngrok.com) and a runtime (Node 18+, or Python 3.8+ with `flask`).

## First success: inline AMD callout (no backend)

This places an outbound call and runs AMD on it. The matching branch executes on the call, so you observe the result **by answering the phone**.

Pick a language below, paste the script, export your variables, and run it.

What happens:

- The script POSTs the full SVAML (including all four AMD branches) to `POST /v2/projects/{projectId}/calls` and prints `AMD call created successfully` with the returned `callId` on **HTTP 201**.
- Your `DESTINATION_NUMBER` rings. Depending on how it is answered:
  - **A person answers**, AMD resolves to human, the `onHuman` branch plays *"Hello! This is a call from Acme Corp..."* then hangs up.
  - **Voicemail picks up**, AMD waits for the beep, and on the tone the `onBeep` branch plays *"Hi, this is Acme Corp calling about your recent inquiry..."* then hangs up.
  - **Machine greeting, no beep yet**, `onMachine` hangs up silently.
  - **Inconclusive**, `onUnknown` hangs up.

> Visibility note: the script's terminal output only confirms the call was **created** (HTTP 201). It does **not** print which AMD branch fired, because that verdict lives on the call. To see the branch in your terminal, run the callback-server path further down and watch for `call.amd.*` events.

### Bash (curl)

```bash
#!/bin/bash
# Sinch AMD Callout: outbound call with Answering Machine Detection (AMD).
# AMD detects human vs. machine and fires different SVAML for each outcome.
# Reads credentials from exported environment variables (see Setup).

set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set. Export it first.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"

BASE_URL="https://voice.api.sinch.com/v2"

echo "Placing AMD callout from ${SINCH_NUMBER} to ${DESTINATION_NUMBER} ..."

BODY=$(printf '{
  "commands": [
    {
      "command": "dial",
      "callName": "amd-call",
      "from": { "type": "PHONE", "phone": { "number": "%s" } },
      "to":   { "type": "PHONE", "phone": { "number": "%s" } },
      "dialTimeoutDurationSeconds": 45,
      "maxCallDurationSeconds": 300,
      "events": {
        "onAnswer": [
          {
            "command": "amd",
            "events": {
              "onHuman": [
                {
                  "command": "messages",
                  "messagesName": "human-greeting",
                  "messages": [
                    {
                      "type": "SAY",
                      "say": {
                        "text": "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                        "voiceName": "Emma"
                      }
                    }
                  ],
                  "events": { "onFinish": [{ "command": "hangup" }] }
                }
              ],
              "onMachine": [
                { "command": "hangup" }
              ],
              "onBeep": [
                {
                  "command": "messages",
                  "messagesName": "voicemail-message",
                  "messages": [
                    {
                      "type": "SAY",
                      "say": {
                        "text": "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                        "voiceName": "Emma"
                      }
                    }
                  ],
                  "events": { "onFinish": [{ "command": "hangup" }] }
                }
              ],
              "onUnknown": [
                { "command": "hangup" }
              ]
            }
          }
        ]
      }
    }
  ]
}' "${SINCH_NUMBER}" "${DESTINATION_NUMBER}")

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "${BASE_URL}/projects/${PROJECT_ID}/calls" \
  -H "Content-Type: application/json" \
  -d "${BODY}")

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 201 ]; then
  echo "AMD call created successfully (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
```

### Python

Requires `pip install requests`.

```python
# Sinch AMD Callout: outbound call with Answering Machine Detection (AMD).
# AMD detects human vs. machine and executes different SVAML for each outcome.
# Reads credentials from exported environment variables (see Setup).
# Requirements: pip install requests

import os
import sys
import json
import requests

project_id         = os.environ.get("PROJECT_ID")
key_id             = os.environ.get("KEY_ID")
key_secret         = os.environ.get("KEY_SECRET")
sinch_number       = os.environ.get("SINCH_NUMBER")
destination_number = os.environ.get("DESTINATION_NUMBER")

for var, name in [
    (project_id, "PROJECT_ID"), (key_id, "KEY_ID"), (key_secret, "KEY_SECRET"),
    (sinch_number, "SINCH_NUMBER"), (destination_number, "DESTINATION_NUMBER"),
]:
    if not var:
        print(f"ERROR: {name} is not set. Export it first.", file=sys.stderr)
        sys.exit(1)

url = f"https://voice.api.sinch.com/v2/projects/{project_id}/calls"

# The `amd` command must be placed in the `onAnswer` event of a `dial` command.
# It fires different SVAML commands based on what AMD detects.
payload = {
    "commands": [
        {
            "command": "dial",
            "callName": "amd-call",
            "from": {"type": "PHONE", "phone": {"number": sinch_number}},
            "to":   {"type": "PHONE", "phone": {"number": destination_number}},
            "dialTimeoutDurationSeconds": 45,
            "maxCallDurationSeconds": 300,
            "events": {
                "onAnswer": [
                    {
                        "command": "amd",
                        "events": {
                            # Human picked up: play a personalized greeting
                            "onHuman": [
                                {
                                    "command": "messages",
                                    "messagesName": "human-greeting",
                                    "messages": [
                                        {
                                            "type": "SAY",
                                            "say": {
                                                "text": "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                                                "voiceName": "Emma"
                                            }
                                        }
                                    ],
                                    "events": {
                                        "onFinish": [{"command": "hangup"}]
                                    }
                                }
                            ],
                            # Machine greeting detected (beep not yet heard): just hang up
                            "onMachine": [
                                {"command": "hangup"}
                            ],
                            # Beep detected: leave a voicemail message right now
                            "onBeep": [
                                {
                                    "command": "messages",
                                    "messagesName": "voicemail-message",
                                    "messages": [
                                        {
                                            "type": "SAY",
                                            "say": {
                                                "text": "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                                                "voiceName": "Emma"
                                            }
                                        }
                                    ],
                                    "events": {
                                        "onFinish": [{"command": "hangup"}]
                                    }
                                }
                            ],
                            # Unknown: hang up safely
                            "onUnknown": [
                                {"command": "hangup"}
                            ]
                        }
                    }
                ]
            }
        }
    ]
}

print(f"Placing AMD callout from {sinch_number} to {destination_number} ...")

try:
    response = requests.post(url, json=payload, auth=(key_id, key_secret))
    data = response.json()

    if response.status_code == 201:
        print("AMD call created successfully:")
        print(json.dumps(data, indent=2))
    else:
        print(f"ERROR {response.status_code}:", file=sys.stderr)
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)

except requests.RequestException as e:
    print(f"Request failed: {e}", file=sys.stderr)
    sys.exit(1)
```

### Node.js (native fetch, Node 18+)

Save as `amd-callout.mjs` (or use `"type": "module"` in `package.json`) so top-level `await` works.

```javascript
// Sinch AMD Callout: Node.js (native fetch, Node 18+) outbound call with AMD.
// Reads credentials from exported environment variables (see Setup).
// Run: node amd-callout.mjs

const projectId         = process.env.PROJECT_ID         || (() => { throw new Error("PROJECT_ID not set"); })();
const keyId             = process.env.KEY_ID             || (() => { throw new Error("KEY_ID not set"); })();
const keySecret         = process.env.KEY_SECRET         || (() => { throw new Error("KEY_SECRET not set"); })();
const sinchNumber       = process.env.SINCH_NUMBER       || (() => { throw new Error("SINCH_NUMBER not set"); })();
const destinationNumber = process.env.DESTINATION_NUMBER || (() => { throw new Error("DESTINATION_NUMBER not set"); })();

const authHeader = "Basic " + Buffer.from(`${keyId}:${keySecret}`).toString("base64");

const payload = {
  commands: [
    {
      command: "dial",
      callName: "amd-call",
      from: { type: "PHONE", phone: { number: sinchNumber } },
      to:   { type: "PHONE", phone: { number: destinationNumber } },
      dialTimeoutDurationSeconds: 45,
      maxCallDurationSeconds: 300,
      events: {
        onAnswer: [
          {
            command: "amd",
            events: {
              // Human detected: greet and connect to an agent (or take further action)
              onHuman: [
                {
                  command: "messages",
                  messagesName: "human-greeting",
                  messages: [
                    {
                      type: "SAY",
                      say: {
                        text: "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                        voiceName: "Emma"
                      }
                    }
                  ],
                  events: { onFinish: [{ command: "hangup" }] }
                }
              ],
              // Machine detected (no beep yet): hang up silently
              onMachine: [{ command: "hangup" }],
              // Beep detected: play the voicemail message right after the beep
              onBeep: [
                {
                  command: "messages",
                  messagesName: "voicemail-message",
                  messages: [
                    {
                      type: "SAY",
                      say: {
                        text: "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                        voiceName: "Emma"
                      }
                    }
                  ],
                  events: { onFinish: [{ command: "hangup" }] }
                }
              ],
              // Unknown: safe default is to hang up
              onUnknown: [{ command: "hangup" }]
            }
          }
        ]
      }
    }
  ]
};

console.log(`Placing AMD callout from ${sinchNumber} to ${destinationNumber} ...`);

const response = await fetch(
  `https://voice.api.sinch.com/v2/projects/${projectId}/calls`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: authHeader
    },
    body: JSON.stringify(payload)
  }
);

const data = await response.json();

if (response.status === 201) {
  console.log("AMD call created successfully:", JSON.stringify(data, null, 2));
} else {
  console.error(`ERROR ${response.status}:`, JSON.stringify(data, null, 2));
  process.exit(1);
}
```

### PHP

Requires PHP 8+ with the curl extension. `getenv()` reads the exported variables directly.

```php
<?php
// Sinch AMD Callout: PHP outbound call with Answering Machine Detection.
// Reads credentials from exported environment variables (see Setup).
// Requirements: PHP 8+ with the curl extension.

$projectId         = getenv('PROJECT_ID')         ?: die("ERROR: PROJECT_ID not set.\n");
$keyId             = getenv('KEY_ID')             ?: die("ERROR: KEY_ID not set.\n");
$keySecret         = getenv('KEY_SECRET')         ?: die("ERROR: KEY_SECRET not set.\n");
$sinchNumber       = getenv('SINCH_NUMBER')       ?: die("ERROR: SINCH_NUMBER not set.\n");
$destinationNumber = getenv('DESTINATION_NUMBER') ?: die("ERROR: DESTINATION_NUMBER not set.\n");

$url = "https://voice.api.sinch.com/v2/projects/{$projectId}/calls";

// The `amd` command must be inside `onAnswer`. AMD fires different SVAML
// depending on whether a human, machine, or beep is detected.
$payload = [
    'commands' => [
        [
            'command' => 'dial',
            'callName' => 'amd-call',
            'from'    => ['type' => 'PHONE', 'phone' => ['number' => $sinchNumber]],
            'to'      => ['type' => 'PHONE', 'phone' => ['number' => $destinationNumber]],
            'dialTimeoutDurationSeconds' => 45,
            'maxCallDurationSeconds' => 300,
            'events' => [
                'onAnswer' => [
                    [
                        'command' => 'amd',
                        'events'  => [
                            // Human detected: play a personalized greeting
                            'onHuman' => [
                                [
                                    'command'       => 'messages',
                                    'messagesName'  => 'human-greeting',
                                    'messages' => [
                                        [
                                            'type' => 'SAY',
                                            'say'  => [
                                                'text'      => 'Hello! This is a call from Acme Corp. An agent will be with you shortly.',
                                                'voiceName' => 'Emma',
                                            ],
                                        ],
                                    ],
                                    'events' => [
                                        'onFinish' => [['command' => 'hangup']],
                                    ],
                                ],
                            ],
                            // Machine greeting (no beep yet): hang up
                            'onMachine' => [
                                ['command' => 'hangup'],
                            ],
                            // Beep detected: leave voicemail immediately after the beep
                            'onBeep' => [
                                [
                                    'command'       => 'messages',
                                    'messagesName'  => 'voicemail-message',
                                    'messages' => [
                                        [
                                            'type' => 'SAY',
                                            'say'  => [
                                                'text'      => 'Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.',
                                                'voiceName' => 'Emma',
                                            ],
                                        ],
                                    ],
                                    'events' => [
                                        'onFinish' => [['command' => 'hangup']],
                                    ],
                                ],
                            ],
                            // Unknown result: hang up safely
                            'onUnknown' => [
                                ['command' => 'hangup'],
                            ],
                        ],
                    ],
                ],
            ],
        ],
    ],
];

echo "Placing AMD callout from {$sinchNumber} to {$destinationNumber} ...\n";

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
    echo "AMD call created successfully:\n";
    echo json_encode($data, JSON_PRETTY_PRINT) . "\n";
} else {
    fwrite(STDERR, "ERROR {$httpCode}:\n");
    fwrite(STDERR, json_encode($data, JSON_PRETTY_PRINT) . "\n");
    exit(1);
}
```

### Java (11+)

`System.getenv` reads the exported variables directly.

```java
// Sinch AMD Callout: Java outbound call with Answering Machine Detection.
// Requires Java 11+ (java.net.http.HttpClient).
// Reads credentials from exported environment variables (see Setup).
//
// Compile: javac -d out AmdCallout.java
// Run:     java -cp out com.sinch.tutorials.amd.AmdCallout

package com.sinch.tutorials.amd;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Base64;

public class AmdCallout {

    public static void main(String[] args) throws Exception {
        String projectId         = requireEnv("PROJECT_ID");
        String keyId             = requireEnv("KEY_ID");
        String keySecret         = requireEnv("KEY_SECRET");
        String sinchNumber       = requireEnv("SINCH_NUMBER");
        String destinationNumber = requireEnv("DESTINATION_NUMBER");

        String url         = "https://voice.api.sinch.com/v2/projects/" + projectId + "/calls";
        String credentials = Base64.getEncoder()
                .encodeToString((keyId + ":" + keySecret).getBytes());

        // The `amd` command must be inside `onAnswer`.
        // AMD fires different SVAML depending on detection result.
        String body = String.format("""
            {
              "commands": [
                {
                  "command": "dial",
                  "callName": "amd-call",
                  "from": { "type": "PHONE", "phone": { "number": "%s" } },
                  "to":   { "type": "PHONE", "phone": { "number": "%s" } },
                  "dialTimeoutDurationSeconds": 45,
                  "maxCallDurationSeconds": 300,
                  "events": {
                    "onAnswer": [
                      {
                        "command": "amd",
                        "events": {
                          "onHuman": [
                            {
                              "command": "messages",
                              "messagesName": "human-greeting",
                              "messages": [
                                {
                                  "type": "SAY",
                                  "say": {
                                    "text": "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                                    "voiceName": "Emma"
                                  }
                                }
                              ],
                              "events": { "onFinish": [{ "command": "hangup" }] }
                            }
                          ],
                          "onMachine": [
                            { "command": "hangup" }
                          ],
                          "onBeep": [
                            {
                              "command": "messages",
                              "messagesName": "voicemail-message",
                              "messages": [
                                {
                                  "type": "SAY",
                                  "say": {
                                    "text": "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                                    "voiceName": "Emma"
                                  }
                                }
                              ],
                              "events": { "onFinish": [{ "command": "hangup" }] }
                            }
                          ],
                          "onUnknown": [
                            { "command": "hangup" }
                          ]
                        }
                      }
                    ]
                  }
                }
              ]
            }
            """, sinchNumber, destinationNumber);

        System.out.println("Placing AMD callout from " + sinchNumber + " to " + destinationNumber + " ...");

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .header("Authorization", "Basic " + credentials)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        int statusCode = response.statusCode();

        if (statusCode == 201) {
            System.out.println("AMD call created successfully:");
            System.out.println(response.body());
        } else {
            System.err.println("ERROR " + statusCode + ":");
            System.err.println(response.body());
            System.exit(1);
        }
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            System.err.println("ERROR: " + name + " is not set. Export it first.");
            System.exit(1);
        }
        return value;
    }
}
```

### Browser JavaScript (demo only)

Calling the Sinch API directly from a browser hits CORS restrictions, so this is a copy-paste template rather than a runnable script. It ships with placeholder strings you must replace, and in production you should proxy the call through your own backend.

```javascript
// Sinch AMD Callout: browser JS to trigger an outbound call with AMD.
// Note: calling the Sinch API directly from a browser will hit CORS restrictions.
// In production, proxy these calls through your backend.
// Replace the placeholders below; this file will not run as-is.

(async function sinchAmdCallout() {
  const projectId         = "YOUR_PROJECT_ID";
  const keyId             = "YOUR_KEY_ID";
  const keySecret         = "YOUR_KEY_SECRET";
  const sinchNumber       = "+1XXXXXXXXXX";
  const destinationNumber = "+1YYYYYYYYYY";

  const baseUrl    = "https://voice.api.sinch.com/v2";
  const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

  const payload = {
    commands: [
      {
        command: "dial",
        callName: "amd-call",
        from: { type: "PHONE", phone: { number: sinchNumber } },
        to:   { type: "PHONE", phone: { number: destinationNumber } },
        dialTimeoutDurationSeconds: 45,
        maxCallDurationSeconds: 300,
        events: {
          onAnswer: [
            {
              command: "amd",
              events: {
                onHuman: [
                  {
                    command: "messages",
                    messagesName: "human-greeting",
                    messages: [
                      {
                        type: "SAY",
                        say: {
                          text: "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                          voiceName: "Emma"
                        }
                      }
                    ],
                    events: { onFinish: [{ command: "hangup" }] }
                  }
                ],
                onMachine: [{ command: "hangup" }],
                onBeep: [
                  {
                    command: "messages",
                    messagesName: "voicemail-message",
                    messages: [
                      {
                        type: "SAY",
                        say: {
                          text: "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                          voiceName: "Emma"
                        }
                      }
                    ],
                    events: { onFinish: [{ command: "hangup" }] }
                  }
                ],
                onUnknown: [{ command: "hangup" }]
              }
            }
          ]
        }
      }
    ]
  };

  console.log(`Placing AMD callout from ${sinchNumber} to ${destinationNumber} ...`);

  const response = await fetch(
    `${baseUrl}/projects/${projectId}/calls`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: authHeader
      },
      body: JSON.stringify(payload)
    }
  );

  const data = await response.json();

  if (response.status === 201) {
    console.log("AMD call created successfully:", data);
  } else {
    console.error(`ERROR ${response.status}:`, data);
  }
})();
```

## Place AMD inside an outbound dial (the contract)

Run `amd` as the **first** command in the dial's `onAnswer` event:

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "amd-call",
      "from": { "type": "PHONE", "phone": { "number": "+1SINCH_NUMBER" } },
      "to":   { "type": "PHONE", "phone": { "number": "+1DESTINATION" } },
      "dialTimeoutDurationSeconds": 45,
      "maxCallDurationSeconds": 300,
      "events": {
        "onAnswer": [
          { "command": "amd", "events": { /* onHuman / onMachine / onBeep / onUnknown */ } }
        ]
      }
    }
  ]
}
```

The four AMD branches (verified against the spec's `amdEvents` schema):

- `onHuman`: a live person picked up. Connect to an agent or start a conversation.
- `onMachine`: a machine answered and is playing its greeting (beep not yet detected). Usually hang up or wait for the beep.
- `onBeep`: a voicemail beep was detected. Leave your voicemail message now.
- `onUnknown`: detection was inconclusive. Safe default is to hang up, or treat as human.

Each branch holds a normal array of SVAML commands. All four are **optional**: branches you leave out are simply not executed, so you can wire only the outcomes you care about.

> Per the spec, the `amd` command has **no fields besides `command` and `events`**. There are no tuning knobs (no timeouts, no sensitivity) on the command itself.

## Dynamic AMD via a callback server

Use this when you want per-call AMD configuration (for example, choosing the voicemail script by destination) or when you want **server-side logs** of the AMD verdict. The callback server answers inbound calls and returns SVAML that runs `amd`, and it logs the `call.amd.*` result events Sinch posts back.

### 1. Start the server and expose it

Paste one of the servers below, export your variables, then run it and expose it with ngrok:

```bash
node amd-callback-server.mjs   # Express, port 3000
# or
python amd-callback-server.py  # Flask, port 3000

ngrok http 3000
```

Copy the ngrok HTTPS URL into your service's webhook configuration (set the service `callBehavior` to `WEBHOOK`, see [2.1 Handle Inbound PSTN Calls](../2.1-inbound-pstn/description.md) for the exact PATCH request). The server's `/webhook` endpoint receives the `call.incoming` event and responds with SVAML that answers the call and runs `amd`.

There is no wrapper command in the webhook response: the `commands` array is returned at the top level, starting with `answer`, then `amd` as the first command after answering. Hangup handling goes in the top-level `events.onHangup`.

### 2. Node.js server (Express)

Requires `npm install express`, and `"type": "module"` in `package.json` (or a `.mjs` extension).

```javascript
// Sinch AMD Callback Server: Express.js webhook server.
// Handles inbound call events, responds with SVAML including the AMD command,
// and logs the AMD verdict events Sinch posts back.
// Reads config from exported environment variables (see Setup).
//
// Requirements: npm install express
// Run: node amd-callback-server.mjs

import express from "express";

const sinchNumber       = process.env.SINCH_NUMBER       || (() => { throw new Error("SINCH_NUMBER not set"); })();
const destinationNumber = process.env.DESTINATION_NUMBER || (() => { throw new Error("DESTINATION_NUMBER not set"); })();
const PORT = process.env.PORT || 3000;

const app = express();
app.use(express.json());

// POST /webhook: receives Sinch call events and responds with AMD SVAML
app.post("/webhook", (req, res) => {
  const event = req.body?.event;
  const call  = req.body?.call;

  console.log(`Received event: ${event}`, call?.callId);

  if (event === "call.incoming") {
    // Inbound call: respond with SVAML to answer and run AMD detection.
    // Return the commands directly at the top level: `answer` first, then `amd`
    // as the first command after answering. AMD then fires one of:
    // onHuman, onMachine, onBeep, onUnknown. Hangup handling goes in the
    // top-level events.onHangup (honored only on call.incoming responses).
    const svamlResponse = {
      commands: [
        { command: "answer" },
        // Run AMD detection as the first thing after answering
        {
          command: "amd",
          events: {
            // Live human detected: play a personalized message
            onHuman: [
              {
                command: "messages",
                messagesName: "human-greeting",
                messages: [
                  {
                    type: "SAY",
                    say: {
                      text: "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                      voiceName: "Emma"
                    }
                  }
                ],
                events: { onFinish: [{ command: "hangup" }] }
              }
            ],

            // Machine greeting detected (waiting for beep): hang up silently
            onMachine: [{ command: "hangup" }],

            // Beep detected: leave voicemail right after the beep tone
            onBeep: [
              {
                command: "messages",
                messagesName: "voicemail-message",
                messages: [
                  {
                    type: "SAY",
                    say: {
                      text: "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                      voiceName: "Emma"
                    }
                  }
                ],
                events: { onFinish: [{ command: "hangup" }] }
              }
            ],

            // AMD inconclusive: hang up rather than risk a bad experience
            onUnknown: [{ command: "hangup" }]
          }
        }
      ],
      events: {
        onHangup: [{ command: "hangup" }]
      }
    };

    return res.status(200).json(svamlResponse);
  }

  // AMD verdict events: this is how you see which branch fired, server-side.
  if (event?.startsWith("call.amd.")) {
    console.log(`AMD verdict: ${event}`);         // call.amd.human, call.amd.beep, ...
    return res.status(200).json({ commands: [] }); // no further SVAML needed
  }

  // Acknowledge all other events
  console.log(`Unhandled event: ${event}`);
  res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`AMD callback server listening on port ${PORT}`);
  console.log(`Set your Sinch service webhook URL to: http://localhost:${PORT}/webhook`);
  console.log(`(Use ngrok: ngrok http ${PORT})`);
});
```

### 3. Python server (Flask)

Requires `pip install flask`.

```python
# Sinch AMD Callback Server: Flask webhook server.
# Handles inbound call events, responds with SVAML including the AMD command,
# and logs the AMD verdict events Sinch posts back.
# Reads config from exported environment variables (see Setup).
# Requirements: pip install flask

import os
import sys
from flask import Flask, request, jsonify

sinch_number       = os.environ.get("SINCH_NUMBER")
destination_number = os.environ.get("DESTINATION_NUMBER")

for var, name in [(sinch_number, "SINCH_NUMBER"), (destination_number, "DESTINATION_NUMBER")]:
    if not var:
        print(f"ERROR: {name} is not set. Export it first.", file=sys.stderr)
        sys.exit(1)

port = int(os.environ.get("PORT", 3000))
app  = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handles Sinch call events and responds with AMD SVAML."""
    body  = request.get_json(force=True)
    event = body.get("event")
    call  = body.get("call", {})

    print(f"Received event: {event}, callId: {call.get('callId')}")

    if event == "call.incoming":
        # Inbound call: answer and run AMD.
        # Return the commands directly at the top level: `answer` first, then
        # `amd` as the first command after answering. AMD fires one of:
        # onHuman, onMachine, onBeep, onUnknown. Hangup handling goes in the
        # top-level events.onHangup (honored only on call.incoming responses).
        svaml_response = {
            "commands": [
                {"command": "answer"},
                # AMD detection: first command after answering
                {
                    "command": "amd",
                    "events": {
                        # Live human: play a personalized greeting
                        "onHuman": [
                            {
                                "command": "messages",
                                "messagesName": "human-greeting",
                                "messages": [
                                    {
                                        "type": "SAY",
                                        "say": {
                                            "text": "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                                            "voiceName": "Emma"
                                        }
                                    }
                                ],
                                "events": {"onFinish": [{"command": "hangup"}]}
                            }
                        ],

                        # Machine greeting (no beep yet): hang up silently
                        "onMachine": [{"command": "hangup"}],

                        # Beep detected: leave voicemail right after the beep
                        "onBeep": [
                            {
                                "command": "messages",
                                "messagesName": "voicemail-message",
                                "messages": [
                                    {
                                        "type": "SAY",
                                        "say": {
                                            "text": "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                                            "voiceName": "Emma"
                                        }
                                    }
                                ],
                                "events": {"onFinish": [{"command": "hangup"}]}
                            }
                        ],

                        # Unknown result: hang up safely
                        "onUnknown": [{"command": "hangup"}]
                    }
                }
            ],
            "events": {
                "onHangup": [{"command": "hangup"}]
            }
        }
        return jsonify(svaml_response), 200

    # AMD verdict events: this is how you see which branch fired, server-side.
    if event and event.startswith("call.amd."):
        print(f"AMD verdict: {event}")            # call.amd.human, call.amd.beep, ...
        return jsonify({"commands": []}), 200      # no further SVAML needed

    print(f"Unhandled event: {event}")
    return jsonify({"commands": []}), 200


if __name__ == "__main__":
    print(f"AMD callback server listening on port {port}")
    print(f"Set your Sinch service webhook URL to: http://localhost:{port}/webhook")
    print(f"(Use ngrok: ngrok http {port})")
    app.run(host="0.0.0.0", port=port)
```

### 4. See the AMD verdict in your logs

Both servers above include a handler for the AMD result events. Sinch posts the verdict back to the same webhook URL as one of `call.amd.human`, `call.amd.machine`, `call.amd.beep`, or `call.amd.unknown` (verified event names). With the handler in place, answering as a human logs `AMD verdict: call.amd.human`, and a voicemail logs `call.amd.machine` then `call.amd.beep`.

Webhook delivery uses CloudEvents (HTTP binary content mode, `ce-type: com.sinch.voice.webhook.v2`); the JSON body is `{ event, call }`. 
## What success looks like

| Scenario | On the answering phone | In your callback log |
| --- | --- | --- |
| Human answers | Hears the `onHuman` greeting | `call.amd.human` |
| Voicemail | Beep, then hears the `onBeep` voicemail message | `call.amd.machine` then `call.amd.beep` |
| Machine, no beep | Silence then hangup | `call.amd.machine` |
| Inconclusive | Hangup | `call.amd.unknown` |

The inline-callout terminal only ever prints `AMD call created successfully` (HTTP 201). That confirms the call was placed, not which branch ran. Use the callback server for the branch verdict.

## Tips for AMD accuracy

- Allow `dialTimeoutDurationSeconds` of at least `30`, because machines may take a few seconds to answer. The scripts use `45`.
- Make `amd` the **first** command in `onAnswer`. Do not play messages before AMD runs, since they bias detection.
- `onBeep` is the right moment to start your voicemail message, not `onMachine`.
- If you want hold tones during analysis, play them on a separate call leg, not the leg being analysed.

## Language coverage

Six callout variants are shown above, plus two callback-server variants. All send an **identical AMD payload** (same four branches, same `voiceName: Emma`, `dialTimeoutDurationSeconds: 45`, `maxCallDurationSeconds: 300`). Every server-side variant reads credentials from **exported environment variables**, so export your variables in the same shell before running.

| Variant | Run | Notes |
| --- | --- | --- |
| Bash | `bash amd-callout.sh` | curl + Basic auth, pretty-prints with `jq` if present. |
| Python | `python amd-callout.py` | `pip install requests`. |
| Node.js | `node amd-callout.mjs` | Node 18+ native `fetch`, save as `.mjs` or set `"type": "module"`. |
| Browser JS | (browser) | Demo only, has placeholder credentials and hits CORS. Proxy through a backend in production. |
| PHP | `php amd-callout.php` | PHP 8+ with curl. Reads env via `getenv()`, so export the vars first. |
| Java | `javac -d out AmdCallout.java && java -cp out com.sinch.tutorials.amd.AmdCallout` | Java 11+. Reads `System.getenv`, so export the vars first. |
| Node callback server | `node amd-callback-server.mjs` | Express, `npm install express`. |
| Python callback server | `python amd-callback-server.py` | Flask, `pip install flask`. |

> The five runnable callouts (Bash, Python, Node.js, PHP, Java) all read credentials from the exported environment. The browser JS variant is the odd one out: it uses placeholder strings and will not run as-is, since a browser has no environment variables to export and calling the API directly hits CORS. The Node.js callout and the browser JS are intentionally different (server-side Node vs browser), not duplicates.

## The `amd` command at a glance

- `amd` is a non-blocking SVAML command with **only** `command` and `events`.
- `events` holds optional `onHuman`, `onMachine`, `onBeep`, and `onUnknown` arrays, each a list of SVAML commands.
- Its natural home is the first command after the call is answered: inside `dial.events.onAnswer` for outbound calls, or right after `answer` in a webhook response for inbound calls.
- The AMD verdict is also delivered as a webhook event: `call.amd.human` / `call.amd.machine` / `call.amd.beep` / `call.amd.unknown`.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with API credentials and a Sinch virtual number.
- For the callback-server path: a publicly reachable URL (use [ngrok](https://ngrok.com) during development) and a service set to `WEBHOOK`.