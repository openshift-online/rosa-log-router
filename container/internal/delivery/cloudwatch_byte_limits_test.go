package delivery

import (
	"context"
	"log/slog"
	"os"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestCloudWatchByteLimitScenarios tests specific edge cases around CloudWatch PutLogEvents API limits,
// focusing on scenarios where the 26-byte overhead per event becomes significant
// and where batches approach the 1MB size limit.
//
// This test suite is based on the Python test suite from commit 8195ee5a03119 which fixed
// a critical batching bug where events were added BEFORE checking size limits.

const (
	// CloudWatch Logs limits
	maxBytesPerBatch  = 1047576 // 1MB limit
	maxEventsPerBatch = 10000   // CloudWatch event count limit
	eventOverhead     = 26      // bytes per event
)

// Helper to create a mock CloudWatch client for batching tests
type mockCloudWatchBatchingClient struct {
	putLogEventsCalls [][]types.InputLogEvent // Track each batch sent
	rejectedInfo      *types.RejectedLogEventsInfo
}

func (m *mockCloudWatchBatchingClient) PutLogEvents(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
	m.putLogEventsCalls = append(m.putLogEventsCalls, params.LogEvents)
	return &cloudwatchlogs.PutLogEventsOutput{
		RejectedLogEventsInfo: m.rejectedInfo,
	}, nil
}

func (m *mockCloudWatchBatchingClient) CreateLogGroup(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error) {
	return &cloudwatchlogs.CreateLogGroupOutput{}, nil
}

func (m *mockCloudWatchBatchingClient) CreateLogStream(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error) {
	return &cloudwatchlogs.CreateLogStreamOutput{}, nil
}

func (m *mockCloudWatchBatchingClient) DescribeLogGroups(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error) {
	return &cloudwatchlogs.DescribeLogGroupsOutput{
		LogGroups: []types.LogGroup{
			{LogGroupName: params.LogGroupNamePrefix},
		},
	}, nil
}

func (m *mockCloudWatchBatchingClient) DescribeLogStreams(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error) {
	return &cloudwatchlogs.DescribeLogStreamsOutput{
		LogStreams: []types.LogStream{
			{LogStreamName: params.LogStreamNamePrefix},
		},
	}, nil
}

// Helper to calculate batch size
func calculateBatchSize(events []types.InputLogEvent) int64 {
	var size int64
	for _, event := range events {
		size += int64(len(*event.Message)) + eventOverhead
	}
	return size
}

// Helper to create events with specific message size
func createEventsWithSize(count int, messageSize int) []types.InputLogEvent {
	events := make([]types.InputLogEvent, count)
	message := strings.Repeat("x", messageSize)
	for i := 0; i < count; i++ {
		events[i] = types.InputLogEvent{
			Timestamp: aws.Int64(1640995200000 + int64(i)),
			Message:   aws.String(message),
		}
	}
	return events
}

func TestMaximumEventsWithMinimalMessages(t *testing.T) {
	// Test maximum number of events that can fit in a batch with minimal (1-byte) messages.
	// This is the worst-case scenario where overhead dominates.
	//
	// Theoretical max: 1,047,576 bytes / (1 + 26) = 38,802 events
	theoreticalMax := maxBytesPerBatch / (1 + eventOverhead) // = 38,802

	// Create slightly more than theoretical max to test batching splits correctly
	numEvents := theoreticalMax + 100
	events := createEventsWithSize(numEvents, 1)

	mockClient := &mockCloudWatchBatchingClient{}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		50000, // High count limit to test byte limits
		maxBytesPerBatch,
		60, // Long timeout
		logger,
	)

	require.NoError(t, err)
	assert.Equal(t, numEvents, stats.SuccessfulEvents, "all events should be delivered successfully")
	assert.Equal(t, 0, stats.FailedEvents)

	// Should require exactly 2 batches: one at capacity, one small remainder
	require.Equal(t, 2, len(mockClient.putLogEventsCalls), "should split into 2 batches")

	// Verify first batch is at capacity but doesn't exceed limit
	firstBatch := mockClient.putLogEventsCalls[0]
	firstBatchSize := calculateBatchSize(firstBatch)
	assert.LessOrEqual(t, firstBatchSize, int64(maxBytesPerBatch), "first batch must not exceed 1MB limit")
	assert.Greater(t, firstBatchSize, int64(maxBytesPerBatch)*95/100, "first batch should be >95%% full (efficient packing)")

	// Verify second batch contains remainder
	secondBatch := mockClient.putLogEventsCalls[1]
	assert.Equal(t, 100, len(secondBatch), "second batch should contain the 100 remaining events")
}

