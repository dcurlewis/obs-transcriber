# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OBS Meeting Transcriber is a set of scripts to automate the recording, transcription, and processing of multi-track meeting audio. The workflow uses:

- OBS Studio to record
- FFmpeg to process audio
- MLX Whisper for transcription (optimized for Apple Silicon)

## Environment Setup

1. The project requires a Python virtual environment:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# .\venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

1. Required external dependencies:
   - OBS Studio with OBS-Websocket Plugin
   - FFmpeg
   - Python 3
   - MLX Whisper (Apple Silicon optimized)

1. Configuration via `.env` file in project root:

```ini
[OBS]
HOST=localhost
PORT=4455
PASSWORD=your_obs_websocket_password

[WHISPER]
# Model options: tiny, base, small, medium, large-v3, turbo, distil-large-v3
MODEL=turbo
LANGUAGE=en

[PATHS]
RECORDING_PATH=/Users/your_user/Movies  # Path to OBS recordings
TRANSCRIPTION_OUTPUT_DIR=recordings     # Path for transcription output (default: "recordings")
```

## Commands

The main entry point is `run.sh` which handles all operations:

- **Start Recording**: `./run.sh start "Meeting Name"`
- **Stop Recording**: `./run.sh stop`
- **Process Recordings**: `./run.sh process`
- **Check Queue Status**: `./run.sh status`
- **Discard a Recording**: `./run.sh discard`

## Code Architecture

The codebase consists of:

1. **Main Controller**: `run.sh` - Bash script that handles the entire workflow orchestration
   - Controls recording (start/stop)
   - Processes recordings (audio extraction, transcription, interleaving)
   - Manages recording queue (status display, discarding)
   - Error handling and recovery

2. **Python Scripts**:
   - `scripts/obs_controller.py` - Controls OBS via the WebSocket API
   - `scripts/transcribe.py` - Transcribes audio using MLX Whisper (Apple Silicon optimized)
   - `scripts/interleave.py` - Merges separate transcripts into a single chronological file
   - `scripts/filter_hallucinations.py` - Removes common hallucinations from Whisper transcriptions

3. **Data Flow**:
   - Recording creation: OBS creates a MKV file with multiple audio tracks
   - Audio extraction: FFmpeg extracts "Me" and "Others" audio tracks as separate WAV files
   - Transcription: Whisper converts WAV files to SRT transcripts
   - Post-processing: Hallucination filtering cleans transcripts
   - Final output: Interleaving script combines transcripts into a chronological TXT file

4. **File Organization**:
   - `processing_queue.csv` - Tracks recording status (recorded, processed, discarded)
   - `recordings/` (or configured path) - Contains final transcript files:
     - `YYYYMMDD-Meeting-Name_transcript.txt`
   - Temporary processing directories are created during transcription but cleaned up afterward

## Development Notes

- Audio processing parameters are optimized for speech recognition
- MLX Whisper automatically uses Apple Silicon GPU acceleration (Metal)
- Error recovery is implemented to handle transcription failures
- Model downloads are cached in HuggingFace hub cache (~/.cache/huggingface)

## Working with Git and Terminal Commands

**IMPORTANT**: When running git commands (status, add, commit, push, pull, diff, etc.) in this workspace:
- **ALWAYS** use `required_permissions: ["all"]`
- The sandbox does not work properly with git operations - they will fail or give incomplete output
- Never waste time trying git commands in the sandbox first
- Go straight to `required_permissions: ["all"]` for any git operation

This applies to any command that needs to interact with git state or push to remote repositories.

## Troubleshooting

If transcription fails:

- The script will automatically retry with a smaller model (base)
- Check audio file integrity with: `ffmpeg -i audio.wav -f null -`
- Try manual transcription: `python scripts/transcribe.py audio.wav -o ./output -m base`
- Check available disk space and memory

Common issues:

- OBS WebSocket connectivity failures
- Corrupted audio files
- Network issues affecting initial model downloads from HuggingFace
- Insufficient memory for larger models (try `base` or `small` instead of `turbo`)
