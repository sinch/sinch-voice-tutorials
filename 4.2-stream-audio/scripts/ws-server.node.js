// Sinch WebSocket Audio Streaming Server — Node.js (ws library).
// Receives PCM audio from a live Sinch call and can send audio back.
// This example logs received audio stats and sends heartbeats to keep the connection alive.
//
// Requirements: npm install ws
// Run: node ws-server.node.js
//
// package.json snippet:
// {
//   "type": "module",
//   "dependencies": { "ws": "^8.0.0" }
// }

import { WebSocketServer, WebSocket } from "ws";
import { createWriteStream } from "fs";

const PORT = parseInt(process.env.WS_PORT || "8765");

const wss = new WebSocketServer({ port: PORT });
console.log(`Sinch WebSocket audio server listening on ws://localhost:${PORT}`);
console.log("Expose with ngrok: ngrok http " + PORT);
console.log("Then set WS_ENDPOINT=wss://<your-ngrok-id>.ngrok-free.app when triggering a call.\n");

wss.on("connection", (ws, req) => {
  console.log(`New WebSocket connection from ${req.socket.remoteAddress}`);

  let callId = null;
  let applicationId = null;
  let audioFrameCount = 0;
  let totalBytesReceived = 0;

  // Optional: write PCM audio to a file (one per connection)
  const timestamp = Date.now();
  const pcmFile = createWriteStream(`call-${timestamp}.pcm`);
  console.log(`Saving raw PCM audio to call-${timestamp}.pcm`);

  ws.on("message", (data, isBinary) => {
    if (!isBinary) {
      // Text frame: JSON control message (ConnectRequest or StreamControl)
      let msg;
      try {
        msg = JSON.parse(data.toString());
      } catch {
        console.warn("Received non-JSON text frame:", data.toString());
        return;
      }

      if (msg.command === "connect") {
        // ConnectRequest: first message Sinch sends when a call is routed to this server.
        // It contains the callId and applicationId. Respond with {"command":"answer"} to accept.
        callId        = msg.callId;
        applicationId = msg.applicationId;
        console.log(`ConnectRequest received — callId: ${callId}, appId: ${applicationId}`);
        console.log("Custom headers:", msg.headers);

        // Accept the call; audio will start flowing after this response
        const response = JSON.stringify({ command: "answer" });
        ws.send(response);
        console.log("Sent ConnectResponse: answer");

        // Send periodic heartbeats to keep the connection alive during silence
        const heartbeatInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ command: "heartbeat" }));
          } else {
            clearInterval(heartbeatInterval);
          }
        }, 5000);

        ws.once("close", () => clearInterval(heartbeatInterval));

      } else {
        console.log("Received StreamControl or other message:", msg);
      }

    } else {
      // Binary frame: raw PCM audio data
      audioFrameCount++;
      totalBytesReceived += data.length;

      // Write to file for offline analysis
      pcmFile.write(data);

      // Log every 100 frames to avoid flooding the console
      if (audioFrameCount % 100 === 0) {
        console.log(`Audio frames received: ${audioFrameCount} | Total bytes: ${totalBytesReceived}`);
      }

      // --- HERE: plug in your AI / STT processing ---
      // Example:
      //   const transcript = await mySTTEngine.process(data);
      //   if (transcript) {
      //     const audioResponse = await myTTS.synthesize(llmReply(transcript));
      //     ws.send(audioResponse);   // Send PCM audio back to the caller
      //   }
    }
  });

  ws.on("close", (code, reason) => {
    pcmFile.end();
    console.log(`Connection closed — code: ${code}, reason: ${reason?.toString()}`);
    console.log(`Call summary — callId: ${callId}, frames: ${audioFrameCount}, bytes: ${totalBytesReceived}`);
  });

  ws.on("error", (err) => {
    console.error("WebSocket error:", err);
  });
});
