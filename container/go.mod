module github.com/openshift/rosa-log-router

go 1.24

require (
	github.com/aws/aws-lambda-go v1.51.0
	github.com/aws/aws-sdk-go-v2 v1.47.6
	github.com/aws/aws-sdk-go-v2/config v1.33.13
	github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue v1.21.17
	github.com/aws/aws-sdk-go-v2/service/cloudwatch v1.75.3
	github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs v1.91.0
	github.com/aws/aws-sdk-go-v2/service/dynamodb v1.73.0
	github.com/aws/aws-sdk-go-v2/service/s3 v1.114.6
	github.com/aws/aws-sdk-go-v2/service/sqs v1.52.8
	github.com/aws/aws-sdk-go-v2/service/sts v1.51.6
	github.com/aws/smithy-go v1.28.8
	github.com/google/uuid v1.6.0
	github.com/stretchr/testify v1.12.1
)

require (
	github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream v1.7.25 // indirect
	github.com/aws/aws-sdk-go-v2/credentials v1.20.13 // indirect
	github.com/aws/aws-sdk-go-v2/feature/ec2/imds v1.20.5 // indirect
	github.com/aws/aws-sdk-go-v2/internal/configsources v1.5.9 // indirect
	github.com/aws/aws-sdk-go-v2/internal/endpoints/v2 v2.8.9 // indirect
	github.com/aws/aws-sdk-go-v2/internal/v4a v1.5.8 // indirect
	github.com/aws/aws-sdk-go-v2/service/dynamodbstreams v1.46.4 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/accept-encoding v1.13.24 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/checksum v1.11.9 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/endpoint-discovery v1.13.9 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/presigned-url v1.14.8 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/s3shared v1.20.8 // indirect
	github.com/aws/aws-sdk-go-v2/service/signin v1.12.1 // indirect
	github.com/aws/aws-sdk-go-v2/service/sso v1.39.1 // indirect
	github.com/aws/aws-sdk-go-v2/service/ssooidc v1.44.1 // indirect
	go.yaml.in/yaml/v3 v3.0.5 // indirect
)
