// Sinch AMD Callout — browser JS to trigger an outbound call with AMD.
// Note: calling the Sinch API directly from a browser will hit CORS restrictions.
// In production, proxy these calls through your backend.
// This example is for demonstration/testing with CORS disabled or a proxy.

(async function sinchAmdCallout() {
  const projectId         = /* process.env.PROJECT_ID         || */ "YOUR_PROJECT_ID";
  const keyId             = /* process.env.KEY_ID             || */ "YOUR_KEY_ID";
  const keySecret         = /* process.env.KEY_SECRET         || */ "YOUR_KEY_SECRET";
  const sinchNumber       = /* process.env.SINCH_NUMBER       || */ "+1XXXXXXXXXX";
  const destinationNumber = /* process.env.DESTINATION_NUMBER || */ "+1YYYYYYYYYY";

  const baseUrl    = "https://voice.api.sinch.com/v2";
  const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

  // The `amd` command fires different SVAML based on what AMD detects.
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
                // Human picked up: play a personalized greeting
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
                // Machine greeting (no beep yet): hang up
                onMachine: [{ command: "hangup" }],
                // Beep detected: leave voicemail immediately
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
                // Unknown detection result: hang up safely
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
    `${baseUrl}/projects/${projectId}/calls`,
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
    console.log("AMD call created successfully:", data);
  } else {
    console.error(`ERROR ${response.status}:`, data);
  }
})();
