# Multi-Tenant Logging Kubernetes Components

This directory contains the Kustomize manifests for the Kubernetes-deployed
components of the multi-tenant logging pipeline.

> **Deployment reality — read this first.**
> Most of the pipeline does **not** run as Kubernetes workloads in production:
> - The **log processor** and the **tenant-configuration API** run as **AWS
>   Lambda container images**, deployed via Terraform (`terraform/`). There are
>   no Kubernetes Deployments for them.
> - The **Vector collector** runs as a privileged DaemonSet on management
>   clusters, but in production it is deployed by a **separate system**
>   (osd-fleet-manager), *not* from this repository. The manifests here are the
>   prod-shaped **reference** for that configuration and are what the LocalStack
>   integration test exercises.
>
> As a result, this directory intentionally contains only the collector and
> heartbeat manifests. It is not a full deployment surface.

## Directory Structure

```
k8s/
├── README.md
├── collector/                       # Vector log collection agent (DaemonSet)
│   ├── base/                        # Prod-shaped reference config
│   │   ├── kustomization.yaml
│   │   ├── service-account.yaml
│   │   ├── vector-config.yaml       # Vector ConfigMap (source of truth)
│   │   ├── vector-daemonset.yaml
│   │   ├── vector-clusterrole.yaml
│   │   └── vector-clusterrolebinding.yaml
│   └── overlays/
│       └── localstack/              # Used by the LocalStack integration test
└── heartbeat/                       # Synthetic liveness emitter (reference)
    └── base/
```

## Collector (Vector)

`collector/base` is the canonical description of how Vector should be configured
in production:

- **Source**: `kubernetes_logs` filtered to namespaces labeled
  `hypershift.openshift.io/hosted-control-plane=true`.
- **Transforms**: metadata enrichment (`cluster_id`, `namespace`, `application`,
  `pod_name`) and timestamp parsing.
- **Sink**: `aws_s3` with key prefix
  `{{ cluster_id }}/{{ namespace }}/{{ application }}/{{ pod_name }}/`,
  gzip NDJSON, authenticated via IRSA (`auth.assume_role`).

Required environment variables: `CLUSTER_ID`, `S3_BUCKET_NAME`, `AWS_REGION`,
`S3_WRITER_ROLE_ARN`.

The `overlays/localstack` overlay patches the base config to point Vector at a
LocalStack S3 endpoint and is applied by
`.github/workflows/localstack-integration-tests.yaml` (see below). It is not for
production use.

## Heartbeat

`heartbeat/base` deploys a small container that emits a JSON log line every
~2 minutes, providing a synthetic liveness signal through the pipeline. Like the
collector, it is a prod-shaped reference; this repo does not deploy it to prod.

## Testing

The single integration pipeline lives in
`.github/workflows/localstack-integration-tests.yaml`. It stands up minikube +
LocalStack + Terraform, applies `k8s/collector/overlays/localstack`, and
validates the full flow (Vector → central S3 → SNS/SQS → Lambda → customer
buckets), including the multi-tenant `{namespace}/{application}/` S3 key
structure (`make validate-vector-flow`) and the Go end-to-end suite
(`container/integration/`).

There is no longer a minikube/MinIO-based Kubernetes deployment of the API or
processor for testing — those components are validated as real Lambdas through
the LocalStack pipeline, which matches production.

## Verifying Vector (any environment)

```bash
# Pod status and logs
kubectl get pods -n logging -l app=vector-logs
kubectl logs -n logging daemonset/vector-logs --tail=50

# Validate config syntax
kubectl exec -n logging -it daemonset/vector-logs -- vector validate /etc/vector/vector.yaml

# Metrics
kubectl port-forward -n logging daemonset/vector-logs 8686:8686
# then visit http://localhost:8686/metrics
```

## Security Notes

- Vector authenticates via IRSA (`auth.assume_role`) — no long-lived credentials.
- The collector DaemonSet's privileged securityContext and hostPath mounts are
  inherent to node-level log collection; changes to that posture belong in the
  base config here and must be mirrored by osd-fleet-manager, which owns the
  production deployment.
