#!/usr/bin/env python3
"""
Speaker diarization script using pyannote.audio.

Identifies individual speakers in the 'others' audio track and applies
speaker labels to the corresponding SRT transcript. Outputs an SRT file
with each subtitle prefixed by its speaker label (e.g. "[Speaker 1] Hello").

This format is consumed directly by interleave.py which expects the
[Speaker N] prefix pattern.
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import srt
except ImportError:
    print("Error: srt is not installed. Install it with: pip install srt", file=sys.stderr)
    sys.exit(1)

try:
    import torch
    from pyannote.audio import Pipeline
except ImportError:
    print(
        "Error: pyannote.audio and torch are required.\n"
        "Install with: pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


def _dominant_speaker(segment_start: float, segment_end: float, diarization) -> str | None:
    """Return the speaker with the most overlap in the given time range, or None."""
    best_speaker = None
    best_overlap = 0.0

    for turn, _, speaker in diarization.itertracks(yield_label=True):
        overlap = max(0.0, min(turn.end, segment_end) - max(turn.start, segment_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker

    return best_speaker


def _human_label(raw_speaker: str, speaker_map: dict) -> str:
    """
    Convert a pyannote speaker ID (e.g. 'SPEAKER_00') to a human-readable label
    (e.g. 'Speaker 1'), assigning numbers in order of first appearance.
    """
    if raw_speaker not in speaker_map:
        speaker_map[raw_speaker] = f"Speaker {len(speaker_map) + 1}"
    return speaker_map[raw_speaker]


def diarize(
    audio_path: str,
    srt_path: str,
    output_path: str,
    hf_token: str,
    device: str | None = None,
    verbose: bool = True,
) -> Path:
    """
    Run speaker diarization on audio and apply speaker labels to an SRT transcript.

    For each SRT segment, finds the pyannote speaker with the greatest temporal
    overlap and prepends a [Speaker N] label to the subtitle content.

    Args:
        audio_path: Path to the audio WAV file (16 kHz mono is ideal)
        srt_path: Path to the existing SRT transcript to label
        output_path: Destination path for the labeled SRT file
        hf_token: HuggingFace access token for pyannote model download
        device: Torch device ('mps' or 'cpu'). Auto-detected if None.
        verbose: Whether to print progress information

    Returns:
        Path to the labeled output SRT file
    """
    audio_path = Path(audio_path)
    srt_path = Path(srt_path)
    output_path = Path(output_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    # Auto-select device: prefer MPS (Apple Silicon GPU), fall back to CPU
    if device is None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch_device = torch.device(device)

    if verbose:
        print(f"🎙️  Device: {device}")
        print("⏳ Loading pyannote speaker diarization pipeline...")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )
    pipeline.to(torch_device)

    if verbose:
        print(f"⏳ Running diarization on: {audio_path.name}")

    diarization_result = pipeline(str(audio_path))

    detected_speakers = sorted(
        {speaker for _, _, speaker in diarization_result.itertracks(yield_label=True)}
    )
    if verbose:
        print(f"✅ Detected {len(detected_speakers)} speaker(s): {', '.join(detected_speakers)}")

    with open(srt_path, "r", encoding="utf-8") as f:
        subtitles = list(srt.parse(f.read()))

    if not subtitles:
        if verbose:
            print("⚠️  SRT file is empty; nothing to label.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return output_path

    speaker_map: dict[str, str] = {}
    labeled_count = 0

    for sub in subtitles:
        seg_start = sub.start.total_seconds()
        seg_end = sub.end.total_seconds()
        raw_speaker = _dominant_speaker(seg_start, seg_end, diarization_result)
        if raw_speaker:
            label = _human_label(raw_speaker, speaker_map)
            sub.content = f"[{label}] {sub.content.strip()}"
            labeled_count += 1

    if verbose:
        print(f"💬 Labeled {labeled_count}/{len(subtitles)} segments with speaker information")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subtitles))

    if verbose:
        print(f"💾 Output: {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Apply speaker diarization labels to an SRT transcript (pyannote.audio)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
One-time setup:
  1. Create a HuggingFace account at https://huggingface.co
  2. Accept the model license at https://huggingface.co/pyannote/speaker-diarization-3.1
  3. Accept the model license at https://huggingface.co/pyannote/segmentation-3.0
  4. Generate a read token at https://huggingface.co/settings/tokens
  5. Add HF_TOKEN=<your_token> to your .env file

Examples:
  %(prog)s others.wav others.srt -o others_labeled.srt
  %(prog)s others.wav others.srt -o others_labeled.srt --device cpu
        """,
    )

    parser.add_argument("audio_file", help="Path to the audio WAV file")
    parser.add_argument("srt_file", help="Path to the SRT transcript file to label")
    parser.add_argument("-o", "--output", required=True, help="Output path for the labeled SRT file")
    parser.add_argument(
        "--token",
        default=None,
        help="HuggingFace API token (falls back to HF_TOKEN environment variable)",
    )
    parser.add_argument(
        "--device",
        default=None,
        choices=["mps", "cpu"],
        help="Torch device to use (default: auto-detect MPS, fall back to CPU)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")

    args = parser.parse_args()

    hf_token = args.token or os.environ.get("HF_TOKEN")
    if not hf_token:
        print(
            "❌ Error: HuggingFace token required for pyannote model access.\n"
            "   Set HF_TOKEN=<token> in your .env file, or pass --token <token>.\n"
            "   Get a token at: https://huggingface.co/settings/tokens\n"
            "   Accept model licenses at:\n"
            "     https://huggingface.co/pyannote/speaker-diarization-3.1\n"
            "     https://huggingface.co/pyannote/segmentation-3.0",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        diarize(
            audio_path=args.audio_file,
            srt_path=args.srt_file,
            output_path=args.output,
            hf_token=hf_token,
            device=args.device,
            verbose=not args.quiet,
        )
    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Diarization failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
