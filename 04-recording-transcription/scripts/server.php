<?php
// Sinch Recording & Transcription — Slim Framework 4 webhook server.
// Starts recording when a call is answered and uploads to cloud storage.
// Requirements: composer require slim/slim slim/psr7 nyholm/psr7

use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Factory\AppFactory;

require __DIR__ . '/vendor/autoload.php';

$sinchNumber           = getenv('SINCH_NUMBER')            ?: die("ERROR: SINCH_NUMBER not set.\n");
$storageDestinationUrl = getenv('STORAGE_DESTINATION_URL') ?: die("ERROR: STORAGE_DESTINATION_URL not set.\n");
$storageCredentials    = getenv('STORAGE_CREDENTIALS')     ?: die("ERROR: STORAGE_CREDENTIALS not set.\n");

// Infer storage provider from URL scheme
if (str_starts_with($storageDestinationUrl, 'gs://')) {
    $storageDestination = 'GCP';
} elseif (str_starts_with($storageDestinationUrl, 's3://')) {
    $storageDestination = 'AWS';
} else {
    $storageDestination = 'AZURE';
}

$app = AppFactory::create();
$app->addBodyParsingMiddleware();

$app->post('/webhook', function (Request $request, Response $response)
    use ($sinchNumber, $storageDestination, $storageDestinationUrl, $storageCredentials) {

    $body  = $request->getParsedBody();
    $event = $body['data']['event'] ?? null;
    $call  = $body['data']['call']  ?? [];

    error_log("Received event: {$event}, callId: " . ($call['callId'] ?? ''));

    if ($event === 'call.incoming') {
        $svaml = [
            'commands' => [
                [
                    'command'  => 'accept',
                    'commands' => [
                        // Start recording immediately when the call is answered
                        [
                            'command' => 'startRecording',
                            'name'    => 'main-recording',
                            'recordingOptions' => [
                                'format'        => 'MP3',
                                'recordingType' => 'COMBINED',      // Both parties
                                'destination'   => $storageDestination,
                                'destinationUrl' => $storageDestinationUrl,
                                'credentials'   => $storageCredentials,
                                'transcriptionOptions' => [
                                    'isEnabled' => true,            // Auto-transcribe the recording
                                    'locale'    => 'en-US',
                                ],
                            ],
                        ],

                        // Inform the caller the call is being recorded
                        [
                            'command'  => 'messages',
                            'name'     => 'recording-notice',
                            'messages' => [
                                [
                                    'type' => 'SAY',
                                    'say'  => [
                                        'text'      => 'This call may be recorded for quality and compliance purposes.',
                                        'voiceName' => 'Emma',
                                    ],
                                ],
                            ],
                        ],

                        // Add your routing SVAML here:
                        // ['command' => 'bridgeCall', 'name' => 'agent-bridge'],
                    ],
                ],
            ],
        ];

        $response->getBody()->write(json_encode($svaml));
        return $response->withHeader('Content-Type', 'application/json')->withStatus(200);
    }

    error_log("Unhandled event: {$event}");
    $response->getBody()->write(json_encode(['commands' => []]));
    return $response->withHeader('Content-Type', 'application/json')->withStatus(200);
});

$port = (int)(getenv('PORT') ?: 3000);
echo "Recording webhook server listening on port {$port}\n";
echo "Storage: {$storageDestination} → {$storageDestinationUrl}\n";
echo "(Use ngrok: ngrok http {$port})\n";

$app->run();
