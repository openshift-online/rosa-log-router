# Cluster IAM Roles for Multi-Tenant Logging

This directory contains CloudFormation templates for creating cluster-specific IAM roles that enable secure authentication between Kubernetes/OpenShift clusters and AWS services using IRSA (IAM Roles for Service Accounts).

## Overview

The cluster deployment creates IAM roles that allow:
- **Vector agents** to securely write logs to S3 via role assumption
- **Log processors** to read from S3, DynamoDB, and perform cross-account log delivery

## Templates

### `cluster-vector-role.yaml`
Creates an IAM role for Vector log collection agents running in Kubernetes/OpenShift clusters.

**Purpose**: Enables Vector to assume the S3 writer role for secure log ingestion
**Integration**: Connects with [regional infrastructure](../regional/) S3 writer role

### `cluster-processor-role.yaml` 
Creates an IAM role for log processor pods running in Kubernetes/OpenShift clusters.

**Purpose**: Enables processors to read logs, access tenant configs, and perform cross-account delivery
**Integration**: Connects with [regional infrastructure](../regional/) and [global role](../global/)

## Prerequisites

Before deploying cluster roles, ensure:

1. **Regional Infrastructure Deployed**: The [regional stack](../regional/) must be deployed first
2. **OIDC Provider Registered**: Your cluster's OIDC provider must be registered in AWS IAM
3. **Service Accounts Created**: Kubernetes service accounts must exist in the target namespace

## Template Generation

This directory uses **Jinja2 template generation** to solve CloudFormation YAML limitations with dynamic OIDC provider substitution. Templates are generated before deployment using the `generate_templates.py` script.

### Prerequisites

```bash
# Install Python dependencies (handled automatically by deploy.sh)
cd cluster/
pip3 install -r requirements.txt
```

### Manual Template Generation

```bash
# Generate processor role template
python3 generate_templates.py processor \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123

# Generate vector role template  
python3 generate_templates.py vector \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123

# Generate both templates
python3 generate_templates.py both \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123

# Validate generated templates
python3 generate_templates.py processor \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123 \
  --validate
```

**Generated templates are saved to:** `rendered/cluster-{type}-role.yaml`

## Deployment

**Note:** Template generation is automatically handled by `deploy.sh` - you don't need to run `generate_templates.py` manually.

### Deploy Vector Role

```bash
# Deploy Vector role for log collection
./deploy.sh -t cluster --cluster-template vector \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123 \
  --oidc-audience openshift

# Stack name will be: multi-tenant-logging-cluster-my-cluster
```

### Deploy Processor Role

```bash
# Deploy processor role for log processing  
./deploy.sh -t cluster --cluster-template processor \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123 \
  --oidc-audience openshift \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

# You'll provide additional parameters during deployment for:
# - TenantConfigTableArn (from regional stack outputs)
# - CentralLoggingBucketArn (from regional stack outputs)
```

### Deploy Both Roles

```bash
# Deploy both Vector and processor roles (creates separate stacks)
./deploy.sh -t cluster --cluster-template both \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123 \
  --oidc-audience openshift
```

### Parameters

