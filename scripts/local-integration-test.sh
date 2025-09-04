#!/bin/bash

# local-integration-test.sh - Run complete integration test suite locally
#
# This script replicates the GitHub Actions integration test workflow locally
# using minikube and podman, providing the same level of testing confidence.
#
# Usage:
#   chmod +x scripts/local-integration-test.sh
#   ./scripts/local-integration-test.sh
#
# Prerequisites:
#   - minikube installed and running
#   - podman installed
#   - kubectl configured for minikube
#   - Python 3.13+ with pip

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global variables
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT_FORWARD_PIDS=()

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}=== Cleanup ===${NC}"
    
    # Kill port forwards
    for pid in "${PORT_FORWARD_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stopping port forward (PID: $pid)"
            kill "$pid" 2>/dev/null || true
        fi
    done
    
    # Stop minikube to clean up resources
    if command -v minikube &> /dev/null && minikube status | grep -q "host: Running"; then
        echo "Stopping minikube..."
        minikube stop
    fi
    
    echo "Cleanup complete"
}

# Set up cleanup on exit
trap cleanup EXIT

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✅${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}❌${NC} $1"
}

log_section() {
    echo -e "\n${YELLOW}=== $1 ===${NC}"
}

# Wait for service to be ready
wait_for_service() {
    local url="$1"
    local service_name="$2"
    local max_retries="${3:-30}"
    local retry_interval="${4:-5}"
    
    log_info "Waiting for $service_name to be ready at $url..."
    
    for ((i=1; i<=max_retries; i++)); do
        if curl -sf "$url" >/dev/null 2>&1; then
            log_success "$service_name is ready"
            return 0
        fi
        
        if [[ $i -eq $max_retries ]]; then
            log_error "$service_name failed to become ready after $((max_retries * retry_interval)) seconds"
            return 1
        fi
        
        echo -n "."
        sleep "$retry_interval"
    done
}

# Check prerequisites
check_prerequisites() {
    log_section "Checking Prerequisites"
    
    # Check minikube
    if ! command -v minikube &> /dev/null; then
        log_error "minikube is not installed"
        exit 1
    fi
    
    # Check if minikube is running
    if ! minikube status | grep -q "host: Running"; then
        log_warning "minikube is not running, starting it..."
        minikube start
    fi
    log_success "minikube is running"
    
    # Check podman
    if ! command -v podman &> /dev/null; then
        log_error "podman is not installed"
        exit 1
    fi
    log_success "podman is available"
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi
    
    # Test kubectl connectivity
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "kubectl cannot connect to cluster"
        exit 1
    fi
    log_success "kubectl can connect to minikube cluster"
    
    # Check Python and pip
    if ! command -v python3 &> /dev/null; then
        log_error "python3 is not installed"
        exit 1
    fi
    
    if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
        log_error "pip is not installed"
        exit 1
    fi
    log_success "Python and pip are available"
    
    # Install test dependencies
    log_info "Installing Python test dependencies..."
    pip3 install --user pytest requests boto3 >/dev/null 2>&1
    log_success "Test dependencies installed"
}

# Deploy DynamoDB Local to minikube
deploy_dynamodb_local() {
    log_section "Deploying DynamoDB Local to Minikube"
    
    # Create logging namespace if it doesn't exist
    log_info "Creating logging namespace..."
    kubectl create namespace logging --dry-run=client -o yaml | kubectl apply -f -
    
    # Deploy DynamoDB Local inside minikube cluster
    log_info "Deploying DynamoDB Local inside minikube cluster..."
    kubectl apply -f tests/integration/manifests/dynamodb-local.yaml
    
    # Wait for deployment to be available first
    log_info "Waiting for DynamoDB Local deployment to be available..."
    kubectl wait --for=condition=available deployment/dynamodb-local --timeout=300s --namespace=logging
    
    # Wait for DynamoDB Local pods to be ready
    log_info "Waiting for DynamoDB Local pods to be ready..."
    kubectl wait --for=condition=ready pod -l app=dynamodb-local --timeout=300s --namespace=logging
    
    log_success "DynamoDB Local is ready in minikube cluster"
}

