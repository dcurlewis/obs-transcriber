#!/usr/bin/env python3
"""
Logging sanitization module for protecting sensitive user data.

Provides a custom logging filter to redact emails, meeting names,
calendar events, and personal file paths from all log output.
"""

import logging
import re
from pathlib import Path


class SensitiveDataFilter(logging.Filter):
    """Filter that redacts sensitive information from log records.

    Sanitizes:
    - Email addresses → [EMAIL_REDACTED]
    - Personal paths → Replace home directory with ~
    - Meeting names → Meeting: [REDACTED]
    - Calendar event titles → Event: [REDACTED]

    Args:
        project_root: Project root path for reference
    """

    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.home_dir = Path.home()

    def filter(self, record):
        """Sanitize log record in-place.

        Modifies the log record to remove or redact sensitive data
        before it is written to any handler (console, file, etc.).

        Args:
            record: LogRecord instance to sanitize

        Returns:
            bool: Always True (don't filter out, just sanitize)
        """
        # Convert message to string if needed
        if not isinstance(record.msg, str):
            record.msg = str(record.msg)

        # Redact email addresses
        # Pattern matches: user@domain.com, first.last@company.co.uk, etc.
        record.msg = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '[EMAIL_REDACTED]',
            record.msg
        )

        # Redact personal paths (replace home dir with ~)
        # Protects user privacy by not exposing full home directory paths
        record.msg = record.msg.replace(str(self.home_dir), '~')

        # Redact meeting names in common patterns
        # Examples:
        #   "Meeting: Team Standup" → "Meeting: [REDACTED]"
        #   "meeting: Client Review" → "meeting: [REDACTED]"
        record.msg = re.sub(
            r'(Meeting|meeting):\s+[^\n]+',
            r'\1: [REDACTED]',
            record.msg
        )

        # Redact calendar event titles
        # Examples:
        #   "Event: Weekly Sync" → "Event: [REDACTED]"
        #   "Title: Sprint Planning" → "Title: [REDACTED]"
        record.msg = re.sub(
            r'(Event|event|title|Title):\s+[^\n]+',
            r'\1: [REDACTED]',
            record.msg
        )

        # Sanitize args if they exist
        # Some logging calls use: logger.info("Message: %s", sensitive_value)
        # We need to sanitize those args as well
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    self._sanitize_value(arg) for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: self._sanitize_value(v)
                    for k, v in record.args.items()
                }

        return True

    def _sanitize_value(self, value):
        """Sanitize a single value (used for record.args).

        Args:
            value: Any value that might contain sensitive data

        Returns:
            Sanitized value (same type as input)
        """
        if isinstance(value, str):
            # Redact emails
            value = re.sub(
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                '[EMAIL_REDACTED]',
                value
            )
            # Redact paths
            value = value.replace(str(self.home_dir), '~')
        return value


def setup_sanitized_logging(project_root: Path, level=logging.INFO):
    """Configure root logger with sensitive data filtering.

    Applies the SensitiveDataFilter to the root logger so that
    all loggers in the application automatically inherit the
    sanitization behavior.

    Args:
        project_root: Project root path
        level: Logging level (default: INFO)
    """
    # Create and apply filter
    sanitizer = SensitiveDataFilter(project_root)
    root_logger = logging.getLogger()
    root_logger.addFilter(sanitizer)

    # Set level if not already configured
    if not root_logger.handlers:
        root_logger.setLevel(level)
