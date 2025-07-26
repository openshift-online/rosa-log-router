# Multi-Tenant Logging Kubernetes Components

This directory contains Kustomize-based deployment configurations for the multi-tenant logging pipeline components in OpenShift/EKS clusters.

## Directory Structure

```
k8s/
├── README.md                  # This file
├── collector/                 # Vector log collection agent
│   ├── base/                  # Base Vector deployment resources
│   │   ├── kustomization.yaml
│   │   ├── service-account.yaml      # Vector service account
│   │   ├── vector-config.yaml        # Vector ConfigMap
│   │   ├── vector-daemonset.yaml     # Vector DaemonSet
│   │   ├── vector-clusterrole.yaml   # RBAC permissions
│   │   └── vector-clusterrolebinding.yaml
│   ├── openshift-base/        # OpenShift-specific resources
│   │   ├── kustomization.yaml
│   │   └── scc.yaml          # SecurityContextConstraints
│   └── overlays/             # Environment-specific configurations
│       ├── development/
│       ├── staging/
│       └── production/
└── processor/                 # Log processing application
    ├── base/                  # Base processor deployment resources
    │   ├── kustomization.yaml
    │   ├── service-account.yaml      # Processor service account
    │   ├── config.yaml              # Processor ConfigMap
    │   ├── deployment.yaml          # Processor Deployment
    │   ├── role.yaml               # RBAC permissions
    │   └── rolebinding.yaml
    ├── openshift-base/        # OpenShift-specific resources
    │   ├── kustomization.yaml
    │   └── scc.yaml          # SecurityContextConstraints
    └── overlays/             # Environment-specific configurations
        └── development/
```

## Overview

The multi-tenant logging pipeline consists of two main components:

1. **Collector (Vector)**: A DaemonSet that runs on every node, collecting logs from pods and writing them directly to S3
2. **Processor**: A Deployment that polls SQS for S3 events and distributes logs to customer CloudWatch Logs

## Prerequisites

1. **Deploy Core Infrastructure**
   ```bash
   cd ../cloudformation
   ./deploy.sh -b your-templates-bucket --include-sqs
   ```
   Note these outputs:
   - `VectorAssumeRolePolicyArn`: Policy for Vector to assume S3 writer role
   - `CentralS3WriterRoleArn`: S3 writer role ARN
   - `LogDeliveryQueueUrl`: SQS queue URL for processor
   - `TenantConfigTableName`: DynamoDB table name
   - `CentralLogDistributionRoleArn`: Central distribution role ARN

2. **Create OIDC Provider in AWS IAM** (if not already exists)
   ```bash
   # Get your cluster's OIDC issuer URL
   OIDC_URL=$(oc get authentication.config.openshift.io cluster -o json | jq -r .spec.serviceAccountIssuer | sed 's|https://||')
   
   # Create OIDC provider in AWS
   aws iam create-open-id-connect-provider \
     --url https://${OIDC_URL} \
     --client-id-list openshift
   ```

3. **Deploy Cluster-Specific IAM Roles**
   
   For the Vector collector:
   ```bash
   aws cloudformation create-stack \
     --stack-name vector-role-CLUSTER_NAME \
     --template-body file://../cloudformation/cluster-vector-role.yaml \
     --parameters \
       ParameterKey=ClusterName,ParameterValue=CLUSTER_NAME \
       ParameterKey=OIDCProviderURL,ParameterValue=${OIDC_URL} \
       ParameterKey=OIDCAudience,ParameterValue=openshift \
       ParameterKey=ServiceAccountNamespace,ParameterValue=logging \
       ParameterKey=ServiceAccountName,ParameterValue=vector-logs \
       ParameterKey=VectorAssumeRolePolicyArn,ParameterValue=VECTOR_ASSUME_ROLE_POLICY_ARN \
     --capabilities CAPABILITY_NAMED_IAM
   ```
   
   For the log processor:
   ```bash
   aws cloudformation create-stack \
     --stack-name processor-role-CLUSTER_NAME \
     --template-body file://../cloudformation/cluster-processor-role.yaml \
     --parameters \
       ParameterKey=ClusterName,ParameterValue=CLUSTER_NAME \
       ParameterKey=OIDCProviderURL,ParameterValue=${OIDC_URL} \
       ParameterKey=OIDCAudience,ParameterValue=openshift \
       ParameterKey=ServiceAccountNamespace,ParameterValue=logging \
       ParameterKey=ServiceAccountName,ParameterValue=log-processor \
       ParameterKey=TenantConfigTableArn,ParameterValue=TENANT_CONFIG_TABLE_ARN \
       ParameterKey=CentralLoggingBucketArn,ParameterValue=CENTRAL_LOGGING_BUCKET_ARN \
       ParameterKey=CentralLogDistributionRoleArn,ParameterValue=CENTRAL_LOG_DISTRIBUTION_ROLE_ARN \
     --capabilities CAPABILITY_NAMED_IAM
   ```
   
   Note the role ARNs from both stack outputs.

## Deployment

### Deploy the Collector (Vector)

1. **Update the service account annotation** with your Vector role ARN:
   ```bash
   # Edit k8s/collector/overlays/development/service-account-patch.yaml
   # Replace REPLACE_WITH_VECTOR_ROLE_ARN with your actual role ARN
   ```

