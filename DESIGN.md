# **Architecting a Scalable, Multi-Tenant, and Cross-Account Logging Pipeline on AWS**

## **Section 1: Foundational Principles and Architectural Framework**

### **1.1. Executive Summary**

This document presents a comprehensive architectural design for a high-throughput, multi-region, and multi-tenant logging pipeline on Amazon Web Services (AWS). The proposed solution is tailored for ingesting log streams from Kubernetes and OpenShift environments, processing them efficiently, and securely delivering them to individual customer AWS accounts. The architecture is optimized for cost, manageability, scalability, and operational simplicity.

The recommended blueprint follows a "Direct Ingestion, Staged Processing, and Decentralized Delivery" model. At the source, the high-performance log forwarder, **Vector**, is deployed as a DaemonSet within each Kubernetes/OpenShift cluster. Vector agents identify target pods via specific labels (e.g., rosa\_export\_logs), automatically enrich logs with other pod metadata (e.g., customer\_id, cluster\_id), and write them directly to a central **Amazon S3** bucket. This direct-to-S3 approach simplifies the pipeline by removing intermediate services, giving the Vector agent full control over batching, compression, and dynamic object key formatting.

The S3 bucket acts as a temporary staging area for downstream processing, with logs automatically segregated into tenant-specific prefixes based on the metadata provided by Vector. Files are automatically deleted after a configurable retention period (default 7 days) to minimize storage costs. This staging layer serves as a clean, decoupled interface to the final delivery mechanism.

The delivery pipeline is an event-driven, "hub and spoke" workflow. An S3 event notification publishes a message to a central **Amazon SNS topic** whenever a new log file is delivered by Vector. An **Amazon SQS queue**, subscribed to this topic, receives these notifications and triggers a processing component that remains within your AWS account. This processor can be deployed as either:
- **AWS Lambda function** for serverless, auto-scaling processing
- **Kubernetes pod** running in the same cluster as Vector for better cost control in high-volume scenarios

Both deployment options use the same container image and processing logic. The processor reads the tenant-specific log file, securely assumes a specialized **"log distribution" role** in the corresponding customer's AWS account, and delivers the log records to the customer's Amazon CloudWatch Logs service. This end-to-end architecture provides a robust, automated, and cost-optimized solution for large-scale, multi-tenant logging on AWS.

### **1.2. Deconstructing the Core Requirements**

A successful architectural design must be guided by a clear understanding of the primary constraints and objectives. The user query outlines a set of demanding requirements that will serve as the foundational tenets for all subsequent design decisions.

* **Efficiency at the Source:** The system will encompass hundreds of log-producing pods. The logging mechanism must impose minimal CPU and memory overhead on the cluster nodes to avoid impacting application performance.  
* **Cost Optimization at Scale:** With a potential data volume of multiple megabytes per second, the per-gigabyte cost of ingestion, processing, and transfer is a dominant factor. The architecture must prioritize services and configurations that offer the best price-to-performance ratio.  
* **Scalable Multi-Tenancy:** The solution must support hundreds of distinct customer tenants. The architecture must employ patterns that allow for the seamless onboarding of new tenants without requiring significant manual configuration or redeployment of core infrastructure. 1  
* **Multi-Region Operation:** The log producers are replicated across multiple AWS regions. The architecture must be deployable in any AWS region to operate proximate to the data sources, minimizing data transfer latency and costs. 3  
* **Secure Cross-Account Delivery:** The ultimate destination for the logs is each customer's individual AWS account. This necessitates a highly secure and robust mechanism for cross-account data delivery, ensuring strict data isolation and operating on the principle of least privilege. 6  
* **Manageability and Simplicity:** Despite its complexity, the overall system must be manageable by a small operational team. The design should favor managed services where appropriate and leverage the configuration power of the agent to reduce operational burden.

### **1.3. The "Direct Ingestion, Decentralized Delivery" Blueprint**

To satisfy these multifaceted requirements, the proposed architecture is structured as a multi-stage pipeline.

* **Stage 1: Collection and Direct Ingestion (Producers in Your Account):** The **Vector** log collection agent is deployed as a DaemonSet within all Kubernetes/OpenShift clusters. Vector agents are configured to:  
  1. Filter for pods with a specific label (e.g., rosa\_export\_logs=true).  
  2. Extract metadata from other pod labels (customer\_id, cluster\_id, etc.).  
  3. Batch, compress, and write log data directly to a central Amazon S3 bucket, using the extracted metadata to dynamically construct the object key prefix.  
* **Stage 2: Staging & Segregation (Your AWS Account):** The central Amazon S3 bucket acts as a temporary and cost-effective staging area with automatic deletion after 7 days. The dynamic object keys created by Vector automatically organize the incoming logs into a predictable, tenant-segregated prefix structure (e.g., /customer\_id/cluster\_id/...).  
* **Stage 3: Notification and Queuing (Your AWS Account):** The delivery of new log files to the S3 staging bucket triggers an event notification to a central **Amazon SNS topic**. This acts as a "hub" in a hub-and-spoke model. An **Amazon SQS queue** subscribes to this topic, receiving the notifications and placing them in a durable queue that triggers the final processing step. This fan-out pattern allows other downstream systems to also subscribe to new log payload notifications.  
* **Stage 4: Cross-Account Routing and Delivery (Your AWS Account to Customer Account):** An AWS Lambda function (or an array of compute resources) is triggered by messages in the SQS queue. This processing logic, which lives in your account, assumes a specialized **"log distribution" role** in the target customer's AWS account. Using the temporary credentials from this role, the function pushes the log records into the customer's designated Amazon CloudWatch Logs log group, completing the delivery.

## **Section 2: High-Efficiency Log Collection and Ingestion with Vector**

In this simplified and highly efficient architecture, the collection agent, Vector, takes on the dual responsibility of log collection and direct ingestion into the S3 staging area. This approach leverages Vector's powerful configuration capabilities to create a streamlined "first mile" for the data pipeline.

### **2.1. The Optimal Log Agent: Vector**

For this architecture, **Vector** is the recommended agent. It is a modern, high-performance observability data pipeline tool written in Rust. Its efficiency and rich feature set make it ideal for handling log collection, transformation, and delivery directly from Kubernetes and OpenShift environments.

* **High Performance and Low Resource Footprint:** Vector is engineered for efficiency, consuming minimal CPU and memory, which is critical when running as a DaemonSet across many cluster nodes. 9  
* **Native AWS S3 Sink:** Vector includes a robust, highly configurable aws\_s3 sink, allowing it to write data directly to Amazon S3 without intermediate services. This sink supports authentication, batching, compression, and dynamic object key generation. 12  
* **Powerful Transformation Engine:** Vector uses the Vector Remap Language (VRL) for powerful, in-flight data transformation. This is essential for filtering logs based on labels and constructing the precise S3 object paths required for multi-tenant segregation. 13

### **2.2. Agent Configuration for Direct S3 Ingestion**

To effectively implement this model, the Vector configuration must be precisely tuned for filtering, enrichment, and direct S3 delivery.

