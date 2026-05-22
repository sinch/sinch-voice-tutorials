# Sinch AMD Callback Server — Flask webhook server.
# Handles inbound call events and responds with SVAML including the AMD command.
# Requirements: pip install flask python-dotenv

import os
import sys
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

sinch_number       = os.environ.get("SINCH_NUMBER")
destination_number = os.environ.get("DESTINATION_NUMBER")

for var, name in [(sinch_number, "SINCH_NUMBER"), (destination_number, "DESTINATION_NUMBER")]:
    if not var:
        print(f"ERROR: {name} is not set.", file=sys.stderr)
        sys.exit(1)

port = int(os.environ.get("PORT", 3000))
app  = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handles Sinch call events and responds with AMD SVAML."""
    body  = request.get_json(force=True)
    event = body.get("data", {}).get("event")
    call  = body.get("data", {}).get("call", {})

    print(f"Received event: {event}, callId: {call.get('callId')}")

    if event == "call.incoming":
        # Inbound call: answer and run AMD.
        # AMD fires one of: onHuman, onMachine, onBeep, onUnknown.
        svaml_response = {
            "commands": [
                {
                    "command": "accept",
                    "commands": [
                        # AMD detection — must be the first command after answering
                        {
                            "command": "amd",
                            "events": {
                                # Live human: play a personalized greeting
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
                                        "events": {"onFinish": [{"command": "hangup"}]}
                                    }
                                ],

                                # Machine greeting (no beep yet): hang up silently
                                "onMachine": [{"command": "hangup"}],

                                # Beep detected: leave voicemail right after the beep
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
                                        "events": {"onFinish": [{"command": "hangup"}]}
                                    }
                                ],

                                # Unknown result: hang up safely
                                "onUnknown": [{"command": "hangup"}]
                            }
                        }
                    ]
                }
            ]
        }
        return jsonify(svaml_response), 200

    print(f"Unhandled event: {event}")
    return jsonify({"commands": []}), 200


if __name__ == "__main__":
    print(f"AMD callback server listening on port {port}")
    print(f"Set your Sinch service webhook URL to: http://localhost:{port}/webhook")
    print(f"(Use ngrok: ngrok http {port})")
    app.run(host="0.0.0.0", port=port)
