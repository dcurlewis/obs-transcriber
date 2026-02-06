# Codebase Structure

**Analysis Date:** 2026-02-07

## Directory Layout

```
obs-transcriber/
├── run.sh                      # Main entry point: orchestrates entire workflow
├── requirements.txt            # Python dependencies
├── .env                        # Configuration: OBS, Whisper, paths (secrets)
├── CLAUDE.md                   # Developer instructions
├── README.md                   # Project documentation
├── processing_queue.csv        # State machine: tracks recording lifecycle
├── .pending_meeting            # Transient: current recording metadata
├── scripts/                    # Core Python processing modules
│   ├── obs_controller.py      # OBS WebSocket control
│   ├── transcribe.py          # MLX Whisper transcription to SRT
│   ├── interleave.py          # Merge SRT files into chronological transcript
│   └── filter_hallucinations.py # Remove Whisper artifacts
├── web/                        # Flask web UI and API
│   ├── app.py                 # Flask routes and API endpoints
│   ├── recorder.py            # Recording controller class
│   ├── calendar_service.py    # Google Calendar integration
│   ├── __init__.py            # Module initialization
│   ├── static/                # CSS, JS assets
│   └── templates/
│       └── index.html         # Web UI HTML
├── recordings/                # Output directory (default)
│   └── YYYYMMDD-Meeting-Name/ # Per-recording subdirectory
│       ├── YYYYMMDD-Name_transcript.txt  # Final output
│       ├── YYYYMMDD-Name_me.wav         # Intermediate (deleted after SRT)
│       ├── YYYYMMDD-Name_others.wav     # Intermediate (deleted after SRT)
│       ├── YYYYMMDD-Name_me.srt         # Intermediate (deleted after merge)
│       ├── YYYYMMDD-Name_others.srt     # Intermediate (deleted after merge)
│       └── YYYYMMDD-Name.mkv            # Optional: kept if KEEP_RAW_RECORDING=true
├── logs/                      # Log files
│   └── processing.log         # Processing activity log (weekly rotation)
├── venv/                      # Python virtual environment
└── .claude/                   # GSD/Claude workspace config (git-ignored)
```

## Directory Purposes

**`scripts/`:**
- Purpose: Core processing modules for recording control, transcription, and post-processing
- Contains: Python scripts for orchestration by bash main script
- Key files: `obs_controller.py`, `transcribe.py`, `interleave.py`, `filter_hallucinations.py`

**`web/`:**
- Purpose: Web UI and REST API for recording management and calendar integration
- Contains: Flask application, recording controller, calendar service
- Key files: `app.py` (Flask routes), `recorder.py` (business logic), `calendar_service.py` (Google Calendar)

**`recordings/`:**
- Purpose: Final output directory for processed transcripts
- Contains: Per-meeting subdirectories with transcripts, logs, optionally raw files
- Default location: `./recordings` (configurable via `TRANSCRIPTION_OUTPUT_DIR` in `.env`)

**`logs/`:**
- Purpose: Persistent logging of processing activity
- Contains: `processing.log` with weekly rotation
- Pattern: Weekly rotation on Mondays, 4-week retention

## Key File Locations

**Entry Points:**
- `./run.sh`: Main CLI entry point for all operations (start, stop, process, status, discard, web)

**Configuration:**
- `.env`: Environment configuration (OBS host/port/password, Whisper model, paths) - **SECRETS FILE, never commit**
- `requirements.txt`: Python dependencies

**Core Logic:**
- `scripts/obs_controller.py`: OBS WebSocket connection and start/stop commands
- `scripts/transcribe.py`: Audio-to-text conversion via MLX Whisper, SRT output
- `scripts/interleave.py`: Merge and sort two SRT files chronologically
- `scripts/filter_hallucinations.py`: Pattern-based hallucination detection and removal

**State Machine:**
- `processing_queue.csv`: Recording lifecycle tracking (path, name, date, status, attendees)
- `.pending_meeting`: Transient file tracking current active recording

**Web UI:**
- `web/app.py`: Flask application with REST API endpoints
- `web/recorder.py`: Recording controller business logic
- `web/calendar_service.py`: Google Calendar service integration
- `web/templates/index.html`: Web UI HTML template

## Naming Conventions

**Files:**

**Bash Scripts:**
- Pattern: Lowercase with underscores: `run.sh`, `start_recording()`, `process_recordings()`

