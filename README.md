# OBS Meeting Transcriber

A set of scripts to automate the recording, transcription, and processing of multi-track meeting audio. This workflow uses OBS Studio to record, FFmpeg to process audio, and MLX Whisper for transcription (optimized for Apple Silicon Macs).

## Features

- **CLI Control**: Easily start, stop, and process recordings from the command line.
- **Speaker Separation**: Automatically separates your audio from other participants' audio.
- **Speaker Diarization**: Identifies and labels different speakers in the "Others" track.
- **Fast & Accurate Transcription**: Utilizes MLX Whisper (Apple Silicon optimized via Metal) for high-quality, fast speech-to-text. Multiple model options (tiny, base, small, medium, large-v3, turbo, distil-large-v3) to balance speed and accuracy.
- **Audio Normalization**: Dynamic volume normalization and speech-frequency filtering (80Hz–8kHz) for consistent, clean input to the transcription engine.
- **Audio Validation**: Validates audio files before transcription to catch corrupt or empty files early.
- **Hallucination Filtering**: Removes common transcription artifacts and hallucinations.
- **Interleaved Transcripts**: Merges separate transcripts into a single, chronologically-ordered file with clear speaker labels.
- **Dependency Checking**: Automatically verifies required tools (FFmpeg, OBS, Python packages) are installed before running.
- **Centralized Configuration**: Validated `.env`-based config with clear error messages when settings are missing or invalid.
- **Log Sanitization**: Sensitive data (passwords, paths) is filtered from log output.
- **Organized Files**: Manages recordings and transcripts in a clean, timestamped folder structure for easy access.

## Prerequisites

Before you begin, ensure you have the following installed:

