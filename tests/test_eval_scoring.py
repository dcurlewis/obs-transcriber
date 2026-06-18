"""Unit tests for the evaluation scoring core (evaluation/scoring.py).

These use only synthetic, in-memory data — no audio downloads, models, or
network — so they run as part of the default fast suite.
"""

import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from evaluation import scoring


# --------------------------------------------------------------------------- #
# WER
# --------------------------------------------------------------------------- #

class TestWER:
    def test_perfect_match_is_zero(self):
        r = scoring.compute_wer("the quick brown fox", "the quick brown fox")
        assert r.wer == 0.0
        assert r.substitutions == r.deletions == r.insertions == 0
        assert r.hits == 4

    def test_normalization_ignores_case_and_punctuation(self):
        r = scoring.compute_wer("The Quick, Brown Fox.", "the quick brown fox")
        assert r.wer == 0.0

    def test_one_substitution(self):
        r = scoring.compute_wer("the cat sat", "the cat sit")
        assert r.substitutions == 1
        assert r.wer == pytest.approx(1 / 3)
        assert r.reference_words == 3

    def test_deletion_and_insertion(self):
        # reference has 3 words, hypothesis drops one and adds one elsewhere
        r = scoring.compute_wer("alpha beta gamma", "alpha gamma delta")
        assert r.reference_words == 3
        assert r.wer > 0

    def test_empty_reference_empty_hyp(self):
        r = scoring.compute_wer("", "")
        assert r.wer == 0.0

    def test_empty_reference_nonempty_hyp(self):
        r = scoring.compute_wer("", "hello world")
        assert r.wer == 1.0
        assert r.insertions == 2


# --------------------------------------------------------------------------- #
# SRT parsing
# --------------------------------------------------------------------------- #

_PLAIN_SRT = """1
00:00:00,000 --> 00:00:02,000
Hello there.

2
00:00:03,000 --> 00:00:05,000
General Kenobi.
"""

_DIARIZED_SRT = """1
00:00:00,000 --> 00:00:02,000
[Speaker 1] Hello there.

2
00:00:03,000 --> 00:00:05,000
[Speaker 2] General Kenobi.
"""


class TestSRT:
    def test_parse_plain_srt(self, tmp_path):
        p = tmp_path / "a.srt"
        p.write_text(_PLAIN_SRT, encoding="utf-8")
        cues = scoring.parse_srt(p)
        assert len(cues) == 2
        assert cues[0].start == 0.0 and cues[0].end == 2.0
        assert cues[0].text == "Hello there."
        assert cues[0].speaker is None

    def test_parse_diarized_srt_extracts_speaker(self, tmp_path):
        p = tmp_path / "b.srt"
        p.write_text(_DIARIZED_SRT, encoding="utf-8")
        cues = scoring.parse_srt(p)
        assert cues[0].speaker == "Speaker 1"
        assert cues[0].text == "Hello there."
        assert cues[1].speaker == "Speaker 2"

    def test_empty_srt_returns_no_cues(self, tmp_path):
        p = tmp_path / "empty.srt"
        p.write_text("", encoding="utf-8")
        assert scoring.parse_srt(p) == []

    def test_srt_to_text_strips_speaker_prefix(self, tmp_path):
        p = tmp_path / "c.srt"
        p.write_text(_DIARIZED_SRT, encoding="utf-8")
        assert scoring.srt_to_text(p) == "Hello there. General Kenobi."


# --------------------------------------------------------------------------- #
# RTTM + DER
# --------------------------------------------------------------------------- #

def _rttm(uri: str, turns) -> str:
    return "\n".join(
        f"SPEAKER {uri} 1 {start:.3f} {dur:.3f} <NA> <NA> {spk} <NA> <NA>"
        for (start, dur, spk) in turns
    )


