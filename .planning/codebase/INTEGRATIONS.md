# External Integrations

**Analysis Date:** 2026-02-07

## APIs & External Services

**OBS (Open Broadcaster Software):**
- OBS WebSocket Server - Controls recording start/stop via WebSocket API
  - SDK/Client: `obsws-python` package
  - Connection: `OBS_HOST`, `OBS_PORT`, `OBS_PASSWORD` (env vars)
  - Implementation: `scripts/obs_controller.py` uses `obsws_python.ReqClient` class
  - Methods: `get_record_status()`, `start_record()`, `stop_record()`
  - Default: localhost:4455

**Audio Transcription:**
- MLX Whisper (via HuggingFace Hub)
  - SDK/Client: `mlx-whisper` Python package
  - Models: Hosted on mlx-community HuggingFace repo
  - Implementation: `scripts/transcribe.py` calls `mlx_whisper.transcribe()`
  - Model paths: `mlx-community/whisper-turbo`, `mlx-community/whisper-base`, etc.
  - Caching: Models cached locally in `~/.cache/huggingface`
  - Authentication: None required (public models)

**Google Calendar Integration:**
- macOS Calendar.app (synced with Google Calendar)
  - SDK/Client: `pyobjc-framework-EventKit` - Native macOS EventKit framework
  - Implementation: `web/calendar_service.py` uses EventKit API
  - Authentication: System permissions (Calendar Access)
  - Data: Reads events via `EKEventStore` and EventKit predicates
  - Methods: `get_meetings_for_date()` returns meeting data
  - Conference detection: Parses event URL/notes for Zoom links

## Data Storage

**Databases:**
- None - Application is file-based

**File Storage:**
- Local filesystem only
  - Recording path: Configured via `RECORDING_PATH` env var
  - Transcription output: `TRANSCRIPTION_OUTPUT_DIR` (default: `recordings/`)
  - Processing queue: `processing_queue.csv` (semicolon-delimited)
  - Pending recording state: `.pending_meeting` file
  - Processing logs: `logs/processing.log` (with weekly rotation)

**Caching:**
- HuggingFace model cache: `~/.cache/huggingface/` (MLX Whisper models)
- No application-level cache configured

## Authentication & Identity

**Auth Provider:**
- None for API integrations
- System-level only:
  - OBS WebSocket password (shared secret)
  - macOS Calendar permission (system dialog)

**Implementation:**
- OBS: Password in `.env` file, passed to `obsws_python.ReqClient(password=...)`
- Calendar: User grants permission via macOS Privacy settings

## Monitoring & Observability

**Error Tracking:**
- None detected - no external error tracking service

**Logs:**
- Processing logs: `logs/processing.log`
- Log rotation: Weekly (keeps 4 weeks of logs)
- Format: `%(asctime)s - %(levelname)s - %(message)s`
- Implementation: `logging.handlers.TimedRotatingFileHandler` in `web/recorder.py`
- Console output: Progress indicators and status messages in `run.sh`

**Debug Mode:**
- `DEBUG_CALENDAR=true` env var enables calendar debugging output
- `FLASK_DEBUG=true` enables Flask debug mode

## CI/CD & Deployment

**Hosting:**
- Local-only - designed to run on user's machine with OBS

**CI Pipeline:**
- None detected

**Deployment:**
- Manual via git clone
- Python virtual environment setup via `python3 -m venv venv`
- Dependency installation via `pip install -r requirements.txt`

## Environment Configuration

**Required env vars:**
- `OBS_HOST` - OBS WebSocket host
- `OBS_PORT` - OBS WebSocket port
- `OBS_PASSWORD` - OBS WebSocket password
- `RECORDING_PATH` - Directory with OBS recordings

**Optional env vars:**
- `WHISPER_MODEL` - Transcription model (default: turbo)
- `WHISPER_LANGUAGE` - Language code (default: en)
- `TRANSCRIPTION_OUTPUT_DIR` - Output directory (default: recordings)
- `KEEP_RAW_RECORDING` - Keep MKV files (default: false)
- `WEB_HOST` - Web UI host (default: 127.0.0.1)
- `WEB_PORT` - Web UI port (default: 5000)
- `SECRET_KEY` - Flask session key (auto-generated if omitted)
- `FLASK_DEBUG` - Enable Flask debug mode
- `DEBUG_CALENDAR` - Enable calendar debugging

**Secrets location:**
- `.env` file (local, git-ignored)
- Environment variables (system)

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## External Command Dependencies

**System Binaries:**
- `ffmpeg` - Audio extraction and format conversion
  - Called in `run.sh` for audio track extraction from MKV
  - Parameters: 16kHz PCM mono with audio normalization filters

**Application Launch:**
- `open -a OBS` - Launch OBS.app on macOS
  - Called via `subprocess.Popen()` in `web/recorder.py`
  - Checked with `pgrep -x OBS` before launching

## Data Flow Summary

1. **Recording**: OBS records → MKV file with dual audio tracks
2. **Queue**: Recording metadata → `processing_queue.csv`
3. **Extraction**: MKV file → `ffmpeg` → WAV files (separate tracks)
4. **Transcription**: WAV files → MLX Whisper → SRT subtitles
5. **Post-processing**: SRT files → Hallucination filter → Clean SRT
6. **Interleaving**: Two SRT files → Chronological merge → Final TXT transcript
7. **Calendar**: macOS Calendar.app → EventKit → Meeting metadata (optional header in transcript)

---

*Integration audit: 2026-02-07*
