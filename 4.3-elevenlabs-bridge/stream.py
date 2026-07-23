import requests
import os
import sys
from dotenv import load_dotenv
# To have USERNAME and PASSWORD
load_dotenv() 
PROJECT_ID = os.getenv("PROJECT_ID")
KEY_ID = os.getenv("KEY_ID")
KEY_SECRET = os.getenv("KEY_SECRET")
DESTINATION_NUMBER = os.getenv("DESTINATION_NUMBER")
SINCH_NUMBER = os.getenv("SINCH_NUMBER")
WS_URL = os.getenv("WS_URL")

url = "https://voice.api.sinch.com/v2/projects/" + PROJECT_ID + "/calls"

payload = {
    "commands": [
        {
            "command": "dial",
            "callName": "origin",
            "from": {"type":"PHONE","phone":  {"number":      SINCH_NUMBER}},
            "to":   {"type":"PHONE","phone":  {"number":DESTINATION_NUMBER}},
            "dialTimeoutDurationSeconds": 30,
            "maxCallDurationSeconds": 180,
            "events": {
                "onAnswer": [
                    {"command":"bridgeCall","bridgeName":"bridge"},
                    {
                        "command": "dial",
                        "callName": "connect_stream",
                        "from": {"type":"PHONE","phone":{"number":SINCH_NUMBER}},
                        "to": {
                            "type": "STREAM",
                            "stream": {
                                "endpoint": WS_URL,
                                "streamOptions": {"version":1,"codec":"PCM","sampleRate":8000},
                                "callHeaders": [{"key":"X-Timeout-Seconds","value":"10"}]
                            }
                        },
                        "events": {
                            "onAnswer": [{"command":"bridgeCall","bridgeName":"bridge"}]
                        }
                    }
                ],
                "onHangup": [
                    {"command":"hangup","callName":"connect_stream"}
                ]
            }
        }
    ]
}




headers = {"Content-Type": "application/json"}

try:
    response = requests.post(url, json=payload, headers=headers, auth=(KEY_ID,KEY_SECRET))
    data = response.json()
    print(data)
except Exception as e:
    print(e)