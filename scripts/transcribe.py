#!/usr/bin/env python3
"""
MLX Whisper Transcription Script
Transcribes audio files using MLX Whisper (optimized for Apple Silicon)
and outputs SRT format subtitles.
"""

import argparse
import sys
from pathlib import Path
from datetime import timedelta

try:
    import mlx_whisper
except ImportError:
    print("Error: mlx-whisper is not installed. Install it with: pip install mlx-whisper")
    sys.exit(1)

# Model mapping - maps simple names to HuggingFace repos
# MLX-community provides optimized versions for Apple Silicon
MODEL_MAPPING = {
    "tiny": "mlx-community/whisper-tiny",
    "tiny.en": "mlx-community/whisper-tiny.en",
    "base": "mlx-community/whisper-base",
    "base.en": "mlx-community/whisper-base.en",
    "small": "mlx-community/whisper-small",
    "small.en": "mlx-community/whisper-small.en",
    "medium": "mlx-community/whisper-medium",
    "medium.en": "mlx-community/whisper-medium.en",
    "large": "mlx-community/whisper-large-v3",
    "large-v2": "mlx-community/whisper-large-v2",
    "large-v3": "mlx-community/whisper-large-v3",
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    # Distilled models for even faster performance
    "distil-large-v3": "mlx-community/distil-whisper-large-v3",
    "distil-medium.en": "mlx-community/distil-whisper-medium.en",
    "distil-small.en": "mlx-community/distil-whisper-small.en",
}


def format_timestamp_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)"""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(segments: list, output_path: Path) -> None:
    """Write segments to SRT file format"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, start=1):
            start_time = format_timestamp_srt(segment['start'])
            end_time = format_timestamp_srt(segment['end'])
            text = segment['text'].strip()
            
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n")
            f.write("\n")


def transcribe(
    audio_path: str,
    output_dir: str,
    model: str = "turbo",
    language: str = "en",
    verbose: bool = True
) -> Path:
    """
    Transcribe an audio file using MLX Whisper.
    
    Args:
        audio_path: Path to the input audio file
        output_dir: Directory to save the output SRT file
        model: Whisper model to use (e.g., 'turbo', 'large-v3', 'base')
        language: Language code (e.g., 'en', 'es', 'fr')
        verbose: Whether to print progress information
    
    Returns:
        Path to the output SRT file
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine the model path
    model_path = MODEL_MAPPING.get(model, model)
    
    if verbose:
        print(f"🎯 Model: {model} ({model_path})")
        print(f"🌍 Language: {language}")
        print(f"📂 Input: {audio_path}")
    
    # Transcribe using MLX Whisper
    if verbose:
        print("⏳ Transcribing...")
    
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model_path,
        language=language,
        # Optimize for transcription quality
        condition_on_previous_text=False,  # Reduces hallucinations
        no_speech_threshold=0.6,  # Filter out non-speech segments
        compression_ratio_threshold=2.4,  # Filter garbled audio
        word_timestamps=False,  # We only need segment-level timestamps for SRT
        verbose=verbose,
    )
    
    # Write SRT output
    output_filename = audio_path.stem + ".srt"
    output_path = output_dir / output_filename
    
    segments = result.get('segments', [])
    
    if not segments:
        if verbose:
            print("⚠️  No speech segments detected in audio")
        # Create empty SRT file
        output_path.touch()
    else:
        write_srt(segments, output_path)
        if verbose:
            print(f"✅ Transcription complete: {len(segments)} segments")
    
    if verbose:
        print(f"💾 Output: {output_path}")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio files using MLX Whisper (optimized for Apple Silicon)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available models:
  tiny, tiny.en       - Fastest, lowest accuracy
  base, base.en       - Fast, good for quick transcriptions  
  small, small.en     - Balanced speed/accuracy
  medium, medium.en   - Good accuracy, moderate speed
  large-v3            - Best accuracy, slower
  turbo               - Large-v3-turbo: fast with good accuracy (recommended)
  distil-large-v3     - Distilled: very fast with good accuracy

Examples:
  %(prog)s audio.wav -o ./output
  %(prog)s audio.wav -o ./output -m turbo -l en
  %(prog)s meeting.mp3 -o ./transcripts -m distil-large-v3
        """
    )
    
    parser.add_argument(
        "audio_file",
        help="Path to the audio file to transcribe"
    )
    parser.add_argument(
        "-o", "--output-dir",
        required=True,
        help="Directory to save the output SRT file"
    )
    parser.add_argument(
        "-m", "--model",
        default="turbo",
        help="Whisper model to use (default: turbo)"
    )
    parser.add_argument(
        "-l", "--language",
        default="en",
        help="Language code (default: en)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress output"
    )
    
    args = parser.parse_args()
    
    try:
        output_path = transcribe(
            audio_path=args.audio_file,
            output_dir=args.output_dir,
            model=args.model,
            language=args.language,
            verbose=not args.quiet
        )
        print(output_path)  # Print path for shell script to capture
    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Transcription failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

