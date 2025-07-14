#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Source environment variables from .env file if it exists
if [ -f .env ]; then
    # Using a simple source command which is more robust than the previous sed/xargs combo
    set -o allexport; source .env; set +o allexport
fi

# Set defaults if not provided in .env
WHISPER_MODEL=${WHISPER_MODEL:-base}
WHISPER_LANGUAGE=${WHISPER_LANGUAGE:-en}
# Use PWD for recordings path if not set, replacing ~ with $HOME
RECORDING_PATH_RAW=${RECORDING_PATH:-.}
RECORDING_PATH="${RECORDING_PATH_RAW/\~/$HOME}"

# --- Setup Python Command ---
# Prioritize using a project-local virtual environment if it exists.
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
    echo "Using Python from virtual environment."
else
    # Fallback to the system's python3
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

function safe_delete() {
    local file_path="$1"
    local verification_message="$2"
    
    if [ -f "$file_path" ]; then
        echo "Deleting $verification_message: $file_path"
        rm "$file_path"
        if [ $? -eq 0 ]; then
            echo "Successfully deleted: $file_path"
        else
            echo "Warning: Failed to delete $file_path"
        fi
    else
        echo "File not found (may already be deleted): $file_path"
    fi
}

# --- Commands ---
function start_recording() {
    if [ -z "$1" ]; then
        echo "Usage: $0 start \"<Meeting Name>\""
        exit 1
    fi
    MEETING_NAME=$1

    if [ -f "$PENDING_FILE" ]; then
        LAST_MEETING=$(head -n 1 "$PENDING_FILE")
        echo "Error: A pending recording for '$LAST_MEETING' already exists."
        echo "Please run '$0 stop' before starting a new one."
        exit 1
    fi
    
    echo "Starting recording for: $MEETING_NAME"
    $PYTHON_CMD "$SCRIPTS_DIR/obs_controller.py" start
    
    MEETING_DATE=$(date +"%Y%m%d")
    echo "$MEETING_NAME" > "$PENDING_FILE"
    echo "$MEETING_DATE" >> "$PENDING_FILE"
    
    echo "Recording started. To stop, run: $0 stop"
}

