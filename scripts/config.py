"""
Configuration management with environment variable validation.

This module provides centralized configuration loading from environment variables
and .env files, with validation and colored error messages.

Usage:
    from config import get_config

    config = get_config()  # Validates on first call
    print(config.obs_host)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from colorama import Fore, Style, just_fix_windows_console

# Initialize colorama for Windows compatibility
just_fix_windows_console()


class ConfigError(Exception):
    """Configuration validation error with formatted output"""
    pass


class Config:
    """Centralized configuration with validation

    Loads configuration from:
    1. Environment variables (highest priority)
    2. .env file in project root (lower priority)

    Validates all required settings at instantiation and fails fast
    with colored, actionable error messages.
    """

    def __init__(self):
        """Load and validate configuration from environment variables"""
        self._load_dotenv()
        self._load_and_validate()

    def _load_dotenv(self):
        """Load .env file if it exists (optional)"""
        # Find .env in project root
        project_root = Path(__file__).parent.parent
        dotenv_path = project_root / '.env'

        # Load .env file if it exists (environment variables take precedence)
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=False)
        # If .env doesn't exist, continue with environment variables only

    def _load_and_validate(self):
        """Load and validate all configuration values"""
        try:
            # Required: OBS settings
            self.obs_host = self._get_required('OBS_HOST', default='localhost')
            self.obs_port = self._get_int('OBS_PORT', default=4455)
            self.obs_password = self._get_required('OBS_PASSWORD',
                context="Required to connect to OBS WebSocket")

            # Required: Paths
            self.recording_path = self._get_path('RECORDING_PATH',
                must_exist=True,
                context="Path to OBS recordings directory")
            self.transcription_output_dir = self._get_path('TRANSCRIPTION_OUTPUT_DIR',
                must_exist=False,  # Can be created
                context="Path for transcription output")

            # Required: Email for calendar filtering
            self.user_email = self._get_required('USER_EMAIL',
                context="Email address for filtering calendar events")

            # Optional: Whisper settings (with defaults)
            self.whisper_model = os.getenv('WHISPER_MODEL', 'turbo')
            self.whisper_language = os.getenv('WHISPER_LANGUAGE', 'en')

            # Optional: Behavior settings
            self.keep_raw_recording = self._get_bool('KEEP_RAW_RECORDING', default=False)

        except ConfigError as e:
            self._print_error(str(e))
            sys.exit(1)

    def _get_required(self, key, context=None, default=None):
        """Get required environment variable or use default

        Args:
            key: Environment variable name
            context: Optional context explaining why this is needed
            default: Optional default value (if provided, field is not truly required)

        Returns:
            Value from environment or default

        Raises:
            ConfigError: If value is not set and no default provided
        """
        value = os.getenv(key, default)
        if not value:
            msg = f"{key} not set."
            if context:
                msg += f" {context}."
            msg += "\n\nSee .env.example for configuration template."
            msg += f"\nCopy .env.example to .env and set {key}"
            raise ConfigError(msg)
        return value

    def _get_int(self, key, default):
        """Get integer environment variable with type conversion

        Args:
            key: Environment variable name
            default: Default value if not set

        Returns:
            Integer value from environment or default

        Raises:
            ConfigError: If value cannot be converted to integer
        """
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise ConfigError(f"{key} must be an integer, got: {value}")

    def _get_bool(self, key, default):
        """Get boolean environment variable with type conversion

        Args:
            key: Environment variable name
            default: Default value if not set

        Returns:
            Boolean value from environment or default
        """
        value = os.getenv(key)
        if value is None:
            return default
        return value.lower() in ('true', '1', 'yes', 'on')

    def _get_path(self, key, must_exist=False, context=None):
        """Get and validate path environment variable

        Args:
            key: Environment variable name
            must_exist: If True, path must exist on disk (input paths)
                       If False, path will be created if missing (output paths)
            context: Optional context explaining what this path is for

        Returns:
            Path object with expanded home directory

        Raises:
            ConfigError: If path is not set or doesn't exist (when must_exist=True)
        """
        value = os.getenv(key)
        if not value:
            msg = f"{key} not set."
            if context:
                msg += f" {context}."
            msg += "\n\nSee .env.example for configuration template."
            msg += f"\nCopy .env.example to .env and set {key}"
            raise ConfigError(msg)

        # Expand ~ to home directory
        path = Path(value).expanduser()

        if must_exist and not path.exists():
            msg = f"{key} path does not exist: {path}"
            if context:
                msg += f"\n{context}."
            msg += "\n\nPlease create the directory or update the path in .env"
            raise ConfigError(msg)

        # Create output directories automatically
        if not must_exist and not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        return path

    def _print_error(self, message):
        """Print formatted error message with colors

        Args:
            message: Error message to print
        """
        print(f"\n{Fore.RED}{Style.BRIGHT}Configuration Error:{Style.RESET_ALL}")
        print(f"{Fore.RED}{message}{Style.RESET_ALL}\n")


# Global config instance (lazy-loaded)
_config = None


def get_config():
    """Get or create global config instance

    Returns:
        Config: Singleton config instance

    Raises:
        SystemExit: If configuration is invalid (via Config.__init__)
    """
    global _config
    if _config is None:
        _config = Config()
    return _config