**Python Scripts:**
- Pattern: Lowercase with underscores: `obs_controller.py`, `transcribe.py`, `filter_hallucinations.py`

**Output Files:**
- Pattern: `YYYYMMDD_HHMM-{sanitized_meeting_name}_{component}`
- Examples:
  - `20250207_1430-Team-Standup_me.wav` (audio track)
  - `20250207_1430-Team-Standup_me.srt` (transcript segment)
  - `20250207_1430-Team-Standup_transcript.txt` (final transcript)
- Sanitization: All non-alphanumeric characters replaced with hyphens

**Directories:**

**Recording Directories:**
- Pattern: `YYYYMMDD-{sanitized_meeting_name}`
- Purpose: Isolate all processing artifacts for a single recording
- Lifecycle: Deleted when processing completes (unless `KEEP_RAW_RECORDING=true`)

**Module Directories:**
- Pattern: Lowercase, functional grouping: `scripts/`, `web/`, `logs/`, `recordings/`

## Where to Add New Code

**New Feature (Processing Pipeline Enhancement):**
- Primary code: `scripts/` directory for new processing stage
- Integration: Call from `run.sh` as new function
- Tests: Create corresponding test in desired testing framework
- Example: New speaker detection → `scripts/detect_speakers.py` + call in `process_recordings()`

**New Component/Module:**
- Implementation: `scripts/` for backend logic, `web/` for UI endpoints
- Pattern: Create new `.py` file, implement main logic function, add `main()` CLI interface
- Imports: Import and use from orchestration script or web endpoint

**Utilities:**
- Shared helpers: `scripts/utils.py` or within specific script module
- Pattern: Avoid duplication; if used by multiple scripts, centralize
- Current pattern: Each script is self-contained; consider refactoring shared utility logic

**Web UI Enhancements:**
- Frontend: `web/templates/` for HTML, `web/static/` for CSS/JS
- Backend: `web/app.py` for new routes, `web/recorder.py` for business logic
- Pattern: Add route → add recorder method → update HTML UI

## Special Directories

**`venv/`:**
- Purpose: Python virtual environment (local dependencies isolation)
- Generated: Yes (created via `python3 -m venv venv`)
- Committed: No (excluded in `.gitignore`)

**`logs/`:**
- Purpose: Processing activity logging with rotation
- Generated: Yes (created automatically by first run)
- Committed: No (log files excluded)
- Retention: Weekly rotation on Mondays, keeps 4 weeks (configurable in `recorder.py`)

**`.pending_meeting`:**
- Purpose: Tracks current active recording session
- Generated: Yes (created by `start_recording()`)
- Committed: No (transient state)
- Lifecycle: Removed after `stop_recording()` or `abort_recording()`

**`.claude/`:**
- Purpose: GSD/Claude workspace configuration
- Generated: Yes (Claude commands write config here)
- Committed: No (excluded in `.gitignore`)

**`recordings/`:**
- Purpose: Output directory for all final transcripts
- Generated: Yes (created by processing pipeline)
- Committed: No (data files excluded)
- Structure: One subdirectory per recording with nested artifacts

## Processing File Lifecycle

**Recording Phase:**
1. `./run.sh start "Meeting Name"` → Creates `.pending_meeting`
2. OBS records → Creates `~/Movies/[timestamp].mkv` (or `RECORDING_PATH` configured location)

**Extraction Phase:**
1. `./run.sh stop` → Adds entry to `processing_queue.csv` with status "recorded"
2. `.pending_meeting` removed
3. Latest MKV moved to `recordings/YYYYMMDD-Name/YYYYMMDD-Name.mkv`

**Transcription Phase:**
1. FFmpeg extracts audio → `*_me.wav`, `*_others.wav` in recording subdirectory
2. MLX Whisper transcribes in parallel → `*_me.srt`, `*_others.srt`
3. Hallucination filter applied in-place

**Merge Phase:**
1. `interleave.py` merges SRTs → `recordings/YYYYMMDD-Name_transcript.txt` (final output)
2. Intermediate WAV and SRT files deleted (if processing successful)
3. Recording subdirectory deleted if empty (unless `KEEP_RAW_RECORDING=true`)

**Recovery Points:**
- After audio extraction: Can re-run transcription if it fails
- After transcription: Can re-run hallucination filtering
- After hallucination filtering: Can re-run interleaving
- Any stage: Intermediate files preserved if prior stage failed

---

*Structure analysis: 2026-02-07*
