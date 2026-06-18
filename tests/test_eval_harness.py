"""End-to-end evaluation-harness tests.

These are opt-in: they download AMI data from the network and (for the full
run) load ASR/diarization models. They are skipped unless ``RUN_EVAL=1`` so the
default fast suite stays hermetic.

Run them with:
    RUN_EVAL=1 python -m pytest tests/test_eval_harness.py -m eval -s
"""

import os
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(os.getenv("RUN_EVAL") != "1", reason="set RUN_EVAL=1 to run eval E2E"),
]

from evaluation import datasets_ami, scoring


def test_fetch_rttm_and_score(tmp_path):
    """Cheap check: RTTM download + parse + DER integration (no audio/models)."""
    meeting = datasets_ami.DEFAULT_SUBSET[0]
    rttm = datasets_ami.fetch_rttm(meeting, cache_dir=tmp_path)
    assert rttm.exists() and rttm.stat().st_size > 0

    ref = scoring.load_rttm(rttm, uri=meeting)
    assert len(ref.labels()) >= 2  # AMI scenario meetings have multiple speakers

    # Scoring the reference against itself must be a perfect score.
    res = scoring.compute_der(ref, ref)
    assert res.der == pytest.approx(0.0)
    assert res.total > 0


@pytest.mark.skipif(os.getenv("RUN_EVAL_FULL") != "1",
                    reason="set RUN_EVAL_FULL=1 to run the full transcribe+diarize E2E")
def test_full_pipeline_eval():
    """Full run on the default subset; asserts the numbers are at least plausible."""
    from evaluation.run_eval import run_meeting

    meeting = datasets_ami.DEFAULT_SUBSET[0]
    row = run_meeting(
        meeting,
        asr_model=os.getenv("WHISPER_MODEL", "turbo"),
        do_diarize=bool(os.getenv("HF_TOKEN")),
        hf_token=os.getenv("HF_TOKEN"),
        verbose=True,
    )
    assert row["error"] is None, row["error"]
    if row["wer"] is not None:
        assert 0.0 <= row["wer"]["wer"] < 1.0
    if row["der"] is not None:
        assert 0.0 <= row["der"]["der"] < 1.0
