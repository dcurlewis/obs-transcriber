# Coding Conventions

**Analysis Date:** 2026-02-07

## Naming Patterns

**Files:**
- Python scripts: `snake_case.py` (e.g., `obs_controller.py`, `filter_hallucinations.py`)
- Shell scripts: `lowercase.sh` (e.g., `run.sh`)
- JavaScript files: `camelCase.js` (e.g., `app.js`)
- Output files: `YYYYMMDD-SanitizedName_type.ext` (e.g., `20250801-1-1-with-Arman_transcript.txt`)

**Functions:**
- Python: `snake_case` for all functions, both private and public
  - Example: `def transcribe()`, `def format_timestamp_srt()`, `def _initialize_event_store()`
- JavaScript: `camelCase` for methods in classes and standalone functions
  - Example: `async refreshStatus()`, `updateCurrentTimeDisplay()`

**Variables:**
- Python: `snake_case` for local variables and parameters
  - Example: `audio_path`, `output_dir`, `meeting_name`
- JavaScript: `camelCase` for all variables
  - Example: `isRecording`, `currentMeeting`, `statusInterval`
- Bash: `UPPERCASE` for exported variables, `snake_case` for local variables
  - Example: `RECORDING_PATH`, `WHISPER_MODEL`, `TEMP_QUEUE_FILE`

**Types/Classes:**
- Python: `PascalCase` for class names (e.g., `RecordingController`, `CalendarService`, `MeetingTranscriber`)
- JavaScript: `PascalCase` for class names (e.g., `MeetingTranscriber`)

**Constants:**
- Python: `UPPERCASE_WITH_UNDERSCORES` (e.g., `MODEL_MAPPING`, `EVENTKIT_AVAILABLE`)
- Bash: `UPPERCASE_WITH_UNDERSCORES` (e.g., `KEEP_RAW_RECORDING`, `TRANSCRIPTION_OUTPUT_DIR`)

## Code Style

**Formatting:**
- No automatic formatter configured (no Black, no Prettier)
- Python: 4-space indentation
- JavaScript: 4-space indentation (visible in class constructor and methods)
- Bash: 4-space indentation

**Linting:**
- No ESLint or Pylint configuration detected
- Code follows PEP 8 conventions informally (no strict enforcement)

**Line Length:**
- No enforced line length limit observed
- Typical Python lines: 80-100 characters
- Typical Bash lines: variable, multiline commands use backslash continuation

**Imports:**
- Python: Standard library imports first, then third-party, then local imports
- Conditional imports wrapped in try/except blocks for optional dependencies
- Example in `transcribe.py`:
  ```python
  import argparse
  import sys
  from pathlib import Path
  from datetime import timedelta

  try:
      import mlx_whisper
  except ImportError:
      print("Error: mlx-whisper is not installed...")
      sys.exit(1)
  ```

## Import Organization

**Order:**
1. Standard library imports (`sys`, `os`, `subprocess`, `pathlib`, etc.)
2. Third-party imports (Flask, `obsws_python`, `pytz`, `EventKit`, etc.)
3. Relative imports from project (from `web.recorder import RecordingController`)

**Path Aliases:**
- Not used; all imports are absolute or relative to project root
- Project root is added to sys.path when needed: `sys.path.insert(0, str(Path(__file__).parent.parent))`

**Barrel Files:**
- Not used; minimal use of `__init__.py` files
- `web/__init__.py` exists but is minimal

## Error Handling

**Patterns:**
- Explicit exception catching for specific exception types (not bare `except`)
- Error messages printed to stdout or stderr with context
- Exit codes: `sys.exit(1)` for fatal errors, `sys.exit(0)` for success
- Return status dictionaries from service methods instead of raising exceptions in web layer

**Python Examples:**
- In `scripts/obs_controller.py`:
  ```python
  try:
      client = obs.ReqClient(...)
  except ConnectionRefusedError:
      print("Error: Connection refused. Is OBS running...")
      sys.exit(1)
  except Exception as e:
      print(f"Error connecting to OBS: {e}")
      sys.exit(1)
  ```

- In `web/recorder.py`:
  ```python
  try:
      result = subprocess.run([...], check=True)
  except subprocess.TimeoutExpired:
      return {'success': False, 'error': "OBS WebSocket connection timeout..."}
  except subprocess.CalledProcessError as e:
      return {'success': False, 'error': f"Failed to start recording: {error_msg}"}
  ```

**Bash Examples:**
- Early exit with descriptive errors: `exit 1`
- Verification before actions (e.g., file existence checks before operations)
- Recovery mode detection: resume processing if intermediate files exist

