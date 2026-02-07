"""
Project root detection and import configuration.

This module provides centralized utilities for locating the project root
directory and setting up Python imports to work consistently across all
entry points (CLI scripts, web server, tests).

Usage:
    from scripts.root_detection import find_project_root, setup_project_imports

    # Get project root
    project_root = find_project_root()

    # Configure imports for cross-directory imports
    setup_project_imports()

    # Now can import from anywhere
    from queue_manager import QueueManager
"""

import subprocess
import sys
from pathlib import Path
from colorama import Fore, Style

# Cache for root detection result (avoid repeated git calls)
_cached_root = None


def find_project_root(start_path=None):
    """
    Find project root using a robust fallback chain.

    Detection order:
    1. Git repository root (most reliable for version-controlled projects)
    2. Directory containing .env or .env.example file
    3. Current working directory if it has expected structure (scripts/ and web/)
    4. Raise RuntimeError if root cannot be determined

    The result is cached at module level to avoid repeated subprocess calls.

    Args:
        start_path: Directory to start searching from (default: this script's directory)

    Returns:
        Path: Absolute path to project root

    Raises:
        RuntimeError: If root cannot be determined, with detailed error showing
                     all attempted methods and paths tried

    Examples:
        >>> root = find_project_root()
        >>> dotenv_path = root / '.env'
        >>> queue_path = root / 'processing_queue.csv'
    """
    global _cached_root

    # Return cached result if available
    if _cached_root is not None:
        return _cached_root

    # Start from script's directory if not specified
    if start_path is None:
        start_path = Path(__file__).parent.resolve()
    else:
        start_path = Path(start_path).resolve()

    attempted_methods = []

    # Try 1: Git repository root (most reliable)
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=start_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=2  # Fail fast if git hangs
        )

        if result.returncode == 0:
            root = Path(result.stdout.strip()).resolve()
            _cached_root = root
            return root
        else:
            attempted_methods.append(
                f"Git repository root from {start_path}: Not a git repository"
            )
    except FileNotFoundError:
        attempted_methods.append(
            f"Git repository root from {start_path}: Git not installed"
        )
    except subprocess.TimeoutExpired:
        attempted_methods.append(
            f"Git repository root from {start_path}: Git command timed out"
        )

    # Try 2: Walk up looking for .env or .env.example file
    current = start_path
    env_search_paths = []

    for parent in [current] + list(current.parents):
        env_search_paths.append(str(parent))
        if (parent / '.env').exists() or (parent / '.env.example').exists():
            _cached_root = parent
            return parent

    attempted_methods.append(
        f"Parent directories containing .env file: Searched {len(env_search_paths)} directories up to /"
    )

    # Try 3: Current working directory if it has expected structure
    cwd = Path.cwd()
    has_scripts = (cwd / 'scripts').is_dir()
    has_web = (cwd / 'web').is_dir()

    if has_scripts and has_web:
        _cached_root = cwd
        return cwd

    attempted_methods.append(
        f"Current directory {cwd}: Missing expected structure (scripts={'✓' if has_scripts else '✗'}, web={'✓' if has_web else '✗'})"
    )

    # Failed to find root - provide detailed error with all attempts
    error_msg = (
        f"\n{Fore.RED}{Style.BRIGHT}Could not determine project root{Style.RESET_ALL}\n\n"
        f"{Style.BRIGHT}Attempted methods:{Style.RESET_ALL}\n"
    )

    for i, method in enumerate(attempted_methods, 1):
        error_msg += f"  {i}. {method}\n"

    error_msg += (
        f"\n{Style.BRIGHT}Current directory:{Style.RESET_ALL}\n"
        f"  {cwd}\n\n"
        f"{Style.BRIGHT}Script location:{Style.RESET_ALL}\n"
        f"  {Path(__file__).resolve()}\n\n"
        f"{Style.BRIGHT}Suggestions:{Style.RESET_ALL}\n"
        f"  • Ensure you are running from within the project directory\n"
        f"  • Verify the project is a git repository (has .git directory)\n"
        f"  • Ensure the project has a .env or .env.example file\n"
        f"  • Check that project has scripts/ and web/ directories\n"
    )

    raise RuntimeError(error_msg)


def setup_project_imports():
    """
    Configure sys.path for cross-directory imports.

    Adds both project root and scripts directory to sys.path (if not already
    present), enabling imports like 'from queue_manager import QueueManager'
    to work from any entry point (CLI, web server, tests).

    This function is idempotent - safe to call multiple times.

    Call this at the start of every entry point:
    - CLI scripts: queue_cli.py, obs_controller.py, transcribe.py, etc.
    - Web server: web/app.py
    - Tests: conftest.py or individual test files

    Examples:
        >>> # At top of web/app.py
        >>> from pathlib import Path
        >>> import sys
        >>> sys.path.insert(0, str(Path(__file__).parent.parent))
        >>> from scripts.root_detection import setup_project_imports
        >>> setup_project_imports()
        >>>
        >>> # Now can import from scripts/
        >>> from queue_manager import QueueManager
        >>> from config import get_config
    """
    project_root = find_project_root()
    scripts_dir = project_root / 'scripts'

    # Add both root and scripts to sys.path (if not already present)
    # Use insert(0, ...) to give priority over other paths
    for path_to_add in [str(project_root), str(scripts_dir)]:
        if path_to_add not in sys.path:
            sys.path.insert(0, path_to_add)
