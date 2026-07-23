// 3.4.5 AI IVR — Voice Relay server that classifies caller intent with an LLM
// and patches a human agent into the live call.
//
// Flow per connection:
//   1. Sinch sends {"command":"connect","callId":"..."} -> we answer + greet.
//   2. Sinch sends {"command":"text"/"prompt","text":"<caller speech>"}.
//   3. We ask the LLM to classify. One-word reply ("Sales"/"Support") = route;
//      anything longer is spoken back as a clarifying question.
//   4. On a route, we PATCH /v2/projects/{projectId}/calls/{callId} to dial the
//      agent and bridge them into "ivr-bridge", then close the socket.
//
// Requirements: npm install   (installs ws). Node 18+ for global fetch.
// Run:    node relay-server.node.js
// Expose: ngrok http 8765

import { WebSocketServer } from "ws";
import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Load the tutorial-folder .env (../.env relative to this scripts/ folder) ──
const envPath = resolve(__dirname, "../.env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const m = line.match(/^([^#=]+)=(.*)$/);
    if (m) process.env[m[1].trim()] = m[2].trim().replace(/^['"]|['"]$/g, "");
  }
}

// ── Configuration ────────────────────────────────────────────────────────────
function require_(name) {
  const v = process.env[name];
  if (!v) { console.error(`ERROR: ${name} is not set in the environment / .env`); process.exit(1); }
  return v;
}

const PROJECT_ID  = require_("PROJECT_ID");
const KEY_ID      = require_("KEY_ID");
const KEY_SECRET  = require_("KEY_SECRET");
const SINCH_NUMBER   = require_("SINCH_NUMBER");
const SALES_NUMBER   = require_("SALES_NUMBER");
const SUPPORT_NUMBER = require_("SUPPORT_NUMBER");
const LLM_BASE_URL = (process.env.LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
const LLM_API_KEY  = require_("LLM_API_KEY");
const LLM_MODEL    = process.env.LLM_MODEL || "gpt-4o-mini";
const PORT         = Number(process.env.PORT || 8765);

const SINCH_BASE = "https://voice.api.sinch.com/v2";
const GREETING   = "Hello, this is the call centre. How can I help you?";
const AGENTS = { sales: [SALES_NUMBER, "Sales"], support: [SUPPORT_NUMBER, "Support"] };

const SYSTEM_PROMPT = readFileSync(resolve(__dirname, "../system_prompt.md"), "utf8").trim();

// ── LLM intent classification ────────────────────────────────────────────────
async function classifyIntent(callerText) {
  const res = await fetch(`${LLM_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${LLM_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: LLM_MODEL,
      temperature: 0,
      max_tokens: 20,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: callerText },
      ],
    }),
  });
  if (!res.ok) throw new Error(`LLM ${res.status}: ${await res.text()}`);
  const data = await res.json();
  return data.choices[0].message.content.trim();
}

// ── PATCH the live call to bridge in a human agent ───────────────────────────
async function patchInAgent(callId, intentKey) {
  const [number, label] = AGENTS[intentKey];
  const body = {
    commands: [
      {
        command: "dial",
        callName: "agent_call",
        from: { type: "PHONE", phone: { number: SINCH_NUMBER } },
        to:   { type: "PHONE", phone: { number } },
        dialTimeoutDurationSeconds: 20,
        maxCallDurationSeconds: 3600,
        events: {
          onAnswer: [
            { command: "bridgeCall", bridgeName: "ivr-bridge" },
            { command: "messages", messagesName: "agent-intro",
              messages: [{ type: "SAY", say: {
                format: "TEXT",
                text: `Connecting you to a customer. Intent: ${label}.`,
                voiceName: "Tiffany" } }] },
          ],
          onHangup: [{ command: "hangup", callName: "caller" }],
        },
      },
    ],
  };
  const auth = "Basic " + Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString("base64");
  const res = await fetch(`${SINCH_BASE}/projects/${PROJECT_ID}/calls/${callId}`, {
    method: "PATCH",
    headers: { Authorization: auth, "Content-Type": "application/json",
               "Idempotency-Key": `${callId}-${intentKey}` },
    body: JSON.stringify(body),
  });
  if (res.status !== 202) throw new Error(`PATCH ${res.status}: ${await res.text()}`);
}

// ── WebSocket session ────────────────────────────────────────────────────────
const wss = new WebSocketServer({ port: PORT });
console.log(`[*] AI IVR relay  model=${LLM_MODEL}  listening on ws://0.0.0.0:${PORT}`);

wss.on("connection", (ws) => {
  let callId = null;
  let patched = false;
  console.log("[+] connected");

  const send = (payload) => {
    const raw = JSON.stringify(payload);
    console.log(`  >> ${raw}`);
    ws.send(raw);
  };

  ws.on("message", async (data) => {
    const raw = data.toString();
    console.log(`  << ${raw}`);
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    if (msg.command === "connect") {
      callId = msg.callId;
      send({ command: "answer" });
      send({ command: "text", text: GREETING, isLast: true });
      return;
    }

    if ((msg.command === "text" || msg.command === "prompt") && callId && !patched) {
      const callerText = (msg.text || "").trim();
      if (!callerText) return;

      let reply;
      try {
        reply = await classifyIntent(callerText);
      } catch (err) {
        console.error(`[!] classify failed: ${err.message}`);
        send({ command: "text", text: "Sorry, please try again.", isLast: true });
        return;
      }

      const intentKey = reply.toLowerCase();
      if (AGENTS[intentKey]) {            // one-word, known route
        const [, label] = AGENTS[intentKey];
        send({ command: "text", text: `Please wait, connecting you to ${label}.`, isLast: true });
        await new Promise((r) => setTimeout(r, 2500)); // let the TTS play
        try {
          await patchInAgent(callId, intentKey);
          patched = true;
          console.log(`[*] patched ${label} into call ${callId}`);
        } catch (err) {
          console.error(`[!] patch failed: ${err.message}`);
        }
        ws.close();
      } else {                            // not confident — clarify
        send({ command: "text", text: reply, isLast: true });
      }
    }
  });

  ws.on("close", () => console.log(`[-] session ended  callId=${callId}`));
});