2. **Deploy Vector to OpenShift**:
   ```bash
   kubectl apply -k k8s/collector/overlays/development/
   ```

3. **Verify Vector deployment**:
   ```bash
   kubectl get pods -n logging -l app=vector-logs
   kubectl logs -n logging daemonset/vector-logs
   ```

### Deploy the Processor

1. **Update the service account annotation** with your processor role ARN:
   ```bash
   # Edit k8s/processor/overlays/development/service-account-patch.yaml
   # Replace REPLACE_WITH_PROCESSOR_ROLE_ARN with your actual role ARN
   ```

2. **Deploy the processor to OpenShift**:
   ```bash
   kubectl apply -k k8s/processor/overlays/development/
   ```

3. **Verify processor deployment**:
   ```bash
   kubectl get pods -n logging -l app=log-processor
   kubectl logs -n logging deployment/log-processor
   ```

## Component Configuration

### Vector Collector Configuration

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

### Log Processor Configuration

#### Execution Modes
The processor supports three execution modes:
- `sqs`: Polls SQS queue for S3 events (used in Kubernetes)
- `lambda`: AWS Lambda runtime mode
- `manual`: Manual input for testing

#### Environment Variables
- `EXECUTION_MODE`: Set to "sqs" for Kubernetes deployment
- `SQS_QUEUE_URL`: URL of the SQS queue from infrastructure
- `TENANT_CONFIG_TABLE`: DynamoDB table for tenant configurations
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: Role for cross-account access
- `MAX_BATCH_SIZE`: Maximum events per CloudWatch batch (default: 1000)
- `RETRY_ATTEMPTS`: Number of retry attempts (default: 3)

### Environment Variables

#### Vector Collector Environment Variables
- `AWS_REGION`: AWS region where S3 bucket exists
- `S3_BUCKET_NAME`: Central S3 bucket name from core infrastructure
- `S3_WRITER_ROLE_ARN`: S3 writer role ARN from core infrastructure
- `CLUSTER_ID`: Unique identifier for this cluster

#### Processor Environment Variables
- `AWS_REGION`: AWS region for services
- `EXECUTION_MODE`: "sqs" for Kubernetes deployment
- `SQS_QUEUE_URL`: SQS queue URL from infrastructure
- `TENANT_CONFIG_TABLE`: DynamoDB table name
- `CENTRAL_LOG_DISTRIBUTION_ROLE_ARN`: Central distribution role ARN

### Service Account Annotations

Both service accounts must be annotated with their respective IAM role ARNs:
```yaml
annotations:
  eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/ROLE_NAME
```

## Verification

### Verify Vector Collector

1. **Check Vector pods are running**:
   ```bash
   kubectl get pods -n logging -l app=vector-logs
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

### Verify Log Processor

1. **Check processor pod is running**:
   ```bash
   kubectl get pods -n logging -l app=log-processor
   ```

2. **Check processor logs**:
   ```bash
   kubectl logs -n logging deployment/log-processor
   ```

3. **Monitor SQS queue depth**:
   ```bash
   aws sqs get-queue-attributes \
     --queue-url YOUR_QUEUE_URL \
     --attribute-names ApproximateNumberOfMessages
   ```

4. **Check CloudWatch Logs delivery**:
   ```bash
   aws logs describe-log-groups --log-group-name-prefix /aws/logs/
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

## Creating New Environment Overlays

### For Vector Collector

1. **Create overlay directory**:
   ```bash
   mkdir -p k8s/collector/overlays/new-environment
   ```

2. **Create kustomization.yaml**:
   ```yaml
   apiVersion: kustomize.config.k8s.io/v1beta1
   kind: Kustomization
   
   namespace: logging
   
   resources:
     - ../../openshift-base
   
   patches:
     - path: service-account-patch.yaml
       target:
         kind: ServiceAccount
         name: vector-logs
   ```

3. **Create service-account-patch.yaml** with your IAM role:
   ```yaml
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: vector-logs
     annotations:
       eks.amazonaws.com/role-arn: YOUR_VECTOR_ROLE_ARN
   ```

### For Log Processor

1. **Create overlay directory**:
   ```bash
   mkdir -p k8s/processor/overlays/new-environment
   ```

2. **Create kustomization.yaml**:
   ```yaml
   apiVersion: kustomize.config.k8s.io/v1beta1
   kind: Kustomization
   
   namespace: logging
   
   resources:
     - ../../openshift-base
   
   patches:
     - path: service-account-patch.yaml
       target:
         kind: ServiceAccount
         name: log-processor
     - path: deployment-patch.yaml
       target:
         kind: Deployment
         name: log-processor
   ```

3. **Create patches for environment-specific configuration**

## Security Considerations

- Both service accounts use IRSA (IAM Roles for Service Accounts) - no long-lived credentials
- Vector service account only has permission to assume the S3 writer role
- S3 writer role only has permission to write to the central logging bucket
- Processor service account has permissions for:
  - Reading from S3 bucket
  - Accessing DynamoDB tenant configuration table
  - Assuming the central log distribution role for cross-account access
- Each cluster has its own IAM roles with OIDC trust
- S3 encryption is enforced with KMS
- Both components use role assumption for enhanced security boundaries

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