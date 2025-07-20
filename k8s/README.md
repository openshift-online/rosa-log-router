# Vector Deployment with Kustomize

This directory contains Kustomize-based deployment configurations for Vector log collection agents in OpenShift/EKS clusters.

## Directory Structure

```
k8s/
├── base/                      # Base Vector deployment resources
│   ├── kustomization.yaml
│   ├── service-account.yaml   # Vector service account
│   ├── vector-config.yaml     # Vector ConfigMap
│   └── vector-daemonset.yaml  # Vector DaemonSet
└── overlays/                  # Environment-specific configurations
    ├── development/
    │   ├── kustomization.yaml
    │   └── service-account-patch.yaml
    ├── staging/
    └── production/
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

1. **Update the overlay configuration** for your environment:
   ```bash
   cd overlays/development
   
   # Edit service-account-patch.yaml with your IAM role ARN
   vim service-account-patch.yaml
   
   # Edit kustomization.yaml with your AWS resources
   vim kustomization.yaml
   ```

2. **Create the logging namespace**:
   ```bash
   kubectl create namespace logging
   ```

3. **Deploy Vector**:
   ```bash
   # From the k8s directory
   kubectl apply -k overlays/development
   ```

### Manual Deployment (without Kustomize)

If you prefer not to use Kustomize:

1. **Create namespace**:
   ```bash
   kubectl create namespace logging
   ```

2. **Create service account with IAM annotation**:
   ```bash
   kubectl create serviceaccount vector-logs -n logging
   kubectl annotate serviceaccount vector-logs -n logging \
     eks.amazonaws.com/role-arn=arn:aws:iam::ACCOUNT:role/ROLE_NAME
   ```

3. **Update and apply base resources**:
   ```bash
   # Update vector-config.yaml with your values
   kubectl apply -f base/vector-config.yaml
   kubectl apply -f base/vector-daemonset.yaml
   ```

## Configuration

### Environment Variables in ConfigMap

Update these values in your overlay's `kustomization.yaml`:

- `aws_region`: AWS region where S3 bucket exists
- `s3_bucket_name`: Central S3 bucket name from core infrastructure
- `s3_writer_role_arn`: S3 writer role ARN from core infrastructure
- `cluster_id`: Unique identifier for this cluster

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
   
   namespace: logging
   
   bases:
     - ../../base
   
   patches:
     - path: service-account-patch.yaml
       target:
         kind: ServiceAccount
         name: vector-logs
   
   configMapGenerator:
     - name: vector-config
       behavior: merge
       literals:
         - aws_region=YOUR_REGION
         - s3_bucket_name=YOUR_BUCKET
         - s3_writer_role_arn=YOUR_S3_WRITER_ROLE
         - cluster_id=YOUR_CLUSTER_ID
   ```

3. **Create service-account-patch.yaml**:
   ```yaml
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: vector-logs
     annotations:
       eks.amazonaws.com/role-arn: YOUR_VECTOR_ROLE_ARN
   ```

## Security Considerations

- Vector service account only has permission to assume the S3 writer role
- S3 writer role only has permission to write to the central logging bucket
- Each cluster has its own Vector IAM role with OIDC trust
- No long-lived credentials are used