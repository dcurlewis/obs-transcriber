#!/usr/bin/env python3
"""
Speaker Diarization for "Others" audio track
Identifies different speakers in the audio and updates SRT files with speaker labels
"""

import sys
from pathlib import Path
import torch
import srt
from pyannote.audio import Pipeline
from datetime import timedelta

def diarize_audio(audio_file, srt_file, output_file):
    """
    Apply speaker diarization to an audio file and update its SRT file with speaker labels
    """
    print(f"🎙️ Diarizing speakers in: {audio_file}")
    
    # Load the diarization pipeline
    # Note: Users will need to get their own HF token for production use
    try:
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization@2.1",
                                           use_auth_token=True)
    except Exception as e:
        print(f"❌ Error loading diarization model: {e}")
        print("💡 You may need to create a Hugging Face account and get an access token")
        print("   Visit https://huggingface.co/pyannote/speaker-diarization and accept terms")
        return False
    
    # Run diarization
    try:
        # Set device to GPU if available
        device = "cuda" if torch.cuda.is_available() else "cpu"
        pipeline.to(device)
        
        print(f"🔍 Running diarization on {device}...")
        diarization = pipeline(audio_file)
        
        # Extract speaker segments with timestamps
        speaker_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append({
                'start': turn.start,
                'end': turn.end,
                'speaker': speaker
            })
        
        print(f"✅ Found {len(set(s['speaker'] for s in speaker_segments))} unique speakers")
    except Exception as e:
        print(f"❌ Diarization failed: {e}")
        return False
    
    # Read the SRT file
    try:
        with open(srt_file, 'r', encoding='utf-8') as f:
            subtitles = list(srt.parse(f.read()))
    except Exception as e:
        print(f"❌ Error reading {srt_file}: {e}")
        return False
    
    # Assign speakers to each subtitle segment based on overlap
    for subtitle in subtitles:
        # Find overlapping speaker segments
        subtitle_start_secs = subtitle.start.total_seconds()
        subtitle_end_secs = subtitle.end.total_seconds()
        
        best_overlap = 0
        best_speaker = None
        
        for segment in speaker_segments:
            # Calculate overlap duration
            overlap_start = max(subtitle_start_secs, segment['start'])
            overlap_end = min(subtitle_end_secs, segment['end'])
            overlap_duration = max(0, overlap_end - overlap_start)
            
            if overlap_duration > best_overlap:
                best_overlap = overlap_duration
                best_speaker = segment['speaker']
        
        # Add speaker label to subtitle content
        if best_speaker:
            # Format speaker number as "Speaker 1", "Speaker 2", etc.
            speaker_num = best_speaker.split("_")[1]
            speaker_label = f"Speaker {speaker_num}"
            subtitle.content = f"[{speaker_label}] {subtitle.content}"
    
    # Write the updated SRT file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(srt.compose(subtitles))
        print(f"💾 Saved diarized subtitles to: {output_file}")
        return True
    except Exception as e:
        print(f"❌ Error writing {output_file}: {e}")
        return False

def main():
    if len(sys.argv) != 4:
        print("Usage: python speaker_diarization.py <audio_file.wav> <input.srt> <output.srt>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    srt_file = sys.argv[2]
    output_file = sys.argv[3]
    
    if not Path(audio_file).exists() or not Path(srt_file).exists():
        print(f"❌ Input file not found")
        sys.exit(1)
    
    print(f"🎙️ Adding speaker diarization to transcript")
    
    if diarize_audio(audio_file, srt_file, output_file):
        print("✅ Diarization complete!")
    else:
        print("❌ Diarization failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()