# Minimal Sinch Voice VOICE_RELAY server (Python).
# Echoes whatever the caller says back as TTS. Plug in an LLM later.
#
# Requirements: pip install websockets
# Run:    python ws-relay-server.py
# Expose: ngrok http 8765

import asyncio
import json
import os

import websockets

PORT = int(os.environ.get("PORT", "8765"))


async def handler(ws):
    print("new connection")
    try:
        async for msg in ws:
            if isinstance(msg, (bytes, bytearray)):
                # Voice Relay should not deliver binary frames — ignore if it does.
                continue
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                continue
            print("rx", payload)
            cmd = payload.get("command")
            if cmd == "connect":
                await ws.send(json.dumps({"command": "answer"}))
                await ws.send(json.dumps({
                    "command": "text",
                    "text":    "Hi! Anything you say I will repeat back.",
                    "isLast":  True,
                }))
                continue
            if cmd in ("text", "prompt") and payload.get("text"):
                await ws.send(json.dumps({
                    "command": "text",
                    "text":    f"You said: {payload['text']}",
                    "isLast":  True,
                }))
    finally:
        print("connection closed")


async def main():
    async with websockets.serve(handler, "0.0.0.0", PORT):
        print(f"VOICE_RELAY echo server on :{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
