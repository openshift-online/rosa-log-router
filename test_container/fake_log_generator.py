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
                 pod_name: str = "test-pod"):
        """Initialize the fake log generator"""
        self.fake = Faker()
        self.min_message_bytes = min_message_bytes
        self.max_message_bytes = max_message_bytes
        self.customer_id = customer_id
        self.cluster_id = cluster_id
        self.application = application
        self.pod_name = pod_name
        
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
    
    def generate_log_entry(self) -> Dict[str, Any]:
        """Generate a single fake log entry"""
        global total_logs_generated
        
        # Generate message of random size within range
        target_bytes = random.randint(self.min_message_bytes, self.max_message_bytes)
        message = self.generate_fake_message(target_bytes)
        
        # Select log level with weighted distribution
        level = random.choice(self.log_levels)
        
        # Generate module and line number
        module = random.choice(self.MODULE_NAMES)
        line_number = random.randint(1, 999)
        
        # Create log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "module": module,
            "line": line_number,
            "message": message,
            "customer_id": self.customer_id,
            "cluster_id": self.cluster_id,
            "application": self.application,
            "pod_name": self.pod_name,
            "source": "fake-log-generator"
        }
        
        # Add some additional structured data occasionally
        if random.random() < 0.3:  # 30% chance
            log_entry["additional_data"] = {
                "request_id": self.fake.uuid4(),
                "session_id": self.fake.lexify(text='????????'),
                "ip_address": self.fake.ipv4(),
                "user_agent": self.fake.user_agent()
            }
        
        total_logs_generated += 1
        return log_entry
    
    def generate_batch(self, batch_size: int) -> List[Dict[str, Any]]:
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
    
    args = parser.parse_args()
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Initialize generator
    generator = FakeLogGenerator(
        min_message_bytes=args.min_message_bytes,
        max_message_bytes=args.max_message_bytes,
        customer_id=args.customer_id,
        cluster_id=args.cluster_id,
        application=args.application,
        pod_name=args.pod_name
    )
    
    print(f"Starting fake log generator...", file=sys.stderr)
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
            
            # Output batch as NDJSON
            for log_entry in batch:
                print(json.dumps(log_entry))
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