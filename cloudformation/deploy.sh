#!/bin/bash

# CloudFormation Deployment Script for Multi-Tenant Logging Infrastructure
# This script deploys the nested stack architecture for the logging pipeline

set -e  # Exit on any error

# Default values
ENVIRONMENT="development"
PROJECT_NAME="multi-tenant-logging"
REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
TEMPLATE_BUCKET=""
PROFILE="${AWS_PROFILE:-}"
DRY_RUN=false
VALIDATE_ONLY=false
INCLUDE_SQS=false
INCLUDE_LAMBDA=false
ECR_IMAGE_URI=""

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

OPTIONS:
    -e, --environment ENV       Environment name (production, staging, development). Default: development
    -p, --project-name NAME     Project name. Default: multi-tenant-logging
    -r, --region REGION         AWS region. Default: us-east-1
    -s, --stack-name NAME       CloudFormation stack name. Default: PROJECT_NAME-ENVIRONMENT
    -b, --template-bucket NAME  S3 bucket for storing nested templates (required)
    --profile PROFILE           AWS CLI profile to use
    --include-sqs               Include SQS stack for log processing
    --include-lambda            Include Lambda stack for container-based processing
    --ecr-image-uri URI         ECR container image URI (required if --include-lambda)
    --dry-run                   Show what would be deployed without actually deploying
    --validate-only             Only validate templates without deploying
    -h, --help                  Display this help message

EXAMPLES:
    # Deploy core infrastructure only
    $0 -b my-cloudformation-templates-bucket

    # Deploy core + SQS for external processing
    $0 -b my-templates-bucket --include-sqs

    # Deploy core + SQS + Lambda container processing
    $0 -b my-templates-bucket --include-sqs --include-lambda --ecr-image-uri 123456789012.dkr.ecr.us-east-2.amazonaws.com/log-processor:latest

    # Deploy to staging environment with SQS
    $0 -e staging -b my-templates-bucket --include-sqs

    # Validate templates only
    $0 -b my-templates-bucket --validate-only

    # Deploy with specific AWS profile
    $0 -b my-templates-bucket --profile my-aws-profile --include-sqs

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
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

# For stack updates, template bucket might come from existing stack
if [[ -z "$TEMPLATE_BUCKET" ]]; then
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
        # Try to get template bucket from existing stack
        TEMPLATE_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].Parameters[?ParameterKey==`TemplateBucket`].ParameterValue' --output text 2>/dev/null || echo "")
        if [[ -n "$TEMPLATE_BUCKET" ]]; then
            print_status "Using existing template bucket from stack: $TEMPLATE_BUCKET"
        else
            print_error "Template bucket is required. Use -b or --template-bucket option."
            usage
            exit 1
        fi
    else
        print_error "Template bucket is required for new stacks. Use -b or --template-bucket option."
        usage
        exit 1
    fi
fi

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(production|staging|development)$ ]]; then
    print_error "Environment must be one of: production, staging, development"
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

# Update stack name if not explicitly provided
if [[ "$STACK_NAME" == "multi-tenant-logging-development" ]]; then
    STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
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

