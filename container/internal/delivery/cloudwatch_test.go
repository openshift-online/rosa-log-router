package delivery

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Mock CloudWatch Logs client for testing
type mockCloudWatchLogsClient struct {
	createLogGroupFunc     func(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error)
	createLogStreamFunc    func(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error)
	putLogEventsFunc       func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error)
	describeLogGroupsFunc  func(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error)
	describeLogStreamsFunc func(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error)
}

func (m *mockCloudWatchLogsClient) CreateLogGroup(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error) {
	if m.createLogGroupFunc != nil {
		return m.createLogGroupFunc(ctx, params, optFns...)
	}
	return &cloudwatchlogs.CreateLogGroupOutput{}, nil
}

func (m *mockCloudWatchLogsClient) CreateLogStream(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error) {
	if m.createLogStreamFunc != nil {
		return m.createLogStreamFunc(ctx, params, optFns...)
	}
	return &cloudwatchlogs.CreateLogStreamOutput{}, nil
}

func (m *mockCloudWatchLogsClient) PutLogEvents(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
	if m.putLogEventsFunc != nil {
		return m.putLogEventsFunc(ctx, params, optFns...)
	}
	return &cloudwatchlogs.PutLogEventsOutput{}, nil
}

func (m *mockCloudWatchLogsClient) DescribeLogGroups(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error) {
	if m.describeLogGroupsFunc != nil {
		return m.describeLogGroupsFunc(ctx, params, optFns...)
	}
	return &cloudwatchlogs.DescribeLogGroupsOutput{}, nil
}

func (m *mockCloudWatchLogsClient) DescribeLogStreams(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error) {
	if m.describeLogStreamsFunc != nil {
		return m.describeLogStreamsFunc(ctx, params, optFns...)
	}
	return &cloudwatchlogs.DescribeLogStreamsOutput{}, nil
}

func TestDeliverEventsInBatchesMaxEvents(t *testing.T) {
	logger := models.NewDefaultLogger()

	capturedBatches := make([][]types.InputLogEvent, 0)
	mockClient := &mockCloudWatchLogsClient{
		putLogEventsFunc: func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
			// Capture the batch
			batch := make([]types.InputLogEvent, len(params.LogEvents))
			copy(batch, params.LogEvents)
			capturedBatches = append(capturedBatches, batch)
			return &cloudwatchlogs.PutLogEventsOutput{}, nil
		},
	}

	// Create exactly 1,500 events to test multiple batches
	events := make([]types.InputLogEvent, 1500)
	for i := 0; i < 1500; i++ {
		timestamp := aws.Int64(time.Now().UnixMilli() + int64(i))
		message := aws.String("Test log event")
		events[i] = types.InputLogEvent{
			Timestamp: timestamp,
			Message:   message,
		}
	}

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		1000,    // maxEventsPerBatch
		1037576, // maxBytesPerBatch
		5,       // timeoutSeconds
		logger,
	)

	require.NoError(t, err)

	// Should make exactly 2 API calls: 1000 + 500 events
	assert.Len(t, capturedBatches, 2)

	// Verify first batch has exactly 1000 events
	assert.Len(t, capturedBatches[0], 1000)

	// Verify second batch has remaining 500 events
	assert.Len(t, capturedBatches[1], 500)

	// Verify all events were processed
	assert.Equal(t, 1500, stats.SuccessfulEvents)
	assert.Equal(t, 0, stats.FailedEvents)
}

func TestDeliverEventsInBatchesPartialSuccess(t *testing.T) {
	logger := models.NewDefaultLogger()

	mockClient := &mockCloudWatchLogsClient{
		putLogEventsFunc: func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
			// Mock CloudWatch response with some rejected events
			tooOldIndex := aws.Int32(1) // First 2 events rejected as too old
			tooNewIndex := aws.Int32(8) // Last 2 events rejected as too new

			return &cloudwatchlogs.PutLogEventsOutput{
				RejectedLogEventsInfo: &types.RejectedLogEventsInfo{
					TooOldLogEventEndIndex:   tooOldIndex,
					TooNewLogEventStartIndex: tooNewIndex,
				},
			}, nil
		},
	}

	// Create 10 events
	events := make([]types.InputLogEvent, 10)
	baseTime := time.Now().UnixMilli()
	for i := 0; i < 10; i++ {
		events[i] = types.InputLogEvent{
			Timestamp: aws.Int64(baseTime + int64(i)),
			Message:   aws.String("Test event"),
		}
	}

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		1000,
		1037576,
		5,
		logger,
	)

	require.NoError(t, err)

	// Should report partial success: 6 successful (events 2-7), 4 failed (0-1, 8-9)
	assert.Equal(t, 6, stats.SuccessfulEvents)
	assert.Equal(t, 4, stats.FailedEvents)
	assert.Equal(t, 10, stats.TotalProcessed)
}

