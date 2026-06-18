"""Unit tests for word-level speaker assignment in diarize.py (issue #6).

Pure logic — uses a synthetic pyannote Annotation, no audio or models.
"""

import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).parent.parent
for _p in (str(_project_root), str(_project_root / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import diarize  # scripts/diarize.py
from pyannote.core import Annotation, Segment


def _annotation(turns):
    """turns: list of (start, end, speaker)."""
    ann = Annotation()
    for i, (s, e, spk) in enumerate(turns):
        ann[Segment(s, e), i] = spk
    return ann


def _words(*specs):
    """specs: (text, start, end) tuples."""
    return [{"text": t, "start": s, "end": e} for (t, s, e) in specs]


def test_groups_consecutive_same_speaker_words():
    ann = _annotation([(0.0, 10.0, "SPEAKER_00")])
    words = _words((" hello", 0.0, 0.5), (" world", 0.6, 1.0))
    cues = diarize._words_to_labeled_cues(words, ann, {})
    assert len(cues) == 1
    assert cues[0]["label"] == "Speaker 1"
    assert cues[0]["text"] == "hello world"
    assert cues[0]["start"] == 0.0 and cues[0]["end"] == 1.0


def test_splits_on_within_segment_speaker_change():
    # Two speakers back-to-back — segment-level labeling would pick only one.
    ann = _annotation([(0.0, 1.0, "SPEAKER_00"), (1.0, 2.0, "SPEAKER_01")])
    words = _words((" a", 0.1, 0.4), (" b", 0.5, 0.9), (" c", 1.1, 1.4), (" d", 1.5, 1.9))
    cues = diarize._words_to_labeled_cues(words, ann, {})
    assert len(cues) == 2
    assert cues[0]["label"] == "Speaker 1" and cues[0]["text"] == "a b"
    assert cues[1]["label"] == "Speaker 2" and cues[1]["text"] == "c d"


def test_speaker_numbering_by_first_appearance():
    ann = _annotation([(0.0, 1.0, "SPEAKER_05"), (1.0, 2.0, "SPEAKER_02")])
    words = _words((" x", 0.1, 0.5), (" y", 1.1, 1.5))
    cues = diarize._words_to_labeled_cues(words, ann, {})
    assert cues[0]["label"] == "Speaker 1"  # SPEAKER_05 appears first
    assert cues[1]["label"] == "Speaker 2"


def test_unlabeled_words_have_no_speaker():
    # Word falls outside any diarized turn -> label None (no prefix downstream).
    ann = _annotation([(5.0, 6.0, "SPEAKER_00")])
    words = _words((" orphan", 0.0, 0.5))
    cues = diarize._words_to_labeled_cues(words, ann, {})
    assert len(cues) == 1
    assert cues[0]["label"] is None


def _write_srt(path, cues):
    """cues: list of (start, end, text)."""
    import srt as srt_lib
    from datetime import timedelta
    subs = [
        srt_lib.Subtitle(index=i, start=timedelta(seconds=s), end=timedelta(seconds=e), content=t)
        for i, (s, e, t) in enumerate(cues, start=1)
    ]
    path.write_text(srt_lib.compose(subs), encoding="utf-8")


def test_word_level_srt_written(tmp_path):
    import json
    ann = _annotation([(0.0, 1.0, "SPEAKER_00"), (1.0, 2.0, "SPEAKER_01")])
    words_path = tmp_path / "x.words.json"
    words_path.write_text(json.dumps(_words((" a", 0.1, 0.4), (" b", 1.1, 1.4))), encoding="utf-8")
    srt_path = tmp_path / "x.srt"
    _write_srt(srt_path, [(0.0, 2.0, "a b")])  # cue covers both words
    out = tmp_path / "x_labeled.srt"
    result = diarize._write_word_level_srt(words_path, srt_path, ann, out, verbose=False)
    assert result == out
    content = out.read_text(encoding="utf-8")
    assert "[Speaker 1] a" in content
    assert "[Speaker 2] b" in content


def test_empty_sidecar_returns_none(tmp_path):
    import json
    words_path = tmp_path / "e.words.json"
    words_path.write_text(json.dumps([]), encoding="utf-8")
    srt_path = tmp_path / "e.srt"
    _write_srt(srt_path, [(0.0, 1.0, "x")])
    out = tmp_path / "e_labeled.srt"
    assert diarize._write_word_level_srt(words_path, srt_path, _annotation([]), out, verbose=False) is None


def test_filtered_hallucination_not_reintroduced(tmp_path):
    """Reviewer's case: a cue removed by hallucination filtering must not come
    back via the unfiltered word sidecar (issue #6 review)."""
    import json
    ann = _annotation([(0.0, 5.0, "SPEAKER_00")])
    # Sidecar still has the hallucination words at [0.0,0.8] plus real content.
    words_path = tmp_path / "h.words.json"
    words_path.write_text(json.dumps(_words(
        (" thank", 0.0, 0.4), (" you", 0.4, 0.8),
        (" actual", 1.0, 1.4), (" content", 1.5, 1.9),
    )), encoding="utf-8")
    # Cleaned SRT: the "thank you" cue was removed, only the real cue survives.
    srt_path = tmp_path / "h.srt"
    _write_srt(srt_path, [(1.0, 1.9, "actual content")])
    out = tmp_path / "h_labeled.srt"
    diarize._write_word_level_srt(words_path, srt_path, ann, out, verbose=False)
    content = out.read_text(encoding="utf-8").lower()
    assert "thank you" not in content
    assert "actual content" in content
