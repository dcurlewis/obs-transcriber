#!/bin/bash
# DEBUG VERSION - Preserves intermediate files for troubleshooting
# This is a copy of run.sh with staged deletion disabled

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Source environment variables from .env file if it exists
if [ -f .env ]; then
    set -o allexport; source .env; set +o allexport
fi

# Set defaults if not provided in .env
WHISPER_MODEL=${WHISPER_MODEL:-base}
WHISPER_LANGUAGE=${WHISPER_LANGUAGE:-en}
RECORDING_PATH_RAW=${RECORDING_PATH:-.}
RECORDING_PATH="${RECORDING_PATH_RAW/\~/$HOME}"

# --- Setup Python Command ---
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
    echo "Using Python from virtual environment."
else
    PYTHON_CMD=$(which python3)
    echo "Using system Python: $PYTHON_CMD"
fi

PENDING_FILE=".pending_meeting"
QUEUE_FILE="processing_queue.csv"
SCRIPTS_DIR="scripts"
RECORDINGS_DIR="recordings"

# --- Helper Functions ---
function check_deps() {
    for cmd in "$@"; do
        if ! command -v $cmd &> /dev/null; then
            echo "Error: Required command '$cmd' not found. Please install it."
            exit 1
        fi
    done
}

function debug_audio_analysis() {
    local target_dir="$1"
    local basename="$2"
    
    echo "🔍 DEBUG: Running audio analysis..."
    
    # Analyze MKV file
    if [ -f "$target_dir/${basename}.mkv" ]; then
        echo "Analyzing MKV file:"
        $PYTHON_CMD scripts/debug_audio.py analyze-mkv "$target_dir/${basename}.mkv"
    fi
    
    # Analyze WAV files
    if [ -f "$target_dir/${basename}_me.wav" ]; then
        echo "Analyzing 'me' WAV file:"
        $PYTHON_CMD scripts/debug_audio.py analyze-wav "$target_dir/${basename}_me.wav"
    fi
    
    if [ -f "$target_dir/${basename}_others.wav" ]; then
        echo "Analyzing 'others' WAV file:"
        $PYTHON_CMD scripts/debug_audio.py analyze-wav "$target_dir/${basename}_others.wav"
    fi
    
    # Extract samples for manual inspection
    if [ -f "$target_dir/${basename}_others.wav" ]; then
        echo "Extracting sample from 'others' track for manual inspection:"
        $PYTHON_CMD scripts/debug_audio.py extract-sample "$target_dir/${basename}_others.wav"
    fi
}

