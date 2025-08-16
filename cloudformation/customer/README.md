# Customer Log Distribution Role

This directory contains the CloudFormation template for customer-deployed IAM roles that enable secure cross-account log delivery in the multi-tenant logging infrastructure.

## Overview

Customer deployments create IAM roles in customer AWS accounts that allow the central logging service to deliver logs to customer-owned CloudWatch Logs. The role provides minimal, regional permissions with strong security controls.

## Template

### `customer-log-distribution-role.yaml`
Creates a customer-side IAM role that trusts the central log distribution role and grants CloudWatch Logs permissions.

**Key Features**:
- **Regional Role Naming**: Role name includes AWS region for regional isolation
- **Minimal Permissions**: Only CloudWatch Logs access required for log delivery
- **Trust Relationship**: Trusts central log distribution role with ExternalId validation
- **Regional Scope**: Permissions limited to specific AWS region where deployed

## Architecture Role

The customer role serves as the final step in the cross-account access chain:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Central       │    │   Customer       │    │   CloudWatch    │
│   Logging       │───▶│   Log            │───▶│   Logs          │
│   Service       │    │   Distribution   │    │   (Customer     │
│   (Provider)    │    │   Role           │    │    Account)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

1. **Central logging service** assumes customer role with ExternalId
2. **Customer role** provides CloudWatch Logs permissions
3. **Logs delivered** to customer's CloudWatch Logs in the specific region

## Prerequisites

Before deploying customer roles:

1. **Central Role ARN**: Obtain from logging service provider
2. **AWS Account Access**: IAM permissions to create roles in customer account
3. **Region Planning**: Deploy role in each region where log delivery is needed

## Deployment

### Basic Deployment

```bash
# Deploy customer role in current region
./deploy.sh -t customer \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

# Stack name: multi-tenant-logging-customer-us-east-2
# Role name: CustomerLogDistribution-us-east-2
```

### Multi-Region Deployment

```bash
# Deploy in multiple regions for multi-region log delivery
# US East 2
./deploy.sh -t customer -r us-east-2 \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

# US West 2  
./deploy.sh -t customer -r us-west-2 \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

# EU West 1
./deploy.sh -t customer -r eu-west-1 \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234
```

### Parameters

| Parameter | Description | Required | Example |
|-----------|-------------|----------|---------|
| `CentralLogDistributionRoleArn` | ARN of central role from logging provider | Yes | `arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234` |

## Role Configuration

### Role Name Pattern
The customer role uses a region-specific naming pattern:
- **Format**: `CustomerLogDistribution-{region}`
- **Examples**: 
  - `CustomerLogDistribution-us-east-2`
  - `CustomerLogDistribution-eu-west-1`
  - `CustomerLogDistribution-ap-southeast-1`

### Trust Policy
The role trusts the central log distribution role with ExternalId validation:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "123456789012"
        }
      }
    }
  ]
}
```

### Permissions Policy
Minimal CloudWatch Logs permissions for log delivery:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DescribeAnyLogGroups",
      "Effect": "Allow", 
      "Action": [
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CreateAndManageLogGroupsAndStreams",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream", 
        "logs:DescribeLogStreams",
        "logs:PutRetentionPolicy"
      ],
      "Resource": [
        "arn:aws:logs:us-east-2:CUSTOMER-ACCOUNT:log-group:/ROSA/cluster-logs/*"
      ]
    },
    {
      "Sid": "PutLogEvents", 
      "Effect": "Allow",
      "Action": [
        "logs:PutLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:us-east-2:CUSTOMER-ACCOUNT:log-group:/ROSA/cluster-logs/*:log-stream:*"
      ]
    }
  ]
}
```

## Stack Outputs

The customer deployment provides outputs for integration and verification:

### `CustomerLogDistributionRoleArn`
**Purpose**: ARN of the created customer role
**Usage**: Provide to logging service provider for configuration
**Example**: `arn:aws:iam::CUSTOMER-ACCOUNT:role/CustomerLogDistribution-us-east-2`

### `HandshakeInformation`
**Purpose**: Formatted information to share with logging service provider
**Content**: 
- Customer Account ID
- Customer Role ARN  
- Target Region
- Setup instructions

## Integration Process

### 1. Customer Deployment
Customer deploys the role in their AWS account:

```bash
# Customer deploys role
./deploy.sh -t customer \
  --central-role-arn arn:aws:iam::PROVIDER-ACCOUNT:role/ROSA-CentralLogDistributionRole-abcd1234
```

### 2. Information Exchange
Customer provides role ARN to logging service provider:

```bash
# Get customer role ARN
aws cloudformation describe-stacks \
  --stack-name multi-tenant-logging-customer-us-east-2 \
  --query 'Stacks[0].Outputs[?OutputKey==`CustomerLogDistributionRoleArn`].OutputValue' \
  --output text

# Output: arn:aws:iam::CUSTOMER-ACCOUNT:role/CustomerLogDistribution-us-east-2
```

### 3. Provider Configuration
Logging service provider configures tenant in their system:

```bash
# Provider adds customer configuration to DynamoDB
aws dynamodb put-item \
  --table-name multi-tenant-logging-development-tenant-configs \
  --item '{
    "tenant_id": {"S": "customer-name"},
    "account_id": {"S": "CUSTOMER-ACCOUNT"},
    "region": {"S": "us-east-2"},
    "role_arn": {"S": "arn:aws:iam::CUSTOMER-ACCOUNT:role/CustomerLogDistribution-us-east-2"},
    "status": {"S": "active"}
  }'
```

### 4. Testing and Validation
Both parties can test the cross-account access:

