"""Scoring core for the evaluation harness.

Pure, dependency-light functions for:
  - Word Error Rate (WER) via jiwer, with meeting-appropriate text normalization.
  - Diarization Error Rate (DER) via pyannote.metrics.
  - Converters between the formats our pipeline emits (SRT, optionally with
    ``[Speaker N]`` prefixes) and the formats the scorers need (plain text,
    pyannote ``Annotation``), plus a minimal RTTM parser for ground-truth refs.

Heavy imports (jiwer, pyannote) are done lazily inside the functions that need
them so this module is cheap to import and unit-testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing pyannote at module load
    from pyannote.core import Annotation


# Matches a leading "[Speaker 1] " style label produced by diarize.py.
_SPEAKER_PREFIX = re.compile(r"^\[(Speaker \d+|Others|SPEAKER_\d+)\]\s*(.*)$", re.DOTALL)


# --------------------------------------------------------------------------- #
# WER
# --------------------------------------------------------------------------- #

@dataclass
class WERResult:
    """Word-error-rate result with error breakdown."""

    wer: float
    substitutions: int
    deletions: int
    insertions: int
    hits: int
    reference_words: int

    def as_dict(self) -> dict:
        return {
            "wer": self.wer,
            "substitutions": self.substitutions,
            "deletions": self.deletions,
            "insertions": self.insertions,
            "hits": self.hits,
            "reference_words": self.reference_words,
        }


def _wer_transform():
    """A jiwer transform: lowercase, strip punctuation, collapse whitespace.

    Mirrors the normalization used by ASR leaderboards closely enough for
    relative comparison between models (the absolute number is not directly
    comparable to a leaderboard unless their exact normalizer is used).
    """
    import jiwer

    return jiwer.Compose(
        [
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
            jiwer.ReduceToListOfListOfWords(),
        ]
    )


def compute_wer(reference: str, hypothesis: str) -> WERResult:
    """Compute WER between a reference and hypothesis transcript.

    Both inputs are normalized (lowercased, depunctuated, whitespace-collapsed)
    before scoring. An empty reference with an empty hypothesis scores 0.0; an
    empty reference with any hypothesis scores 1.0 (all insertions).
    """
    import jiwer

    transform = _wer_transform()
    ref_words = transform(reference)
    # jiwer needs at least one reference word to define WER.
    n_ref = sum(len(s) for s in ref_words)
    if n_ref == 0:
        hyp_words = transform(hypothesis)
        n_hyp = sum(len(s) for s in hyp_words)
        return WERResult(
            wer=0.0 if n_hyp == 0 else 1.0,
            substitutions=0,
            deletions=0,
            insertions=n_hyp,
            hits=0,
            reference_words=0,
        )

    out = jiwer.process_words(
        reference,
        hypothesis,
        reference_transform=transform,
        hypothesis_transform=transform,
    )
    return WERResult(
        wer=out.wer,
        substitutions=out.substitutions,
        deletions=out.deletions,
        insertions=out.insertions,
        hits=out.hits,
        reference_words=n_ref,
    )


# --------------------------------------------------------------------------- #
# SRT helpers
# --------------------------------------------------------------------------- #

@dataclass
class Cue:
    """A single transcript cue with timing, optional speaker label, and text."""

    start: float  # seconds
    end: float  # seconds
    text: str
    speaker: str | None = None


def parse_srt(srt_path: str | Path) -> list[Cue]:
    """Parse an SRT file into cues, splitting off any ``[Speaker N]`` prefix.

    Returns an empty list for an empty/whitespace-only file.
    """
    import srt as srt_lib

    raw = Path(srt_path).read_text(encoding="utf-8")
    if not raw.strip():
        return []

    cues: list[Cue] = []
    for sub in srt_lib.parse(raw):
        content = sub.content.strip()
        speaker = None
        m = _SPEAKER_PREFIX.match(content)
        if m:
            speaker = m.group(1)
            content = m.group(2).strip()
        cues.append(
            Cue(
                start=sub.start.total_seconds(),
                end=sub.end.total_seconds(),
                text=content,
                speaker=speaker,
            )
        )
    return cues


def srt_to_text(srt_path: str | Path) -> str:
    """Concatenate an SRT file's cues into one transcript string for WER.

    Any ``[Speaker N]`` prefixes are stripped (handled by parse_srt).
    """
    return " ".join(c.text for c in parse_srt(srt_path) if c.text)


def cues_to_annotation(cues: list[Cue], uri: str = "audio") -> "Annotation":
    """Build a pyannote Annotation from cues, using their speaker labels.

    Cues without a speaker label are assigned a single shared "UNKNOWN" label.
    """
    from pyannote.core import Annotation, Segment

    annotation = Annotation(uri=uri)
    for i, cue in enumerate(cues):
        if cue.end <= cue.start:
            continue
        label = cue.speaker if cue.speaker else "UNKNOWN"
        annotation[Segment(cue.start, cue.end), i] = label
    return annotation


def srt_to_annotation(srt_path: str | Path, uri: str = "audio") -> "Annotation":
    """Parse a (diarized) SRT file directly into a pyannote Annotation."""
    return cues_to_annotation(parse_srt(srt_path), uri=uri)


# --------------------------------------------------------------------------- #
# RTTM (ground-truth diarization references)
# --------------------------------------------------------------------------- #

def load_rttm(rttm_path: str | Path, uri: str | None = None) -> "Annotation":
    """Parse an NIST RTTM file into a single pyannote Annotation.

    RTTM ``SPEAKER`` lines look like::

        SPEAKER <file> <chan> <start> <dur> <NA> <NA> <speaker> <NA> <NA>

    Lines for other file ids are skipped when ``uri`` is given; otherwise all
    SPEAKER lines are merged into one annotation.
    """
    from pyannote.core import Annotation, Segment

    annotation = Annotation(uri=uri or Path(rttm_path).stem)
    idx = 0
    for line in Path(rttm_path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts or parts[0] != "SPEAKER":
            continue
        file_id, _chan, start, dur = parts[1], parts[2], parts[3], parts[4]
        speaker = parts[7]
        if uri is not None and file_id != uri:
            continue
        start_f = float(start)
        dur_f = float(dur)
        if dur_f <= 0:
            continue
        annotation[Segment(start_f, start_f + dur_f), idx] = speaker
        idx += 1
    return annotation


def load_uem(uem_path: str | Path, uri: str | None = None):
    """Parse a UEM file into a pyannote Timeline (the scored region).

    UEM lines: ``<file> <chan> <start> <end>``. Returns None-safe Timeline.
    """
    from pyannote.core import Segment, Timeline

    segments = []
    for line in Path(uem_path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        file_id, _chan, start, end = parts[0], parts[1], parts[2], parts[3]
        if uri is not None and file_id != uri:
            continue
        segments.append(Segment(float(start), float(end)))
    return Timeline(segments, uri=uri or Path(uem_path).stem)


# --------------------------------------------------------------------------- #
# DER
# --------------------------------------------------------------------------- #

@dataclass
class DERResult:
    """Diarization-error-rate result with its standard components (seconds)."""

    der: float
    missed_detection: float
    false_alarm: float
    confusion: float
    total: float
    collar: float = 0.0
    skip_overlap: bool = False

    def as_dict(self) -> dict:
        return {
            "der": self.der,
            "missed_detection": self.missed_detection,
            "false_alarm": self.false_alarm,
            "confusion": self.confusion,
            "total": self.total,
            "collar": self.collar,
            "skip_overlap": self.skip_overlap,
        }


def compute_der(
    reference: "Annotation",
    hypothesis: "Annotation",
    collar: float = 0.0,
    skip_overlap: bool = False,
    uem=None,
) -> DERResult:
    """Compute DER between reference and hypothesis pyannote Annotations.

    Defaults (collar=0.0, skip_overlap=False) match the "fair" no-forgiveness
    setting pyannote uses for its published community-1/3.1 benchmark numbers,
    so results here are directly comparable to those. Pass collar=0.25 to
    reproduce the older, more lenient NIST-style scoring.
    """
    from pyannote.metrics.diarization import DiarizationErrorRate

    metric = DiarizationErrorRate(collar=collar, skip_overlap=skip_overlap)
    components = metric(reference, hypothesis, uem=uem, detailed=True)
    total = components["total"]
    der = components["diarization error rate"]
    return DERResult(
        der=der,
        missed_detection=components["missed detection"],
        false_alarm=components["false alarm"],
        confusion=components["confusion"],
        total=total,
        collar=collar,
        skip_overlap=skip_overlap,
    )
