# Integrate an ElevenLabs AI Agent via SIP

## Overview

This tutorial connects a Sinch voice call to an [ElevenLabs](https://elevenlabs.io) Conversational AI agent over SIP. Unlike the [bridge-based integration](../4.3-elevenlabs-bridge/description.md), there is no relay server to deploy: Sinch dials the ElevenLabs SIP endpoint directly, and the two platforms exchange audio natively over the SIP session. The call flow is expressed entirely in SVAML, either as a static service behavior (inbound) or as a one-shot `POST /v2/projects/{projectId}/calls` payload (outbound).

Four scenarios are covered, all using the same underlying pattern of bridging two call legs:

1. **PSTN-in to ElevenLabs** : an external caller dials your Sinch number; Sinch answers and bridges to the ElevenLabs agent.
2. **SIP-in to ElevenLabs** : an external caller reaches Sinch over a configured SIP trunk, same SVAML, different ingress.
3. **PSTN-out to ElevenLabs** : Sinch dials a phone number and, on answer, bridges the callee to the ElevenLabs agent.
4. **SIP-out to ElevenLabs** : Sinch dials an external SIP endpoint and, on answer, bridges the callee to the ElevenLabs agent.

**When to use this vs the WebSocket bridge:** Use SIP when you want ElevenLabs to own the entire voice pipeline (STT, LLM, TTS) with zero relay infrastructure on your side. Use the [WebSocket bridge](/docs/voice/tutorials/integrate-ai-agent-bridge) when you need to intercept or transform the raw audio frames between Sinch and ElevenLabs (for example, to inject custom audio, apply gain, or log PCM). If you only need to exchange plain text with your own backend and want Sinch to handle speech-to-text and TTS, use [Voice Relay](/docs/voice/tutorials/voice-relay) instead.

## What success looks like

**Inbound:** you call your Sinch number (or SIP URI), the call is answered immediately, and you hear the ElevenLabs agent's greeting. You hold a spoken conversation with the agent.

**Outbound:** you run a script, your phone (or SIP client) rings, you answer, and you hear the ElevenLabs agent. A spoken back-and-forth follows.

In both cases, the Sinch dashboard shows two call legs joined by a bridge, and the ElevenLabs dashboard shows agent activity for the session.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project, API credentials (`KEY_ID` / `KEY_SECRET`), and a Sinch virtual number assigned to a service.
- An ElevenLabs account with a configured Conversational AI agent whose **Phone** channel is enabled and whose SIP endpoint is known (typically `sip:<number>@sip.rtc.elevenlabs.io:5060`). See [ElevenLabs SIP setup](#elevenlabs-sip-setup) below.
- `curl` (and optionally `jq`) for the shell examples; `pip install requests` for the Python examples.

## ElevenLabs SIP setup

Before any of the scenarios below will work, configure the ElevenLabs side:

1. In the [ElevenLabs dashboard](https://elevenlabs.io), open your Conversational AI agent.
2. Configure the **Telephony** channel (sometimes labeled "Phone Numbers" or "SIP").
3. Note the SIP endpoint ElevenLabs assigns. The conventional format is `sip:<your-sinch-number>@sip.rtc.elevenlabs.io:5060`, but verify the exact URI in the ElevenLabs dashboard or their current docs, as the domain and port may change.
4. Configure the agent's voice, system prompt, and first message in the ElevenLabs dashboard. Sinch only routes audio; it does not configure the agent.

> ElevenLabs' SIP offering, endpoint format, and authentication requirements evolve independently. Treat the URI shown above as a starting point and verify it against ElevenLabs' current documentation.


## Setup

Export your credentials and scenario-specific variables into the shell you will run the examples from. Each scenario uses a subset of these variables.

```bash
# ── Sinch credentials (all scenarios) ──
export PROJECT_ID="your-project-uuid"
export KEY_ID="your-access-key-id"
export KEY_SECRET="your-access-key-secret"
export SINCH_NUMBER="+1XXXXXXXXXX"

# ── Inbound scenarios only ──
export SERVICE_ID="your-service-uuid"

# ── Outbound PSTN scenario ──
export DESTINATION_NUMBER="+1YYYYYYYYYY"

# ── Outbound SIP scenario ──
export DESTINATION_SIP="sip:user@their-domain.example"

# ── ElevenLabs SIP endpoint (all scenarios) ──
export ELEVENLABS_SIP_URI="sip:+1XXXXXXXXXX@sip.rtc.elevenlabs.io:5060"

# ── Optional tuning ──
export DIAL_TIMEOUT=30         # seconds to wait for answer
export MAX_CALL_DURATION=7200  # hard ceiling on answered call (seconds)
```

| Variable | Required | Where to get it | Notes |
| --- | --- | --- | --- |
| `PROJECT_ID` | yes | [Sinch Dashboard](https://dashboard.sinch.com) > your Voice project | |
| `KEY_ID` | yes | Dashboard > Access Keys | HTTP Basic username |
| `KEY_SECRET` | yes | Dashboard > Access Keys (shown once at creation) | HTTP Basic password |
| `SINCH_NUMBER` | yes | Dashboard > Numbers | Your Sinch number, E.164. Used as `from` and typically also as the user part of `ELEVENLABS_SIP_URI`. |
| `SERVICE_ID` | inbound only | Dashboard > your Voice project > Services | The service whose call behavior you want to set. |
| `DESTINATION_NUMBER` | PSTN-out only | Your own list | E.164 phone number to dial. |
| `DESTINATION_SIP` | SIP-out only | Your own list | Full SIP URI of the external endpoint to dial. |
| `ELEVENLABS_SIP_URI` | yes | ElevenLabs dashboard, Phone/SIP channel config | Full SIP URI including port. Verify format in ElevenLabs docs. |
| `DIAL_TIMEOUT` | no | n/a | Defaults to `30` in the examples. |
| `MAX_CALL_DURATION` | no | n/a | Defaults to `7200` in the examples. |

Authentication is HTTP Basic using `KEY_ID:KEY_SECRET`. The API base URL is `https://voice.api.sinch.com` (regional hosts `us1`, `eu1`, `br1`, `sg1`, `au1` are also available).

---

## Scenario 1: Inbound PSTN to ElevenLabs agent

An external caller dials your Sinch phone number. Sinch answers, bridges the caller leg, then dials the ElevenLabs SIP endpoint and bridges it into the same bridge. The caller talks to the agent.

This uses `PATCH /v2/projects/{projectId}/services/{serviceId}` to set a **static** call behavior on the service so that every inbound call is handled the same way without a webhook.

### The SVAML

```json
{
  "callBehavior": {
    "type": "STATIC",
    "static": {
      "callName": "caller",
      "commands": [
        { "command": "answer" },
        { "command": "bridgeCall", "bridgeName": "sip-bridge" },
        {
          "command": "dial",
          "callName": "sip-agent",
          "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
          "to": {
            "type": "SIP",
            "sip": {
              "endpoint": "<ELEVENLABS_SIP_URI>",
              "transport": "TCP"
            }
          },
          "dialTimeoutDurationSeconds": 30,
          "maxCallDurationSeconds": 7200,
          "events": {
            "onAnswer": [
              { "command": "bridgeCall", "bridgeName": "sip-bridge" }
            ],
            "onHangup": [
              { "command": "hangup", "callName": "caller" }
            ]
          }
        }
      ],
      "events": {
        "onHangup": [
          { "command": "hangup", "callName": "sip-agent" }
        ]
      }
    }
  }
}
```

Key points:

- `callName: "caller"` labels the inbound leg. `callName: "sip-agent"` labels the ElevenLabs leg. Both join `bridgeName: "sip-bridge"`, so audio flows bidirectionally.
- `transport: "TCP"` is required for the ElevenLabs SIP endpoint (at the time of writing).
- The mutual `onHangup` handlers ensure that when either party hangs up, the other leg is also torn down.

### Shell (curl)

```bash
#!/bin/bash
set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SERVICE_ID:?ERROR: SERVICE_ID is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${ELEVENLABS_SIP_URI:?ERROR: ELEVENLABS_SIP_URI is not set.}"

DIAL_TIMEOUT="${DIAL_TIMEOUT:-30}"
MAX_CALL_DURATION="${MAX_CALL_DURATION:-7200}"

echo "Patching service ${SERVICE_ID} for inbound -> ElevenLabs SIP ..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X PATCH \
  -u "${KEY_ID}:${KEY_SECRET}" \
  "https://voice.api.sinch.com/v2/projects/${PROJECT_ID}/services/${SERVICE_ID}" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "callBehavior": {
    "type": "STATIC",
    "static": {
      "callName": "caller",
      "commands": [
        { "command": "answer" },
        { "command": "bridgeCall", "bridgeName": "sip-bridge" },
        {
          "command": "dial",
          "callName": "sip-agent",
          "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
          "to": {
            "type": "SIP",
            "sip": {
              "endpoint": "${ELEVENLABS_SIP_URI}",
              "transport": "TCP"
            }
          },
          "dialTimeoutDurationSeconds": ${DIAL_TIMEOUT},
          "maxCallDurationSeconds": ${MAX_CALL_DURATION},
          "events": {
            "onAnswer": [
              { "command": "bridgeCall", "bridgeName": "sip-bridge" }
            ],
            "onHangup": [
              { "command": "hangup", "callName": "caller" }
            ]
          }
        }
      ],
      "events": {
        "onHangup": [
          { "command": "hangup", "callName": "sip-agent" }
        ]
      }
    }
  }
}
EOF
)

HTTP_BODY=$(echo "${RESPONSE}" | head -n -1)
HTTP_CODE=$(echo "${RESPONSE}" | tail -n 1)

if [ "${HTTP_CODE}" -eq 200 ]; then
  echo "Service updated (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
```

### Python

```python
# Requirements: pip install requests
import json
import os
import sys

import requests


def env(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        print(f"ERROR: {name} is not set. Run: export {name}=...", file=sys.stderr)
        sys.exit(1)
    return value


project_id        = env("PROJECT_ID")
key_id            = env("KEY_ID")
key_secret        = env("KEY_SECRET")
service_id        = env("SERVICE_ID")
sinch_number      = env("SINCH_NUMBER")
elevenlabs_sip    = env("ELEVENLABS_SIP_URI")
dial_timeout      = int(env("DIAL_TIMEOUT", "30"))
max_call_duration = int(env("MAX_CALL_DURATION", "7200"))

url = f"https://voice.api.sinch.com/v2/projects/{project_id}/services/{service_id}"

payload = {
    "callBehavior": {
        "type": "STATIC",
        "static": {
            "callName": "caller",
            "commands": [
                {"command": "answer"},
                {"command": "bridgeCall", "bridgeName": "sip-bridge"},
                {
                    "command": "dial",
                    "callName": "sip-agent",
                    "from": {"type": "PHONE", "phone": {"number": sinch_number}},
                    "to": {
                        "type": "SIP",
                        "sip": {
                            "endpoint": elevenlabs_sip,
                            "transport": "TCP",
                        },
                    },
                    "dialTimeoutDurationSeconds": dial_timeout,
                    "maxCallDurationSeconds": max_call_duration,
                    "events": {
                        "onAnswer": [
                            {"command": "bridgeCall", "bridgeName": "sip-bridge"}
                        ],
                        "onHangup": [
                            {"command": "hangup", "callName": "caller"}
                        ],
                    },
                },
            ],
            "events": {
                "onHangup": [
                    {"command": "hangup", "callName": "sip-agent"}
                ]
            },
        },
    }
}

print(f"Patching service {service_id} for inbound -> ElevenLabs SIP ...")

resp = requests.patch(url, json=payload, auth=(key_id, key_secret))
if resp.status_code == 200:
    print(f"Service updated (HTTP {resp.status_code}):")
    print(json.dumps(resp.json(), indent=2))
else:
    print(f"ERROR: API returned HTTP {resp.status_code}:", file=sys.stderr)
    print(resp.text, file=sys.stderr)
    sys.exit(1)
```

Once the PATCH succeeds, call your Sinch number from any phone. Sinch answers and bridges you to the ElevenLabs agent.

---

## Scenario 2: Inbound SIP to ElevenLabs agent

An external SIP client (softphone, PBX, or another SIP trunk) calls your Sinch SIP endpoint. The SVAML is **identical** to Scenario 1; only the ingress path differs.

### What changes

- Instead of a PSTN phone number, the external caller targets your Sinch SIP URI. The exact URI depends on how your project's SIP trunk is configured; consult the Sinch dashboard under your Voice project's SIP settings.
- The `PATCH /v2/projects/{projectId}/services/{serviceId}` payload is the same as Scenario 1 (the static behavior handles whatever inbound call arrives, regardless of whether it came in over PSTN or SIP).

### Setup

Run the same PATCH from Scenario 1 (shell or Python). Then, from an external SIP client, dial your Sinch SIP URI. The call is answered, bridged, and the ElevenLabs agent greets the caller.

> If you have both a phone number and a SIP trunk assigned to the same service, the same static behavior handles calls from either ingress. You do not need separate services unless you want different call flows for PSTN and SIP callers.

---

## Scenario 3: Outbound PSTN, bridged to ElevenLabs agent

Sinch dials a phone number. When the callee answers, the call is bridged to the ElevenLabs SIP agent. Use this for outbound campaigns, appointment reminders, or survey calls where the AI agent drives the conversation.

This uses `POST /v2/projects/{projectId}/calls`.

### The SVAML

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "origin",
      "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
      "to":   { "type": "PHONE", "phone": { "number": "<DESTINATION_NUMBER>" } },
      "dialTimeoutDurationSeconds": 30,
      "maxCallDurationSeconds": 180,
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "bridge" },
          {
            "command": "dial",
            "callName": "elevenlabs",
            "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
            "to": {
              "type": "SIP",
              "sip": {
                "endpoint": "<ELEVENLABS_SIP_URI>",
                "transport": "TCP"
              }
            },
            "events": {
              "onAnswer": [
                { "command": "bridgeCall", "bridgeName": "bridge" }
              ]
            }
          }
        ],
        "onHangup": [
          { "command": "hangup", "callName": "elevenlabs" }
        ]
      }
    }
  ]
}
```

Key points:

- `callName: "origin"` is the PSTN leg. `callName: "elevenlabs"` is the SIP leg. Both join `bridgeName: "bridge"`.
- The ElevenLabs `dial` fires only `onAnswer` of the PSTN leg, so the agent is not invoked for unanswered calls.
- `onHangup` on the origin tears down the ElevenLabs leg when the callee hangs up.

### Shell (curl)

```bash
#!/bin/bash
set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_NUMBER:?ERROR: DESTINATION_NUMBER is not set.}"
: "${ELEVENLABS_SIP_URI:?ERROR: ELEVENLABS_SIP_URI is not set.}"