* **Deployment as a DaemonSet:** Vector is deployed as a DaemonSet in each Kubernetes/OpenShift cluster, ensuring an agent runs on every node to collect logs from all pods.  
* **Filtering and Enrichment Logic:** The Vector configuration uses namespace label selectors and transforms for filtering and enrichment.  
  * **Filtering:** Vector's kubernetes_logs source is configured with `extra_namespace_label_selector: "hypershift.openshift.io/hosted-control-plane=true"` to collect logs only from namespaces with the hosted control plane label. This approach is more efficient than using filter transforms.  
  * **Enrichment:** A remap transform extracts values from pod annotations (e.g., `customer_id`, `cluster_id`, `application`) and the pod name from the Kubernetes metadata that Vector automatically adds to the event. These values are promoted to top-level fields in the log event.  
* **Configuring the aws\_s3 Sink:** The sink is the final step in the Vector agent's pipeline.  
  * **Dynamic key\_prefix:** The sink's key_prefix option uses Vector's template syntax to build the dynamic S3 path from the fields created during the enrichment step:
    ```yaml
    # In vector-config.yaml
    s3:
      type: "aws_s3"
      inputs: ["final_logs"]
      bucket: "${S3_BUCKET_NAME}"
      key_prefix: "{{ customer_id }}/{{ cluster_id }}/{{ application }}/{{ pod_name }}/"
      compression: "gzip"
      encoding:
        codec: "json"
        method: "newline_delimited"
    ```
  * **File Format:** Vector outputs logs in NDJSON format (newline-delimited JSON) but actually writes them as a JSON array on a single line. The log processor handles this format appropriately.
  * **File Naming:** Vector's S3 sink automatically ensures unique file names by appending a timestamp and UUID. Files are compressed with gzip to produce .gz files.
  * **Batching and Compression:** The sink's batching parameters are tuned for cost efficiency with `batch.timeout_secs: 300` and `batch.max_bytes: 10485760` (10MB). This reduces S3 PUT request costs and downstream notifications.
  * **Authentication:** Vector uses IAM role assumption to access S3, configured with `auth.assume_role: "${S3_WRITER_ROLE_ARN}"`

## **Section 3: S3 Staging and the Hub-and-Spoke Delivery Pipeline**

By removing the Kinesis Data Firehose middleware, the architecture becomes more direct. The central S3 bucket and the subsequent event-driven delivery pipeline are now the core components for processing and routing the staged data.

### **3.1. The S3 Staging Area**

The central S3 bucket is the temporary staging area for all log data, with automatic deletion after a configurable period (default 7 days). The object key structure, now created directly by Vector, is the foundation of the multi-tenant segregation. A typical object path would look like:

s3://your-central-logging-bucket/acme-corp/prod-cluster-1/payment-app/pod-xyz-123/1672531200-a1b2c3d4.json.gz

This predictable structure allows the downstream processing logic to easily parse the tenant and cluster information directly from the object key.

### **3.2. The Hub and Spoke Notification Trigger**

The mechanism that initiates the final delivery is a highly decoupled and responsive event-driven pattern designed for flexibility.

1. **S3 Event Notification to SNS:** The trigger is an S3 Event Notification configured on the central logging S3 bucket for the s3:ObjectCreated:\* event type. This event is published to a central **Amazon SNS topic**, which acts as the "hub" of the delivery system.  
2. **SNS to SQS Fan-Out:** An **Amazon SQS queue** is subscribed to this SNS topic. When the SNS topic receives the S3 event notification, it "fans out" the message to all its subscribers, including this SQS queue. The SQS queue serves as a durable buffer for the delivery process.  
3. **Extensibility:** This design allows other downstream systems (e.g., analytics, security monitoring) to simply subscribe their own SQS queues to the same SNS topic to receive notifications about new log payloads without impacting the primary delivery workflow.

### **3.3. The SQS-Triggered Delivery Engine**

An AWS Lambda function, configured with the SQS queue as its event source, serves as the delivery engine. This processing logic lives entirely within your AWS account.

1. **Parse the Event:** The Lambda function is invoked with a batch of messages from the SQS queue. It parses each message to extract the S3 bucket name and object key.  
2. **Extract Tenant Identifier:** The function parses the object key to extract the customer_id from the first path segment.
3. **Assume Cross-Account Role:** The function performs double-hop role assumption:
   - First assumes the central log distribution role without session tags
   - Then uses that role to assume the customer's log distribution role with ExternalId validation
4. **Fetch and Deliver Logs:** The Lambda function:
   - Downloads and decompresses the gzipped file from S3
   - Parses the JSON array format produced by Vector
   - Spawns a Vector subprocess for reliable CloudWatch Logs delivery
   - Streams only the message content (not the full Vector record) to the subprocess
   - Uses log stream naming format: `application-pod_name-date`

### **3.4. The Final Hop: Infrastructure in the Customer Account**

Each customer must deploy a standardized AWS CloudFormation template in their account to create the necessary resources. The key component is the specialized **"log distribution" IAM Role**.