func TestLargeEventsNearLimit(t *testing.T) {
	// Test scenario with a few very large events approaching the 256KB individual event limit.
	// CloudWatch has a 256KB limit per individual event.
	// This tests that batches split appropriately when events are large.

	// Create events with 200KB messages (well below 256KB individual limit)
	largeMessageSize := 200 * 1024 // 200KB
	numEvents := 10

	events := createEventsWithSize(numEvents, largeMessageSize)

	mockClient := &mockCloudWatchBatchingClient{}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		maxEventsPerBatch,
		maxBytesPerBatch,
		60,
		logger,
	)

	require.NoError(t, err)
	assert.Equal(t, numEvents, stats.SuccessfulEvents)

	// With 200KB events, each batch can only hold ~5 events (200KB * 5 = 1MB)
	// So we expect 2 batches
	require.GreaterOrEqual(t, len(mockClient.putLogEventsCalls), 2, "should require multiple batches for large events")

	// Verify no batch exceeds limit
	for i, batch := range mockClient.putLogEventsCalls {
		batchSize := calculateBatchSize(batch)
		assert.LessOrEqual(t, batchSize, int64(maxBytesPerBatch),
			"batch %d with size %d exceeds 1MB limit", i, batchSize)
	}
}

func TestExact1MBBoundary(t *testing.T) {
	// Test events that would create exactly 1MB batches.
	// This ensures we handle the boundary condition correctly.

	// Calculate message size that results in exactly 1MB when batched
	// If we want 1000 events to equal 1MB:
	// 1000 * (message_size + 26) = 1,047,576
	// message_size = (1,047,576 / 1000) - 26 = 1047.576 - 26 = 1021.576
	// Use 1021 bytes per message for clean math
	eventsPerBatch := 1000
	messageSize := (maxBytesPerBatch / eventsPerBatch) - eventOverhead

	// Create exactly 2 batches worth
	events := createEventsWithSize(eventsPerBatch*2, messageSize)

	mockClient := &mockCloudWatchBatchingClient{}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		maxEventsPerBatch,
		maxBytesPerBatch,
		60,
		logger,
	)

	require.NoError(t, err)
	assert.Equal(t, eventsPerBatch*2, stats.SuccessfulEvents)

	// Should create exactly 2 batches
	require.Equal(t, 2, len(mockClient.putLogEventsCalls))

	// Each batch should be very close to 1MB
	for i, batch := range mockClient.putLogEventsCalls {
		batchSize := calculateBatchSize(batch)
		assert.LessOrEqual(t, batchSize, int64(maxBytesPerBatch), "batch %d exceeds limit", i)
		assert.GreaterOrEqual(t, batchSize, int64(maxBytesPerBatch)*95/100, "batch %d should be >95%% full", i)
	}
}

func TestOneByteOverLimit(t *testing.T) {
	// Critical test: If adding one more event would put us 1 byte over the limit,
	// we should split to a new batch BEFORE adding that event.
	// This specifically tests the bug fix from PR110.

	// Create events where the last event would push us 1 byte over
	// Let's use events that are exactly 1KB each
	eventSize := 1000 // message size
	eventsInFirstBatch := maxBytesPerBatch / (eventSize + eventOverhead)

	// Create events: first batch worth + 1 more
	events := createEventsWithSize(eventsInFirstBatch+1, eventSize)

	mockClient := &mockCloudWatchBatchingClient{}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		maxEventsPerBatch,
		maxBytesPerBatch,
		60,
		logger,
	)

	require.NoError(t, err)
	assert.Equal(t, eventsInFirstBatch+1, stats.SuccessfulEvents)

	// Should create 2 batches
	require.Equal(t, 2, len(mockClient.putLogEventsCalls), "should split when next event would exceed limit")

	// First batch should not exceed limit
	firstBatchSize := calculateBatchSize(mockClient.putLogEventsCalls[0])
	assert.LessOrEqual(t, firstBatchSize, int64(maxBytesPerBatch), "first batch must not exceed limit")

	// Second batch should have exactly 1 event
	assert.Equal(t, 1, len(mockClient.putLogEventsCalls[1]), "second batch should contain the overflow event")
}

