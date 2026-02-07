#!/usr/bin/env python3
"""
CLI wrapper for queue operations used by run.sh

Provides command-line interface to QueueManager for all queue operations:
- add: Add new recording entry to queue
- update: Update status/error/processing_time for existing entry
- list: List queue entries (with optional status filter)
- discard: Mark entry as discarded

Usage examples:
    queue_cli.py add "/path/to/recording.mkv" "Meeting Name" "20260207_1000" "recorded" "attendees@example.com"
    queue_cli.py update "/path/to/recording.mkv" "processed" "" "120.5"
    queue_cli.py list
    queue_cli.py list recorded
    queue_cli.py discard "/path/to/recording.mkv"
"""

import sys
import json
from pathlib import Path
from root_detection import find_project_root
from queue_manager import QueueManager


def main():
    """Main entry point for CLI"""
    # Check dependencies before any operations
    from dependencies import check_dependencies
    check_dependencies()

    # Get project root using centralized root detection
    project_root = find_project_root()
    queue_path = project_root / 'processing_queue.csv'
    manager = QueueManager(queue_path)

    # Validate queue at startup per user decision
    try:
        manager.validate()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse command
    if len(sys.argv) < 2:
        print("Usage: queue_cli.py <command> [args]", file=sys.stderr)
        print("Commands: add, update, list, discard", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    # Dispatch commands
    try:
        if command == 'add':
            # Usage: queue_cli.py add <path> <name> <date> <status> [attendees]
            add_entry(manager, sys.argv[2:])
        elif command == 'update':
            # Usage: queue_cli.py update <path> <status> [error] [processing_time]
            update_status(manager, sys.argv[2:])
        elif command == 'list':
            # Usage: queue_cli.py list [status_filter]
            list_queue(manager, sys.argv[2:])
        elif command == 'discard':
            # Usage: queue_cli.py discard <path>
            discard_entry(manager, sys.argv[2:])
        else:
            print(f"Unknown command: {command}", file=sys.stderr)
            print("Valid commands: add, update, list, discard", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def add_entry(manager: QueueManager, args: list):
    """
    Add new entry to queue

    Args:
        manager: QueueManager instance
        args: [path, name, date, status, attendees (optional)]
    """
    if len(args) < 4:
        print("Usage: queue_cli.py add <path> <name> <date> <status> [attendees]", file=sys.stderr)
        sys.exit(1)

    path = args[0]
    name = args[1]
    date = args[2]
    status = args[3]
    attendees = args[4] if len(args) > 4 else ''

    # Create entry dict with all 9 fields
    entry = {
        'path': path,
        'name': name,
        'date': date,
        'status': status,
        'attendees': attendees,
        'duration': '',
        'size': '',
        'error': '',
        'processing_time': ''
    }

    # Use atomic_update to add entry
    with manager.atomic_update() as entries:
        entries.append(entry)

    print(f"Added entry: {name}", file=sys.stderr)


def update_status(manager: QueueManager, args: list):
    """
    Update status of existing entry

    Args:
        manager: QueueManager instance
        args: [path, status, error (optional), processing_time (optional)]
    """
    if len(args) < 2:
        print("Usage: queue_cli.py update <path> <status> [error] [processing_time]", file=sys.stderr)
        sys.exit(1)

    path = args[0]
    new_status = args[1]
    error = args[2] if len(args) > 2 else ''
    processing_time = args[3] if len(args) > 3 else ''

    # Find and update entry
    with manager.atomic_update() as entries:
        found = False
        for entry in entries:
            if entry['path'] == path:
                entry['status'] = new_status
                if error:
                    entry['error'] = error
                if processing_time:
                    entry['processing_time'] = processing_time
                found = True
                break

        if not found:
            raise ValueError(f"Entry not found with path: {path}")

    print(f"Updated entry: {path} -> {new_status}", file=sys.stderr)


def list_queue(manager: QueueManager, args: list):
    """
    List queue entries as JSON

    Args:
        manager: QueueManager instance
        args: [status_filter (optional)]
    """
    status_filter = args[0] if len(args) > 0 else None

    entries = manager.read_queue()

    # Apply filter if provided
    if status_filter:
        entries = [e for e in entries if e['status'] == status_filter]

    # Output JSON array for easy parsing by run.sh
    print(json.dumps(entries, indent=2))


def discard_entry(manager: QueueManager, args: list):
    """
    Mark entry as discarded

    Args:
        manager: QueueManager instance
        args: [path]
    """
    if len(args) < 1:
        print("Usage: queue_cli.py discard <path>", file=sys.stderr)
        sys.exit(1)

    path = args[0]

    # Find and mark as discarded
    with manager.atomic_update() as entries:
        found = False
        for entry in entries:
            if entry['path'] == path:
                entry['status'] = 'discarded'
                found = True
                break

        if not found:
            raise ValueError(f"Entry not found with path: {path}")

    print(f"Discarded entry: {path}", file=sys.stderr)


if __name__ == '__main__':
    main()