func TestDeliverEventsInBatchesRetryLogic(t *testing.T) {
	logger := models.NewDefaultLogger()

	callCount := 0
	mockClient := &mockCloudWatchLogsClient{
		putLogEventsFunc: func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
			callCount++
			// First two calls fail with throttling, third succeeds
			if callCount <= 2 {
				return nil, &types.ThrottlingException{
					Message: aws.String("Rate exceeded"),
				}
			}
			return &cloudwatchlogs.PutLogEventsOutput{}, nil
		},
	}

	events := []types.InputLogEvent{
		{
			Timestamp: aws.Int64(time.Now().UnixMilli()),
			Message:   aws.String("Test event"),
		},
	}

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		1000,
		1037576,
		5,
		logger,
	)

	require.NoError(t, err)

	// Should have made 3 attempts
	assert.Equal(t, 3, callCount)

	// Should report success after retries
	assert.Equal(t, 1, stats.SuccessfulEvents)
	assert.Equal(t, 0, stats.FailedEvents)
}

func TestDeliverEventsInBatchesMaxRetriesExhausted(t *testing.T) {
	logger := models.NewDefaultLogger()

	callCount := 0
	mockClient := &mockCloudWatchLogsClient{
		putLogEventsFunc: func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
			callCount++
			// All calls get throttled (exceed max retries)
			return nil, &types.ThrottlingException{
				Message: aws.String("Rate exceeded"),
			}
		},
	}

	events := []types.InputLogEvent{
		{
			Timestamp: aws.Int64(time.Now().UnixMilli()),
			Message:   aws.String("Test event"),
		},
	}

	_, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		1000,
		1037576,
		5,
		logger,
	)

	require.Error(t, err)

	// Should have made 3 attempts (1 initial + 2 retries)
	assert.Equal(t, 3, callCount)

	// Error should indicate throttling
	assert.Contains(t, err.Error(), "after 3 attempts")
}

func TestDeliverEventsInBatchesEmptyList(t *testing.T) {
	logger := models.NewDefaultLogger()

	mockClient := &mockCloudWatchLogsClient{
		putLogEventsFunc: func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
			t.Fatal("PutLogEvents should not be called for empty events list")
			return nil, nil
		},
	}

	events := []types.InputLogEvent{}

	stats, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		1000,
		1037576,
		5,
		logger,
	)

	require.NoError(t, err)

	// Should handle empty list gracefully
	assert.Equal(t, 0, stats.SuccessfulEvents)
	assert.Equal(t, 0, stats.FailedEvents)
	assert.Equal(t, 0, stats.TotalProcessed)
}

func TestDeliverEventsInBatchesChronologicalOrdering(t *testing.T) {
	logger := models.NewDefaultLogger()

	var capturedEvents []types.InputLogEvent
	mockClient := &mockCloudWatchLogsClient{
		putLogEventsFunc: func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
			capturedEvents = params.LogEvents
			return &cloudwatchlogs.PutLogEventsOutput{}, nil
		},
	}

	baseTime := time.Now().UnixMilli()
	// Create events with out-of-order timestamps
	events := []types.InputLogEvent{
		{Timestamp: aws.Int64(baseTime + 2000), Message: aws.String("Third event")},
		{Timestamp: aws.Int64(baseTime), Message: aws.String("First event")},
		{Timestamp: aws.Int64(baseTime + 1000), Message: aws.String("Second event")},
		{Timestamp: aws.Int64(baseTime + 3000), Message: aws.String("Fourth event")},
	}

	_, err := deliverEventsInBatches(
		context.Background(),
		mockClient,
		"test-group",
		"test-stream",
		events,
		1000,
		1037576,
		5,
		logger,
	)

	require.NoError(t, err)

	// Verify events were sent (but not necessarily sorted by this function)
	require.Len(t, capturedEvents, 4)

	// Note: The sorting happens in deliverLogsNative before calling deliverEventsInBatches
	// This test just verifies that the function preserves the order it receives
	assert.Equal(t, "Third event", *capturedEvents[0].Message)
	assert.Equal(t, "First event", *capturedEvents[1].Message)
	assert.Equal(t, "Second event", *capturedEvents[2].Message)
	assert.Equal(t, "Fourth event", *capturedEvents[3].Message)
}