| Parameter            | Description                                | Required                | Example                             |
|----------------------|--------------------------------------------|-------------------------|-------------------------------------|
| `--cluster-template` | Template type: vector, processor, or both  | Yes                     | `processor`                         |
| `--cluster-name`     | Unique cluster identifier                  | Yes                     | `my-cluster`                        |
| `--oidc-provider`    | OIDC provider URL (without https://)       | Yes                     | `oidc.op1.openshiftapps.com/abc123` |
| `--oidc-audience`    | OIDC audience                              | No (default: openshift) | `openshift` or `sts.amazonaws.com`  |
| `--central-role-arn` | Central log distribution role ARN          | For processor only      | See [global docs](../global/)       |

**Runtime Parameters** (provided during CloudFormation deployment):
- `TenantConfigTableArn`: From regional stack outputs
- `CentralLoggingBucketArn`: From regional stack outputs  
- `VectorAssumeRolePolicyArn`: From regional stack outputs (vector only)

## Integration Steps

### 1. Register OIDC Provider (One-time per cluster)

```bash
# For OpenShift clusters
aws iam create-open-id-connect-provider \
  --url https://oidc.op1.openshiftapps.com/abc123 \
  --client-id-list openshift

# For EKS clusters  
aws iam create-open-id-connect-provider \
  --url https://oidc.eks.us-east-2.amazonaws.com/id/ABC123 \
  --client-id-list sts.amazonaws.com
```

### 2. Deploy Cluster Roles

Deploy the appropriate cluster role templates using the commands above.

### 3. Configure Service Accounts

Annotate your Kubernetes service accounts with the IAM role ARNs:

```bash
# Vector service account
kubectl annotate serviceaccount -n logging vector \
  eks.amazonaws.com/role-arn=arn:aws:iam::123456789012:role/multi-tenant-logging-my-cluster-vector-role

# Processor service account  
kubectl annotate serviceaccount -n logging log-processor \
  eks.amazonaws.com/role-arn=arn:aws:iam::123456789012:role/multi-tenant-logging-my-cluster-processor-role
```

### 4. Deploy Workloads

Use the provided [Kubernetes manifests](../../k8s/) to deploy Vector and processor workloads.

## OIDC Configuration

### OpenShift Clusters
- **OIDC Provider**: Extract from cluster: `oc get authentication cluster -o jsonpath='{.spec.serviceAccountIssuer}'`
- **Audience**: `openshift`
- **Service Account Format**: `system:serviceaccount:namespace:service-account-name`

### EKS Clusters  
- **OIDC Provider**: Extract from cluster: `aws eks describe-cluster --name cluster-name --query 'cluster.identity.oidc.issuer'`
- **Audience**: `sts.amazonaws.com`
- **Service Account Format**: `system:serviceaccount:namespace:service-account-name`

## Role Permissions

### Vector Role Permissions
- **S3 Writer Role Assumption**: Can assume the regional S3 writer role
- **No Direct Permissions**: All S3 access is through role assumption

### Processor Role Permissions
- **DynamoDB**: Read access to tenant configuration table
- **S3**: Read access to central logging bucket  
- **Central Role Assumption**: Can assume the global central log distribution role
- **KMS**: Decrypt operations for encrypted resources
- **CloudWatch Logs**: Create log groups/streams for processor logging

## Stack Outputs

Both templates provide useful outputs for integration:

### Vector Role Outputs
- **ClusterVectorRoleArn**: IAM role ARN for the Vector service account
- **ServiceAccountAnnotation**: Ready-to-use annotation for kubectl
- **KustomizationExample**: Example patch for kustomize deployments

### Processor Role Outputs  
- **ClusterProcessorRoleArn**: IAM role ARN for the processor service account
- **ServiceAccountAnnotation**: Ready-to-use annotation for kubectl
- **DeploymentInstructions**: Step-by-step integration guide

## Example Kustomization

Use kustomize to apply service account annotations:

```yaml
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- ../../base

patchesStrategicMerge:
- service-account-annotations.yaml
```

```yaml
# service-account-annotations.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vector
  namespace: logging
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/multi-tenant-logging-my-cluster-vector-role
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: log-processor
  namespace: logging
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/multi-tenant-logging-my-cluster-processor-role
```

## Troubleshooting

### Common Issues

1. **OIDC Provider Not Found**
   ```bash
   # Verify OIDC provider is registered
   aws iam list-open-id-connect-providers
   ```

2. **Role Assumption Failures**
   ```bash
   # Check service account annotation
   kubectl get serviceaccount vector -n logging -o yaml
   
   # Verify OIDC conditions match
   aws iam get-role --role-name multi-tenant-logging-my-cluster-vector-role
   ```

3. **Permission Denied Errors**
   ```bash
   # Check role trust policy
   aws iam get-role --role-name multi-tenant-logging-my-cluster-vector-role \
     --query 'Role.AssumeRolePolicyDocument'
   ```

### Debugging Commands

```bash
# Test role assumption from pod
kubectl run -it --rm debug --image=amazon/aws-cli --restart=Never -- \
  aws sts get-caller-identity

# Check Vector logs
kubectl logs -n logging daemonset/vector-logs

# Check processor logs  
kubectl logs -n logging deployment/log-processor
```

## Security Considerations

- **Least Privilege**: Roles have minimal permissions for their specific functions
- **Namespace Isolation**: Service account conditions restrict access to specific namespaces
- **OIDC Validation**: Strong identity verification through OIDC provider integration
- **No Long-term Credentials**: Uses temporary credentials via IRSA

## Related Documentation

- **[Global Deployment](../global/)** - Central log distribution role
- **[Regional Deployment](../regional/)** - Core infrastructure and S3 writer role  
- **[Customer Deployment](../customer/)** - Customer-side roles and permissions
- **[Main Documentation](../)** - Architecture overview and deployment workflows
- **[Kubernetes Manifests](../../k8s/)** - Vector and processor deployment configurations

## Support

For cluster-specific issues:
1. Verify OIDC provider registration and configuration
2. Check service account annotations and role trust policies
3. Review cluster-specific logs and AWS CloudTrail for role assumption events
4. Consult the main [troubleshooting guide](../#troubleshooting)