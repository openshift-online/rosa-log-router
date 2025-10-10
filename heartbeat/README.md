# Vector Heartbeat Container

A minimal Go application that emits structured JSON logs every 2 minutes to verify that the Vector logging pipeline is actively collecting and forwarding logs.

## Purpose

This heartbeat container solves a critical observability problem: **How do you know if Vector has stopped working?**

When Vector is configured to collect logs from applications, it only forwards logs when applications generate them. If applications are idle or Vector stops functioning, there's no log traffic, making it impossible to distinguish between:
- Applications producing no logs (normal)
- Vector failing to collect logs (problem)

The heartbeat container ensures there's always a predictable log source. If these heartbeat logs stop appearing in your destination (S3, CloudWatch, etc.), you immediately know there's a pipeline issue.

## Features

- **Minimal footprint**: Built with Go on UBI9-micro base (~10MB container)
- **Low resource usage**: 8Mi memory request, 10m CPU request
- **Structured JSON logs**: Easy to parse and alert on
- **Predictable timing**: Emits logs exactly every 2 minutes
- **Production-ready**: Non-root, read-only, minimal security context

## Log Format

```json
{
  "timestamp": "2025-10-10T12:34:56Z",
  "level": "INFO",
  "message": "Vector heartbeat - logging pipeline active",
  "heartbeat": true,
  "interval_seconds": 120,
  "source": "heartbeat-container"
}
```

## Building the Container

```bash
cd heartbeat/

# Build locally with Podman
podman build -f Containerfile -t heartbeat:latest .

# Test locally
podman run --rm heartbeat:latest

# Build and push to ECR
aws ecr get-login-password --region us-east-1 | \
  podman login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

podman tag heartbeat:latest <account>.dkr.ecr.us-east-1.amazonaws.com/heartbeat:main
podman push <account>.dkr.ecr.us-east-1.amazonaws.com/heartbeat:main
```

## Deploying to Kubernetes

Using kustomize:

```bash
# Deploy to cluster
kubectl apply -k k8s/heartbeat/base/

# Verify deployment
kubectl get pods -n logging -l app=vector-heartbeat

# Check logs
kubectl logs -n logging -l app=vector-heartbeat --tail=10
```

The deployment will create:
- **Namespace**: `logging` (with Vector collection label)
- **Deployment**: `vector-heartbeat` with 1 replica

## Verifying Pipeline Health

### Check S3 for Heartbeat Logs

```bash
# List recent heartbeat log files
aws s3 ls s3://your-bucket/heartbeat/ --recursive | tail -20

# Download and inspect a recent log file
aws s3 cp s3://your-bucket/path/to/heartbeat.json.gz - | gunzip | jq '.heartbeat'
```

### Check CloudWatch for Heartbeat Logs

```bash
# Query CloudWatch Logs for heartbeat messages
aws logs filter-log-events \
  --log-group-name /aws/logs/your-log-group \
  --filter-pattern '{ $.heartbeat = true }' \
  --start-time $(date -d '30 minutes ago' +%s)000
```

### Set Up Alerting

Create a CloudWatch alarm or monitoring query that alerts when:
- No heartbeat logs received in the last 5 minutes (2.5x the interval)
- This indicates Vector or the collection pipeline has failed

## Resource Usage

The heartbeat container is extremely lightweight:

**Requests:**
- Memory: 8Mi
- CPU: 10m (0.01 cores)

**Limits:**
- Memory: 16Mi
- CPU: 20m (0.02 cores)

This makes it safe to run alongside other workloads without impacting cluster resources.

## Architecture

```
┌─────────────────────┐
│  Heartbeat Pod      │
│  (logging namespace)│
│                     │
│  Emits JSON every   │
│  2 minutes          │
└──────────┬──────────┘
           │
           │ stdout
           │
           ▼
    ┌──────────────┐
    │    Vector    │
    │  DaemonSet   │
    │              │
    │  Collects    │
    │  from pods   │
    │  in labeled  │
    │  namespaces  │
    └──────┬───────┘
           │
           ▼
     ┌─────────┐
     │   S3    │
     │CloudWatch│
     │   etc.  │
     └─────────┘
```

## Troubleshooting

### Heartbeat pod not starting

```bash
kubectl describe pod -n logging -l app=vector-heartbeat
```

Check for image pull errors or resource constraints.

### Heartbeat logs not appearing in Vector

1. Verify namespace has the required label:
   ```bash
   kubectl get namespace logging -o jsonpath='{.metadata.labels}'
   ```
   Should contain: `hypershift.openshift.io/hosted-control-plane: "true"`

2. Check Vector is collecting from the logging namespace:
   ```bash
   kubectl logs -n logging daemonset/vector-logs | grep heartbeat
   ```

### Heartbeat logs not reaching destination

If logs appear in Vector but not in S3/CloudWatch:
- Check Vector configuration for routing rules
- Verify AWS credentials and permissions
- Check Vector metrics for delivery errors

## Development

To modify the heartbeat interval:

1. Edit `main.go`:
   ```go
   const heartbeatInterval = 5 * time.Minute  // Change to desired interval
   ```

2. Rebuild and redeploy:
   ```bash
   podman build -f Containerfile -t heartbeat:latest .
   # Push to registry and update deployment
   ```

## Security

The container follows security best practices:
- **Non-root user**: Runs as UID 1001
- **Read-only root filesystem**: No writable filesystem (except stdout)
- **Dropped capabilities**: All Linux capabilities dropped
- **Seccomp**: Runtime default seccomp profile
- **No privilege escalation**: `allowPrivilegeEscalation: false`
