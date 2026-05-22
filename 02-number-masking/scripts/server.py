# Sinch Number Masking — Flask webhook server.
# Handles inbound call events and responds with SVAML to anonymously bridge calls.
# Requirements: pip install flask python-dotenv

import os
import sys
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load credentials from project root .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

sinch_number       = os.environ.get("SINCH_NUMBER")
destination_number = os.environ.get("DESTINATION_NUMBER")

for var, name in [(sinch_number, "SINCH_NUMBER"), (destination_number, "DESTINATION_NUMBER")]:
    if not var:
        print(f"ERROR: {name} is not set.", file=sys.stderr)
        sys.exit(1)

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receives Sinch call events and responds with SVAML commands."""
    body  = request.get_json(force=True)
    event = body.get("data", {}).get("event")
    call  = body.get("data", {}).get("call", {})

    print(f"Received webhook event: {event}")
    print(json.dumps(call, indent=2))

    if event == "call.incoming":
        # Inbound call to the Sinch number from Party A.
        # Respond with SVAML to bridge Party A anonymously to Party B.
        svaml_response = {
            "commands": [
                {
                    "command": "accept",
                    "commands": [
                        # Play a short greeting while the second leg is being dialed
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

                        # Add Party A to a named bridge
                        {"command": "bridgeCall", "name": "main-bridge"},

                        # Dial Party B from the Sinch number (masks Party A's real number)
                        {
                            "command": "dial",
                            "name": "callee",
                            "from": {
                                "type": "PHONE",
                                "phone": {"number": sinch_number}   # Party B sees the Sinch number
                            },
                            "to": {
                                "type": "PHONE",
                                # In production, look up the destination from your DB
                                # based on the called Sinch number (call["to"])
                                "phone": {"number": destination_number}
                            },
                            "dialTimeout": "30s",
                            "events": {
                                # Party B answers -> add them to the bridge so audio flows
                                "onAnswer": [{"command": "bridgeCall", "name": "main-bridge"}],
                                # Party B hangs up -> terminate Party A's leg too
                                "onHangup": [{"command": "hangup", "callName": "inbound"}]
                            }
                        }
                    ]
                }
            ]
        }
        return jsonify(svaml_response), 200

    # Acknowledge all other events with an empty command list
    print(f"Unhandled event: {event}")
    return jsonify({"commands": []}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"Number masking webhook server listening on port {port}")
    print(f"Set your Sinch service webhook URL to: http://localhost:{port}/webhook")
    print(f"(Use ngrok: ngrok http {port})")
    app.run(host="0.0.0.0", port=port)