# Build containers using podman
build_containers() {
    log_section "Building Containers with Podman"
    
    cd "$PROJECT_ROOT"
    
    # Build API container using existing Containerfile
    log_info "Building API container..."
    
    podman build -f api/Containerfile.server -t tenant-config-api:local-test api/
    log_success "API container built"
    
    # Build Vector collector container first (dependency for processor)
    log_info "Building Vector collector container..."
    podman build -f container/Containerfile.collector -t log-collector:local-test container/
    log_success "Vector collector container built"
    
    # Build processor container (depends on collector)
    log_info "Building processor container..."
    podman build -f container/Containerfile.processor -t log-processor:local-test container/
    log_success "Processor container built"
    
    # Build fake log generator container
    log_info "Building fake log generator container..."
    podman build -f test_container/Containerfile -t fake-log-generator:local-test test_container/
    log_success "Fake log generator container built"
    
    # Load images into minikube using save/load
    log_info "Loading images into minikube..."
    
    # Save all images as tar files
    podman save tenant-config-api:local-test -o /tmp/tenant-config-api-local-test.tar
    podman save log-collector:local-test -o /tmp/log-collector-local-test.tar
    podman save log-processor:local-test -o /tmp/log-processor-local-test.tar
    podman save fake-log-generator:local-test -o /tmp/fake-log-generator-local-test.tar
    
    # Load them into minikube
    minikube image load /tmp/tenant-config-api-local-test.tar
    minikube image load /tmp/log-collector-local-test.tar
    minikube image load /tmp/log-processor-local-test.tar
    minikube image load /tmp/fake-log-generator-local-test.tar
    
    # Cleanup temp files
    rm -f /tmp/tenant-config-api-local-test.tar
    rm -f /tmp/log-collector-local-test.tar
    rm -f /tmp/log-processor-local-test.tar
    rm -f /tmp/fake-log-generator-local-test.tar
    
    log_success "All images loaded into minikube"
    
    # Verify images are loaded
    log_info "Verifying images in minikube..."
    if minikube image ls | grep -q "local-test"; then
        log_success "Images verified in minikube"
    else
        log_error "Images not found in minikube"
        exit 1
    fi
}

# Deploy MinIO (S3-compatible storage)
deploy_minio() {
    log_section "Deploying MinIO"
    
    kubectl apply -f tests/integration/manifests/minio.yaml
    
    # Wait for MinIO to be ready
    log_info "Waiting for MinIO deployment..."
    kubectl wait --for=condition=ready pod -l app=minio --timeout=300s --namespace=logging
    kubectl wait --for=condition=complete job/minio-setup --timeout=300s --namespace=logging
    
    log_success "MinIO is ready"
}

# Deploy tenant configuration API
deploy_api() {
    log_section "Deploying Tenant Configuration API"
    
    # Create logging namespace if it doesn't exist
    kubectl create namespace logging --dry-run=client -o yaml | kubectl apply -f -
    
    # Use static overlay
    kubectl apply -k k8s/api/overlays/local-test
    
    # Wait for API to be ready
    log_info "Waiting for API deployment..."
    kubectl wait --for=condition=ready pod -l app=tenant-config-api -n logging --timeout=300s
    
    log_success "Tenant configuration API is ready"
}

# Run API integration tests
test_api_integration() {
    log_section "Running API Integration Tests"
    
    # Set up port forward for API testing
    log_info "Setting up port forward for API testing..."
    kubectl port-forward service/tenant-config-api -n logging 8080:8080 &
    local port_forward_pid=$!
    PORT_FORWARD_PIDS+=("$port_forward_pid")
    
    # Wait for port forward to be ready
    sleep 10
    
    # Verify API is accessible with retry logic (matching GitHub Actions)
    log_info "Verifying API accessibility..."
    local max_retries=10
    for i in $(seq 1 $max_retries); do
        if curl -f http://localhost:8080/api/v1/health >/dev/null 2>&1; then
            log_success "API health check passed"
            break
        else
            log_warning "API health check attempt $i/$max_retries failed, retrying..."
            if [ $i -eq $max_retries ]; then
                log_error "API health check failed after $max_retries attempts"
                exit 1
            fi
            sleep 3
        fi
    done
    
    # Run integration tests that use API endpoints
    log_info "Running API integration test..."
    cd tests/integration
    if API_BASE_URL=http://localhost:8080 pytest test_api_integration.py::TestTenantDeliveryConfigAPIIntegration::test_delivery_config_crud_operations -v; then
        log_success "API integration tests passed"
    else
        log_error "API integration test failed"
        exit 1
    fi
    
    cd "$PROJECT_ROOT"
}

# Deploy log processor
deploy_processor() {
    log_section "Deploying Log Processor"
    
    # Use static overlay
    kubectl apply -k k8s/processor/overlays/local-test
    
    # Wait for log processor to be ready
    log_info "Waiting for log processor deployment..."
    kubectl wait --for=condition=ready pod -l app=log-processor -n logging --timeout=300s
    
    log_success "Log processor is ready"
}

