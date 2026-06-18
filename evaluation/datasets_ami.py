"""Fetch a small, fixed subset of the AMI Meeting Corpus for evaluation.

Two ground-truth sources, both freely available (CC-BY-4.0):

  * Audio — the continuous mixed-headset WAV from the Edinburgh AMI mirror.
    This is a single mixed far-field-style track of all participants, which we
    feed to our pipeline as the "Others" track.

  * Diarization reference (RTTM) — pyannote's canonical "AMI-diarization-setup"
    (the ``only_words`` references), the same ones used for published
    community-1 / 3.1 DER numbers, so our DER is comparable to those.

  * Transcription reference (text) — OPTIONAL, via the Hugging Face
    ``edinburghcstr/ami`` dataset (requires the ``datasets`` package). If it
    is not installed the harness still runs DER; WER is reported as unavailable.

Downloaded audio is cached under ``.eval_cache/`` (gitignored) and never
committed. Nothing here imports heavy deps at module load.
"""

from __future__ import annotations

import os
import ssl
import sys
import urllib.request
from pathlib import Path

# Make project modules importable when run as a script.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
    sys.path.insert(0, str(_ROOT / "scripts"))

from root_detection import find_project_root

AMI_AUDIO_BASE = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
RTTM_BASE = (
    "https://raw.githubusercontent.com/pyannote/AMI-diarization-setup/main/only_words/rttms"
)
RTTM_SPLITS = ("test", "dev", "train")

# Short 4-participant scenario meetings (the "a" sessions are the shortest),
# which mirrors a typical small meeting and keeps eval runs fast.
DEFAULT_SUBSET = ["IS1009a"]


def default_cache_dir() -> Path:
    """Location for cached AMI audio/references (gitignored)."""
    return find_project_root() / ".eval_cache" / "ami"


def audio_url(meeting: str) -> str:
    return f"{AMI_AUDIO_BASE}/{meeting}/audio/{meeting}.Mix-Headset.wav"


def _ssl_context() -> ssl.SSLContext:
    """Build an SSL context that works on macOS Pythons with no system certs.

    Uses the ``certifi`` CA bundle when available (the usual fix for
    ``CERTIFICATE_VERIFY_FAILED``). Set ``EVAL_IGNORE_SSL=true`` (or the
    project's existing ``WHISPER_IGNORE_SSL=true``) to disable verification
    entirely, e.g. behind a TLS-intercepting corporate proxy.
    """
    if os.getenv("EVAL_IGNORE_SSL", "").lower() in ("true", "1", "yes") or \
       os.getenv("WHISPER_IGNORE_SSL", "").lower() in ("true", "1", "yes"):
        return ssl._create_unverified_context()
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _download(url: str, dest: Path, *, min_bytes: int = 1) -> Path:
    """Download ``url`` to ``dest`` unless a non-trivial file is already cached."""
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "obs-transcriber-eval"})
    with urllib.request.urlopen(req, context=_ssl_context()) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)
    return dest


def fetch_audio(meeting: str, cache_dir: Path | None = None) -> Path:
    """Download the meeting's mixed-headset WAV (large, ~tens of MB). Cached."""
    cache_dir = cache_dir or default_cache_dir()
    dest = cache_dir / "audio" / f"{meeting}.Mix-Headset.wav"
    # Audio files are large; guard against truncated/HTML-error caches.
    return _download(audio_url(meeting), dest, min_bytes=100_000)


def fetch_rttm(meeting: str, cache_dir: Path | None = None) -> Path:
    """Download the meeting's reference RTTM, trying each AMI split in turn."""
    cache_dir = cache_dir or default_cache_dir()
    dest = cache_dir / "rttms" / f"{meeting}.rttm"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    last_err: Exception | None = None
    for split in RTTM_SPLITS:
        try:
            return _download(f"{RTTM_BASE}/{split}/{meeting}.rttm", dest)
        except Exception as e:  # try the next split
            last_err = e
    raise FileNotFoundError(
        f"No reference RTTM found for meeting '{meeting}' in splits {RTTM_SPLITS}. "
        f"Last error: {last_err}"
    )


def fetch_reference_transcript(meeting: str, cache_dir: Path | None = None) -> Path | None:
    """Build a whole-meeting reference transcript for WER, if possible.

    Uses the Hugging Face ``edinburghcstr/ami`` dataset (segment text ordered by
    start time). Returns the path to a cached ``.txt`` reference, or ``None`` if
    the ``datasets`` package is unavailable or the meeting can't be resolved
    (in which case WER is simply skipped).

    NOTE: the exact ``edinburghcstr/ami`` schema should be validated on first
    real run; failures here are non-fatal by design.
    """
    cache_dir = cache_dir or default_cache_dir()
    dest = cache_dir / "transcripts" / f"{meeting}.txt"
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    try:
        from datasets import load_dataset
    except ImportError:
        return None

    try:
        # The "ihm" config is segmented per utterance with meeting_id + timing.
        # Stream and drop the (large) audio column so we only pull text — never
        # the multi-GB audio. We collect every segment for this meeting, then
        # order by start time to reconstruct the whole-meeting reference.
        ds = load_dataset(
            "edinburghcstr/ami", "ihm", split="test",
            streaming=True, trust_remote_code=True,
        )
        if "audio" in (ds.column_names or []):
            ds = ds.remove_columns("audio")
        rows = [r for r in ds if r.get("meeting_id") == meeting]
        if not rows:
            return None
        rows.sort(key=lambda r: float(r.get("begin_time", 0.0)))
        text = " ".join(str(r.get("text", "")).strip() for r in rows if r.get("text"))
        if not text.strip():
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return dest
    except Exception:
        # Best-effort: schema/availability of the HF dataset may change. WER is
        # skipped (DER still runs) rather than failing the whole eval.
        return None


def ensure_meeting(
    meeting: str,
    cache_dir: Path | None = None,
    *,
    want_transcript: bool = True,
) -> dict:
    """Ensure all available ground truth for a meeting is cached locally.

    Returns a dict with ``audio`` and ``rttm`` paths (always) and ``transcript``
    (a Path or None). Raises if audio or RTTM cannot be obtained.
    """
    cache_dir = cache_dir or default_cache_dir()
    result = {
        "meeting": meeting,
        "audio": fetch_audio(meeting, cache_dir),
        "rttm": fetch_rttm(meeting, cache_dir),
        "transcript": None,
    }
    if want_transcript:
        result["transcript"] = fetch_reference_transcript(meeting, cache_dir)
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pre-fetch the AMI eval subset.")
    parser.add_argument("meetings", nargs="*", default=DEFAULT_SUBSET,
                        help=f"Meeting IDs (default: {DEFAULT_SUBSET})")
    parser.add_argument("--no-transcript", action="store_true",
                        help="Skip the optional WER reference transcript")
    args = parser.parse_args()

    meetings = args.meetings or DEFAULT_SUBSET
    for m in meetings:
        print(f"Fetching {m} ...")
        info = ensure_meeting(m, want_transcript=not args.no_transcript)
        print(f"  audio:      {info['audio']}")
        print(f"  rttm:       {info['rttm']}")
        print(f"  transcript: {info['transcript'] or '(unavailable — WER will be skipped)'}")