1. **OBS Studio**: [Download here](https://obsproject.com/)
2. **OBS-Websocket Plugin**: [Installation instructions](https://github.com/obsproject/obs-websocket/releases)
3. **FFmpeg**:
   - macOS: `brew install ffmpeg`
   - Windows: [Download here](https://www.ffmpeg.org/download.html)
   - Linux: `sudo apt update && sudo apt install ffmpeg`
4. **Python 3**: [Download here](https://www.python.org/downloads/)
5. **Project Dependencies**: Once you have cloned the project, you need to set up a virtual environment and install the required packages.

    ```bash
    # From the project root directory:

    # 1. Create a virtual environment
    python3 -m venv venv

    # 2. Activate the virtual environment
    # On macOS/Linux:
    source venv/bin/activate
    # On Windows:
    # .\venv\Scripts\activate

    # 3. Install the required packages
    pip install -r requirements.txt
    ```

    *Note: You will need to activate the virtual environment (`source venv/bin/activate`) in each new terminal session before running the scripts.*

6. **Speaker Diarization Setup (Optional)**:

    Speaker diarization identifies individual speakers in the "Others" track (e.g. "Speaker 1", "Speaker 2"). It is disabled by default and requires a one-time HuggingFace setup:

    1. Create a HuggingFace account at <https://huggingface.co>
    2. Accept the model license: <https://huggingface.co/pyannote/speaker-diarization-3.1>
    3. Accept the model license: <https://huggingface.co/pyannote/segmentation-3.0>
    4. Generate a read token: <https://huggingface.co/settings/tokens>
    5. Add the following to your `.env` file:

    ```ini
    ENABLE_DIARIZATION=true
    HF_TOKEN=hf_your_token_here
    ```

    Models (~95 MB total) are downloaded automatically on first use and cached in `~/.cache/huggingface/`. Subsequent runs use the cache with no download needed.

## Setup

1. **Configure OBS-Websocket**:
   - In OBS, go to `Tools > WebSocket Server Settings`.
   - Enable the WebSocket server.
   - Set a server password and note it down. You will need it for the configuration file.

2. **Configure OBS Audio Tracks**:
   - In the OBS "Audio Mixer" panel, click the three dots on any source and select "Advanced Audio Properties".
   - Find your microphone source and ensure it is only checked for **Track 1**.
   - Find your Desktop Audio / Application Audio source and ensure it is only checked for **Track 2**.
   - Uncheck all other tracks for these sources.

3. **Configure OBS Recording Output**:
   - Go to `File > Settings > Output`.
   - Set "Output Mode" to "Advanced".
   - Go to the "Recording" tab.
   - Set "Type" to "Standard".
   - Set **Recording Format** to **MKV**. This is crucial for multi-track audio.
   - Note down your "Recording Path", as the scripts will need to find the recordings there.

4. **Create Configuration File**:
   - Copy the example configuration and customize it for your setup:

    ```bash
    cp .env.example .env
    ```

   - Open `.env` and fill in at minimum:
     - `OBS_PASSWORD` — your OBS WebSocket password
     - `RECORDING_PATH` — the same path as your OBS Recording Path setting
     - `TRANSCRIPTION_OUTPUT_DIR` — where final transcripts are saved

   - To enable speaker diarization, also add:
     - `ENABLE_DIARIZATION=true`
     - `HF_TOKEN=hf_your_token_here` (see prerequisite step 6 above)

   - See `.env.example` for all available options including calendar filtering, model selection, and more.

## Usage

### Web UI (Recommended)

Start the web interface for easy one-click recording:

```bash
./run.sh web
```

Then open `http://localhost:5000` in your browser.

**Optional - Add Calendar:**

Sync your Google Calendar to macOS Calendar.app (System Settings > Internet Accounts > Add Google Account). The web UI will automatically read your calendar - no config needed!

**First time:** macOS will ask for calendar permission when you start the web UI. Click "OK" to allow.

Your meetings will appear in the UI for one-click recording. OBS launches automatically.

### CLI Commands

The `run.sh` script also provides CLI commands:

- **Start Recording**:

    ```bash
    ./run.sh start "Your Meeting Name"
    ```

- **Stop Recording**:

    ```bash
    ./run.sh stop
    ```

    This will stop the recording and add it to the processing queue.

- **Abort Recording** (Cancel without saving):

    ```bash
    ./run.sh abort
    ```

    This immediately cancels an active recording without any confirmation prompts. The recording file is deleted and nothing is added to the processing queue. Useful for:
  - Accidentally starting a recording
  - Meetings that are cancelled after recording starts
  - Test recordings you don't want to keep

- **Process All Pending Recordings**:

    ```bash
    ./run.sh process
    ```

    This will find all unprocessed recordings in the queue, and then extract, transcribe, and interleave each one.

- **Check Queue Status**:

    ```bash
    ./run.sh status
    ```

    This shows all recorded meetings and their current processing status.

- **Discard a Recording** (with confirmation):

    ```bash
    ./run.sh discard
    ```

    If a recording is in progress, this will ask for confirmation before stopping and deleting it. Otherwise, it will present an interactive menu of queued recordings to discard. Unlike `abort`, this command:
  - Always asks for confirmation before deleting
  - Can remove recordings from the queue after they've been stopped
  - Marks discarded recordings in the processing queue for audit purposes

## Project Structure

```text
.
├── .env.example              # Documented configuration template
├── .env                      # Your local configuration (copy from .env.example)
├── .github/workflows/
│   └── test.yml              # CI workflow (GitHub Actions)
├── processing_queue.csv      # A log of all recordings and their status
├── pytest.ini                # Test configuration
├── recordings/               # Default output directory for transcripts
│   ├── 20231027-My-Meeting_transcript.txt
│   └── 20231028-Another-Meeting_transcript.txt
├── scripts/                  # All executable scripts
│   ├── audio_validator.py    # Validates audio files before transcription
│   ├── config.py             # Centralized configuration with validation
│   ├── dependencies.py       # Dependency checking (FFmpeg, OBS, etc.)
│   ├── filter_hallucinations.py  # Removes transcription artifacts
│   ├── interleave.py         # Merges transcripts with timestamps
│   ├── log_sanitizer.py      # Sanitizes sensitive data in logs
│   ├── obs_controller.py     # Controls OBS recording via WebSocket
│   ├── queue_cli.py          # CLI wrapper for queue management
│   ├── queue_manager.py      # Queue with file locking and atomic writes
│   ├── root_detection.py     # Centralized project root detection
│   ├── diarize.py            # Speaker diarization via pyannote.audio (optional)
│   └── transcribe.py         # MLX Whisper transcription (Apple Silicon)
├── tests/                    # Automated test suite
│   ├── conftest.py           # Shared fixtures
│   ├── test_config.py        # Configuration validation tests
│   ├── test_pipeline_integration.py  # End-to-end workflow tests
│   ├── test_queue_manager.py # CSV parsing, locking, atomic writes
│   └── test_root_detection.py    # Path resolution tests
├── web/                      # Web UI
│   ├── app.py                # Flask server
│   ├── calendar_service.py   # macOS Calendar integration
│   ├── recorder.py           # Recording controller
│   ├── static/               # CSS, JS, favicon
│   └── templates/            # HTML templates
└── run.sh                    # Main entrypoint (CLI and Web UI)
```

Note: During processing, temporary files (MKV, WAV, SRT) are created in a subdirectory but cleaned up after successful transcription. Only the final transcript file is saved to your configured output directory.

## Testing

The project includes automated tests for regression protection.

### Running Tests Locally

**Install test dependencies:**
```bash
pip install -r requirements.txt  # Includes pytest and pytest-cov
```

**Run all tests:**
```bash
pytest
```

**Run only fast unit tests (skip integration tests):**
```bash
pytest -m "not integration"
```

**Run with coverage report:**
```bash
pytest --cov=scripts --cov=web --cov-report=html
open htmlcov/index.html  # View coverage report
```

**Run specific test file:**
```bash
pytest tests/test_queue_manager.py -v
```

### Test Organization

- `tests/test_queue_manager.py` - CSV parsing, file locking, atomic writes (TEST-01)
- `tests/test_config.py` - Configuration validation (TEST-02)
- `tests/test_root_detection.py` - Path resolution from multiple directories (TEST-03)
- `tests/test_pipeline_integration.py` - End-to-end transcription workflow (TEST-04)

### Continuous Integration

Tests run automatically on every push via GitHub Actions. The CI workflow:
1. Runs unit tests (all tests not marked `integration`)
2. Runs integration tests (marked with `@pytest.mark.integration`)
3. Generates coverage reports
4. Uploads coverage to Codecov (if configured)

See `.github/workflows/test.yml` for workflow configuration.
