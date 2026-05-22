# Sinch Voice Callout — dials a phone number, plays an audio file, then a TTS message.
# Requirements: pip install requests python-dotenv

import os
import sys
import requests
from dotenv import load_dotenv

# Load credentials from project root .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

project_id         = os.environ.get("PROJECT_ID")
key_id             = os.environ.get("KEY_ID")
key_secret         = os.environ.get("KEY_SECRET")
sinch_number       = os.environ.get("SINCH_NUMBER")
destination_number = os.environ.get("DESTINATION_NUMBER")

for var, name in [
    (project_id, "PROJECT_ID"),
    (key_id, "KEY_ID"),
    (key_secret, "KEY_SECRET"),
    (sinch_number, "SINCH_NUMBER"),
    (destination_number, "DESTINATION_NUMBER"),
]:
    if not var:
        print(f"ERROR: {name} is not set. Copy .env.example to .env and fill in your credentials.", file=sys.stderr)
        sys.exit(1)

base_url = f"https://voice.api.sinch.com/v2/projects/{project_id}/calls"

# SVAML payload: dial -> on answer play audio file -> hangup
payload = {
    "commands": [
        {
            "command": "dial",
            "name": "audio-notification",
            "from": {
                "type": "PHONE",
                "phone": {"number": sinch_number}
            },
            "to": {
                "type": "PHONE",
                "phone": {"number": destination_number}
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
                                {"command": "hangup"}
                            ]
                        }
                    }
                ]
            }
        }
    ]
}

print(f"Placing callout from {sinch_number} to {destination_number} ...")

try:
    response = requests.post(
        base_url,
        json=payload,
        auth=(key_id, key_secret)
    )
    data = response.json()

    if response.status_code == 201:
        print("Call created successfully:")
        import json
        print(json.dumps(data, indent=2))
    else:
        print(f"ERROR {response.status_code}:", file=sys.stderr)
        import json
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)

except requests.RequestException as e:
    print(f"Request failed: {e}", file=sys.stderr)
    sys.exit(1)
