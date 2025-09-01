#!/bin/bash

# Integration test script to run log processor externally
# This script sets up port forwards and runs the real log processor in scan mode

set -e

echo "=== Integration Test External Processor ==="
echo "This script runs the log processor externally using port-forwards"
echo

# Function to cleanup background processes
cleanup() {
    echo "Cleaning up background processes..."
    jobs -p | xargs -r kill
    wait
    echo "Cleanup complete"
}

# Set up cleanup on exit
trap cleanup EXIT

# Check if minikube is running
if ! kubectl get nodes &>/dev/null; then
    echo "ERROR: kubectl cannot connect to cluster. Is minikube running?"
    exit 1
fi

echo "✅ Kubernetes cluster is accessible"

# Check if required services are running
echo "Checking required services..."
kubectl get svc minio tenant-config-api dynamodb-local || {
    echo "ERROR: Required services not found. Deploy the integration manifests first:"
    echo "  kubectl apply -f tests/integration/manifests/"
    exit 1
}

echo "✅ Required services are running"

# Set up port forwards
echo "Setting up port forwards..."

echo "  - MinIO (9000:9000)"
kubectl port-forward service/minio 9000:9000 &
MINIO_PID=$!

echo "  - Tenant Config API (8080:8080)"  
kubectl port-forward service/tenant-config-api 8080:8080 &
API_PID=$!

echo "  - DynamoDB Local (8000:8000)"
kubectl port-forward service/dynamodb-local 8000:8000 &
DYNAMO_PID=$!

# Wait for port forwards to be ready
echo "Waiting for port forwards to be ready..."
sleep 5

# Verify port forwards are working
echo "Verifying port forwards..."

if ! curl -s http://localhost:9000/minio/health/live > /dev/null; then
    echo "WARNING: MinIO health check failed, but continuing..."
fi

if ! curl -s http://localhost:8080/health > /dev/null; then
    echo "WARNING: API health check failed, but continuing..."
fi

echo "✅ Port forwards are ready"

# Set up environment variables for integration testing
export TENANT_CONFIG_TABLE="integration-test-tenant-configs"
export AWS_REGION="us-east-1"
export SOURCE_BUCKET="test-logs"
export SCAN_INTERVAL="5"
export S3_ENDPOINT_URL="http://localhost:9000"

# For integration testing with MinIO
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"

echo "✅ Environment configured:"
echo "  TENANT_CONFIG_TABLE: $TENANT_CONFIG_TABLE"
echo "  SOURCE_BUCKET: $SOURCE_BUCKET"
echo "  SCAN_INTERVAL: $SCAN_INTERVAL"
echo "  S3_ENDPOINT_URL: $S3_ENDPOINT_URL"
echo

# Run the real log processor in scan mode
echo "🚀 Starting log processor in scan mode..."
echo "Press Ctrl+C to stop"
echo

cd "$(dirname "$0")/../.."
python3 container/log_processor.py --mode scan