```bash
# Provider tests role assumption (from central account)
aws sts assume-role \
  --role-arn arn:aws:iam::CUSTOMER-ACCOUNT:role/CustomerLogDistribution-us-east-2 \
  --role-session-name test-log-delivery \
  --external-id PROVIDER-ACCOUNT-ID

# Customer monitors CloudTrail for role assumption events
aws logs filter-log-events \
  --log-group-name CloudTrail/AssumeRole \
  --filter-pattern "CustomerLogDistribution"
```

## Security Considerations

### ExternalId Validation
- **Purpose**: Prevents confused deputy attacks
- **Value**: Always the central logging account ID
- **Validation**: Role cannot be assumed without correct ExternalId

### Minimal Permissions
- **CloudWatch Logs Only**: No other AWS service permissions
- **Regional Scope**: Permissions limited to deployment region
- **Resource Restrictions**: Limited to specific log group patterns

### Regional Isolation
- **Per-Region Roles**: Separate role for each region
- **Regional Permissions**: CloudWatch Logs permissions scoped to specific region
- **Independent Management**: Each region can be managed independently

### Audit Trail
- **CloudTrail Integration**: All role assumptions logged
- **Session Names**: Identifiable session names for tracking
- **Monitoring**: Customer can monitor all access to their role

## Multi-Region Considerations

### Deployment Strategy
```bash
# Deploy roles in all regions where log delivery is needed
for region in us-east-2 us-west-2 eu-west-1; do
  ./deploy.sh -t customer -r $region \
    --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234
done
```

### Regional Independence
- **Separate Stacks**: Each region has independent CloudFormation stack
- **Independent Updates**: Regions can be updated individually
- **Isolated Failures**: Issues in one region don't affect others
- **Regional Policies**: CloudWatch Logs permissions scoped per region

### Cross-Region Considerations
- **Same Central Role**: All regions trust the same central role
- **Consistent ExternalId**: Same ExternalId across all regions
- **Role Naming**: Region included in role name for clarity
- **Provider Coordination**: Provider must configure all regional role ARNs

## Maintenance and Updates

### Role Updates
```bash
# Update existing customer role
./deploy.sh -t customer \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

# Role ARN remains stable during updates
```

### Permission Changes
Customer role permissions are minimal and rarely need updates. If changes are needed:

1. Provider releases updated template
2. Customer applies updated template
3. Provider validates new permissions
4. Testing confirms log delivery continues

### Central Role Changes
If the central role ARN changes:

1. Provider notifies all customers
2. Customers update with new central role ARN
3. Provider coordinates update timing
4. Testing validates continued access

## Troubleshooting

### Common Issues

1. **Role Assumption Fails**
   ```bash
   # Check trust policy includes correct central role ARN
   aws iam get-role --role-name CustomerLogDistribution-us-east-2 \
     --query 'Role.AssumeRolePolicyDocument'
   
   # Verify ExternalId condition is present
   ```

2. **Permission Denied for CloudWatch Logs**
   ```bash
   # Check role policies
   aws iam list-attached-role-policies --role-name CustomerLogDistribution-us-east-2
   aws iam list-role-policies --role-name CustomerLogDistribution-us-east-2
   
   # Verify CloudWatch Logs permissions
   aws iam get-role-policy --role-name CustomerLogDistribution-us-east-2 \
     --policy-name CloudWatchLogsDeliveryPolicy
   ```

3. **Wrong Region Deployment**
   ```bash
   # Check current region
   echo $AWS_REGION
   
   # Verify role name includes correct region
   aws iam get-role --role-name CustomerLogDistribution-us-east-2
   ```

### Debugging Commands

```bash
# Test role assumption from provider account
aws sts assume-role \
  --role-arn arn:aws:iam::CUSTOMER-ACCOUNT:role/CustomerLogDistribution-us-east-2 \
  --role-session-name debug-test \
  --external-id PROVIDER-ACCOUNT-ID

# Check CloudTrail for role assumption events
aws logs filter-log-events \
  --log-group-name cloudtrail-log-group \
  --filter-pattern "{ $.eventName = AssumeRole && $.requestParameters.roleArn = \"*CustomerLogDistribution*\" }"

# Validate CloudWatch Logs access
aws logs describe-log-groups --log-group-name-prefix "/ROSA/cluster-logs"
```

## Cost Considerations

- **No Role Costs**: IAM roles have no charges
- **CloudTrail Events**: Role assumptions generate CloudTrail events (standard rates)
- **CloudWatch Logs**: Standard CloudWatch Logs charges for delivered logs
- **Cross-Account Calls**: STS AssumeRole calls are free

## Best Practices

1. **Regional Deployment**: Deploy role in each region where logs will be delivered
2. **Monitor Access**: Use CloudTrail to monitor role assumption activity
3. **Regular Review**: Periodically review role permissions and usage
4. **Consistent Naming**: Follow role naming convention for clarity
5. **Documentation**: Document role ARNs for provider coordination

## Related Documentation

- **[Global Deployment](../global/)** - Central log distribution role that assumes customer roles
- **[Regional Deployment](../regional/)** - Infrastructure that uses customer roles for delivery
- **[Cluster Deployment](../cluster/)** - Source of logs delivered to customer accounts
- **[Main Documentation](../)** - Complete architecture overview and security model

## Support

For customer role issues:
1. Verify central role ARN accuracy and accessibility
2. Check role trust policy and ExternalId configuration  
3. Validate CloudWatch Logs permissions for target log groups
4. Monitor CloudTrail for role assumption events and errors
5. Coordinate with logging service provider for integration testing