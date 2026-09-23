# Scripts

Helper scripts supporting the LocalStack integration pipeline and image builds.

## `validate-vector-flow.sh`
Validates that Vector collected pod logs and that the full pipeline delivered
them to the customer S3 buckets in LocalStack, asserting the multi-tenant
`{namespace}/{application}/` key layout for each customer. Invoked by
`make validate-vector-flow` and by
`.github/workflows/localstack-integration-tests.yaml`.

Prerequisite: infrastructure deployed to LocalStack (`make deploy-api`).

## `warmup-lambda.sh`
Warms up the LocalStack Lambda container to avoid cold-start flakiness before
the end-to-end suite. Invoked by `make warmup-lambda` /
`make test-e2e-with-warmup`.

## `build-and-push-lambda.sh`
Builds and pushes the Lambda container image(s). Used for local/manual image
publishing; production images are built by Konflux (`.tekton/`).

---

For running the full integration suite locally, use the Makefile targets
(`make start`, `make deploy-api`, `make validate-vector-flow`,
`make test-e2e-with-warmup`) rather than a standalone script. The previous
minikube/MinIO local integration script was removed alongside the redundant
minikube CI job (ROSAENG-66611).
