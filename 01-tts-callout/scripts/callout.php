<?php
// Sinch TTS Callout — dials a phone number and plays a text-to-speech message.
// Requirements: PHP 8+ with the curl extension enabled.
$envPath = __DIR__ . '/../../.env';

if (file_exists($envPath)) {
    $lines = file($envPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        $line = trim($line);
        if ($line === '' || str_starts_with($line, '#')) {
            continue;
        }
        if (str_contains($line, '=')) {
            [$name, $value] = explode('=', $line, 2);
            $name  = trim($name);
            $value = trim($value, " \t\n\r\0\x0B\"'");
            putenv("{$name}={$value}");
        }
    }
}

$projectId         = getenv('PROJECT_ID')         ?: die("ERROR: PROJECT_ID not set.\n");
$keyId             = getenv('KEY_ID')             ?: die("ERROR: KEY_ID not set.\n");
$keySecret         = getenv('KEY_SECRET')         ?: die("ERROR: KEY_SECRET not set.\n");
$sinchNumber       = getenv('SINCH_NUMBER')       ?: die("ERROR: SINCH_NUMBER not set.\n");
$destinationNumber = getenv('DESTINATION_NUMBER') ?: die("ERROR: DESTINATION_NUMBER not set.\n");

$baseUrl = "https://voice.api.sinch.com/v2/projects/{$projectId}/calls";

// SVAML payload: dial -> on answer play audio file -> hangup
$payload = [
    'commands' => [
        [
            'command' => 'dial',
            'name'    => 'audio-notification',
            'from'    => [
                'type'  => 'PHONE',
                'phone' => ['number' => $sinchNumber],
            ],
            'to'      => [
                'type'  => 'PHONE',
                'phone' => ['number' => $destinationNumber],
            ],
            'dialTimeout' => '30s',
            'maxDuration' => '5m',
            'events'      => [
                'onAnswer' => [
                    [
                        'command'  => 'messages',
                        'name'     => 'notification',
                        'messages' => [
                            [
                                'type' => 'PLAY',
                                'play' => [
                                    'url' => 'https://samplelib.com/mp3/sample-12s.mp3',
                                ],
                            ],
                            [
                                'type' => 'SAY',
                                'say'  => [
                                    'text'      => 'Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.',
                                    'voiceName' => 'Emma',
                                ],
                            ],
                        ],
                        'events' => [
                            'onFinish' => [
                                ['command' => 'hangup'],
                            ],
                        ],
                    ],
                ],
            ],
        ],
    ],
];

echo "Placing callout from {$sinchNumber} to {$destinationNumber} ...\n";

$ch = curl_init($baseUrl);
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
    echo "Call created successfully:\n";
    echo json_encode($data, JSON_PRETTY_PRINT) . "\n";
} else {
    fwrite(STDERR, "ERROR {$httpCode}:\n");
    fwrite(STDERR, json_encode($data, JSON_PRETTY_PRINT) . "\n");
    exit(1);
}
