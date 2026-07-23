// Sinch WebSocket Agent — browser JS to trigger an outbound call that streams to a WebSocket server.
// Note: calling the Sinch API directly from a browser will hit CORS restrictions.
// In production, proxy these calls through your backend.
// This example is for demonstration/testing with CORS disabled or a proxy.

(async function sinchWsAgentCall() {
  const projectId         = /* process.env.PROJECT_ID         || */ "YOUR_PROJECT_ID";
  const keyId             = /* process.env.KEY_ID             || */ "YOUR_KEY_ID";
  const keySecret         = /* process.env.KEY_SECRET         || */ "YOUR_KEY_SECRET";
  const sinchNumber       = /* process.env.SINCH_NUMBER       || */ "+1XXXXXXXXXX";
  const destinationNumber = /* process.env.DESTINATION_NUMBER || */ "+1YYYYYYYYYY";
  // WS_ENDPOINT: your publicly accessible WebSocket URL (convert ngrok https:// -> wss://)
  const wsEndpoint        = /* process.env.WS_ENDPOINT        || */ "wss://abc123.ngrok-free.app";

  const baseUrl    = "https://voice.api.sinch.com/v2";
  const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

  // SVAML payload:
  // 1. Dial the destination phone number
  // 2. On answer: add phone call to a bridge, then dial the WebSocket stream endpoint
  // 3. On stream answer: add stream to the same bridge -> bidirectional audio flows
  const payload = {
    commands: [
      {
        command: "dial",
        callName: "phone-leg",
        from: { type: "PHONE", phone: { number: sinchNumber } },
        to:   { type: "PHONE", phone: { number: destinationNumber } },
        dialTimeoutDurationSeconds: 30,
        maxCallDurationSeconds: 1800,
        events: {
          onAnswer: [
            // Bridge the phone call
            { command: "bridgeCall", bridgeName: "stream-bridge" },
            // Dial the WebSocket stream endpoint (your AI agent / STT service)
            {
              command: "dial",
              callName: "stream-leg",
              to: {
                type: "STREAM",
                stream: {
                  endpoint: wsEndpoint,
                  streamOptions: {
                    version: 1,
                    codec: "PCM",
                    sampleRate: 8000       // 8 kHz is standard for PSTN calls
                  },
                  callHeaders: [
                    { key: "X-Tutorial", value: "sinch-ws-agent" }
                  ]
                }
              },
              dialTimeoutDurationSeconds: 10,
              events: {
                // Stream answers -> join the same bridge so audio flows bidirectionally
                onAnswer: [{ command: "bridgeCall", bridgeName: "stream-bridge" }],
                // Stream disconnects -> hang up the phone call
                onHangup: [{ command: "hangup", callName: "phone-leg" }]
              }
            }
          ],
          // Phone hangs up -> disconnect the stream leg
          onHangup: [{ command: "hangup", callName: "stream-leg" }]
        }
      }
    ]
  };

  console.log(`Dialing ${destinationNumber} and streaming to ${wsEndpoint} ...`);

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
