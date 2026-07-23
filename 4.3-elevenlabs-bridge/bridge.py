#!/usr/bin/env python3
"""
Sinch Outbound Stream → ElevenLabs Conversational AI WebSocket Bridge

Protocol flow (per stream-out.asyncapi.yml):
  1. Sinch sends ConnectRequest  (JSON, command="connect")
  2. We reply   ConnectResponse  (JSON, command="answer")
  3. Binary PCM audio frames flow in both directions
  4. Sinch may send StreamControl JSON frames (heartbeat / clear)
"""

import asyncio
import base64
import json
import logging
import os

import websockets
from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sinch-el-bridge")

# ── Config (all values come from .env) ────────────────────────────────────────
PORT: int = int(os.getenv("PORT", "8765"))
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID: str = os.getenv("ELEVENLABS_AGENT_ID", "")
# Output format sent to ElevenLabs — must match what Sinch expects.
# Sinch telephony is typically 8 kHz linear PCM → "pcm_8000".
# If your Sinch stream is configured for 16 kHz use "pcm_16000".
ELEVENLABS_OUTPUT_FORMAT: str = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_8000")
# Input format Sinch sends to us — ElevenLabs must know this to decode correctly.
# Must match the sample rate Sinch is actually streaming (default 8 kHz).
ELEVENLABS_INPUT_FORMAT: str = os.getenv("ELEVENLABS_INPUT_FORMAT", "pcm_8000")
# How long (seconds) to wait for the initial ConnectRequest before closing
CONNECT_TIMEOUT: float = float(os.getenv("CONNECT_TIMEOUT_SECONDS", "10"))


def elevenlabs_ws_url() -> str:
    return (
        f"wss://api.elevenlabs.io/v1/convai/conversation"
        f"?agent_id={ELEVENLABS_AGENT_ID}"
        f"&output_format={ELEVENLABS_OUTPUT_FORMAT}"
        f"&input_audio_format={ELEVENLABS_INPUT_FORMAT}"
    )


# ── ElevenLabs → Sinch ────────────────────────────────────────────────────────
async def el_to_sinch(el_ws, sinch_ws, call_id: str) -> None:
    """Forward ElevenLabs events to Sinch; decode audio to binary PCM frames."""
    async for raw in el_ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[%s] Non-JSON from ElevenLabs (ignored)", call_id)
            continue

        msg_type = msg.get("type")

        if msg_type == "conversation_initiation_metadata":
            meta = msg.get("conversation_initiation_metadata_event", {})
            logger.info(
                "[%s] ElevenLabs conversation started — conv_id=%s",
                call_id,
                meta.get("conversation_id", "?"),
            )

        elif msg_type == "audio":
            audio_b64 = msg.get("audio_event", {}).get("audio_base_64", "")
            if audio_b64:
                await sinch_ws.send(base64.b64decode(audio_b64))

        elif msg_type == "ping":
            event_id = msg.get("ping_event", {}).get("event_id")
            await el_ws.send(json.dumps({"type": "pong", "event_id": event_id}))

        elif msg_type == "agent_response":
            text = msg.get("agent_response_event", {}).get("agent_response", "")
            logger.info("[%s] Agent : %s", call_id, text)

        elif msg_type == "user_transcript":
            text = msg.get("user_transcription_event", {}).get("user_transcript", "")
            logger.info("[%s] User  : %s", call_id, text)

        elif msg_type == "interruption":
            logger.info("[%s] User interrupted agent — sending clear to Sinch", call_id)
            await sinch_ws.send(json.dumps({"command": "clear"}))

        elif msg_type == "internal_tentative_agent_response":
            pass  # verbose; skip

        else:
            logger.debug("[%s] ElevenLabs event: %s", call_id, msg_type)


# ── Sinch → ElevenLabs ────────────────────────────────────────────────────────
async def sinch_to_el(sinch_ws, el_ws, call_id: str) -> None:
    """
    Forward Sinch messages to ElevenLabs.
      - Binary frames  → base64-wrapped user_audio_chunk
      - JSON control   → handled locally (heartbeat / clear)
    """
    first_frame = True
    async for message in sinch_ws:
        if isinstance(message, bytes):
            if first_frame:
                logger.info("[%s] First Sinch audio frame: %d bytes", call_id, len(message))
                first_frame = False
            audio_b64 = base64.b64encode(message).decode()
            await el_ws.send(json.dumps({"user_audio_chunk": audio_b64}))
        else:
            try:
                ctrl = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("[%s] Non-JSON text from Sinch (ignored)", call_id)
                continue

            cmd = ctrl.get("command")
            if cmd == "heartbeat":
                logger.debug("[%s] Heartbeat", call_id)
            elif cmd == "clear":
                # ElevenLabs has no explicit buffer-clear command; log only.
                logger.info("[%s] Clear requested by Sinch (no-op on ElevenLabs)", call_id)
            else:
                logger.warning("[%s] Unknown StreamControl command: %s", call_id, cmd)


# ── Bridge ────────────────────────────────────────────────────────────────────
async def bridge_call(sinch_ws, call_id: str) -> None:
    """Open an ElevenLabs WebSocket and run both forwarding loops concurrently."""
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    async with websockets.connect(elevenlabs_ws_url(), additional_headers=headers) as el_ws:
        logger.info("[%s] ElevenLabs WebSocket connected", call_id)

        tasks = [
            asyncio.create_task(el_to_sinch(el_ws, sinch_ws, call_id), name="el→sinch"),
            asyncio.create_task(sinch_to_el(sinch_ws, el_ws, call_id), name="sinch→el"),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for t in pending:
            t.cancel()

        # Propagate any unexpected exception from the finished task
        for t in done:
            exc = t.exception()
            if exc:
                raise exc


# ── Connection handler ────────────────────────────────────────────────────────
async def handle_connection(websocket) -> None:
    """Entry point for every incoming Sinch WebSocket connection."""
    call_id = "pending"
    try:
        # Step 1 — receive ConnectRequest
        raw = await asyncio.wait_for(websocket.recv(), timeout=CONNECT_TIMEOUT)
        req = json.loads(raw)

        if req.get("command") != "connect":
            logger.warning("First message was not 'connect': %s", req)
            return

        call_id = req.get("callId", "unknown")
        logger.info(
            "[%s] ConnectRequest — appId=%s headers=%s",
            call_id,
            req.get("applicationId", ""),
            req.get("headers", {}),
        )

        # Step 2 — answer the call
        await websocket.send(json.dumps({"command": "answer"}))
        logger.info("[%s] Answered", call_id)

        # Step 3 — bridge audio
        await bridge_call(websocket, call_id)

    except asyncio.TimeoutError:
        logger.warning("[%s] Timed out waiting for ConnectRequest", call_id)
    except websockets.exceptions.ConnectionClosedOK:
        logger.info("[%s] Connection closed cleanly", call_id)
    except websockets.exceptions.ConnectionClosedError as exc:
        logger.warning("[%s] Connection closed with error: %s", call_id, exc)
    except Exception as exc:
        logger.error("[%s] Unhandled error: %s", call_id, exc, exc_info=True)
    finally:
        logger.info("[%s] Session ended", call_id)


# ── Entry point ───────────────────────────────────────────────────────────────
async def main() -> None:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in .env")
    if not ELEVENLABS_AGENT_ID:
        raise RuntimeError("ELEVENLABS_AGENT_ID is not set in .env")

    logger.info("Bridge listening on ws://0.0.0.0:%d", PORT)
    async with websockets.serve(handle_connection, "0.0.0.0", PORT):
        await asyncio.Future()  # run until interrupted


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down")
