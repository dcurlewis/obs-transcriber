"""
Test suite for root detection and path resolution (TEST-03).

Tests cover:
- Project root detection from different starting points
- Fallback chain: git → .env → cwd structure check
- Path resolution from multiple working directories
- Import setup idempotency
- Caching behavior
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.root_detection import find_project_root, setup_project_imports, _cached_root


class TestFindProjectRoot:
    """Test project root detection with fallback chain"""

    def test_finds_git_root(self, tmp_path, monkeypatch):
        """Should find git repository root using git rev-parse"""
        # Create git repository structure
        git_root = tmp_path / 'project'
        git_root.mkdir()
        (git_root / '.git').mkdir()

        # Create subdirectory to test from
        subdir = git_root / 'nested' / 'deep'
        subdir.mkdir(parents=True)

        # Mock subprocess to return git root
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = str(git_root)
            return result

        # Clear cache before test
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        with patch('subprocess.run', mock_run):
            root = find_project_root(start_path=subdir)
            assert root == git_root

    def test_finds_dotenv_fallback(self, tmp_path, monkeypatch):
        """Should fall back to .env file location when git not available"""
        # Create project structure with .env
        project_root = tmp_path / 'project'
        project_root.mkdir()
        (project_root / '.env').write_text('TEST=value\n')

        # Create subdirectory
        subdir = project_root / 'subdir'
        subdir.mkdir()

        # Mock git to fail (not a git repo)
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 128  # Git error code for "not a git repo"
            result.stdout = ''
            return result

        # Clear cache before test
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        with patch('subprocess.run', mock_run):
            root = find_project_root(start_path=subdir)
            assert root == project_root

    def test_finds_from_nested_directory(self, tmp_path, monkeypatch):
        """Should find root from deeply nested directory"""
        # Create deep nested structure
        project_root = tmp_path / 'project'
        project_root.mkdir()
        (project_root / '.env.example').write_text('# Example config\n')

        deep_dir = project_root / 'a' / 'b' / 'c' / 'd' / 'e'
        deep_dir.mkdir(parents=True)

        # Mock git to fail
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 128
            result.stdout = ''
            return result

        # Clear cache before test
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        with patch('subprocess.run', mock_run):
            root = find_project_root(start_path=deep_dir)
            assert root == project_root

    def test_returns_cwd_if_has_expected_structure(self, tmp_path, monkeypatch):
        """Should return cwd as fallback if it has scripts/ and web/ directories"""
        # Create project structure
        project_root = tmp_path / 'project'
        project_root.mkdir()
        (project_root / 'scripts').mkdir()
        (project_root / 'web').mkdir()

        # Mock git to fail
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 128
            result.stdout = ''
            return result

        # Clear cache before test
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        # Change to project directory
        monkeypatch.chdir(project_root)

        with patch('subprocess.run', mock_run):
            root = find_project_root(start_path=project_root)
            assert root == project_root

    def test_error_when_outside_project(self, tmp_path, monkeypatch):
        """Should raise RuntimeError with detailed message when root cannot be found"""
        # Create empty directory with no markers
        empty_dir = tmp_path / 'empty'
        empty_dir.mkdir()

        # Mock git to fail
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 128
            result.stdout = ''
            return result

        # Clear cache before test
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        # Change to empty directory
        monkeypatch.chdir(empty_dir)

        with patch('subprocess.run', mock_run):
            with pytest.raises(RuntimeError) as exc_info:
                find_project_root(start_path=empty_dir)

            error_msg = str(exc_info.value)
            # Error should be detailed and mention attempts
            assert 'Could not determine project root' in error_msg or 'project root' in error_msg.lower()


class TestPathResolutionFromMultipleDirectories:
    """Test that scripts work from any directory (TEST-03 core requirement)"""

    def test_scripts_work_from_project_root(self, temp_project_root, monkeypatch):
        """Imports should work when running from project root"""
        # Clear sys.path and cache
        original_path = sys.path.copy()
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        try:
            # Change to project root
            monkeypatch.chdir(temp_project_root)

            # Mock find_project_root to return temp directory
            with patch('scripts.root_detection.find_project_root', return_value=temp_project_root):
                # Setup imports
                setup_project_imports()

                # Verify scripts directory is in path
                scripts_dir = str(temp_project_root / 'scripts')
                assert scripts_dir in sys.path

        finally:
            # Restore sys.path
            sys.path[:] = original_path

    def test_scripts_work_from_subdirectory(self, temp_project_root, monkeypatch):
        """Imports should work when running from subdirectory"""
        # Create subdirectory
        subdir = temp_project_root / 'tests'
        subdir.mkdir(exist_ok=True)

        # Clear sys.path and cache
        original_path = sys.path.copy()
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        try:
            # Change to subdirectory
            monkeypatch.chdir(subdir)

            # Mock find_project_root to return temp directory
            with patch('scripts.root_detection.find_project_root', return_value=temp_project_root):
                # Setup imports should still work
                setup_project_imports()

                # Verify scripts directory is in path
                scripts_dir = str(temp_project_root / 'scripts')
                assert scripts_dir in sys.path

        finally:
            # Restore sys.path
            sys.path[:] = original_path

    def test_scripts_work_from_parent_directory(self, temp_project_root, monkeypatch):
        """Import setup from parent directory should fail or use fallback"""
        # Clear cache
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        # Change to parent of project root
        parent_dir = temp_project_root.parent
        monkeypatch.chdir(parent_dir)

        # From parent directory, should not find project root
        # (unless parent also has .git or .env, which it shouldn't in test)
        with pytest.raises(RuntimeError):
            find_project_root(start_path=parent_dir)


class TestImportSetup:
    """Test import setup functionality"""

    def test_setup_project_imports_adds_to_syspath(self, temp_project_root, monkeypatch):
        """setup_project_imports should add project root and scripts to sys.path"""
        # Clear sys.path and cache
        original_path = sys.path.copy()
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        try:
            # Change to project root
            monkeypatch.chdir(temp_project_root)

            # Clear scripts paths from sys.path if present
            sys.path = [p for p in sys.path if 'scripts' not in p and str(temp_project_root) not in p]

            # Mock find_project_root to return temp directory
            with patch('scripts.root_detection.find_project_root', return_value=temp_project_root):
                # Setup imports
                setup_project_imports()

                # Verify both root and scripts are in path
                assert str(temp_project_root) in sys.path
                assert str(temp_project_root / 'scripts') in sys.path

        finally:
            # Restore sys.path
            sys.path[:] = original_path

    def test_setup_project_imports_idempotent(self, temp_project_root, monkeypatch):
        """Calling setup_project_imports multiple times should not duplicate paths"""
        # Clear sys.path and cache
        original_path = sys.path.copy()
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        try:
            # Change to project root
            monkeypatch.chdir(temp_project_root)

            # Clear scripts paths
            sys.path = [p for p in sys.path if 'scripts' not in p and str(temp_project_root) not in p]

            # Mock find_project_root to return temp directory
            with patch('scripts.root_detection.find_project_root', return_value=temp_project_root):
                # Call setup_project_imports twice
                setup_project_imports()
                initial_path = sys.path.copy()

                setup_project_imports()
                second_path = sys.path.copy()

                # Paths should be identical (no duplicates added)
                assert initial_path == second_path

        finally:
            # Restore sys.path
            sys.path[:] = original_path


class TestCaching:
    """Test root detection caching behavior"""

    def test_root_detection_cached(self, temp_project_root, monkeypatch):
        """Second call to find_project_root should use cache, not run git again"""
        # Clear cache
        import scripts.root_detection
        scripts.root_detection._cached_root = None

        # Change to project root
        monkeypatch.chdir(temp_project_root)

        # Track how many times subprocess.run is called
        call_count = []

        original_run = subprocess.run

        def counting_run(*args, **kwargs):
            call_count.append(1)
            return original_run(*args, **kwargs)

        with patch('subprocess.run', counting_run):
            # First call should execute git command
            root1 = find_project_root(start_path=temp_project_root)

            # Second call should use cache (no additional git calls)
            root2 = find_project_root(start_path=temp_project_root)

            # Both should return same root
            assert root1 == root2

            # Subprocess should only be called once (for first call)
            assert len(call_count) == 1, "Expected only 1 subprocess call, caching should prevent second call"
