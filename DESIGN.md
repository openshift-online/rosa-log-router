# **Architecting a Scalable, Multi-Tenant, and Cross-Account Logging Pipeline on AWS**

## **Section 1: Foundational Principles and Architectural Framework**

### **1.1. Executive Summary**

This document presents a comprehensive architectural design for a high-throughput, multi-region, and multi-tenant logging pipeline on Amazon Web Services (AWS). The proposed solution is tailored for ingesting log streams from Kubernetes and OpenShift environments, processing them efficiently, and securely delivering them to individual customer AWS accounts. The architecture is optimized for cost, manageability, scalability, and operational simplicity.

The recommended blueprint follows a "Direct Ingestion, Staged Processing, and Decentralized Delivery" model. At the source, the high-performance log forwarder, **Vector**, is deployed as a DaemonSet within each Kubernetes/OpenShift cluster. Vector agents identify target pods via specific labels (e.g., rosa\_export\_logs), automatically enrich logs with other pod metadata (e.g., customer\_id, cluster\_id), and write them directly to a central **Amazon S3** bucket. This direct-to-S3 approach simplifies the pipeline by removing intermediate services, giving the Vector agent full control over batching, compression, and dynamic object key formatting.

The S3 bucket acts as a durable, structured staging area, with logs automatically segregated into tenant-specific prefixes based on the metadata provided by Vector. This staging layer serves as a clean, decoupled interface to the final delivery mechanism.

The delivery pipeline is an event-driven, "hub and spoke" workflow. An S3 event notification publishes a message to a central **Amazon SNS topic** whenever a new log file is delivered by Vector. An **Amazon SQS queue**, subscribed to this topic, receives these notifications and triggers a processing array (such as an AWS Lambda function) that remains within your AWS account. This processor reads the tenant-specific log file, securely assumes a specialized **"log distribution" role** in the corresponding customer's AWS account, and delivers the log records to the customer's Amazon CloudWatch Logs service. This end-to-end architecture provides a robust, automated, and cost-optimized solution for large-scale, multi-tenant logging on AWS.

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
* **Stage 2: Staging & Segregation (Your AWS Account):** The central Amazon S3 bucket acts as a durable and cost-effective staging area. The dynamic object keys created by Vector automatically organize the incoming logs into a predictable, tenant-segregated prefix structure (e.g., /customer\_id/cluster\_id/...).  
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
* **Filtering and Enrichment Logic:** The Vector configuration will contain a filter transform that uses VRL to inspect pod labels.  
  * **Filtering:** The filter will be configured to only allow logs from pods that contain the rosa\_export\_logs label. All other logs will be dropped.  
  * **Enrichment:** For the logs that pass the filter, a remap transform will extract the values from other labels (e.g., customer\_id, cluster\_id, application) and the pod name from the Kubernetes metadata that Vector automatically adds to the event. These values are promoted to top-level fields in the log event.  
* **Configuring the aws\_s3 Sink:** The sink is the final step in the Vector agent's pipeline.  
  * **Dynamic key\_prefix:** The sink's key\_prefix option will use Vector's template syntax to build the dynamic S3 path from the fields created during the enrichment step. 12  
    Ini, TOML  
    \# In vector.toml  
    \[sinks.s3\_destination\]  
      type \= "aws\_s3"  
      inputs \= \["enriched\_logs"\]  
      bucket \= "your-central-logging-bucket"  
      key\_prefix \= "{{customer\_id}}/{{cluster\_id}}/{{application}}/{{pod\_name}}/"  
      \#... other options

  * **File Naming:** Vector's S3 sink automatically ensures unique file names by appending a timestamp and a UUID, matching the desired \<ts\>-\<uuid\> format. Compression is enabled by default to produce .gz files. 12  
  * **Batching and Compression:** To optimize S3 costs and avoid the "small file problem," the sink's batching parameters must be tuned. By setting a larger batch.timeout\_secs (e.g., 300 seconds) and batch.max\_bytes (e.g., 10MB), each Vector agent will buffer logs and write larger, more cost-efficient objects to S3. This is critical for reducing S3 PUT request costs and the number of downstream notifications. 12

## **Section 3: S3 Staging and the Hub-and-Spoke Delivery Pipeline**

By removing the Kinesis Data Firehose middleware, the architecture becomes more direct. The central S3 bucket and the subsequent event-driven delivery pipeline are now the core components for processing and routing the staged data.

### **3.1. The S3 Staging Area**

The central S3 bucket is the durable, long-term staging area for all log data. The object key structure, now created directly by Vector, is the foundation of the multi-tenant segregation. A typical object path would look like:

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
2. **Extract Tenant Identifier:** The function's code parses the object key to extract the customer\_id.  
3. **Assume Cross-Account Role:** Using the customer\_id, the function looks up the configuration for that tenant (e.g., from DynamoDB) and calls the AWS Security Token Service (STS) to assume the specialized **"log distribution" role** in the customer's account.  
4. **Fetch and Deliver Logs:** Using the temporary credentials, the Lambda function reads the gzipped JSON file from S3, parses the log records, and calls the PutLogEvents API to deliver them to the correct Log Group in the customer's account. 17

### **3.4. The Final Hop: Infrastructure in the Customer Account**

Each customer must deploy a standardized AWS CloudFormation template in their account to create the necessary resources. The key component is the specialized **"log distribution" IAM Role**.

* **Trust Policy:** This policy explicitly trusts the ARN of your central log processing Lambda's execution role, ensuring only your designated function can assume it. 6  
* **Permissions Policy:** This policy grants only the logs:PutLogEvents permission and restricts it to a specific, pre-agreed-upon CloudWatch Log Group ARN within the customer's account.

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
* The SQS Queue triggers an **"AWS Lambda Function (Log Distributor)"**.  
* The Lambda function has a two-way arrow labeled **"sts:AssumeRole"** pointing towards the boundary of "Your AWS Environment".

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
6. **Cross-Account Delivery:** The Lambda assumes the "log distribution" role in the acme-corp account, reads the log file from S3, and pushes the events to the customer's CloudWatch Logs.

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
* **Batching is Critical:** The most important cost optimization lever is now the **batching configuration within Vector's S3 sink**. Configuring a large buffer size (batch.max\_bytes) and a long buffer interval (batch.timeout\_secs) is essential. This strategy creates larger files in S3, which drastically reduces the number of S3 PUT requests and the corresponding downstream SNS/SQS/Lambda invocations, leading to significant cost savings. 23  
* **Storage Cost Trade-off:** This architecture loses the ability to easily convert logs to Apache Parquet, which was a feature of Kinesis Data Firehose. Storing gzipped JSON is generally less space-efficient than Parquet, which may lead to slightly higher S3 storage costs over time. This is a trade-off for the architectural simplicity of the direct-to-S3 approach. 16

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