DIAL_TIMEOUT="${DIAL_TIMEOUT:-30}"
MAX_CALL_DURATION="${MAX_CALL_DURATION:-180}"

echo "Dialing ${DESTINATION_NUMBER}, will bridge to ElevenLabs SIP on answer ..."

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
      "callName": "origin",
      "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
      "to":   { "type": "PHONE", "phone": { "number": "${DESTINATION_NUMBER}" } },
      "dialTimeoutDurationSeconds": ${DIAL_TIMEOUT},
      "maxCallDurationSeconds": ${MAX_CALL_DURATION},
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "bridge" },
          {
            "command": "dial",
            "callName": "elevenlabs",
            "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
            "to": {
              "type": "SIP",
              "sip": {
                "endpoint": "${ELEVENLABS_SIP_URI}",
                "transport": "TCP"
              }
            },
            "events": {
              "onAnswer": [
                { "command": "bridgeCall", "bridgeName": "bridge" }
              ]
            }
          }
        ],
        "onHangup": [
          { "command": "hangup", "callName": "elevenlabs" }
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
  echo "Call created (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
```

### Python

```python
# Requirements: pip install requests
import json
import os
import sys

import requests


def env(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        print(f"ERROR: {name} is not set. Run: export {name}=...", file=sys.stderr)
        sys.exit(1)
    return value


project_id         = env("PROJECT_ID")
key_id             = env("KEY_ID")
key_secret         = env("KEY_SECRET")
sinch_number       = env("SINCH_NUMBER")
destination_number = env("DESTINATION_NUMBER")
elevenlabs_sip     = env("ELEVENLABS_SIP_URI")
dial_timeout       = int(env("DIAL_TIMEOUT", "30"))
max_call_duration  = int(env("MAX_CALL_DURATION", "180"))

url = f"https://voice.api.sinch.com/v2/projects/{project_id}/calls"

payload = {
    "commands": [
        {
            "command": "dial",
            "callName": "origin",
            "from": {"type": "PHONE", "phone": {"number": sinch_number}},
            "to":   {"type": "PHONE", "phone": {"number": destination_number}},
            "dialTimeoutDurationSeconds": dial_timeout,
            "maxCallDurationSeconds": max_call_duration,
            "events": {
                "onAnswer": [
                    {"command": "bridgeCall", "bridgeName": "bridge"},
                    {
                        "command": "dial",
                        "callName": "elevenlabs",
                        "from": {"type": "PHONE", "phone": {"number": sinch_number}},
                        "to": {
                            "type": "SIP",
                            "sip": {
                                "endpoint": elevenlabs_sip,
                                "transport": "TCP",
                            },
                        },
                        "events": {
                            "onAnswer": [
                                {"command": "bridgeCall", "bridgeName": "bridge"}
                            ]
                        },
                    },
                ],
                "onHangup": [
                    {"command": "hangup", "callName": "elevenlabs"}
                ],
            },
        }
    ]
}

print(f"Dialing {destination_number}, will bridge to ElevenLabs SIP on answer ...")

resp = requests.post(url, json=payload, auth=(key_id, key_secret))
if resp.status_code == 201:
    print(f"Call created (HTTP {resp.status_code}):")
    print(json.dumps(resp.json(), indent=2))
else:
    print(f"ERROR: API returned HTTP {resp.status_code}:", file=sys.stderr)
    print(resp.text, file=sys.stderr)
    sys.exit(1)
```

---

## Scenario 4: Outbound SIP, bridged to ElevenLabs agent

Identical to Scenario 3, but the outbound leg dials an external SIP endpoint instead of a phone number. Use this when the person you are calling is reachable over SIP (a softphone, a PBX extension, another SIP trunk).

### The SVAML

```json
{
  "commands": [
    {
      "command": "dial",
      "callName": "origin",
      "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
      "to":   { "type": "SIP", "sip": { "endpoint": "<DESTINATION_SIP>" } },
      "dialTimeoutDurationSeconds": 30,
      "maxCallDurationSeconds": 180,
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "bridge" },
          {
            "command": "dial",
            "callName": "elevenlabs",
            "from": { "type": "PHONE", "phone": { "number": "<SINCH_NUMBER>" } },
            "to": {
              "type": "SIP",
              "sip": {
                "endpoint": "<ELEVENLABS_SIP_URI>",
                "transport": "TCP"
              }
            },
            "events": {
              "onAnswer": [
                { "command": "bridgeCall", "bridgeName": "bridge" }
              ]
            }
          }
        ],
        "onHangup": [
          { "command": "hangup", "callName": "elevenlabs" }
        ]
      }
    }
  ]
}
```

The only difference from Scenario 3 is that `to` on the origin leg uses `type: "SIP"` with a `sip.endpoint` instead of `type: "PHONE"`. Note that `transport` is not set on the destination SIP leg here (it defaults to UDP), since the external SIP endpoint may support different transports than ElevenLabs. Set it explicitly if your destination requires TCP or TLS.

### Shell (curl)

```bash
#!/bin/bash
set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is not set.}"
: "${KEY_ID:?ERROR: KEY_ID is not set.}"
: "${KEY_SECRET:?ERROR: KEY_SECRET is not set.}"
: "${SINCH_NUMBER:?ERROR: SINCH_NUMBER is not set.}"
: "${DESTINATION_SIP:?ERROR: DESTINATION_SIP is not set.}"
: "${ELEVENLABS_SIP_URI:?ERROR: ELEVENLABS_SIP_URI is not set.}"

