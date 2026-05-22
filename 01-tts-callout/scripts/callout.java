// Sinch Voice Callout - dials a phone number, plays an audio file, then a TTS message.
// Requires Java 11+ (uses java.net.http.HttpClient).
//
// Maven pom.xml dependencies: none beyond JDK 11+
// Compile: javac -d out Callout.java
// Run:     java -cp out com.sinch.tutorials.ttscallout.Callout
//
// Variables are loaded from ../../.env (relative to the working directory).
// If the .env file is missing, system environment variables are used as a fallback.
//
// .env file format (one per line):
//   PROJECT_ID=your_project_id
//   KEY_ID=your_key_id
//   KEY_SECRET=your_key_secret
//   SINCH_NUMBER=+1234567890
//   DESTINATION_NUMBER=+0987654321

package com.sinch.tutorials.ttscallout;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

public class Callout {

    private static final Map<String, String> dotEnv = new HashMap<>();

    public static void main(String[] args) throws Exception {
        // Load .env file from two directories up (../../.env)
        loadDotEnv(Path.of("../../.env"));

        String projectId         = requireEnv("PROJECT_ID");
        String keyId             = requireEnv("KEY_ID");
        String keySecret         = requireEnv("KEY_SECRET");
        String sinchNumber       = requireEnv("SINCH_NUMBER");
        String destinationNumber = requireEnv("DESTINATION_NUMBER");

        String baseUrl = "https://voice.api.sinch.com/v2/projects/" + projectId + "/calls";

        // Basic Auth header: base64("keyId:keySecret")
        String credentials = Base64.getEncoder()
                .encodeToString((keyId + ":" + keySecret).getBytes());

        // SVAML payload: dial -> on answer play audio file -> hangup
        String body = String.format("""
            {
              "commands": [
                {
                  "command": "dial",
                  "name": "audio-notification",
                  "from": {
                    "type": "PHONE",
                    "phone": { "number": "%s" }
                  },
                  "to": {
                    "type": "PHONE",
                    "phone": { "number": "%s" }
                  },
                  "dialTimeout": "30s",
                  "maxDuration": "5m",
                  "events": {
                    "onAnswer": [
                      {
                        "command": "messages",
                        "name": "notification",
                        "messages": [
                          {
                            "type": "PLAY",
                            "play": {
                              "url": "https://samplelib.com/mp3/sample-12s.mp3"
                            }
                          },
                          {
                            "type": "SAY",
                            "say": {
                              "text": "Hello! This is a test notification from Sinch. Your verification code is 4 8 3 7.",
                              "voiceName": "Emma"
                            }
                          }
                        ],
                        "events": {
                          "onFinish": [
                            { "command": "hangup" }
                          ]
                        }
                      }
                    ]
                  }
                }
              ]
            }
            """, sinchNumber, destinationNumber);

        System.out.println("Placing callout from " + sinchNumber + " to " + destinationNumber + " ...");

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl))
                .header("Content-Type", "application/json")
                .header("Authorization", "Basic " + credentials)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        int statusCode = response.statusCode();
        String responseBody = response.body();

        if (statusCode == 201) {
            System.out.println("Call created successfully:");
            System.out.println(responseBody);
        } else {
            System.err.println("ERROR " + statusCode + ":");
            System.err.println(responseBody);
            System.exit(1);
        }
    }

    /**
     * Loads key=value pairs from a .env file into the dotEnv map.
     * Blank lines and lines starting with '#' are ignored.
     * Surrounding quotes on values are stripped.
     */
    private static void loadDotEnv(Path path) {
        Path resolved = path.toAbsolutePath().normalize();
        if (!Files.exists(resolved)) {
            System.out.println("Note: .env file not found at " + resolved + ", falling back to system environment variables.");
            return;
        }
        try {
            for (String line : Files.readAllLines(resolved)) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                int eqIndex = line.indexOf('=');
                if (eqIndex < 0) continue;
                String key = line.substring(0, eqIndex).trim();
                String value = line.substring(eqIndex + 1).trim();
                // Strip surrounding quotes if present
                if (value.length() >= 2
                        && ((value.startsWith("\"") && value.endsWith("\""))
                        ||  (value.startsWith("'")  && value.endsWith("'")))) {
                    value = value.substring(1, value.length() - 1);
                }
                dotEnv.put(key, value);
            }
            System.out.println("Loaded " + dotEnv.size() + " variable(s) from " + resolved);
        } catch (IOException e) {
            System.err.println("Warning: could not read .env file: " + e.getMessage());
        }
    }

    /**
     * Returns the value for a variable, checking the .env map first,
     * then falling back to system environment variables.
     */
    private static String requireEnv(String name) {
        String value = dotEnv.get(name);
        if (value == null || value.isBlank()) {
            value = System.getenv(name);
        }
        if (value == null || value.isBlank()) {
            System.err.println("ERROR: " + name + " is not set in .env or system environment.");
            System.exit(1);
        }
        return value;
    }
}