class TestDER:
    def test_load_rttm(self, tmp_path):
        p = tmp_path / "m.rttm"
        p.write_text(_rttm("m", [(0.0, 5.0, "A"), (5.0, 5.0, "B")]), encoding="utf-8")
        ann = scoring.load_rttm(p, uri="m")
        assert set(ann.labels()) == {"A", "B"}
        assert ann.get_timeline().duration() == pytest.approx(10.0)

    def test_perfect_diarization_is_zero_der(self, tmp_path):
        ref_p = tmp_path / "ref.rttm"
        ref_p.write_text(_rttm("m", [(0.0, 5.0, "A"), (5.0, 5.0, "B")]), encoding="utf-8")
        ref = scoring.load_rttm(ref_p, uri="m")
        # Hypothesis uses different label names but identical segmentation.
        hyp_p = tmp_path / "hyp.rttm"
        hyp_p.write_text(_rttm("m", [(0.0, 5.0, "X"), (5.0, 5.0, "Y")]), encoding="utf-8")
        hyp = scoring.load_rttm(hyp_p, uri="m")
        res = scoring.compute_der(ref, hyp)
        assert res.der == pytest.approx(0.0)
        assert res.total == pytest.approx(10.0)

    def test_missed_detection_half(self, tmp_path):
        ref_p = tmp_path / "ref.rttm"
        ref_p.write_text(_rttm("m", [(0.0, 10.0, "A")]), encoding="utf-8")
        ref = scoring.load_rttm(ref_p, uri="m")
        hyp_p = tmp_path / "hyp.rttm"
        hyp_p.write_text(_rttm("m", [(0.0, 5.0, "A")]), encoding="utf-8")
        hyp = scoring.load_rttm(hyp_p, uri="m")
        res = scoring.compute_der(ref, hyp)
        assert res.der == pytest.approx(0.5)
        assert res.missed_detection == pytest.approx(5.0)
        assert res.false_alarm == pytest.approx(0.0)

    def test_speaker_confusion(self, tmp_path):
        # Reference: two speakers; hypothesis collapses them into one → confusion.
        ref_p = tmp_path / "ref.rttm"
        ref_p.write_text(_rttm("m", [(0.0, 5.0, "A"), (5.0, 5.0, "B")]), encoding="utf-8")
        ref = scoring.load_rttm(ref_p, uri="m")
        hyp_p = tmp_path / "hyp.rttm"
        hyp_p.write_text(_rttm("m", [(0.0, 10.0, "A")]), encoding="utf-8")
        hyp = scoring.load_rttm(hyp_p, uri="m")
        res = scoring.compute_der(ref, hyp)
        # Half the time is attributed to the wrong speaker.
        assert res.confusion == pytest.approx(5.0)
        assert res.der == pytest.approx(0.5)

    def test_srt_to_annotation_roundtrip_der(self, tmp_path):
        p = tmp_path / "b.srt"
        p.write_text(_DIARIZED_SRT, encoding="utf-8")
        ann = scoring.srt_to_annotation(p)
        # Scoring an annotation against itself is a perfect score.
        res = scoring.compute_der(ann, ann)
        assert res.der == pytest.approx(0.0)

    def test_uem_bounds_scored_region(self, tmp_path):
        # Reference speaks 0-10s; hypothesis only covers 0-5s (misses 5-10s).
        ref_p = tmp_path / "ref.rttm"
        ref_p.write_text(_rttm("m", [(0.0, 10.0, "A")]), encoding="utf-8")
        ref = scoring.load_rttm(ref_p, uri="m")
        hyp_p = tmp_path / "hyp.rttm"
        hyp_p.write_text(_rttm("m", [(0.0, 5.0, "A")]), encoding="utf-8")
        hyp = scoring.load_rttm(hyp_p, uri="m")
        # A UEM that only scores 0-5s should exclude the missed region → DER 0.
        uem_p = tmp_path / "m.uem"
        uem_p.write_text("m 1 0.000 5.000\n", encoding="utf-8")
        uem = scoring.load_uem(uem_p, uri="m")
        res = scoring.compute_der(ref, hyp, uem=uem)
        assert res.der == pytest.approx(0.0)
        assert res.total == pytest.approx(5.0)
