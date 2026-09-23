# Multi-Tenant Logging Pipeline Testing

This directory contains the Python **unit** tests for the pipeline. End-to-end
integration testing is Go-based and lives elsewhere (see below).

## Test layers

### 1. Unit tests — `tests/unit/` (Python, pytest)
Run with mocked AWS services (`moto`); no credentials or cluster required.

- `test_api_app_endpoints.py` — FastAPI endpoint behavior and validation
- `test_api_authorizer.py` — Lambda authorizer / HMAC authentication
- `test_api_dynamo_service.py` — DynamoDB tenant service
- `test_api_v1.py` — API integration-style tests (mocked)
- `test_vector_timestamp_parsing.py` — timestamp parsing parity with Vector

Shared fixtures live in `tests/conftest.py`; dependencies in
`tests/requirements.txt`.

```bash
pip3 install -r tests/requirements.txt

# Run all unit tests
pytest tests/unit/ -v

# With coverage (matches the unit-tests CI workflow)
pytest tests/unit/ --cov=container --cov=api/src --cov-report=term-missing
```

CI: `.github/workflows/unit-tests.yaml` (Python) and
`.github/workflows/go-unit-tests.yaml` (Go, `container/internal/...`).

### 2. Integration / end-to-end — LocalStack (Go)
The single integration pipeline stands up minikube + LocalStack + Terraform and
exercises the **real** deployment shape (Lambda log processor + API Gateway),
matching production. It is defined in
`.github/workflows/localstack-integration-tests.yaml` and driven locally by the
Makefile:

```bash
make start              # start LocalStack (Pro; requires auth token)
make deploy-api         # deploy infra + Lambda + API via Terraform
make validate-vector-flow   # verify Vector -> S3 -> Lambda -> customer buckets,
                            # including the {namespace}/{application}/ key layout
make test-e2e-with-warmup   # Go e2e suite (container/integration/)
```

The Go end-to-end tests themselves live in `container/integration/`.

> There is no longer a minikube/MinIO + DynamoDB-Local Python integration suite.
> Those tests validated the API and processor as in-cluster Kubernetes
> Deployments — a topology that does not exist in production (both run as AWS
> Lambdas). They were removed in favor of the higher-fidelity LocalStack
> pipeline. See ROSAENG-66611.

## Other files

`test_data.py`, `test_mock_sqs.py`, `test_sqs_handling.sh`,
`test_container_sqs.sh`, `test_metrics.py`, and `vector-local-test.yaml` are
legacy manual utilities. Some reference an older Python processor
(`container/log_processor.py`) that has since been replaced by the Go
implementation; treat them as historical and prefer the unit and LocalStack
suites above.
