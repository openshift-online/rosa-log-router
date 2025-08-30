#!/usr/bin/env python3
"""
Fake Log Generator for Multi-Tenant Logging Pipeline Testing

Generates realistic fake log data using the faker library for testing
the logging pipeline with configurable volumes and patterns.
"""

import argparse
import json
import random
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Any

try:
    from faker import Faker
except ImportError:
    print("Error: faker library not installed. Run: pip install faker", file=sys.stderr)
    sys.exit(1)

# Global state for graceful shutdown
shutdown_requested = False
total_logs_generated = 0

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_requested
    print(f"\nReceived signal {signum}, shutting down gracefully...", file=sys.stderr)
    print(f"Total logs generated: {total_logs_generated}", file=sys.stderr)
    shutdown_requested = True

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

class FakeLogGenerator:
    """Generates realistic fake log data with configurable patterns"""
    
    # Supported timestamp formats for Vector testing
    TIMESTAMP_FORMATS = {
        'json_ts': 'JSON logs with ts field (etcd style)',
        'json_time': 'JSON logs with time field',
        'iso_direct': 'Direct ISO timestamp at start',
        'time_equals': 'Structured time="..." format', 
        'kubernetes': 'Kubernetes log format (I0830 format)',
        'go_standard': 'Go standard log format (2025/08/30)',
        'mixed': 'Mixed formats (random selection)'
    }
    
    # Log levels with realistic distribution weights
    LOG_LEVELS = {
        'DEBUG': 30,
        'INFO': 50, 
        'WARN': 15,
        'ERROR': 5
    }
    
    # Common module names for realistic logs
    MODULE_NAMES = [
        'auth.service', 'payment.processor', 'user.controller', 'order.handler',
        'inventory.manager', 'notification.sender', 'config.loader', 'cache.redis',
        'database.connection', 'api.gateway', 'security.validator', 'metrics.collector',
        'scheduler.jobs', 'file.uploader', 'email.service', 'search.engine',
        'analytics.tracker', 'backup.manager', 'health.checker', 'logger.writer'
    ]
    
    def __init__(self, 
                 min_message_bytes: int = 100, 
                 max_message_bytes: int = 1024,
                 customer_id: str = "test-customer",
                 cluster_id: str = "test-cluster",
                 application: str = "test-app",
                 pod_name: str = "test-pod",
                 timestamp_format: str = "mixed"):
        """Initialize the fake log generator"""
        self.fake = Faker()
        self.min_message_bytes = min_message_bytes
        self.max_message_bytes = max_message_bytes
        self.customer_id = customer_id
        self.cluster_id = cluster_id
        self.application = application
        self.pod_name = pod_name
        self.timestamp_format = timestamp_format
        
        # Validate timestamp format
        if timestamp_format not in self.TIMESTAMP_FORMATS:
            raise ValueError(f"Invalid timestamp format: {timestamp_format}. "
                           f"Valid options: {list(self.TIMESTAMP_FORMATS.keys())}")
        
        # Create weighted log level choices
        self.log_levels = []
        for level, weight in self.LOG_LEVELS.items():
            self.log_levels.extend([level] * weight)
    
    def generate_fake_message(self, target_bytes: int) -> str:
        """Generate a fake log message of approximately target_bytes length"""
        message_parts = []
        current_length = 0
        
        # Start with a base action/event
        actions = [
            "Processing request", "Executing operation", "Handling transaction",
            "Validating input", "Connecting to service", "Loading configuration",
            "Updating records", "Sending notification", "Checking permissions",
            "Performing backup", "Analyzing data", "Generating report"
        ]
        
        base_message = random.choice(actions)
        message_parts.append(base_message)
        current_length += len(base_message)
        
        # Add details until we reach target length
        while current_length < target_bytes - 50:  # Leave room for final touches
            detail_type = random.choice(['user', 'id', 'error', 'time', 'data'])
            
            if detail_type == 'user':
                detail = f" for user {self.fake.user_name()}"
            elif detail_type == 'id':
                detail = f" with ID {self.fake.uuid4()}"
            elif detail_type == 'error':
                detail = f" - {self.fake.catch_phrase()}"
            elif detail_type == 'time':
                detail = f" taking {random.randint(1, 5000)}ms"
            else:  # data
                detail = f" containing {random.randint(1, 1000)} items"
            
            if current_length + len(detail) < target_bytes - 20:
                message_parts.append(detail)
                current_length += len(detail)
            else:
                break
        
        # Add final period if needed
        message = "".join(message_parts)
        if not message.endswith('.'):
            message += "."
            
        # Pad or trim to get closer to target
        if len(message) < target_bytes - 10:
            padding = self.fake.text(max_nb_chars=target_bytes - len(message) - 1)
            message += f" Additional context: {padding}"
        
        return message[:target_bytes] if len(message) > target_bytes else message
    
    def generate_timestamp_formatted_log(self, message: str, level: str, timestamp_format: str = None) -> Any:
        """Generate a log in the specified timestamp format"""
        if timestamp_format is None:
            timestamp_format = self.timestamp_format
            
        now = datetime.now(timezone.utc)
        
        if timestamp_format == 'json_ts':
            # JSON logs with 'ts' field (etcd style)
            return {
                "ts": now.isoformat(),
                "level": level.lower(),
                "msg": message,
                "component": random.choice(['etcd', 'ignition-server', 'machine-config-daemon']),
                "source": self.application
            }
            
        elif timestamp_format == 'json_time':
            # JSON logs with 'time' field
            return {
                "time": now.isoformat(),
                "level": level,
                "message": message,
                "service": self.application,
                "host": self.pod_name
            }
            
        elif timestamp_format == 'iso_direct':
            # Direct ISO timestamp at start: "2025-08-30T06:11:26.816Z Message here"
            return f"{now.isoformat()} {message}"
            
        elif timestamp_format == 'time_equals':
            # Structured time="..." format: 'time="2025-08-30T09:21:21Z" level=info msg="message"'
            escaped_message = message.replace('"', '\\"')
            return f'time="{now.isoformat()}" level={level.lower()} msg="{escaped_message}" component={self.application}'
            
        elif timestamp_format == 'kubernetes':
            # Kubernetes log format: "I0830 11:27:01.564974 1 controller.go:231] Message"
            log_level_map = {'INFO': 'I', 'WARN': 'W', 'ERROR': 'E', 'DEBUG': 'I'}
            k8s_level = log_level_map.get(level, 'I')
            month_day = now.strftime("%m%d")
            time_part = now.strftime("%H:%M:%S.%f")[:-3]  # microseconds to milliseconds
            thread_id = random.randint(1, 999)
            filename = random.choice(['controller.go', 'manager.go', 'reconciler.go', 'webhook.go'])
            line_num = random.randint(100, 999)
            return f"{k8s_level}{month_day} {time_part} {thread_id} {filename}:{line_num}] {message}"
            
        elif timestamp_format == 'go_standard':
            # Go standard log format: "2025/08/30 10:33:20 message"
            go_timestamp = now.strftime("%Y/%m/%d %H:%M:%S")
            return f"{go_timestamp} {message}"
            
        else:  # mixed or fallback
            # Randomly select a format for mixed mode
            formats = ['json_ts', 'json_time', 'iso_direct', 'time_equals', 'kubernetes', 'go_standard']
            selected_format = random.choice(formats)
            return self.generate_timestamp_formatted_log(message, level, selected_format)
    
    def generate_log_entry(self) -> Any:
        """Generate a single fake log entry in the specified timestamp format"""
        global total_logs_generated
        
        # Generate message of random size within range
        target_bytes = random.randint(self.min_message_bytes, self.max_message_bytes)
        base_message = self.generate_fake_message(target_bytes)
        
        # Select log level with weighted distribution
        level = random.choice(self.log_levels)
        
        # Generate realistic message with module/operation context
        module = random.choice(self.MODULE_NAMES)
        operation = random.choice(['started', 'completed', 'failed', 'processing', 'initialized', 'terminated'])
        contextual_message = f"{module}: {operation} - {base_message}"
        
        # Generate log in the specified timestamp format
        formatted_log = self.generate_timestamp_formatted_log(contextual_message, level)
        
        total_logs_generated += 1
        return formatted_log
    
    def generate_batch(self, batch_size: int) -> List[Any]:
        """Generate a batch of log entries"""
        return [self.generate_log_entry() for _ in range(batch_size)]

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='Generate fake log data for testing')
    parser.add_argument('--min-batch-size', type=int, default=1,
                       help='Minimum number of logs per batch (default: 1)')
    parser.add_argument('--max-batch-size', type=int, default=50,
                       help='Maximum number of logs per batch (default: 50)')
    parser.add_argument('--min-sleep', type=float, default=0.1,
                       help='Minimum sleep between batches in seconds (default: 0.1)')
    parser.add_argument('--max-sleep', type=float, default=5.0,
                       help='Maximum sleep between batches in seconds (default: 5.0)')
    parser.add_argument('--min-message-bytes', type=int, default=100,
                       help='Minimum message size in bytes (default: 100)')
    parser.add_argument('--max-message-bytes', type=int, default=1024,
                       help='Maximum message size in bytes (default: 1024)')
    parser.add_argument('--customer-id', type=str, default='test-customer',
                       help='Customer ID for log metadata (default: test-customer)')
    parser.add_argument('--cluster-id', type=str, default='test-cluster',
                       help='Cluster ID for log metadata (default: test-cluster)')
    parser.add_argument('--application', type=str, default='test-app',
                       help='Application name for log metadata (default: test-app)')
    parser.add_argument('--pod-name', type=str, default='test-pod',
                       help='Pod name for log metadata (default: test-pod)')
    parser.add_argument('--total-batches', type=int, default=0,
                       help='Total number of batches to generate (0 = infinite)')
    parser.add_argument('--stats-interval', type=int, default=100,
                       help='Print stats every N batches (default: 100)')
    parser.add_argument('--timestamp-format', type=str, default='mixed',
                       choices=list(FakeLogGenerator.TIMESTAMP_FORMATS.keys()),
                       help='Timestamp format to generate (default: mixed)')
    parser.add_argument('--list-formats', action='store_true',
                       help='List available timestamp formats and exit')
    
    args = parser.parse_args()
    
    # Handle format listing
    if args.list_formats:
        print("Available timestamp formats:", file=sys.stderr)
        for fmt, desc in FakeLogGenerator.TIMESTAMP_FORMATS.items():
            print(f"  {fmt}: {desc}", file=sys.stderr)
        sys.exit(0)
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Initialize generator
    generator = FakeLogGenerator(
        min_message_bytes=args.min_message_bytes,
        max_message_bytes=args.max_message_bytes,
        customer_id=args.customer_id,
        cluster_id=args.cluster_id,
        application=args.application,
        pod_name=args.pod_name,
        timestamp_format=args.timestamp_format
    )
    
    print(f"Starting fake log generator...", file=sys.stderr)
    print(f"Timestamp format: {args.timestamp_format} ({FakeLogGenerator.TIMESTAMP_FORMATS[args.timestamp_format]})", file=sys.stderr)
    print(f"Batch size: {args.min_batch_size}-{args.max_batch_size}", file=sys.stderr)
    print(f"Sleep interval: {args.min_sleep}-{args.max_sleep}s", file=sys.stderr)
    print(f"Message size: {args.min_message_bytes}-{args.max_message_bytes} bytes", file=sys.stderr)
    print(f"Metadata: {args.customer_id}/{args.cluster_id}/{args.application}/{args.pod_name}", file=sys.stderr)
    print("", file=sys.stderr)
    
    batch_count = 0
    start_time = time.time()
    
    try:
        while not shutdown_requested and (args.total_batches == 0 or batch_count < args.total_batches):
            # Generate random batch size
            batch_size = random.randint(args.min_batch_size, args.max_batch_size)
            
            # Generate batch
            batch = generator.generate_batch(batch_size)
            
            # Output batch - handle both JSON objects and plain text strings
            for log_entry in batch:
                if isinstance(log_entry, (dict, list)):
                    # JSON format - output as JSON
                    print(json.dumps(log_entry))
                else:
                    # Plain text format - output directly
                    print(log_entry)
                sys.stdout.flush()
            
            batch_count += 1
            
            # Print stats periodically
            if batch_count % args.stats_interval == 0:
                elapsed_time = time.time() - start_time
                rate = total_logs_generated / elapsed_time if elapsed_time > 0 else 0
                print(f"Generated {batch_count} batches, {total_logs_generated} logs, "
                      f"{rate:.1f} logs/sec", file=sys.stderr)
            
            # Sleep random amount
            if not shutdown_requested:
                sleep_time = random.uniform(args.min_sleep, args.max_sleep)
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        pass  # Handled by signal handler
    except BrokenPipeError:
        # Handle broken pipe gracefully (e.g., when piped to head or other tools)
        print("Pipe broken, shutting down gracefully...", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Final stats
    elapsed_time = time.time() - start_time
    rate = total_logs_generated / elapsed_time if elapsed_time > 0 else 0
    print(f"\nFinal stats:", file=sys.stderr)
    print(f"Total batches: {batch_count}", file=sys.stderr)
    print(f"Total logs: {total_logs_generated}", file=sys.stderr)
    print(f"Runtime: {elapsed_time:.1f}s", file=sys.stderr)
    print(f"Average rate: {rate:.1f} logs/sec", file=sys.stderr)

if __name__ == '__main__':
    main()