function stop_recording() {
    if [ ! -f "$PENDING_FILE" ]; then
        echo "Error: No pending recording found. Use '$0 start \"<name>\"' first."
        exit 1
    fi
    
    echo "Stopping recording..."
    $PYTHON_CMD "$SCRIPTS_DIR/obs_controller.py" stop
    
    MEETING_NAME=$(head -n 1 "$PENDING_FILE")
    MEETING_DATE=$(tail -n 1 "$PENDING_FILE")
    
    # Give OBS a moment to finalize the file
    sleep 3 

    LATEST_RECORDING=$(find "$RECORDING_PATH" -maxdepth 1 -name "*.mkv" -print0 | xargs -0 ls -t | head -n 1)

    if [ -z "$LATEST_RECORDING" ]; then
        echo "Error: Could not find any new .mkv recordings in '$RECORDING_PATH'."
        rm "$PENDING_FILE"
        exit 1
    fi
    
    # Create queue file if it doesn't exist
    touch "$QUEUE_FILE"

    # Use semicolon as delimiter for CSV
    echo "$LATEST_RECORDING;$MEETING_NAME;$MEETING_DATE;recorded" >> "$QUEUE_FILE"
    
    rm "$PENDING_FILE"
    echo "Recording stopped and logged to queue."
    echo "To process, run: $0 process"
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

    echo "Found $UNPROCESSED_COUNT recordings to process..."
    
    # Use a temporary file for safe iteration and modification
    TEMP_QUEUE_FILE=$(mktemp)
    cp "$QUEUE_FILE" "$TEMP_QUEUE_FILE"

    # Process each 'recorded' entry
    while IFS=';' read -r raw_mkv_path meeting_name meeting_date status; do
        if [ "$status" = "recorded" ]; then
            echo "-----------------------------------------------------"
            echo "Processing: '$meeting_name' from $meeting_date"
            echo "Source file: $raw_mkv_path"
            
            # Create sanitized filename and folder name
            SANITIZED_NAME=$(echo "$meeting_name" | sed 's/[^a-zA-Z0-9]/-/g')
            FINAL_BASENAME="${meeting_date}-${SANITIZED_NAME}"
            TARGET_DIR="${RECORDINGS_DIR}/${FINAL_BASENAME}"

            mkdir -p "$TARGET_DIR"

            # Move and rename original recording if it hasn't been moved yet
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
                
                # Verify both WAV files were successfully created before deleting MKV
                if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                    echo "Audio extraction successful. Verifying file integrity..."
                    # Check if WAV files have content (not empty)
                    if [ -s "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] && [ -s "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                        echo "WAV files verified successfully."
                        safe_delete "$TARGET_DIR/${FINAL_BASENAME}.mkv" "raw recording file"
                    else
                        echo "Warning: WAV files are empty. Keeping MKV file for safety."
                    fi
                else
                    echo "Warning: Audio extraction failed. Keeping MKV file for safety."
                fi
            else
                echo "Audio tracks already extracted. Skipping ffmpeg."
                # Check if MKV file exists and WAV files are verified, then delete MKV
                if [ -f "$TARGET_DIR/${FINAL_BASENAME}.mkv" ] && [ -s "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] && [ -s "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                    echo "WAV files exist and verified. Cleaning up MKV file..."
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}.mkv" "raw recording file"
                fi
            fi

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
            
            # Verify both SRT files were successfully created before deleting WAV files
            if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                echo "Transcription successful. Verifying SRT file integrity..."
                # Check if SRT files have content (not empty)
                if [ -s "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ] && [ -s "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                    echo "SRT files verified successfully."
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_me.wav" "audio file (me)"
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_others.wav" "audio file (others)"
                else
                    echo "Warning: SRT files are empty. Keeping WAV files for safety."
                fi
            else
                echo "Warning: Transcription failed. Keeping WAV files for safety."
            fi
            
            # --- Interleaving ---
            echo "Interleaving transcripts..."
            $PYTHON_CMD "$SCRIPTS_DIR/interleave.py" \
                "$TARGET_DIR/${FINAL_BASENAME}_me.srt" \
                "$TARGET_DIR/${FINAL_BASENAME}_others.srt" > "$TARGET_DIR/${FINAL_BASENAME}_transcript.txt"
            
            # Verify final transcript file was successfully created before deleting SRT files
            if [ -f "$TARGET_DIR/${FINAL_BASENAME}_transcript.txt" ]; then
                echo "Interleaving successful. Verifying final transcript file integrity..."
                # Check if transcript file has content (not empty)
                if [ -s "$TARGET_DIR/${FINAL_BASENAME}_transcript.txt" ]; then
                    echo "Final transcript verified successfully."
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_me.srt" "transcript file (me)"
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_others.srt" "transcript file (others)"
                else
                    echo "Warning: Final transcript file is empty. Keeping SRT files for safety."
                fi
            else
                echo "Warning: Interleaving failed. Keeping SRT files for safety."
            fi

            # Update status immediately after successful processing (avoiding race condition by using temp file)
            TEMP_QUEUE_UPDATE=$(mktemp)
            ESCAPED_PATH=$(printf '%s\n' "$raw_mkv_path" | sed 's:[][\\/.^$*]:\\&:g')
            sed "s/$ESCAPED_PATH;$meeting_name;$meeting_date;recorded/$ESCAPED_PATH;$meeting_name;$meeting_date;processed/" "$QUEUE_FILE" > "$TEMP_QUEUE_UPDATE"
            mv "$TEMP_QUEUE_UPDATE" "$QUEUE_FILE"

            echo "Processing complete!"
            echo "Final transcript: $TARGET_DIR/${FINAL_BASENAME}_transcript.txt"
        fi
    done < "$TEMP_QUEUE_FILE"

    rm "$TEMP_QUEUE_FILE"
    echo "-----------------------------------------------------"
    echo "All recordings processed."
}

function show_status() {
    if [ ! -f "$QUEUE_FILE" ]; then
        echo "Processing queue is empty."
        return
    fi
    echo "--- Recording Queue Status ---"
    echo "STATUS      | DATE       | NAME"
    echo "--------------------------------------------------"
    while IFS=';' read -r raw_mkv_path meeting_name meeting_date status; do
        printf "%-11s | %-10s | %s\n" "$status" "$meeting_date" "$meeting_name"
    done < "$QUEUE_FILE"
}

function discard_recording() {
    # Case 1: A recording is currently in progress and needs to be cancelled.
    if [ -f "$PENDING_FILE" ]; then
        MEETING_NAME=$(head -n 1 "$PENDING_FILE")
        # Ask for confirmation using read.
        read -p "A recording for '$MEETING_NAME' is in progress. Stop and discard it? [y/N] " -n 1 -r
        echo # Move to a new line
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Stopping and discarding current recording..."
            $PYTHON_CMD "$SCRIPTS_DIR/obs_controller.py" stop
            sleep 3 # Give OBS a moment to finalize the file

            LATEST_RECORDING=$(find "$RECORDING_PATH" -maxdepth 1 -name "*.mkv" -print0 | xargs -0 ls -t | head -n 1)

            if [ -n "$LATEST_RECORDING" ] && [ -f "$LATEST_RECORDING" ]; then
                echo "Deleting recording file: $LATEST_RECORDING"
                rm "$LATEST_RECORDING"
            else
                echo "Warning: Could not find a new recording file to delete."
            fi

            rm "$PENDING_FILE"
            echo "Recording for '$MEETING_NAME' has been discarded."
        else
            echo "Discard cancelled. The recording is still running."
        fi
        return
    fi

    # Case 2: Select a queued recording to discard.
    if [ ! -f "$QUEUE_FILE" ] || ! grep -q ';recorded$' "$QUEUE_FILE"; then
        echo "No queued recordings to discard."
        return
    fi

    echo "Select a recording to discard:"
    # Use mapfile to read matching lines into an array
    mapfile -t options < <(grep ';recorded$' "$QUEUE_FILE")

    # Use a select loop to create a menu.
    select opt in "${options[@]}" "Quit"; do
        if [ "$opt" == "Quit" ]; then
            echo "Discard cancelled."
            break
        fi

        # Extract details from the selected line
        IFS=';' read -r raw_mkv_path meeting_name meeting_date status <<< "$opt"

        read -p "Are you sure you want to discard '$meeting_name' and delete its recording file? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Discarding '$meeting_name'..."

            # Delete the recording file if it exists
            if [ -f "$raw_mkv_path" ]; then
                echo "Deleting file: $raw_mkv_path"
                rm "$raw_mkv_path"
            else
                echo "Warning: Recording file not found at '$raw_mkv_path'."
            fi

            # Update status in queue file to 'discarded'
            ESCAPED_PATH=$(printf '%s\n' "$raw_mkv_path" | sed 's:[][\\/.^$*]:\\&:g')
            sed -i.bak "s/$ESCAPED_PATH;$meeting_name;$meeting_date;recorded/$ESCAPED_PATH;$meeting_name;$meeting_date;discarded/" "$QUEUE_FILE"
            rm "$QUEUE_FILE.bak"

            echo "'$meeting_name' has been discarded."
            break
        else
            echo "Discard cancelled."
            break
        fi
    done
}


# --- Main Logic ---
if [ -z "$1" ]; then
    echo "Usage: $0 <start|stop|process|status|discard> [args]"
    exit 1
fi

COMMAND=$1
shift

# Check dependencies
check_deps "$PYTHON_CMD" ffmpeg whisper

case $COMMAND in
    start)
        start_recording "$@"
        ;;
    stop)
        stop_recording
        ;;
    process)
        process_recordings
        ;;
    status)
        show_status
        ;;
    discard)
        discard_recording
        ;;
    *)
        echo "Unknown command: $COMMAND"
        exit 1
        ;;
esac 