# Function to check if S3 bucket exists
check_template_bucket() {
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

# Function to upload templates to S3
upload_templates() {
    local template_dir="$(dirname "$0")"
    local templates=("core-infrastructure.yaml")
    
    # Add SQS stack if requested
    if [[ "$INCLUDE_SQS" == true ]]; then
        templates+=("sqs-stack.yaml")
    fi
    
    # Add Lambda stack if requested
    if [[ "$INCLUDE_LAMBDA" == true ]]; then
        templates+=("lambda-stack.yaml")
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
    local templates=("main.yaml" "core-infrastructure.yaml")
    
    # Add SQS stack if requested
    if [[ "$INCLUDE_SQS" == true ]]; then
        templates+=("sqs-stack.yaml")
    fi
    
    # Add Lambda stack if requested
    if [[ "$INCLUDE_LAMBDA" == true ]]; then
        templates+=("lambda-stack.yaml")
    fi
    
    print_status "Validating CloudFormation templates..."
    
    for template in "${templates[@]}"; do
        local template_path="$template_dir/$template"
        
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
    local main_template="$template_dir/main.yaml"
    local operation
    
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
    
    # Prepare parameters
    local parameters=()
    
    # For updates, read existing parameters and preserve their values
    if [[ "$operation" == "update" ]]; then
        print_status "Reading existing stack parameters..."
        local existing_params=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].Parameters' --output json 2>/dev/null || echo '[]')
        
        # Use jq for parameter extraction (required)
        local random_suffix_existing=$(echo "$existing_params" | jq -r '.[] | select(.ParameterKey=="RandomSuffix") | .ParameterValue // empty')
        local template_bucket_existing=$(echo "$existing_params" | jq -r '.[] | select(.ParameterKey=="TemplateBucket") | .ParameterValue // empty')
        
        # Use existing RandomSuffix if it exists, otherwise generate new one
        if [[ -n "$random_suffix_existing" ]]; then
            random_suffix="$random_suffix_existing"
            print_status "Using existing RandomSuffix: $random_suffix"
        fi
        
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
        parameters+=("RandomSuffix=$random_suffix")
        parameters+=("IncludeSQSStack=$INCLUDE_SQS")
        parameters+=("IncludeLambdaStack=$INCLUDE_LAMBDA")
        
        # Add new S3DeleteAfterDays parameter with default if not in existing params
        local s3_delete_days_found=false
        
        # Process each existing parameter to preserve values not specified on command line
        while IFS= read -r param_entry; do
            local param_key=$(echo "$param_entry" | jq -r '.ParameterKey')
            local param_value=$(echo "$param_entry" | jq -r '.ParameterValue')
            
            # Skip parameters we've already set from command line
            case "$param_key" in
                Environment|ProjectName|TemplateBucket|RandomSuffix|IncludeSQSStack|IncludeLambdaStack)
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
            "RandomSuffix=$random_suffix"
            "IncludeSQSStack=$INCLUDE_SQS"
            "IncludeLambdaStack=$INCLUDE_LAMBDA"
        )
        
        # Add ECR image URI if Lambda is enabled
        if [[ "$INCLUDE_LAMBDA" == true && -n "$ECR_IMAGE_URI" ]]; then
            parameters+=("ECRImageUri=$ECR_IMAGE_URI")
        fi
    fi
    
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
Stack Name:     $STACK_NAME
Environment:    $ENVIRONMENT
Project:        $PROJECT_NAME
Region:         $REGION
Template Bucket: $TEMPLATE_BUCKET
AWS Profile:    ${PROFILE:-default}

Templates:
- main.yaml (main template)
- core-infrastructure.yaml (S3, DynamoDB, KMS, IAM, SNS)
$(if [[ "$INCLUDE_SQS" == true ]]; then echo "- sqs-stack.yaml (SQS queue and DLQ)"; fi)
$(if [[ "$INCLUDE_LAMBDA" == true ]]; then echo "- lambda-stack.yaml (Container-based Lambda functions)"; fi)

Configuration:
- Include SQS Stack: $INCLUDE_SQS
- Include Lambda Stack: $INCLUDE_LAMBDA
$(if [[ -n "$ECR_IMAGE_URI" ]]; then echo "- ECR Image URI: $ECR_IMAGE_URI"; fi)

========================================

EOF
}

# Main execution flow
main() {
    display_summary
    
    print_status "Starting deployment process..."
    
    # Step 1: Check prerequisites
    check_aws_cli
    check_jq
    check_template_bucket
    
    # Step 2: Validate templates
    validate_templates
    
    if [[ "$VALIDATE_ONLY" == true ]]; then
        print_success "Template validation completed successfully. Exiting."
        exit 0
    fi
    
    # Step 3: Upload nested templates
    upload_templates
    
    # Step 4: Deploy stack
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