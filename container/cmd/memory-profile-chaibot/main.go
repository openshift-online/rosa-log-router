package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"log/slog"
	"os"
	"runtime"
	"time"

	"github.com/openshift/rosa-log-router/internal/processor"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))

	fmt.Println("=== chai-bot Methodology Test ===")

	// Test 1: 85 MiB target with 82,987 events (chai-bot's exact scenario)
	fmt.Println("\n📊 Test 1: 85 MiB input with 82,987 events (chai-bot's scenario)")
	runChaiTest(logger, 82987, 85*1024*1024)

	// Test 2: 64 MiB Vector batch
	fmt.Println("\n📊 Test 2: 64 MiB input (Vector batch size)")
	runChaiTest(logger, 64000, 64*1024*1024)
}

func runChaiTest(logger *slog.Logger, targetEvents int, maxSize int) {
	ctx := context.Background()

	// Force GC before starting
	runtime.GC()
	time.Sleep(100 * time.Millisecond)

	// Take baseline snapshot BEFORE generating any data
	var baselineMem runtime.MemStats
	runtime.ReadMemStats(&baselineMem)

	fmt.Printf("Baseline:\n")
	fmt.Printf("  HeapAlloc: %.2f MB\n", float64(baselineMem.HeapAlloc)/1024/1024)
	fmt.Printf("  Sys: %.2f MB\n", float64(baselineMem.Sys)/1024/1024)
	fmt.Printf("  TotalAlloc: %.2f MB\n\n", float64(baselineMem.TotalAlloc)/1024/1024)

	// Generate NDJSON data with target number of events
	var buf bytes.Buffer
	recordSize := maxSize / targetEvents

	for i := 0; i < targetEvents; i++ {
		// Generate a record of approximately recordSize bytes
		padding := ""
		if recordSize > 100 {
			padding = fmt.Sprintf("%*s", recordSize-100, "")
		}
		fmt.Fprintf(&buf, `{"timestamp":%d,"message":"Log entry %d%s"}%s`,
			time.Now().UnixMilli(), i, padding, "\n")
	}

	uncompressedSize := buf.Len()
	fmt.Printf("Generated uncompressed data:\n")
	fmt.Printf("  Size: %.2f MB\n", float64(uncompressedSize)/1024/1024)
	fmt.Printf("  Events: %d\n\n", targetEvents)

	// Compress the data
	var compressed bytes.Buffer
	gzw := gzip.NewWriter(&compressed)
	if _, err := gzw.Write(buf.Bytes()); err != nil {
		logger.Error("gzip write failed", "error", err)
		return
	}
	gzw.Close()

	compressedSize := compressed.Len()
	fmt.Printf("Compressed data:\n")
	fmt.Printf("  Size: %.2f MB\n", float64(compressedSize)/1024/1024)
	fmt.Printf("  Compression ratio: %.1fx\n\n", float64(uncompressedSize)/float64(compressedSize))

	gzippedData := compressed.Bytes()

	// Take snapshot BEFORE ProcessLogFile (this is the "object-path" start)
	var beforeMem runtime.MemStats
	runtime.ReadMemStats(&beforeMem)

	fmt.Printf("Before ProcessLogFile:\n")
	fmt.Printf("  HeapAlloc: %.2f MB\n", float64(beforeMem.HeapAlloc)/1024/1024)
	fmt.Printf("  Sys: %.2f MB\n", float64(beforeMem.Sys)/1024/1024)
	fmt.Printf("  TotalAlloc: %.2f MB\n\n", float64(beforeMem.TotalAlloc)/1024/1024)

	// Process the file - KEEP EVENTS IN MEMORY (don't let them GC)
	events, err := processor.ProcessLogFile(ctx, "test.json.gz", gzippedData, logger, int64(maxSize))
	if err != nil {
		logger.Error("processing failed", "error", err)
		return
	}

	// Take snapshot AFTER ProcessLogFile but BEFORE GC
	// This matches chai-bot's "peak Go heap" measurement
	var afterMem runtime.MemStats
	runtime.ReadMemStats(&afterMem)

	fmt.Printf("After ProcessLogFile (before GC):\n")
	fmt.Printf("  HeapAlloc: %.2f MB\n", float64(afterMem.HeapAlloc)/1024/1024)
	fmt.Printf("  Sys: %.2f MB\n", float64(afterMem.Sys)/1024/1024)
	fmt.Printf("  TotalAlloc: %.2f MB\n", float64(afterMem.TotalAlloc)/1024/1024)
	fmt.Printf("  NumGC: %d\n\n", afterMem.NumGC)

	// Calculate deltas (chai-bot's "object-path heap delta")
	heapDelta := float64(afterMem.HeapAlloc-beforeMem.HeapAlloc) / 1024 / 1024
	sysDelta := float64(afterMem.Sys-beforeMem.Sys) / 1024 / 1024
	totalAllocDelta := float64(afterMem.TotalAlloc-beforeMem.TotalAlloc) / 1024 / 1024

	// Also calculate from baseline (full object-path delta)
	heapDeltaFromBaseline := float64(afterMem.HeapAlloc-baselineMem.HeapAlloc) / 1024 / 1024
	sysDeltaFromBaseline := float64(afterMem.Sys-baselineMem.Sys) / 1024 / 1024

	fmt.Printf("📈 DELTAS (before → after ProcessLogFile):\n")
	fmt.Printf("  Events parsed: %d\n", len(events))
	fmt.Printf("  HeapAlloc delta: %.2f MB\n", heapDelta)
	fmt.Printf("  Sys delta: %.2f MB\n", sysDelta)
	fmt.Printf("  TotalAlloc delta: %.2f MB\n", totalAllocDelta)
	fmt.Printf("\n")

	fmt.Printf("📈 DELTAS (baseline → after ProcessLogFile):\n")
	fmt.Printf("  HeapAlloc delta: %.2f MB (chai-bot's \"object-path heap delta\")\n", heapDeltaFromBaseline)
	fmt.Printf("  Sys delta: %.2f MB\n", sysDeltaFromBaseline)
	fmt.Printf("\n")

	fmt.Printf("🎯 PEAK MEASUREMENTS:\n")
	fmt.Printf("  Peak HeapAlloc: %.2f MB\n", float64(afterMem.HeapAlloc)/1024/1024)
	fmt.Printf("  Peak Sys: %.2f MB\n", float64(afterMem.Sys)/1024/1024)
	fmt.Printf("\n")

	fmt.Printf("🧮 PROJECTED LAMBDA TOTALS (312 MB baseline + peak):\n")
	fmt.Printf("  312 + HeapAlloc: %.2f MB\n", 312+float64(afterMem.HeapAlloc)/1024/1024)
	fmt.Printf("  312 + Sys: %.2f MB\n", 312+float64(afterMem.Sys)/1024/1024)
	fmt.Printf("  312 + object-path delta: %.2f MB\n", 312+heapDeltaFromBaseline)
	fmt.Printf("\n")

	// Keep events in memory to prevent GC (chai-bot's methodology)
	// This ensures we measure the true peak with all structures retained
	if len(events) > 0 {
		// Touch the events to prevent compiler optimization
		_ = events[0].Timestamp
		_ = events[len(events)-1].Message
	}

	fmt.Println("✓ Events retained in memory (no GC)")
	fmt.Println("=" + string(make([]byte, 70)) + "=")
}
