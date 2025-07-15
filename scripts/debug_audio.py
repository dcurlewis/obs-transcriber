#!/usr/bin/env python3
"""
Audio Diagnostics Script for OBS Transcriber
Helps troubleshoot corrupt WAV files and audio track issues
"""

import sys
import os
import subprocess
import json
from pathlib import Path

def get_audio_info(file_path):
    """Get detailed audio information using ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', '-show_format', str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return None

def analyze_mkv_tracks(mkv_file):
    """Analyze MKV file to show audio track information"""
    print(f"\n🔍 Analyzing MKV file: {mkv_file}")
    print("=" * 60)
    
    info = get_audio_info(mkv_file)
    if not info:
        return False
    
    audio_streams = [s for s in info['streams'] if s['codec_type'] == 'audio']
    print(f"Found {len(audio_streams)} audio streams:")
    
    for i, stream in enumerate(audio_streams):
        print(f"\n  Track {i}: {stream.get('codec_name', 'unknown')}")
        print(f"    Sample Rate: {stream.get('sample_rate', 'unknown')} Hz")
        print(f"    Channels: {stream.get('channels', 'unknown')}")
        print(f"    Duration: {stream.get('duration', 'unknown')} seconds")
        print(f"    Bit Rate: {stream.get('bit_rate', 'unknown')} bps")
        
        # Check if stream has any audio data
        if 'tags' in stream and 'title' in stream['tags']:
            print(f"    Title: {stream['tags']['title']}")
    
    return True

def analyze_wav_file(wav_file):
    """Analyze WAV file for potential issues"""
    print(f"\n🔍 Analyzing WAV file: {wav_file}")
    print("=" * 60)
    
    if not os.path.exists(wav_file):
        print("❌ File does not exist")
        return False
    
    # Check file size
    size = os.path.getsize(wav_file)
    print(f"File size: {size:,} bytes ({size/1024/1024:.1f} MB)")
    
    if size < 1000:  # Very small file
        print("⚠️  WARNING: File is very small, likely empty or corrupted")
    
    # Get audio info
    info = get_audio_info(wav_file)
    if not info:
        return False
    
    format_info = info.get('format', {})
    print(f"Duration: {format_info.get('duration', 'unknown')} seconds")
    print(f"Bit Rate: {format_info.get('bit_rate', 'unknown')} bps")
    
    # Check for audio streams
    audio_streams = [s for s in info['streams'] if s['codec_type'] == 'audio']
    if not audio_streams:
        print("❌ No audio streams found")
        return False
    
    stream = audio_streams[0]
    print(f"Sample Rate: {stream.get('sample_rate', 'unknown')} Hz")
    print(f"Channels: {stream.get('channels', 'unknown')}")
    
    # Check for very low bit rate (might indicate silence)
    bit_rate = stream.get('bit_rate')
    if bit_rate and int(bit_rate) < 10000:  # Less than 10kbps
        print("⚠️  WARNING: Very low bit rate, file might be mostly silent")
    
    return True

def extract_audio_sample(wav_file, output_file, start_time=0, duration=10):
    """Extract a short sample from WAV file for manual inspection"""
    print(f"\n🎵 Extracting {duration}s sample from {wav_file}")
    
    cmd = [
        'ffmpeg', '-i', str(wav_file),
        '-ss', str(start_time),
        '-t', str(duration),
        '-y', output_file
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ Sample extracted to: {output_file}")
        print("   You can listen to this file to check for audio quality")
        return True
    else:
        print(f"❌ Failed to extract sample: {result.stderr}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_audio.py <command> [file]")
        print("\nCommands:")
        print("  analyze-mkv <file.mkv>    - Analyze MKV file audio tracks")
        print("  analyze-wav <file.wav>    - Analyze WAV file for issues")
        print("  extract-sample <file.wav> - Extract 10s sample for manual inspection")
        print("  check-latest              - Check the latest recording")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "analyze-mkv":
        if len(sys.argv) < 3:
            print("Please provide MKV file path")
            sys.exit(1)
        analyze_mkv_tracks(sys.argv[2])
    
    elif command == "analyze-wav":
        if len(sys.argv) < 3:
            print("Please provide WAV file path")
            sys.exit(1)
        analyze_wav_file(sys.argv[2])
    
    elif command == "extract-sample":
        if len(sys.argv) < 3:
            print("Please provide WAV file path")
            sys.exit(1)
        wav_file = sys.argv[2]
        base_name = os.path.splitext(os.path.basename(wav_file))[0]
        output_file = f"{base_name}_sample.wav"
        extract_audio_sample(wav_file, output_file)
    
    elif command == "check-latest":
        print("To check the latest recording, you'll need to run this during processing")
        print("Modify run.sh to skip deletion temporarily, then run:")
        print("  python debug_audio.py analyze-mkv recordings/latest/file.mkv")
        print("  python debug_audio.py analyze-wav recordings/latest/file_me.wav")
        print("  python debug_audio.py analyze-wav recordings/latest/file_others.wav")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main() 