# DynamoDB table for tenant configurations
resource "aws_dynamodb_table" "tenant_configurations" {
  name           = "tenant-configurations"
  billing_mode   = "PAY_PER_REQUEST"  # On-demand billing for variable workload
  hash_key       = "tenant_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "account_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # Global Secondary Index for querying by account ID
  global_secondary_index {
    name     = "AccountIdIndex"
    hash_key = "account_id"
  }

  # Global Secondary Index for querying by status
  global_secondary_index {
    name     = "StatusIndex"
    hash_key = "status"
  }

  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "tenant-configurations"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Sample tenant configuration items (for testing/demo)
resource "aws_dynamodb_table_item" "sample_tenant_1" {
  table_name = aws_dynamodb_table.tenant_configurations.name
  hash_key   = aws_dynamodb_table.tenant_configurations.hash_key

  item = jsonencode({
    tenant_id = {
      S = "acme-corp"
    }
    account_id = {
      S = "123456789012"
    }
    environment = {
      S = "production"
    }
    log_distribution_role_arn = {
      S = "arn:aws:iam::123456789012:role/LogDistribution-acme-corp-production"
    }
    target_region = {
      S = "us-east-1"
    }
    log_groups = {
      M = {
        application = {
          S = "/tenant-logs/acme-corp/application"
        }
        system = {
          S = "/tenant-logs/acme-corp/system"
        }
        audit = {
          S = "/tenant-logs/acme-corp/audit"
        }
      }
    }
    created_at = {
      S = "2024-01-15T10:30:00Z"
    }
    updated_at = {
      S = "2024-01-15T10:30:00Z"
    }
    status = {
      S = "active"
    }
    retention_days = {
      N = "90"
    }
    max_log_rate_per_minute = {
      N = "1000"
    }
    alert_endpoints = {
      L = [
        {
          M = {
            type = {
              S = "email"
            }
            endpoint = {
              S = "ops@acme-corp.com"
            }
          }
        }
      ]
    }
  })

  depends_on = [aws_dynamodb_table.tenant_configurations]
}

resource "aws_dynamodb_table_item" "sample_tenant_2" {
  table_name = aws_dynamodb_table.tenant_configurations.name
  hash_key   = aws_dynamodb_table.tenant_configurations.hash_key

  item = jsonencode({
    tenant_id = {
      S = "globodyne-inc"
    }
    account_id = {
      S = "987654321098"
    }
    environment = {
      S = "production"
    }
    log_distribution_role_arn = {
      S = "arn:aws:iam::987654321098:role/LogDistribution-globodyne-inc-production"
    }
    target_region = {
      S = "eu-west-1"
    }
    log_groups = {
      M = {
        application = {
          S = "/tenant-logs/globodyne-inc/application"
        }
        system = {
          S = "/tenant-logs/globodyne-inc/system"
        }
        audit = {
          S = "/tenant-logs/globodyne-inc/audit"
        }
      }
    }
    created_at = {
      S = "2024-01-20T14:15:00Z"
    }
    updated_at = {
      S = "2024-01-20T14:15:00Z"
    }
    status = {
      S = "active"
    }
    retention_days = {
      N = "120"
    }
    max_log_rate_per_minute = {
      N = "2000"
    }
    alert_endpoints = {
      L = [
        {
          M = {
            type = {
              S = "slack"
            }
            endpoint = {
              S = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
            }
          }
        }
      ]
    }
  })

  depends_on = [aws_dynamodb_table.tenant_configurations]
}

# CloudWatch alarms for DynamoDB monitoring
resource "aws_cloudwatch_metric_alarm" "dynamodb_read_throttle" {
  alarm_name          = "tenant-config-read-throttle"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ReadThrottledEvents"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors DynamoDB read throttling"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    TableName = aws_dynamodb_table.tenant_configurations.name
  }

  tags = {
    Name        = "tenant-config-read-throttle"
    Environment = "production"
  }
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_write_throttle" {
  alarm_name          = "tenant-config-write-throttle"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "WriteThrottledEvents"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors DynamoDB write throttling"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    TableName = aws_dynamodb_table.tenant_configurations.name
  }

  tags = {
    Name        = "tenant-config-write-throttle"
    Environment = "production"
  }
}