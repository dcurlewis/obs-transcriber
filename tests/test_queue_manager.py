"""
Test suite for QueueManager class

Tests cover:
- CSV handling with special characters in meeting names
- Backwards compatibility with legacy semicolon-delimited format
- File locking with timeout for concurrent access
- Atomic writes with backup creation
- Validation with clear error messages
"""

import csv
import os
import tempfile
import time
import threading
from pathlib import Path

import pytest

from scripts.queue_manager import QueueManager


@pytest.fixture
def temp_queue_file():
    """Create a temporary queue file for testing"""
    fd, path = tempfile.mkstemp(suffix='.csv')
    os.close(fd)
    queue_path = Path(path)
    yield queue_path
    # Cleanup
    if queue_path.exists():
        queue_path.unlink()
    backup_path = queue_path.with_suffix('.csv.bak')
    if backup_path.exists():
        backup_path.unlink()


class TestWriteReadNewFormat:
    """Test writing and reading new CSV format with header"""

    def test_write_read_roundtrip(self, temp_queue_file):
        """Write entries with header, read back, assert equality"""
        manager = QueueManager(temp_queue_file)

        entries = [
            {
                'path': '/path/to/recording.mkv',
                'name': 'Test Meeting',
                'date': '20260207',
                'status': 'recorded',
                'attendees': 'alice@example.com|bob@example.com',
                'duration': '3600',
                'size': '1048576',
                'error': '',
                'processing_time': ''
            }
        ]

        manager.write_queue(entries)
        result = manager.read_queue()

        assert len(result) == 1
        assert result[0]['name'] == 'Test Meeting'
        assert result[0]['attendees'] == 'alice@example.com|bob@example.com'

    def test_header_present(self, temp_queue_file):
        """Verify header row is written"""
        manager = QueueManager(temp_queue_file)

        entries = [{'path': '/test', 'name': 'Test', 'date': '20260207',
                   'status': 'recorded', 'attendees': '', 'duration': '',
                   'size': '', 'error': '', 'processing_time': ''}]

        manager.write_queue(entries)

        # Read raw file and check first line
        with open(temp_queue_file, 'r') as f:
            first_line = f.readline()
            assert 'path' in first_line.lower()
            assert 'name' in first_line.lower()
            assert 'status' in first_line.lower()


