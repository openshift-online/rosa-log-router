package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"log/slog"
	"os"
	"runtime"
	"runtime/debug"
	"time"

	"github.com/openshift/rosa-log-router/internal/processor"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelWarn, // Reduce noise
	}))

	fmt.Println("=== Memory Test with GC DISABLED ===")
	fmt.Println("(This shows true peak before garbage collection)")

	// DISABLE GARBAGE COLLECTION to see true peak
	debug.SetGCPercent(-1)
	fmt.Println("⚠️  GC DISABLED - measuring true allocation peak")

	// Test with 85 MiB
	runTest(logger, 82987, 85*1024*1024, "85 MiB (chai-bot scenario)")

	// Re-enable GC and clean up
	debug.SetGCPercent(100)
	runtime.GC()
	time.Sleep(200 * time.Millisecond)

	// Test with 64 MiB
	debug.SetGCPercent(-1)
	runTest(logger, 64000, 64*1024*1024, "64 MiB (Vector batch)")
	debug.SetGCPercent(100)
}

func runTest(logger *slog.Logger, targetEvents int, maxSize int, label string) {
	ctx := context.Background()

	// Force GC before disabling it
	runtime.GC()
	time.Sleep(100 * time.Millisecond)

	// Baseline
	var baseline runtime.MemStats
	runtime.ReadMemStats(&baseline)

	// Generate test data
	var buf bytes.Buffer
	recordSize := maxSize / targetEvents
	for i := 0; i < targetEvents; i++ {
		padding := ""
		if recordSize > 100 {
			padding = fmt.Sprintf("%*s", recordSize-100, "")
		}
		fmt.Fprintf(&buf, `{"timestamp":%d,"message":"Log %d%s"}%s`,
			time.Now().UnixMilli(), i, padding, "\n")
	}

	// Compress
	var compressed bytes.Buffer
	gzw := gzip.NewWriter(&compressed)
	if _, err := gzw.Write(buf.Bytes()); err != nil {
		fmt.Printf("Error: gzip write failed: %v\n", err)
		return
	}
	gzw.Close()
	gzippedData := compressed.Bytes()

	// Snapshot before ProcessLogFile
	var before runtime.MemStats
	runtime.ReadMemStats(&before)

	// PROCESS (with GC disabled - true peak!)
	events, err := processor.ProcessLogFile(ctx, "test.json.gz", gzippedData, logger, int64(maxSize))
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	// Snapshot after ProcessLogFile (THIS IS THE TRUE PEAK - NO GC CLEANUP)
	var after runtime.MemStats
	runtime.ReadMemStats(&after)

	// Calculate metrics
	peakHeap := float64(after.HeapAlloc) / 1024 / 1024
	peakSys := float64(after.Sys) / 1024 / 1024
	heapDelta := float64(after.HeapAlloc-before.HeapAlloc) / 1024 / 1024
	heapDeltaFromBaseline := float64(after.HeapAlloc-baseline.HeapAlloc) / 1024 / 1024

	fmt.Printf("\n📊 %s:\n", label)
	fmt.Printf("  Events parsed: %d\n", len(events))
	fmt.Printf("  Compressed size: %.2f MB\n", float64(len(gzippedData))/1024/1024)
	fmt.Printf("  Uncompressed size: %.2f MB\n\n", float64(buf.Len())/1024/1024)

	fmt.Printf("  Baseline HeapAlloc: %.2f MB\n", float64(baseline.HeapAlloc)/1024/1024)
	fmt.Printf("  Before ProcessLogFile: %.2f MB\n", float64(before.HeapAlloc)/1024/1024)
	fmt.Printf("  After ProcessLogFile (NO GC): %.2f MB\n\n", peakHeap)

	fmt.Printf("  HeapAlloc delta (ProcessLogFile): %.2f MB\n", heapDelta)
	fmt.Printf("  HeapAlloc delta (from baseline): %.2f MB\n", heapDeltaFromBaseline)
	fmt.Printf("  Sys memory: %.2f MB\n\n", peakSys)

	fmt.Printf("  🎯 TRUE PEAK (no GC cleanup): %.2f MB\n", peakHeap)
	fmt.Printf("  📊 Projected Total (312 + peak): %.2f MB\n", 312+peakHeap)
	fmt.Printf("  ✅ Fits in 512 MB Lambda? %v\n", (312+peakHeap) < 512)
	fmt.Println("  " + string(make([]byte, 60)))

	// Keep events alive
	if len(events) > 0 {
		_ = events[0]
	}
}
