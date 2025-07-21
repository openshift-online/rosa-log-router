# Vector Deployment with Kustomize

This directory contains Kustomize-based deployment configurations for Vector log collection agents in OpenShift/EKS clusters.

## Directory Structure

```
k8s/
├── base/                      # Base Vector deployment resources
│   ├── kustomization.yaml
│   ├── vector-namespace.yaml  # Logging namespace
│   ├── vector-serviceaccount.yaml   # Vector service account
│   ├── vector-config.yaml     # Vector ConfigMap
│   └── vector-daemonset.yaml  # Vector DaemonSet
└── overlays/                  # Environment-specific configurations
    └── production/
        ├── kustomization.yaml
        └── vector-config-patch.yaml  # Production config overrides
```

## Prerequisites

1. **Deploy Core Infrastructure**
   ```bash
   cd ../cloudformation
   ./deploy.sh -b your-templates-bucket
   ```
   Note the `VectorAssumeRolePolicyArn` and `CentralS3WriterRoleArn` from the stack outputs.

2. **Create OIDC Provider in AWS IAM** (if not already exists)
   ```bash
   # Get your cluster's OIDC issuer URL
   OIDC_URL=$(oc get authentication.config.openshift.io cluster -o json | jq -r .spec.serviceAccountIssuer | sed 's|https://||')
   
   # Create OIDC provider in AWS
   aws iam create-open-id-connect-provider \
     --url https://${OIDC_URL} \
     --client-id-list openshift
   ```

3. **Deploy Cluster-Specific IAM Role**
   ```bash
   aws cloudformation create-stack \
     --stack-name vector-role-dev-cluster-1 \
     --template-body file://../cloudformation/cluster-vector-role.yaml \
     --parameters \
       ParameterKey=ClusterName,ParameterValue=dev-cluster-1 \
       ParameterKey=OIDCProviderURL,ParameterValue=${OIDC_URL} \
       ParameterKey=OIDCAudience,ParameterValue=openshift \
       ParameterKey=ServiceAccountNamespace,ParameterValue=logging \
       ParameterKey=ServiceAccountName,ParameterValue=vector-logs \
       ParameterKey=VectorAssumeRolePolicyArn,ParameterValue=arn:aws:iam::ACCOUNT:policy/POLICY_NAME \
     --capabilities CAPABILITY_NAMED_IAM
   ```
   Note the `ClusterVectorRoleArn` from the stack outputs.

## Deployment

### Using Kustomize

1. **Deploy Vector to development/testing** (uses base configuration):
   ```bash
   kubectl apply -k k8s/base/
   ```

2. **Deploy Vector to production** (applies production overlays):
   ```bash
   kubectl apply -k k8s/overlays/production/
   ```

3. **Preview changes before applying**:
   ```bash
   kubectl kustomize k8s/base/
   ```

The base configuration creates the logging namespace automatically.

### Key Configuration Updates

#### Namespace Label Filtering
Vector is configured to collect logs only from namespaces with specific labels:
```yaml
extra_namespace_label_selector: "hypershift.openshift.io/hosted-control-plane=true"
```

#### Vector Output Format
Vector outputs logs as NDJSON (newline-delimited JSON) with a JSON array format:
- Each file contains a single JSON array on one line
- Files are compressed with gzip
- S3 object keys follow the pattern: `customer_id/cluster_id/application/pod_name/timestamp-uuid.json.gz`

#### Pod Annotations for Metadata
Vector extracts metadata from pod annotations:
- `customer_id`: Customer identifier
- `cluster_id`: Cluster identifier
- `application`: Application name
- `environment`: Environment (production, staging, etc.)

## Configuration

### Environment Variables in ConfigMap

The base configuration uses environment variable substitution:

- `AWS_REGION`: AWS region where S3 bucket exists
- `S3_BUCKET_NAME`: Central S3 bucket name from core infrastructure
- `S3_WRITER_ROLE_ARN`: S3 writer role ARN from core infrastructure
- `CLUSTER_ID`: Unique identifier for this cluster

These can be set as ConfigMap literals in overlays or provided at deployment time.

