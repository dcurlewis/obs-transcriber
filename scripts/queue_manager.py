"""
Queue Manager for OBS Meeting Transcriber

Manages the processing queue with:
- CSV handling with proper quoting for special characters
- Backwards compatibility with legacy semicolon-delimited format
- File locking to prevent concurrent access corruption
- Atomic writes with automatic backup creation
- Validation with detailed error messages and recovery instructions

Usage:
    from scripts.queue_manager import QueueManager

    manager = QueueManager('processing_queue.csv')

    # Read queue (handles both legacy and new formats)
    entries = manager.read_queue()

    # Write queue (atomic with backup)
    manager.write_queue(entries)

    # Validate queue structure
    manager.validate()
"""

import csv
import errno
import fcntl
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List


class QueueManager:
    """Manages processing queue with file locking and atomic writes"""

    # CSV schema - all required fields
    FIELDNAMES = [
        'path',              # Path to MKV recording file
        'name',              # Meeting name
        'date',              # Recording date (YYYYMMDD format)
        'status',            # Processing status
        'attendees',         # Pipe-separated attendee emails
        'duration',          # Recording duration in seconds
        'size',              # File size in bytes
        'error',             # Error message if processing failed
        'processing_time'    # Time taken to process in seconds
    ]

    # Valid status values
    VALID_STATUSES = {'recorded', 'processed', 'discarded'}

    # Lock acquisition timeout in seconds
    LOCK_TIMEOUT = 5

    def __init__(self, queue_path: Path):
        """
        Initialize QueueManager

        Args:
            queue_path: Path to the queue CSV file
        """
        self.queue_path = Path(queue_path)
        self.backup_path = self.queue_path.with_suffix('.csv.bak')

    @contextmanager
    def _lock(self, mode='r'):
        """
        Context manager for locked queue access with retry and timeout

        Args:
            mode: File open mode ('r' for read, 'r+' for write)

        Yields:
            file: Opened and locked file handle

        Raises:
            TimeoutError: If lock cannot be acquired within LOCK_TIMEOUT seconds
        """
        # Determine lock type based on mode
        lock_type = fcntl.LOCK_SH if mode == 'r' else fcntl.LOCK_EX

        # Ensure parent directory exists
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

        # Create file if it doesn't exist (for write mode)
        if not self.queue_path.exists() and 'r' not in mode:
            self.queue_path.touch()

        f = open(self.queue_path, mode, newline='', encoding='utf-8')
        start_time = time.time()

        try:
            # Try to acquire lock with retry
            while True:
                try:
                    fcntl.flock(f.fileno(), lock_type | fcntl.LOCK_NB)
                    break  # Lock acquired
                except OSError as e:
                    if e.errno not in (errno.EACCES, errno.EAGAIN):
                        raise

                    # Check timeout
                    if time.time() - start_time > self.LOCK_TIMEOUT:
                        raise TimeoutError(
                            f"Could not acquire lock on {self.queue_path} within {self.LOCK_TIMEOUT}s. "
                            f"Another process may be accessing the queue."
                        )

                    # Wait before retry
                    time.sleep(0.1)

            yield f

        finally:
            # Release lock and close file
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except:
                pass
            f.close()

    def _parse_entries_from_file(self, f) -> List[Dict[str, str]]:
        """
        Parse queue entries from an open file handle

        Internal helper to avoid code duplication between read_queue and atomic_update.

        Args:
            f: Open file handle positioned at start

        Returns:
            List of queue entries

        Raises:
            csv.Error: If CSV parsing fails
        """
        # Detect format by checking first line
        first_line = f.readline()
        f.seek(0)

        has_header = (
            'path' in first_line.lower() and
            'status' in first_line.lower()
        ) if first_line else False

        entries = []

        if has_header:
            # New format: CSV with DictReader
            reader = csv.DictReader(f)
            for row in reader:
                # Fill missing fields with defaults
                entry = {field: row.get(field, '') for field in self.FIELDNAMES}
                entries.append(entry)
        elif first_line:
            # Legacy format: semicolon-delimited, no header
            reader = csv.reader(f, delimiter=';')
            for row in reader:
                if len(row) < 4:
                    continue  # Skip malformed rows

                # Map legacy fields to new schema
                entry = {
                    'path': row[0],
                    'name': row[1],
                    'date': row[2],
                    'status': row[3],
                    'attendees': row[4] if len(row) > 4 else '',
                    'duration': '',
                    'size': '',
                    'error': '',
                    'processing_time': ''
                }
                entries.append(entry)

        return entries

    def read_queue(self) -> List[Dict[str, str]]:
        """
        Read queue with backwards compatibility for legacy format

        Supports:
        - New format: CSV with header, 9 fields
        - Legacy format: Semicolon-delimited, no header, 4-5 fields

        Returns:
            List of queue entries as dictionaries with all 9 fields

        Raises:
            ValueError: If CSV parsing fails (corrupted queue)
        """
        if not self.queue_path.exists():
            return []

        with self._lock('r') as f:
            try:
                return self._parse_entries_from_file(f)
            except csv.Error as e:
                raise ValueError(
                    f"CSV parsing error in {self.queue_path}: {e}\n"
                    f"Queue file may be corrupted. Check {self.backup_path} for last good state.\n"
                    f"To recover: cp {self.backup_path} {self.queue_path}"
                )

    def write_queue(self, entries: List[Dict[str, str]]):
        """
        Write queue atomically with backup

        Process:
        1. Write to temporary file in same directory
        2. Acquire exclusive lock
        3. Backup existing queue
        4. Atomically replace queue with temp file

        Args:
            entries: List of queue entries as dictionaries

        Raises:
            KeyError: If entries are missing required fields
            OSError: If file operations fail
        """
        # Create temp file in same directory (for atomic rename)
        with tempfile.NamedTemporaryFile(
            mode='w',
            delete=False,
            dir=self.queue_path.parent,
            suffix='.tmp',
            newline='',
            encoding='utf-8'
        ) as tmp:
            tmp_path = tmp.name

            try:
                # Write to temp file with CSV quoting
                writer = csv.DictWriter(
                    tmp,
                    fieldnames=self.FIELDNAMES,
                    quoting=csv.QUOTE_MINIMAL
                )
                writer.writeheader()
                writer.writerows(entries)
                tmp.flush()
                os.fsync(tmp.fileno())

            except Exception as e:
                # Clean up temp file on error
                os.unlink(tmp_path)
                raise

        # Acquire exclusive lock for backup + replace
        # Note: We need to ensure file exists before locking
        if not self.queue_path.exists():
            self.queue_path.touch()

        with self._lock('r+'):
            # Backup existing file
            if self.queue_path.exists() and self.queue_path.stat().st_size > 0:
                shutil.copy2(self.queue_path, self.backup_path)

            # Atomic replace
            os.replace(tmp_path, self.queue_path)

    @contextmanager
    def atomic_update(self):
        """
        Context manager for atomic read-modify-write operations

        Acquires exclusive lock, reads current queue, yields entries for modification,
        then writes back atomically. The lock is held throughout the entire operation
        to prevent concurrent modifications.

        Usage:
            with manager.atomic_update() as entries:
                entries.append(new_entry)
                # Modifications are automatically written back

        Yields:
            list: Current queue entries (mutable list)
        """
        # Ensure file exists before locking
        if not self.queue_path.exists():
            self.queue_path.touch()

        # Acquire exclusive lock for entire read-modify-write operation
        with self._lock('r+') as f:
            # Read current queue using shared parsing logic
            try:
                entries = self._parse_entries_from_file(f)
            except csv.Error as e:
                raise ValueError(f"CSV parsing error: {e}")

            # Yield entries for modification (lock still held)
            yield entries

            # Write back modifications (still under same lock)
            # Backup current content before writing
            f.seek(0)
            current_content = f.read()
            if current_content:
                with open(self.backup_path, 'w', encoding='utf-8') as backup:
                    backup.write(current_content)

            # Truncate and write new content to same file (keeps lock valid)
            f.seek(0)
            f.truncate()

            writer = csv.DictWriter(
                f,
                fieldnames=self.FIELDNAMES,
                quoting=csv.QUOTE_MINIMAL
            )
            writer.writeheader()
            writer.writerows(entries)
            f.flush()
            os.fsync(f.fileno())

    def validate(self) -> bool:
        """
        Validate queue structure

        Checks:
        - CSV parsing succeeds
        - Required fields present (path, name, status)
        - Status values are valid

        Returns:
            True if validation passes

        Raises:
            ValueError: If validation fails, with detailed error message
                       including line number, issue, and recovery instructions
        """
        if not self.queue_path.exists():
            return True  # Empty queue is valid

        try:
            # Read and parse file strictly (don't use lenient read_queue)
            with self._lock('r') as f:
                # Try to detect format
                first_line = f.readline()
                f.seek(0)

                has_header = (
                    'path' in first_line.lower() and
                    'status' in first_line.lower()
                )

                if has_header:
                    # Validate new format
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader):
                        # Check required fields are present and non-empty
                        if not row.get('path') or not row.get('name') or not row.get('status'):
                            raise ValueError(
                                f"Line {i+2}: Missing required field (path, name, or status)\n"
                                f"Entry: {row}"
                            )

                        # Check status is valid
                        if row['status'] not in self.VALID_STATUSES:
                            raise ValueError(
                                f"Line {i+2}: Invalid status '{row['status']}'\n"
                                f"Valid statuses: {', '.join(sorted(self.VALID_STATUSES))}\n"
                                f"Entry: {row}"
                            )
                else:
                    # Validate legacy format
                    reader = csv.reader(f, delimiter=';')
                    for i, row in enumerate(reader):
                        if len(row) < 4:
                            raise ValueError(
                                f"Line {i+1}: Invalid legacy format (needs at least 4 fields: path, name, date, status)\n"
                                f"Got {len(row)} fields: {row}"
                            )

                        # Check status (4th field)
                        status = row[3]
                        if status not in self.VALID_STATUSES:
                            raise ValueError(
                                f"Line {i+1}: Invalid status '{status}'\n"
                                f"Valid statuses: {', '.join(sorted(self.VALID_STATUSES))}\n"
                                f"Entry: {row}"
                            )

            return True

        except ValueError as e:
            # Wrap validation errors with recovery instructions
            raise ValueError(
                f"{str(e)}\n\n"
                f"Recovery instructions:\n"
                f"1. Check backup: {self.backup_path}\n"
                f"2. If backup is good: cp {self.backup_path} {self.queue_path}\n"
                f"3. If backup is also bad: manually fix {self.queue_path}\n"
                f"4. Required fields: path, name, status\n"
                f"5. Valid statuses: {', '.join(sorted(self.VALID_STATUSES))}"
            ) from e

        except Exception as e:
            # Wrap other errors with recovery instructions
            raise ValueError(
                f"Queue validation failed: {e}\n\n"
                f"Recovery instructions:\n"
                f"1. Check backup: {self.backup_path}\n"
                f"2. If backup is good: cp {self.backup_path} {self.queue_path}\n"
                f"3. If backup is also bad: manually fix {self.queue_path}\n"
                f"4. Required fields: path, name, status\n"
                f"5. Valid statuses: {', '.join(sorted(self.VALID_STATUSES))}"
            ) from e
