#!/bin/bash

# Entrypoint script to handle different execution modes
# Supports Lambda runtime, SQS polling, and manual input modes

MODE=${EXECUTION_MODE:-lambda}

case "$MODE" in
    "lambda")
        # Lambda runtime mode - use AWS Lambda Runtime Interface Emulator
        exec python3 -m awslambdaric log_processor.lambda_handler
        ;;
    "sqs")
        # SQS polling mode for local testing
        exec python3 log_processor.py --mode sqs
        ;;
    "manual")
        # Manual input mode for development/testing
        exec python3 log_processor.py --mode manual
        ;;
    "scan")
        # Scan mode for integration testing
        exec python3 log_processor.py --mode scan
        ;;
    *)
        echo "Unknown execution mode: $MODE"
        echo "Supported modes: lambda, sqs, manual, scan"
        exit 1
        ;;
esac