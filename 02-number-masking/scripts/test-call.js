// Sinch Number Masking — browser JS to trigger a programmatic bridge call.
// Note: calling the Sinch API directly from a browser will hit CORS restrictions.
// In production, proxy these calls through your backend.
// This example is for demonstration/testing with CORS disabled or a proxy.

(async function sinchMaskedBridgeCall() {
  const projectId    = /* process.env.PROJECT_ID    || */ "YOUR_PROJECT_ID";
  const keyId        = /* process.env.KEY_ID        || */ "YOUR_KEY_ID";
  const keySecret    = /* process.env.KEY_SECRET    || */ "YOUR_KEY_SECRET";
  const sinchNumber  = /* process.env.SINCH_NUMBER  || */ "+1XXXXXXXXXX";
  const partyANumber = /* process.env.PARTY_A_NUMBER || */ "+1AAAAAAAAAAA";  // First person to call
  const partyBNumber = /* process.env.PARTY_B_NUMBER || */ "+1BBBBBBBBBBB";  // Second person to connect

  const baseUrl = "https://voice.api.sinch.com/v2";
  const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

  // SVAML payload: dial Party A, on answer bridge, then dial Party B from Sinch number.
  // Both parties see only the Sinch number — neither sees the other's real number.
  const payload = {
    commands: [
      {
        command: "dial",
        name: "party-a",
        from: { type: "PHONE", phone: { number: sinchNumber } },
        to:   { type: "PHONE", phone: { number: partyANumber } },
        dialTimeout: "30s",
        events: {
          onAnswer: [
            {
              command: "messages",
              name: "greeting",
              messages: [
                {
                  type: "SAY",
                  say: {
                    text: "Please hold while we connect the other party.",
                    voiceName: "Emma"
                  }
                }
              ]
            },
            // Add Party A to the bridge
            { command: "bridgeCall", name: "masked-bridge" },
            // Dial Party B from the Sinch number (masks Party A's real number)
            {
              command: "dial",
              name: "party-b",
              from: { type: "PHONE", phone: { number: sinchNumber } },
              to:   { type: "PHONE", phone: { number: partyBNumber } },
              dialTimeout: "30s",
              events: {
                onAnswer: [{ command: "bridgeCall", name: "masked-bridge" }],
                onHangup: [{ command: "hangup", callName: "party-a" }]
              }
            }
          ],
          onHangup: [{ command: "hangup", callName: "party-b" }]
        }
      }
    ]
  };

  console.log(`Initiating masked bridge call between ${partyANumber} and ${partyBNumber} ...`);
  console.log(`(Both parties will see ${sinchNumber} as caller ID)`);

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
    console.log("Bridge call created successfully:", data);
  } else {
    console.error(`ERROR ${response.status}:`, data);
  }
})();