function process_recordings() {
    if [ ! -f "$QUEUE_FILE" ]; then
        echo "Processing queue is empty. Nothing to do."
        return
    fi

    UNPROCESSED_COUNT=$(grep -c ';recorded$' "$QUEUE_FILE" || true)
    if [ "$UNPROCESSED_COUNT" -eq 0 ]; then
        echo "No recordings to process."
        return
    fi

    echo "🐛 DEBUG MODE: Intermediate files will be preserved for analysis"
    echo "Found $UNPROCESSED_COUNT recordings to process..."
    
    TEMP_QUEUE_FILE=$(mktemp)
    cp "$QUEUE_FILE" "$TEMP_QUEUE_FILE"

    while IFS=';' read -r raw_mkv_path meeting_name meeting_date status; do
        if [ "$status" = "recorded" ]; then
            echo "-----------------------------------------------------"
            echo "Processing: '$meeting_name' from $meeting_date"
            echo "Source file: $raw_mkv_path"
            
            SANITIZED_NAME=$(echo "$meeting_name" | sed 's/[^a-zA-Z0-9]/-/g')
            FINAL_BASENAME="${meeting_date}-${SANITIZED_NAME}"
            TARGET_DIR="${RECORDINGS_DIR}/${FINAL_BASENAME}"

            mkdir -p "$TARGET_DIR"

            # Move and rename original recording
            if [ -f "$raw_mkv_path" ]; then
                echo "Moving source file to target directory..."
                mv "$raw_mkv_path" "$TARGET_DIR/${FINAL_BASENAME}.mkv"
            else
                echo "Source file already moved. Skipping move."
            fi

            # --- Audio Extraction ---
            if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] || [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                echo "Extracting audio tracks with ffmpeg..."
                ffmpeg -i "$TARGET_DIR/${FINAL_BASENAME}.mkv" \
                    -map 0:a:0 "$TARGET_DIR/${FINAL_BASENAME}_me.wav" \
                    -map 0:a:1 "$TARGET_DIR/${FINAL_BASENAME}_others.wav" \
                    -loglevel error
                
                if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                    echo "Audio extraction successful."
                    # DEBUG: Skip MKV deletion
                    echo "🐛 DEBUG: Keeping MKV file for analysis"
                else
                    echo "Warning: Audio extraction failed."
                fi
            else
                echo "Audio tracks already extracted. Skipping ffmpeg."
            fi

            # --- DEBUG: Audio Analysis ---
            debug_audio_analysis "$TARGET_DIR" "$FINAL_BASENAME"

            # --- Transcription ---
            echo "Transcribing audio with Whisper (Model: $WHISPER_MODEL)..."
            if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ]; then
                 whisper --model "$WHISPER_MODEL" --language "$WHISPER_LANGUAGE" --output_format srt \
                    --output_dir "$TARGET_DIR" "$TARGET_DIR/${FINAL_BASENAME}_me.wav"
            else
                echo "My audio already transcribed. Skipping."
            fi

            if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                whisper --model "$WHISPER_MODEL" --language "$WHISPER_LANGUAGE" --output_format srt \
                    --output_dir "$TARGET_DIR" "$TARGET_DIR/${FINAL_BASENAME}_others.wav"
            else
                echo "Others audio already transcribed. Skipping."
            fi
            
            if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                echo "Transcription successful."
                # DEBUG: Skip WAV deletion
                echo "🐛 DEBUG: Keeping WAV files for analysis"
            else
                echo "Warning: Transcription failed."
            fi
            
            # --- Interleaving ---
            echo "Interleaving transcripts..."
            $PYTHON_CMD "$SCRIPTS_DIR/interleave.py" \
                "$TARGET_DIR/${FINAL_BASENAME}_me.srt" \
                "$TARGET_DIR/${FINAL_BASENAME}_others.srt" > "$TARGET_DIR/${FINAL_BASENAME}_transcript.txt"
            
            if [ -f "$TARGET_DIR/${FINAL_BASENAME}_transcript.txt" ]; then
                echo "Interleaving successful."
                # DEBUG: Skip SRT deletion
                echo "🐛 DEBUG: Keeping SRT files for analysis"
            else
                echo "Warning: Interleaving failed."
            fi

            # Update status
            TEMP_QUEUE_UPDATE=$(mktemp)
            ESCAPED_PATH=$(printf '%s\n' "$raw_mkv_path" | sed 's:[][\\/.^$*]:\\&:g')
            sed "s/$ESCAPED_PATH;$meeting_name;$meeting_date;recorded/$ESCAPED_PATH;$meeting_name;$meeting_date;processed/" "$QUEUE_FILE" > "$TEMP_QUEUE_UPDATE"
            mv "$TEMP_QUEUE_UPDATE" "$QUEUE_FILE"

            echo "Processing complete!"
            echo "🐛 DEBUG: All intermediate files preserved in: $TARGET_DIR"
            echo "Final transcript: $TARGET_DIR/${FINAL_BASENAME}_transcript.txt"
        fi
    done < "$TEMP_QUEUE_FILE"

    rm "$TEMP_QUEUE_FILE"
    echo "-----------------------------------------------------"
    echo "🐛 DEBUG MODE: All recordings processed with files preserved for analysis"
}

# --- Main Logic ---
if [ -z "$1" ]; then
    echo "Usage: $0 <process>"
    echo "This is a debug version that only supports processing with file preservation."
    exit 1
fi

COMMAND=$1
shift

check_deps "$PYTHON_CMD" ffmpeg whisper

case $COMMAND in
    process)
        process_recordings
        ;;
    *)
        echo "Debug version only supports: process"
        exit 1
        ;;
esac 