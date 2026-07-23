// Minimal Sinch Voice STREAM server (Node.js).
// Echoes audio back to the caller, so you can verify the WebSocket plumbing
// before wiring in an actual STT/LLM/TTS pipeline.
//
// Requirements: npm install ws
// Run:    node ws-stream-server.node.js
// Expose: ngrok http 8765
// Then set the STREAM `endpoint` in your SVAML to wss://<ngrok-id>.ngrok-free.app

import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT || 8765);
const wss = new WebSocketServer({ port: PORT });

console.log(`STREAM echo server on :${PORT}`);

wss.on("connection", (ws, req) => {
  console.log(`new connection from ${req.socket.remoteAddress}`);

  // Heartbeat every 30 seconds while connected (keeps corporate proxies quiet).
  const heartbeat = setInterval(() => {
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ command: "heartbeat" }));
  }, 30_000);

  ws.on("message", (data, isBinary) => {
    if (!isBinary) {
      let msg;
      try { msg = JSON.parse(data.toString()); } catch { return; }
      console.log("text frame", msg);
      if (msg.command === "connect") {
        ws.send(JSON.stringify({ command: "answer" }));
      }
      return;
    }
    // Binary frame == raw PCM from the caller. Echo it back.
    ws.send(data, { binary: true });
  });

  ws.on("close", () => {
    clearInterval(heartbeat);
    console.log("connection closed");
  });
});
