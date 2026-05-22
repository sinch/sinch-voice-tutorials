# Number Masking (Anonymous Call Bridging)

## Overview

Number masking lets two parties speak over a bridged phone call without either party ever seeing the other's real phone number. Instead, both parties see only your Sinch virtual number as the caller ID. The Sinch Voice API handles this by: accepting an inbound call from Party A to your Sinch number, your webhook server responds with SVAML to dial Party B using the Sinch number as the origin, and then bridges both call legs together via the `bridgeCall` command. Neither party's real phone number is exposed at any point. When either party hangs up, the bridge tears down and the other leg is also terminated.

## Real-life examples

- **Ride-sharing**: Driver and passenger communicate without sharing personal numbers. The app provides a masked Sinch number for each ride.
- **Marketplace transactions**: Buyer and seller can call each other through the platform without revealing their real numbers.
- **Healthcare**: Patient calls a Sinch number to reach their doctor, who sees only the clinic's virtual number.
- **Delivery services**: Delivery agent and recipient coordinate via a disposable Sinch number that expires after the delivery.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with a project and API credentials.
- A Sinch virtual phone number configured with a **Webhook** call behavior pointing to your server's `/webhook` endpoint.
- A publicly accessible callback URL (use [ngrok](https://ngrok.com) during development).
- Node.js 18+, Python 3.8+, PHP 8+, or Java 11+ depending on the server you choose.

## Step-by-step instructions

### 1. Configure your Sinch service

In the [Sinch Dashboard](https://dashboard.sinch.com/voice/services), set your service's **Call Behavior** to `WEBHOOK` and point it to:

```
https://your-ngrok-url.ngrok.io/webhook
```

Or via the API:

```bash
curl -X PATCH \
  -u "$KEY_ID:$KEY_SECRET" \
  "https://voice.api.sinch.com/v2/projects/$PROJECT_ID/services/$SERVICE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "callBehavior": {
      "type": "WEBHOOK",
      "webhook": {
        "url": "https://your-ngrok-url.ngrok.io/webhook"
      }
    }
  }'
```

### 2. Start the callback server

```bash
# Node.js
node scripts/server.node.js

# Python
python scripts/server.py

# PHP (requires Slim 4)
php -S 0.0.0.0:3000 scripts/server.php

# Java (Spring Boot — build and run the jar)
mvn spring-boot:run -f scripts/Server.java
```

### 3. How the webhook flow works

When Party A calls your Sinch virtual number:

1. Sinch sends a `POST` to your webhook URL with a JSON body like:
```json
{
  "specversion": "1.0",
  "type": "com.sinch.voice.webhook.v1",
  "id": "...",
  "time": "2026-01-01T00:00:00Z",
  "source": "projects/...",
  "data": {
    "event": "call.incoming",
    "call": { "callId": "...", "from": {...}, "to": {...}, ... }
  }
}
```

2. Your server responds with SVAML commands:
```json
{
  "commands": [
    {
      "command": "accept",
      "commands": [
        {
          "command": "messages",
          "name": "greeting",
          "messages": [
            {
              "type": "SAY",
              "say": {
                "text": "Please hold while we connect your call.",
                "voiceName": "Emma"
              }
            }
          ]
        },
        { "command": "bridgeCall", "name": "main-bridge" },
        {
          "command": "dial",
          "name": "callee",
          "from": { "type": "PHONE", "phone": { "number": "+1SINCH_NUMBER" } },
          "to":   { "type": "PHONE", "phone": { "number": "+1PARTY_B_NUMBER" } },
          "events": {
            "onAnswer":  [{ "command": "bridgeCall", "name": "main-bridge" }],
            "onHangup":  [{ "command": "hangup", "callName": "inbound" }]
          }
        }
      ]
    }
  ]
}
```

3. Party B receives a call from the Sinch number (not Party A's real number).
4. When Party B answers, both legs join the same bridge and can talk.
5. When either party hangs up, the `onHangup` event terminates the other leg.

### 4. Trigger a test call

You can also trigger a programmatic number-masking call via the API (outbound masking):

```bash
bash scripts/test-call.sh
```

This makes an API call that dials both parties programmatically and bridges them.

### 5. Number mapping

In a real application, your webhook server would look up the destination number from a database based on the inbound call's `to` number (the Sinch virtual number called). The example server uses `DESTINATION_NUMBER` from the environment for simplicity.