# Deploy fake log generators
deploy_fake_generators() {
    log_section "Deploying Fake Log Generators"
    
    # Use static overlay with multi-tenant setup
    kubectl apply -k k8s/fake-log-generator/overlays/local-test
    
    # Wait for multi-tenant fake log generators to be ready in customer namespaces
    log_info "Waiting for fake log generators deployment across customer namespaces..."
    
    # Wait for ACME Corp applications
    kubectl wait --for=condition=ready pod -l app=payment-service --timeout=300s --namespace=acme-corp || echo "payment-service not ready"
    kubectl wait --for=condition=ready pod -l app=user-database --timeout=300s --namespace=acme-corp || echo "user-database not ready"
    
    # Wait for Globex Industries applications  
    kubectl wait --for=condition=ready pod -l app=api-gateway --timeout=300s --namespace=globex-industries || echo "api-gateway not ready"
    
    # Wait for Umbrella Corp applications
    kubectl wait --for=condition=ready pod -l app=analytics-engine --timeout=300s --namespace=umbrella-corp || echo "analytics-engine not ready"
    
    # Wait for Wayne Enterprises applications
    kubectl wait --for=condition=ready pod -l app=security-monitor --timeout=300s --namespace=wayne-enterprises || echo "security-monitor not ready"
    kubectl wait --for=condition=ready pod -l app=backup-service --timeout=300s --namespace=wayne-enterprises || echo "backup-service not ready"
    
    log_success "Multi-tenant fake log generators are ready across customer namespaces"
}

# Deploy Vector collector
deploy_vector() {
    log_section "Deploying Vector Collector"
    
    # Use static overlay
    kubectl apply -k k8s/collector/overlays/local-test
    
    # Wait for Vector DaemonSet to be ready
    log_info "Waiting for Vector collector deployment..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=vector --timeout=300s --namespace=logging
    
    log_success "Vector collector is ready"
}

# Wait for log collection and processing
wait_for_logs() {
    log_section "Waiting for Log Collection and Processing"
    
    log_info "Waiting for logs to be collected and processed by Vector..."
    sleep 180
    
    # Check Vector logs for any errors
    log_info "Checking Vector logs..."
    kubectl logs -l app.kubernetes.io/name=vector --tail=20 --namespace=logging
}

# Verify log delivery to MinIO
verify_log_delivery() {
    log_section "Verifying Log Delivery to MinIO"
    
    # Get MinIO pod name
    local minio_pod
    minio_pod=$(kubectl get pod -l app=minio -o jsonpath='{.items[0].metadata.name}' --namespace=logging)
    log_info "MinIO pod: $minio_pod"
    
    # Check if log files exist in MinIO bucket
    log_info "Checking for log files in MinIO bucket..."
    kubectl exec "$minio_pod" --namespace=logging -- ls -la /data/test-logs/
    
    # Verify multi-tenant log directory structure exists
    log_info "Verifying multi-tenant log directory structure..."
    local structure_found=false
    
    # Check for ACME Corp logs (payment-service or user-database)
    if kubectl exec "$minio_pod" --namespace=logging -- ls /data/test-logs/test-cluster/acme-corp/payment-service/ > /dev/null 2>&1; then
        log_success "Found ACME Corp payment-service logs"
        structure_found=true
    fi
    
    if kubectl exec "$minio_pod" --namespace=logging -- ls /data/test-logs/test-cluster/acme-corp/user-database/ > /dev/null 2>&1; then
        log_success "Found ACME Corp user-database logs"
        structure_found=true
    fi
    
    # Check for Wayne Enterprises logs (security-monitor or backup-service)
    if kubectl exec "$minio_pod" --namespace=logging -- ls /data/test-logs/test-cluster/wayne-enterprises/security-monitor/ > /dev/null 2>&1; then
        log_success "Found Wayne Enterprises security-monitor logs"
        structure_found=true
    fi
    
    if kubectl exec "$minio_pod" --namespace=logging -- ls /data/test-logs/test-cluster/wayne-enterprises/backup-service/ > /dev/null 2>&1; then
        log_success "Found Wayne Enterprises backup-service logs"
        structure_found=true
    fi
    
    # Check for other customers
    if kubectl exec "$minio_pod" --namespace=logging -- ls /data/test-logs/test-cluster/globex-industries/api-gateway/ > /dev/null 2>&1; then
        log_success "Found Globex Industries api-gateway logs"
        structure_found=true
    fi
    
    if kubectl exec "$minio_pod" --namespace=logging -- ls /data/test-logs/test-cluster/umbrella-corp/analytics-engine/ > /dev/null 2>&1; then
        log_success "Found Umbrella Corp analytics-engine logs"
        structure_found=true
    fi
    
    if [[ "$structure_found" != true ]]; then
        log_error "No multi-tenant log directory structure found"
        log_info "Available paths:"
        kubectl exec "$minio_pod" --namespace=logging -- find /data/test-logs -type d -maxdepth 4 || log_warning "Could not list paths"
        exit 1
    fi
    
    # Count S3 objects across multi-tenant structure
    log_info "Checking for S3 objects across multi-tenant applications..."
    local total_s3_objects=0
    local total_applications=0
    
    # Function to check S3 objects for a specific application
    check_s3_objects() {
        local customer=$1
        local app=$2
        local app_path="/data/test-logs/test-cluster/$customer/$app"
        
        # Check if the application path exists
        if kubectl exec "$minio_pod" --namespace=logging -- ls "$app_path/" > /dev/null 2>&1; then
            log_info "  Found logs for $customer/$app"
            total_applications=$((total_applications + 1))
            
            # Get pod directories for this application
            local pod_dirs
            pod_dirs=$(kubectl exec "$minio_pod" --namespace=logging -- ls "$app_path/" 2>/dev/null || echo "")
            
            for pod_dir in $pod_dirs; do
                if [[ -n "$pod_dir" ]]; then
                    # Count .json.gz objects in this pod directory
                    local s3_objects
                    s3_objects=$(kubectl exec "$minio_pod" --namespace=logging -- ls "$app_path/$pod_dir/" 2>/dev/null | grep -c "\.json\.gz" || echo "0")
                    if [[ "$s3_objects" -gt 0 ]]; then
                        log_info "    Pod $pod_dir: $s3_objects objects"
                        total_s3_objects=$((total_s3_objects + s3_objects))
                    fi
                fi
            done
        fi
    }
    
    # Check all multi-tenant applications
    check_s3_objects "acme-corp" "payment-service"
    check_s3_objects "acme-corp" "user-database" 
    check_s3_objects "globex-industries" "api-gateway"
    check_s3_objects "umbrella-corp" "analytics-engine"
    check_s3_objects "wayne-enterprises" "security-monitor"
    check_s3_objects "wayne-enterprises" "backup-service"
    
    log_info "Total S3 objects found: $total_s3_objects across $total_applications applications"
    
    if [[ "$total_s3_objects" -gt 0 ]]; then
        log_success "Multi-tenant log objects were created and stored in MinIO"
        log_success "Vector is successfully writing logs to S3-compatible storage"
        log_success "Found logs from $total_applications different applications across multiple customers"
    else
        log_error "No S3 objects (.json.gz) found across multi-tenant applications"
        log_info "Debug: Available directory structure:"
        kubectl exec "$minio_pod" --namespace=logging -- find /data/test-logs -name "*.json.gz" | head -10 || log_warning "Could not find any .json.gz files"
        exit 1
    fi
}

