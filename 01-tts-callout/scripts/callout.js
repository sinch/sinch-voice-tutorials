// Sinch Voice Callout — plays an audio file then a TTS message. Browser-friendly fetch version.
// Note: calling the Sinch API directly from a browser will hit CORS restrictions.
// In production, proxy these calls through your backend.
// This example is for demonstration/testing with CORS disabled or a proxy.

(async function sinchTtsCallout() {
  // Read credentials from environment variables (set these in your .env or environment)
  // When running in a browser, replace these with your actual values or use a proxy.
  const projectId = /* process.env.PROJECT_ID || */ "YOUR_PROJECT_ID";
  const keyId     = /* process.env.KEY_ID     || */ "YOUR_KEY_ID";
  const keySecret = /* process.env.KEY_SECRET || */ "YOUR_KEY_SECRET";
  const sinchNumber       = /* process.env.SINCH_NUMBER       || */ "+1XXXXXXXXXX";
  const destinationNumber = /* process.env.DESTINATION_NUMBER || */ "+1YYYYYYYYYY";

  const baseUrl = "https://voice.api.sinch.com/v2";

  // Basic Auth header: base64("keyId:keySecret")
  const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

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
        Authorization: authHeader
      },
      body: JSON.stringify(payload)
    }
  );

  const data = await response.json();

  if (response.status === 201) {
    console.log("Call created successfully:", data);
  } else {
    console.error(`ERROR ${response.status}:`, data);
  }
})();
