#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Source environment variables from .env file if it exists
# You can set KEEP_RAW_RECORDING=true, FORCE_CPU_TRANSCRIPTION=true, WHISPER_IGNORE_SSL=true, etc.
if [ -f .env ]; then
    # Using a simple source command which is more robust than the previous sed/xargs combo
    set -o allexport; source .env; set +o allexport
fi

# Set defaults if not provided in .env
# Default to 'turbo' model (large-v3-turbo) for best speed/accuracy balance on Apple Silicon
WHISPER_MODEL=${WHISPER_MODEL:-turbo}
WHISPER_LANGUAGE=${WHISPER_LANGUAGE:-en}
# Use PWD for recordings path if not set, replacing ~ with $HOME
RECORDING_PATH_RAW=${RECORDING_PATH:-.}
RECORDING_PATH="${RECORDING_PATH_RAW/\~/$HOME}"
# Option to retain raw MKV files for troubleshooting (default: false)
KEEP_RAW_RECORDING=${KEEP_RAW_RECORDING:-false}

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

SCRIPTS_DIR="scripts"

# --- Check Dependencies ---
# Verify all required external tools are available before proceeding
$PYTHON_CMD "$SCRIPTS_DIR/dependencies.py"
if [ $? -ne 0 ]; then
    echo "Error: Dependency check failed. Please install missing dependencies."
    exit 1
fi

PENDING_FILE=".pending_meeting"
QUEUE_FILE="processing_queue.csv"
# Use TRANSCRIPTION_OUTPUT_DIR from .env, default to "recordings" if not set
TRANSCRIPTION_OUTPUT_DIR_RAW=${TRANSCRIPTION_OUTPUT_DIR:-recordings}
# Replace ~ with $HOME in the path
RECORDINGS_DIR="${TRANSCRIPTION_OUTPUT_DIR_RAW/\~/$HOME}"

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
        echo "Enter meeting name:"
        read -r MEETING_NAME
        
        # Validate that user entered something
        if [ -z "$MEETING_NAME" ]; then
            echo "Error: Meeting name cannot be empty."
            exit 1
        fi
    else
        MEETING_NAME=$1
    fi

    if [ -f "$PENDING_FILE" ]; then
        LAST_MEETING=$(head -n 1 "$PENDING_FILE")
        echo "Error: A pending recording for '$LAST_MEETING' already exists."
        echo "Please run '$0 stop' before starting a new one."
        exit 1
    fi
    
    echo "Starting recording for: $MEETING_NAME"
    $PYTHON_CMD "$SCRIPTS_DIR/obs_controller.py" start
    
    MEETING_DATE=$(date +"%Y%m%d_%H%M")
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
    
    MEETING_NAME=$(sed -n '1p' "$PENDING_FILE")
    MEETING_DATE=$(sed -n '2p' "$PENDING_FILE")
    ATTENDEES=$(sed -n '3p' "$PENDING_FILE")
    
    # Give OBS a moment to finalize the file
    sleep 4 

    LATEST_RECORDING=$(find "$RECORDING_PATH" -maxdepth 1 -name "*.mkv" -print0 | xargs -0 ls -t | head -n 1)

    if [ -z "$LATEST_RECORDING" ]; then
        echo "Error: Could not find any new .mkv recordings in '$RECORDING_PATH'."
        rm "$PENDING_FILE"
        exit 1
    fi
    
    # Add to queue using queue_cli.py for safe CSV handling
    $PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" add "$LATEST_RECORDING" "$MEETING_NAME" "$MEETING_DATE" "recorded" "$ATTENDEES"

    if [ $? -ne 0 ]; then
        echo "Error: Failed to add recording to queue"
        rm "$PENDING_FILE"
        exit 1
    fi
    
    rm "$PENDING_FILE"
    echo "Recording stopped and logged to queue."
    echo "To process, run: $0 process"
}