**JavaScript (Flask/Web layer):**
- Try/catch wrapping API calls and operations
- Return JSON error responses: `{'error': 'message'}`

## Logging

**Framework:**
- Python scripts: `print()` to stdout for user-facing messages
- Web layer: Python's built-in `logging` module for background tasks
  - `processing_logger` configured in `web/recorder.py` with `TimedRotatingFileHandler`
  - Writes to `logs/processing.log` with weekly rotation (keeps 4 weeks)

**Patterns:**
- User-facing output: emojis + descriptive messages to stdout
  - Example: `print("🎯 Model: {model}")`, `print("❌ Error: {e}")`
- Background processing: structured logging to file with timestamps and levels
  - `processing_logger.info()`, `processing_logger.error()`
- Shell scripts: direct `echo` statements for progress

**When/how to log:**
- Start/stop events: always log
- File operations: log before/after major operations
- Errors: always log with context
- Performance metrics: log timing information (e.g., audio extraction time, transcription time)

## Comments

**When to Comment:**
- Explain why, not what (code should be self-documenting for "what")
- Complex logic or non-obvious algorithms
- Important invariants or assumptions
- Configuration parameters and their effects

**Examples from codebase:**
- In `web/recorder.py`: `# Process has finished`, `# Check if process is still running`
- In `run.sh`: Comments explaining ffmpeg options for audio processing
- In `scripts/interleave.py`: `# Look for speaker labels like "[Speaker 1]" at the start of content`

**JSDoc/TSDoc:**
- Python: Docstrings for functions using triple quotes, not strict Google/NumPy style
  - Example in `transcribe.py`:
    ```python
    def transcribe(audio_path: str, output_dir: str, model: str = "turbo", language: str = "en", verbose: bool = True) -> Path:
        """
        Transcribe an audio file using MLX Whisper.

        Args:
            audio_path: Path to the input audio file
            output_dir: Directory to save the output SRT file
            model: Whisper model to use (e.g., 'turbo', 'large-v3', 'base')
            language: Language code (e.g., 'en', 'es', 'fr')
            verbose: Whether to print progress information

        Returns:
            Path to the output SRT file
        """
    ```
- JavaScript: No formal JSDoc observed; comments inline in methods

## Function Design

**Size:**
- Small focused functions (20-50 lines typical)
- Bash functions often 10-30 lines with clear single purpose

**Parameters:**
- Python: Explicit parameters, optional parameters with defaults
- Python type hints used: `def transcribe(audio_path: str, output_dir: str, model: str = "turbo") -> Path:`
- Avoid long parameter lists (> 5 params); use configuration objects or named parameters instead

**Return Values:**
- Python scripts: return file paths (as `Path` objects) or status dictionaries
- Web layer: return dictionaries with `success`, `message`/`error`, and operation-specific fields
  - Example: `{'success': True, 'message': 'Recording started...', 'obs_was_started': True}`
- JavaScript: methods don't explicitly return (use async/await, class state)

## Module Design

**Exports:**
- Python: Main function `main()` as entry point when run as script
- All scripts follow pattern: module functions can be imported, `if __name__ == "__main__": main()`

**Barrel Files:**
- `web/__init__.py` minimal (contains `# This module contains the web server`)
- Not used for re-exporting or organizing imports

**File Responsibilities:**
- `scripts/obs_controller.py`: OBS WebSocket communication only
- `scripts/transcribe.py`: MLX Whisper audio-to-SRT conversion
- `scripts/interleave.py`: SRT file merging and formatting
- `scripts/filter_hallucinations.py`: Hallucination detection and removal
- `web/app.py`: Flask route definitions and initialization
- `web/recorder.py`: Recording and processing orchestration
- `web/calendar_service.py`: Calendar event fetching from macOS EventKit
- `run.sh`: Main orchestration workflow (recording, processing pipeline)

## Special Patterns

**Data Structures:**
- Meeting metadata: stored in `.pending_meeting` file (plaintext, newline-delimited)
  - Line 1: meeting name
  - Line 2: meeting date (YYYYMMDD_HHMM)
  - Line 3: pipe-delimited attendees

- Queue format: `processing_queue.csv` with semicolon delimiter
  - Fields: path, name, date, status (recorded/processed/discarded), attendees
  - Example: `/path/to/file.mkv;Meeting Name;20250801_1000;recorded;Alice|Bob`

- Output JSON: Flask endpoints return `{'success': bool, ...}` format consistently

---

*Convention analysis: 2026-02-07*