* **Trust Policy:** This policy trusts the ARN of the central log distribution role (not the Lambda execution role directly), implementing proper role chaining:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "CENTRAL-ACCOUNT-ID"
        }
      }
    }]
  }
  ```
* **Permissions Policy:** Grants CloudWatch Logs permissions including:
  - `logs:CreateLogGroup` and `logs:CreateLogStream` for automatic resource creation
  - `logs:PutLogEvents` for log delivery
  - `logs:DescribeLogGroups` on all resources for Vector healthchecks
  - `logs:DescribeLogStreams` on the specific log group

## **Section 4: The Recommended End-to-End Architecture**

This section provides a visual representation and a narrative walkthrough of the complete, re-architected data flow.

### **4.1. Architectural Diagram**

*(A textual description of the diagram is provided below, as visual rendering is not possible.)*

**Title: Multi-Region, Multi-Tenant Logging Architecture (Direct S3 Ingestion)**

The diagram is split into two main sections: **"Your AWS Environment (per Region)"** and **"Customer AWS Environment"**.

**1\. Your AWS Environment (per Region \- e.g., us-east-1)**

* On the far left, an icon representing **"Kubernetes/OpenShift Pods"** with a **"Vector Agent (DaemonSet)"** icon attached.  
* An arrow from the Vector agent points directly to an **"Amazon S3 Bucket (Central Staging)"**.  
  * A note on the arrow indicates: "Direct s3:PutObject with dynamic key prefix".  
  * Inside the S3 bucket icon, a folder structure is depicted: /customer-A/cluster-1/, /customer-B/cluster-2/.  
* The S3 bucket has a trigger icon labeled **"S3 Event Notification"** pointing to an **"Amazon SNS Topic (Log Payloads Hub)"**.  
* The SNS Topic has an arrow fanning out to an **"Amazon SQS Queue (Log Delivery)"**.  
* The SQS Queue has two processing options:
  * **Option A**: Triggers an **"AWS Lambda Function (Log Distributor)"** for serverless processing
  * **Option B**: Polled by a **"Kubernetes Pod (Log Processor)"** running in the same cluster as Vector
* Both processors have a two-way arrow labeled **"sts:AssumeRole"** pointing towards the boundary of "Your AWS Environment".

**2\. Customer AWS Environment (e.g., eu-west-1)**

* At the boundary, an icon for a **"Log Distribution IAM Role"** is shown.  
  * Trust Policy: "Trusts Your Log Distributor Lambda ARN".  
  * Permissions Policy: "logs:PutLogEvents on specific Log Group".  
* The sts:AssumeRole arrow from the Lambda function points to this IAM Role.  
* An arrow from the IAM Role points to **"Amazon CloudWatch Logs"**.

### **4.2. Narrative Data Flow (Step-by-Step)**

1. **Generation & Filtering:** A log is generated in a pod labeled with rosa\_export\_logs: "true", customer\_id: "acme-corp", and cluster\_id: "prod-cluster-1".  
2. **Collection & Direct Ingestion:** The Vector agent on the node collects the log. Its configuration validates the rosa\_export\_logs label, enriches the event with the other labels, and after batching and compressing, writes the data directly to S3 with the object key acme-corp/prod-cluster-1/.../\<ts\>-\<uuid\>.json.gz.  
3. **Notification (Hub):** The creation of the S3 object triggers an event notification to the central SNS topic.  
4. **Queuing (Spoke):** The SNS topic fans out the notification to the SQS queue for log delivery.  
5. **Invocation & Routing:** The Log Distributor Lambda is triggered by the SQS message. It parses the object key to identify the tenant as "acme-corp".  
6. **Application Filtering (Optional):** The processor checks the tenant's configuration for an optional `desired_logs` field. If present, it verifies that the application from the S3 object key is in the allowed list. If not in the list, processing is skipped for cost optimization.
7. **Cross-Account Delivery:** The Lambda assumes the "log distribution" role in the acme-corp account, reads the log file from S3, and pushes the events to the customer's CloudWatch Logs.

### **4.3. Application-Level Log Filtering**

The log processor supports optional application-level filtering through the `desired_logs` configuration field in the tenant's DynamoDB record. This feature allows tenants to specify exactly which applications they want to receive logs for, reducing processing costs and noise while maintaining backward compatibility.

#### **Configuration Schema**

Tenants can optionally include a `desired_logs` field in their DynamoDB configuration record:

```json
{
  "tenant_id": "acme-corp",
  "log_distribution_role_arn": "arn:aws:iam::123456789012:role/LogDistributionRole",
  "log_group_name": "/aws/logs/acme-corp",
  "target_region": "us-east-1",
  "desired_logs": ["payment-service", "user-service", "api-gateway"]
}
```

#### **Filtering Behavior**

The filtering logic operates as follows:

* **No `desired_logs` field**: All application logs are processed (full backward compatibility)
* **`desired_logs` present**: Only applications listed in the array are processed
* **Case-insensitive matching**: Application names are matched without regard to case for robustness
* **Early filtering**: Filtering occurs before expensive S3 download operations, minimizing processing costs

#### **Processing Examples**

Given the configuration above with `desired_logs: ["payment-service", "user-service", "api-gateway"]`:

* **S3 Object**: `acme-corp/prod-cluster-1/payment-service/pod-123/20240101-abc.json.gz`  
  **Result**: ✅ **PROCESSED** (payment-service is in desired_logs)

* **S3 Object**: `acme-corp/prod-cluster-1/logging-service/pod-456/20240101-def.json.gz`  
  **Result**: ❌ **FILTERED** (logging-service is not in desired_logs)

* **S3 Object**: `acme-corp/prod-cluster-1/API-Gateway/pod-789/20240101-ghi.json.gz`  
  **Result**: ✅ **PROCESSED** (API-Gateway matches api-gateway case-insensitively)

#### **Cost Benefits**

Application filtering provides significant cost optimization:

* **Reduced S3 Operations**: Filtered applications skip expensive S3 downloads entirely
* **Lower Processing Costs**: Fewer Lambda invocations and shorter execution times
* **Minimized Data Transfer**: Only relevant logs are transferred cross-account
* **Reduced CloudWatch Costs**: Fewer log events sent to customer accounts

#### **Operational Advantages**

* **Noise Reduction**: Customers receive only the logs they actually need
* **Compliance Support**: Easier to maintain data governance by excluding sensitive applications
* **Incremental Adoption**: Customers can start with all logs, then gradually refine their desired_logs list
* **Debugging Capability**: Clear logging indicates which applications are processed vs. filtered

## **Section 5: Security, Operations, and Cost**

### **5.1. A Scalable Security Model**

The security model remains robust. The primary change is in the permissions required by the log producers.

* **Vector Agent Permissions:** The IAM role associated with the Kubernetes/OpenShift node instance profiles must now have s3:PutObject permissions on the central logging S3 bucket, restricted to the appropriate prefixes if possible. This replaces the previous firehose:PutRecordBatch permission.  
* **Cross-Account Security:** The downstream delivery security model, which uses a customer-deployed **"log distribution" role** and can be enhanced with **Attribute-Based Access Control (ABAC)**, is unaffected and remains the best practice for scalable, secure cross-account access. 2

### **5.2. Operational Excellence**

* **Monitoring:** Monitoring shifts from Kinesis Data Firehose to the Vector agents themselves. It is critical to monitor Vector's logs and internal metrics for S3 sink errors, buffer capacity, and event throughput to ensure the health of the ingestion pipeline. Monitoring for S3, SNS, SQS, and Lambda remains the same.  
* **Error Handling:** Vector's S3 sink has a built-in retry mechanism for transient S3 API errors. 12 However, unlike Firehose, it does not have a native dead-letter bucket for failed batches. Batches that fail after all retries are exhausted will be dropped. Therefore, it is crucial to have alarms on Vector's error metrics to detect and address persistent delivery failures. The Dead-Letter Queue (DLQ) on the downstream Lambda function remains essential for handling "poison pill" files or failures in the final delivery step. 19

### **5.3. Cost Optimization**

* **Primary Cost Levers:** With the removal of Kinesis Data Firehose, the primary cost components are now Vector's compute overhead (which is minimal), S3 storage and requests, and the Lambda delivery function.  
* **Application-Level Filtering:** The optional `desired_logs` configuration provides significant cost optimization by filtering applications before expensive S3 downloads and processing. This reduces Lambda execution time, S3 operations, and cross-account data transfer costs.
* **Batching is Critical:** The most important cost optimization lever is now the **batching configuration within Vector's S3 sink**. Configuring a large buffer size (batch.max\_bytes) and a long buffer interval (batch.timeout\_secs) is essential. This strategy creates larger files in S3, which drastically reduces the number of S3 PUT requests and the corresponding downstream SNS/SQS/Lambda invocations, leading to significant cost savings. 23  
* **Storage Cost Management:** This architecture uses S3 as a temporary staging area rather than long-term storage. With automatic deletion after 7 days and Vector's efficient GZIP compression (achieving ~30-35:1 compression ratios), storage costs are minimal. The simplicity of the direct-to-S3 approach outweighs the loss of Parquet conversion capability from Kinesis Data Firehose. 16

## **Section 6: CloudFormation Implementation and Recent Architectural Improvements**

### **6.1. Infrastructure as Code Implementation**

The multi-tenant logging architecture has been fully implemented using AWS CloudFormation with a regional deployment model, providing a complete Infrastructure as Code (IaC) solution. The implementation is organized into four deployment types that support multi-region, scalable infrastructure:

#### **Regional Deployment Architecture**

The CloudFormation infrastructure is organized into separate deployment types that can be deployed independently:

* **Global Templates** (`global/`): One-time deployment creating central cross-account IAM role
  * `central-log-distribution-role.yaml`: Creates the central log distribution role for cross-account access
* **Regional Templates** (`regional/`): Per-region infrastructure deployment
  * `main.yaml`: Orchestrates regional deployment with parameter management and conditional stack inclusion
  * `core-infrastructure.yaml`: Deploys foundational resources including S3, DynamoDB, KMS, IAM roles, and native S3 event notifications
  * `sqs-stack.yaml`: Optional SQS queue infrastructure for message processing
  * `lambda-stack.yaml`: Optional container-based Lambda functions using ECR images for log processing
* **Customer Templates** (`customer/`): Customer-deployed roles for cross-account log delivery
  * `customer-log-distribution-role.yaml`: Creates customer-side IAM role with regional naming
* **Cluster Templates** (`cluster/`): Cluster-specific IAM roles for IRSA integration
  * `cluster-vector-role.yaml`: Vector IAM role for log collection
  * `cluster-processor-role.yaml`: Processor IAM role for log processing

This modular structure enables independent deployment, regional scaling, and flexible processing options while maintaining security and operational simplicity.

### **6.1.1. Modular Deployment Architecture**

The CloudFormation implementation supports four deployment types with multiple configuration options:

#### **Global Deployment (One-time)**
```bash
./cloudformation/deploy.sh -t global
```
Deploys the central log distribution role that enables cross-account access across all regions. This must be deployed first and only once per AWS account.

#### **Regional Core Infrastructure**
```bash
./cloudformation/deploy.sh -t regional -b templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234
```
Deploys S3, DynamoDB, SNS, and IAM resources in a specific region. Suitable for external log processing systems.

#### **Regional + SQS Processing**
```bash
./cloudformation/deploy.sh -t regional -b templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs
```
Adds SQS queue and DLQ for message buffering. Enables external applications to poll for log processing events.

#### **Full Regional Container-Based Processing**
```bash
./cloudformation/deploy.sh -t regional -b templates-bucket \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234 \
  --include-sqs --include-lambda \
  --ecr-image-uri AWS_ACCOUNT_ID.dkr.ecr.YOUR_AWS_REGION.amazonaws.com/log-processor:latest
