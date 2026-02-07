#!/usr/bin/env python3
"""
Audio file validation using FFmpeg.

This module provides fast audio validation using ffprobe to detect
corrupted or invalid files before expensive transcription operations.

Usage:
    from audio_validator import validate_audio_file, AudioValidationError

    try:
        validate_audio_file(Path("audio.wav"))
    except AudioValidationError as e:
        print(e)  # Displays formatted error with troubleshooting steps
"""

import subprocess
import sys
from pathlib import Path
from colorama import Fore, Style, just_fix_windows_console

# Initialize colorama for Windows compatibility
just_fix_windows_console()


class AudioValidationError(Exception):
    """Raised when audio file validation fails"""
    pass


def _format_validation_error(problem: str, file_path: Path, suggestions: list[str]) -> str:
    """Format actionable error message with troubleshooting steps.

    Args:
        problem: Description of what went wrong
        file_path: Path to the file that failed validation
        suggestions: List of actionable troubleshooting steps

    Returns:
        Formatted error string with colors
    """
    msg = f"\n{Fore.RED}{Style.BRIGHT}Audio Validation Failed:{Style.RESET_ALL}\n"
    msg += f"{Fore.RED}{problem}{Style.RESET_ALL}\n\n"

    # Show file details if it exists
    if file_path.exists():
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        msg += f"File: {file_path.name} ({file_size_mb:.1f} MB)\n\n"
    else:
        msg += f"File: {file_path.name}\n\n"

    msg += f"{Style.BRIGHT}Troubleshooting Steps:{Style.RESET_ALL}\n"
    for i, suggestion in enumerate(suggestions, 1):
        msg += f"  {i}. {suggestion}\n"

    return msg


def validate_audio_file(audio_path: Path) -> None:
    """Validate audio file integrity using ffprobe.

    Performs fast validation (<5 seconds) to detect:
    - Missing files
    - Empty files (0 bytes)
    - Files without audio streams
    - Corrupted audio files

    Args:
        audio_path: Path to audio file to validate

    Raises:
        AudioValidationError: If file is invalid or corrupted with actionable error message
        FileNotFoundError: If ffprobe is not available (shouldn't happen after dependency check)
    """
    # Check 1: File exists
    if not audio_path.exists():
        error_msg = _format_validation_error(
            problem=f"Audio file not found: {audio_path}",
            file_path=audio_path,
            suggestions=[
                "Verify the file path is correct",
                "Check that OBS recording completed successfully",
                "Ensure the file wasn't moved or deleted",
                f"Check file with: ls -lh {audio_path.parent}"
            ]
        )
        raise AudioValidationError(error_msg)

    # Check 2: File is non-empty
    file_size = audio_path.stat().st_size
    if file_size == 0:
        error_msg = _format_validation_error(
            problem="Audio file is empty (0 bytes)",
            file_path=audio_path,
            suggestions=[
                "Check OBS audio settings (Settings → Audio)",
                "Verify microphone is enabled in OBS audio mixer",
                "Check that audio tracks are configured in recording settings",
                "Test with a manual recording to verify audio capture works"
            ]
        )
        raise AudioValidationError(error_msg)

    # Check 3: FFprobe validation (format and audio stream)
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',  # Only show errors
                '-show_entries', 'stream=codec_type,codec_name',
                '-of', 'default=noprint_wrappers=1',
                str(audio_path)
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )

        # Check for audio stream in output
        if 'codec_type=audio' not in result.stdout:
            error_msg = _format_validation_error(
                problem="No audio stream found in file",
                file_path=audio_path,
                suggestions=[
                    "Verify OBS is recording audio tracks (Settings → Output → Recording)",
                    "Check that audio devices are enabled in OBS audio mixer",
                    f"Inspect file manually: ffprobe -show_streams {audio_path}",
                    "Try recording a test session to verify audio capture"
                ]
            )
            raise AudioValidationError(error_msg)

    except subprocess.TimeoutExpired:
        error_msg = _format_validation_error(
            problem="Validation timeout - file may be severely corrupted",
            file_path=audio_path,
            suggestions=[
                "File may be corrupted during recording or transfer",
                "Check available disk space during recording",
                f"Try comprehensive check: ffmpeg -v error -i {audio_path} -f null -",
                "Consider re-recording the session"
            ]
        )
        raise AudioValidationError(error_msg)

    except subprocess.CalledProcessError as e:
        # ffprobe returned non-zero exit code (invalid/corrupted file)
        error_detail = e.stderr.strip() if e.stderr else "Unknown format error"
        error_msg = _format_validation_error(
            problem=f"Audio file is corrupted or invalid format\nFFmpeg error: {error_detail}",
            file_path=audio_path,
            suggestions=[
                "File may be corrupted during recording",
                "Check available disk space (full disk can corrupt recordings)",
                f"Try manual inspection: ffprobe -v error {audio_path}",
                "If file is corrupted, re-record the session"
            ]
        )
        raise AudioValidationError(error_msg)

    except FileNotFoundError:
        # This shouldn't happen if dependency check runs at startup
        error_msg = _format_validation_error(
            problem="ffprobe not found - FFmpeg is not installed",
            file_path=audio_path,
            suggestions=[
                "Install FFmpeg: brew install ffmpeg (macOS)",
                "Install FFmpeg: apt install ffmpeg (Linux)",
                "Install FFmpeg: Download from https://ffmpeg.org (Windows)",
                "Verify installation: ffprobe -version"
            ]
        )
        raise AudioValidationError(error_msg)

    # If we get here, file is valid
    # No return value needed - function succeeds silently or raises exception


def main():
    """Command-line interface for audio validation (for testing)"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate audio files before transcription",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s audio.wav
  %(prog)s recording.mkv
  %(prog)s *.wav  # Validate multiple files
        """
    )

    parser.add_argument(
        "audio_files",
        nargs='+',
        help="Audio file(s) to validate"
    )

    args = parser.parse_args()

    # Validate each file
    failed = []
    for audio_file in args.audio_files:
        audio_path = Path(audio_file)
        try:
            validate_audio_file(audio_path)
            print(f"✅ Valid: {audio_path.name}")
        except AudioValidationError as e:
            print(str(e), file=sys.stderr)
            failed.append(audio_path.name)

    # Exit with error if any files failed
    if failed:
        print(f"\n❌ Validation failed for {len(failed)} file(s)", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\n✅ All {len(args.audio_files)} file(s) validated successfully")


if __name__ == "__main__":
    main()
