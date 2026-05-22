<?php
// Sinch AMD Callout — PHP outbound call with Answering Machine Detection.
// Requirements: PHP 8+ with the curl extension.

$projectId         = getenv('PROJECT_ID')         ?: die("ERROR: PROJECT_ID not set.\n");
$keyId             = getenv('KEY_ID')             ?: die("ERROR: KEY_ID not set.\n");
$keySecret         = getenv('KEY_SECRET')         ?: die("ERROR: KEY_SECRET not set.\n");
$sinchNumber       = getenv('SINCH_NUMBER')       ?: die("ERROR: SINCH_NUMBER not set.\n");
$destinationNumber = getenv('DESTINATION_NUMBER') ?: die("ERROR: DESTINATION_NUMBER not set.\n");

$url = "https://voice.api.sinch.com/v2/projects/{$projectId}/calls";

// The `amd` command must be inside `onAnswer`. AMD fires different SVAML
// depending on whether a human, machine, or beep is detected.
$payload = [
    'commands' => [
        [
            'command' => 'dial',
            'name'    => 'amd-call',
            'from'    => ['type' => 'PHONE', 'phone' => ['number' => $sinchNumber]],
            'to'      => ['type' => 'PHONE', 'phone' => ['number' => $destinationNumber]],
            'dialTimeout' => '45s',
            'maxDuration' => '5m',
            'events' => [
                'onAnswer' => [
                    [
                        'command' => 'amd',
                        'events'  => [
                            // Human detected: play a personalized greeting
                            'onHuman' => [
                                [
                                    'command'  => 'messages',
                                    'name'     => 'human-greeting',
                                    'messages' => [
                                        [
                                            'type' => 'SAY',
                                            'say'  => [
                                                'text'         => 'Hello! This is a call from Acme Corp. An agent will be with you shortly.',
                                                'voiceName' => 'Emma',
                                            ],
                                        ],
                                    ],
                                    'events' => [
                                        'onFinish' => [['command' => 'hangup']],
                                    ],
                                ],
                            ],
                            // Machine greeting (no beep yet): hang up
                            'onMachine' => [
                                ['command' => 'hangup'],
                            ],
                            // Beep detected: leave voicemail immediately after the beep
                            'onBeep' => [
                                [
                                    'command'  => 'messages',
                                    'name'     => 'voicemail-message',
                                    'messages' => [
                                        [
                                            'type' => 'SAY',
                                            'say'  => [
                                                'text'         => 'Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.',
                                                'voiceName' => 'Emma',
                                            ],
                                        ],
                                    ],
                                    'events' => [
                                        'onFinish' => [['command' => 'hangup']],
                                    ],
                                ],
                            ],
                            // Unknown result: hang up safely
                            'onUnknown' => [
                                ['command' => 'hangup'],
                            ],
                        ],
                    ],
                ],
            ],
        ],
    ],
];

echo "Placing AMD callout from {$sinchNumber} to {$destinationNumber} ...\n";

$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
    CURLOPT_USERPWD        => "{$keyId}:{$keySecret}",
    CURLOPT_POSTFIELDS     => json_encode($payload),
    CURLOPT_RETURNTRANSFER => true,
]);

$responseBody = curl_exec($ch);
$httpCode     = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curlError    = curl_error($ch);
curl_close($ch);

if ($curlError) {
    fwrite(STDERR, "curl error: {$curlError}\n");
    exit(1);
}

$data = json_decode($responseBody, true);

if ($httpCode === 201) {
    echo "AMD call created successfully:\n";
    echo json_encode($data, JSON_PRETTY_PRINT) . "\n";
} else {
    fwrite(STDERR, "ERROR {$httpCode}:\n");
    fwrite(STDERR, json_encode($data, JSON_PRETTY_PRINT) . "\n");
    exit(1);
}