DIAL_TIMEOUT="${DIAL_TIMEOUT:-30}"
MAX_CALL_DURATION="${MAX_CALL_DURATION:-180}"

echo "Dialing SIP ${DESTINATION_SIP}, will bridge to ElevenLabs SIP on answer ..."

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
      "callName": "origin",
      "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
      "to":   { "type": "SIP", "sip": { "endpoint": "${DESTINATION_SIP}" } },
      "dialTimeoutDurationSeconds": ${DIAL_TIMEOUT},
      "maxCallDurationSeconds": ${MAX_CALL_DURATION},
      "events": {
        "onAnswer": [
          { "command": "bridgeCall", "bridgeName": "bridge" },
          {
            "command": "dial",
            "callName": "elevenlabs",
            "from": { "type": "PHONE", "phone": { "number": "${SINCH_NUMBER}" } },
            "to": {
              "type": "SIP",
              "sip": {
                "endpoint": "${ELEVENLABS_SIP_URI}",
                "transport": "TCP"
              }
            },
            "events": {
              "onAnswer": [
                { "command": "bridgeCall", "bridgeName": "bridge" }
              ]
            }
          }
        ],
        "onHangup": [
          { "command": "hangup", "callName": "elevenlabs" }
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
  echo "Call created (HTTP ${HTTP_CODE}):"
  echo "${HTTP_BODY}" | (command -v jq > /dev/null && jq '.' || cat)
else
  echo "ERROR: API returned HTTP ${HTTP_CODE}:" >&2
  echo "${HTTP_BODY}" >&2
  exit 1
fi
```

### Python

```python
# Requirements: pip install requests
import json
import os
import sys

import requests


def env(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        print(f"ERROR: {name} is not set. Run: export {name}=...", file=sys.stderr)
        sys.exit(1)
    return value


project_id        = env("PROJECT_ID")
key_id            = env("KEY_ID")
key_secret        = env("KEY_SECRET")
sinch_number      = env("SINCH_NUMBER")
destination_sip   = env("DESTINATION_SIP")
elevenlabs_sip    = env("ELEVENLABS_SIP_URI")
dial_timeout      = int(env("DIAL_TIMEOUT", "30"))
max_call_duration = int(env("MAX_CALL_DURATION", "180"))

url = f"https://voice.api.sinch.com/v2/projects/{project_id}/calls"

payload = {
    "commands": [
        {
            "command": "dial",
            "callName": "origin",
            "from": {"type": "PHONE", "phone": {"number": sinch_number}},
            "to":   {"type": "SIP", "sip": {"endpoint": destination_sip}},
            "dialTimeoutDurationSeconds": dial_timeout,
            "maxCallDurationSeconds": max_call_duration,
            "events": {
                "onAnswer": [
                    {"command": "bridgeCall", "bridgeName": "bridge"},
                    {
                        "command": "dial",
                        "callName": "elevenlabs",
                        "from": {"type": "PHONE", "phone": {"number": sinch_number}},
                        "to": {
                            "type": "SIP",
                            "sip": {
                                "endpoint": elevenlabs_sip,
                                "transport": "TCP",
                            },
                        },
                        "events": {
                            "onAnswer": [
                                {"command": "bridgeCall", "bridgeName": "bridge"}
                            ]
                        },
                    },
                ],
                "onHangup": [
                    {"command": "hangup", "callName": "elevenlabs"}
                ],
            },
        }
    ]
}

print(f"Dialing SIP {destination_sip}, will bridge to ElevenLabs SIP on answer ...")

resp = requests.post(url, json=payload, auth=(key_id, key_secret))
if resp.status_code == 201:
    print(f"Call created (HTTP {resp.status_code}):")
    print(json.dumps(resp.json(), indent=2))
else:
    print(f"ERROR: API returned HTTP {resp.status_code}:", file=sys.stderr)
    print(resp.text, file=sys.stderr)
    sys.exit(1)
```

---

## How it works

All four scenarios use the same underlying mechanism: a **bridge** that joins two call legs.

1. **Inbound:** Sinch receives the call on the service and executes the static SVAML. It answers the caller, puts the caller into a named bridge, then dials the ElevenLabs SIP endpoint as a second leg and puts it into the same bridge. Audio flows bidirectionally.

2. **Outbound:** A `POST /v2/projects/{projectId}/calls` creates the session. The first `dial` reaches the destination (phone or SIP). On answer, SVAML puts that leg into a bridge and fires a second `dial` to the ElevenLabs SIP endpoint, which also joins the bridge.

In both cases, the `bridgeCall` command on each leg's `onAnswer` is what connects the audio. The bridge name (`"sip-bridge"` or `"bridge"` in the examples) is arbitrary but must match across both legs within the same session.

### SIP transport

The ElevenLabs SIP endpoint requires `"transport": "TCP"` (at the time of writing). If omitted, the default is UDP, which may cause the SIP `INVITE` to fail or audio to not flow. Verify the current transport requirement in the ElevenLabs documentation.

### Hangup propagation

Each scenario includes `onHangup` handlers on both the caller/origin leg and the agent leg so that when either party disconnects, the other leg is torn down. Without these, the surviving leg would remain connected (and billable) until `maxCallDurationSeconds` expires.

## Audio considerations

SIP audio negotiation happens at the SIP level between Sinch and ElevenLabs, so there is no manual sample-rate alignment like the WebSocket bridge requires. The two platforms negotiate codecs during SIP session setup. If you hear degraded audio quality, check:

- That the ElevenLabs agent's audio configuration matches what Sinch is offering during SDP negotiation.
- That `transport: "TCP"` is set on the ElevenLabs `to` leg (UDP may cause packet loss on some paths).
- Network connectivity between your Sinch region and ElevenLabs' SIP infrastructure.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `400` on the PATCH or POST | Malformed SVAML. Check that the `to.type` is `"SIP"` and `sip.endpoint` is a valid SIP URI. |
| `401` | Bad or missing Basic Auth credentials. |
| `404` on the PATCH | Unknown `projectId` or `serviceId`. |
| Inbound calls are not answered | The service's `callBehavior` was not patched, or the phone number is not assigned to the service. |
| ElevenLabs leg times out | The SIP URI is wrong, ElevenLabs' SIP service is unreachable, or the transport does not match. Verify `ELEVENLABS_SIP_URI` and `transport`. |
| Audio flows one way only | Transport mismatch or firewall blocking RTP. Confirm `transport: "TCP"` and check network path. |
| Agent does not greet the caller | The ElevenLabs agent may not have a first message configured, or the Phone/SIP channel is not enabled on the agent. Check the ElevenLabs dashboard. |

## Production-readiness checklist

| Concern | What to do |
| --- | --- |
| **Call duration caps** | Set `maxCallDurationSeconds` to bound costs. The inbound examples default to 7200 s (2 h); outbound to 180 s. Tune these to your use case. |
| **Hangup propagation** | Both legs need mutual `onHangup` handlers. The examples include them; do not remove them. |
| **ElevenLabs costs** | ElevenLabs bills per minute of agent usage. Cap exposure with `maxCallDurationSeconds`. |
| **Failover** | If the ElevenLabs SIP endpoint is unreachable, the agent `dial` will time out and the caller hears nothing. Consider adding an `onTimeout` or `onFailure` handler on the agent leg to play a fallback TTS message or route to a human. |
| **Idempotency (outbound)** | For outbound calls, send an `Idempotency-Key` header to make retries safe. See [Make an Outbound Call](/docs/voice/tutorials/outbound-call) for details. |
| **AMD (outbound PSTN)** | If dialing mobile numbers that may go to voicemail, insert an `amd` command before bridging. See [AMD](/docs/voice/tutorials/amd). |
| **Recording** | If you need call recordings, add `startRecording` inside `onAnswer`. See [Recording & Transcription](/docs/voice/tutorials/recording-and-transcription). |
| **Monitoring** | Use the `sessionId` from the `POST` response (or retrieve it for inbound calls) with `GET /v2/projects/{projectId}/sessions/{sessionId}` to inspect call legs and outcomes. See [Track Call Status](/docs/voice/tutorials/track-call-status). |

## API reference (at a glance)

- `PATCH /v2/projects/{projectId}/services/{serviceId}`: sets the service's `callBehavior`. `type: "STATIC"` means every inbound call executes the same inline SVAML, no webhook needed.
- `POST /v2/projects/{projectId}/calls`: creates an outbound call session. Returns `201` with `projectId`, `serviceId`, `sessionId`.
- `to: { type: "SIP", sip: { endpoint, transport } }`: the SIP destination type. `endpoint` is a SIP URI (required). `transport` is `"UDP"` (default), `"TCP"`, or `"TLS"`.
- `bridgeCall`: joins the current call leg to a named bridge. Two legs in the same bridge exchange audio bidirectionally.
- `from`: the originating identity. Uses `type: "PHONE"` with a Sinch virtual number in these examples. Also supports `type: "SIP"`.
- `dialTimeoutDurationSeconds`: how long to wait for the destination to answer.
- `maxCallDurationSeconds`: hard ceiling on the answered call. The call is terminated automatically when reached.