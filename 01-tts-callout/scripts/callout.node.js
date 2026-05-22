// Sinch Voice Callout — plays an audio file then a TTS message. Node.js, native fetch (Node 18+).
// Run with: node callout.node.js
// Requires "type": "module" in package.json, or rename to callout.mjs.
//
// Dependencies: none (uses Node 18+ built-in fetch)
// If on Node < 18, install node-fetch: npm install node-fetch
// and replace the import below with: import fetch from 'node-fetch';
//
// package.json snippet:
// {
//   "type": "module",
//   "dependencies": {}
// }

import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// Load .env from project root (two directories up from scripts/)
const __dirname = dirname(fileURLToPath(import.meta.url));
const envPath = resolve(__dirname, "../../.env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const match = line.match(/^([^#=]+)=(.*)$/);
    if (match) process.env[match[1].trim()] = match[2].trim().replace(/^['"]|['"]$/g, "");
  }
}

const projectId         = process.env.PROJECT_ID         || (() => { throw new Error("PROJECT_ID not set"); })();
const keyId             = process.env.KEY_ID             || (() => { throw new Error("KEY_ID not set"); })();
const keySecret         = process.env.KEY_SECRET         || (() => { throw new Error("KEY_SECRET not set"); })();
const sinchNumber       = process.env.SINCH_NUMBER       || (() => { throw new Error("SINCH_NUMBER not set"); })();
const destinationNumber = process.env.DESTINATION_NUMBER || (() => { throw new Error("DESTINATION_NUMBER not set"); })();
const baseUrl = "https://voice.api.sinch.com/v2";

// Basic Auth: base64("keyId:keySecret") using Node.js Buffer
const authHeader = "Basic " + Buffer.from(`${keyId}:${keySecret}`).toString("base64");

// SVAML payload: dial -> on answer play audio file -> hangup
const payload = {
  commands: [
    {
      command: "dial",
      name: "audio-notification",
      from: {
        type: "PHONE",
        phone: { number: sinchNumber }
      },
      to: {
        type: "PHONE",
        phone: { number: destinationNumber }
      },
      dialTimeout: "30s",
      maxDuration: "5m",
      events: {
        onAnswer: [
          {
            command: "messages",
            name: "notification",
            messages: [
              {
                type: "PLAY",
                play: {
                  url: "https://samplelib.com/mp3/sample-12s.mp3"
                }
              },
              {
                type: "SAY",
                say: {
                  text: "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                  voiceName: "Emma"
                }
              }
            ],
            events: {
              onFinish: [
                { command: "hangup" }
              ]
            }
          }
        ]
      }
    }
  ]
};

console.log(`Placing callout from ${sinchNumber} to ${destinationNumber} ...`);
const response = await fetch(
  `${baseUrl}/projects/${projectId}/calls`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
	  "Authorization": authHeader
    },
    body: JSON.stringify(payload)
  }
);
const data = await response.json();

if (response.status === 201) {
  console.log("Call created successfully:", JSON.stringify(data, null, 2));
} else {
  console.error(`ERROR ${response.status}:`, JSON.stringify(data, null, 2));
  process.exit(1);
}
