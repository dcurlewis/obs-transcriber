# OBS Meeting Transcriber

A set of scripts to automate the recording, transcription, and processing of multi-track meeting audio. This workflow uses OBS Studio to record, FFmpeg to process audio, and OpenAI's Whisper for transcription.

## Features

- **CLI Control**: Easily start, stop, and process recordings from the command line.
- **Speaker Separation**: Automatically separates your audio from other participants' audio.
- **Accurate Transcription**: Utilizes OpenAI's Whisper for high-quality speech-to-text.
- **Interleaved Transcripts**: Merges separate transcripts into a single, chronologically-ordered file with speaker labels (`Me:` and `Others:`).
- **Organized Files**: Manages recordings and transcripts in a clean, timestamped folder structure for easy access.

## Prerequisites

Before you begin, ensure you have the following installed:

1.  **OBS Studio**: [Download here](https://obsproject.com/)
2.  **OBS-Websocket Plugin**: [Installation instructions](https://github.com/obsproject/obs-websocket/releases)
3.  **FFmpeg**:
    -   macOS: `brew install ffmpeg`
    -   Windows: [Download here](https://www.ffmpeg.org/download.html)
    -   Linux: `sudo apt update && sudo apt install ffmpeg`
4.  **Python 3**: [Download here](https://www.python.org/downloads/)
5.  **Project Dependencies**: Once you have cloned the project, you need to set up a virtual environment and install the required packages.
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


## Setup

1.  **Configure OBS-Websocket**:
    -   In OBS, go to `Tools > WebSocket Server Settings`.
    -   Enable the WebSocket server.
    -   Set a server password and note it down. You will need it for the configuration file.

2.  **Configure OBS Audio Tracks**:
    -   In the OBS "Audio Mixer" panel, click the three dots on any source and select "Advanced Audio Properties".
    -   Find your microphone source and ensure it is only checked for **Track 1**.
    -   Find your Desktop Audio / Application Audio source and ensure it is only checked for **Track 2**.
    -   Uncheck all other tracks for these sources.

3.  **Configure OBS Recording Output**:
    -   Go to `File > Settings > Output`.
    -   Set "Output Mode" to "Advanced".
    -   Go to the "Recording" tab.
    -   Set "Type" to "Standard".
    -   Set **Recording Format** to **MKV**. This is crucial for multi-track audio.
    -   Note down your "Recording Path", as the scripts will need to find the recordings there.

4.  **Create Configuration File**:
    -   Create a file named `.env` in the project root.
    -   Add the following content, replacing the placeholder values with your own:
    ```ini
    [OBS]
    HOST=localhost
    PORT=4455
    PASSWORD=your_obs_websocket_password

    [WHISPER]
    MODEL=base
    LANGUAGE=en

    [PATHS]
    # This should be the same as the "Recording Path" in your OBS settings
    RECORDING_PATH=/Users/your_user/Movies 
    ```

## Usage

The main script `run.sh` provides all the necessary commands:

-   **Start Recording**:
    ```bash
    ./run.sh start "Your Meeting Name"
    ```

-   **Stop Recording**:
    ```bash
    ./run.sh stop
    ```
    This will stop the recording and add it to the processing queue.

-   **Process All Pending Recordings**:
    ```bash
    ./run.sh process
    ```
    This will find all unprocessed recordings in the queue, and then extract, transcribe, and interleave each one.

-   **Check Queue Status**:
    ```bash
    ./run.sh status
    ```
    This shows all recorded meetings and their current processing status.

-   **Discard a Recording**:
    ```bash
    ./run.sh discard
    ```
    If a recording is in progress, this will stop and delete it. Otherwise, it will present a menu of queued recordings to discard.

## Project Structure

```
.
├── .env                  # Configuration for OBS, Whisper, and paths
├── processing_queue.csv  # A log of all recordings and their status
├── recordings/           # Output directory for processed meetings
│   └── 20231027-My-Meeting/
│       ├── 20231027-My-Meeting.mkv
│       ├── 20231027-My-Meeting_me.wav
│       ├── 20231027-My-Meeting_others.wav
│       ├── 20231027-My-Meeting_me.srt
│       ├── 20231027-My-Meeting_others.srt
│       └── 20231027-My-Meeting_transcript.txt
├── scripts/              # All executable scripts
│   ├── obs_controller.py
│   ├── process_audio.py
│   └── interleave.py
└── run.sh                # Main CLI entrypoint
``` 