func TestDeliverEventsInBatchesRejectedEventsHandling(t *testing.T) {
	logger := models.NewDefaultLogger()

	testCases := []struct {
		name           string
		rejectionInfo  *types.RejectedLogEventsInfo
		totalEvents    int
		expectedFailed int
	}{
		{
			name: "too_old_events",
			rejectionInfo: &types.RejectedLogEventsInfo{
				TooOldLogEventEndIndex: aws.Int32(2),
			},
			totalEvents:    10,
			expectedFailed: 3, // Events 0, 1, 2 are too old
		},
		{
			name: "too_new_events",
			rejectionInfo: &types.RejectedLogEventsInfo{
				TooNewLogEventStartIndex: aws.Int32(7),
			},
			totalEvents:    10,
			expectedFailed: 3, // Events 7, 8, 9 are too new
		},
		{
			name: "expired_events",
			rejectionInfo: &types.RejectedLogEventsInfo{
				ExpiredLogEventEndIndex: aws.Int32(4),
			},
			totalEvents:    10,
			expectedFailed: 5, // Events 0, 1, 2, 3, 4 are expired
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			mockClient := &mockCloudWatchLogsClient{
				putLogEventsFunc: func(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error) {
					return &cloudwatchlogs.PutLogEventsOutput{
						RejectedLogEventsInfo: tc.rejectionInfo,
					}, nil
				},
			}

			events := make([]types.InputLogEvent, tc.totalEvents)
			baseTime := time.Now().UnixMilli()
			for i := 0; i < tc.totalEvents; i++ {
				events[i] = types.InputLogEvent{
					Timestamp: aws.Int64(baseTime + int64(i)),
					Message:   aws.String("Test event"),
				}
			}

			stats, err := deliverEventsInBatches(
				context.Background(),
				mockClient,
				"test-group",
				"test-stream",
				events,
				1000,
				1037576,
				5,
				logger,
			)

			require.NoError(t, err)

			expectedSuccess := tc.totalEvents - tc.expectedFailed
			assert.Equal(t, expectedSuccess, stats.SuccessfulEvents, "Failed for case: %s", tc.name)
			assert.Equal(t, tc.expectedFailed, stats.FailedEvents, "Failed for case: %s", tc.name)
		})
	}
}

