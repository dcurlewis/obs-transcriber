"""
Dependency checking with fail-fast validation.

This module validates that all required external tools and Python modules
are available before operations start, providing clear installation guidance
if dependencies are missing.

Usage:
    from dependencies import check_dependencies

    check_dependencies()  # Exits with code 1 if dependencies missing
"""

import shutil
import sys
from colorama import Fore, Style, just_fix_windows_console

# Initialize colorama for Windows compatibility
just_fix_windows_console()


def check_command_available(cmd: str) -> bool:
    """Check if external command is available on PATH.

    Args:
        cmd: Command name to check (e.g., 'ffmpeg', 'ffprobe')

    Returns:
        True if command exists and is executable, False otherwise
    """
    return shutil.which(cmd) is not None


def check_dependencies() -> None:
    """Pre-flight check for all required dependencies.

    Validates:
    - External commands: ffmpeg, ffprobe
    - Python modules: obsws_python

    Exits with code 1 if any dependency is missing, displaying
    colored error message with installation instructions.
    """
    missing = []

    # Check external commands
    if not check_command_available('ffmpeg'):
        missing.append({
            'name': 'ffmpeg',
            'purpose': 'Required for audio extraction from MKV files',
            'type': 'external'
        })

    if not check_command_available('ffprobe'):
        missing.append({
            'name': 'ffprobe',
            'purpose': 'Required for audio validation',
            'type': 'external'
        })

    # Check Python modules
    try:
        import obsws_python
    except ImportError:
        missing.append({
            'name': 'obsws-python',
            'purpose': 'Required for OBS WebSocket control',
            'type': 'python'
        })

    # If any dependencies missing, display error and exit
    if missing:
        print(f"\n{Fore.RED}{Style.BRIGHT}Missing Dependencies:{Style.RESET_ALL}")
        for dep in missing:
            print(f"{Fore.RED}  • {dep['name']}: {dep['purpose']}{Style.RESET_ALL}")

        print(f"\n{Style.BRIGHT}Installation:{Style.RESET_ALL}")

        # Check if FFmpeg tools are missing
        ffmpeg_missing = any(d['name'] in ('ffmpeg', 'ffprobe') for d in missing)
        if ffmpeg_missing:
            # Detect OS and provide appropriate installation command
            import platform
            os_type = platform.system()
            if os_type == 'Darwin':
                print("  • FFmpeg: brew install ffmpeg")
            elif os_type == 'Linux':
                print("  • FFmpeg: apt install ffmpeg  # Debian/Ubuntu")
                print("            yum install ffmpeg  # RHEL/CentOS")
            elif os_type == 'Windows':
                print("  • FFmpeg: Download from https://ffmpeg.org/download.html")
            else:
                print("  • FFmpeg: See https://ffmpeg.org/download.html")

        # Check if Python modules are missing
        python_missing = any(d['type'] == 'python' for d in missing)
        if python_missing:
            print("  • Python packages: pip install -r requirements.txt")

        print()  # Blank line before exit
        sys.exit(1)


if __name__ == '__main__':
    # Allow running directly for testing
    check_dependencies()
    print(f"{Fore.GREEN}{Style.BRIGHT}✓ All dependencies available{Style.RESET_ALL}")
