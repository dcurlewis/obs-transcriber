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
from datetime import timedelta
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


def _words_to_labeled_cues(words: list, diarization, speaker_map: dict) -> list:
    """Assign a speaker to each word, then group consecutive same-speaker words.

    `words` is a list of {text, start, end}. Returns cue dicts
    {start, end, label, text} where `label` is a human label or None (unknown).
    Word-level grouping splits a transcript at speaker changes that whole-segment
    labeling would miss, and uses tight word timings (issue #6).
    """
    cues: list = []
    cur = None
    for w in words:
        try:
            start = float(w["start"])
            end = float(w["end"])
        except (TypeError, KeyError, ValueError):
            continue
        text = w.get("text", "")
        # Guard against zero-duration tokens so overlap is well-defined.
        raw = _dominant_speaker(start, max(end, start + 1e-3), diarization)
        label = _human_label(raw, speaker_map) if raw else None
        if cur is not None and cur["label"] == label:
            cur["end"] = end
            cur["text"] += text
        else:
            if cur is not None:
                cues.append(cur)
            cur = {"start": start, "end": end, "label": label, "text": text}
    if cur is not None:
        cues.append(cur)
    for c in cues:
        c["text"] = c["text"].strip()
    return [c for c in cues if c["text"]]


def _kept_intervals(srt_path: Path) -> list | None:
    """Time spans (start, end) of the cues present in ``srt_path``.

    Used to gate the word sidecar: upstream hallucination filtering removes whole
    cues from the SRT, so words whose timing falls in a removed span must also be
    dropped — otherwise word-level diarization would rebuild them from the
    unfiltered sidecar and reintroduce the hallucination (issue #6 review).
    Returns None if the SRT can't be read (then no gating is applied).
    """
    try:
        subs = list(srt.parse(Path(srt_path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None
    return [(s.start.total_seconds(), s.end.total_seconds()) for s in subs]


def _filter_words_to_intervals(words: list, intervals: list) -> list:
    """Keep only words that overlap one of the (sorted) kept intervals."""
    intervals = sorted(intervals)
    n = len(intervals)
    kept = []
    j = 0
    for w in sorted(words, key=lambda x: float(x.get("start", 0.0))):
        try:
            ws, we = float(w["start"]), float(w["end"])
        except (TypeError, KeyError, ValueError):
            continue
        while j < n and intervals[j][1] <= ws:
            j += 1
        if j < n and intervals[j][0] < max(we, ws + 1e-3):
            kept.append(w)
    return kept


def _write_word_level_srt(words_path: Path, srt_path: Path, diarization,
                          output_path: Path, verbose: bool) -> Path | None:
    """Build a speaker-labeled SRT from a word-timings sidecar.

    Words are gated to the cue spans of ``srt_path`` (the possibly
    hallucination-filtered transcript) so filtered content is not reintroduced.

    Returns the output path, or None if the sidecar is empty/unusable so the
    caller can fall back to segment-level labeling.
    """
    import json

    try:
        words = json.loads(Path(words_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not words:
        return None

    # Drop words that fall outside the (filtered) SRT's surviving cues.
    intervals = _kept_intervals(srt_path)
    if intervals is not None:
        words = _filter_words_to_intervals(words, intervals)
    if not words:
        return None

    speaker_map: dict[str, str] = {}
    cues = _words_to_labeled_cues(words, diarization, speaker_map)
    if not cues:
        return None

    subtitles = []
    for i, c in enumerate(cues, start=1):
        content = f"[{c['label']}] {c['text']}" if c["label"] else c["text"]
        subtitles.append(srt.Subtitle(
            index=i,
            start=timedelta(seconds=c["start"]),
            end=timedelta(seconds=c["end"]),
            content=content,
        ))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subtitles))

    if verbose:
        labeled = sum(1 for c in cues if c["label"])
        print(f"💬 Word-level: {len(cues)} cues, {labeled} labeled, "
              f"{len(speaker_map)} speaker(s)")
        print(f"💾 Output: {output_path}")
    return output_path


# Diarization model. Defined once so both the production pipeline and the
# evaluation harness stay in sync. Requires pyannote.audio 4.x. The model is
# gated on HuggingFace — accept its conditions at
# https://huggingface.co/pyannote/speaker-diarization-community-1
# Overridable via DIARIZATION_MODEL env var (handy for A/B-ing models in eval).
DIARIZATION_MODEL = os.environ.get(
    "DIARIZATION_MODEL", "pyannote/speaker-diarization-community-1"
)


def run_diarization(
    audio_path: str,
    hf_token: str,
    device: str | None = None,
    verbose: bool = True,
):
    """
    Run the pyannote diarization pipeline and return the raw result.

    Separated from label application so callers (e.g. the evaluation harness)
    can score pyannote's native output directly without re-running the model.

    Args:
        audio_path: Path to the audio WAV file (16 kHz mono is ideal)
        hf_token: HuggingFace access token for pyannote model download
        device: Torch device ('mps' or 'cpu'). Auto-detected if None.
        verbose: Whether to print progress information

    Returns:
        A pyannote.core.Annotation with the diarization result.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Auto-select device: prefer MPS (Apple Silicon GPU), fall back to CPU
    if device is None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch_device = torch.device(device)

    if verbose:
        print(f"🎙️  Device: {device}")
        print(f"⏳ Loading pyannote speaker diarization pipeline ({DIARIZATION_MODEL})...")

    pipeline = Pipeline.from_pretrained(
        DIARIZATION_MODEL,
        token=hf_token,  # pyannote.audio 4.x renamed use_auth_token -> token
    )
    pipeline.to(torch_device)

    if verbose:
        print(f"⏳ Running diarization on: {audio_path.name}")

    output = pipeline(str(audio_path))
    # pyannote.audio 4.x returns a result object whose Annotation is exposed as
    # `.speaker_diarization`; 3.x returned the Annotation directly. Support both.
    diarization_result = getattr(output, "speaker_diarization", output)

    detected_speakers = sorted(
        {speaker for _, _, speaker in diarization_result.itertracks(yield_label=True)}
    )
    if verbose:
        print(f"✅ Detected {len(detected_speakers)} speaker(s): {', '.join(detected_speakers)}")

    return diarization_result


def diarize(
    audio_path: str,
    srt_path: str,
    output_path: str,
    hf_token: str = None,
    device: str | None = None,
    verbose: bool = True,
    diarization=None,
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
        diarization: Optional precomputed diarization Annotation (from
            run_diarization). If provided, the model is not re-run.

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

    if diarization is None:
        diarization_result = run_diarization(audio_path, hf_token, device, verbose)
    else:
        diarization_result = diarization

    # Prefer word-level speaker assignment when a word-timings sidecar exists
    # (written by transcribe.py). It splits at within-segment speaker changes and
    # uses tight word timings, which segment-level max-overlap cannot (issue #6).
    words_path = srt_path.with_suffix(".words.json")
    if words_path.exists():
        result = _write_word_level_srt(words_path, srt_path, diarization_result,
                                       output_path, verbose)
        if result is not None:
            return result
        if verbose:
            print("ℹ️  Word sidecar unusable; falling back to segment-level labeling.")

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
  2. Accept the model conditions at https://huggingface.co/pyannote/speaker-diarization-community-1
  3. Generate a read token at https://huggingface.co/settings/tokens
  4. Add HF_TOKEN=<your_token> to your .env file

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
            "   Accept the model conditions at:\n"
            "     https://huggingface.co/pyannote/speaker-diarization-community-1",
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
