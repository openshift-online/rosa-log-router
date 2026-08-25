package models

import (
	"errors"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNonRecoverableError(t *testing.T) {
	t.Run("creates error with message", func(t *testing.T) {
		err := NewNonRecoverableError("test error")
		assert.NotNil(t, err)
		assert.Equal(t, "test error", err.Error())
	})

	t.Run("wraps underlying error", func(t *testing.T) {
		baseErr := errors.New("base error")
		err := WrapNonRecoverableError("wrapper", baseErr)
		assert.NotNil(t, err)
		assert.Contains(t, err.Error(), "wrapper")
		assert.Contains(t, err.Error(), "base error")
		assert.Equal(t, baseErr, err.Unwrap())
	})

	t.Run("IsNonRecoverable detects non-recoverable errors", func(t *testing.T) {
		err := NewNonRecoverableError("test")
		assert.True(t, IsNonRecoverable(err))

		regularErr := errors.New("regular error")
		assert.False(t, IsNonRecoverable(regularErr))

		var nilErr error = nil
		assert.False(t, IsNonRecoverable(nilErr))
	})
}

func TestTenantNotFoundError(t *testing.T) {
	t.Run("creates error with tenant ID and message", func(t *testing.T) {
		err := NewTenantNotFoundError("tenant-123", "no configs found")
		assert.NotNil(t, err)
		assert.Contains(t, err.Error(), "tenant-123")
		assert.Contains(t, err.Error(), "no configs found")
	})

	t.Run("wraps underlying error", func(t *testing.T) {
		baseErr := errors.New("dynamodb error")
		err := WrapTenantNotFoundError("tenant-456", "lookup failed", baseErr)
		assert.NotNil(t, err)
		assert.Contains(t, err.Error(), "tenant-456")
		assert.Contains(t, err.Error(), "lookup failed")
		assert.Equal(t, baseErr, err.Unwrap())
	})

	t.Run("is treated as non-recoverable", func(t *testing.T) {
		err := NewTenantNotFoundError("tenant-789", "missing")
		// TenantNotFoundError should be detectable as NonRecoverableError
		var nonRecoverable *NonRecoverableError
		assert.True(t, errors.As(err, &nonRecoverable))
	})
}

func TestInvalidS3NotificationError(t *testing.T) {
	t.Run("creates error with message", func(t *testing.T) {
		err := NewInvalidS3NotificationError("invalid format")
		assert.NotNil(t, err)
		assert.Contains(t, err.Error(), "invalid S3 notification")
		assert.Contains(t, err.Error(), "invalid format")
	})

	t.Run("wraps underlying error", func(t *testing.T) {
		baseErr := errors.New("json parse error")
		err := WrapInvalidS3NotificationError("malformed", baseErr)
		assert.NotNil(t, err)
		assert.Contains(t, err.Error(), "malformed")
		assert.Equal(t, baseErr, err.Unwrap())
	})

	t.Run("is treated as non-recoverable", func(t *testing.T) {
		err := NewInvalidS3NotificationError("bad data")
		var nonRecoverable *NonRecoverableError
		assert.True(t, errors.As(err, &nonRecoverable))
	})
}

func TestIsPermissionError(t *testing.T) {
	tests := []struct {
		name     string
		err      error
		expected bool
	}{
		{"nil error", nil, false},
		{"AccessDenied from AWS SDK", errors.New("AccessDenied: User is not authorized"), true},
		{"access denied lowercase", errors.New("access denied to S3 bucket 'foo'"), true},
		{"not authorized", errors.New("User: arn:aws:iam::123:role/X is not authorized to perform: sts:AssumeRole"), true},
		{"timeout error", errors.New("RequestTimeout: connection timed out"), false},
		{"throttling error", errors.New("SlowDown: Please reduce your request rate"), false},
		{"wrapped AccessDenied", fmt.Errorf("failed to assume customer role: %w", errors.New("AccessDenied: forbidden")), true},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			assert.Equal(t, tc.expected, IsPermissionError(tc.err))
		})
	}
}
