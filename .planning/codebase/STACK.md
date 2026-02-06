# Technology Stack

**Analysis Date:** 2026-02-07

## Languages

**Primary:**
- Python 3.13.7 - Core application logic (transcription, processing, web UI)
- Bash - Main orchestration script (`run.sh`) for workflow automation
- JavaScript - Web UI frontend (minimal, in `web/templates/index.html`)

**Secondary:**
- HTML/CSS - Web UI template

## Runtime

**Environment:**
- Python 3.13.7 (system or virtual environment)
- Bash shell (for orchestration)
- macOS (primary platform - uses EventKit framework)

**Package Manager:**
- pip with `requirements.txt`
- Lockfile: Not detected (no poetry.lock or Pipfile.lock present)

## Frameworks

**Core:**
- Flask 3.0+ - Web server for web UI (`web/app.py`)
- MLX Whisper 0.4.0+ - Audio transcription (Apple Silicon optimized)
- PyAnnote Audio 2.1.0+ - Audio segmentation/diarization support

**Testing:**
- Not detected - no test framework found

**Build/Dev:**
- Not detected - no build tool configured

## Key Dependencies

**Critical:**
- `mlx-whisper>=0.4.0` - Core transcription using MLX (Metal Performance Shaders on Apple Silicon)
- `obsws-python` - OBS WebSocket client for recording control
- `flask>=3.0` - Web framework for UI
- `torch>=1.9.0` - Deep learning inference (via MLX Whisper)
- `pyannote.audio>=2.1.0` - Audio diarization/speaker separation

**Infrastructure:**
- `python-dotenv` - Environment variable loading from `.env`
- `srt` - SRT subtitle file parsing/writing
- `icalendar>=5.0.0` - iCalendar format parsing (for calendar data)
- `pytz` - Timezone handling
- `tzlocal` - Local timezone detection
- `requests` - HTTP client library
- `pyobjc-framework-EventKit>=10.0` - macOS Calendar.app integration via EventKit

**Audio Processing:**
- `ffmpeg` (external binary) - Audio extraction and format conversion (16kHz PCM, mono)

**Recording:**
- OBS Studio (external) with OBS-Websocket Plugin - Screen/audio recording

## Configuration

**Environment:**
- Configured via `.env` file in project root (present but contents not inspected per security policy)
- Fallback to environment variables if not in `.env`
- Configuration sections: `[OBS]`, `[WHISPER]`, `[PATHS]`

**Build:**
- No build configuration detected (direct Python execution)
- Uses `run.sh` as main entry point

**Key Configuration Variables:**
- `OBS_HOST` (default: localhost)
- `OBS_PORT` (default: 4455)
- `OBS_PASSWORD` - OBS WebSocket password
- `WHISPER_MODEL` (default: turbo) - Model options: tiny, base, small, medium, large-v3, turbo, distil-large-v3
- `WHISPER_LANGUAGE` (default: en)
- `RECORDING_PATH` - Directory where OBS saves recordings
- `TRANSCRIPTION_OUTPUT_DIR` (default: recordings)
- `KEEP_RAW_RECORDING` (default: false)
- `FORCE_CPU_TRANSCRIPTION` - Force CPU-only inference
- `WHISPER_IGNORE_SSL` - SSL certificate verification
- `WEB_HOST` (default: 127.0.0.1)
- `WEB_PORT` (default: 5000)
- `SECRET_KEY` - Flask session secret (auto-generated if not set)

## Platform Requirements

**Development:**
- macOS (EventKit framework required for calendar integration)
- Python 3.9+
- Virtual environment with pip
- OBS Studio with OBS-Websocket Plugin enabled
- FFmpeg installed

**Production:**
- Deployment target: macOS with Apple Silicon (M-series) for optimal performance
- OBS Studio running locally or on same network
- Minimum 8GB RAM recommended for turbo model transcription

---

*Stack analysis: 2026-02-07*
