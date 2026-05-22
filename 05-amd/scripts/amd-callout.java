// Sinch AMD Callout — Java outbound call with Answering Machine Detection.
// Requires Java 11+ (java.net.http.HttpClient).
//
// Compile: javac -d out amd-callout.java
// Run:     java -cp out com.sinch.tutorials.amd.AmdCallout
//
// Set environment variables before running:
//   export PROJECT_ID=... KEY_ID=... KEY_SECRET=... SINCH_NUMBER=... DESTINATION_NUMBER=...

package com.sinch.tutorials.amd;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Base64;

public class AmdCallout {

    public static void main(String[] args) throws Exception {
        String projectId         = requireEnv("PROJECT_ID");
        String keyId             = requireEnv("KEY_ID");
        String keySecret         = requireEnv("KEY_SECRET");
        String sinchNumber       = requireEnv("SINCH_NUMBER");
        String destinationNumber = requireEnv("DESTINATION_NUMBER");

        String url         = "https://voice.api.sinch.com/v2/projects/" + projectId + "/calls";
        String credentials = Base64.getEncoder()
                .encodeToString((keyId + ":" + keySecret).getBytes());

        // The `amd` command must be inside `onAnswer`.
        // AMD fires different SVAML depending on detection result.
        String body = String.format("""
            {
              "commands": [
                {
                  "command": "dial",
                  "name": "amd-call",
                  "from": { "type": "PHONE", "phone": { "number": "%s" } },
                  "to":   { "type": "PHONE", "phone": { "number": "%s" } },
                  "dialTimeout": "45s",
                  "maxDuration": "5m",
                  "events": {
                    "onAnswer": [
                      {
                        "command": "amd",
                        "events": {
                          "onHuman": [
                            {
                              "command": "messages",
                              "name": "human-greeting",
                              "messages": [
                                {
                                  "type": "SAY",
                                  "say": {
                                    "text": "Hello! This is a call from Acme Corp. An agent will be with you shortly.",
                                    "voiceName": "Emma"
                                  }
                                }
                              ],
                              "events": { "onFinish": [{ "command": "hangup" }] }
                            }
                          ],
                          "onMachine": [
                            { "command": "hangup" }
                          ],
                          "onBeep": [
                            {
                              "command": "messages",
                              "name": "voicemail-message",
                              "messages": [
                                {
                                  "type": "SAY",
                                  "say": {
                                    "text": "Hi, this is Acme Corp calling about your recent inquiry. Please call us back at 555-1234. Thank you.",
                                    "voiceName": "Emma"
                                  }
                                }
                              ],
                              "events": { "onFinish": [{ "command": "hangup" }] }
                            }
                          ],
                          "onUnknown": [
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

        System.out.println("Placing AMD callout from " + sinchNumber + " to " + destinationNumber + " ...");

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .header("Authorization", "Basic " + credentials)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        int statusCode = response.statusCode();

        if (statusCode == 201) {
            System.out.println("AMD call created successfully:");
            System.out.println(response.body());
        } else {
            System.err.println("ERROR " + statusCode + ":");
            System.err.println(response.body());
            System.exit(1);
        }
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
