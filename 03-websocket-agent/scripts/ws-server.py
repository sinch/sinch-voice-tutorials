# Sinch WebSocket Audio Streaming Server — Python (websockets library).
# Receives PCM audio from a live Sinch call and can send audio back.
# Requirements: pip install websockets

import asyncio
import json
import time
import websockets
import os

PORT = int(os.environ.get("WS_PORT", 8765))


async def handle_connection(websocket):
    """Handle a single Sinch WebSocket streaming connection."""
    remote = websocket.remote_address
    print(f"New WebSocket connection from {remote}")

    call_id = None
    application_id = None
    audio_frame_count = 0
    total_bytes = 0

    # Optional: write raw PCM audio to a file for offline analysis
    timestamp = int(time.time())
    pcm_filename = f"call-{timestamp}.pcm"
    pcm_file = open(pcm_filename, "wb")
    print(f"Saving raw PCM audio to {pcm_filename}")

    # Heartbeat task — sends {"command":"heartbeat"} every 5 s during silence
    async def send_heartbeats():
        while True:
            await asyncio.sleep(5)
            try:
                await websocket.send(json.dumps({"command": "heartbeat"}))
            except websockets.exceptions.ConnectionClosed:
                break

    heartbeat_task = None

    try:
        async for message in websocket:
            if isinstance(message, str):
                # Text frame: JSON control message
                try:
                    msg = json.loads(message)
                except json.JSONDecodeError:
                    print(f"Received non-JSON text frame: {message}")
                    continue

                if msg.get("command") == "connect":
                    # ConnectRequest: first message from Sinch when a call arrives.
                    # Contains callId and applicationId. Must reply with {"command":"answer"}.
                    call_id        = msg.get("callId")
                    application_id = msg.get("applicationId")
                    headers        = msg.get("headers", {})
                    print(f"ConnectRequest — callId: {call_id}, appId: {application_id}")
                    print(f"Custom headers: {headers}")

                    # Accept the call
                    await websocket.send(json.dumps({"command": "answer"}))
                    print("Sent ConnectResponse: answer")

                    # Start heartbeat task
                    heartbeat_task = asyncio.create_task(send_heartbeats())

                else:
                    print(f"Received StreamControl or other message: {msg}")

            elif isinstance(message, bytes):
                # Binary frame: raw PCM audio
                audio_frame_count += 1
                total_bytes += len(message)

                # Write to file for offline analysis / AI pipeline
                pcm_file.write(message)

                if audio_frame_count % 100 == 0:
                    print(f"Audio frames: {audio_frame_count} | Bytes: {total_bytes}")

                # --- HERE: plug in your AI / STT processing ---
                # Example:
                #   transcript = await stt_engine.process(message)
                #   if transcript:
                #       audio_response = tts_engine.synthesize(llm_reply(transcript))
                #       await websocket.send(audio_response)  # PCM bytes back to caller
                await websocket.send(message)  # PCM bytes back to caller

    except websockets.exceptions.ConnectionClosedOK:
        print("Connection closed normally")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"Connection closed with error: {e}")
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        pcm_file.close()
        print(f"Call summary — callId: {call_id}, frames: {audio_frame_count}, bytes: {total_bytes}")


async def main():
    print(f"Sinch WebSocket audio server listening on ws://localhost:{PORT}")
    print(f"Expose with ngrok: ngrok http {PORT}")
    print("Then set WS_ENDPOINT=wss://<your-ngrok-id>.ngrok-free.app when triggering a call.\n")

    async with websockets.serve(handle_connection, "0.0.0.0", PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
