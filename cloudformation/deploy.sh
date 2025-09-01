#!/bin/bash

# CloudFormation Deployment Script for Multi-Tenant Logging Infrastructure
# This script deploys the nested stack architecture for the logging pipeline

set -e  # Exit on any error

# Default values
DEPLOYMENT_TYPE=""
ENVIRONMENT="development"
PROJECT_NAME="multi-tenant-logging"
REGION="${AWS_REGION:-}"
STACK_NAME=""
TEMPLATE_BUCKET=""
PROFILE="${AWS_PROFILE:-}"
DRY_RUN=false
VALIDATE_ONLY=false
INCLUDE_SQS=false
INCLUDE_LAMBDA=false
ECR_IMAGE_URI=""
CENTRAL_ROLE_ARN=""
INCLUDE_API=false
API_AUTH_SSM_PARAMETER=""
AUTHORIZER_IMAGE_URI=""
API_IMAGE_URI=""
CLUSTER_NAME=""
OIDC_PROVIDER=""
OIDC_AUDIENCE="openshift"
CLUSTER_TEMPLATE=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy the multi-tenant logging infrastructure using CloudFormation.

REQUIRED:
    -t, --deployment-type TYPE  Deployment type: global, regional, customer, or cluster

OPTIONS:
    -e, --environment ENV       Environment name (production, staging, development). Default: development
    -p, --project-name NAME     Project name. Default: multi-tenant-logging
    -r, --region REGION         AWS region. Default: us-east-1
    -s, --stack-name NAME       CloudFormation stack name (auto-generated if not specified)
    -b, --template-bucket NAME  S3 bucket for storing nested templates (required for regional deployments)
    --profile PROFILE           AWS CLI profile to use
    --central-role-arn ARN      ARN of central log distribution role (required for regional/customer deployments)
    --cluster-name NAME         Cluster name (required for cluster deployments)
    --oidc-provider URL         OIDC provider URL without https:// (required for cluster deployments)
    --oidc-audience AUD         OIDC audience (default: openshift for cluster deployments)
    --cluster-template TYPE     Cluster template type: vector, processor, or both (required for cluster deployments)
    --include-sqs               Include SQS stack for log processing (regional only)
    --include-lambda            Include Lambda stack for container-based processing (regional only)
    --ecr-image-uri URI         ECR container image URI (required if --include-lambda)
    --include-api               Include API stack for tenant management (regional only)
    --api-auth-ssm-parameter    SSM parameter name for API PSK (required if --include-api)
    --authorizer-image-uri URI  ECR URI for API authorizer container (required if --include-api)
    --api-image-uri URI         ECR URI for API service container (required if --include-api)
    --dry-run                   Show what would be deployed without actually deploying
    --validate-only             Only validate templates without deploying
    -h, --help                  Display this help message

EXAMPLES:
    # Deploy global central role
    $0 -t global

    # Deploy regional infrastructure with central role ARN
    $0 -t regional -b my-templates-bucket --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

    # Deploy regional with SQS and Lambda
    $0 -t regional -b my-templates-bucket --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 --include-sqs --include-lambda --ecr-image-uri 123456789012.dkr.ecr.us-east-2.amazonaws.com/log-processor:latest

    # Deploy regional with API management
    $0 -t regional -b my-templates-bucket --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 --include-api --api-auth-ssm-parameter /logging/api/psk --authorizer-image-uri 123456789012.dkr.ecr.us-east-2.amazonaws.com/logging-authorizer:latest --api-image-uri 123456789012.dkr.ecr.us-east-2.amazonaws.com/logging-api:latest

    # Deploy customer role
    $0 -t customer --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

    # Deploy cluster Vector role
    $0 -t cluster --cluster-template vector --cluster-name my-cluster --oidc-provider oidc.op1.openshiftapps.com/abc123

    # Deploy cluster processor role
    $0 -t cluster --cluster-template processor --cluster-name my-cluster --oidc-provider oidc.op1.openshiftapps.com/abc123 --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

    # Deploy both cluster roles
    $0 -t cluster --cluster-template both --cluster-name my-cluster --oidc-provider oidc.op1.openshiftapps.com/abc123

    # Validate templates only
    $0 -t regional --validate-only -b my-templates-bucket --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--deployment-type)
            DEPLOYMENT_TYPE="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -p|--project-name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -s|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        -b|--template-bucket)
            TEMPLATE_BUCKET="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --central-role-arn)
            CENTRAL_ROLE_ARN="$2"
            shift 2
            ;;
        --cluster-name)
            CLUSTER_NAME="$2"
            shift 2
            ;;
        --oidc-provider)
            OIDC_PROVIDER="$2"
            shift 2
            ;;
        --oidc-audience)
            OIDC_AUDIENCE="$2"
            shift 2
            ;;
        --cluster-template)
            CLUSTER_TEMPLATE="$2"
            shift 2
            ;;
        --include-sqs)
            INCLUDE_SQS=true
            shift
            ;;
        --include-lambda)
            INCLUDE_LAMBDA=true
            shift
            ;;
        --ecr-image-uri)
            ECR_IMAGE_URI="$2"
            shift 2
            ;;
        --include-api)
            INCLUDE_API=true
            shift
            ;;
        --api-auth-ssm-parameter)
            API_AUTH_SSM_PARAMETER="$2"
            shift 2
            ;;
        --authorizer-image-uri)
            AUTHORIZER_IMAGE_URI="$2"
            shift 2
            ;;
        --api-image-uri)
            API_IMAGE_URI="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --validate-only)
            VALIDATE_ONLY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate deployment type
