#!/usr/bin/env python3
"""
Payload Size Analysis Utilities for CloudWatch Batch Testing

This module provides utilities to analyze and report on CloudWatch Logs
batch payload sizes, helping to understand byte limit behavior and
optimize batching strategies.
"""

import json
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class EventSizeAnalysis:
    """Analysis results for a single log event."""
    message_bytes: int
    overhead_bytes: int
    total_bytes: int
    message_length: int

    @property
    def overhead_percentage(self) -> float:
        """Calculate overhead as percentage of total size."""
        return (self.overhead_bytes / self.total_bytes) * 100 if self.total_bytes > 0 else 0


@dataclass
class BatchSizeAnalysis:
    """Analysis results for a batch of log events."""
    event_count: int
    total_message_bytes: int
    total_overhead_bytes: int
    total_batch_bytes: int
    largest_event_bytes: int
    smallest_event_bytes: int
    average_event_bytes: float
    overhead_percentage: float
    cloudwatch_limit_bytes: int = 1048576  # 1MB AWS limit

    @property
    def remaining_capacity_bytes(self) -> int:
        """Calculate remaining capacity before hitting CloudWatch limit."""
        return max(0, self.cloudwatch_limit_bytes - self.total_batch_bytes)

    @property
    def capacity_utilization_percentage(self) -> float:
        """Calculate what percentage of CloudWatch limit is being used."""
        return (self.total_batch_bytes / self.cloudwatch_limit_bytes) * 100

    @property
    def would_exceed_limit(self) -> bool:
        """Check if this batch would exceed CloudWatch limits."""
        return self.total_batch_bytes > self.cloudwatch_limit_bytes


class PayloadAnalyzer:
    """Analyze CloudWatch Logs payload sizes and batch efficiency."""

    # CloudWatch API constants
    CW_OVERHEAD_BYTES_PER_EVENT = 26
    CW_MAX_BATCH_SIZE_BYTES = 1048576  # 1MB
    CW_MAX_EVENTS_PER_BATCH = 1000

    @classmethod
    def analyze_event(cls, event: Dict[str, Any]) -> EventSizeAnalysis:
        """
        Analyze a single log event for size information.

        Args:
            event: CloudWatch log event with 'message' and 'timestamp' fields

        Returns:
            EventSizeAnalysis with detailed size breakdown
        """
        message = event.get('message', '')

        # Handle different message types (string, dict, list)
        if isinstance(message, str):
            message_bytes = len(message.encode('utf-8'))
            message_length = len(message)
        else:
            # For non-string messages (JSON objects), convert to string
            message_str = json.dumps(message) if isinstance(message, (dict, list)) else str(message)
            message_bytes = len(message_str.encode('utf-8'))
            message_length = len(message_str)

        return EventSizeAnalysis(
            message_bytes=message_bytes,
            overhead_bytes=cls.CW_OVERHEAD_BYTES_PER_EVENT,
            total_bytes=message_bytes + cls.CW_OVERHEAD_BYTES_PER_EVENT,
            message_length=message_length
        )

    @classmethod
    def analyze_batch(cls, events: List[Dict[str, Any]]) -> BatchSizeAnalysis:
        """
        Analyze a batch of log events for CloudWatch compliance.

        Args:
            events: List of CloudWatch log events

        Returns:
            BatchSizeAnalysis with comprehensive batch metrics
        """
        if not events:
            return BatchSizeAnalysis(
                event_count=0,
                total_message_bytes=0,
                total_overhead_bytes=0,
                total_batch_bytes=0,
                largest_event_bytes=0,
                smallest_event_bytes=0,
                average_event_bytes=0,
                overhead_percentage=0
            )

        event_analyses = [cls.analyze_event(event) for event in events]

        total_message_bytes = sum(analysis.message_bytes for analysis in event_analyses)
        total_overhead_bytes = sum(analysis.overhead_bytes for analysis in event_analyses)
        total_batch_bytes = total_message_bytes + total_overhead_bytes

        event_sizes = [analysis.total_bytes for analysis in event_analyses]
        largest_event_bytes = max(event_sizes)
        smallest_event_bytes = min(event_sizes)
        average_event_bytes = sum(event_sizes) / len(event_sizes)

        overhead_percentage = (total_overhead_bytes / total_batch_bytes) * 100 if total_batch_bytes > 0 else 0

        return BatchSizeAnalysis(
            event_count=len(events),
            total_message_bytes=total_message_bytes,
            total_overhead_bytes=total_overhead_bytes,
            total_batch_bytes=total_batch_bytes,
            largest_event_bytes=largest_event_bytes,
            smallest_event_bytes=smallest_event_bytes,
            average_event_bytes=average_event_bytes,
            overhead_percentage=overhead_percentage
        )

    @classmethod
    def calculate_optimal_batch_size(
        cls,
        average_event_size: int,
        include_overhead: bool = True
    ) -> Tuple[int, int]:
        """
        Calculate optimal batch size given average event size.

        Args:
            average_event_size: Average size of events in bytes (message only)
            include_overhead: Whether to include 26-byte overhead in calculations

        Returns:
            Tuple of (max_events_by_size, max_events_by_count)
        """
        if include_overhead:
            effective_event_size = average_event_size + cls.CW_OVERHEAD_BYTES_PER_EVENT
        else:
            effective_event_size = average_event_size

        # Calculate max events based on size limit
        if effective_event_size <= 0:
            max_events_by_size = 0
        else:
            max_events_by_size = cls.CW_MAX_BATCH_SIZE_BYTES // effective_event_size

        # CloudWatch also has a 1000 event limit per batch
        max_events_by_count = cls.CW_MAX_EVENTS_PER_BATCH

        return min(max_events_by_size, max_events_by_count), max_events_by_count

    @classmethod
    def generate_size_report(cls, batch_analysis: BatchSizeAnalysis) -> str:
        """
        Generate a human-readable report of batch size analysis.

        Args:
            batch_analysis: BatchSizeAnalysis object

        Returns:
            Formatted string report
        """
        report_lines = [
            "=== CloudWatch Batch Size Analysis ===",
            f"Event Count: {batch_analysis.event_count:,}",
            f"Total Message Bytes: {batch_analysis.total_message_bytes:,}",
            f"Total Overhead Bytes: {batch_analysis.total_overhead_bytes:,} ({batch_analysis.overhead_percentage:.1f}%)",
            f"Total Batch Bytes: {batch_analysis.total_batch_bytes:,}",
            "",
            f"CloudWatch Limit: {batch_analysis.cloudwatch_limit_bytes:,} bytes",
            f"Capacity Used: {batch_analysis.capacity_utilization_percentage:.1f}%",
            f"Remaining Capacity: {batch_analysis.remaining_capacity_bytes:,} bytes",
            f"Would Exceed Limit: {'YES' if batch_analysis.would_exceed_limit else 'NO'}",
            "",
            f"Largest Event: {batch_analysis.largest_event_bytes:,} bytes",
            f"Smallest Event: {batch_analysis.smallest_event_bytes:,} bytes",
            f"Average Event: {batch_analysis.average_event_bytes:.1f} bytes",
            "",
            "=== Overhead Impact Analysis ===",
            f"Per-event overhead: {cls.CW_OVERHEAD_BYTES_PER_EVENT} bytes",
            f"Total overhead impact: {batch_analysis.total_overhead_bytes:,} bytes",
            f"Overhead as % of batch: {batch_analysis.overhead_percentage:.1f}%"
        ]

        return "\n".join(report_lines)

    @classmethod
    def find_problematic_scenarios(cls, events: List[Dict[str, Any]]) -> List[str]:
        """
        Identify potentially problematic scenarios in the event batch.

        Args:
            events: List of CloudWatch log events

        Returns:
            List of warning messages about potential issues
        """
        warnings = []

        if not events:
            return warnings

        batch_analysis = cls.analyze_batch(events)

        # Check for high overhead scenarios
        if batch_analysis.overhead_percentage > 50:
            warnings.append(
                f"HIGH OVERHEAD WARNING: {batch_analysis.overhead_percentage:.1f}% of batch size is CloudWatch overhead. "
                f"Consider using larger messages to improve efficiency."
            )

        # Check for approaching size limits
        if batch_analysis.capacity_utilization_percentage > 90:
            warnings.append(
                f"SIZE LIMIT WARNING: Batch uses {batch_analysis.capacity_utilization_percentage:.1f}% of CloudWatch limit. "
                f"Risk of exceeding 1MB limit."
            )

        # Check for very small events where overhead dominates
        small_event_threshold = 50  # bytes
        small_events = [cls.analyze_event(event) for event in events
                       if cls.analyze_event(event).message_bytes < small_event_threshold]

        if small_events and len(small_events) > len(events) * 0.5:
            warnings.append(
                f"SMALL EVENTS WARNING: {len(small_events)} events ({len(small_events)/len(events)*100:.1f}%) "
                f"have messages under {small_event_threshold} bytes. Overhead impact is significant."
            )

        # Check for events approaching individual size limits
        large_event_threshold = 1000000  # ~1MB
        large_events = [event for event in events
                       if cls.analyze_event(event).total_bytes > large_event_threshold]

        if large_events:
            warnings.append(
                f"LARGE EVENTS WARNING: {len(large_events)} events exceed {large_event_threshold:,} bytes. "
                f"Risk of hitting individual event size limits."
            )

        return warnings