func TestEnsureLogGroupAndStreamExist(t *testing.T) {
	logger := models.NewDefaultLogger()

	t.Run("creates_new_group_and_stream", func(t *testing.T) {
		createGroupCalled := false
		createStreamCalled := false

		mockClient := &mockCloudWatchLogsClient{
			describeLogGroupsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error) {
				// Simulate group doesn't exist
				return &cloudwatchlogs.DescribeLogGroupsOutput{
					LogGroups: []types.LogGroup{},
				}, nil
			},
			createLogGroupFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error) {
				createGroupCalled = true
				assert.Equal(t, "/aws/logs/test-group", *params.LogGroupName)
				return &cloudwatchlogs.CreateLogGroupOutput{}, nil
			},
			describeLogStreamsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error) {
				// Simulate stream doesn't exist
				return &cloudwatchlogs.DescribeLogStreamsOutput{
					LogStreams: []types.LogStream{},
				}, nil
			},
			createLogStreamFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error) {
				createStreamCalled = true
				assert.Equal(t, "/aws/logs/test-group", *params.LogGroupName)
				assert.Equal(t, "test-stream", *params.LogStreamName)
				return &cloudwatchlogs.CreateLogStreamOutput{}, nil
			},
		}

		err := ensureLogGroupAndStreamExist(
			context.Background(),
			mockClient,
			"/aws/logs/test-group",
			"test-stream",
			logger,
		)

		require.NoError(t, err)
		assert.True(t, createGroupCalled, "CreateLogGroup should be called")
		assert.True(t, createStreamCalled, "CreateLogStream should be called")
	})

	t.Run("group_exists_creates_stream", func(t *testing.T) {
		createGroupCalled := false
		createStreamCalled := false

		mockClient := &mockCloudWatchLogsClient{
			describeLogGroupsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error) {
				// Simulate group exists
				return &cloudwatchlogs.DescribeLogGroupsOutput{
					LogGroups: []types.LogGroup{
						{LogGroupName: aws.String("/aws/logs/test-group")},
					},
				}, nil
			},
			createLogGroupFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error) {
				createGroupCalled = true
				return &cloudwatchlogs.CreateLogGroupOutput{}, nil
			},
			describeLogStreamsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error) {
				// Simulate stream doesn't exist
				return &cloudwatchlogs.DescribeLogStreamsOutput{
					LogStreams: []types.LogStream{},
				}, nil
			},
			createLogStreamFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error) {
				createStreamCalled = true
				return &cloudwatchlogs.CreateLogStreamOutput{}, nil
			},
		}

		err := ensureLogGroupAndStreamExist(
			context.Background(),
			mockClient,
			"/aws/logs/test-group",
			"test-stream",
			logger,
		)

		require.NoError(t, err)
		assert.False(t, createGroupCalled, "CreateLogGroup should NOT be called when group exists")
		assert.True(t, createStreamCalled, "CreateLogStream should be called")
	})

	t.Run("both_exist_no_creation", func(t *testing.T) {
		createGroupCalled := false
		createStreamCalled := false

		mockClient := &mockCloudWatchLogsClient{
			describeLogGroupsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error) {
				return &cloudwatchlogs.DescribeLogGroupsOutput{
					LogGroups: []types.LogGroup{
						{LogGroupName: aws.String("/aws/logs/test-group")},
					},
				}, nil
			},
			createLogGroupFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error) {
				createGroupCalled = true
				return &cloudwatchlogs.CreateLogGroupOutput{}, nil
			},
			describeLogStreamsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error) {
				return &cloudwatchlogs.DescribeLogStreamsOutput{
					LogStreams: []types.LogStream{
						{LogStreamName: aws.String("test-stream")},
					},
				}, nil
			},
			createLogStreamFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error) {
				createStreamCalled = true
				return &cloudwatchlogs.CreateLogStreamOutput{}, nil
			},
		}

		err := ensureLogGroupAndStreamExist(
			context.Background(),
			mockClient,
			"/aws/logs/test-group",
			"test-stream",
			logger,
		)

		require.NoError(t, err)
		assert.False(t, createGroupCalled, "CreateLogGroup should NOT be called when group exists")
		assert.False(t, createStreamCalled, "CreateLogStream should NOT be called when stream exists")
	})

	t.Run("handles_already_exists_errors", func(t *testing.T) {
		mockClient := &mockCloudWatchLogsClient{
			describeLogGroupsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error) {
				return &cloudwatchlogs.DescribeLogGroupsOutput{
					LogGroups: []types.LogGroup{},
				}, nil
			},
			createLogGroupFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error) {
				// Simulate concurrent creation
				return nil, &types.ResourceAlreadyExistsException{
					Message: aws.String("Log group already exists"),
				}
			},
			describeLogStreamsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error) {
				return &cloudwatchlogs.DescribeLogStreamsOutput{
					LogStreams: []types.LogStream{},
				}, nil
			},
			createLogStreamFunc: func(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error) {
				// Simulate concurrent creation
				return nil, &types.ResourceAlreadyExistsException{
					Message: aws.String("Log stream already exists"),
				}
			},
		}

		err := ensureLogGroupAndStreamExist(
			context.Background(),
			mockClient,
			"/aws/logs/test-group",
			"test-stream",
			logger,
		)

		// Should not error when resources already exist
		require.NoError(t, err)
	})

	t.Run("propagates_other_errors", func(t *testing.T) {
		mockClient := &mockCloudWatchLogsClient{
			describeLogGroupsFunc: func(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error) {
				return nil, errors.New("service unavailable")
			},
		}

		err := ensureLogGroupAndStreamExist(
			context.Background(),
			mockClient,
			"/aws/logs/test-group",
			"test-stream",
			logger,
		)

		require.Error(t, err)
		assert.Contains(t, err.Error(), "service unavailable")
	})
}
