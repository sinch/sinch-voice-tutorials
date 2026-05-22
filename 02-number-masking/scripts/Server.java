// Sinch Number Masking — Spring Boot webhook server.
// Handles inbound call events and responds with SVAML to anonymously bridge calls.
//
// Maven pom.xml dependencies:
// <dependency>
//   <groupId>org.springframework.boot</groupId>
//   <artifactId>spring-boot-starter-web</artifactId>
// </dependency>
//
// Run: mvn spring-boot:run  OR  java -jar target/server.jar
// Set environment variables: PROJECT_ID, KEY_ID, KEY_SECRET, SINCH_NUMBER, DESTINATION_NUMBER

package com.sinch.tutorials.numbermasking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@SpringBootApplication
@RestController
public class Server {

    private final String sinchNumber;
    private final String destinationNumber;
    private final int port;

    public Server() {
        this.sinchNumber       = requireEnv("SINCH_NUMBER");
        this.destinationNumber = requireEnv("DESTINATION_NUMBER");
        this.port              = Integer.parseInt(System.getenv().getOrDefault("PORT", "3000"));
    }

    public static void main(String[] args) {
        // Set server port from environment
        String port = System.getenv().getOrDefault("PORT", "3000");
        System.setProperty("server.port", port);
        SpringApplication.run(Server.class, args);
        System.out.println("Number masking webhook server started.");
        System.out.println("Set your Sinch webhook URL to: http://localhost:" + port + "/webhook");
        System.out.println("(Use ngrok: ngrok http " + port + ")");
    }

    /** POST /webhook — receives Sinch call events and responds with SVAML */
    @PostMapping("/webhook")
    public ResponseEntity<Map<String, Object>> webhook(@RequestBody Map<String, Object> body) {
        @SuppressWarnings("unchecked")
        Map<String, Object> data  = (Map<String, Object>) body.getOrDefault("data", Map.of());
        String event              = (String) data.getOrDefault("event", "");
        Object call               = data.getOrDefault("call", Map.of());

        System.out.println("Received webhook event: " + event);
        System.out.println("Call: " + call);

        if ("call.incoming".equals(event)) {
            // Inbound call to the Sinch number from Party A.
            // Respond with SVAML to bridge Party A anonymously to Party B.
            Map<String, Object> svaml = Map.of(
                "commands", List.of(
                    Map.of(
                        "command", "accept",
                        "commands", List.of(
                            // Play a short greeting while the second leg is being dialed
                            Map.of(
                                "command", "messages",
                                "name", "greeting",
                                "messages", List.of(
                                    Map.of(
                                        "type", "SAY",
                                        "say", Map.of(
                                            "text", "Please hold while we connect your call.",
                                            "voiceName", "Emma"
                                        )
                                    )
                                )
                            ),

                            // Add Party A to a named bridge
                            Map.of("command", "bridgeCall", "name", "main-bridge"),

                            // Dial Party B from the Sinch number (masks Party A's real number)
                            Map.of(
                                "command", "dial",
                                "name", "callee",
                                "from", Map.of(
                                    "type", "PHONE",
                                    // Party B sees the Sinch number, not Party A's real number
                                    "phone", Map.of("number", sinchNumber)
                                ),
                                "to", Map.of(
                                    "type", "PHONE",
                                    // In production, look up from your DB based on the called Sinch number
                                    "phone", Map.of("number", destinationNumber)
                                ),
                                "dialTimeout", "30s",
                                "events", Map.of(
                                    // Party B answers -> join the same bridge
                                    "onAnswer", List.of(Map.of("command", "bridgeCall", "name", "main-bridge")),
                                    // Party B hangs up -> terminate Party A's leg
                                    "onHangup", List.of(Map.of("command", "hangup", "callName", "inbound"))
                                )
                            )
                        )
                    )
                )
            );

            return ResponseEntity.ok(svaml);
        }

        // Acknowledge all other events
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
