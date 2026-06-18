"""Run the evaluation harness: transcribe + diarize an AMI subset, then score.

Drives the *real* pipeline functions (scripts/transcribe.py, scripts/diarize.py)
so the numbers reflect our actual settings, then computes WER and DER against
AMI ground truth. The ASR model/backend and diarization toggle are
configurable, so changes from issues #3-#6 can be compared apples-to-apples
against today's baseline.

Examples:
    # Baseline: current stack on the default subset
    python -m evaluation.run_eval

    # Compare a different Whisper model, no diarization
    python -m evaluation.run_eval --asr-model large-v3 --no-diarize

    # Specific meetings, custom collar, JSON report
    python -m evaluation.run_eval IS1009a ES2004a --collar 0.25 --json report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent
for _p in (str(_ROOT), str(_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from evaluation import datasets_ami, scoring


def _transcribe(audio_path: Path, out_dir: Path, backend: str, model: str,
                language: str, verbose: bool) -> Path:
    """Produce an SRT for ``audio_path`` using the chosen ASR backend."""
    if backend == "whisper":
        import transcribe  # scripts/transcribe.py
        return transcribe.transcribe(
            audio_path=str(audio_path),
            output_dir=str(out_dir),
            model=model,
            language=language,
            verbose=verbose,
        )
    if backend == "parakeet":
        # Placeholder for issue #4 (NVIDIA Parakeet-TDT via MLX). Once a
        # Parakeet path exists in the pipeline, wire it in here.
        raise NotImplementedError(
            "Parakeet backend not implemented yet — see issue #4. Use --asr-backend whisper."
        )
    raise ValueError(f"Unknown ASR backend: {backend!r}")


def run_meeting(
    meeting: str,
    *,
    asr_backend: str = "whisper",
    asr_model: str = "turbo",
    language: str = "en",
    do_diarize: bool = True,
    diar_model_label: str = "pyannote/speaker-diarization-3.1",
    hf_token: str | None = None,
    device: str | None = None,
    collar: float = 0.0,
    cache_dir: Path | None = None,
    verbose: bool = True,
) -> dict:
    """Run + score one meeting. Returns a result row (errors captured, not raised)."""
    cache_dir = cache_dir or datasets_ami.default_cache_dir()
    work_dir = cache_dir / "work" / meeting
    work_dir.mkdir(parents=True, exist_ok=True)

    row: dict = {
        "meeting": meeting,
        "asr_backend": asr_backend,
        "asr_model": asr_model,
        "diar_model": diar_model_label if do_diarize else None,
        "wer": None,
        "der": None,        # SRT-derived labels (what the pipeline actually emits)
        "der_raw": None,    # pyannote's native output (comparable to published DER)
        "transcribe_s": None,
        "diarize_s": None,
        "error": None,
    }

    try:
        info = datasets_ami.ensure_meeting(meeting, cache_dir)
        audio = info["audio"]

        # --- Transcription ---
        t0 = time.monotonic()
        srt_path = _transcribe(audio, work_dir, asr_backend, asr_model, language, verbose)
        row["transcribe_s"] = round(time.monotonic() - t0, 1)

        # --- WER (only if a reference transcript is available) ---
        if info["transcript"]:
            ref_text = Path(info["transcript"]).read_text(encoding="utf-8")
            hyp_text = scoring.srt_to_text(srt_path)
            row["wer"] = scoring.compute_wer(ref_text, hyp_text).as_dict()

        # --- Diarization + DER ---
        if do_diarize:
            if not hf_token:
                row["error"] = "diarization requested but HF_TOKEN not set; DER skipped"
            else:
                import diarize  # scripts/diarize.py

                # Run the pyannote pipeline once; score both its native output
                # and the SRT-derived labels the pipeline ultimately emits.
                t0 = time.monotonic()
                diar_ann = diarize.run_diarization(
                    str(audio), hf_token, device=device, verbose=verbose
                )
                row["diarize_s"] = round(time.monotonic() - t0, 1)

                ref_ann = scoring.load_rttm(info["rttm"], uri=meeting)
                uem = scoring.load_uem(info["uem"], uri=meeting) if info.get("uem") else None

                # Raw: pyannote's native diarization, UEM-bounded → comparable
                # to published DER.
                row["der_raw"] = scoring.compute_der(
                    ref_ann, diar_ann, collar=collar, uem=uem
                ).as_dict()

                # SRT-derived: speaker labels applied to Whisper segments (the
                # pipeline's actual transcript output), reusing the same run.
                labeled = work_dir / f"{meeting}_labeled.srt"
                diarize.diarize(
                    audio_path=str(audio),
                    srt_path=str(srt_path),
                    output_path=str(labeled),
                    verbose=verbose,
                    diarization=diar_ann,
                )
                hyp_ann = scoring.srt_to_annotation(labeled, uri=meeting)
                row["der"] = scoring.compute_der(
                    ref_ann, hyp_ann, collar=collar, uem=uem
                ).as_dict()
    except Exception as e:  # one bad meeting shouldn't abort the whole run
        row["error"] = f"{type(e).__name__}: {e}"

    return row


def _pct(x: float | None) -> str:
    return f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "—"


def render_markdown(rows: list[dict]) -> str:
    """Render results as a Markdown table."""
    header = (
        "| Meeting | ASR backend | ASR model | Diar model | WER | DER (raw) | "
        "DER (srt) | Miss | FA | Conf | Transcribe (s) | Diarize (s) |"
    )
    sep = "|" + "|".join(["---"] * 12) + "|"
    lines = [header, sep]
    for r in rows:
        wer = r.get("wer") or {}
        der_raw = r.get("der_raw") or {}
        der = r.get("der") or {}
        # Miss/FA/Conf shown for the raw (native) diarization output.
        total = der_raw.get("total") or 0
        miss = der_raw.get("missed_detection")
        fa = der_raw.get("false_alarm")
        conf = der_raw.get("confusion")
        lines.append(
            "| {meeting} | {backend} | {model} | {diar} | {wer} | {der_raw} | {der} | "
            "{miss} | {fa} | {conf} | {ts} | {ds} |".format(
                meeting=r["meeting"],
                backend=r["asr_backend"],
                model=r["asr_model"],
                diar=r.get("diar_model") or "—",
                wer=_pct(wer.get("wer")),
                der_raw=_pct(der_raw.get("der")),
                der=_pct(der.get("der")),
                miss=_pct(miss / total) if total else "—",
                fa=_pct(fa / total) if total else "—",
                conf=_pct(conf / total) if total else "—",
                ts=r.get("transcribe_s") if r.get("transcribe_s") is not None else "—",
                ds=r.get("diarize_s") if r.get("diarize_s") is not None else "—",
            )
        )
    errs = [r for r in rows if r.get("error")]
    if errs:
        lines.append("")
        lines.append("**Notes / errors:**")
        for r in errs:
            lines.append(f"- {r['meeting']}: {r['error']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate the transcription/diarization pipeline against the AMI corpus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("meetings", nargs="*", default=None,
                        help=f"AMI meeting IDs (default: {datasets_ami.DEFAULT_SUBSET})")
    parser.add_argument("--asr-backend", default="whisper", choices=["whisper", "parakeet"],
                        help="ASR backend (default: whisper)")
    parser.add_argument("--asr-model", default=os.getenv("WHISPER_MODEL", "turbo"),
                        help="ASR model (default: $WHISPER_MODEL or 'turbo')")
    parser.add_argument("-l", "--language", default=os.getenv("WHISPER_LANGUAGE", "en"))
    parser.add_argument("--no-diarize", action="store_true",
                        help="Skip diarization (WER only)")
    parser.add_argument("--diar-model-label", default="pyannote/speaker-diarization-3.1",
                        help="Label recorded for the diarization model in the report")
    parser.add_argument("--hf-token", default=os.getenv("HF_TOKEN"),
                        help="HuggingFace token for pyannote (default: $HF_TOKEN)")
    parser.add_argument("--device", default=None, choices=["mps", "cpu"],
                        help="Torch device for diarization (default: auto)")
    parser.add_argument("--collar", type=float, default=0.0,
                        help="DER collar in seconds (0.0 = strict/comparable to pyannote; "
                             "0.25 = lenient NIST-style)")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="Write the raw results to this JSON file")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    meetings = args.meetings or datasets_ami.DEFAULT_SUBSET
    rows = []
    for m in meetings:
        if not args.quiet:
            print(f"\n=== Evaluating {m} ===", file=sys.stderr)
        rows.append(run_meeting(
            m,
            asr_backend=args.asr_backend,
            asr_model=args.asr_model,
            language=args.language,
            do_diarize=not args.no_diarize,
            diar_model_label=args.diar_model_label,
            hf_token=args.hf_token,
            device=args.device,
            collar=args.collar,
            verbose=not args.quiet,
        ))

    print("\n" + render_markdown(rows))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nRaw results written to {args.json_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
