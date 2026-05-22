<?php
// Sinch Number Masking — Slim Framework 4 webhook server.
// Handles inbound call events and responds with SVAML to anonymously bridge calls.
// Requirements: composer require slim/slim slim/psr7 nyholm/psr7 php-di/php-di

use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Factory\AppFactory;

require __DIR__ . '/vendor/autoload.php';

$sinchNumber       = getenv('SINCH_NUMBER')       ?: die("ERROR: SINCH_NUMBER not set.\n");
$destinationNumber = getenv('DESTINATION_NUMBER') ?: die("ERROR: DESTINATION_NUMBER not set.\n");

$app = AppFactory::create();
$app->addBodyParsingMiddleware();

// POST /webhook — receives Sinch call events and responds with SVAML
$app->post('/webhook', function (Request $request, Response $response) use ($sinchNumber, $destinationNumber) {
    $body  = $request->getParsedBody();
    $event = $body['data']['event'] ?? null;
    $call  = $body['data']['call']  ?? [];

    error_log("Received webhook event: {$event}");
    error_log(json_encode($call, JSON_PRETTY_PRINT));

    if ($event === 'call.incoming') {
        // Inbound call to the Sinch number from Party A.
        // Respond with SVAML to bridge Party A anonymously to Party B.
        $svaml = [
            'commands' => [
                [
                    'command'  => 'accept',
                    'commands' => [
                        // Play a short greeting while the second leg is being dialed
                        [
                            'command'  => 'messages',
                            'name'     => 'greeting',
                            'messages' => [
                                [
                                    'type' => 'SAY',
                                    'say'  => [
                                        'text'      => 'Please hold while we connect your call.',
                                        'voiceName' => 'Emma',
                                    ],
                                ],
                            ],
                        ],

                        // Add Party A to a named bridge
                        ['command' => 'bridgeCall', 'name' => 'main-bridge'],

                        // Dial Party B from the Sinch number (masks Party A's real number)
                        [
                            'command' => 'dial',
                            'name'    => 'callee',
                            'from'    => [
                                'type'  => 'PHONE',
                                'phone' => ['number' => $sinchNumber],  // Party B sees the Sinch number
                            ],
                            'to'      => [
                                'type'  => 'PHONE',
                                // In production, look up destination from your DB
                                // based on the called Sinch number ($call['to'])
                                'phone' => ['number' => $destinationNumber],
                            ],
                            'dialTimeout' => '30s',
                            'events'      => [
                                'onAnswer' => [['command' => 'bridgeCall', 'name' => 'main-bridge']],
                                'onHangup' => [['command' => 'hangup', 'callName' => 'inbound']],
                            ],
                        ],
                    ],
                ],
            ],
        ];

        $response->getBody()->write(json_encode($svaml));
        return $response
            ->withHeader('Content-Type', 'application/json')
            ->withStatus(200);
    }

    // Acknowledge all other events
    error_log("Unhandled event: {$event}");
    $response->getBody()->write(json_encode(['commands' => []]));
    return $response->withHeader('Content-Type', 'application/json')->withStatus(200);
});

$port = (int)(getenv('PORT') ?: 3000);
echo "Number masking webhook server listening on port {$port}\n";
echo "Set your Sinch service webhook URL to: http://localhost:{$port}/webhook\n";
echo "(Use ngrok: ngrok http {$port})\n";

$app->run();
