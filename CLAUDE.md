# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OBS Meeting Transcriber is a set of scripts to automate the recording, transcription, and processing of multi-track meeting audio. The workflow uses:

- OBS Studio to record
- FFmpeg to process audio
- OpenAI's Whisper for transcription

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
   - OpenAI Whisper

1. Configuration via `.env` file in project root:

```ini
[OBS]
HOST=localhost
PORT=4455
PASSWORD=your_obs_websocket_password

[WHISPER]
MODEL=base
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
- GPU acceleration is used when available (CUDA, MPS on Apple Silicon)
- SSL bypass option is available for corporate networks with certificate issues
- Error recovery is implemented to handle transcription failures

## Troubleshooting

If transcription fails:

- First attempt recovery using CPU fallback
- Check audio file integrity
- Try manual transcription with the Whisper CLI
- Check available disk space and memory

Common issues:

- OBS WebSocket connectivity failures
- Corrupted audio files
- Network issues affecting Whisper model downloads