```
Complete serverless processing using container-based Lambda functions with ECR image deployment.

#### **Customer Role Deployment**
```bash
./cloudformation/deploy.sh -t customer \
  --central-role-arn arn:aws:iam::123456789012:role/ROSA-CentralLogDistributionRole-abcd1234
```
Customers deploy this in their AWS accounts to enable log delivery. Role names include the region for proper isolation.

#### **Cluster IRSA Role Deployment**
```bash
./cloudformation/deploy.sh -t cluster \
  --cluster-name my-cluster \
  --oidc-provider oidc.op1.openshiftapps.com/abc123
```
Deploys cluster-specific IAM roles for Vector and processor service accounts using IRSA.

### **6.1.2. Regional Deployment Architecture and Dependencies**

The regional deployment model implements a hierarchical infrastructure pattern that supports multi-region scalability while maintaining security and operational simplicity:

#### **Deployment Hierarchy**

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Global    │    │  Regional   │    │  Customer   │    │  Cluster    │
│             │    │             │    │             │    │             │
│ Central IAM │───▶│Core Infra-  │───▶│Cross-Account│    │Cluster IAM  │
│ Role        │    │structure    │    │Roles        │    │Roles (IRSA) │
│             │    │S3, DynamoDB │    │             │    │             │
│(Deploy Once │    │SNS, Optional│    │(Per Customer│    │(Per Cluster)│
│   Global)   │    │SQS, Lambda) │    │   Region)   │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

#### **Deployment Dependencies and Order**

1. **Global Deployment** (Prerequisites: None)
   - Creates central log distribution role: `ROSA-CentralLogDistributionRole-{suffix}`
   - Enables cross-account access to customer roles globally
   - **Stack Name**: `multi-tenant-logging-global`
   - **Deployed Once**: Per AWS account (not per region)

2. **Regional Deployment** (Prerequisites: Global role ARN)
   - Creates regional infrastructure: S3, DynamoDB, SNS, optional SQS/Lambda
   - References global role ARN via parameter
   - **Stack Name**: `multi-tenant-logging-{environment}-{region}`
   - **Deployed Per**: Target region

3. **Customer Deployment** (Prerequisites: Global role ARN)
   - Creates customer-side role with regional naming: `CustomerLogDistribution-{region}`
   - Trusts global central role with ExternalId validation
   - **Stack Name**: `multi-tenant-logging-customer-{region}`
   - **Deployed Per**: Customer account, per region

4. **Cluster Deployment** (Prerequisites: OIDC provider setup)
   - Creates IRSA roles for Vector and processor service accounts
   - Integrates with regional infrastructure via role ARNs
   - **Stack Name**: `multi-tenant-logging-cluster-{cluster-name}`
   - **Deployed Per**: Kubernetes/OpenShift cluster

#### **Cross-Account Security Model**

The regional architecture maintains a secure double-hop role assumption pattern:

```
Regional Processor → Global Central Role → Customer Regional Role → CloudWatch Logs
```

**Security Features**:
- **ExternalId Validation**: Prevents confused deputy attacks
- **Regional Isolation**: Customer roles scoped to specific regions
- **Least Privilege**: Minimal permissions with resource-specific restrictions
- **Audit Trail**: All role assumptions logged via CloudTrail

#### **Regional Scaling Benefits**

- **Independent Regional Operation**: Each region operates independently
- **Regional Fault Isolation**: Issues in one region don't affect others
- **Cost Optimization**: Resources deployed only where needed
- **Compliance**: Supports data residency requirements per region
- **Gradual Rollout**: New regions can be added incrementally

#### **Stack Naming Conventions**

The regional model uses consistent, predictable stack naming:

| Deployment Type | Stack Name Pattern | Example |
|----------------|-------------------|---------|
| Global | `{project}-global` | `multi-tenant-logging-global` |
| Regional | `{project}-{env}-{region}` | `multi-tenant-logging-production-us-east-2` |
| Customer | `{project}-customer-{region}` | `multi-tenant-logging-customer-us-east-2` |
| Cluster | `{project}-cluster-{cluster}` | `multi-tenant-logging-cluster-my-cluster` |

### **6.1.3. Container-Based Lambda Architecture**

The log processing component has been redesigned as a unified, container-based solution that supports multiple execution modes:

#### **Unified Log Processor**
The core processing logic is implemented in a single Python script (`container/log_processor.py`) that supports three execution modes with optional application-level filtering:

* **Lambda Runtime Mode** (`EXECUTION_MODE=lambda`): Handles AWS Lambda events for serverless processing
* **SQS Polling Mode** (`EXECUTION_MODE=sqs`): Continuously polls SQS queue for external processing scenarios  
* **Manual Input Mode** (`EXECUTION_MODE=manual`): Accepts JSON input via stdin for development and testing
* **Application Filtering**: Optional `desired_logs` configuration in tenant DynamoDB records enables selective log processing for cost optimization

#### **Container Architecture**
```dockerfile
# Fedora 42 base with Python 3.13
FROM registry.fedoraproject.org/fedora:42
WORKDIR /app
COPY requirements.txt log_processor.py entrypoint.sh ./
RUN pip3 install -r requirements.txt && chmod +x entrypoint.sh
USER logprocessor
ENTRYPOINT ["/app/entrypoint.sh"]
```

#### **Multi-Mode Entrypoint**
The container entrypoint (`container/entrypoint.sh`) dynamically selects execution mode based on the `EXECUTION_MODE` environment variable:

```bash
case "$EXECUTION_MODE" in
    "lambda")  exec python3 -m awslambdaric log_processor.lambda_handler ;;
    "sqs")     exec python3 log_processor.py --mode sqs ;;
    "manual")  exec python3 log_processor.py --mode manual ;;
