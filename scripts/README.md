# Local Integration Testing Scripts

This directory contains scripts for running the complete integration test suite locally using minikube and podman, replicating the same tests that run in GitHub Actions.

## Scripts

### `local-integration-test.sh`
Complete integration test suite that replicates the GitHub Actions workflow locally.

**What it tests:**
- All prerequisites from `test-local-setup.sh`
- Full container builds (API, processor, collector, fake generators)
- DynamoDB Local setup with proper connectivity
- MinIO deployment (S3-compatible storage)
- Tenant Configuration API deployment and testing
- Log processor deployment
- Multi-tenant fake log generators
- Vector collector DaemonSet
- End-to-end log collection and processing verification
- Log delivery to MinIO bucket validation

**Usage:**
```bash
chmod +x scripts/local-integration-test.sh
./scripts/local-integration-test.sh
```

**Runtime:** ~15-25 minutes

## Prerequisites

### Required Software
- **minikube**: Kubernetes cluster for local testing
- **podman**: Container runtime for building images
- **kubectl**: Kubernetes CLI (configured for minikube)
- **Python 3.13+**: For test dependencies and API
- **pip**: Python package manager
- **curl**: For health checks and connectivity tests

### Environment Setup
1. **Start minikube** (if not running):
   ```bash
   minikube start
   ```

2. **Verify connectivity**:
   ```bash
   kubectl cluster-info
   kubectl get nodes
   ```

3. **Check podman**:
   ```bash
   podman version
   ```

## How It Works

### Container Build Process
1. **API Container**: Builds from `api/Containerfile.server` with uvicorn
2. **Vector Collector**: Builds from `container/Containerfile.collector`
3. **Log Processor**: Builds from `container/Containerfile.processor_go (depends on collector)
4. **Fake Log Generator**: Builds from `test_container/Containerfile`

### Image Loading Strategy
Due to minikube using containerd instead of Docker, the scripts use:
1. `podman save` to export images as tar files
2. `minikube image load` to import tar files into minikube
3. Cleanup of temporary tar files

### Test Flow (Matches GitHub Actions Exactly)
1. **Environment Setup**: Prerequisites, create logging namespace, DynamoDB Local deployment
2. **Container Builds**: Build all 4 containers with `:local-test` tags and load into minikube
3. **Service Deployment**: MinIO → API → API Integration Tests → Processor → Multi-tenant Generators → Vector
4. **Log Processing**: Wait for collection, verify multi-tenant delivery to MinIO
5. **Validation**: Check logs, pod status, end-to-end multi-tenant functionality

### Key Differences from GitHub Actions
- Uses `podman` instead of `docker` for container builds
- Uses save/load method for minikube image loading instead of direct minikube load
- Uses static `local-test` overlays instead of `github` overlays
- Uses all the same DynamoDB Local, MinIO, and multi-tenant setup as GitHub Actions
- Follows identical step sequence: Prerequisites → DynamoDB → Build → MinIO → API → API Tests → Processor → Generators → Vector → Verification

## Troubleshooting

### Common Issues

#### minikube not running
```bash
minikube start
```

#### Container build failures
Check if the base images are accessible:
```bash
podman pull python:3.13-slim
podman pull registry.fedoraproject.org/fedora:42
```

#### Image loading failures
Verify minikube is using containerd:
```bash
minikube profile list
# Should show containerd runtime
```

#### DynamoDB Local connectivity issues
Check if port 8000 is already in use:
```bash
netstat -tulpn | grep 8000
```

#### kubectl connectivity issues
Verify minikube context:
```bash
kubectl config current-context
# Should show minikube
```

### Debugging Tips

1. **Check container logs**:
   ```bash
   podman logs <container-id>
   ```

2. **Check Kubernetes pod logs**:
   ```bash
   kubectl logs -l app=<app-name>
   ```

3. **Verify images in minikube**:
   ```bash
   minikube image ls | grep local-test
   ```

4. **Check static overlays**:
   ```bash
   ls k8s/*/overlays/local-test/
   ```

5. **Check service endpoints**:
   ```bash
   kubectl get services
   kubectl get endpoints
   ```

## Development

### Modifying the Scripts

The scripts are designed to be:
- **Self-contained**: All dependencies and cleanup handled automatically
- **Robust**: Comprehensive error handling and cleanup on exit
- **Informative**: Colored output with clear progress indicators
- **Static**: Uses pre-defined kustomize overlays instead of dynamic file creation
- **Consistent**: Matches GitHub Actions workflow exactly

### Adding New Tests

To add new test steps:
1. Create a new function following the existing pattern
2. Add it to the main execution flow
3. Include appropriate logging and error handling
4. Update the cleanup function if needed

### Overlay Customization

To test with different configurations:
1. Modify the overlay files in `k8s/*/overlays/local-test/`
2. Update container images, environment variables, or resource limits
3. Run the integration test to validate changes

### Container Customization

To test with different container configurations:
1. Modify the Containerfiles in their respective directories
2. Images are built with `:local-test` tags automatically
3. Run the integration test to validate changes

## Integration with CI/CD

These scripts serve as:
- **Development tool**: Test changes locally before pushing
- **CI/CD validation**: Ensure GitHub Actions workflow accuracy
- **Debugging aid**: Reproduce and debug integration issues locally
- **Documentation**: Live examples of the complete system deployment