function process_recordings() {
    if [ ! -f "$QUEUE_FILE" ]; then
        echo "Processing queue is empty. Nothing to do."
        return
    fi

    UNPROCESSED_COUNT=$($PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" list recorded 2>/dev/null | $PYTHON_CMD -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [ "$UNPROCESSED_COUNT" -eq 0 ]; then
        echo "No recordings to process."
        return
    fi

    echo "Found $UNPROCESSED_COUNT recordings to process..."
    echo "📁 Transcriptions will be saved to: $RECORDINGS_DIR"
    
    # Ensure the recordings directory exists
    if [ ! -d "$RECORDINGS_DIR" ]; then
        echo "Creating transcription output directory: $RECORDINGS_DIR"
        mkdir -p "$RECORDINGS_DIR"
    fi
    
    # Get list of recorded entries using queue_cli.py
    # Use a temporary file for safe iteration (ffmpeg can't consume stdin this way)
    TEMP_QUEUE_FILE=$(mktemp)
    $PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" list recorded | $PYTHON_CMD -c "
import sys, json
entries = json.load(sys.stdin)
for entry in entries:
    # Output in pipe-delimited format for shell parsing
    print('|'.join([entry.get('path', ''), entry.get('name', ''), entry.get('date', ''), entry.get('status', ''), entry.get('attendees', '')]))
" > "$TEMP_QUEUE_FILE"

    # Track which recordings were successfully processed
    PROCESSED_RECORDINGS=()

    # Process each 'recorded' entry
    # IMPORTANT: read from a dedicated FD so commands inside the loop
    # (notably ffmpeg) can't accidentally consume stdin and corrupt subsequent reads.
    exec 3< "$TEMP_QUEUE_FILE"
    while IFS='|' read -r raw_mkv_path meeting_name meeting_date status attendees <&3; do
        if [ "$status" = "recorded" ] && [ -n "$raw_mkv_path" ]; then
            echo "-----------------------------------------------------"
            echo "Processing: '$meeting_name' from $meeting_date"
            echo "Source file: $raw_mkv_path"
            
            # Start timing for performance feedback
            PROCESSING_START=$(date +%s)
            
            # Create sanitized filename and folder name
            SANITIZED_NAME=$(echo "$meeting_name" | sed 's/[^a-zA-Z0-9]/-/g')
            FINAL_BASENAME="${meeting_date}-${SANITIZED_NAME}"
            TARGET_DIR="${RECORDINGS_DIR}/${FINAL_BASENAME}"

            mkdir -p "$TARGET_DIR"

            # Move and rename original recording if it hasn't been moved yet
            if [ -f "$raw_mkv_path" ]; then
                echo "Moving source file to target directory..."
                mv "$raw_mkv_path" "$TARGET_DIR/${FINAL_BASENAME}.mkv"
            elif [ -f "$TARGET_DIR/${FINAL_BASENAME}.mkv" ]; then
                echo "Source file already moved. Skipping move."
            elif [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] || [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ]; then
                # Recovery mode: MKV is gone but audio/transcript files exist
                echo "⚠️  MKV file not found, but audio/transcript files exist. Continuing from recovery..."
                echo "   (This can happen if processing was interrupted after audio extraction)"
            else
                echo "❌ Error: Source file not found and target file doesn't exist!"
                echo "   Expected source: $raw_mkv_path"
                echo "   Expected target: $TARGET_DIR/${FINAL_BASENAME}.mkv"
                echo "   Skipping this recording."
                continue
            fi

            # --- Audio Extraction ---
            if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] || [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                echo "⏳ [1/3] Extracting audio tracks with ffmpeg..."
                AUDIO_START=$(date +%s)
                # Enhanced ffmpeg command with quality options optimized for speech recognition
                # - pcm_s16le: High-quality 16-bit PCM codec
                # - ar 16000: 16kHz sample rate (optimal for speech recognition)
                # - ac 1: Convert to mono (often better for speech)
                # - dynaudnorm: Dynamic audio normalizer to ensure consistent levels
                # - highpass/lowpass: Filter for speech frequencies (80Hz-8kHz)
                # -nostdin prevents ffmpeg from consuming stdin (which would corrupt the queue reads)
                # -y avoids interactive overwrite prompts (another stdin consumer)
                ffmpeg -nostdin -y -i "$TARGET_DIR/${FINAL_BASENAME}.mkv" \
                    -map 0:a:0 -af "dynaudnorm=f=150:g=15:p=0.75,highpass=f=80,lowpass=f=8000" -acodec pcm_s16le -ar 16000 -ac 1 "$TARGET_DIR/${FINAL_BASENAME}_me.wav" \
                    -map 0:a:1 -af "dynaudnorm=f=150:g=15:p=0.75,highpass=f=80,lowpass=f=8000" -acodec pcm_s16le -ar 16000 -ac 1 "$TARGET_DIR/${FINAL_BASENAME}_others.wav" \
                    -loglevel error
                
                # Verify both WAV files were successfully created before deleting MKV
                if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                    AUDIO_END=$(date +%s)
                    AUDIO_TIME=$((AUDIO_END - AUDIO_START))
                    echo "✅ Audio extraction completed in ${AUDIO_TIME}s. Verifying file integrity..."
                    # Check if WAV files have content (not empty)
                    if [ -s "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ] && [ -s "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                        echo "WAV files verified successfully."
                        if [ "${KEEP_RAW_RECORDING}" = "true" ]; then
                            echo "🗂️  Keeping raw MKV file for troubleshooting (KEEP_RAW_RECORDING=true)"
                        else
                            safe_delete "$TARGET_DIR/${FINAL_BASENAME}.mkv" "raw recording file"
                        fi
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
                    if [ "${KEEP_RAW_RECORDING}" = "true" ]; then
                        echo "🗂️  Raw MKV file exists and keeping for troubleshooting (KEEP_RAW_RECORDING=true)"
                    else
                        echo "WAV files exist and verified. Cleaning up MKV file..."
                        safe_delete "$TARGET_DIR/${FINAL_BASENAME}.mkv" "raw recording file"
                    fi
                fi
            fi

            # --- Parallel Transcription with MLX Whisper ---
            echo "⏳ [2/3] Transcribing audio with MLX Whisper (Model: $WHISPER_MODEL)..."
            echo "🍎 Using Apple Silicon optimized transcription via MLX"
            TRANSCRIPTION_START=$(date +%s)
            
            # Start both transcriptions in parallel for ~50% speed improvement
            TRANSCRIPTION_PIDS=()
            
            if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ]; then
                echo "Starting transcription: My audio..."
                $PYTHON_CMD "$SCRIPTS_DIR/transcribe.py" \
                    "$TARGET_DIR/${FINAL_BASENAME}_me.wav" \
                    -o "$TARGET_DIR" \
                    -m "$WHISPER_MODEL" \
                    -l "$WHISPER_LANGUAGE" &
                TRANSCRIPTION_PIDS+=($!)
            else
                echo "My audio already transcribed. Skipping."
            fi

            if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                echo "Starting transcription: Others audio..."
                $PYTHON_CMD "$SCRIPTS_DIR/transcribe.py" \
                    "$TARGET_DIR/${FINAL_BASENAME}_others.wav" \
                    -o "$TARGET_DIR" \
                    -m "$WHISPER_MODEL" \
                    -l "$WHISPER_LANGUAGE" &
                TRANSCRIPTION_PIDS+=($!)
            else
                echo "Others audio already transcribed. Skipping."
            fi
            
            # Wait for all transcription processes to complete with error checking
            if [ ${#TRANSCRIPTION_PIDS[@]} -gt 0 ]; then
                echo "Waiting for ${#TRANSCRIPTION_PIDS[@]} parallel transcription(s) to complete..."
                FAILED_PROCESSES=()
                for pid in "${TRANSCRIPTION_PIDS[@]}"; do
                    if ! wait "$pid"; then
                        FAILED_PROCESSES+=($pid)
                    fi
                done
                
                if [ ${#FAILED_PROCESSES[@]} -gt 0 ]; then
                    echo "⚠️  ${#FAILED_PROCESSES[@]} transcription(s) failed, attempting recovery with smaller model..."
                    
                    # Retry failed transcriptions with a smaller/faster model
                    echo "🔄 Retrying with 'base' model..."
                    RETRY_START=$(date +%s)
                    
                    if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.wav" ]; then
                        $PYTHON_CMD "$SCRIPTS_DIR/transcribe.py" \
                            "$TARGET_DIR/${FINAL_BASENAME}_me.wav" \
                            -o "$TARGET_DIR" \
                            -m "base" \
                            -l "$WHISPER_LANGUAGE"
                    fi
                    if [ ! -f "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.wav" ]; then
                        $PYTHON_CMD "$SCRIPTS_DIR/transcribe.py" \
                            "$TARGET_DIR/${FINAL_BASENAME}_others.wav" \
                            -o "$TARGET_DIR" \
                            -m "base" \
                            -l "$WHISPER_LANGUAGE"
                    fi
                    
                    RETRY_END=$(date +%s)
                    TRANSCRIPTION_TIME=$((RETRY_END - RETRY_START))
                    
                    # Check if recovery was successful
                    if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                        echo "✅ Recovery successful! Transcriptions completed in ${TRANSCRIPTION_TIME}s"
                    else
                        echo "❌ Transcription failed even after recovery attempts"
                        echo "💡 Troubleshooting suggestions:"
                        echo "   - Check audio file integrity: ffmpeg -i \"$TARGET_DIR/${FINAL_BASENAME}_me.wav\" -f null -"
                        echo "   - Try manual transcription: python scripts/transcribe.py \"$TARGET_DIR/${FINAL_BASENAME}_me.wav\" -o \"$TARGET_DIR\" -m base"
                        echo "   - Check available disk space and memory"
                        echo "   - Ensure mlx-whisper is installed: pip install mlx-whisper"
                    fi
                else
                    TRANSCRIPTION_END=$(date +%s)
                    TRANSCRIPTION_TIME=$((TRANSCRIPTION_END - TRANSCRIPTION_START))
                    echo "✅ All transcriptions completed in ${TRANSCRIPTION_TIME}s!"
                fi
            fi
            
            # Verify both SRT files were successfully created before deleting WAV files
            if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                echo "Transcription successful. Verifying SRT file integrity..."
                # Check if SRT files have content (not empty)
                if [ -s "$TARGET_DIR/${FINAL_BASENAME}_me.srt" ] && [ -s "$TARGET_DIR/${FINAL_BASENAME}_others.srt" ]; then
                    echo "SRT files verified successfully."
                    
                    
                    # Filter hallucinations from transcription files
                    echo "🧹 Filtering hallucinations from transcripts..."
                    $PYTHON_CMD "$SCRIPTS_DIR/filter_hallucinations.py" "$TARGET_DIR/${FINAL_BASENAME}_me.srt" "$TARGET_DIR/${FINAL_BASENAME}_me_clean.srt"
                    $PYTHON_CMD "$SCRIPTS_DIR/filter_hallucinations.py" "$TARGET_DIR/${FINAL_BASENAME}_others.srt" "$TARGET_DIR/${FINAL_BASENAME}_others_clean.srt"
                    
                    # Replace original SRT files with filtered versions if filtering succeeded
                    if [ -f "$TARGET_DIR/${FINAL_BASENAME}_me_clean.srt" ] && [ -f "$TARGET_DIR/${FINAL_BASENAME}_others_clean.srt" ]; then
                        mv "$TARGET_DIR/${FINAL_BASENAME}_me_clean.srt" "$TARGET_DIR/${FINAL_BASENAME}_me.srt"
                        mv "$TARGET_DIR/${FINAL_BASENAME}_others_clean.srt" "$TARGET_DIR/${FINAL_BASENAME}_others.srt"
                        echo "✅ Hallucination filtering completed"
                    else
                        echo "⚠️  Hallucination filtering failed, keeping original SRT files"
                    fi
                    
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_me.wav" "audio file (me)"
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_others.wav" "audio file (others)"
                else
                    echo "Warning: SRT files are empty. Keeping WAV files for safety."
                fi
            else
                echo "Warning: Transcription failed. Keeping WAV files for safety."
            fi
            
            # --- Interleaving ---
            echo "⏳ [3/3] Interleaving transcripts..."
            INTERLEAVE_START=$(date +%s)
            # Save transcript directly to the configured directory
            FINAL_TRANSCRIPT_PATH="$RECORDINGS_DIR/${FINAL_BASENAME}_transcript.txt"
            $PYTHON_CMD "$SCRIPTS_DIR/interleave.py" \
                "$TARGET_DIR/${FINAL_BASENAME}_me.srt" \
                "$TARGET_DIR/${FINAL_BASENAME}_others.srt" \
                --meeting-name "$meeting_name" \
                --meeting-date "$meeting_date" \
                --attendees "$attendees" > "$FINAL_TRANSCRIPT_PATH"
            
            # Verify final transcript file was successfully created before deleting SRT files
            if [ -f "$FINAL_TRANSCRIPT_PATH" ]; then
                echo "Interleaving successful. Verifying final transcript file integrity..."
                # Check if transcript file has content (not empty)
                if [ -s "$FINAL_TRANSCRIPT_PATH" ]; then
                    echo "Final transcript verified successfully."
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_me.srt" "transcript file (me)"
                    safe_delete "$TARGET_DIR/${FINAL_BASENAME}_others.srt" "transcript file (others)"
                    
                    # Clean up the temporary directory if it's empty (no raw recording kept)
                    if [ "${KEEP_RAW_RECORDING}" != "true" ]; then
                        # Check if directory is empty
                        if [ -z "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
                            echo "Removing empty temporary directory: $TARGET_DIR"
                            rmdir "$TARGET_DIR"
                        fi
                    fi
                else
                    echo "Warning: Final transcript file is empty. Keeping SRT files for safety."
                fi
            else
                echo "Warning: Interleaving failed. Keeping SRT files for safety."
            fi

            # Mark this recording as successfully processed (defer queue update until after loop)
            PROCESSED_RECORDINGS+=("$raw_mkv_path")

            # Final processing summary with timing
            PROCESSING_END=$(date +%s)
            TOTAL_TIME=$((PROCESSING_END - PROCESSING_START))
            
            echo "🎉 Processing complete!"
            echo "📄 Final transcript: $FINAL_TRANSCRIPT_PATH"
            echo "⏱️  Total processing time: ${TOTAL_TIME}s"
            
            # Show breakdown if we have all timings
            if [ -n "${AUDIO_TIME:-}" ] && [ -n "${TRANSCRIPTION_TIME:-}" ]; then
                INTERLEAVE_TIME=$((PROCESSING_END - INTERLEAVE_START))
                echo "   ├─ Audio extraction: ${AUDIO_TIME}s"
                echo "   ├─ Transcription: ${TRANSCRIPTION_TIME}s"
                echo "   └─ Interleaving: ${INTERLEAVE_TIME}s"
            fi
        fi
    done
    exec 3<&-

    rm "$TEMP_QUEUE_FILE"
    
    # Now update the queue for all successfully processed recordings using queue_cli.py
    if [ ${#PROCESSED_RECORDINGS[@]} -gt 0 ]; then
        for path in "${PROCESSED_RECORDINGS[@]}"; do
            # Update status using queue_cli.py
            $PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" update "$path" "processed"

            if [ $? -ne 0 ]; then
                echo "Warning: Failed to update queue status for: $path"
            fi
        done
    fi
    
    echo "-----------------------------------------------------"
    echo "All recordings processed."
}

function show_status() {
    if [ ! -f "$QUEUE_FILE" ]; then
        echo "📭 Processing queue is empty."
        return
    fi
    
    echo "📊 Recording Queue Status"
    echo "═══════════════════════════════════════════════════════════════════════════════"
    printf "%-12s │ %-10s │ %-20s │ %-10s │ %s\n" "STATUS" "DATE" "NAME" "SIZE" "LOCATION"
    echo "─────────────┼────────────┼──────────────────────┼────────────┼─────────────────"
    
    TOTAL_FILES=0
    TOTAL_SIZE=0
    
    # Get queue entries as JSON from queue_cli.py, then parse with Python
    $PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" list | $PYTHON_CMD -c "
import sys, json
entries = json.load(sys.stdin)
for entry in entries:
    # Output in pipe-delimited format for shell parsing
    print('|'.join([entry.get('path', ''), entry.get('name', ''), entry.get('date', ''), entry.get('status', ''), entry.get('attendees', '')]))
" | while IFS='|' read -r raw_mkv_path meeting_name meeting_date status attendees; do
        # Skip empty entries
        if [ -z "$status" ] || [ -z "$meeting_date" ] || [ -z "$meeting_name" ] || [ -z "$raw_mkv_path" ]; then
            continue
        fi
        
        TOTAL_FILES=$((TOTAL_FILES + 1))
        
        # Determine file location and size based on status
        if [ "$status" = "recorded" ]; then
            if [ -f "$raw_mkv_path" ]; then
                FILE_SIZE=$(stat -f%z "$raw_mkv_path" 2>/dev/null || echo "0")
                TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE))
                SIZE_MB=$((FILE_SIZE / 1024 / 1024))
                SIZE_DISPLAY="${SIZE_MB}MB"
                LOCATION="$(dirname "$raw_mkv_path")"
            else
                SIZE_DISPLAY="Missing"
                LOCATION="Not found"
            fi
        elif [ "$status" = "processed" ]; then
            # Look for processed transcript file
            SANITIZED_NAME=$(echo "$meeting_name" | sed 's/[^a-zA-Z0-9]/-/g')
            FINAL_BASENAME="${meeting_date}-${SANITIZED_NAME}"
            TRANSCRIPT_FILE="${RECORDINGS_DIR}/${FINAL_BASENAME}_transcript.txt"
            if [ -f "$TRANSCRIPT_FILE" ]; then
                # Get size of transcript file
                FILE_SIZE=$(stat -f%z "$TRANSCRIPT_FILE" 2>/dev/null || echo "0")
                TOTAL_SIZE=$((TOTAL_SIZE + FILE_SIZE))
                SIZE_MB=$((FILE_SIZE / 1024 / 1024))
                if [ "$SIZE_MB" -eq 0 ]; then
                    # Show size in KB for small files
                    SIZE_KB=$((FILE_SIZE / 1024))
                    SIZE_DISPLAY="${SIZE_KB}KB"
                else
                    SIZE_DISPLAY="${SIZE_MB}MB"
                fi
                LOCATION="$RECORDINGS_DIR"
            else
                SIZE_DISPLAY="Unknown"
                LOCATION="Processed"
            fi
        else
            SIZE_DISPLAY="N/A"
            LOCATION="$(dirname "$raw_mkv_path")"
        fi
        
        # Truncate long names for display and handle special characters
        DISPLAY_NAME="$meeting_name"
        # Remove any embedded newlines or control characters
        DISPLAY_NAME=$(echo "$DISPLAY_NAME" | tr -d '\n\r' | tr -c '[:print:]' '?')
        if [ ${#DISPLAY_NAME} -gt 20 ]; then
            DISPLAY_NAME="${DISPLAY_NAME:0:17}..."
        fi
        
        # Add status emoji
        case "$status" in
            "recorded") STATUS_ICON="⏳ $status" ;;
            "processed") STATUS_ICON="✅ $status" ;;
            "discarded") STATUS_ICON="🗑️  $status" ;;
            *) STATUS_ICON="❓ $status" ;;
        esac
        
        printf "%-12s │ %-10s │ %-20s │ %-10s │ %s\n" "$STATUS_ICON" "$meeting_date" "$DISPLAY_NAME" "$SIZE_DISPLAY" "$(basename "$LOCATION")"
    done
    
    echo "─────────────┴────────────┴──────────────────────┴────────────┴─────────────────"
    
    # Summary statistics using queue_cli.py
    TOTAL_SIZE_MB=$((TOTAL_SIZE / 1024 / 1024))
    RECORDED_COUNT=$($PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" list recorded | $PYTHON_CMD -c "import sys, json; print(len(json.load(sys.stdin)))")
    PROCESSED_COUNT=$($PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" list processed | $PYTHON_CMD -c "import sys, json; print(len(json.load(sys.stdin)))")

    # Ensure counts are valid integers
    RECORDED_COUNT=${RECORDED_COUNT:-0}
    PROCESSED_COUNT=${PROCESSED_COUNT:-0}
    
    echo "📈 Summary: $TOTAL_FILES total recordings │ $RECORDED_COUNT pending │ $PROCESSED_COUNT completed │ ${TOTAL_SIZE_MB}MB total"
    
    if [ "$RECORDED_COUNT" -gt 0 ]; then
        echo "💡 Run './run.sh process' to transcribe pending recordings"
    fi
}

function abort_recording() {
    # Abort an active recording without adding it to the processing queue
    if [ ! -f "$PENDING_FILE" ]; then
        echo "Error: No active recording found."
        echo "Use '$0 start \"<name>\"' to begin a recording."
        exit 1
    fi
    
    MEETING_NAME=$(head -n 1 "$PENDING_FILE")
    echo "Aborting recording for: $MEETING_NAME"
    
    # Stop the recording
    $PYTHON_CMD "$SCRIPTS_DIR/obs_controller.py" stop
    
    # Give OBS a moment to finalize the file
    sleep 3
    
    # Find and delete the most recent recording
    LATEST_RECORDING=$(find "$RECORDING_PATH" -maxdepth 1 -name "*.mkv" -print0 | xargs -0 ls -t | head -n 1)
    
    if [ -n "$LATEST_RECORDING" ] && [ -f "$LATEST_RECORDING" ]; then
        echo "Deleting recording file: $LATEST_RECORDING"
        rm "$LATEST_RECORDING"
        echo "Recording file deleted successfully."
    else
        echo "Warning: Could not find recording file to delete."
    fi
    
    # Clean up the pending file
    rm "$PENDING_FILE"
    echo "Recording for '$MEETING_NAME' has been aborted."
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
    # Check if there are any recorded entries using queue_cli.py
    RECORDED_COUNT=$($PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" list recorded | $PYTHON_CMD -c "import sys, json; print(len(json.load(sys.stdin)))")
    if [ "$RECORDED_COUNT" -eq 0 ]; then
        echo "No queued recordings to discard."
        return
    fi

    echo "Select a recording to discard:"
    # Create array of options using queue_cli.py (portable for zsh and bash)
    options=()
    while IFS= read -r line; do
        options+=("$line")
    done < <($PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" list recorded | $PYTHON_CMD -c "
import sys, json
entries = json.load(sys.stdin)
for entry in entries:
    # Output in format: path|name|date|status for shell parsing
    print('|'.join([entry.get('path', ''), entry.get('name', ''), entry.get('date', ''), entry.get('status', '')]))
")

    # Use a select loop to create a menu.
    select opt in "${options[@]}" "Quit"; do
        if [ "$opt" == "Quit" ]; then
            echo "Discard cancelled."
            break
        fi

        # Extract details from the selected line (pipe-delimited)
        IFS='|' read -r raw_mkv_path meeting_name meeting_date status <<< "$opt"

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

            # Update status in queue using queue_cli.py
            $PYTHON_CMD "$SCRIPTS_DIR/queue_cli.py" discard "$raw_mkv_path"

            if [ $? -eq 0 ]; then
                echo "'$meeting_name' has been discarded."
            else
                echo "Error: Failed to update queue status."
            fi
            break
        else
            echo "Discard cancelled."
            break
        fi
    done
}


# --- Web UI Command ---
function start_web_ui() {
    echo "🚀 Starting Meeting Transcriber Web UI..."
    echo "📍 Access at: http://localhost:5000"
    echo "⌨️  Press Ctrl+C to stop"
    echo ""
    
    # Start the Flask server
    $PYTHON_CMD -m web.app
}

# --- Main Logic ---
if [ -z "$1" ]; then
    echo "Usage: $0 <start|stop|abort|process|status|discard|web> [args]"
    echo ""
    echo "Commands:"
    echo "  start <name>  - Start recording with the given meeting name"
    echo "  stop          - Stop recording and add to processing queue"
    echo "  abort         - Cancel active recording without saving"
    echo "  process       - Process all queued recordings"
    echo "  status        - Show recording queue status"
    echo "  discard       - Discard recordings (with confirmation)"
    echo "  web           - Start the web UI (http://localhost:5000)"
    echo ""
    echo "Environment Variables:"
    echo "  WHISPER_MODEL=turbo        Whisper model to use (default: turbo)"
    echo "                             Options: tiny, base, small, medium, large-v3, turbo, distil-large-v3"
    echo "  WHISPER_LANGUAGE=en        Language code for transcription (default: en)"
    echo "  KEEP_RAW_RECORDING=true    Retain raw MKV files for troubleshooting (default: false)"
    echo "  TRANSCRIPTION_OUTPUT_DIR=path    Set transcription output directory (default: recordings)"
    echo "  WEB_PORT=5000              Web UI port (default: 5000)"
    echo "  WEB_HOST=127.0.0.1         Web UI host (default: 127.0.0.1)"
    exit 1
fi

COMMAND=$1
shift

# Check dependencies (whisper CLI no longer needed - using mlx-whisper via Python)
check_deps "$PYTHON_CMD" ffmpeg

case $COMMAND in
    start)
        start_recording "$@"
        ;;
    stop)
        stop_recording
        ;;
    abort)
        abort_recording
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
    web)
        start_web_ui
        ;;
    *)
        echo "Unknown command: $COMMAND"
        exit 1
        ;;
esac 