# Sinch Recording & Transcription — Flask webhook server.
# Starts recording when a call is answered and uploads to cloud storage.
# Requirements: pip install flask python-dotenv

import os
import sys
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

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
    call  = body.get("call")

    print(f"Received event: {event}, callId: {call.get('callId')}")

    if event == "INCOMING":
        # Inbound call: answer, start recording, play notice
        svaml_response = {
            "commands": [
                {
                    "command": "accept",
                    "commands": [
                        # Start recording immediately on answer
                        {
                            "command": "startRecording",
                            "name": "main-recording",
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
                            "name": "recording-notice",
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
                        # {"command": "bridgeCall", "name": "agent-bridge"},
                        # {"command": "dial", "name": "agent", "to": {...}}
                    ]
                }
            ]
        }
        return jsonify(svaml_response), 200

    print(f"Unhandled event: {event}")
    return jsonify({"commands": []}), 200


if __name__ == "__main__":
    print(f"Recording webhook server listening on port {port}")
    print(f"Storage: {storage_destination} → {storage_destination_url}")
    print(f"(Use ngrok: ngrok http {port})")
    app.run(host="0.0.0.0", port=port)