func TestManySmallEventsOverheadDominance(t *testing.T) {
	// Test scenario: Many tiny events where 26-byte overhead dominates.
	// This tests batching when overhead is 70-80% of total size.

	// Create 2000 very small events (5-10 bytes each)
	smallEvents := make([]types.InputLogEvent, 2000)
	for i := 0; i < 2000; i++ {
		messageSize := 5 + (i % 6) // 5-10 byte messages
		message := strings.Repeat("x", messageSize)
		smallEvents[i] = types.InputLogEvent{
			Timestamp: aws.Int64(1640995200000 + int64(i)),
			Message:   aws.String(message),
		}
	}

	// Calculate overhead percentage
	totalMessageBytes := int64(0)
	for _, event := range smallEvents {
		totalMessageBytes += int64(len(*event.Message))
	}
	totalOverheadBytes := int64(len(smallEvents)) * eventOverhead
	totalBytes := totalMessageBytes + totalOverheadBytes
	overheadPercentage := (float64(totalOverheadBytes) / float64(totalBytes)) * 100

	// Verify overhead is significant (> 70%)
	assert.Greater(t, overheadPercentage, 70.0,
		"expected overhead > 70%%, got %.1f%%. This test requires small messages to demonstrate overhead impact",
		overheadPercentage)

	mockClient := &mockCloudWatchBatchingClient{}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		smallEvents,
		1000,
		maxBytesPerBatch,
		5,
		logger,
	)

	require.NoError(t, err)
	assert.Equal(t, 2000, stats.SuccessfulEvents, "all events should be delivered")
	assert.Equal(t, 0, stats.FailedEvents)

	// Should require multiple batches due to size limit, not event count
	assert.GreaterOrEqual(t, len(mockClient.putLogEventsCalls), 2,
		"with high overhead ratio, should require multiple batches")

	// Verify all batches respect limits
	for i, batch := range mockClient.putLogEventsCalls {
		batchSize := calculateBatchSize(batch)
		assert.LessOrEqual(t, batchSize, int64(maxBytesPerBatch),
			"batch %d with %d events and %d bytes exceeds CloudWatch 1MB limit",
			i, len(batch), batchSize)
	}
}

func TestMixedEventSizes(t *testing.T) {
	// Test realistic scenario with mixed event sizes
	// Simulates real application logs with varying message lengths

	events := make([]types.InputLogEvent, 0)

	// Add small logs (100 bytes)
	events = append(events, createEventsWithSize(500, 100)...)

	// Add medium logs (1KB)
	events = append(events, createEventsWithSize(300, 1024)...)

	// Add large logs (50KB)
	events = append(events, createEventsWithSize(20, 50*1024)...)

	// Add tiny logs (10 bytes)
	events = append(events, createEventsWithSize(200, 10)...)

	mockClient := &mockCloudWatchBatchingClient{}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		maxEventsPerBatch,
		maxBytesPerBatch,
		60,
		logger,
	)

	require.NoError(t, err)
	assert.Equal(t, 1020, stats.SuccessfulEvents) // 500+300+20+200
	assert.Equal(t, 0, stats.FailedEvents)

	// Verify all batches respect limits
	for i, batch := range mockClient.putLogEventsCalls {
		batchSize := calculateBatchSize(batch)
		assert.LessOrEqual(t, batchSize, int64(maxBytesPerBatch),
			"batch %d exceeds limit", i)
		assert.LessOrEqual(t, len(batch), maxEventsPerBatch,
			"batch %d exceeds event count limit", i)
	}
}

func TestEventCountLimit(t *testing.T) {
	// Test that batching respects the 10,000 event count limit
	// even when byte size would allow more

	// Create 15,000 tiny events (well under byte limit)
	events := createEventsWithSize(15000, 10)

	mockClient := &mockCloudWatchBatchingClient{}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug}))

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		maxEventsPerBatch,
		maxBytesPerBatch,
		60,
		logger,
	)

	require.NoError(t, err)
	assert.Equal(t, 15000, stats.SuccessfulEvents)

	// Should create at least 2 batches (15000 / 10000)
	require.GreaterOrEqual(t, len(mockClient.putLogEventsCalls), 2)

	// Verify no batch exceeds event count limit
	for i, batch := range mockClient.putLogEventsCalls {
		assert.LessOrEqual(t, len(batch), maxEventsPerBatch,
			"batch %d has %d events, exceeds limit of %d",
			i, len(batch), maxEventsPerBatch)
	}
}

func TestOverheadCalculationAccuracy(t *testing.T) {
	// Test the accuracy of overhead calculations with extremely small messages.
	// Verifies that the 26-byte overhead is calculated correctly.

	events := []types.InputLogEvent{
		{Timestamp: aws.Int64(1640995200000), Message: aws.String("a")},   // 1 byte + 26 overhead = 27 bytes
		{Timestamp: aws.Int64(1640995200001), Message: aws.String("bb")},  // 2 bytes + 26 overhead = 28 bytes
		{Timestamp: aws.Int64(1640995200002), Message: aws.String("ccc")}, // 3 bytes + 26 overhead = 29 bytes
	}

	expectedMessageBytes := int64(1 + 2 + 3)                           // 6 bytes total
	expectedOverheadBytes := int64(3 * 26)                             // 78 bytes total
	expectedTotalBytes := expectedMessageBytes + expectedOverheadBytes // 84 bytes

	actualSize := calculateBatchSize(events)
	assert.Equal(t, expectedTotalBytes, actualSize,
		"batch size calculation incorrect: expected %d, got %d", expectedTotalBytes, actualSize)

	// Overhead should be ~92.9% of total (78/84)
	overheadPercentage := (float64(expectedOverheadBytes) / float64(expectedTotalBytes)) * 100
	assert.Greater(t, overheadPercentage, 90.0,
		"expected overhead > 90%% for tiny messages, got %.1f%%", overheadPercentage)
}
