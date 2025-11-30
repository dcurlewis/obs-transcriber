# OBS Meeting Transcriber

A set of scripts to automate the recording, transcription, and processing of multi-track meeting audio. This workflow uses OBS Studio to record, FFmpeg to process audio, and MLX Whisper for transcription (optimized for Apple Silicon Macs).

## Features

- **CLI Control**: Easily start, stop, and process recordings from the command line.
- **Speaker Separation**: Automatically separates your audio from other participants' audio.
- **Speaker Diarization**: Identifies and labels different speakers in the "Others" track.
- **Fast & Accurate Transcription**: Utilizes MLX Whisper (Apple Silicon optimized) for high-quality, fast speech-to-text with audio normalization.
- **Hallucination Filtering**: Removes common transcription artifacts and hallucinations.
- **Interleaved Transcripts**: Merges separate transcripts into a single, chronologically-ordered file with clear speaker labels.
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
   - For speaker diarization, you need a Hugging Face account and access token
   - Visit <https://huggingface.co/pyannote/speaker-diarization> and accept the terms
   - Get your access token from <https://huggingface.co/settings/tokens>
   - Use your token when prompted during the first diarization run

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
   - Create a file named `.env` in the project root.
   - Add the following content, replacing the placeholder values with your own:

    ```ini
    [OBS]
    HOST=localhost
    PORT=4455
    PASSWORD=your_obs_websocket_password

    [WHISPER]
    # Model options: tiny, base, small, medium, large-v3, turbo, distil-large-v3
    # 'turbo' (large-v3-turbo) recommended for best speed/accuracy balance
    MODEL=turbo
    LANGUAGE=en

    [PATHS]
    # This should be the same as the "Recording Path" in your OBS settings
    RECORDING_PATH=/Users/your_user/Movies 
    # Directory where transcriptions will be saved (default: "recordings")
    TRANSCRIPTION_OUTPUT_DIR=recordings
    ```

## Usage

The main script `run.sh` provides all the necessary commands:

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
├── .env                  # Configuration for OBS, Whisper, and paths
├── processing_queue.csv  # A log of all recordings and their status
├── recordings/           # Default output directory for transcripts
│   ├── 20231027-My-Meeting_transcript.txt
│   └── 20231028-Another-Meeting_transcript.txt
├── scripts/              # All executable scripts
│   ├── obs_controller.py        # Controls OBS recording via WebSocket
│   ├── transcribe.py            # MLX Whisper transcription (Apple Silicon)
│   ├── interleave.py            # Merges transcripts with timestamps
│   ├── filter_hallucinations.py # Removes transcription artifacts
│   └── speaker_diarization.py   # Identifies different speakers
└── run.sh                # Main CLI entrypoint
```

Note: During processing, temporary files (MKV, WAV, SRT) are created in a subdirectory but cleaned up after successful transcription. Only the final transcript file is saved to your configured output directory.

## Recent Improvements

The following enhancements have been made to improve the quality and usefulness of transcriptions:

### Audio Processing

- **Dynamic Audio Normalization**: The system now applies dynamic audio normalization for consistent volume levels, significantly improving transcription accuracy for quiet or distant speakers.
- **Optimized Speech Filters**: Audio is filtered to focus on speech frequencies (80Hz-8kHz) for cleaner transcriptions.

### Speaker Identification

- **Speaker Diarization**: The system now identifies different speakers in the "Others" audio track and labels them as "Speaker 1", "Speaker 2", etc., making it much easier to follow conversations in the transcript.
- **Label Preservation**: Speaker labels are preserved throughout the processing pipeline and reflected in the final transcript.

### Error Handling

- **Improved Troubleshooting**: Better error messages and recovery options for failed transcriptions.
- **Robust File Processing**: Added safety checks to prevent data loss when processing audio files.
- **Hallucination Filtering**: Automatic removal of common transcription artifacts and "hallucinations" (like repeated "Thank you" phrases during silence).

### Apple Silicon Optimization

- **MLX Whisper**: Uses MLX Whisper, which is specifically optimized for Apple Silicon Macs using the Metal framework.
- **Automatic GPU Utilization**: MLX automatically leverages Apple's Neural Engine and GPU for significantly faster transcription.
- **Multiple Model Options**: Choose from various models (tiny, base, small, medium, large-v3, turbo, distil-large-v3) based on your speed/accuracy needs.