esac
```

#### **ECR Integration**
Container images are stored in Amazon Elastic Container Registry (ECR) and deployed to Lambda:

```bash
# Build and push to ECR
podman build -f Containerfile -t log-processor:latest .
aws ecr get-login-password | podman login --username AWS --password-stdin ECR_URI
podman tag log-processor:latest ECR_URI/log-processor:latest
podman push ECR_URI/log-processor:latest

# Deploy with CloudFormation
./deploy.sh --include-lambda --ecr-image-uri ECR_URI/log-processor:latest
```

#### **Benefits of Container-Based Approach**
* **Consistency**: Same codebase runs in Lambda, local development, and external processing
* **Flexibility**: Support for multiple execution patterns without code duplication
* **Development**: Full local testing capabilities with podman
* **Maintenance**: Single container image for all deployment scenarios
* **Scalability**: Container-based Lambda provides better cold start performance and resource management

### **6.2. Major Architectural Improvements (2025)**

During the CloudFormation implementation, several significant architectural improvements were made that enhance the system's simplicity, maintainability, and adherence to AWS best practices:

#### **6.2.1. Native S3 Event Notifications**

**Problem Solved:** The initial implementation used custom Lambda functions to configure S3 bucket notifications, creating complex circular dependencies between resources.

**Solution Implemented:** 
- Replaced custom `S3NotificationFunction` with native `AWS::S3::Bucket NotificationConfiguration`
- Eliminated circular dependencies by using deterministic bucket naming with external parameter generation
- Random suffix generation moved from CloudFormation custom resource to deploy script parameter

**Benefits:**
- Reduced infrastructure complexity (eliminated 159 lines of custom Lambda code)
- Improved reliability using AWS native capabilities
- Better CloudFormation best practices compliance
- Simplified troubleshooting and maintenance

#### **6.2.2. Simplified Resource Management**

**Improvements Made:**
- **Deterministic Resource Naming:** Random suffixes generated in deployment script and passed as parameters
- **Pure CloudFormation Resources:** Eliminated custom resource dependencies
- **Streamlined IAM:** Reduced IAM roles from 5 to 3 by removing custom function roles

**Technical Implementation:**
```yaml
# Native S3 notification configuration
NotificationConfiguration:
  TopicConfigurations:
    - Topic: !Ref LogDeliveryTopic
      Event: s3:ObjectCreated:*
      Filter:
        S3Key:
          Rules:
            - Name: Suffix
              Value: .gz
```

#### **6.2.3. Enhanced Deployment Experience**

**Deploy Script Improvements:**
- Automatic random suffix generation for unique resource names
- Comprehensive template validation
- Parallel template uploading for faster deployments
- Better error handling and user feedback
- Support for dry-run and validation-only modes

### **6.3. Cost Optimization Enhancements**

The CloudFormation implementation includes several cost optimization features:

* **S3 Lifecycle Policy:** Simple deletion rule after N days (default 7) minimizes storage costs for temporary staging
* **Lambda Batch Processing:** SQS batch processing reduces Lambda invocations
* **Direct S3 Writes:** Elimination of Kinesis Data Firehose saves ~$50/TB in data processing costs
* **GZIP Compression:** Vector's compression achieves ~30-35:1 ratios, significantly reducing storage and transfer costs

### **6.4. Security Model Implementation**

**Multi-Layer Security:**
- **Encryption at Rest:** KMS encryption for S3, DynamoDB, and other services
- **ABAC Cross-Account Access:** Attribute-Based Access Control for tenant isolation
- **Least Privilege IAM:** Minimal permissions with resource-specific restrictions
- **Session Tagging:** Dynamic session tags for tenant identification and access control

**Example ABAC Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CENTRAL-ACCOUNT:role/ROSA-CentralLogDistributionRole-XXXXXXXX"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### **6.5. Production Readiness Features**

**Operational Excellence:**
- **Error Handling:** Dead letter queues and retry mechanisms
- **Scalability:** Auto-scaling Lambda concurrency and SQS queue management
- **Observability:** CloudWatch Logs integration and resource tagging
- **Disaster Recovery:** Cross-region deployment support with infrastructure templates

**Deployment Validation:**
- All templates validated against AWS CloudFormation standards
- End-to-end testing confirmed for S3 → SNS → SQS → Lambda pipeline
- Successfully deployed and tested on AWS account with full functionality

### **6.6. Local Development and Testing**

The container-based architecture enables comprehensive local development and testing capabilities:

#### **Local Development Environment Setup**
```bash
# Install dependencies
cd container/
pip3 install --user -r requirements.txt

# Set environment variables  
export AWS_PROFILE=YOUR_AWS_PROFILE
export AWS_REGION=YOUR_AWS_REGION
export TENANT_CONFIG_TABLE=multi-tenant-logging-development-tenant-configs
export CENTRAL_LOG_DISTRIBUTION_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/role-name
export SQS_QUEUE_URL=https://sqs.YOUR_AWS_REGION.amazonaws.com/AWS_ACCOUNT_ID/queue-name
```

#### **Testing Execution Modes**

**Direct Python Execution:**
```bash
# SQS polling mode
python3 log_processor.py --mode sqs

# Manual testing with sample S3 event
echo '{"Message": "{\"Records\": [...]}"}' | python3 log_processor.py --mode manual
```

**Container Testing:**
```bash
# Build container
podman build -f Containerfile -t log-processor:latest .

# Test with AWS credentials
podman run --rm \
  -e AWS_PROFILE=YOUR_AWS_PROFILE \
  -e EXECUTION_MODE=sqs \
  -v ~/.aws:/home/logprocessor/.aws:ro \
  log-processor:latest

