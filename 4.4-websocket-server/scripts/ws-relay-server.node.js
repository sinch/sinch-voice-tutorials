// Minimal Sinch Voice VOICE_RELAY server (Node.js).
// Echoes whatever the caller says back as TTS. Use to validate plumbing before
// wiring an LLM in (see 3.4.1 for a real LangChain-backed agent).
//
// Requirements: npm install ws
// Run:    node ws-relay-server.node.js
// Expose: ngrok http 8765

import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT || 8765);
const wss = new WebSocketServer({ port: PORT });

console.log(`VOICE_RELAY echo server on :${PORT}`);

wss.on("connection", (ws) => {
  ws.on("message", (data) => {
    let msg;
    try { msg = JSON.parse(data.toString()); } catch { return; }
    console.log("rx", msg);

    if (msg.command === "connect") {
      // Accept the session
      ws.send(JSON.stringify({ command: "answer" }));
      // Initial greeting
      ws.send(JSON.stringify({ command: "text", text: "Hi! Anything you say I will repeat back.", isLast: true }));
      return;
    }

    // Sinch sends transcribed user speech as `text` (or `prompt`).
    if ((msg.command === "text" || msg.command === "prompt") && msg.text) {
      ws.send(JSON.stringify({
        command: "text",
        text:    `You said: ${msg.text}`,
        isLast:  true,
      }));
    }
  });

  ws.on("close", () => console.log("connection closed"));
});
