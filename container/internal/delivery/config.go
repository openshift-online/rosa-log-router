package delivery

import (
	"context"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
)

// buildConfigWithEndpoint creates an AWS config with the specified region, credentials, and optional endpoint URL.
// This is used when assuming roles to create clients that need to work with LocalStack (via endpoint URL override)
// or real AWS (with empty endpoint URL).
func buildConfigWithEndpoint(ctx context.Context, region string, creds aws.Credentials, endpointURL string) (aws.Config, error) {
	configOptions := []func(*config.LoadOptions) error{
		config.WithRegion(region),
		config.WithCredentialsProvider(aws.CredentialsProviderFunc(func(ctx context.Context) (aws.Credentials, error) {
			return creds, nil
		})),
	}

	// Add endpoint resolver if endpoint URL is configured (for LocalStack)
	// Note: Using deprecated endpoint resolver API for backward compatibility with LocalStack.
	// The modern per-service endpoint configuration would require refactoring the service client creation.
	// This approach works consistently across all AWS services (S3, CloudWatch, STS, etc.).
	// SA1019 deprecation warnings are suppressed in .golangci.yml for LocalStack compatibility.
	if endpointURL != "" {
		configOptions = append(configOptions, config.WithEndpointResolverWithOptions(
			aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
				return aws.Endpoint{
					URL:               endpointURL,
					HostnameImmutable: true,
				}, nil
			}),
		))
	}

	return config.LoadDefaultConfig(ctx, configOptions...)
}
