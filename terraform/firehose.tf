# Kinesis Data Firehose configuration with dynamic partitioning
resource "aws_kinesis_firehose_delivery_stream" "central_logging" {
  name        = "central-logging-stream"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose_role.arn
    bucket_arn = aws_s3_bucket.central_logging.arn
    
    # Dynamic partitioning with tenant segregation
    prefix = "logs/tenant_id=!{partitionKeyFromQuery:customer_tenant}/cluster_id=!{partitionKeyFromQuery:cluster_id}/environment=!{partitionKeyFromQuery:environment}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
    error_output_prefix = "errors/"
    
    # Buffering configuration for cost optimization
    buffering_size     = 128  # 128 MB
    buffering_interval = 900  # 15 minutes
    compression_format = "GZIP"

    # Data format conversion to Parquet for cost savings
    data_format_conversion_configuration {
      enabled = true
      output_format_configuration {
        serializer {
          parquet_ser_de {}
        }
      }
      schema_configuration {
        database_name = aws_glue_catalog_database.central_logging.name
        table_name    = aws_glue_catalog_table.central_logging.name
        role_arn      = aws_iam_role.firehose_role.arn
      }
    }

    # Dynamic partitioning configuration
    dynamic_partitioning {
      enabled = true
    }

    # Processing configuration for metadata extraction
    processing_configuration {
      enabled = true
      
      processors {
        type = "MetadataExtraction"
        parameters {
          parameter_name  = "JsonParsingEngine"
          parameter_value = "JQ-1.6"
        }
        parameters {
          parameter_name  = "MetadataExtractionQuery"
          parameter_value = "{customer_tenant: .customer_tenant, cluster_id: .cluster_id, environment: .environment}"
        }
      }
    }

    # S3 backup configuration
    s3_backup_mode = "Enabled"
    s3_backup_configuration {
      role_arn   = aws_iam_role.firehose_role.arn
      bucket_arn = aws_s3_bucket.central_logging_backup.arn
      prefix     = "backup/"
      buffering_size     = 5
      buffering_interval = 300
      compression_format = "GZIP"
    }
  }

  tags = {
    Name        = "central-logging-stream"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# S3 bucket for central logging
resource "aws_s3_bucket" "central_logging" {
  bucket = "central-logging-${random_id.bucket_suffix.hex}"
  
  tags = {
    Name        = "central-logging"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# S3 bucket for backup
resource "aws_s3_bucket" "central_logging_backup" {
  bucket = "central-logging-backup-${random_id.bucket_suffix.hex}"
  
  tags = {
    Name        = "central-logging-backup"
    Environment = "production"
    Purpose     = "multi-tenant-logging-backup"
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# S3 bucket versioning
resource "aws_s3_bucket_versioning" "central_logging" {
  bucket = aws_s3_bucket.central_logging.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 bucket encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "central_logging" {
  bucket = aws_s3_bucket.central_logging.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 bucket lifecycle configuration
resource "aws_s3_bucket_lifecycle_configuration" "central_logging" {
  bucket = aws_s3_bucket.central_logging.id

  rule {
    id     = "central_logging_lifecycle"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }

    expiration {
      days = 2555  # 7 years retention
    }
  }
}

# S3 event notification to SNS
resource "aws_s3_bucket_notification" "central_logging_notification" {
  bucket = aws_s3_bucket.central_logging.id

  topic {
    topic_arn = aws_sns_topic.log_delivery_hub.arn
    events    = ["s3:ObjectCreated:*"]
    filter_prefix = "logs/"
    filter_suffix = ".gz"
  }

  depends_on = [aws_sns_topic_policy.log_delivery_hub]
}

# Glue catalog database for schema registry
resource "aws_glue_catalog_database" "central_logging" {
  name = "central_logging_db"
  description = "Database for central logging schema"
}

# Glue catalog table for log schema
resource "aws_glue_catalog_table" "central_logging" {
  name          = "central_logging_table"
  database_name = aws_glue_catalog_database.central_logging.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "projection.enabled"                    = "true"
    "projection.tenant_id.type"            = "enum"
    "projection.tenant_id.values"          = "tenant1,tenant2,tenant3"  # Update as needed
    "projection.cluster_id.type"           = "enum"
    "projection.cluster_id.values"         = "prod,staging,dev"
    "projection.environment.type"          = "enum"
    "projection.environment.values"        = "production,staging,development"
    "projection.year.type"                 = "integer"
    "projection.year.range"                = "2024,2030"
    "projection.month.type"                = "integer"
    "projection.month.range"               = "1,12"
    "projection.month.digits"              = "2"
    "projection.day.type"                  = "integer"
    "projection.day.range"                 = "1,31"
    "projection.day.digits"                = "2"
    "projection.hour.type"                 = "integer"
    "projection.hour.range"                = "0,23"
    "projection.hour.digits"               = "2"
    "storage.location.template"            = "s3://${aws_s3_bucket.central_logging.bucket}/logs/tenant_id=$${tenant_id}/cluster_id=$${cluster_id}/environment=$${environment}/year=$${year}/month=$${month}/day=$${day}/hour=$${hour}/"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.central_logging.bucket}/logs/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "timestamp"
      type = "timestamp"
    }
    columns {
      name = "customer_tenant"
      type = "string"
    }
    columns {
      name = "cluster_id"
      type = "string"
    }
    columns {
      name = "environment"
      type = "string"
    }
    columns {
      name = "application"
      type = "string"
    }
    columns {
      name = "log_level"
      type = "string"
    }
    columns {
      name = "message"
      type = "string"
    }
    columns {
      name = "kubernetes"
      type = "struct<namespace:string,pod_name:string,container_name:string,node_name:string>"
    }
    columns {
      name = "source_type"
      type = "string"
    }
    columns {
      name = "file"
      type = "string"
    }
  }

  partition_keys {
    name = "tenant_id"
    type = "string"
  }
  partition_keys {
    name = "cluster_id"
    type = "string"
  }
  partition_keys {
    name = "environment"
    type = "string"
  }
  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
  partition_keys {
    name = "hour"
    type = "string"
  }
}