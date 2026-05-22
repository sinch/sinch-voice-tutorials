// Sinch Number Masking — Express.js webhook server.
// Handles inbound call events and responds with SVAML to anonymously bridge calls.
//
// Requirements: npm install express
// Run: node server.node.js
//
// package.json snippet:
// {
//   "type": "module",
//   "dependencies": {
//     "express": "^4.18.0"
//   }
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

const sinchNumber       = process.env.SINCH_NUMBER       || (() => { throw new Error("SINCH_NUMBER not set"); })();
const destinationNumber = process.env.DESTINATION_NUMBER || (() => { throw new Error("DESTINATION_NUMBER not set"); })();
const PORT = process.env.PORT || 3000;

const app = express();
app.use(express.json());

// POST /webhook — receives Sinch call events and responds with SVAML
app.post("/webhook", (req, res) => {
  const event = req.body?.data?.event;
  const call  = req.body?.data?.call;

  console.log(`Received webhook event: ${event}`, JSON.stringify(call, null, 2));

  if (event === "call.incoming") {
    // Inbound call to the Sinch number from Party A.
    // Respond with SVAML to:
    // 1. Answer the call
    // 2. Play a hold greeting
    // 3. Bridge Party A to a new call leg
    // 4. Dial Party B from the Sinch number (masking Party A's real number)
    // 5. Bridge Party B into the same bridge when they answer
    const svamlResponse = {
      commands: [
        {
          command: "accept",
          commands: [
            // Play a short greeting while connecting
            {
              command: "messages",
              name: "greeting",
              messages: [
                {
                  type: "SAY",
                  say: {
                    text: "Please hold while we connect your call.",
                    voiceName: "Emma"
                  }
                }
              ]
            },

            // Add Party A to a named bridge (created automatically if it doesn't exist)
            { command: "bridgeCall", name: "main-bridge" },

            // Dial Party B — using the Sinch number as "from" to mask Party A's real number
            {
              command: "dial",
              name: "callee",
              from: {
                type: "PHONE",
                phone: { number: sinchNumber }   // Party B sees the Sinch number, not Party A's number
              },
              to: {
                type: "PHONE",
                // In production, look up Party B's number from your database
                // based on the Sinch virtual number that was called (call.to)
                phone: { number: destinationNumber }
              },
              dialTimeout: "30s",
              events: {
                // When Party B answers, add them to the same bridge -> audio flows between A and B
                onAnswer: [{ command: "bridgeCall", name: "main-bridge" }],
                // When Party B hangs up, terminate Party A's call leg as well
                onHangup: [{ command: "hangup", callName: "inbound" }]
              }
            }
          ]
        }
      ]
    };

    return res.status(200).json(svamlResponse);
  }

  // For all other events, respond with 200 and no commands (acknowledge receipt)
  console.log(`Unhandled event: ${event}`);
  res.status(200).json({ commands: [] });
});

app.listen(PORT, () => {
  console.log(`Number masking webhook server listening on port ${PORT}`);
  console.log(`Set your Sinch service webhook URL to: http://localhost:${PORT}/webhook`);
  console.log(`(Use ngrok to expose this locally: ngrok http ${PORT})`);
});
