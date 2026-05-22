// Sinch AMD Callback Server — Express.js webhook server.
// Handles inbound call events and responds with SVAML including the AMD command.
// Use this when you want dynamic AMD behavior via webhook (e.g., per-call configuration).
//
// Requirements: npm install express
// Run: node callback-server.node.js
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
const envPath   = resolve(__dirname, "../../.env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const match = line.match(/^([^#=]+)=(.*)$/);
    if (match) process.env[match[1].trim()] = match[2].trim();
  }
}

const sinchNumber       = process.env.SINCH_NUMBER       || (() => { throw new Error("SINCH_NUMBER not set"); })();
const destinationNumber = process.env.DESTINATION_NUMBER || (() => { throw new Error("DESTINATION_NUMBER not set"); })();
const PORT = process.env.PORT || 3000;

const app = express();
app.use(express.json());

// POST /webhook — receives Sinch call events and responds with AMD SVAML
app.post("/webhook", (req, res) => {
  const event = req.body?.data?.event;
  const call  = req.body?.data?.call;

  console.log(`Received event: ${event}`, call?.callId);

  if (event === "call.incoming") {
    // Inbound call: respond with SVAML to answer and run AMD detection.
    // The `amd` command is the first (and only) command in `onAnswer`.
    // AMD will then fire one of: onHuman, onMachine, onBeep, onUnknown.
    const svamlResponse = {
      commands: [
        {
          command: "accept",
          commands: [
            // Run AMD detection as the first thing after answering
            {
              command: "amd",
              events: {
                // Live human detected: play a personalized message
                onHuman: [
                  {
                    command: "messages",
                    name: "human-greeting",
                    messages: [
                      {
                        type: "SAY",
                        say: {
                          text: "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                          voiceName: "Emma"
                        }
                      }
                    ],
                    events: { onFinish: [{ command: "hangup" }] }
                  }
                ],

                // Machine greeting detected (waiting for beep): hang up silently
                onMachine: [{ command: "hangup" }],

                // Beep detected: leave voicemail right after the beep tone
                onBeep: [
                  {
                    command: "messages",
                    name: "voicemail-message",
                    messages: [
                      {
                        type: "SAY",
                        say: {
                          text: "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                          voiceName: "Emma"
                        }
                      }
                    ],
                    events: { onFinish: [{ command: "hangup" }] }
                  }
                ],

                // AMD inconclusive: hang up rather than risk a bad experience
                onUnknown: [{ command: "hangup" }]
              }
            }
          ]
        }
      ]
    };

    return res.status(200).json(svamlResponse);
  }

  // Acknowledge all other events
  console.log(`Unhandled event: ${event}`);
  res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`AMD callback server listening on port ${PORT}`);
  console.log(`Set your Sinch service webhook URL to: http://localhost:${PORT}/webhook`);
  console.log(`(Use ngrok: ngrok http ${PORT})`);
});