# Test with environment variables
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile YOUR_AWS_PROFILE)
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile YOUR_AWS_PROFILE)
podman run --rm \
  -e AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  -e AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  -e EXECUTION_MODE=manual \
  log-processor:latest
```

### **6.7. Kubernetes Deployment with Kustomize**

The Vector deployment on Kubernetes/OpenShift uses Kustomize for flexible, environment-specific configurations:

#### **Kustomize Structure**
```
k8s/
├── collector/          # Vector log collector (DaemonSet)
│   ├── base/          # Base Kubernetes resources
│   ├── openshift-base/# OpenShift-specific (includes SCC)
│   └── overlays/      # Environment-specific patches
│       ├── development/
│       └── production/
└── processor/          # Log processor (Deployment)
    ├── base/          # Base Kubernetes resources
    ├── openshift-base/# OpenShift-specific (includes SCC)
    └── overlays/      # Environment-specific patches
        ├── development/
        └── production/
```

#### **Deployment Commands**
```bash
# Deploy Vector collector to development (uses base configuration)
kubectl apply -k k8s/collector/base/

# Deploy Vector collector to production (applies production overlays)
kubectl apply -k k8s/collector/overlays/production/

# Deploy log processor to development
kubectl apply -k k8s/processor/base/

# Deploy log processor to production
kubectl apply -k k8s/processor/overlays/production/

# Preview changes before applying
kubectl kustomize k8s/collector/base/
kubectl kustomize k8s/processor/base/
```

### **6.8. Complete Deployment Workflow**

#### **Regional Deployment Workflow**

The regional deployment model requires a specific deployment order to establish proper dependencies:

1. **Deploy Global Infrastructure (One-time):**
   ```bash
   cd cloudformation/
   # Deploy central log distribution role (one-time per AWS account)
   ./deploy.sh -t global
   
   # Capture the role ARN for regional deployments
   CENTRAL_ROLE_ARN=$(aws cloudformation describe-stacks \
     --stack-name multi-tenant-logging-global \
     --query 'Stacks[0].Outputs[?OutputKey==`CentralLogDistributionRoleArn`].OutputValue' \
     --output text)
   ```

2. **Build and Push Containers (if using Lambda processing):**
   ```bash
   cd container/
   # Build collector container first (contains Vector)
   podman build -f Containerfile.collector -t log-collector:latest .
   # Build processor container (includes Vector from collector)
   podman build -f Containerfile.processor -t log-processor:latest .
   
   # Push to ECR
   aws ecr get-login-password --region YOUR_REGION | podman login --username AWS --password-stdin ECR_URI
   podman tag log-processor:latest ECR_URI/log-processor:latest
   podman push ECR_URI/log-processor:latest
   ```

3. **Deploy Regional Infrastructure:**
   ```bash
   cd cloudformation/
   # Deploy core + SQS + Lambda processing
   ./deploy.sh -t regional -b templates-bucket \
     --central-role-arn $CENTRAL_ROLE_ARN \
     --include-sqs --include-lambda \
     --ecr-image-uri ECR_URI/log-processor:latest
   ```

4. **Customer Role Deployment (customers deploy in their accounts):**
   ```bash
   # Customers deploy this in their AWS accounts
   ./deploy.sh -t customer --central-role-arn $CENTRAL_ROLE_ARN
   
   # Customers provide their role ARN back to logging service provider
   CUSTOMER_ROLE_ARN=$(aws cloudformation describe-stacks \
     --stack-name multi-tenant-logging-customer-us-east-2 \
     --query 'Stacks[0].Outputs[?OutputKey==`CustomerLogDistributionRoleArn`].OutputValue' \
     --output text)
   ```

5. **Cluster IAM Role Deployment (optional, for IRSA):**
   ```bash
   # Deploy Vector role for specific cluster
   ./deploy.sh -t cluster \
     --cluster-name my-cluster \
     --oidc-provider oidc.op1.openshiftapps.com/abc123
   ```

6. **Deploy Vector with Kustomize:**
   ```bash
   # For development/testing
   kubectl apply -k k8s/collector/base/
   
   # For production with custom settings
   kubectl apply -k k8s/collector/overlays/production/
   
   # Verify deployment
   kubectl get pods -n logging
   kubectl logs -n logging daemonset/vector-logs
   ```

#### **Multi-Region Deployment**
For multi-region deployments, repeat steps 3-6 for each target region:

```bash
# Deploy to multiple regions
for region in us-east-2 us-west-2 eu-west-1; do
  # Deploy regional infrastructure
  ./deploy.sh -t regional -r $region -b templates-bucket-$region \
    --central-role-arn $CENTRAL_ROLE_ARN \
    --include-sqs --include-lambda \
    --ecr-image-uri $region.amazonaws.com/ECR_URI/log-processor:latest
  
  # Customers deploy regional roles in their accounts
  ./deploy.sh -t customer -r $region --central-role-arn $CENTRAL_ROLE_ARN
done
```

#### **Environment-Specific Deployments**
```bash
# Development
./deploy.sh -t regional -e development -b templates-bucket \
  --central-role-arn $CENTRAL_ROLE_ARN --include-sqs

# Staging with full Lambda processing
./deploy.sh -t regional -e staging -b templates-bucket \
  --central-role-arn $CENTRAL_ROLE_ARN --include-sqs --include-lambda \
  --ecr-image-uri ECR_URI/log-processor:latest

# Production with enhanced monitoring
./deploy.sh -t regional -e production -b templates-bucket \
  --central-role-arn $CENTRAL_ROLE_ARN --include-sqs --include-lambda \
  --ecr-image-uri ECR_URI/log-processor:latest
```

### **6.9. Log Processing Architecture Details**

#### **Vector Output Format**
Vector produces compressed files containing a JSON array on a single line:
```json
[{"timestamp":"2024-01-01T00:00:00Z","message":"Log line 1","customer_id":"acme","cluster_id":"prod-1"},{"timestamp":"2024-01-01T00:00:01Z","message":"Log line 2","customer_id":"acme","cluster_id":"prod-1"}]
```

#### **Lambda Processing Flow**
1. **S3 Event Processing**: Lambda receives S3 event notifications via SQS
2. **File Download**: Downloads and decompresses the .gz file
3. **JSON Parsing**: Handles Vector's single-line JSON array format
4. **Message Extraction**: Extracts only the `message` field from each log record
5. **Vector Subprocess**: Spawns Vector with temporary config for CloudWatch delivery
6. **Error Handling**: Returns `batchItemFailures` for proper SQS retry behavior

#### **CloudWatch Logs Integration**
- **Log Groups**: Created automatically if they don't exist
- **Log Streams**: Named as `application-pod_name-date` for easy identification
- **Message Format**: Only the log message content is sent, without Vector metadata
- **Permissions**: Customer roles must include `logs:DescribeLogGroups` for Vector healthchecks

### **6.10. Kubernetes-Based Processing Architecture**

#### **6.10.1. Alternative to Lambda: Kubernetes Deployment**

While the Lambda-based processing works well for serverless scenarios, a Kubernetes-based deployment option has been implemented to provide better control and potentially lower costs for high-volume environments:

**Architecture Components:**
- **Log Processor Deployment**: Single-replica Kubernetes Deployment running the same container image
- **SQS Polling Mode**: Processor runs in `EXECUTION_MODE=sqs` to continuously poll the SQS queue
- **IRSA Integration**: Uses IAM Roles for Service Accounts for secure AWS access
- **OpenShift Support**: Includes SecurityContextConstraints for OpenShift deployments

**Key Benefits:**
- **Cost Optimization**: Eliminates Lambda invocation costs for high-volume processing
- **Better Control**: Direct management of processing resources and scaling
- **Unified Codebase**: Same container image works for both Lambda and Kubernetes
- **Local Development**: Easier debugging and testing in Kubernetes environments

**Deployment Structure:**
```
k8s/
├── collector/          # Vector log collector (DaemonSet)
│   ├── base/          # Base Kubernetes resources
│   ├── openshift-base/# OpenShift-specific (includes SCC)
│   └── overlays/      # Environment-specific patches
└── processor/          # Log processor (Deployment)
    ├── base/          # Base Kubernetes resources
    ├── openshift-base/# OpenShift-specific (includes SCC)
    └── overlays/      # Environment-specific patches