class TestSpecialCharactersInNames:
    """Test handling of special characters in meeting names"""

    def test_semicolon_in_name(self, temp_queue_file):
        """Meeting names with semicolons should be properly quoted"""
        manager = QueueManager(temp_queue_file)

        entries = [{
            'path': '/test.mkv',
            'name': 'Meeting with Bob; Also: Alice',
            'date': '20260207',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]

        manager.write_queue(entries)
        result = manager.read_queue()

        assert result[0]['name'] == 'Meeting with Bob; Also: Alice'

    def test_quotes_in_name(self, temp_queue_file):
        """Meeting names with embedded quotes should be escaped correctly"""
        manager = QueueManager(temp_queue_file)

        entries = [{
            'path': '/test.mkv',
            'name': 'Project "Alpha" Review',
            'date': '20260207',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]

        manager.write_queue(entries)
        result = manager.read_queue()

        assert result[0]['name'] == 'Project "Alpha" Review'

    def test_multiple_special_characters(self, temp_queue_file):
        """Names with semicolons, quotes, commas, and pipes"""
        manager = QueueManager(temp_queue_file)

        entries = [{
            'path': '/test.mkv',
            'name': 'Meeting; Bob|Alice: "Project Alpha", Review',
            'date': '20260207',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]

        manager.write_queue(entries)
        result = manager.read_queue()

        assert result[0]['name'] == 'Meeting; Bob|Alice: "Project Alpha", Review'


class TestLegacyFormatCompatibility:
    """Test backwards compatibility with legacy semicolon-delimited format"""

    def test_read_legacy_format_4_fields(self, temp_queue_file):
        """Legacy format: semicolon-delimited, no header, 4 fields"""
        # Write legacy format directly
        with open(temp_queue_file, 'w') as f:
            f.write('/path/to/file.mkv;Meeting Name;20260207;recorded\n')

        manager = QueueManager(temp_queue_file)
        result = manager.read_queue()

        assert len(result) == 1
        assert result[0]['path'] == '/path/to/file.mkv'
        assert result[0]['name'] == 'Meeting Name'
        assert result[0]['date'] == '20260207'
        assert result[0]['status'] == 'recorded'
        assert result[0]['attendees'] == ''  # Should default to empty
        assert result[0]['duration'] == ''
        assert result[0]['size'] == ''
        assert result[0]['error'] == ''
        assert result[0]['processing_time'] == ''

    def test_read_legacy_format_5_fields(self, temp_queue_file):
        """Legacy format with attendees field (5 fields)"""
        # Write legacy format with attendees
        with open(temp_queue_file, 'w') as f:
            f.write('/path/to/file.mkv;Meeting Name;20260207;recorded;alice@example.com\n')

        manager = QueueManager(temp_queue_file)
        result = manager.read_queue()

        assert len(result) == 1
        assert result[0]['attendees'] == 'alice@example.com'
        assert result[0]['duration'] == ''  # New fields default to empty

    def test_migrate_legacy_to_new_format(self, temp_queue_file):
        """Reading legacy, then writing should upgrade to new format"""
        # Write legacy format
        with open(temp_queue_file, 'w') as f:
            f.write('/path/to/file.mkv;Meeting Name;20260207;recorded\n')

        manager = QueueManager(temp_queue_file)
        entries = manager.read_queue()

        # Write back (should upgrade to new format)
        manager.write_queue(entries)

        # Verify header exists
        with open(temp_queue_file, 'r') as f:
            first_line = f.readline()
            assert 'path' in first_line.lower()


class TestFileLocking:
    """Test file locking prevents concurrent access corruption"""

    def test_concurrent_writes_dont_corrupt(self, temp_queue_file):
        """Multiple threads writing should be serialized by locks"""
        manager = QueueManager(temp_queue_file)

        # Initialize with empty queue
        manager.write_queue([])

        results = []
        errors = []

        def write_entry(thread_id):
            try:
                # Each thread reads, adds entry, writes back
                entries = manager.read_queue()
                entries.append({
                    'path': f'/test{thread_id}.mkv',
                    'name': f'Thread {thread_id}',
                    'date': '20260207',
                    'status': 'recorded',
                    'attendees': '',
                    'duration': '',
                    'size': '',
                    'error': '',
                    'processing_time': ''
                })
                manager.write_queue(entries)
                results.append(thread_id)
            except Exception as e:
                errors.append(str(e))

        # Launch 5 concurrent writers
        threads = []
        for i in range(5):
            t = threading.Thread(target=write_entry, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # Verify all writes succeeded
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5

        # Verify queue has all 5 entries
        final_entries = manager.read_queue()
        assert len(final_entries) == 5

    def test_lock_timeout(self, temp_queue_file):
        """Lock timeout should raise TimeoutError after 5 seconds"""
        manager = QueueManager(temp_queue_file)

        # Initialize queue
        manager.write_queue([])

        # Thread 1: Hold lock for 6 seconds (exceeds 5s timeout)
        def hold_lock_long():
            with manager._lock('r+') as f:
                time.sleep(6)

        # Thread 2: Try to acquire lock (should timeout)
        timeout_occurred = []

        def try_acquire_lock():
            try:
                manager.read_queue()
            except TimeoutError as e:
                timeout_occurred.append(str(e))

        t1 = threading.Thread(target=hold_lock_long)
        t1.start()

        # Wait a bit to ensure t1 has the lock
        time.sleep(0.5)

        t2 = threading.Thread(target=try_acquire_lock)
        t2.start()

        t2.join()
        t1.join()

        # Verify timeout occurred
        assert len(timeout_occurred) == 1
        assert 'lock' in timeout_occurred[0].lower()
        assert 'timeout' in timeout_occurred[0].lower() or '5' in timeout_occurred[0]


class TestAtomicWrites:
    """Test atomic writes with backup creation"""

    def test_backup_created_before_write(self, temp_queue_file):
        """Writing should create .bak file with previous content"""
        manager = QueueManager(temp_queue_file)

        # Write initial data
        entries1 = [{
            'path': '/test1.mkv',
            'name': 'Meeting 1',
            'date': '20260207',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]
        manager.write_queue(entries1)

        # Write new data (should backup old)
        entries2 = [{
            'path': '/test2.mkv',
            'name': 'Meeting 2',
            'date': '20260208',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]
        manager.write_queue(entries2)

        # Verify backup exists
        backup_path = temp_queue_file.with_suffix('.csv.bak')
        assert backup_path.exists()

        # Verify backup contains old data
        with open(backup_path, 'r') as f:
            reader = csv.DictReader(f)
            backup_entries = list(reader)
            assert len(backup_entries) == 1
            assert backup_entries[0]['name'] == 'Meeting 1'

    def test_crash_simulation_leaves_queue_intact(self, temp_queue_file):
        """If write crashes mid-operation, original queue should be unchanged"""
        manager = QueueManager(temp_queue_file)

        # Write initial data
        initial_entries = [{
            'path': '/test.mkv',
            'name': 'Original',
            'date': '20260207',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]
        manager.write_queue(initial_entries)

        # Simulate crash by trying to write invalid data
        # (This should fail during write, not corrupt queue)
        try:
            # Create invalid entries that might cause write to fail
            invalid_entries = [{'invalid': 'data'}]  # Missing required fields
            manager.write_queue(invalid_entries)
        except (KeyError, ValueError):
            pass  # Expected to fail

        # Original queue should still be readable and intact
        result = manager.read_queue()
        assert len(result) == 1
        assert result[0]['name'] == 'Original'


class TestValidation:
    """Test validation with clear error messages"""

    def test_validation_missing_required_field(self, temp_queue_file):
        """Missing required field should raise ValueError with line number"""
        manager = QueueManager(temp_queue_file)

        # Write entry missing 'status'
        with open(temp_queue_file, 'w') as f:
            writer = csv.DictWriter(f, fieldnames=['path', 'name', 'date'])
            writer.writeheader()
            writer.writerow({'path': '/test.mkv', 'name': 'Test', 'date': '20260207'})

        with pytest.raises(ValueError) as exc_info:
            manager.validate()

        error_msg = str(exc_info.value)
        assert 'line' in error_msg.lower()
        assert 'status' in error_msg.lower() or 'required' in error_msg.lower()

    def test_validation_invalid_status(self, temp_queue_file):
        """Invalid status should raise ValueError with valid options"""
        manager = QueueManager(temp_queue_file)

        # Write entry with invalid status
        entries = [{
            'path': '/test.mkv',
            'name': 'Test',
            'date': '20260207',
            'status': 'invalid_status',  # Not in VALID_STATUSES
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]
        manager.write_queue(entries)

        with pytest.raises(ValueError) as exc_info:
            manager.validate()

        error_msg = str(exc_info.value)
        assert 'status' in error_msg.lower()
        assert 'recorded' in error_msg.lower()  # Should list valid options
        assert 'processed' in error_msg.lower()
        assert 'discarded' in error_msg.lower()

    def test_validation_passes_for_valid_queue(self, temp_queue_file):
        """Valid queue should pass validation"""
        manager = QueueManager(temp_queue_file)

        entries = [{
            'path': '/test.mkv',
            'name': 'Test',
            'date': '20260207',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]
        manager.write_queue(entries)

        # Should not raise
        assert manager.validate() == True

    def test_validation_provides_recovery_instructions(self, temp_queue_file):
        """Validation error should include recovery instructions"""
        manager = QueueManager(temp_queue_file)

        # Write corrupted queue
        with open(temp_queue_file, 'w') as f:
            f.write('corrupted,data\n')

        with pytest.raises(ValueError) as exc_info:
            manager.validate()

        error_msg = str(exc_info.value)
        # Should mention backup file
        assert 'backup' in error_msg.lower() or '.bak' in error_msg.lower()
        # Should provide recovery steps
        assert 'recover' in error_msg.lower() or 'fix' in error_msg.lower()


class TestEmptyQueue:
    """Test handling of empty/nonexistent queue files"""

    def test_read_nonexistent_queue(self, temp_queue_file):
        """Reading nonexistent queue should return empty list"""
        temp_queue_file.unlink()  # Remove file

        manager = QueueManager(temp_queue_file)
        result = manager.read_queue()

        assert result == []

    def test_write_to_nonexistent_queue(self, temp_queue_file):
        """Writing to nonexistent queue should create it"""
        temp_queue_file.unlink()  # Remove file

        manager = QueueManager(temp_queue_file)
        entries = [{
            'path': '/test.mkv',
            'name': 'Test',
            'date': '20260207',
            'status': 'recorded',
            'attendees': '',
            'duration': '',
            'size': '',
            'error': '',
            'processing_time': ''
        }]

        manager.write_queue(entries)

        assert temp_queue_file.exists()
        result = manager.read_queue()
        assert len(result) == 1
