# Architecture

**Analysis Date:** 2026-02-07

## Pattern Overview

**Overall:** Three-tier pipeline architecture with orchestration, processing, and service layers.

**Key Characteristics:**
- **Orchestration-driven**: Central bash script (`run.sh`) controls entire workflow
- **Sequential processing pipeline**: Each stage (record → extract → transcribe → interleave) has clear dependencies
- **Dual interface**: CLI-first with optional Flask web UI wrapper
- **Modular Python services**: Specialized scripts for OBS control, transcription, and post-processing
- **Queue-based state machine**: CSV file tracks recording states through lifecycle (recorded → processed → discarded)

## Layers

**Orchestration Layer:**
- Purpose: Workflow control, state management, dependency orchestration
- Location: `run.sh`
- Contains: Main command dispatcher, queue management, error recovery
- Depends on: Python services, FFmpeg, file system
- Used by: User CLI and web UI

**Recording Control Layer:**
- Purpose: Interface with OBS Studio via WebSocket
- Location: `scripts/obs_controller.py`
- Contains: OBS connection logic, start/stop commands
- Depends on: obsws_python library, environment config
- Used by: Orchestration layer

**Audio Processing Layer:**
- Purpose: Extract and normalize audio tracks from video containers
- Location: `run.sh` (FFmpeg invocation)
- Contains: FFmpeg command with audio normalization and filtering
- Depends on: FFmpeg binary, input MKV files
- Used by: Orchestration layer

**Transcription Layer:**
- Purpose: Convert audio to timestamped text via speech-to-text
- Location: `scripts/transcribe.py`
- Contains: MLX Whisper integration, SRT format output
- Depends on: mlx-whisper library, HuggingFace model downloads
- Used by: Orchestration layer (parallel execution)

**Post-Processing Layer:**
- Purpose: Clean and validate transcription output
- Location: `scripts/filter_hallucinations.py`, `scripts/interleave.py`
- Contains: Hallucination filtering, speaker diarization parsing, chronological merging
- Depends on: srt library, SRT input files
- Used by: Orchestration layer

**Web Service Layer:**
- Purpose: HTTP API and UI for recording management
- Location: `web/app.py`, `web/recorder.py`, `web/calendar_service.py`
- Contains: Flask routes, Google Calendar integration, processing state tracking
- Depends on: Flask, calendar libraries, recorder module
- Used by: Browser clients

## Data Flow

**Recording Creation Flow:**
1. User invokes `./run.sh start "Meeting Name"` or web UI
2. Orchestration layer:
   - Writes `.pending_meeting` with meeting name and timestamp
   - Calls `scripts/obs_controller.py start`
3. OBS records to MKV file with multiple audio tracks (Me, Others)
4. User stops: `./run.sh stop` or web UI
5. Orchestration layer:
   - Finds latest MKV in `RECORDING_PATH`
   - Appends entry to `processing_queue.csv` with status "recorded"
   - Removes `.pending_meeting`

**Processing Pipeline Flow:**

```
MKV Input (Multi-track audio)
    ↓
[FFmpeg Audio Extraction]
    ├─ Extract track 0 → Me.wav (with normalization & filtering)
    └─ Extract track 1 → Others.wav (with normalization & filtering)
    ↓
[Parallel Transcription - MLX Whisper]
    ├─ Me.wav → Me.srt (with speaker label: "Me")
    └─ Others.wav → Others.srt (with speaker diarization: "[Speaker 1]", "[Speaker 2]", etc.)
    ↓
[Hallucination Filtering]
    ├─ Remove common patterns (thanks, subscribe, etc.)
    └─ Remove orphaned utterances
    ↓
[Interleaving & Merging]
    ├─ Parse speaker labels from diarization
    ├─ Sort by chronological timestamp
    └─ Output: Transcript.txt with format [HH:MM:SS] Speaker: text
    ↓
[Cleanup & State Update]
    ├─ Delete WAV and SRT intermediates (if transcription successful)
    ├─ Update CSV status to "processed"
    └─ Output: Final transcript in RECORDINGS_DIR
```

**State Management:**
- Processing queue stored in `processing_queue.csv` with columns: `path;name;date;status;attendees`
- Status states: `recorded` → `processed` or `discarded`
- Temporary meeting info in `.pending_meeting` (deleted after stop)
- Recovery: If processing interrupted, intermediate files (Me.srt, Others.srt) allow resume

