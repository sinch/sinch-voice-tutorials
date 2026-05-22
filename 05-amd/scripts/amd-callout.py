# Sinch AMD Callout — outbound call with Answering Machine Detection (AMD).
# AMD detects human vs. machine and executes different SVAML for each outcome.
# Requirements: pip install requests python-dotenv

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

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
        print(f"ERROR: {name} is not set.", file=sys.stderr)
        sys.exit(1)

url = f"https://voice.api.sinch.com/v2/projects/{project_id}/calls"

# The `amd` command must be placed in the `onAnswer` event of a `dial` command.
# It fires different SVAML commands based on what AMD detects.
payload = {
    "commands": [
        {
            "command": "dial",
            "name": "amd-call",
            "from": {"type": "PHONE", "phone": {"number": sinch_number}},
            "to":   {"type": "PHONE", "phone": {"number": destination_number}},
            "dialTimeout": "45s",
            "maxDuration": "5m",
            "events": {
                "onAnswer": [
                    {
                        "command": "amd",
                        "events": {
                            # Human picked up: play a personalized greeting
                            "onHuman": [
                                {
                                    "command": "messages",
                                    "name": "human-greeting",
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
                                    "name": "voicemail-message",
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
