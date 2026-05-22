// Sinch Recording & Transcription — Spring Boot webhook server.
// Starts recording when a call is answered and uploads to cloud storage.
//
// Maven pom.xml dependencies:
// <dependency>
//   <groupId>org.springframework.boot</groupId>
//   <artifactId>spring-boot-starter-web</artifactId>
// </dependency>
//
// Set environment variables:
//   SINCH_NUMBER, STORAGE_DESTINATION_URL, STORAGE_CREDENTIALS, PORT

package com.sinch.tutorials.recording;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@SpringBootApplication
@RestController
public class Server {

    private final String storageDestination;
    private final String storageDestinationUrl;
    private final String storageCredentials;

    public Server() {
        String sinchNumber         = requireEnv("SINCH_NUMBER");
        this.storageDestinationUrl = requireEnv("STORAGE_DESTINATION_URL");
        this.storageCredentials    = requireEnv("STORAGE_CREDENTIALS");

        // Infer provider from URL scheme
        if (storageDestinationUrl.startsWith("gs://")) {
            this.storageDestination = "GCP";
        } else if (storageDestinationUrl.startsWith("s3://")) {
            this.storageDestination = "AWS";
        } else {
            this.storageDestination = "AZURE";
        }
    }

    public static void main(String[] args) {
        String port = System.getenv().getOrDefault("PORT", "3000");
        System.setProperty("server.port", port);
        SpringApplication.run(Server.class, args);
        System.out.println("Recording webhook server started on port " + port);
    }

    /** POST /webhook — handles Sinch call events and starts recording on answer */
    @PostMapping("/webhook")
    public ResponseEntity<Map<String, Object>> webhook(@RequestBody Map<String, Object> body) {
        @SuppressWarnings("unchecked")
        Map<String, Object> data = (Map<String, Object>) body.getOrDefault("data", Map.of());
        String event             = (String) data.getOrDefault("event", "");
        @SuppressWarnings("unchecked")
        Map<String, Object> call = (Map<String, Object>) data.getOrDefault("call", Map.of());

        System.out.println("Received event: " + event + ", callId: " + call.get("callId"));

        if ("call.incoming".equals(event)) {
            Map<String, Object> svaml = Map.of(
                "commands", List.of(
                    Map.of(
                        "command", "accept",
                        "commands", List.of(
                            // Start recording immediately when the call is answered
                            Map.of(
                                "command", "startRecording",
                                "name", "main-recording",
                                "recordingOptions", Map.of(
                                    "format", "MP3",
                                    "recordingType", "COMBINED",       // Both parties recorded
                                    "destination", storageDestination,
                                    "destinationUrl", storageDestinationUrl,
                                    "credentials", storageCredentials,
                                    "transcriptionOptions", Map.of(
                                        "isEnabled", true,             // Generate transcript
                                        "locale", "en-US"
                                    )
                                )
                            ),

                            // Inform the caller the call is being recorded
                            Map.of(
                                "command", "messages",
                                "name", "recording-notice",
                                "messages", List.of(
                                    Map.of(
                                        "type", "SAY",
                                        "say", Map.of(
                                            "text", "This call may be recorded for quality and compliance purposes.",
                                            "voiceName", "Emma"
                                        )
                                    )
                                )
                            )

                            // Add routing commands here, e.g.:
                            // Map.of("command", "bridgeCall", "name", "agent-bridge")
                        )
                    )
                )
            );

            return ResponseEntity.ok(svaml);
        }

        System.out.println("Unhandled event: " + event);
        return ResponseEntity.ok(Map.of("commands", List.of()));
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            System.err.println("ERROR: " + name + " is not set.");
            System.exit(1);
        }
        return value;
    }
}
