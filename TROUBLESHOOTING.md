# Audio Troubleshooting Guide

## Issue: "Others" Track Produces Repeating "you" Transcriptions

### Symptoms
- The "others" WAV file appears silent or blank
- Whisper transcribes the "others" track as continuous "you" words
- The "me" track transcribes correctly

### Root Causes

#### 1. **OBS Audio Track Configuration Issue** (Most Common)
**Problem**: The "others" track (Track 2) isn't capturing the right audio source

**Check**:
- Open OBS Studio
- Go to `Audio Mixer` panel → right-click any source → `Advanced Audio Properties`
- Verify your **microphone** is ONLY checked for **Track 1**
- Verify your **Desktop Audio/Application Audio** is ONLY checked for **Track 2**
- Make sure no other tracks are selected

**Fix**:
1. In OBS Advanced Audio Properties:
   - **Your Microphone**: Check only Track 1, uncheck all others
   - **Desktop Audio**: Check only Track 2, uncheck all others
   - **Application Audio**: Check only Track 2, uncheck all others

#### 2. **Silent Audio with Digital Noise**
**Problem**: Track 2 is mostly silent but contains low-level digital noise that Whisper interprets as speech

**Check**:
- Use the debug tools to analyze the WAV file
- Look for very low bit rates (< 10kbps) which indicate mostly silence

**Fix**:
- Check your system audio settings
- Ensure the correct playback device is selected
- Test with a different meeting platform

#### 3. **Audio Routing Problem**
**Problem**: System audio isn't being routed to the recording

**Check**:
- Verify that you can hear other participants during the meeting
- Check that your system volume isn't muted
- Ensure the meeting app has proper audio permissions

**Fix**:
- Test your system audio outside of recording
- Check macOS System Preferences → Security & Privacy → Privacy → Microphone
- Restart OBS and your meeting application

#### 4. **Whisper Model Issue**
**Problem**: The Whisper model is misinterpreting silence/noise as "you"

**Check**:
- Extract a sample from the "others" WAV file and listen to it
- Try with a different Whisper model (base, small, medium)

**Fix**:
- Change `WHISPER_MODEL=medium` to `WHISPER_MODEL=base` in `.env`
- Or try `WHISPER_MODEL=small` for faster, potentially more accurate results

### Debugging Steps

#### Step 1: Record a Test Meeting
1. Record a short test meeting (2-3 minutes)
2. Use the debug mode to preserve intermediate files:
   ```bash
   ./run_debug.sh process
   ```

#### Step 2: Analyze the Audio Files
```bash
# Analyze the MKV file structure
python scripts/debug_audio.py analyze-mkv recordings/test/test.mkv

# Analyze both WAV files
python scripts/debug_audio.py analyze-wav recordings/test/test_me.wav
python scripts/debug_audio.py analyze-wav recordings/test/test_others.wav

# Extract a sample for manual listening
python scripts/debug_audio.py extract-sample recordings/test/test_others.wav
```

#### Step 3: Listen to the Audio Sample
- Play the `*_others_sample.wav` file
- If you hear:
  - **Complete silence**: OBS configuration issue
  - **Low-level noise/static**: Digital noise issue
  - **Actual speech**: Whisper model issue

#### Step 4: Check OBS Settings
1. **Recording Format**: Must be **MKV** (not MP4)
2. **Audio Tracks**: Enable multiple audio tracks
3. **Track Assignment**: Verify correct sources are assigned to correct tracks

### Common Fixes

#### Fix 1: Reset OBS Audio Configuration
```bash
# Stop any current recording
./run.sh stop

# In OBS:
# 1. Go to File → Settings → Output
# 2. Set Recording Format to MKV
# 3. Go to Audio Mixer → Advanced Audio Properties
# 4. Reset all track assignments
# 5. Assign: Microphone → Track 1 only
# 6. Assign: Desktop Audio → Track 2 only
```

#### Fix 2: Test with Different Meeting Platform
- Try recording with a different video conferencing app
- Use a test call with a colleague
- Check if the issue is platform-specific

#### Fix 3: Change Whisper Model
Edit `.env` file:
```bash
# Try a different model
WHISPER_MODEL=base     # Faster, less prone to hallucinations
# OR
WHISPER_MODEL=small    # Good balance of speed and accuracy
```

#### Fix 4: System Audio Check
```bash
# Check system audio devices
system_profiler SPAudioDataType

# Test system audio
afplay /System/Library/Sounds/Glass.aiff
```

### Prevention

1. **Always test your setup** before important meetings
2. **Use a consistent audio setup** (same apps, same audio devices)
3. **Monitor audio levels** in OBS during recording
4. **Keep a backup recording method** for critical meetings

### Getting Help

If issues persist:

1. **Run the debug tools** and save the output
2. **Record a short test meeting** with debug mode enabled
3. **Share the analysis output** when asking for help

### Manual Recovery

If you have a corrupted recording:

1. **Check the MKV file** manually:
   ```bash
   ffplay recordings/problematic/file.mkv
   ```

2. **Extract and examine tracks** separately:
   ```bash
   ffmpeg -i file.mkv -map 0:a:0 track1.wav -map 0:a:1 track2.wav
   ```

3. **Re-transcribe manually** if needed:
   ```bash
   whisper --model medium --language en track2.wav
   ``` 