#!/usr/bin/env python3
"""
MLX Whisper Transcription Script
Transcribes audio files using MLX Whisper (optimized for Apple Silicon)
and outputs SRT format subtitles.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import timedelta

try:
    import mlx_whisper
except ImportError:
    print("Error: mlx-whisper is not installed. Install it with: pip install mlx-whisper")
    sys.exit(1)

from audio_validator import validate_audio_file, AudioValidationError

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

# Default NVIDIA Parakeet model for the 'parakeet' backend (Apple Silicon via MLX).
# See issue #4: faster and more accurate than whisper-large-v3-turbo on the
# Open ASR Leaderboard; multilingual (25 European languages) in v3.
PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"


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


def _whisper_segments(audio_path: Path, model: str, language: str, verbose: bool):
    """Transcribe with MLX Whisper.

    Returns (segments, words): segment dicts {start, end, text} for the SRT, and
    word dicts {text, start, end} for word-level speaker assignment (issue #6).
    """
    model_path = MODEL_MAPPING.get(model, model)
    if verbose:
        print(f"🎯 Backend: whisper | Model: {model} ({model_path})")
        print(f"🌍 Language: {language}")

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model_path,
        language=language,
        # Optimize for transcription quality
        condition_on_previous_text=False,  # Reduces hallucinations
        no_speech_threshold=0.6,  # Filter out non-speech segments
        compression_ratio_threshold=2.4,  # Filter garbled audio
        word_timestamps=True,  # also produce word-level timings for diarization
        verbose=verbose,
    )
    segments = result.get('segments', [])
    words = [
        {"text": w.get("word", ""), "start": w.get("start"), "end": w.get("end")}
        for seg in segments
        for w in seg.get("words", [])
        if w.get("start") is not None and w.get("end") is not None
    ]
    return segments, words


def _parakeet_segments(audio_path: Path, model: str, verbose: bool):
    """Transcribe with NVIDIA Parakeet (MLX).

    Returns (segments, words). Parakeet auto-detects language and processes long
    audio in overlapping chunks. Sentence alignments map to SRT segments; the
    per-sentence tokens give word-level timings for diarization (issue #6).
    """
    try:
        from parakeet_mlx import from_pretrained
    except ImportError:
        raise ImportError(
            "parakeet-mlx is not installed. Install it with: pip install parakeet-mlx"
        )

    if verbose:
        print(f"🎯 Backend: parakeet | Model: {model}")

    pk = from_pretrained(model)
    result = pk.transcribe(str(audio_path), chunk_duration=120.0, overlap_duration=15.0)
    segments = [{"start": s.start, "end": s.end, "text": s.text} for s in result.sentences]
    words = [
        {"text": t.text, "start": t.start, "end": t.end}
        for s in result.sentences
        for t in s.tokens
    ]
    return segments, words


def transcribe(
    audio_path: str,
    output_dir: str,
    model: str = "turbo",
    language: str = "en",
    verbose: bool = True,
    backend: str = "parakeet",
) -> Path:
    """
    Transcribe an audio file to SRT using the chosen ASR backend.

    Args:
        audio_path: Path to the input audio file
        output_dir: Directory to save the output SRT file
        model: Model to use. For backend='whisper', a Whisper name (e.g. 'turbo',
            'large-v3'). For backend='parakeet', a Parakeet repo id; if a Whisper
            name is passed it falls back to PARAKEET_MODEL.
        language: Language code (whisper only; parakeet auto-detects)
        verbose: Whether to print progress information
        backend: 'whisper' (MLX Whisper) or 'parakeet' (NVIDIA Parakeet via MLX)

    Returns:
        Path to the output SRT file
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)

    # Validate audio file before transcription (fail-fast)
    try:
        validate_audio_file(audio_path)
    except AudioValidationError as e:
        if verbose:
            print(str(e), file=sys.stderr)
        raise

    output_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"📂 Input: {audio_path}")
        print("⏳ Transcribing...")

    if backend == "parakeet":
        # A Whisper-style model name (or the default 'turbo') means "use the
        # default Parakeet model" rather than a literal repo id.
        pk_model = model if "parakeet" in model else PARAKEET_MODEL
        segments, words = _parakeet_segments(audio_path, pk_model, verbose)
    elif backend == "whisper":
        segments, words = _whisper_segments(audio_path, model, language, verbose)
    else:
        raise ValueError(f"Unknown ASR backend: {backend!r} (expected 'whisper' or 'parakeet')")

    # Write SRT output
    output_filename = audio_path.stem + ".srt"
    output_path = output_dir / output_filename

    if not segments:
        if verbose:
            print("⚠️  No speech segments detected in audio")
        # Create empty SRT file
        output_path.touch()
    else:
        write_srt(segments, output_path)
        if verbose:
            print(f"✅ Transcription complete: {len(segments)} segments")

    # Write a word-level sidecar (<stem>.words.json) for word-level speaker
    # assignment in diarize.py (issue #6). Best-effort: absence just means the
    # diarizer falls back to segment-level labeling.
    if words:
        words_path = output_dir / (audio_path.stem + ".words.json")
        words_path.write_text(json.dumps(words), encoding="utf-8")
        if verbose:
            print(f"💾 Word timings: {words_path} ({len(words)} words)")

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
        "--backend",
        default=os.environ.get("ASR_BACKEND", "parakeet"),
        choices=["whisper", "parakeet"],
        help="ASR backend (default: $ASR_BACKEND or 'parakeet')"
    )
    parser.add_argument(
        "-m", "--model",
        default="turbo",
        help="Model to use (whisper name like 'turbo'; ignored for parakeet "
             "unless a parakeet repo id is given)"
    )
    parser.add_argument(
        "-l", "--language",
        default="en",
        help="Language code (default: en; whisper only — parakeet auto-detects)"
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
            verbose=not args.quiet,
            backend=args.backend,
        )
        print(output_path)  # Print path for shell script to capture
    except AudioValidationError:
        # Error already printed with troubleshooting steps
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Transcription failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

