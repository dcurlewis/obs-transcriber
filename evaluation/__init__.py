"""Automated evaluation harness for obs-transcriber.

Measures transcription accuracy (WER) and speaker diarization accuracy (DER)
against ground-truth meeting audio (the AMI Meeting Corpus by default), so that
model/technique changes can be compared apples-to-apples.

See evaluation/README.md and GitHub issue #2.
"""
