# Minimal Sinch Voice STREAM server (Python).
# Echoes audio back to the caller. Use this to verify the WebSocket plumbing
# before wiring in an actual STT/LLM/TTS pipeline.
#
# Requirements: pip install websockets
# Run:    python ws-stream-server.py
# Expose: ngrok http 8765
# Then set the STREAM `endpoint` in your SVAML to wss://<ngrok-id>.ngrok-free.app

import asyncio
import json
import os

import websockets

PORT = int(os.environ.get("PORT", "8765"))


async def heartbeat(ws):
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send(json.dumps({"command": "heartbeat"}))
    except websockets.exceptions.ConnectionClosed:
        return


async def handler(ws):
    print(f"new connection from {ws.remote_address}")
    hb = asyncio.create_task(heartbeat(ws))
    try:
        async for msg in ws:
            if isinstance(msg, (bytes, bytearray)):
                # Binary frame == raw PCM. Echo it back.
                await ws.send(bytes(msg))
                continue
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                continue
            print("text frame", payload)
            if payload.get("command") == "connect":
                await ws.send(json.dumps({"command": "answer"}))
    finally:
        hb.cancel()
        print("connection closed")


async def main():
    async with websockets.serve(handler, "0.0.0.0", PORT):
        print(f"STREAM echo server on :{PORT}")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
