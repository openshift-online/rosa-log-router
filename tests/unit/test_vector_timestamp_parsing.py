"""
Unit tests for Vector timestamp parsing transforms

These tests validate the timestamp extraction logic that would be implemented
in Vector's VRL transforms by testing the parsing patterns and expected outputs.
"""
import pytest
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple


class VectorTimestampParser:
    """
    Simulates Vector's timestamp parsing logic for unit testing.
    
    This class implements the same logic as the Vector VRL transforms
    to validate parsing behavior without requiring Vector runtime.
    """
    
    def __init__(self):
        # Precompile regex patterns for performance testing
        self.iso_pattern = re.compile(r'^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?Z?)')
        self.time_equals_pattern = re.compile(r'time="(?P<timestamp>[^"]+)"')
        self.k8s_pattern = re.compile(r'^[IWEF](?P<month>\d{2})(?P<day>\d{2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<microsecond>\d{6})')
        self.go_pattern = re.compile(r'^(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})')
    
    def parse_json_logs_transform(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate the parse_json_logs VRL transform"""
        result = log_record.copy()
        
        # Extract timestamp from JSON fields with priority: ts > time
        if 'ts' in result:
            ts_value = result['ts']
            parsed_timestamp = self._parse_timestamp_value(ts_value)
            if parsed_timestamp:
                result['timestamp'] = parsed_timestamp
            # Remove ts field to avoid duplication
            del result['ts']
            
        elif 'time' in result:
            time_value = result['time']
            if isinstance(time_value, str):
                parsed_timestamp = self._parse_iso_timestamp(time_value)
                if parsed_timestamp:
                    result['timestamp'] = parsed_timestamp
            # Remove time field to avoid duplication
            del result['time']
            
        return result
    
    def parse_plain_text_timestamps_transform(self, message: str) -> Optional[datetime]:
        """Simulate the parse_plain_text_timestamps VRL transform with performance optimizations"""
        message_len = len(message)
        
        # Early exit if message is too short
        if message_len < 8:
            return None
            
        # Performance-optimized pattern matching with structural pre-filtering
        
        # 1. Kubernetes log format - Quick check: starts with log level [IWEF]
        if message_len > 20 and message[0] in 'IWEF':
            match = self.k8s_pattern.match(message)
            if match:
                return self._parse_k8s_timestamp(match.groupdict())
        
        # 2. time="timestamp" format - Quick check: contains 'time="'
        elif 'time="' in message:
            match = self.time_equals_pattern.search(message)
            if match:
                return self._parse_iso_timestamp(match.group('timestamp'))
        
        # 3. Direct ISO timestamp - Quick check: has dashes at positions 4,7 and T around position 10
        elif (message_len > 19 and 
              message[4] == '-' and 
              message[7] == '-' and 
              message[10] == 'T'):
            match = self.iso_pattern.match(message)
            if match:
                return self._parse_iso_timestamp(match.group('timestamp'))
        
        # 4. Go standard log format - Quick check: has slashes at positions 4,7
        elif (message_len > 18 and 
              message[4] == '/' and 
              message[7] == '/'):
            match = self.go_pattern.match(message)
            if match:
                return self._parse_go_timestamp(match.groupdict())
        
        return None
    
    def _parse_timestamp_value(self, ts_value: Any) -> Optional[datetime]:
        """Parse timestamp value from various formats"""
        if isinstance(ts_value, str):
            # Try ISO format first
            parsed = self._parse_iso_timestamp(ts_value)
            if parsed:
                return parsed
            
            # Try Unix timestamp in string format
            try:
                unix_ts = float(ts_value)
                return self._parse_unix_timestamp(unix_ts)
            except ValueError:
                return None
                
        elif isinstance(ts_value, (int, float)):
            return self._parse_unix_timestamp(ts_value)
        
        return None
    
    def _parse_iso_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse ISO format timestamp"""
        try:
            # Handle timezone-aware parsing
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            elif '+' not in timestamp_str and timestamp_str.count(':') == 2:
                timestamp_str += '+00:00'
            
            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            return None
    
    def _parse_unix_timestamp(self, unix_ts: float) -> Optional[datetime]:
        """Parse Unix timestamp (seconds or milliseconds)"""
        try:
            if unix_ts < 1000000000000:  # Seconds
                return datetime.fromtimestamp(unix_ts, tz=timezone.utc)
            else:  # Milliseconds
                return datetime.fromtimestamp(unix_ts / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    
    def _parse_k8s_timestamp(self, groups: Dict[str, str]) -> Optional[datetime]:
        """Parse Kubernetes log format timestamp"""
        try:
            current_year = datetime.now().year
            month = int(groups['month'])
            day = int(groups['day'])
            hour = int(groups['hour'])
            minute = int(groups['minute'])
            second = int(groups['second'])
            # Convert microseconds to milliseconds (first 3 digits)
            microsecond = int(groups['microsecond'][:3]) * 1000
            
            return datetime(
                year=current_year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=second,
                microsecond=microsecond,
                tzinfo=timezone.utc
            )
        except (ValueError, KeyError):
            return None
    
    def _parse_go_timestamp(self, groups: Dict[str, str]) -> Optional[datetime]:
        """Parse Go standard log format timestamp"""
        try:
            year = int(groups['year'])
            month = int(groups['month'])
            day = int(groups['day'])
            hour = int(groups['hour'])
            minute = int(groups['minute'])
            second = int(groups['second'])
            
            return datetime(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=second,
                tzinfo=timezone.utc
            )
        except (ValueError, KeyError):
            return None


class TestJSONTimestampParsing:
    """Test JSON log timestamp parsing (parse_json_logs transform)"""
    
    def setup_method(self):
        self.parser = VectorTimestampParser()
    
    def test_json_ts_field_iso_format(self):
        """Test parsing 'ts' field with ISO timestamp"""
        log_record = {
            "ts": "2025-08-30T06:11:26.816Z",
            "level": "info",
            "msg": "etcd request processed",
            "message": "original message"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        assert 'ts' not in result  # Field should be removed
        assert result['timestamp'] is not None
        assert result['timestamp'].year == 2025
        assert result['timestamp'].month == 8
        assert result['timestamp'].day == 30
        assert result['message'] == "original message"
    
    def test_json_ts_field_unix_seconds(self):
        """Test parsing 'ts' field with Unix timestamp in seconds"""
        log_record = {
            "ts": "1724999486",  # Unix timestamp as string
            "level": "info",
            "msg": "service started"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        assert 'ts' not in result
        assert result['timestamp'] is not None
        assert result['timestamp'].year == 2024
    
    def test_json_ts_field_unix_milliseconds(self):
        """Test parsing 'ts' field with Unix timestamp in milliseconds"""
        log_record = {
            "ts": 1724999486816,  # Unix timestamp in milliseconds
            "level": "info", 
            "msg": "processing complete"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        assert 'ts' not in result
        assert result['timestamp'] is not None
        assert result['timestamp'].year == 2024
    
    def test_json_time_field(self):
        """Test parsing 'time' field as fallback"""
        log_record = {
            "time": "2025-08-30T09:21:21Z",
            "level": "INFO",
            "message": "service started",
            "service": "auth"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        assert 'time' not in result
        assert result['timestamp'] is not None
        assert result['timestamp'].hour == 9
        assert result['timestamp'].minute == 21
    
    def test_json_ts_priority_over_time(self):
        """Test that 'ts' field takes priority over 'time' field"""
        log_record = {
            "ts": "2025-08-30T06:11:26.816Z",
            "time": "2025-08-30T09:21:21Z",
            "level": "info",
            "message": "test message"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        assert 'ts' not in result
        assert 'time' in result  # time field should remain since ts was processed
        assert result['timestamp'].hour == 6  # Should use ts timestamp (6am, not 9am)
    
    def test_json_malformed_timestamp_fallback(self):
        """Test fallback behavior with malformed timestamps"""
        log_record = {
            "ts": "invalid-timestamp",
            "level": "info",
            "message": "test message"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        assert 'ts' not in result  # Field should still be removed
        assert 'timestamp' not in result  # No valid timestamp should be set
    
    def test_json_no_timestamp_fields(self):
        """Test log record without timestamp fields"""
        log_record = {
            "level": "info",
            "message": "test message",
            "service": "api"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        assert result == log_record  # Should be unchanged


class TestPlainTextTimestampParsing:
    """Test plain text log timestamp parsing (parse_plain_text_timestamps transform)"""
    
    def setup_method(self):
        self.parser = VectorTimestampParser()
    
    def test_iso_direct_timestamp(self):
        """Test direct ISO timestamp at start of message"""
        message = "2025-08-30T06:11:26.816Z Here is where my logs go."
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is not None
        assert result.year == 2025
        assert result.month == 8
        assert result.day == 30
        assert result.hour == 6
        assert result.minute == 11
        assert result.second == 26
    
    def test_time_equals_format(self):
        """Test time="..." structured format"""
        message = 'time="2025-08-30T09:21:21Z" level=info msg="connection established"'
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is not None
        assert result.hour == 9
        assert result.minute == 21
        assert result.second == 21
    
    def test_kubernetes_log_format(self):
        """Test Kubernetes log format (I0830 11:27:01.564974)"""
        message = "I0830 11:27:01.564974 1 controller.go:231] Reconciling resource"
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is not None
        assert result.month == 8
        assert result.day == 30
        assert result.hour == 11
        assert result.minute == 27
        assert result.second == 1
        assert result.microsecond == 564000  # 564 milliseconds converted to microseconds
    
    def test_kubernetes_different_log_levels(self):
        """Test Kubernetes format with different log levels"""
        test_cases = [
            "W0830 11:27:01.564974 1 manager.go:123] Warning message",
            "E0830 11:27:01.564974 1 handler.go:456] Error occurred",
            "F0830 11:27:01.564974 1 system.go:789] Fatal error"
        ]
        
        for message in test_cases:
            result = self.parser.parse_plain_text_timestamps_transform(message)
            assert result is not None
            assert result.month == 8
            assert result.day == 30
    
    def test_go_standard_format(self):
        """Test Go standard log format (2025/08/30 10:33:20)"""
        message = "2025/08/30 10:33:20 Found existing service account"
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is not None
        assert result.year == 2025
        assert result.month == 8
        assert result.day == 30
        assert result.hour == 10
        assert result.minute == 33
        assert result.second == 20
    
    def test_no_timestamp_found(self):
        """Test message with no recognizable timestamp"""
        message = "Regular log message without timestamp"
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is None
    
    def test_short_message(self):
        """Test very short message (early exit optimization)"""
        message = "short"
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is None
    
    def test_performance_optimization_kubernetes(self):
        """Test that Kubernetes format is checked first due to quick heuristics"""
        # Message that could match multiple patterns but starts with K8s pattern
        message = "I0830 11:27:01.564974 time=\"2025-08-30T09:21:21Z\" Mixed format"
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        # Should parse as Kubernetes format (11:27) not time= format (09:21)
        assert result is not None
        assert result.hour == 11
        assert result.minute == 27
    
    def test_performance_optimization_time_equals(self):
        """Test time= format detection with contains() optimization"""
        message = 'Some prefix time="2025-08-30T09:21:21Z" and suffix'
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is not None
        assert result.hour == 9
        assert result.minute == 21


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases"""
    
    def setup_method(self):
        self.parser = VectorTimestampParser()
    
    def test_malformed_iso_timestamp(self):
        """Test malformed ISO timestamp"""
        message = "2025-13-45T25:61:61.999Z Invalid timestamp"
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is None
    
    def test_malformed_kubernetes_timestamp(self):
        """Test malformed Kubernetes timestamp"""
        message = "I1340 25:61:61.999999 1 file.go:123] Invalid timestamp"
        
        result = self.parser.parse_plain_text_timestamps_transform(message)
        
        assert result is None
    
    def test_empty_message(self):
        """Test empty message"""
        result = self.parser.parse_plain_text_timestamps_transform("")
        
        assert result is None
    
    def test_json_with_non_string_time_field(self):
        """Test JSON with non-string time field"""
        log_record = {
            "time": 12345,  # Non-string time field
            "message": "test"
        }
        
        result = self.parser.parse_json_logs_transform(log_record)
        
        # Should not process non-string time field
        assert 'time' not in result or result.get('timestamp') is None


class TestTimestampPriorityAndFallback:
    """Test the overall priority hierarchy and fallback behavior"""
    
    def setup_method(self):
        self.parser = VectorTimestampParser()
    
    def test_fallback_hierarchy_documentation(self):
        """Document the expected fallback hierarchy"""
        # This test serves as documentation for the expected behavior:
        # 1. JSON 'ts' field (highest priority)
        # 2. JSON 'time' field  
        # 3. Plain text patterns (in order of performance optimization):
        #    a. Kubernetes format (starts with [IWEF])
        #    b. time="..." format (contains 'time="')
        #    c. ISO direct (dashes at positions 4,7, T at 10)
        #    d. Go format (slashes at positions 4,7)
        # 4. Vector default timestamp (fallback)
        
        # Test case where multiple patterns could match
        complex_message = {
            "ts": "2025-08-30T06:11:26.816Z",  # Should win
            "time": "2025-08-30T09:21:21Z",
            "message": "I0830 11:27:01.564974 time=\"2025-08-30T12:00:00Z\" 2025/08/30 15:30:45 complex log"
        }
        
        json_result = self.parser.parse_json_logs_transform(complex_message)
        
        # Should use 'ts' field (6am), not any other timestamp
        assert json_result['timestamp'].hour == 6
        
        # For plain text, should use first matching pattern (Kubernetes format)
        plain_text_result = self.parser.parse_plain_text_timestamps_transform(
            "I0830 11:27:01.564974 time=\"2025-08-30T12:00:00Z\" 2025/08/30 15:30:45 complex log"
        )
        
        # Should use Kubernetes format (11:27), not time= (12:00) or Go (15:30)
        assert plain_text_result.hour == 11
        assert plain_text_result.minute == 27


class TestVectorIntegrationScenarios:
    """Test scenarios that would occur in real Vector processing"""
    
    def setup_method(self):
        self.parser = VectorTimestampParser()
    
    def test_etcd_log_processing(self):
        """Test processing etcd-style logs"""
        etcd_log = {
            "ts": "2025-08-30T06:11:26.816Z",
            "level": "info",
            "msg": "etcd request processed successfully",
            "component": "etcd-server",
            "took": "1.2ms"
        }
        
        result = self.parser.parse_json_logs_transform(etcd_log)
        
        assert 'ts' not in result
        assert result['timestamp'] is not None
        assert result['component'] == "etcd-server"
        assert result['msg'] == "etcd request processed successfully"
    
    def test_openshift_control_plane_log(self):
        """Test processing OpenShift control plane logs"""
        k8s_log = "I0830 09:47:51.241925 1 controller.go:231] Successfully reconciled namespace/default"
        
        result = self.parser.parse_plain_text_timestamps_transform(k8s_log)
        
        assert result is not None
        assert result.month == 8
        assert result.day == 30
        assert result.hour == 9
        assert result.minute == 47
    
    def test_mixed_log_formats_in_batch(self):
        """Test processing a batch with mixed timestamp formats"""
        test_logs = [
            {"ts": "2025-08-30T06:11:26.816Z", "msg": "JSON with ts"},
            {"time": "2025-08-30T06:12:00Z", "msg": "JSON with time"},
            "2025-08-30T06:13:00Z Direct ISO message",
            'time="2025-08-30T06:14:00Z" level=info msg="Structured format"',
            "I0830 06:15:00.123456 1 file.go:123] Kubernetes format",
            "2025/08/30 06:16:00 Go standard format"
        ]
        
        timestamps = []
        for log in test_logs:
            if isinstance(log, dict):
                result = self.parser.parse_json_logs_transform(log)
                timestamps.append(result.get('timestamp'))
            else:
                timestamp = self.parser.parse_plain_text_timestamps_transform(log)
                timestamps.append(timestamp)
        
        # All should parse successfully
        assert all(ts is not None for ts in timestamps)
        
        # Should have sequential minutes (11, 12, 13, 14, 15, 16)
        minutes = [ts.minute for ts in timestamps]
        assert minutes == [11, 12, 13, 14, 15, 16]


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])