## Key Abstractions

**Queue-Based State Machine:**
- Purpose: Track recording lifecycle and recovery
- Implementation: `processing_queue.csv` with semicolon-delimited fields
- Pattern: Each processing run reads entire queue, updates status in-place

**Audio Processing Pipeline:**
- Purpose: Normalize and extract audio for optimal transcription
- Key settings: 16kHz sample rate, mono, 16-bit PCM, dynaudnorm + highpass/lowpass filters
- Pattern: Applied consistently to all audio before transcription

**Multi-Model Transcription with Fallback:**
- Purpose: Handle transcription failures gracefully
- Pattern: Try primary model (configurable, default: turbo) → fallback to "base" on failure
- Implementation: Parallel processes for Me/Others with per-process error handling

**Speaker Attribution:**
- Purpose: Identify speakers in multi-speaker audio
- Pattern: "Me" track explicitly labeled; "Others" track uses diarization labels extracted from Whisper output
- Extraction: `[Speaker 1]` → `Speaker 1`, `[Speaker 2]` → `Speaker 2`

**Hallucination Filtering:**
- Purpose: Remove common Whisper artifacts (YouTube training data leakage)
- Patterns detected: "Thank you", "Subscribe", isolated words in long gaps, repeated short phrases
- Implementation: Regex matching + temporal gap detection

## Entry Points

**CLI Entry Point:**
- Location: `run.sh`
- Invocation: `./run.sh <command> [args]`
- Responsibilities:
  - Parse command (start, stop, process, status, discard, abort, web)
  - Load `.env` configuration
  - Orchestrate Python scripts and FFmpeg
  - Manage queue lifecycle

**Web UI Entry Point:**
- Location: `web/app.py` (Flask)
- Invocation: `./run.sh web` or `python -m web.app`
- Responsibilities:
  - Serve HTML UI via `/`
  - Provide REST API endpoints for status, meetings, start, stop, process, discard
  - Integrate with Google Calendar

**Recording Management Endpoints (Web):**
- `GET /api/status` → Current recording state and queue
- `GET /api/meetings?date=YYYY-MM-DD` → Calendar meetings for date
- `POST /api/start` → Start new recording with name and attendees
- `POST /api/stop` → Stop current recording
- `POST /api/process` → Trigger queue processing
- `POST /api/discard` → Discard specific recording

## Error Handling

**Strategy:** Defensive layering with recovery at each stage

**Patterns:**

1. **File Verification**:
   - Verify intermediate files before deleting predecessor
   - Example: Verify Me.wav and Others.wav exist before deleting MKV
   - Pattern: Check both `-f` (exists) and `-s` (non-empty) before proceeding

2. **Transcription Failure Recovery**:
   - If parallel transcription fails, retry with smaller model (base)
   - If still fails, preserve WAV files and SRT files for manual investigation
   - Location: `run.sh` lines 287-335

3. **Queue Corruption Prevention**:
   - Use temp files for queue updates, then atomic rename
   - Use file descriptors (FD 3) to isolate subprocess stdin from queue reading
   - Location: `run.sh` lines 158-169, 430-444

4. **Graceful Status Tracking**:
   - Skip malformed CSV entries with warning instead of crashing
   - Log all state changes for debugging
   - Location: `run.sh` lines 465-470

## Cross-Cutting Concerns

**Logging:**
- Bash: echo to stdout with status emojis
- Python: Configurable verbose mode, direct stdout
- Web: Rotating file handler in `logs/processing.log` (weekly rotation, 4-week retention)

**Validation:**
- Meeting name: Non-empty string
- Audio files: Checked for existence and non-zero size
- SRT files: Parsed via srt library, checked for segment count
- CSV entries: 4-5 semicolon-delimited fields required

**Authentication:**
- OBS: WebSocket password from `.env` (OBS_PASSWORD)
- Google Calendar: Implicit via OAuth flow (handled by pyobjc)
- Web UI: Optional SECRET_KEY for Flask session management

**Performance Optimization:**
- Parallel transcription: Me and Others transcribed simultaneously (~50% speedup)
- Audio normalization: Applied during extraction to avoid separate pass
- Model caching: MLX Whisper caches models in HuggingFace cache directory
- Lazy module imports: Only load when needed (especially OBS module)

---

*Architecture analysis: 2026-02-07*