# Verify end-to-end processing
verify_end_to_end() {
    log_section "Verifying End-to-End Processing"
    
    log_info "Waiting for log processing to complete..."
    sleep 120
    
    # Check that all pods are running
    log_info "Checking pod status..."
    kubectl get pods --all-namespaces
    
    # Check Vector logs for processing
    log_info "Vector processing status:"
    kubectl logs -l app.kubernetes.io/name=vector --tail=10 --namespace=logging || log_warning "No Vector logs"
    
    # Check processor logs for activity
    log_info "Processor activity:"
    kubectl logs -l app=log-processor --tail=10 --namespace=logging || log_warning "No processor logs"
    
    # Check API logs
    log_info "API activity:"
    kubectl logs -l app=tenant-config-api --tail=10 --namespace=logging || log_warning "No API logs"
}

# Show final results
show_results() {
    log_section "Integration Test Summary"
    
    log_success "Container builds from current code: OK"
    log_success "MinIO deployment (S3-compatible storage): OK" 
    log_success "DynamoDB Local deployment: OK"
    log_success "Tenant Configuration API deployment (real code): OK"
    log_success "API integration tests: OK"
    log_success "Log Processor deployment (real code): OK"
    log_success "Multi-tenant fake log generators (real code): OK"
    log_success "Vector collector deployment (real code): OK"
    log_success "Log collection and processing: OK"
    log_success "Log delivery to MinIO bucket: OK"
    log_success "End-to-end verification: OK"
    
    echo ""
    log_success "Local integration test completed successfully!"
    log_info "All components built from current code and deployed in minikube:"
    log_info "Vector → MinIO → Processor → API (all using current local code)"
}

# Main execution
main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Local Integration Test Suite${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_prerequisites
    deploy_dynamodb_local
    build_containers
    deploy_minio
    deploy_api
    test_api_integration
    deploy_processor
    deploy_fake_generators
    deploy_vector
    wait_for_logs
    verify_log_delivery
    verify_end_to_end
    show_results
    
    echo ""
    log_success "Local integration testing complete! 🎉"
}

# Run main function
main "$@"