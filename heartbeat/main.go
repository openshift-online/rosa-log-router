package main

import (
	"encoding/json"
	"fmt"
	"log"
	"time"
)

const heartbeatInterval = 2 * time.Minute

type HeartbeatLog struct {
	Timestamp       string `json:"timestamp"`
	Level           string `json:"level"`
	Message         string `json:"message"`
	Heartbeat       bool   `json:"heartbeat"`
	IntervalSeconds int    `json:"interval_seconds"`
	Source          string `json:"source"`
}

type StartupLog struct {
	Timestamp              string `json:"timestamp"`
	Level                  string `json:"level"`
	Message                string `json:"message"`
	HeartbeatIntervalSeconds int    `json:"heartbeat_interval_seconds"`
}

func emitHeartbeat() {
	heartbeat := HeartbeatLog{
		Timestamp:       time.Now().UTC().Format(time.RFC3339),
		Level:           "INFO",
		Message:         "Vector heartbeat - logging pipeline active",
		Heartbeat:       true,
		IntervalSeconds: int(heartbeatInterval.Seconds()),
		Source:          "heartbeat-container",
	}

	jsonBytes, err := json.Marshal(heartbeat)
	if err != nil {
		log.Printf("Error marshaling heartbeat: %v", err)
		return
	}

	fmt.Println(string(jsonBytes))
}

func main() {
	// Emit startup log
	startup := StartupLog{
		Timestamp:              time.Now().UTC().Format(time.RFC3339),
		Level:                  "INFO",
		Message:                "Heartbeat container started",
		HeartbeatIntervalSeconds: int(heartbeatInterval.Seconds()),
	}

	jsonBytes, _ := json.Marshal(startup)
	fmt.Println(string(jsonBytes))

	// Heartbeat loop
	ticker := time.NewTicker(heartbeatInterval)
	defer ticker.Stop()

	for range ticker.C {
		emitHeartbeat()
	}
}
