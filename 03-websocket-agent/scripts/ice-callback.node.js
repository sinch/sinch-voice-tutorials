// Sinch WebSocket Agent — ICE (Incoming Call Event) webhook server — Node.js / Express.
// When an inbound call arrives at your Sinch number, this server responds with SVAML
// to route the call audio directly to your WebSocket server.
//
// Requirements: npm install express
// Run: node ice-callback.node.js
//
// package.json snippet:
// {
//   "type": "module",
//   "dependencies": { "express": "^4.18.0" }
// }

import express from "express";
import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Load .env from project root
const envPath = resolve(__dirname, "../../.env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const match = line.match(/^([^#=]+)=(.*)$/);
    if (match) process.env[match[1].trim()] = match[2].trim();
  }
}

const sinchNumber  = process.env.SINCH_NUMBER || (() => { throw new Error("SINCH_NUMBER not set"); })();
// WS_ENDPOINT: your publicly accessible WebSocket URL, e.g. wss://abc.ngrok-free.app
const wsEndpoint   = process.env.WS_ENDPOINT  || (() => { throw new Error("WS_ENDPOINT not set — run ngrok and set wss://..."); })();
const PORT         = process.env.PORT || 3001;

const app = express();
app.use(express.json());

// POST /webhook — handles incoming call events from Sinch and responds with SVAML
// to connect the inbound call audio to your WebSocket server.
app.post("/webhook", (req, res) => {
  const event = req.body?.data?.event;
  const call  = req.body?.data?.call;

  console.log(`Received event: ${event}`, JSON.stringify(call, null, 2));

  if (event === "call.incoming") {
    // Inbound call to your Sinch number.
    // Respond with SVAML to:
    // 1. Answer the inbound call
    // 2. Bridge it to the phone participant
    // 3. Dial the WebSocket stream endpoint
    // 4. Bridge the stream into the same audio bridge -> audio flows to/from your WS server
    const svamlResponse = {
      commands: [
        {
          command: "accept",
          commands: [
            // Add the inbound phone call to a named audio bridge
            { command: "bridgeCall", name: "stream-bridge" },

            // Dial the WebSocket stream endpoint — this is where your AI agent lives
            {
              command: "dial",
              name: "stream-leg",
              to: {
                type: "STREAM",
                stream: {
                  endpoint: wsEndpoint,    // e.g. wss://abc123.ngrok-free.app
                  streamOptions: {
                    version: 1,
                    codec: "PCM",
                    sampleRate: 8000       // 8 kHz is standard for PSTN calls
                  },
                  // Optional: pass custom metadata to your WebSocket server
                  callHeaders: [
                    { key: "X-Call-From", value: call?.from?.phone?.number || "unknown" }
                  ]
                }
              },
              dialTimeout: "10s",
              events: {
                // When the WebSocket server answers, add the stream leg to the bridge
                onAnswer: [{ command: "bridgeCall", name: "stream-bridge" }],
                // If the stream disconnects, hang up the phone call too
                onHangup: [{ command: "hangup", callName: "inbound" }]
              }
            }
          ]
        }
      ]
    };

    return res.status(200).json(svamlResponse);
  }

  // Acknowledge other events
  console.log(`Unhandled event: ${event}`);
  res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`ICE webhook server listening on port ${PORT}`);
  console.log(`Set your Sinch service webhook URL to: http://localhost:${PORT}/webhook`);
  console.log(`WebSocket endpoint: ${wsEndpoint}`);
  console.log(`(Use ngrok to expose this: ngrok http ${PORT})`);
});
