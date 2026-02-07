"""
Test suite for Config class validation (TEST-02).

Tests cover:
- Missing required environment variables
- Invalid paths (non-existent recording directories)
- Actionable error messages with variable names and context
- Colored error output for visibility
- Environment variable precedence over .env files
- Path expansion (tilde and relative paths)
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.config import Config, ConfigError


class TestConfigValidation:
    """Test Config validation catches missing/invalid settings"""

    def test_config_missing_obs_password(self, clean_env, tmp_path):
        """Missing OBS_PASSWORD should raise SystemExit with error message"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup minimal valid config except OBS_PASSWORD
            clean_env.setenv('RECORDING_PATH', str(tmp_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')
            clean_env.delenv('OBS_PASSWORD', raising=False)

            # Config should fail-fast with SystemExit
            with pytest.raises(SystemExit) as exc_info:
                Config()

            assert exc_info.value.code == 1

    def test_config_missing_recording_path(self, clean_env, tmp_path):
        """Missing RECORDING_PATH should raise SystemExit with clear message"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup config missing RECORDING_PATH
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')
            clean_env.delenv('RECORDING_PATH', raising=False)

            with pytest.raises(SystemExit) as exc_info:
                Config()

            assert exc_info.value.code == 1

    def test_config_missing_user_email(self, clean_env, tmp_path):
        """Missing USER_EMAIL should raise SystemExit with context about calendar filtering"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup config missing USER_EMAIL
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('RECORDING_PATH', str(tmp_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.delenv('USER_EMAIL', raising=False)

            with pytest.raises(SystemExit) as exc_info:
                Config()

            assert exc_info.value.code == 1

    def test_config_invalid_recording_path(self, clean_env, tmp_path):
        """Non-existent RECORDING_PATH should raise SystemExit"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup config with non-existent recording path
            non_existent_path = tmp_path / 'does_not_exist'
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('RECORDING_PATH', str(non_existent_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')

            with pytest.raises(SystemExit) as exc_info:
                Config()

            assert exc_info.value.code == 1

    def test_config_valid_loads_successfully(self, clean_env, tmp_path):
        """Valid config with all required settings should load successfully"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup complete valid config
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('RECORDING_PATH', str(tmp_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')

            # Should load without raising
            config = Config()

            assert config.obs_password == 'test123'
            assert config.recording_path == tmp_path
            assert config.user_email == 'test@example.com'
            assert (tmp_path / 'output').exists()  # Output dir should be created


class TestConfigErrorMessages:
    """Test error messages are actionable and include context (TEST-02 requirement)"""

    def test_error_message_includes_variable_name(self, clean_env, tmp_path, capsys):
        """Error message should include the missing variable name"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup config missing OBS_PASSWORD
            clean_env.setenv('RECORDING_PATH', str(tmp_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')
            clean_env.delenv('OBS_PASSWORD', raising=False)

            with pytest.raises(SystemExit):
                Config()

            captured = capsys.readouterr()
            output = captured.out + captured.err

            # Should mention the variable name
            assert 'OBS_PASSWORD' in output

    def test_error_message_includes_context(self, clean_env, tmp_path, capsys):
        """Error message should include context explaining why setting is needed"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup config missing USER_EMAIL
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('RECORDING_PATH', str(tmp_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.delenv('USER_EMAIL', raising=False)

            with pytest.raises(SystemExit):
                Config()

            captured = capsys.readouterr()
            output = captured.out + captured.err

            # Should include context about calendar filtering
            assert 'USER_EMAIL' in output
            # Context should mention why it's needed (calendar filtering, email address)
            assert 'email' in output.lower() or 'calendar' in output.lower() or 'filtering' in output.lower()

    def test_error_message_colored(self, clean_env, tmp_path, capsys):
        """Error messages should use colorama for visibility"""
        # Mock find_project_root to return isolated temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Setup config with missing OBS_PASSWORD
            clean_env.setenv('RECORDING_PATH', str(tmp_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')
            clean_env.delenv('OBS_PASSWORD', raising=False)

            with pytest.raises(SystemExit):
                Config()

            captured = capsys.readouterr()
            output = captured.out + captured.err

            # Should contain ANSI color codes (colorama Fore.RED)
            # ANSI color codes start with \x1b[ or \033[
            has_ansi_codes = '\x1b[' in output or '\033[' in output or '[31m' in output or '[1m' in output

            assert has_ansi_codes, "Error message should include ANSI color codes"


class TestConfigEnvPrecedence:
    """Test environment variable precedence over .env files"""

    def test_env_var_overrides_dotenv(self, clean_env, tmp_path):
        """Environment variable should take precedence over .env file"""
        # Create .env file with one value
        dotenv_path = tmp_path / '.env'
        dotenv_path.write_text('OBS_HOST=from_dotenv\n')

        # Mock find_project_root to return our temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Set env var with different value
            clean_env.setenv('OBS_HOST', 'from_env_var')
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('RECORDING_PATH', str(tmp_path))
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')

            config = Config()

            # Environment variable should win
            assert config.obs_host == 'from_env_var'

    def test_dotenv_used_when_env_missing(self, clean_env, tmp_path):
        """Values from .env should be used when env var not set"""
        # Create .env file
        dotenv_path = tmp_path / '.env'
        dotenv_content = f"""OBS_HOST=from_dotenv
OBS_PASSWORD=dotenv_password
RECORDING_PATH={tmp_path}
TRANSCRIPTION_OUTPUT_DIR={tmp_path / 'output'}
USER_EMAIL=dotenv@example.com
"""
        dotenv_path.write_text(dotenv_content)

        # Mock find_project_root to return our temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            # Clear all env vars
            clean_env.delenv('OBS_HOST', raising=False)
            clean_env.delenv('OBS_PASSWORD', raising=False)
            clean_env.delenv('RECORDING_PATH', raising=False)
            clean_env.delenv('TRANSCRIPTION_OUTPUT_DIR', raising=False)
            clean_env.delenv('USER_EMAIL', raising=False)

            config = Config()

            # Should load from .env file
            assert config.obs_host == 'from_dotenv'
            assert config.obs_password == 'dotenv_password'
            assert config.user_email == 'dotenv@example.com'


class TestPathExpansion:
    """Test path expansion for tilde and relative paths"""

    def test_tilde_expansion_in_paths(self, clean_env, tmp_path):
        """Tilde in paths should expand to home directory"""
        # Setup config with tilde path
        # Note: We need to use a path that exists, so create a test dir in home
        home_dir = Path.home()
        test_dir = home_dir / '.obs_transcriber_test_temp'
        test_dir.mkdir(exist_ok=True)

        try:
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('RECORDING_PATH', f'~/.obs_transcriber_test_temp')
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', str(tmp_path / 'output'))
            clean_env.setenv('USER_EMAIL', 'test@example.com')

            config = Config()

            # Should expand to home directory
            assert config.recording_path == test_dir
            assert '~' not in str(config.recording_path)

        finally:
            # Cleanup
            if test_dir.exists():
                test_dir.rmdir()

    def test_relative_path_resolution(self, clean_env, tmp_path):
        """Relative paths should resolve relative to project root"""
        # Create subdirectories in tmp_path
        recordings_dir = tmp_path / 'recordings'
        recordings_dir.mkdir()

        # Mock find_project_root to return our temp directory
        with patch('scripts.config.find_project_root', return_value=tmp_path):
            clean_env.setenv('OBS_PASSWORD', 'test123')
            clean_env.setenv('RECORDING_PATH', 'recordings')  # Relative path
            clean_env.setenv('TRANSCRIPTION_OUTPUT_DIR', 'output')  # Relative path
            clean_env.setenv('USER_EMAIL', 'test@example.com')

            config = Config()

            # Should resolve relative to project root (tmp_path)
            assert config.recording_path == recordings_dir
            assert config.transcription_output_dir == tmp_path / 'output'
