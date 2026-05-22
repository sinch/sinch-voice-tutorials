#!/usr/bin/env python3
"""
Agent Relay WebSocket server — port 8765.
Uses LangChain to support OpenAI, Anthropic Claude, and Google Gemini.

Protocol (from agent-relay.asyncapi.yml):
  1. Sinch sends  {"command": "connect", ...}
  2. Server sends {"command": "answer"}
  3. Sinch sends  {"command": "prompt"/"text", "text": "<transcribed speech>", ...}
  4. Server streams LLM reply back as {"command": "text", "text": "...", "isLast": false|true}
  5. Other inbound commands (interrupt, dtmf, textPlayback*) are logged and ignored.
"""

import asyncio
import json
import os
from dotenv import load_dotenv
import websockets
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
PROVIDER = os.getenv("PROVIDER", "openai").lower()  # openai | claude | gemini
API_KEY  = os.getenv("API_KEY", "")
PORT     = int(os.getenv("PORT", "8765"))

_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "claude": "claude-haiku-4-5-20251001",
    "gemini": "gemini-2.0-flash",
}
MODEL       = os.getenv("MODEL",       _DEFAULT_MODELS.get(PROVIDER, "gpt-4o"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS  = int(os.getenv("MAX_TOKENS",    "1024"))
GREETING    = os.getenv("GREETING", "Hello!")

# ── System prompt ──────────────────────────────────────────────────────────────
_system_prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.md")
if os.path.exists(_system_prompt_path):
    with open(_system_prompt_path) as _f:
        SYSTEM_PROMPT = _f.read().strip()
    print(f"[*] Loaded system prompt ({len(SYSTEM_PROMPT)} chars)")
else:
    SYSTEM_PROMPT = ""

# ── LLM initialisation ─────────────────────────────────────────────────────────
def _build_llm():
    if PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=MODEL,
            api_key=API_KEY,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
    if PROVIDER == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=MODEL,
            api_key=API_KEY,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
    if PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=MODEL,
            google_api_key=API_KEY,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
        )
    raise ValueError(f"Unknown PROVIDER={PROVIDER!r}. Use 'openai', 'claude', or 'gemini'.")

LLM = _build_llm()

# ── LLM streaming ──────────────────────────────────────────────────────────────
def _to_lc_messages(history: list[dict]) -> list:
    msgs = []
    if SYSTEM_PROMPT:
        msgs.append(SystemMessage(content=SYSTEM_PROMPT))
    for entry in history:
        if entry["role"] == "user":
            msgs.append(HumanMessage(content=entry["content"]))
        elif entry["role"] == "assistant":
            msgs.append(AIMessage(content=entry["content"]))
    return msgs


async def invoke_llm(history: list[dict]) -> str:
    """Return the full LLM reply as a single string."""
    response = await LLM.ainvoke(_to_lc_messages(history))
    return response.content


# ── WebSocket helpers ──────────────────────────────────────────────────────────
def _log_ws(direction: str, raw: str) -> None:
    preview = raw if len(raw) <= 200 else raw[:200] + "…"
    print(f"  WS {direction} {preview}")


async def _send(websocket, payload: str) -> None:
    _log_ws(">>", payload)
    await websocket.send(payload)


# ── Connection handler ─────────────────────────────────────────────────────────
async def handle_connection(websocket):
    """Handle a single Agent Relay WebSocket session."""
    history: list[dict] = []
    session_info: dict = {}

    print(f"[+] Connected: {websocket.remote_address}")

    try:
        async for raw in websocket:
            _log_ws("<<", raw)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[!] Invalid JSON: {raw!r}")
                continue

            command = msg.get("command")

            # ── connect ───────────────────────────────────────────────────────
            if command == "connect":
                session_info = msg
                print(f"    connect  callId={msg.get('callId')}  serviceId={msg.get('serviceId')}")
                await _send(websocket, json.dumps({"command": "answer"}))
                if GREETING:
                    await _send(websocket, json.dumps({
                        "command": "text",
                        "text": GREETING,
                        "isLast": True,
                        "isInterruptible": True,
                    }))
                    history.append({"role": "assistant", "content": GREETING})

            # ── text/prompt (transcribed speech → LLM → TTS response) ─────────
            elif command in ("text", "prompt"):
                user_text = msg.get("text", "").strip()
                if not user_text:
                    continue
                print(f"    STT → {user_text!r}")
                history.append({"role": "user", "content": user_text})

                try:
                    full_reply = await invoke_llm(history)
                    print(f"    LLM ← {full_reply[:80]!r}{'…' if len(full_reply) > 80 else ''}")
                    await _send(websocket, json.dumps({
                        "command": "text",
                        "text": full_reply,
                        "isLast": True,
                        "isInterruptible": True,
                    }))
                    history.append({"role": "assistant", "content": full_reply})

                except Exception as exc:
                    print(f"[!] LLM error: {exc}")

            # ── interrupt (speech detected during TTS playback) ───────────────
            elif command == "interrupt":
                print(f"    interrupt-detect  reason={msg.get('reason')}")

            # ── dtmf received ─────────────────────────────────────────────────
            elif command == "dtmf":
                print(f"    DTMF received  sequence={msg.get('sequence')!r}")

            # ── playback events ───────────────────────────────────────────────
            elif command in ("textPlaybackStart", "textPlaybackStop", "textPlaybackCancel"):
                print(f"    playback  event={command}  batch={msg.get('batchSequence')}")

            else:
                print(f"    unknown command: {command!r}")

    except websockets.exceptions.ConnectionClosed as exc:
        print(f"[-] Connection closed ({exc.code}): {exc.reason}")
    except Exception as exc:
        print(f"[!] Unexpected error: {exc}")
    finally:
        print(f"[-] Session ended  callId={session_info.get('callId', 'unknown')}")


async def main():
    print(f"[*] Provider: {PROVIDER}  Model: {MODEL}  Temp: {TEMPERATURE}  MaxTokens: {MAX_TOKENS}")
    print(f"[*] Agent Relay listening on ws://0.0.0.0:{PORT}")
    async with websockets.serve(handle_connection, "0.0.0.0", PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
