# Sinch WebSocket Agent — ICE (Incoming Call Event) webhook server — Flask.
# When an inbound call arrives at your Sinch number, responds with SVAML
# to route the call audio to your WebSocket server.
# Requirements: pip install flask python-dotenv

import os
import sys
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

sinch_number = os.environ.get("SINCH_NUMBER") or exit("ERROR: SINCH_NUMBER not set")
# WS_ENDPOINT: your publicly accessible WebSocket URL (e.g. from ngrok)
ws_endpoint  = os.environ.get("WS_ENDPOINT")  or exit("ERROR: WS_ENDPOINT not set — run ngrok and export wss://...")
port         = int(os.environ.get("PORT", 8081))

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handles Sinch incoming call events and responds with SVAML to connect to WebSocket."""
    body  = request.json
    event = body.get("event")
    call  = body.get("call")

    print(f"Received event: {event}")

    if event == "INCOMING":
        # Inbound call to your Sinch number.
        # Respond with SVAML to bridge the phone call to the WebSocket stream.
        caller_number = call.get("from", {}).get("phone", {}).get("number", "unknown")

        svaml_response = {
            "commands": [
                {
                    "command": "accept",
                    "commands": [
                        # Add the phone leg to a named audio bridge
                        {"command": "bridgeCall", "name": "stream-bridge"},

                        # Dial the WebSocket stream endpoint — your AI agent
                        {
                            "command": "dial",
                            "name": "stream-leg",
                            "to": {
                                "type": "STREAM",
                                "stream": {
                                    "endpoint": ws_endpoint,       # e.g. wss://abc.ngrok-free.app
                                    "streamOptions": {
                                        "version": 1,
                                        "codec": "PCM",
                                        "sampleRate": 8000         # 8 kHz standard for PSTN
                                    },
                                    # Optional: pass caller info as custom headers to your WS server
                                    "callHeaders": [
                                        {"key": "X-Call-From", "value": caller_number}
                                    ]
                                }
                            },
                            "dialTimeout": "10s",
                            "events": {
                                # WebSocket server answers -> add stream leg to the same bridge
                                "onAnswer": [{"command": "bridgeCall", "name": "stream-bridge"}],
                                # Stream disconnects -> hang up the phone call
                                "onHangup": [{"command": "hangup", "callName": "inbound"}]
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
    print(f"ICE webhook server listening on port {port}")
    print(f"Set your Sinch service webhook URL to: http://localhost:{port}/webhook")
    print(f"WebSocket endpoint: {ws_endpoint}")
    print(f"(Use ngrok: ngrok http {port})")
    app.run(host="0.0.0.0", port=port)