def print_batch_analysis(events: List[Dict[str, Any]], title: str = "Batch Analysis"):
    """
    Convenience function to print comprehensive batch analysis.

    Args:
        events: List of CloudWatch log events to analyze
        title: Title for the analysis report
    """
    print(f"\n{title}")
    print("=" * len(title))

    analyzer = PayloadAnalyzer()
    batch_analysis = analyzer.analyze_batch(events)

    print(analyzer.generate_size_report(batch_analysis))

    warnings = analyzer.find_problematic_scenarios(events)
    if warnings:
        print("\n=== WARNINGS ===")
        for warning in warnings:
            print(f"⚠️  {warning}")

    print()


if __name__ == "__main__":
    # Example usage and testing
    print("CloudWatch Payload Analyzer - Example Usage")

    # Example 1: Many small events
    small_events = [
        {'timestamp': 1640995200000 + i, 'message': f'Small event {i}'}
        for i in range(100)
    ]

    print_batch_analysis(small_events, "Example 1: Many Small Events")

    # Example 2: Few large events
    large_events = [
        {'timestamp': 1640995200000 + i, 'message': 'X' * 100000}
        for i in range(5)
    ]

    print_batch_analysis(large_events, "Example 2: Few Large Events")

    # Example 3: Mixed sizes
    mixed_events = [
        {'timestamp': 1640995200000, 'message': 'tiny'},
        {'timestamp': 1640995200001, 'message': 'medium message here'},
        {'timestamp': 1640995200002, 'message': 'X' * 10000},
        {'timestamp': 1640995200003, 'message': 'small'},
    ]

    print_batch_analysis(mixed_events, "Example 3: Mixed Event Sizes")