```

#### **6.10.2. Vector Performance Observations**

During implementation, several important findings about Vector's behavior were documented:

**Compression Performance:**
- Vector's GZIP compression is working correctly with excellent ratios (~30-35:1)
- Example: 5.6MB uncompressed logs → 156KB compressed

**Batching Limitations:**
- Vector's S3 sink has known issues where batch settings (`max_bytes`, `timeout_secs`) are not strictly honored
- Files are typically created every 2-3 minutes regardless of configured settings
- This is a well-documented issue in the Vector community with no current workaround
- While this increases S3 PUT requests, the compression efficiency partially offsets the cost impact

**Health Check Considerations:**
- The minimal container images lack common utilities like `ps`
- Health checks were adapted to use `/proc/1/cmdline` for process verification

### **6.11. S3 Lifecycle Management Update**

**Recent Enhancement (July 2025):**
The S3 lifecycle configuration has been simplified to align with the temporary staging nature of the bucket:

- **Previous Configuration:** Complex lifecycle rules with transitions to Standard-IA (30 days), Glacier (90 days), Deep Archive (365 days), and eventual deletion (2555 days)
- **New Configuration:** Single deletion rule after N days (configurable, default 7 days)
- **Rationale:** Since logs are delivered to customer accounts immediately after staging, long-term storage in the central bucket is unnecessary. The simplified lifecycle reduces complexity and storage costs.
- **Parameter:** `S3DeleteAfterDays` in CloudFormation allows customization of the retention period

This change reflects the true purpose of the S3 bucket as a temporary staging area for the delivery pipeline, not a long-term archive.

### **6.12. Future Considerations**

**Potential Enhancements:**
- **Multi-Region Replication:** S3 Cross-Region Replication for disaster recovery
- **Advanced Analytics:** Integration with AWS Glue for log analytics capabilities
- **Cost Monitoring:** Enhanced cost allocation tagging and budgeting
- **Security Scanning:** Automated security compliance checking
- **Container Optimization:** Multi-stage builds and smaller base images for faster Lambda cold starts
- **Batch Processing:** Enhanced batch processing for high-volume scenarios

The CloudFormation implementation provides a robust, scalable, and maintainable foundation for the multi-tenant logging architecture, significantly improving upon the original design through the use of native AWS capabilities, container-based processing, and comprehensive Infrastructure as Code best practices.

## **Section 7: Implementation Documentation and Resources**

### **7.1. Comprehensive Documentation Structure**

The regional deployment model includes comprehensive documentation organized by deployment type:

#### **Main Architecture Documentation**
- **[CloudFormation Overview](cloudformation/README.md)** - Complete architecture overview, quick start guide, and deployment patterns
- **[Development Guide](CLAUDE.md)** - Development commands, container management, and testing procedures

#### **Deployment-Specific Documentation**
- **[Global Deployment Guide](cloudformation/global/README.md)** - Central log distribution role deployment and management
- **[Regional Deployment Guide](cloudformation/regional/README.md)** - Core infrastructure, processing options, and regional architecture
- **[Customer Deployment Guide](cloudformation/customer/README.md)** - Customer-side role configuration and cross-account setup
- **[Cluster Deployment Guide](cloudformation/cluster/README.md)** - IRSA setup, cluster integration, and service account configuration

#### **Implementation Resources**
- **[Container Documentation](container/README.md)** - Container builds, ECR deployment, and multi-mode execution
- **[Kubernetes Manifests](k8s/README.md)** - Vector and processor deployment with Kustomize

### **7.2. Getting Started Workflow**

For new implementations, follow this workflow using the comprehensive documentation:

1. **Architecture Understanding**: Start with [CloudFormation Overview](cloudformation/README.md) for complete architecture understanding
2. **Global Setup**: Follow [Global Deployment Guide](cloudformation/global/README.md) for one-time central role creation
3. **Regional Infrastructure**: Use [Regional Deployment Guide](cloudformation/regional/README.md) for per-region infrastructure
4. **Customer Onboarding**: Direct customers to [Customer Deployment Guide](cloudformation/customer/README.md)
5. **Cluster Integration**: Reference [Cluster Deployment Guide](cloudformation/cluster/README.md) for IRSA setup
6. **Development**: Use [Development Guide](CLAUDE.md) for local development and testing

### **7.3. Support and Troubleshooting**

Each deployment guide includes:
- **Prerequisites and validation steps**
- **Common issues and solutions**
- **Debugging commands and techniques**
- **Cross-references to related documentation**
- **Integration examples and workflows**

For comprehensive troubleshooting across all deployment types, refer to the deployment-specific README files which include detailed troubleshooting sections and debugging procedures.

#### **Works cited**

1. Design patterns for multi-tenant access control on Amazon S3 | AWS Storage Blog, accessed July 17, 2025, [https://aws.amazon.com/blogs/storage/design-patterns-for-multi-tenant-access-control-on-amazon-s3/](https://aws.amazon.com/blogs/storage/design-patterns-for-multi-tenant-access-control-on-amazon-s3/)  
2. How to implement SaaS tenant isolation with ABAC and AWS IAM ..., accessed July 17, 2025, [https://aws.amazon.com/blogs/security/how-to-implement-saas-tenant-isolation-with-abac-and-aws-iam/](https://aws.amazon.com/blogs/security/how-to-implement-saas-tenant-isolation-with-abac-and-aws-iam/)  
3. Architecture guidelines and decisions \- General SAP Guides \- AWS Documentation, accessed July 17, 2025, [https://docs.aws.amazon.com/sap/latest/general/arch-guide-architecture-guidelines-and-decisions.html](https://docs.aws.amazon.com/sap/latest/general/arch-guide-architecture-guidelines-and-decisions.html)  
4. How to Master Multi Region Architectures in AWS \- \- SUDO Consultants, accessed July 17, 2025, [https://sudoconsultants.com/how-to-master-multi-region-architectures-in-aws/](https://sudoconsultants.com/how-to-master-multi-region-architectures-in-aws/)  
5. Creating a Multi-Region Application with AWS Services – Part 1, Compute, Networking, and Security | AWS Architecture Blog, accessed July 17, 2025, [https://aws.amazon.com/blogs/architecture/creating-a-multi-region-application-with-aws-services-part-1-compute-and-security/](https://aws.amazon.com/blogs/architecture/creating-a-multi-region-application-with-aws-services-part-1-compute-and-security/)  
6. IAM roles for cross account delivery \- Amazon Virtual Private Cloud \- AWS Documentation, accessed July 17, 2025, [https://docs.aws.amazon.com/vpc/latest/userguide/firehose-cross-account-delivery.html](https://docs.aws.amazon.com/vpc/latest/userguide/firehose-cross-account-delivery.html)  
7. Allow cross-account users to access your resources through IAM | AWS re:Post, accessed July 17, 2025, [https://repost.aws/knowledge-center/cross-account-access-iam](https://repost.aws/knowledge-center/cross-account-access-iam)  
8. Provide cross-account access to objects in Amazon S3 buckets | AWS re:Post, accessed July 17, 2025, [https://repost.aws/knowledge-center/cross-account-access-s3](https://repost.aws/knowledge-center/cross-account-access-s3)  
9. FluentD vs FluentBit \- Choosing the Right Log Collector | SigNoz, accessed July 17, 2025, [https://signoz.io/blog/fluentd-vs-fluentbit/](https://signoz.io/blog/fluentd-vs-fluentbit/)  
10. Fluentd and Fluent Bit | Fluent Bit: Official Manual, accessed July 17, 2025, [https://docs.fluentbit.io/manual/about/fluentd-and-fluent-bit](https://docs.fluentbit.io/manual/about/fluentd-and-fluent-bit)  
11. The Battle of Logs: Logstash vs. Fluentd vs. Fluent Bit | by Sugam Arora \- Medium, accessed July 17, 2025, [https://medium.com/@sugam.arora23/the-battle-of-logs-logstash-vs-fluentd-vs-fluent-bit-921f567a5abd](https://medium.com/@sugam.arora23/the-battle-of-logs-logstash-vs-fluentd-vs-fluent-bit-921f567a5abd)  
12. AWS S3 | Vector documentation, accessed July 18, 2025, [https://vector.dev/docs/reference/configuration/sinks/aws\_s3/](https://vector.dev/docs/reference/configuration/sinks/aws_s3/)  
13. How to Collect, Process, and Ship Log Data with Vector | Better Stack Community, accessed July 18, 2025, [https://betterstack.com/community/guides/logging/vector-explained/](https://betterstack.com/community/guides/logging/vector-explained/)  
14. Template syntax | Vector documentation, accessed July 18, 2025, [https://vector.dev/docs/reference/configuration/template-syntax/](https://vector.dev/docs/reference/configuration/template-syntax/)  
15. Introducing Buffer and Rate Limits in Vector — Handling Traffic Spikes \- DevOps.dev, accessed July 18, 2025, [https://blog.devops.dev/introducing-buffer-and-rate-limits-in-vector-handling-traffic-spikes-ff5dc8025359](https://blog.devops.dev/introducing-buffer-and-rate-limits-in-vector-handling-traffic-spikes-ff5dc8025359)  
16. Best practice 10.3 – Utilize compression techniques to both decrease storage requirements and enhance I/O efficiency \- Data Analytics Lens \- AWS Documentation, accessed July 18, 2025, [https://docs.aws.amazon.com/wellarchitected/latest/analytics-lens/best-practice-10.3---use-file-compression-to-reduce-number-of-files-and-to-improve-file-io-efficiency..html](https://docs.aws.amazon.com/wellarchitected/latest/analytics-lens/best-practice-10.3---use-file-compression-to-reduce-number-of-files-and-to-improve-file-io-efficiency..html)  
17. AWS Lambda for sending logs from S3 \- New Relic Documentation, accessed July 17, 2025, [https://docs.newrelic.com/docs/logs/forward-logs/aws-lambda-sending-logs-s3/](https://docs.newrelic.com/docs/logs/forward-logs/aws-lambda-sending-logs-s3/)  
18. Tutorial: Using an Amazon S3 trigger to invoke a Lambda function ..., accessed July 17, 2025, [https://docs.aws.amazon.com/lambda/latest/dg/with-s3-example.html](https://docs.aws.amazon.com/lambda/latest/dg/with-s3-example.html)  
19. The one mistake everyone makes when using Kinesis with Lambda \- theburningmonk.com, accessed July 17, 2025, [https://theburningmonk.com/2023/12/the-one-mistake-everyone-makes-when-using-kinesis-with-lambda/](https://theburningmonk.com/2023/12/the-one-mistake-everyone-makes-when-using-kinesis-with-lambda/)  
20. New AWS Lambda controls for stream processing and ..., accessed July 17, 2025, [https://aws.amazon.com/blogs/compute/new-aws-lambda-controls-for-stream-processing-and-asynchronous-invocations/](https://aws.amazon.com/blogs/compute/new-aws-lambda-controls-for-stream-processing-and-asynchronous-invocations/)  
21. Process Kinesis Streams with AWS Lambda, accessed July 17, 2025, [https://aws.amazon.com/awstv/watch/798a6d586ad/](https://aws.amazon.com/awstv/watch/798a6d586ad/)  
22. How can i clear out a kinesis stream? : r/aws \- Reddit, accessed July 17, 2025, [https://www.reddit.com/r/aws/comments/83dgz8/how\_can\_i\_clear\_out\_a\_kinesis\_stream/](https://www.reddit.com/r/aws/comments/83dgz8/how_can_i_clear_out_a_kinesis_stream/)  
23. Strategies for AWS Lambda Cost Optimization \- Sedai, accessed July 17, 2025, [https://www.sedai.io/blog/strategies-for-aws-lambda-cost-optimization](https://www.sedai.io/blog/strategies-for-aws-lambda-cost-optimization)  
24. Tips for configuring AWS Lambda batch size | Capital One \- Medium, accessed July 17, 2025, [https://medium.com/capital-one-tech/best-practices-configuring-aws-lambda-sqs-batch-size-27ebc8a5d5ce](https://medium.com/capital-one-tech/best-practices-configuring-aws-lambda-sqs-batch-size-27ebc8a5d5ce)  
25. Cost Optimization for AWS Lambda | 5\. Filter and batch events \- Serverless Land, accessed July 17, 2025, [https://serverlessland.com/content/service/lambda/guides/cost-optimization/5-filter-and-batch](https://serverlessland.com/content/service/lambda/guides/cost-optimization/5-filter-and-batch)  
26. Lambda Cost Optimization at Scale: My Journey (and what I learned) : r/aws \- Reddit, accessed July 17, 2025, [https://www.reddit.com/r/aws/comments/1kge3yf/lambda\_cost\_optimization\_at\_scale\_my\_journey\_and/](https://www.reddit.com/r/aws/comments/1kge3yf/lambda_cost_optimization_at_scale_my_journey_and/)