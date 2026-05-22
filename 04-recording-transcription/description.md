# Call Recording and Transcription

## Overview

The Sinch Voice API can record a call and upload the audio file directly to your cloud storage bucket (AWS S3, Google Cloud Storage, or Azure Blob Storage) as soon as the call ends. Optionally, it can also transcribe the recording to text and deliver the transcript alongside the audio file. Recording is controlled by the `startRecording` and `stopRecording` SVAML commands, which can be included inline in the call payload or returned from a webhook. You specify a destination URL, your storage credentials, the recording format (MP3 or WAV), and whether to enable transcription.

## Real-life examples

- **Compliance and quality assurance**: Record all customer service calls and store them in S3 for regulatory compliance review.
- **Sales coaching**: Record sales calls, transcribe them, and feed the transcripts into an AI coaching tool.
- **Meeting notes**: Record conference bridge calls and auto-generate meeting summaries from transcripts.
- **Dispute resolution**: Maintain an auditable record of conversations for insurance claims or legal disputes.

## Prerequisites

- A [Sinch account](https://dashboard.sinch.com) with API credentials.
- A Sinch virtual phone number.
- A cloud storage bucket with write access:
  - **AWS S3**: An S3 bucket and an IAM user access key with `s3:PutObject` permission.
  - **GCS**: A service account key with Storage Object Creator role.
  - **Azure**: A storage account with a Blob container and a SAS token or access key.
- Set the `STORAGE_DESTINATION_URL` and `STORAGE_CREDENTIALS` environment variables.

## Step-by-step instructions

### 1. Set storage credentials

In your `.env` file:

```bash
# AWS S3
STORAGE_DESTINATION_URL=s3://my-bucket/recordings/
STORAGE_CREDENTIALS=AKIAIOSFODNN7EXAMPLE:wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY:us-east-1

# Google Cloud Storage
STORAGE_DESTINATION_URL=gs://my-gcs-bucket/recordings/
STORAGE_CREDENTIALS=BASE64_ENCODED_SERVICE_ACCOUNT_JSON

# Azure Blob Storage
STORAGE_DESTINATION_URL=https://myaccount.blob.core.windows.net/recordings/
STORAGE_CREDENTIALS=AZURE_STORAGE_CONNECTION_STRING
```

### 2. Understand the `startRecording` SVAML command

```json
{
  "command": "startRecording",
  "name": "my-recording",
  "recordingOptions": {
    "format": "MP3",
    "recordingType": "COMBINED",
    "destination": "AWS",
    "destinationUrl": "s3://my-bucket/recordings/",
    "credentials": "ACCESS_KEY:SECRET_KEY:REGION",
    "transcriptionOptions": {
      "isEnabled": true,
      "locale": "en-US"
    }
  }
}
```

Key fields:
- `format`: `MP3` (default) or `WAV`.
- `recordingType`: `COMBINED` (both directions), `INBOUND`, or `OUTBOUND`.
- `destination`: `AWS`, `GCP`, or `AZURE`.
- `destinationUrl`: The bucket path where files are uploaded.
- `credentials`: Storage credentials (format varies by provider).
- `transcriptionOptions.isEnabled`: `true` to generate a transcript alongside the audio file.
- `transcriptionOptions.locale`: BCP-47 language code (e.g., `en-US`, `es-ES`).

### 3. Run the trigger script (outbound call with inline recording)

```bash
bash scripts/trigger-call.sh
```

This makes an outbound call that starts recording immediately when answered.

### 4. Run the webhook server (dynamic recording via webhook)

Alternatively, configure your Sinch service with a webhook URL and start the callback server. The server responds with SVAML (including `startRecording`) when the call is answered:

```bash
node scripts/server.node.js    # Node.js
python scripts/server.py       # Python
```

### 5. After the call ends

Sinch uploads the recording file to your storage bucket. The filename includes the call ID for traceability. If transcription is enabled, a JSON transcription file is also uploaded alongside the audio.
