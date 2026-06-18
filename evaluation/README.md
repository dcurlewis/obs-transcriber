# Evaluation harness

Automated, reproducible measurement of the pipeline's **transcription accuracy
(WER)** and **speaker diarization accuracy (DER)** against ground-truth meeting
audio, so model/technique changes (issues #3–#6) can be compared apples-to-apples
instead of eyeballed. Tracks GitHub issue **#2**.

## Why the AMI Meeting Corpus

[AMI](https://groups.inf.ed.ac.uk/ami/corpus/) is the standard public
(CC-BY-4.0) multi-participant meeting dataset, and it maps onto our architecture:

- ~100 h of 4-person English meetings.
- A continuous **mixed-headset** track we feed as the "Others" track.
- Ground truth for **both** metrics: manual transcripts (→ WER) and speaker
  segmentation (→ DER) — the same references behind published community-1 / 3.1
  DER numbers, so our DER is comparable.

Audio and the diarization RTTM references are downloaded on demand into
`.eval_cache/` (gitignored — never committed).

## Components

| File | Role |
|---|---|
| `scoring.py` | Pure WER (jiwer) + DER (pyannote.metrics) + SRT/RTTM converters. Fully unit-tested. |
| `datasets_ami.py` | Fetch a fixed small AMI subset (audio from the Edinburgh mirror, RTTM from pyannote's `AMI-diarization-setup`). |
| `run_eval.py` | Orchestrator/CLI: drives the *real* pipeline (`scripts/transcribe.py`, `scripts/diarize.py`) then scores. |

## Setup

```bash
source venv/bin/activate
pip install -r requirements.txt          # adds jiwer; pyannote.metrics ships with pyannote.audio
```

The WER reference transcript is fetched over plain HTTP from the HF
datasets-server (no `datasets` package needed). On the very first fetch the
server spends ~30–60 s building a filter index (the harness retries through
the transient "index is loading" responses), then caches the result.

Diarization (DER) needs a HuggingFace token with the pyannote model licenses
accepted — same setup as `scripts/diarize.py` (`HF_TOKEN` in `.env`).

If you hit `CERTIFICATE_VERIFY_FAILED` (common on macOS / behind a corporate
proxy), the downloader uses `certifi` automatically; as a last resort set
`EVAL_IGNORE_SSL=true`.

## Running

```bash
# Pre-fetch the default subset (optional; run_eval fetches on demand)
python -m evaluation.datasets_ami

# Baseline: current stack (whisper turbo + pyannote 3.1) on the default subset
python -m evaluation.run_eval --json baseline.json

# WER only (no HF token needed), different model
python -m evaluation.run_eval --asr-model large-v3 --no-diarize

# Specific meetings, lenient NIST-style collar
python -m evaluation.run_eval IS1009a ES2004a --collar 0.25
```

Output is a Markdown table with two DER columns plus timings:

- **DER (raw)** — pyannote's *native* diarization output, UEM-bounded. This is
  the apples-to-apples number for comparing diarization *models* (#3), closest
  to pyannote's published figures. Miss / FA / Conf are reported for this.
- **DER (srt)** — speaker labels applied to Whisper segments by max-overlap, i.e.
  what the pipeline *actually* emits in the transcript. The gap between the two
  is the cost of segment-span labeling and is what #6 (word-level assignment)
  targets.

Both come from a single pyannote run. Use `--collar 0.0` (default) for numbers
comparable to pyannote's published benchmarks; `--collar 0.25` for the older
lenient scoring. The diarization model is defined once in
`scripts/diarize.py::DIARIZATION_MODEL`, so #3's model bump updates the pipeline
and the harness together.

### Comparing changes (#3–#6)

- **#3 diarization model**: after pointing `scripts/diarize.py` at
  `community-1`, re-run and pass `--diar-model-label pyannote/speaker-diarization-community-1`.
- **#4 Parakeet ASR**: implement the `parakeet` branch in `run_eval._transcribe`,
  then `--asr-backend parakeet`.
- **#5 VAD / #6 word-level assignment**: changes land in the pipeline; just re-run
  and compare WER / DER to the recorded baseline.

## Tests

```bash
# Fast, hermetic scoring unit tests (run with the default suite)
python -m pytest tests/test_eval_scoring.py

# Opt-in E2E (downloads AMI data; needs network)
RUN_EVAL=1 python -m pytest tests/test_eval_harness.py -m eval -s

# Full E2E incl. transcription + diarization (slow; needs models + HF_TOKEN)
RUN_EVAL=1 RUN_EVAL_FULL=1 python -m pytest tests/test_eval_harness.py -m eval -s
```

## Status / known limitations

- **DER** (raw + srt) is wired end-to-end and verified against real AMI ground
  truth, UEM-bounded when the UEM is available.
- **WER reference** is fetched from the HF datasets-server filter API over
  `edinburghcstr/ami` (pure HTTP). If the service is unavailable the harness
  reports WER as `—` and still produces DER. You can also drop your own
  reference at `.eval_cache/ami/transcripts/<MEETING>.txt`.
- RTFx/throughput numbers are wall-clock on *this* machine — use for relative
  comparison, not as absolute leaderboard figures.
- Baseline numbers for today's stack are recorded in issue #2.
