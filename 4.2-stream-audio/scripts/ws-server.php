<?php
// Sinch WebSocket Audio Streaming Server — PHP (Ratchet library).
// Receives PCM audio from a live Sinch call and can send audio back.
// Requirements: composer require cboden/ratchet react/socket react/event-loop

require __DIR__ . '/vendor/autoload.php';

use Ratchet\MessageComponentInterface;
use Ratchet\ConnectionInterface;
use Ratchet\Server\IoServer;
use Ratchet\Http\HttpServer;
use Ratchet\WebSocket\WsServer;

class SinchAudioHandler implements MessageComponentInterface
{
    /** @var \SplObjectStorage<ConnectionInterface, array> */
    private \SplObjectStorage $clients;

    public function __construct()
    {
        $this->clients = new \SplObjectStorage();
    }

    public function onOpen(ConnectionInterface $conn): void
    {
        $this->clients->attach($conn, [
            'callId'        => null,
            'applicationId' => null,
            'frameCount'    => 0,
            'totalBytes'    => 0,
            'pcmFile'       => null,
        ]);
        echo "New WebSocket connection #{$conn->resourceId}\n";
    }

    public function onMessage(ConnectionInterface $from, $msg): void
    {
        $state = $this->clients[$from];

        // Ratchet delivers messages as strings.
        // Binary PCM frames arrive as strings containing raw bytes.
        // Heuristic: try JSON decode; if it fails, treat as binary PCM audio.
        $decoded = json_decode($msg, true);

        if (json_last_error() === JSON_ERROR_NONE && isset($decoded['command'])) {
            // JSON control message
            $command = $decoded['command'];

            if ($command === 'connect') {
                // ConnectRequest from Sinch — first message after connection
                $state['callId']        = $decoded['callId'] ?? null;
                $state['applicationId'] = $decoded['applicationId'] ?? null;
                $headers                = $decoded['headers'] ?? [];

                echo "ConnectRequest — callId: {$state['callId']}, appId: {$state['applicationId']}\n";
                echo "Headers: " . json_encode($headers) . "\n";

                // Open a PCM output file
                $timestamp       = time();
                $filename        = "call-{$timestamp}.pcm";
                $state['pcmFile'] = fopen($filename, 'wb');
                echo "Saving raw PCM audio to {$filename}\n";

                $this->clients[$from] = $state;

                // Accept the call — audio frames will start flowing after this
                $from->send(json_encode(['command' => 'answer']));
                echo "Sent ConnectResponse: answer\n";

            } else {
                echo "StreamControl received: {$command}\n";
                $this->clients[$from] = $state;
            }

        } else {
            // Binary PCM audio frame
            $state['frameCount']++;
            $state['totalBytes'] += strlen($msg);

            if ($state['pcmFile']) {
                fwrite($state['pcmFile'], $msg);
            }

            if ($state['frameCount'] % 100 === 0) {
                echo "Audio frames: {$state['frameCount']} | Bytes: {$state['totalBytes']}\n";
            }

            $this->clients[$from] = $state;

            // --- HERE: plug in your AI / STT processing ---
            // $transcript = mySttEngine($msg);
            // if ($transcript) {
            //     $audioResponse = myTts(llmReply($transcript));
            //     $from->send($audioResponse);  // PCM bytes back to caller
            // }
        }
    }

    public function onClose(ConnectionInterface $conn): void
    {
        $state = $this->clients[$conn];
        if ($state['pcmFile']) {
            fclose($state['pcmFile']);
        }
        echo "Connection #{$conn->resourceId} closed — frames: {$state['frameCount']}, bytes: {$state['totalBytes']}\n";
        $this->clients->detach($conn);
    }

    public function onError(ConnectionInterface $conn, \Exception $e): void
    {
        echo "Error on connection #{$conn->resourceId}: {$e->getMessage()}\n";
        $conn->close();
    }
}

$port = (int)(getenv('WS_PORT') ?: 8765);
echo "Sinch WebSocket audio server listening on ws://localhost:{$port}\n";
echo "Expose with ngrok: ngrok http {$port}\n\n";

$server = IoServer::factory(
    new HttpServer(new WsServer(new SinchAudioHandler())),
    $port
);
$server->run();
