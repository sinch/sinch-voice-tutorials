// Sinch AMD Callout — Node.js (native fetch, Node 18+) outbound call with AMD.
// Run: node amd-callout.node.js
// Requires "type": "module" in package.json.

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

const projectId         = process.env.PROJECT_ID         || (() => { throw new Error("PROJECT_ID not set"); })();
const keyId             = process.env.KEY_ID             || (() => { throw new Error("KEY_ID not set"); })();
const keySecret         = process.env.KEY_SECRET         || (() => { throw new Error("KEY_SECRET not set"); })();
const sinchNumber       = process.env.SINCH_NUMBER       || (() => { throw new Error("SINCH_NUMBER not set"); })();
const destinationNumber = process.env.DESTINATION_NUMBER || (() => { throw new Error("DESTINATION_NUMBER not set"); })();

const authHeader = "Basic " + Buffer.from(`${keyId}:${keySecret}`).toString("base64");

const payload = {
  commands: [
    {
      command: "dial",
      name: "amd-call",
      from: { type: "PHONE", phone: { number: sinchNumber } },
      to:   { type: "PHONE", phone: { number: destinationNumber } },
      dialTimeout: "45s",
      maxDuration: "5m",
      events: {
        onAnswer: [
          {
            command: "amd",
            events: {
              // Human detected: greet and connect to an agent (or take further action)
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
              // Machine detected (no beep yet): hang up silently
              onMachine: [{ command: "hangup" }],
              // Beep detected: play the voicemail message right after the beep
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
              // Unknown: safe default is to hang up
              onUnknown: [{ command: "hangup" }]
            }
          }
        ]
      }
    }
  ]
};

console.log(`Placing AMD callout from ${sinchNumber} to ${destinationNumber} ...`);

const response = await fetch(
  `https://voice.api.sinch.com/v2/projects/${projectId}/calls`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: authHeader
    },
    body: JSON.stringify(payload)
  }
);

const data = await response.json();

if (response.status === 201) {
  console.log("AMD call created successfully:", JSON.stringify(data, null, 2));
} else {
  console.error(`ERROR ${response.status}:`, JSON.stringify(data, null, 2));
  process.exit(1);
}