if [[ -z "$DEPLOYMENT_TYPE" ]]; then
    print_error "Deployment type is required. Use -t or --deployment-type option."
    usage
    exit 1
fi

if [[ ! "$DEPLOYMENT_TYPE" =~ ^(global|regional|customer|cluster)$ ]]; then
    print_error "Deployment type must be one of: global, regional, customer, cluster"
    exit 1
fi

# Set stack name based on deployment type if not explicitly provided
if [[ -z "$STACK_NAME" ]]; then
    case "$DEPLOYMENT_TYPE" in
        global)
            STACK_NAME="${PROJECT_NAME}-global"
            ;;
        regional)
            STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
            ;;
        customer)
            STACK_NAME="${PROJECT_NAME}-customer-${REGION}"
            ;;
        cluster)
            if [[ -n "$CLUSTER_NAME" ]]; then
                STACK_NAME="${PROJECT_NAME}-cluster-${CLUSTER_NAME}"
            else
                STACK_NAME="${PROJECT_NAME}-cluster-${REGION}"
            fi
            ;;
    esac
fi

# Validate deployment type specific requirements
case "$DEPLOYMENT_TYPE" in
    global)
        # Global deployment doesn't need template bucket or central role ARN
        # Environment is not used for global deployment
        ;;
    regional)
        # Regional deployment requires template bucket and central role ARN
        if [[ -z "$TEMPLATE_BUCKET" ]]; then
            # Check if stack exists and try to get template bucket
            if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
                TEMPLATE_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].Parameters[?ParameterKey==`TemplateBucket`].ParameterValue' --output text 2>/dev/null || echo "")
                if [[ -n "$TEMPLATE_BUCKET" ]]; then
                    print_status "Using existing template bucket from stack: $TEMPLATE_BUCKET"
                else
                    print_error "Template bucket is required for regional deployment. Use -b or --template-bucket option."
                    exit 1
                fi
            else
                print_error "Template bucket is required for new regional deployment. Use -b or --template-bucket option."
                exit 1
            fi
        fi
        
        if [[ -z "$CENTRAL_ROLE_ARN" ]]; then
            print_error "Central role ARN is required for regional deployment. Use --central-role-arn option."
            exit 1
        fi
        
        # Validate Lambda requirements
        if [[ "$INCLUDE_LAMBDA" == true && -z "$ECR_IMAGE_URI" ]]; then
            print_error "ECR image URI is required when --include-lambda is specified. Use --ecr-image-uri option."
            exit 1
        fi
        
        # Auto-enable SQS if Lambda is enabled
        if [[ "$INCLUDE_LAMBDA" == true ]]; then
            INCLUDE_SQS=true
            print_status "Auto-enabling SQS stack since Lambda stack requires it."
        fi
        
        # Validate API requirements
        if [[ "$INCLUDE_API" == true ]]; then
            if [[ -z "$API_AUTH_SSM_PARAMETER" ]]; then
                print_error "API auth SSM parameter is required when --include-api is specified. Use --api-auth-ssm-parameter option."
                exit 1
            fi
            if [[ -z "$AUTHORIZER_IMAGE_URI" ]]; then
                print_error "Authorizer image URI is required when --include-api is specified. Use --authorizer-image-uri option."
                exit 1
            fi
            if [[ -z "$API_IMAGE_URI" ]]; then
                print_error "API image URI is required when --include-api is specified. Use --api-image-uri option."
                exit 1
            fi
        fi
        ;;
    customer)
        # Customer deployment requires central role ARN
        if [[ -z "$CENTRAL_ROLE_ARN" ]]; then
            print_error "Central role ARN is required for customer deployment. Use --central-role-arn option."
            exit 1
        fi
        ;;
    cluster)
        # Cluster deployment requires cluster name and OIDC provider
        if [[ -z "$CLUSTER_NAME" ]]; then
            print_error "Cluster name is required for cluster deployment. Use --cluster-name option."
            exit 1
        fi
        
        if [[ -z "$OIDC_PROVIDER" ]]; then
            print_error "OIDC provider URL is required for cluster deployment. Use --oidc-provider option."
            exit 1
        fi
        
        if [[ -z "$CLUSTER_TEMPLATE" ]]; then
            print_error "Cluster template type is required for cluster deployment. Use --cluster-template option."
            exit 1
        fi
        
        if [[ ! "$CLUSTER_TEMPLATE" =~ ^(vector|processor|both)$ ]]; then
            print_error "Cluster template type must be one of: vector, processor, both"
            exit 1
        fi
        ;;
