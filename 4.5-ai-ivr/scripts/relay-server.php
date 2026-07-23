<?php
// 3.4.5 AI IVR — Voice Relay server that classifies caller intent with an LLM
// and patches a human agent into the live call.
//
// Flow per connection:
//   1. Sinch sends {"command":"connect","callId":"..."} -> we answer + greet.
//   2. Sinch sends {"command":"text"/"prompt","text":"<caller speech>"}.
//   3. We ask the LLM to classify. One-word reply ("Sales"/"Support") = route;
//      anything longer is spoken back as a clarifying question.
//   4. On a route, we PATCH /v2/projects/{projectId}/calls/{callId} to dial the
//      agent and bridge them into "ivr-bridge", then close the socket.
//
// Requirements: composer install   (installs cboden/ratchet). PHP 8.1+ with curl.
// Run:    php relay-server.php
// Expose: ngrok http 8765

require __DIR__ . '/../vendor/autoload.php';

use Ratchet\ConnectionInterface;
use Ratchet\MessageComponentInterface;
use Ratchet\Server\IoServer;
use Ratchet\Http\HttpServer;
use Ratchet\WebSocket\WsServer;

// ── Load the tutorial-folder .env (../.env relative to this scripts/ folder) ──
$envPath = __DIR__ . '/../.env';
if (is_file($envPath)) {
    foreach (file($envPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        if ($line[0] === '#' || !str_contains($line, '=')) continue;
        [$k, $v] = explode('=', $line, 2);
        $k = trim($k);
        $v = trim(trim($v), "\"'");
        if (getenv($k) === false) putenv("$k=$v");
        $_ENV[$k] = $v;
    }
}

function env_require(string $name): string {
    $v = $_ENV[$name] ?? getenv($name);
    if ($v === false || $v === null || $v === '') {
        fwrite(STDERR, "ERROR: $name is not set in the environment / .env\n");
        exit(1);
    }
    return $v;
}

// ── Configuration ────────────────────────────────────────────────────────────
const SINCH_BASE = 'https://voice.api.sinch.com/v2';
const GREETING   = 'Hello, this is the call centre. How can I help you?';

$config = [
    'projectId'   => env_require('PROJECT_ID'),
    'keyId'       => env_require('KEY_ID'),
    'keySecret'   => env_require('KEY_SECRET'),
    'sinchNumber' => env_require('SINCH_NUMBER'),
    'llmBaseUrl'  => rtrim($_ENV['LLM_BASE_URL'] ?? getenv('LLM_BASE_URL') ?: 'https://api.openai.com/v1', '/'),
    'llmApiKey'   => env_require('LLM_API_KEY'),
    'llmModel'    => $_ENV['LLM_MODEL'] ?? getenv('LLM_MODEL') ?: 'gpt-4o-mini',
    'agents'      => [
        'sales'   => [env_require('SALES_NUMBER'),   'Sales'],
        'support' => [env_require('SUPPORT_NUMBER'), 'Support'],
    ],
    'systemPrompt' => trim(file_get_contents(__DIR__ . '/../system_prompt.md')),
];

$port = (int)($_ENV['PORT'] ?? getenv('PORT') ?: 8765);

// ── Relay component ──────────────────────────────────────────────────────────
class IvrRelay implements MessageComponentInterface
{
    private SplObjectStorage $state;     // conn => ['callId' => ?string, 'patched' => bool]
    private $loop = null;

    public function __construct(private array $cfg)
    {
        $this->state = new SplObjectStorage();
    }

    public function setLoop($loop): void { $this->loop = $loop; }

    public function onOpen(ConnectionInterface $conn): void
    {
        $this->state[$conn] = ['callId' => null, 'patched' => false];
        echo "[+] connected\n";
    }

    public function onMessage(ConnectionInterface $conn, $raw): void
    {
        echo "  << $raw\n";
        $msg = json_decode($raw, true);
        if (!is_array($msg)) return;
        $command = $msg['command'] ?? null;
        $st = $this->state[$conn];

        if ($command === 'connect') {
            $st['callId'] = $msg['callId'] ?? null;
            $this->state[$conn] = $st;
            $this->send($conn, ['command' => 'answer']);
            $this->send($conn, ['command' => 'text', 'text' => GREETING, 'isLast' => true]);
            return;
        }

        if (in_array($command, ['text', 'prompt'], true) && $st['callId'] && !$st['patched']) {
            $callerText = trim($msg['text'] ?? '');
            if ($callerText === '') return;

            try {
                $reply = $this->classifyIntent($callerText);
            } catch (\Throwable $e) {
                fwrite(STDERR, "[!] classify failed: {$e->getMessage()}\n");
                $this->send($conn, ['command' => 'text', 'text' => 'Sorry, please try again.', 'isLast' => true]);
                return;
            }

            $intentKey = strtolower($reply);
            if (isset($this->cfg['agents'][$intentKey])) {        // one-word, known route
                [, $label] = $this->cfg['agents'][$intentKey];
                $this->send($conn, ['command' => 'text',
                    'text' => "Please wait, connecting you to $label.", 'isLast' => true]);

                $callId = $st['callId'];
                $st['patched'] = true;                            // guard immediately
                $this->state[$conn] = $st;

                $doPatch = function () use ($conn, $callId, $intentKey, $label) {
                    try {
                        $this->patchInAgent($callId, $intentKey);
                        echo "[*] patched $label into call $callId\n";
                    } catch (\Throwable $e) {
                        fwrite(STDERR, "[!] patch failed: {$e->getMessage()}\n");
                    }
                    $conn->close();
                };
                // Let the TTS play before we drop out; fall back to inline if no loop.
                if ($this->loop) { $this->loop->addTimer(2.5, $doPatch); } else { sleep(2); $doPatch(); }
            } else {                                              // not confident — clarify
                $this->send($conn, ['command' => 'text', 'text' => $reply, 'isLast' => true]);
            }
        }
    }

    public function onClose(ConnectionInterface $conn): void
    {
        $callId = $this->state[$conn]['callId'] ?? null;
        $this->state->detach($conn);
        echo "[-] session ended  callId=$callId\n";
    }

    public function onError(ConnectionInterface $conn, \Exception $e): void
    {
        fwrite(STDERR, "[!] ws error: {$e->getMessage()}\n");
        $conn->close();
    }

    private function send(ConnectionInterface $conn, array $payload): void
    {
        $raw = json_encode($payload);
        echo "  >> $raw\n";
        $conn->send($raw);
    }

    private function classifyIntent(string $callerText): string
    {
        $body = json_encode([
            'model'       => $this->cfg['llmModel'],
            'temperature' => 0,
            'max_tokens'  => 20,
            'messages'    => [
                ['role' => 'system', 'content' => $this->cfg['systemPrompt']],
                ['role' => 'user',   'content' => $callerText],
            ],
        ]);
        [$status, $resp] = $this->httpPost(
            "{$this->cfg['llmBaseUrl']}/chat/completions", $body,
            ['Authorization: Bearer ' . $this->cfg['llmApiKey'], 'Content-Type: application/json']);
        if ($status < 200 || $status >= 300) throw new \RuntimeException("LLM $status: $resp");
        $data = json_decode($resp, true);
        return trim($data['choices'][0]['message']['content'] ?? '');
    }

    private function patchInAgent(string $callId, string $intentKey): void
    {
        [$number, $label] = $this->cfg['agents'][$intentKey];
        $body = json_encode([
            'commands' => [[
                'command'  => 'dial',
                'callName' => 'agent_call',
                'from' => ['type' => 'PHONE', 'phone' => ['number' => $this->cfg['sinchNumber']]],
                'to'   => ['type' => 'PHONE', 'phone' => ['number' => $number]],
                'dialTimeoutDurationSeconds' => 20,
                'maxCallDurationSeconds' => 3600,
                'events' => [
                    'onAnswer' => [
                        ['command' => 'bridgeCall', 'bridgeName' => 'ivr-bridge'],
                        ['command' => 'messages', 'messagesName' => 'agent-intro',
                         'messages' => [['type' => 'SAY', 'say' => [
                             'format' => 'TEXT',
                             'text' => "Connecting you to a customer. Intent: $label.",
                             'voiceName' => 'Tiffany']]]],
                    ],
                    'onHangup' => [['command' => 'hangup', 'callName' => 'caller']],
                ],
            ]],
        ]);
        $auth = base64_encode("{$this->cfg['keyId']}:{$this->cfg['keySecret']}");
        [$status, $resp] = $this->httpPost(
            SINCH_BASE . "/projects/{$this->cfg['projectId']}/calls/$callId", $body,
            ['Authorization: Basic ' . $auth, 'Content-Type: application/json',
             "Idempotency-Key: $callId-$intentKey"], 'PATCH');
        if ($status !== 202) throw new \RuntimeException("PATCH $status: $resp");
    }

    private function httpPost(string $url, string $body, array $headers, string $method = 'POST'): array
    {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_CUSTOMREQUEST  => $method,
            CURLOPT_POSTFIELDS     => $body,
            CURLOPT_HTTPHEADER     => $headers,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 10,
        ]);
        $resp = curl_exec($ch);
        if ($resp === false) { $err = curl_error($ch); curl_close($ch); throw new \RuntimeException($err); }
        $status = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        curl_close($ch);
        return [$status, $resp];
    }
}

// ── Boot ─────────────────────────────────────────────────────────────────────
$relay = new IvrRelay($config);
$server = IoServer::factory(new HttpServer(new WsServer($relay)), $port, '0.0.0.0');
$relay->setLoop($server->loop);
echo "[*] AI IVR relay  model={$config['llmModel']}  listening on ws://0.0.0.0:$port\n";
$server->run();
