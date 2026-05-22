// Sinch WebSocket Audio Streaming Server — Java (Jakarta WebSocket / Tyrus).
// Receives PCM audio from a live Sinch call and can send audio back.
//
// Maven pom.xml dependencies:
// <dependency>
//   <groupId>org.glassfish.tyrus.bundles</groupId>
//   <artifactId>tyrus-standalone-client</artifactId>
//   <version>2.1.5</version>
// </dependency>
// <dependency>
//   <groupId>org.glassfish.tyrus</groupId>
//   <artifactId>tyrus-server</artifactId>
//   <version>2.1.5</version>
// </dependency>
// <dependency>
//   <groupId>org.glassfish.tyrus</groupId>
//   <artifactId>tyrus-container-grizzly-server</artifactId>
//   <version>2.1.5</version>
// </dependency>
//
// Compile & run: mvn compile exec:java -Dexec.mainClass=com.sinch.tutorials.wsagent.WsServer

package com.sinch.tutorials.wsagent;

import jakarta.websocket.*;
import jakarta.websocket.server.ServerEndpoint;
import org.glassfish.tyrus.server.Server;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;

@ServerEndpoint("/")
public class WsServer {

    private static final ObjectMapper JSON = new ObjectMapper();

    // Per-session state stored in ConcurrentHashMap keyed by session ID
    private static final ConcurrentHashMap<String, SessionState> SESSIONS = new ConcurrentHashMap<>();

    static class SessionState {
        String callId;
        String applicationId;
        AtomicLong frameCount    = new AtomicLong();
        AtomicLong totalBytes    = new AtomicLong();
        FileOutputStream pcmFile;
        ScheduledFuture<?> heartbeat;
    }

    private static final ScheduledExecutorService SCHEDULER = Executors.newScheduledThreadPool(4);

    @OnOpen
    public void onOpen(Session session) {
        System.out.println("New WebSocket connection: " + session.getId());
        SESSIONS.put(session.getId(), new SessionState());
    }

    @OnMessage
    public void onTextMessage(String message, Session session) {
        SessionState state = SESSIONS.get(session.getId());
        if (state == null) return;

        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> msg = JSON.readValue(message, Map.class);
            String command = (String) msg.get("command");

            if ("connect".equals(command)) {
                // ConnectRequest: first message from Sinch.
                // Contains callId, applicationId, and custom headers.
                state.callId        = (String) msg.get("callId");
                state.applicationId = (String) msg.get("applicationId");
                System.out.printf("ConnectRequest — callId: %s, appId: %s%n",
                        state.callId, state.applicationId);
                System.out.println("Headers: " + msg.get("headers"));

                // Open PCM output file
                String filename = "call-" + System.currentTimeMillis() + ".pcm";
                state.pcmFile = new FileOutputStream(filename);
                System.out.println("Saving raw PCM audio to " + filename);

                // Accept the call — audio frames will flow after this response
                session.getBasicRemote().sendText(JSON.writeValueAsString(Map.of("command", "answer")));
                System.out.println("Sent ConnectResponse: answer");

                // Schedule periodic heartbeats to keep the connection alive
                state.heartbeat = SCHEDULER.scheduleAtFixedRate(() -> {
                    try {
                        if (session.isOpen()) {
                            session.getBasicRemote().sendText(
                                    JSON.writeValueAsString(Map.of("command", "heartbeat")));
                        }
                    } catch (IOException e) {
                        System.err.println("Heartbeat error: " + e.getMessage());
                    }
                }, 5, 5, TimeUnit.SECONDS);

            } else {
                System.out.println("StreamControl received: " + command);
            }

        } catch (Exception e) {
            System.err.println("Error handling text message: " + e.getMessage());
        }
    }

    @OnMessage
    public void onBinaryMessage(ByteBuffer data, Session session) {
        SessionState state = SESSIONS.get(session.getId());
        if (state == null) return;

        // Binary frame: raw PCM audio
        byte[] bytes = new byte[data.remaining()];
        data.get(bytes);

        state.frameCount.incrementAndGet();
        state.totalBytes.addAndGet(bytes.length);

        if (state.pcmFile != null) {
            try {
                state.pcmFile.write(bytes);
            } catch (IOException e) {
                System.err.println("Error writing PCM file: " + e.getMessage());
            }
        }

        if (state.frameCount.get() % 100 == 0) {
            System.out.printf("Audio frames: %d | Bytes: %d%n",
                    state.frameCount.get(), state.totalBytes.get());
        }

        // --- HERE: plug in your AI / STT processing ---
        // String transcript = sttEngine.process(bytes);
        // if (transcript != null) {
        //     byte[] audioResponse = tts.synthesize(llmReply(transcript));
        //     session.getBasicRemote().sendBinary(ByteBuffer.wrap(audioResponse));
        // }
    }

    @OnClose
    public void onClose(Session session, CloseReason reason) {
        SessionState state = SESSIONS.remove(session.getId());
        if (state != null) {
            if (state.heartbeat != null) state.heartbeat.cancel(true);
            if (state.pcmFile != null) {
                try { state.pcmFile.close(); } catch (IOException ignored) {}
            }
            System.out.printf("Connection closed — callId: %s, frames: %d, bytes: %d, reason: %s%n",
                    state.callId, state.frameCount.get(), state.totalBytes.get(), reason.getReasonPhrase());
        }
    }

    @OnError
    public void onError(Session session, Throwable throwable) {
        System.err.println("WebSocket error on session " + session.getId() + ": " + throwable.getMessage());
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getenv().getOrDefault("WS_PORT", "8765"));
        Server server = new Server("0.0.0.0", port, "/", null, WsServer.class);
        server.start();
        System.out.println("Sinch WebSocket audio server listening on ws://localhost:" + port);
        System.out.println("Expose with ngrok: ngrok http " + port);
        System.out.println("Then set WS_ENDPOINT=wss://<id>.ngrok-free.app when triggering a call.\n");
        // Block the main thread
        Thread.currentThread().join();
    }
}
