"""
Shared pytest fixtures for obs-transcriber test suite.

Provides fixtures for:
- Environment variable isolation (clean_env)
- Temporary project root directories (temp_project_root)
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Bootstrap: Add project root to sys.path for root_detection import
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Setup project imports for all tests
from scripts.root_detection import setup_project_imports
setup_project_imports()


@pytest.fixture
def clean_env(monkeypatch):
    """
    Provides a clean environment for config testing.

    Saves current environment variables and restores them after test.
    Use monkeypatch to set/delete environment variables within tests.

    Usage:
        def test_config(clean_env, monkeypatch):
            monkeypatch.setenv('OBS_PASSWORD', 'test123')
            monkeypatch.delenv('USER_EMAIL', raising=False)
            # ... test code ...
    """
    # Store original environment
    original_env = os.environ.copy()

    yield monkeypatch

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def temp_project_root(tmp_path):
    """
    Creates a temporary directory structure mimicking project root.

    Creates:
    - .git directory (marker for project root detection)
    - scripts/ directory
    - web/ directory

    Returns:
        Path: Absolute path to temporary project root

    Usage:
        def test_find_root(temp_project_root):
            assert (temp_project_root / '.git').exists()
            assert find_project_root(temp_project_root) == temp_project_root
    """
    # Create project structure markers
    (tmp_path / '.git').mkdir()
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'web').mkdir()

    return tmp_path
