// Sinch Recording & Transcription — browser JS to trigger an outbound call with recording.
// Note: calling the Sinch API directly from a browser will hit CORS restrictions.
// In production, proxy these calls through your backend.
// This example is for demonstration/testing with CORS disabled or a proxy.

(async function sinchRecordingCall() {
  const projectId              = /* process.env.PROJECT_ID              || */ "YOUR_PROJECT_ID";
  const keyId                  = /* process.env.KEY_ID                  || */ "YOUR_KEY_ID";
  const keySecret              = /* process.env.KEY_SECRET              || */ "YOUR_KEY_SECRET";
  const sinchNumber            = /* process.env.SINCH_NUMBER            || */ "+1XXXXXXXXXX";
  const destinationNumber      = /* process.env.DESTINATION_NUMBER      || */ "+1YYYYYYYYYY";
  const storageDestinationUrl  = /* process.env.STORAGE_DESTINATION_URL || */ "s3://my-bucket/recordings/";
  const storageCredentials     = /* process.env.STORAGE_CREDENTIALS     || */ "ACCESS_KEY:SECRET_KEY:REGION";

  // Infer storage provider from the URL scheme
  const storageDestination = storageDestinationUrl.startsWith("gs://") ? "GCP"
    : storageDestinationUrl.startsWith("s3://") ? "AWS"
    : "AZURE";

  const baseUrl    = "https://voice.api.sinch.com/v2";
  const authHeader = "Basic " + btoa(`${keyId}:${keySecret}`);

  const payload = {
    commands: [
      {
        command: "dial",
        name: "recorded-call",
        from: { type: "PHONE", phone: { number: sinchNumber } },
        to:   { type: "PHONE", phone: { number: destinationNumber } },
        dialTimeout: "30s",
        maxDuration: "1h",
        events: {
          onAnswer: [
            // Start recording immediately when the call is answered
            {
              command: "startRecording",
              name: "main-recording",
              recordingOptions: {
                format: "MP3",
                recordingType: "COMBINED",     // Record both inbound and outbound audio
                destination: storageDestination,
                destinationUrl: storageDestinationUrl,
                credentials: storageCredentials,
                transcriptionOptions: {
                  isEnabled: true,             // Enable automatic transcription
                  locale: "en-US"
                }
              }
            },
            // Notify the caller that the call is being recorded
            {
              command: "messages",
              name: "recording-notice",
              messages: [
                {
                  type: "SAY",
                  say: {
                    text: "This call is being recorded.",
                    voiceName: "Emma"
                  }
                }
              ]
            }
          ],
          // Stop the recording explicitly when the call ends
          onHangup: [
            { command: "stopRecording", name: "main-recording" }
          ]
        }
      }
    ]
  };

  console.log(`Calling ${destinationNumber} with recording enabled (${storageDestination}) ...`);

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
    console.log("Call created with recording:", data);
    console.log("Recording will be uploaded to:", storageDestinationUrl);
  } else {
    console.error(`ERROR ${response.status}:`, data);
  }
})();
