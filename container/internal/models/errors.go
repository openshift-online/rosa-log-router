// Package models defines data structures, error types, and configuration for the log processor.
package models

import (
	"errors"
	"fmt"
)

// NonRecoverableError represents an error that should not be retried.
// Examples: missing tenant config, invalid S3 path, malformed data
type NonRecoverableError struct {
	Message string
	Err     error
}

func (e *NonRecoverableError) Error() string {
	if e.Err != nil {
		return fmt.Sprintf("%s: %v", e.Message, e.Err)
	}
	return e.Message
}

func (e *NonRecoverableError) Unwrap() error {
	return e.Err
}

// NewNonRecoverableError creates a new non-recoverable error
func NewNonRecoverableError(message string) *NonRecoverableError {
	return &NonRecoverableError{Message: message}
}

// WrapNonRecoverableError wraps an existing error as non-recoverable
func WrapNonRecoverableError(message string, err error) *NonRecoverableError {
	return &NonRecoverableError{Message: message, Err: err}
}

// IsNonRecoverable checks if an error is non-recoverable
func IsNonRecoverable(err error) bool {
	var nonRecoverable *NonRecoverableError
	return errors.As(err, &nonRecoverable)
}

// TenantNotFoundError represents a missing tenant configuration error
type TenantNotFoundError struct {
	TenantID string
	Message  string
	Err      error
}

func (e *TenantNotFoundError) Error() string {
	if e.Err != nil {
		return fmt.Sprintf("tenant %s: %s: %v", e.TenantID, e.Message, e.Err)
	}
	if e.Message != "" {
		return fmt.Sprintf("tenant %s: %s", e.TenantID, e.Message)
	}
	return fmt.Sprintf("tenant not found: %s", e.TenantID)
}

func (e *TenantNotFoundError) Unwrap() error {
	return e.Err
}

// As allows TenantNotFoundError to be treated as NonRecoverableError
func (e *TenantNotFoundError) As(target interface{}) bool {
	if _, ok := target.(**NonRecoverableError); ok {
		return true
	}
	return false
}

// NewTenantNotFoundError creates a new tenant not found error
func NewTenantNotFoundError(tenantID, message string) *TenantNotFoundError {
	return &TenantNotFoundError{TenantID: tenantID, Message: message}
}

// WrapTenantNotFoundError wraps an existing error as tenant not found
func WrapTenantNotFoundError(tenantID, message string, err error) *TenantNotFoundError {
	return &TenantNotFoundError{TenantID: tenantID, Message: message, Err: err}
}

// InvalidS3NotificationError represents an invalid S3 event notification error
type InvalidS3NotificationError struct {
	Message string
	Err     error
}

func (e *InvalidS3NotificationError) Error() string {
	if e.Err != nil {
		return fmt.Sprintf("invalid S3 notification: %s: %v", e.Message, e.Err)
	}
	return fmt.Sprintf("invalid S3 notification: %s", e.Message)
}

func (e *InvalidS3NotificationError) Unwrap() error {
	return e.Err
}

// As allows InvalidS3NotificationError to be treated as NonRecoverableError
func (e *InvalidS3NotificationError) As(target interface{}) bool {
	if _, ok := target.(**NonRecoverableError); ok {
		return true
	}
	return false
}

// NewInvalidS3NotificationError creates a new invalid S3 notification error
func NewInvalidS3NotificationError(message string) *InvalidS3NotificationError {
	return &InvalidS3NotificationError{Message: message}
}

// WrapInvalidS3NotificationError wraps an existing error as invalid S3 notification
func WrapInvalidS3NotificationError(message string, err error) *InvalidS3NotificationError {
	return &InvalidS3NotificationError{Message: message, Err: err}
}