esac

# Validate environment for regional deployments
if [[ "$DEPLOYMENT_TYPE" == "regional" && ! "$ENVIRONMENT" =~ ^(production|staging|development)$ ]]; then
    print_error "Environment must be one of: production, staging, development for regional deployments"
    exit 1
fi

# Set AWS CLI profile if specified
if [[ -n "$PROFILE" ]]; then
    export AWS_PROFILE="$PROFILE"
    print_status "Using AWS profile: $PROFILE"
fi

# Function to check if AWS CLI is configured
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS CLI is not configured or credentials are invalid."
        exit 1
    fi
    
    local account_id=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
    print_status "AWS Account: $account_id"
    print_status "Current region: $REGION"
}

# Function to generate cluster templates using Jinja2
generate_cluster_templates() {
    if [[ "$DEPLOYMENT_TYPE" != "cluster" ]]; then
        return 0
    fi
    
    print_status "Generating cluster templates using Jinja2..."
    
    local template_script="$(dirname "$0")/cluster/generate_templates.py"
    if [[ ! -f "$template_script" ]]; then
        print_error "Template generator script not found: $template_script"
        exit 1
    fi
    
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required for template generation but is not installed."
        exit 1
    fi
    
    # Check if jinja2 is available
    if ! python3 -c "import jinja2" &> /dev/null; then
        print_status "Installing jinja2 dependency..."
        pip3 install --user jinja2 || {
            print_error "Failed to install jinja2. Please install manually: pip3 install jinja2"
            exit 1
        }
    fi
    
    # Build template generation command
    local generate_cmd="python3 \"$template_script\" \"$CLUSTER_TEMPLATE\""
    generate_cmd="$generate_cmd --cluster-name \"$CLUSTER_NAME\""
    generate_cmd="$generate_cmd --oidc-provider \"$OIDC_PROVIDER\""
    generate_cmd="$generate_cmd --oidc-audience \"$OIDC_AUDIENCE\""
    
    # Add optional parameters
    if [[ -n "$PROJECT_NAME" ]]; then
        generate_cmd="$generate_cmd --project-name \"$PROJECT_NAME\""
    fi
    
    if [[ -n "$ENVIRONMENT" ]]; then
        generate_cmd="$generate_cmd --environment \"$ENVIRONMENT\""
    fi
    
    print_status "Running: $generate_cmd"
    
    # Execute template generation
    if eval "$generate_cmd"; then
        print_success "Template generation completed successfully."
    else
        print_error "Template generation failed."
        exit 1
    fi
}

# Function to check if jq is installed
check_jq() {
    if ! command -v jq &> /dev/null; then
        print_error "jq is not installed. Please install it first."
        print_error "  On macOS: brew install jq"
        print_error "  On Ubuntu/Debian: sudo apt-get install jq"
        print_error "  On RHEL/CentOS: sudo yum install jq"
        print_error "  On Amazon Linux: sudo yum install jq"
        exit 1
    fi
    print_status "jq is installed."
}

# Function to check if S3 bucket exists (only for regional deployments)
check_template_bucket() {
    if [[ "$DEPLOYMENT_TYPE" != "regional" ]]; then
        return 0
    fi
    
    if ! aws s3api head-bucket --bucket "$TEMPLATE_BUCKET" --region "$REGION" 2>/dev/null; then
        print_error "S3 bucket '$TEMPLATE_BUCKET' does not exist or is not accessible."
        print_status "Creating S3 bucket '$TEMPLATE_BUCKET'..."
        
        if [[ "$REGION" == "us-east-1" ]]; then
            aws s3api create-bucket --bucket "$TEMPLATE_BUCKET" --region "$REGION"
        else
            aws s3api create-bucket --bucket "$TEMPLATE_BUCKET" --region "$REGION" \
                --create-bucket-configuration LocationConstraint="$REGION"
        fi
        
        # Enable versioning for template bucket
        aws s3api put-bucket-versioning --bucket "$TEMPLATE_BUCKET" \
            --versioning-configuration Status=Enabled
        
        print_success "Created S3 bucket: $TEMPLATE_BUCKET"
    else
        print_status "S3 bucket '$TEMPLATE_BUCKET' exists and is accessible."
    fi
}

