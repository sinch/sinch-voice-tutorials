#!/usr/bin/env python3
"""
3.4.5 AI IVR — Voice Relay server that classifies caller intent with an LLM and
patches a human agent into the live call.

Flow per connection:
  1. Sinch sends {"command":"connect", "callId": "..."} -> we answer + greet.
  2. Sinch sends {"command":"text"/"prompt", "text":"<caller speech>"}.
  3. We ask the LLM to classify. One-word reply ("Sales"/"Support") = route;
     anything longer is spoken back as a clarifying question.
  4. On a route, we PATCH /v2/projects/{projectId}/calls/{callId} to dial the
     agent and bridge them into "ivr-bridge", then close the socket.

Requirements: pip install -r ../requirements.txt   (websockets, requests)
Run:    python relay-server.py
Expose: ngrok http 8765
"""

import asyncio
import json
import os

import requests
import websockets

# ── Load the tutorial-folder .env (../.env relative to this scripts/ folder) ──
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ── Configuration ────────────────────────────────────────────────────────────
def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"ERROR: {name} is not set in the environment / .env")
    return val

PROJECT_ID  = _require("PROJECT_ID")
KEY_ID      = _require("KEY_ID")
KEY_SECRET  = _require("KEY_SECRET")
SINCH_NUMBER   = _require("SINCH_NUMBER")
SALES_NUMBER   = _require("SALES_NUMBER")
SUPPORT_NUMBER = _require("SUPPORT_NUMBER")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_API_KEY  = _require("LLM_API_KEY")
LLM_MODEL    = os.environ.get("LLM_MODEL", "gpt-4o-mini")
PORT         = int(os.environ.get("PORT", "8765"))

SINCH_BASE = "https://voice.api.sinch.com/v2"
GREETING   = "Hello, this is the call centre. How can I help you?"

AGENTS = {"sales": (SALES_NUMBER, "Sales"), "support": (SUPPORT_NUMBER, "Support")}

_prompt_path = os.path.join(os.path.dirname(__file__), "..", "system_prompt.md")
with open(_prompt_path) as _f:
    SYSTEM_PROMPT = _f.read().strip()


# ── LLM intent classification (blocking; called via asyncio.to_thread) ───────
def classify_intent(caller_text: str) -> str:
    """Return the model's reply: one word ('Sales'/'Support') or a clarification."""
    resp = requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {LLM_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model": LLM_MODEL,
            "temperature": 0,
            "max_tokens": 20,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": caller_text},
            ],
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── PATCH the live call to bridge in a human agent (blocking) ────────────────
def patch_in_agent(call_id: str, intent_key: str) -> None:
    number, label = AGENTS[intent_key]
    body = {
        "commands": [
            {
                "command": "dial",
                "callName": "agent_call",
                "from": {"type": "PHONE", "phone": {"number": SINCH_NUMBER}},
                "to":   {"type": "PHONE", "phone": {"number": number}},
                "dialTimeoutDurationSeconds": 20,
                "maxCallDurationSeconds": 3600,
                "events": {
                    "onAnswer": [
                        {"command": "bridgeCall", "bridgeName": "ivr-bridge"},
                        {"command": "messages", "messagesName": "agent-intro",
                         "messages": [{"type": "SAY", "say": {
                             "format": "TEXT",
                             "text": f"Connecting you to a customer. Intent: {label}.",
                             "voiceName": "Tiffany"}}]},
                    ],
                    "onHangup": [{"command": "hangup", "callName": "caller"}],
                },
            }
        ]
    }
    resp = requests.patch(
        f"{SINCH_BASE}/projects/{PROJECT_ID}/calls/{call_id}",
        auth=(KEY_ID, KEY_SECRET),
        headers={"Content-Type": "application/json",
                 "Idempotency-Key": f"{call_id}-{intent_key}"},
        json=body,
        timeout=10,
    )
    if resp.status_code != 202:
        raise RuntimeError(f"PATCH returned {resp.status_code}: {resp.text}")


# ── WebSocket session ────────────────────────────────────────────────────────
async def send(ws, payload: dict) -> None:
    raw = json.dumps(payload)
    print(f"  >> {raw}")
    await ws.send(raw)


async def handle_connection(ws):
    call_id = None
    patched = False
    print(f"[+] connected: {ws.remote_address}")
    try:
        async for raw in ws:
            print(f"  << {raw}")
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            command = msg.get("command")

            if command == "connect":
                call_id = msg.get("callId")
                await send(ws, {"command": "answer"})
                await send(ws, {"command": "text", "text": GREETING, "isLast": True})

            elif command in ("text", "prompt") and call_id and not patched:
                caller_text = (msg.get("text") or "").strip()
                if not caller_text:
                    continue
                try:
                    reply = await asyncio.to_thread(classify_intent, caller_text)
                except Exception as exc:
                    print(f"[!] classify failed: {exc}")
                    await send(ws, {"command": "text",
                                    "text": "Sorry, please try again.", "isLast": True})
                    continue

                intent_key = reply.lower()
                if intent_key in AGENTS:  # one-word, known route
                    _, label = AGENTS[intent_key]
                    await send(ws, {"command": "text",
                                    "text": f"Please wait, connecting you to {label}.",
                                    "isLast": True})
                    await asyncio.sleep(2.5)  # let the TTS play before we drop out
                    try:
                        await asyncio.to_thread(patch_in_agent, call_id, intent_key)
                        patched = True
                        print(f"[*] patched {label} into call {call_id}")
                    except Exception as exc:
                        print(f"[!] patch failed: {exc}")
                    await ws.close()
                    return
                else:  # not confident — speak the clarification back
                    await send(ws, {"command": "text", "text": reply, "isLast": True})

    except websockets.exceptions.ConnectionClosed as exc:
        print(f"[-] closed ({exc.code}): {exc.reason}")
    finally:
        print(f"[-] session ended  callId={call_id}")


async def main():
    print(f"[*] AI IVR relay  model={LLM_MODEL}  listening on ws://0.0.0.0:{PORT}")
    async with websockets.serve(handle_connection, "0.0.0.0", PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
