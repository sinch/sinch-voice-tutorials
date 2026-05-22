// Sinch Recording & Transcription — Express.js webhook server.
// Handles call events and starts recording when the call is answered.
//
// Requirements: npm install express
// Run: node server.node.js
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

const envPath = resolve(__dirname, "../../.env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const match = line.match(/^([^#=]+)=(.*)$/);
    if (match) process.env[match[1].trim()] = match[2].trim();
  }
}

const sinchNumber           = process.env.SINCH_NUMBER           || (() => { throw new Error("SINCH_NUMBER not set"); })();
const destinationNumber     = process.env.DESTINATION_NUMBER     || (() => { throw new Error("DESTINATION_NUMBER not set"); })();
const storageDestinationUrl = process.env.STORAGE_DESTINATION_URL || (() => { throw new Error("STORAGE_DESTINATION_URL not set"); })();
const storageCredentials    = process.env.STORAGE_CREDENTIALS    || (() => { throw new Error("STORAGE_CREDENTIALS not set"); })();
const PORT = process.env.PORT || 3000;

// Infer storage provider from URL scheme
const storageDestination = storageDestinationUrl.startsWith("gs://") ? "GCP"
  : storageDestinationUrl.startsWith("s3://") ? "AWS"
  : "AZURE";

const app = express();
app.use(express.json());

// POST /webhook — handles call events from Sinch
app.post("/webhook", (req, res) => {
  const event = req.body?.data?.event;
  const call  = req.body?.data?.call;

  console.log(`Received event: ${event}`, call?.callId);

  if (event === "call.incoming") {
    // Inbound call: answer, start recording, play notice, then bridge to agent or hang up
    const svamlResponse = {
      commands: [
        {
          command: "accept",
          commands: [
            // Start recording immediately when the inbound call is answered
            {
              command: "startRecording",
              name: "main-recording",
              recordingOptions: {
                format: "MP3",
                recordingType: "COMBINED",        // Record both parties
                destination: storageDestination,
                destinationUrl: storageDestinationUrl,
                credentials: storageCredentials,
                transcriptionOptions: {
                  isEnabled: true,                // Generate a transcription file
                  locale: "en-US"
                }
              }
            },

            // Tell the caller the call is being recorded (legal requirement in many jurisdictions)
            {
              command: "messages",
              name: "recording-notice",
              messages: [
                {
                  type: "SAY",
                  say: {
                    text: "This call may be recorded for quality and compliance purposes.",
                    voiceName: "Emma"
                  }
                }
              ]
            }

            // Add your additional SVAML commands here, e.g.:
            // { command: "bridgeCall", name: "agent-bridge" }
            // { command: "dial", name: "agent", to: { ... } }
          ]
        }
      ]
    };

    return res.status(200).json(svamlResponse);
  }

  console.log(`Unhandled event: ${event}`);
  res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`Recording webhook server listening on port ${PORT}`);
  console.log(`Storage: ${storageDestination} → ${storageDestinationUrl}`);
  console.log(`(Use ngrok: ngrok http ${PORT})`);
});