# Function to upload templates to S3 (only for regional deployments)
upload_templates() {
    if [[ "$DEPLOYMENT_TYPE" != "regional" ]]; then
        return 0
    fi
    
    local template_dir="$(dirname "$0")/regional"
    local templates=("core-infrastructure.yaml")
    
    # Add SQS stack if requested
    if [[ "$INCLUDE_SQS" == true ]]; then
        templates+=("sqs-stack.yaml")
    fi
    
    # Add Lambda stack if requested
    if [[ "$INCLUDE_LAMBDA" == true ]]; then
        templates+=("lambda-stack.yaml")
    fi
    
    # Add API stack if requested
    if [[ "$INCLUDE_API" == true ]]; then
        templates+=("api-stack.yaml")
    fi
    
    print_status "Uploading nested templates to S3..."
    
    for template in "${templates[@]}"; do
        local template_path="$template_dir/$template"
        
        if [[ ! -f "$template_path" ]]; then
            print_error "Template file not found: $template_path"
            exit 1
        fi
        
        print_status "Uploading $template..."
        aws s3 cp "$template_path" "s3://$TEMPLATE_BUCKET/cloudformation/templates/$template" \
            --region "$REGION"
    done
    
    print_success "All templates uploaded successfully."
}

# Function to validate templates
validate_templates() {
    local template_dir="$(dirname "$0")"
    local templates=()
    
    case "$DEPLOYMENT_TYPE" in
        global)
            templates=("global/central-log-distribution-role.yaml")
            ;;
        regional)
            template_dir="$template_dir/regional"
            templates=("main.yaml" "core-infrastructure.yaml")
            
            # Add SQS stack if requested
            if [[ "$INCLUDE_SQS" == true ]]; then
                templates+=("sqs-stack.yaml")
            fi
            
            # Add Lambda stack if requested
            if [[ "$INCLUDE_LAMBDA" == true ]]; then
                templates+=("lambda-stack.yaml")
            fi
            
            # Add API stack if requested
            if [[ "$INCLUDE_API" == true ]]; then
                templates+=("api-stack.yaml")
            fi
            ;;
        customer)
            templates=("customer/customer-log-distribution-role.yaml")
            ;;
        cluster)
            # For cluster deployment, validate the rendered templates based on type
            if [[ "$CLUSTER_TEMPLATE" == "both" ]]; then
                templates=("cluster/rendered/cluster-vector-role.yaml" "cluster/rendered/cluster-processor-role.yaml")
            else
                templates=("cluster/rendered/cluster-${CLUSTER_TEMPLATE}-role.yaml")
            fi
            ;;
    esac
    
    print_status "Validating CloudFormation templates..."
    
    for template in "${templates[@]}"; do
        local template_path
        if [[ "$template" == */* ]]; then
            # Template path includes subdirectory
            template_path="$(dirname "$0")/$template"
        else
            # Template is in the deployment type directory
            template_path="$template_dir/$template"
        fi
        
        if [[ ! -f "$template_path" ]]; then
            print_error "Template file not found: $template_path"
            exit 1
        fi
        
        print_status "Validating $template..."
        if aws cloudformation validate-template --template-body "file://$template_path" --region "$REGION" > /dev/null; then
            print_success "$template is valid."
        else
            print_error "$template validation failed."
            exit 1
        fi
    done
    
    print_success "All templates are valid."
}

# Function to check if stack exists
stack_exists() {
    aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null
}

# Function to get stack status
get_stack_status() {
    aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST"
}

# Function to wait for stack operation to complete
wait_for_stack() {
    local operation="$1"
    print_status "Waiting for stack $operation to complete..."
    
    aws cloudformation wait "stack-${operation}-complete" --stack-name "$STACK_NAME" --region "$REGION"
    
    local status=$(get_stack_status)
    if [[ "$status" == *"COMPLETE"* ]]; then
        print_success "Stack $operation completed successfully."
        return 0
    else
        print_error "Stack $operation failed. Status: $status"
        return 1
    fi
}

# Function to deploy or update stack
deploy_stack() {
    local template_dir="$(dirname "$0")"
    local main_template
    local operation
    
    # Determine template path based on deployment type
    case "$DEPLOYMENT_TYPE" in
        global)
            main_template="$template_dir/global/central-log-distribution-role.yaml"
            ;;
        regional)
            main_template="$template_dir/regional/main.yaml"
            ;;
        customer)
            main_template="$template_dir/customer/customer-log-distribution-role.yaml"
            ;;
        cluster)
            # For cluster deployment, use the generated template based on type
            if [[ "$CLUSTER_TEMPLATE" == "both" ]]; then
                # For "both", default to processor template (primary template)
                main_template="$template_dir/cluster/rendered/cluster-processor-role.yaml"
            else
                main_template="$template_dir/cluster/rendered/cluster-${CLUSTER_TEMPLATE}-role.yaml"
            fi
            ;;
    esac
    
    if stack_exists; then
        operation="update"
        print_status "Updating existing stack: $STACK_NAME"
    else
        operation="create"
        print_status "Creating new stack: $STACK_NAME"
    fi
    
    # Generate random suffix for unique resource names
    local random_suffix
    if command -v openssl &> /dev/null; then
        random_suffix=$(openssl rand -hex 4)
    else
        # Fallback method using /dev/urandom
        random_suffix=$(head -c 1000 /dev/urandom | tr -dc 'a-f0-9' | head -c 8)
    fi
    
    if [[ -z "$random_suffix" || ${#random_suffix} -ne 8 ]]; then
        # Fallback to timestamp-based suffix if random generation fails
        random_suffix=$(date +%s | tail -c 8)
    fi
    
    print_status "Generated random suffix: $random_suffix"
    
    # Prepare parameters based on deployment type
    local parameters=()
    
    case "$DEPLOYMENT_TYPE" in
        global)
            # Global deployment parameters
            if [[ "$operation" == "update" ]]; then
                print_status "Reading existing stack parameters..."
                local existing_params=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].Parameters' --output json 2>/dev/null || echo '[]')
                local random_suffix_existing=$(echo "$existing_params" | jq -r '.[] | select(.ParameterKey=="RandomSuffix") | .ParameterValue // empty')
                
                if [[ -n "$random_suffix_existing" ]]; then
                    random_suffix="$random_suffix_existing"
                    print_status "Using existing RandomSuffix: $random_suffix"
                fi
                
                parameters=(
                    "ProjectName=$PROJECT_NAME"
                    "RandomSuffix=$random_suffix"
                )
            else
                parameters=(
                    "ProjectName=$PROJECT_NAME"
                    "RandomSuffix=$random_suffix"
                )
            fi
            ;;
        customer)
            # Customer deployment parameters
            parameters=(
                "CentralLogDistributionRoleArn=$CENTRAL_ROLE_ARN"
            )
            ;;
        cluster)
            # Cluster deployment parameters - common for all cluster types
            parameters=(
                "ClusterName=$CLUSTER_NAME"
                "OIDCProviderURL=$OIDC_PROVIDER"
                "OIDCAudience=$OIDC_AUDIENCE"
                "ProjectName=$PROJECT_NAME"
                "Environment=$ENVIRONMENT"
            )
            
            # Try to get regional stack outputs automatically (needed for both vector and processor)
            local regional_stack_name=""
            # Look for a regional stack (main stack, not nested stacks)
            regional_stack_name=$(aws cloudformation list-stacks --region "$REGION" \
                --query "StackSummaries[?StackName == 'multi-tenant-logging-${ENVIRONMENT}' && StackStatus != 'DELETE_COMPLETE'].StackName" \
                --output text 2>/dev/null | head -1 || echo "")
            
            # Add template-specific parameters
            if [[ "$CLUSTER_TEMPLATE" == "processor" || "$CLUSTER_TEMPLATE" == "both" ]]; then
                # Processor role requires additional ARNs
                if [[ -n "$CENTRAL_ROLE_ARN" ]]; then
                    parameters+=("CentralLogDistributionRoleArn=$CENTRAL_ROLE_ARN")
                fi
                
                if [[ -n "$regional_stack_name" ]]; then
                    print_status "Found regional stack: $regional_stack_name"
                    print_status "Retrieving outputs for processor role parameters..."
                    
                    # Get required outputs from regional stack
                    local tenant_table_arn=$(aws cloudformation describe-stacks --stack-name "$regional_stack_name" --region "$REGION" \
                        --query 'Stacks[0].Outputs[?OutputKey==`TenantConfigTableArn`].OutputValue' --output text 2>/dev/null || echo "")
                    local bucket_arn=$(aws cloudformation describe-stacks --stack-name "$regional_stack_name" --region "$REGION" \
                        --query 'Stacks[0].Outputs[?OutputKey==`CentralLoggingBucketArn`].OutputValue' --output text 2>/dev/null || echo "")
                    
                    # Try to get from nested core infrastructure stack if not found
                    if [[ -z "$tenant_table_arn" || -z "$bucket_arn" ]]; then
                        local core_stack_arn=$(aws cloudformation list-stack-resources --stack-name "$regional_stack_name" --region "$REGION" \
                            --query 'StackResourceSummaries[?LogicalResourceId==`CoreInfrastructureStack`].PhysicalResourceId' --output text 2>/dev/null || echo "")
                        
                        if [[ -n "$core_stack_arn" ]]; then
                            local core_stack_name=$(echo "$core_stack_arn" | awk -F'/' '{print $2}')
                            
                            if [[ -z "$tenant_table_arn" ]]; then
                                tenant_table_arn=$(aws cloudformation describe-stacks --stack-name "$core_stack_name" --region "$REGION" \
                                    --query 'Stacks[0].Outputs[?OutputKey==`TenantConfigTableArn`].OutputValue' --output text 2>/dev/null || echo "")
                            fi
                            
                            if [[ -z "$bucket_arn" ]]; then
                                bucket_arn=$(aws cloudformation describe-stacks --stack-name "$core_stack_name" --region "$REGION" \
                                    --query 'Stacks[0].Outputs[?OutputKey==`CentralLoggingBucketArn`].OutputValue' --output text 2>/dev/null || echo "")
                            fi
                        fi
                    fi
                    
                    # Add parameters if found
                    if [[ -n "$tenant_table_arn" ]]; then
                        parameters+=("TenantConfigTableArn=$tenant_table_arn")
                        print_status "Using TenantConfigTableArn: $tenant_table_arn"
                    fi
                    
                    if [[ -n "$bucket_arn" ]]; then
                        parameters+=("CentralLoggingBucketArn=$bucket_arn")
                        print_status "Using CentralLoggingBucketArn: $bucket_arn"
                    fi
                else
                    print_warning "Could not automatically find regional stack. You may need to provide ARNs manually."
                fi
            fi
            
            if [[ "$CLUSTER_TEMPLATE" == "vector" || "$CLUSTER_TEMPLATE" == "both" ]]; then
                # Vector role requires assume role policy ARN
                if [[ -n "$regional_stack_name" ]]; then
                    print_status "Retrieving VectorAssumeRolePolicyArn for vector role..."
                    
                    # Get VectorAssumeRolePolicyArn from regional stack
                    local vector_policy_arn=$(aws cloudformation describe-stacks --stack-name "$regional_stack_name" --region "$REGION" \
                        --query 'Stacks[0].Outputs[?OutputKey==`VectorAssumeRolePolicyArn`].OutputValue' --output text 2>/dev/null || echo "")
                    
                    # Try to get from nested core infrastructure stack if not found
                    if [[ -z "$vector_policy_arn" ]]; then
                        local core_stack_arn=$(aws cloudformation list-stack-resources --stack-name "$regional_stack_name" --region "$REGION" \
                            --query 'StackResourceSummaries[?LogicalResourceId==`CoreInfrastructureStack`].PhysicalResourceId' --output text 2>/dev/null || echo "")
                        
                        if [[ -n "$core_stack_arn" ]]; then
                            local core_stack_name=$(echo "$core_stack_arn" | awk -F'/' '{print $2}')
                            vector_policy_arn=$(aws cloudformation describe-stacks --stack-name "$core_stack_name" --region "$REGION" \
                                --query 'Stacks[0].Outputs[?OutputKey==`VectorAssumeRolePolicyArn`].OutputValue' --output text 2>/dev/null || echo "")
                        fi
                    fi
                    
                    # Add parameter if found
                    if [[ -n "$vector_policy_arn" ]]; then
                        parameters+=("VectorAssumeRolePolicyArn=$vector_policy_arn")
                        print_status "Using VectorAssumeRolePolicyArn: $vector_policy_arn"
                    else
                        print_warning "Could not find VectorAssumeRolePolicyArn. Vector role deployment may require manual parameter."
                    fi
                else
                    print_warning "No regional stack found. Vector role deployment may require manual VectorAssumeRolePolicyArn parameter."
                fi
            fi
            ;;
        regional)
            # Regional deployment parameters - more complex handling
            if [[ "$operation" == "update" ]]; then
                print_status "Reading existing stack parameters..."
                local existing_params=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].Parameters' --output json 2>/dev/null || echo '[]')
                
                # Use jq for parameter extraction (required)
                local template_bucket_existing=$(echo "$existing_params" | jq -r '.[] | select(.ParameterKey=="TemplateBucket") | .ParameterValue // empty')
                
                # Use existing TemplateBucket if not specified on command line
                if [[ -z "$TEMPLATE_BUCKET" && -n "$template_bucket_existing" ]]; then
                    TEMPLATE_BUCKET="$template_bucket_existing"
                    print_status "Using existing TemplateBucket: $TEMPLATE_BUCKET"
                fi
                
                # Build parameters array with values from command line or defaults
                parameters=()
                
                # Add all possible parameters - CloudFormation will ignore any that don't exist in the template
                parameters+=("Environment=$ENVIRONMENT")
                parameters+=("ProjectName=$PROJECT_NAME")
                parameters+=("TemplateBucket=$TEMPLATE_BUCKET")
                parameters+=("CentralLogDistributionRoleArn=$CENTRAL_ROLE_ARN")
                if [[ "$INCLUDE_SQS" == true ]]; then
                    parameters+=("IncludeSQSStack=true")
                else
                    parameters+=("IncludeSQSStack=false")
                fi
                if [[ "$INCLUDE_LAMBDA" == true ]]; then
                    parameters+=("IncludeLambdaStack=true")
                else
                    parameters+=("IncludeLambdaStack=false")
                fi
                if [[ "$INCLUDE_API" == true ]]; then
                    parameters+=("IncludeAPIStack=true")
                else
                    parameters+=("IncludeAPIStack=false")
                fi
                
                # Add new S3DeleteAfterDays parameter with default if not in existing params
                local s3_delete_days_found=false
                
                # Process each existing parameter to preserve values not specified on command line
                while IFS= read -r param_entry; do
                    local param_key=$(echo "$param_entry" | jq -r '.ParameterKey')
                    local param_value=$(echo "$param_entry" | jq -r '.ParameterValue')
                    
                    # Skip parameters we've already set from command line
                    case "$param_key" in
                        Environment|ProjectName|TemplateBucket|CentralLogDistributionRoleArn|IncludeSQSStack|IncludeLambdaStack|IncludeAPIStack)
                            continue
                            ;;
                        ECRImageUri)
                            # Only add if Lambda is enabled and not provided on command line
                            if [[ "$INCLUDE_LAMBDA" == true && -z "$ECR_IMAGE_URI" && -n "$param_value" ]]; then
                                ECR_IMAGE_URI="$param_value"
                                parameters+=("ECRImageUri=$param_value")
                            elif [[ "$INCLUDE_LAMBDA" == true && -n "$ECR_IMAGE_URI" ]]; then
                                parameters+=("ECRImageUri=$ECR_IMAGE_URI")
                            fi
                            ;;
                        *)
                            # Skip removed parameters that no longer exist in template
                            case "$param_key" in
                                S3StandardIADays|S3GlacierDays|S3DeepArchiveDays|S3LogRetentionDays|EnableS3IntelligentTiering)
                                    print_status "Skipping removed parameter: $param_key"
                                    ;;
                                S3DeleteAfterDays)
                                    # Track that we found this parameter
                                    s3_delete_days_found=true
                                    if [[ -n "$param_value" ]]; then
                                        parameters+=("${param_key}=${param_value}")
                                    fi
                                    ;;
                                *)
                                    # Preserve all other parameters with their existing values
                                    if [[ -n "$param_value" ]]; then
                                        parameters+=("${param_key}=${param_value}")
                                    fi
                                    ;;
                            esac
                            ;;
                    esac
                done < <(echo "$existing_params" | jq -c '.[]')
                
                # Add S3DeleteAfterDays with default if not found
                if [[ "$s3_delete_days_found" != true ]]; then
                    parameters+=("S3DeleteAfterDays=7")
                    print_status "Adding new parameter S3DeleteAfterDays with default value: 7"
                fi
                
            else
                # For create operations, use all parameters with defaults/specified values
                parameters=(
                    "Environment=$ENVIRONMENT"
                    "ProjectName=$PROJECT_NAME"
                    "TemplateBucket=$TEMPLATE_BUCKET"
                    "CentralLogDistributionRoleArn=$CENTRAL_ROLE_ARN"
                    "IncludeSQSStack=$(if [[ "$INCLUDE_SQS" == true ]]; then echo 'true'; else echo 'false'; fi)"
                    "IncludeLambdaStack=$(if [[ "$INCLUDE_LAMBDA" == true ]]; then echo 'true'; else echo 'false'; fi)"
                    "IncludeAPIStack=$(if [[ "$INCLUDE_API" == true ]]; then echo 'true'; else echo 'false'; fi)"
                )
                
                # Add ECR image URI if Lambda is enabled
                if [[ "$INCLUDE_LAMBDA" == true && -n "$ECR_IMAGE_URI" ]]; then
                    parameters+=("ECRImageUri=$ECR_IMAGE_URI")
                fi
                
                # Add API parameters if API is enabled
                if [[ "$INCLUDE_API" == true ]]; then
                    parameters+=("APIAuthSSMParameter=$API_AUTH_SSM_PARAMETER")
                    parameters+=("AuthorizerImageUri=$AUTHORIZER_IMAGE_URI")
                    parameters+=("APIImageUri=$API_IMAGE_URI")
                fi
            fi
            ;;
    esac
    
    # Add optional parameters if not default
    local param_file="$template_dir/parameters-${ENVIRONMENT}.json"
    if [[ -f "$param_file" ]]; then
        print_status "Using parameters file: $param_file"
        local param_option="--parameters file://$param_file"
    else
        local param_option="--parameters"
        for param in "${parameters[@]}"; do
            param_option="$param_option ParameterKey=${param%=*},ParameterValue=${param#*=}"
        done
    fi
    
    # Prepare capabilities
    local capabilities="--capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM"
    
    # Prepare tags
    local tags=(
        "Project=$PROJECT_NAME"
        "Environment=$ENVIRONMENT"
        "ManagedBy=cloudformation"
        "DeployedBy=$(whoami)"
        "DeployedAt=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    )
    
    local tag_options="--tags"
    for tag in "${tags[@]}"; do
        tag_options="$tag_options Key=${tag%=*},Value=${tag#*=}"
    done
    
    if [[ "$DRY_RUN" == true ]]; then
        print_warning "DRY RUN MODE - No actual deployment will occur"
        print_status "Would execute:"
        echo "aws cloudformation ${operation}-stack \\"
        echo "  --stack-name $STACK_NAME \\"
        echo "  --template-body file://$main_template \\"
        echo "  --region $REGION \\"
        echo "  $param_option \\"
        echo "  $capabilities \\"
        echo "  $tag_options"
        return 0
    fi
    
    # Execute the deployment
    local cmd="aws cloudformation ${operation}-stack \
        --stack-name $STACK_NAME \
        --template-body file://$main_template \
        --region $REGION \
        $param_option \
        $capabilities \
        $tag_options"
    
    if eval "$cmd"; then
        if wait_for_stack "$operation"; then
            print_success "Stack deployment completed successfully!"
            
            # Display stack outputs
            print_status "Stack outputs:"
            aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
                --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table
            
            return 0
        else
            print_error "Stack deployment failed!"
            return 1
        fi
    else
        print_error "Failed to ${operation} stack."
        return 1
    fi
}

# Function to display deployment summary
display_summary() {
    cat << EOF

========================================
   DEPLOYMENT SUMMARY
========================================
Deployment Type: $DEPLOYMENT_TYPE
Stack Name:      $STACK_NAME
Project:         $PROJECT_NAME
Region:          $REGION
AWS Profile:     ${PROFILE:-default}

EOF

    case "$DEPLOYMENT_TYPE" in
        global)
            cat << EOF
Templates:
- global/central-log-distribution-role.yaml (Global IAM role)

Configuration:
- Creates central log distribution role for cross-account access
- Role name: ROSA-CentralLogDistributionRole-{random-suffix}

EOF
            ;;
        regional)
            cat << EOF
Environment:     $ENVIRONMENT
Template Bucket: $TEMPLATE_BUCKET
Central Role:    $CENTRAL_ROLE_ARN

Templates:
- regional/main.yaml (main template)
- regional/core-infrastructure.yaml (S3, DynamoDB, KMS, IAM, SNS)
$(if [[ "$INCLUDE_SQS" == true ]]; then echo "- regional/sqs-stack.yaml (SQS queue and DLQ)"; fi)
$(if [[ "$INCLUDE_LAMBDA" == true ]]; then echo "- regional/lambda-stack.yaml (Container-based Lambda functions)"; fi)
$(if [[ "$INCLUDE_API" == true ]]; then echo "- regional/api-stack.yaml (API Gateway and Lambda authorizer)"; fi)

Configuration:
- Include SQS Stack: $INCLUDE_SQS
- Include Lambda Stack: $INCLUDE_LAMBDA
- Include API Stack: $INCLUDE_API
$(if [[ -n "$ECR_IMAGE_URI" ]]; then echo "- ECR Image URI: $ECR_IMAGE_URI"; fi)
$(if [[ -n "$API_AUTH_SSM_PARAMETER" ]]; then echo "- API Auth SSM Parameter: $API_AUTH_SSM_PARAMETER"; fi)
$(if [[ -n "$AUTHORIZER_IMAGE_URI" ]]; then echo "- Authorizer Image URI: $AUTHORIZER_IMAGE_URI"; fi)
$(if [[ -n "$API_IMAGE_URI" ]]; then echo "- API Image URI: $API_IMAGE_URI"; fi)

EOF
            ;;
        customer)
            cat << EOF
Central Role:    $CENTRAL_ROLE_ARN

Templates:
- customer/customer-log-distribution-role.yaml (Customer IAM role)

Configuration:
- Creates customer-side role for cross-account log delivery
- Role name: CustomerLogDistribution-{region}
- Grants CloudWatch Logs permissions in this region

EOF
            ;;
        cluster)
            cat << EOF
Cluster Name:    $CLUSTER_NAME
OIDC Provider:   $OIDC_PROVIDER
OIDC Audience:   $OIDC_AUDIENCE

Templates:
- cluster/cluster-vector-role.yaml (Vector IAM role for IRSA)
- cluster/cluster-processor-role.yaml (Processor IAM role for IRSA)

Configuration:
- Creates cluster-specific IAM roles for Vector and log processor
- Uses IRSA (IAM Roles for Service Accounts) for secure authentication
- Integrates with regional infrastructure through role ARNs

EOF
            ;;
    esac

    echo "========================================"
    echo
}

# Main execution flow
main() {
    display_summary
    
    print_status "Starting deployment process..."
    
    # Step 1: Check prerequisites
    check_aws_cli
    check_jq
    check_template_bucket
    
    # Step 2: Generate cluster templates (if needed)
    generate_cluster_templates
    
    # Step 3: Validate templates
    validate_templates
    
    if [[ "$VALIDATE_ONLY" == true ]]; then
        print_success "Template validation completed successfully. Exiting."
        exit 0
    fi
    
    # Step 4: Upload nested templates
    upload_templates
    
    # Step 5: Deploy stack
    if deploy_stack; then
        print_success "Deployment completed successfully!"
        
        # Display useful information
        print_status "CloudFormation Console: https://${REGION}.console.aws.amazon.com/cloudformation/home?region=${REGION}#/stacks/stackinfo?stackId=${STACK_NAME}"
        print_status "Lambda Function: https://${REGION}.console.aws.amazon.com/lambda/home?region=${REGION}#/functions/${PROJECT_NAME}-${ENVIRONMENT}-log-distributor"
    else
        print_error "Deployment failed!"
        exit 1
    fi
}

# Execute main function
main "$@"