### Service Account Annotation

The service account must be annotated with the IAM role ARN:
```yaml
annotations:
  eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/ROLE_NAME
```

## Verification

1. **Check Vector pods are running**:
   ```bash
   kubectl get pods -n logging
   ```

2. **Check Vector logs**:
   ```bash
   kubectl logs -n logging daemonset/vector-logs
   ```

3. **Verify IAM role assumption**:
   ```bash
   kubectl exec -n logging -it daemonset/vector-logs -- vector top
   ```

4. **Check S3 for logs**:
   ```bash
   aws s3 ls s3://YOUR_BUCKET_NAME/ --recursive
   ```

## Troubleshooting

### Namespace Filtering Issues

1. **Check if namespaces have required labels**:
   ```bash
   kubectl get namespaces -l hypershift.openshift.io/hosted-control-plane=true
   ```

2. **Verify Vector is seeing the namespaces**:
   ```bash
   kubectl logs -n logging daemonset/vector-logs | grep "Discovered namespace"
   ```

### OIDC Authentication Issues

1. **Verify OIDC provider exists in AWS**:
   ```bash
   aws iam list-open-id-connect-providers
   ```

2. **Check service account token**:
   ```bash
   kubectl exec -n logging -it daemonset/vector-logs -- cat /var/run/secrets/eks.amazonaws.com/serviceaccount/token
   ```

3. **Test role assumption manually**:
   ```bash
   # Get the token
   TOKEN=$(kubectl exec -n logging daemonset/vector-logs -- cat /var/run/secrets/eks.amazonaws.com/serviceaccount/token)
   
   # Try to assume role
   aws sts assume-role-with-web-identity \
     --role-arn arn:aws:iam::ACCOUNT:role/ROLE_NAME \
     --role-session-name test-session \
     --web-identity-token "$TOKEN"
   ```

### Vector Configuration Issues

1. **Check Vector configuration syntax**:
   ```bash
   kubectl exec -n logging -it daemonset/vector-logs -- vector validate /etc/vector/vector.yaml
   ```

2. **View Vector metrics**:
   ```bash
   kubectl port-forward -n logging daemonset/vector-logs 8686:8686
   # Then visit http://localhost:8686/metrics
   ```

## Creating New Overlays

To create a new environment overlay:

1. **Create overlay directory**:
   ```bash
   mkdir -p overlays/new-environment
   ```

2. **Create kustomization.yaml**:
   ```yaml
   apiVersion: kustomize.config.k8s.io/v1beta1
   kind: Kustomization
   
   resources:
     - ../../base
   
   patchesStrategicMerge:
     - vector-config-patch.yaml
   
   configMapGenerator:
     - name: vector-config
       behavior: merge
       literals:
         - AWS_REGION=YOUR_REGION
         - S3_BUCKET_NAME=YOUR_BUCKET
         - S3_WRITER_ROLE_ARN=YOUR_S3_WRITER_ROLE
         - CLUSTER_ID=YOUR_CLUSTER_ID
   ```

3. **Create vector-config-patch.yaml** for environment-specific Vector configuration:
   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: vector-config
     namespace: logging
   data:
     vector.yaml: |
       # Environment-specific Vector configuration overrides
       # For example, different batching settings or additional transforms
   ```

## Security Considerations

- Vector service account only has permission to assume the S3 writer role
- S3 writer role only has permission to write to the central logging bucket with appropriate prefix restrictions
- Each cluster has its own Vector IAM role with OIDC trust
- No long-lived credentials are used
- S3 encryption is enforced with KMS
- Vector uses double-hop role assumption for enhanced security

## Performance Tuning

### Batching Configuration
Vector is configured with optimal batching for cost efficiency:
- `batch.timeout_secs: 300` (5 minutes)
- `batch.max_bytes: 10485760` (10MB)

These settings reduce S3 PUT requests and improve throughput.

### Buffer Configuration
Vector uses disk buffers for reliability:
- Type: `disk`
- Maximum size: 268435488 bytes (256MB)
- When full: `block_new_events`

This ensures no log loss during S3 connectivity issues.