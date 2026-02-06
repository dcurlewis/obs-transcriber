# OBS Meeting Transcriber - Generalization & Hardening

## What This Is

OBS Meeting Transcriber is a tool for automated recording, transcription, and processing of multi-track meeting audio. This milestone focuses on generalizing the codebase from "working for me" to "working for anyone who clones it" - removing hardcoded personal information, completing stubbed functionality, adding robustness to the core pipeline, and implementing basic regression testing.

## Core Value

The transcription pipeline should work reliably for any user without requiring code modifications - just configuration.

## Requirements

### Validated

The following features are already implemented and working:

- ✓ OBS recording control via WebSocket API — existing
- ✓ Multi-track audio extraction and normalization — existing
- ✓ Parallel transcription with MLX Whisper — existing
- ✓ Speaker diarization for "Others" track — existing
- ✓ Hallucination filtering for common Whisper artifacts — existing
- ✓ Chronological transcript interleaving — existing
- ✓ Web UI for recording management — existing
- ✓ Calendar integration for meeting context (macOS) — existing
- ✓ Processing queue with state tracking — existing
- ✓ CLI interface for all operations — existing

### Active

Current scope for this generalization milestone:

- [ ] Replace hardcoded email address with environment variable
- [ ] Make script paths location-independent (work from any directory)
- [ ] Implement web UI discard functionality (complete stubbed method)
- [ ] Fix CSV queue format to handle special characters properly
- [ ] Add corrupted audio detection before transcription
- [ ] Audit and remove any committed personal file paths
- [ ] Ensure calendar data doesn't leak into logs or committed files
- [ ] Implement core pipeline tests (transcription workflow regression prevention)

### Out of Scope

- Full error handling for all failure scenarios — defer to future
- Comprehensive test coverage (web API, calendar, error handling) — only core pipeline for now
- Multi-user authentication or access control — single-user tool
- Speaker diarization improvements — existing implementation sufficient
- Non-English language support — English-only for v1
- Cross-platform calendar integration — macOS EventKit is acceptable constraint
- Performance optimizations (parallel queue processing, streaming SRT) — defer
- Encryption for transcript files — user responsibility

## Context

**Existing System:**
- Brownfield project with comprehensive codebase analysis in `.planning/codebase/`
- Three-tier architecture: orchestration (bash) → services (Python) → external tools (OBS, FFmpeg, MLX Whisper)
- Currently works well for single user but has hardcoded assumptions
- Public repository requires privacy-conscious development

**Known Issues Addressed:**
- Hardcoded email "dbdave@canva.com" in calendar filtering (CONCERNS.md line 8)
- Stubbed `discard_recording()` in web UI (CONCERNS.md line 14)
- Fragile CSV queue format with semicolons (CONCERNS.md line 47)
- No audio validation before transcription (CONCERNS.md line 20)
- Hard dependency on running from project root (CONCERNS.md line 143)
- Private information exposure risks (CONCERNS.md lines 64-89)

**Testing Baseline:**
- Currently no automated tests (TESTING.md line 7)
- Manual testing only
- Core pipeline is critical path requiring regression protection

## Constraints

- **Tech stack**: Python 3, Bash, Flask, MLX Whisper (Apple Silicon optimized) — no changes
- **Platform**: macOS required for Calendar integration (EventKit dependency)
- **External dependencies**: OBS Studio, FFmpeg, macOS Calendar.app — must remain compatible
- **Backward compatibility**: Existing users' .env files and queue format must continue working
- **Privacy**: No personal data in committed files (email, calendar details, file paths)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Environment variable for email filtering | Existing .env pattern, simple to implement, maintains backward compat | — Pending |
| Python csv module for queue | More robust than sed/awk, handles escaping, well-tested library | — Pending |
| Core pipeline tests only | Highest ROI for regression prevention, limits scope for v1 | — Pending |
| Location-independent paths via Path(__file__).parent | Standard Python pattern, works from any directory | — Pending |
| Keep macOS-only calendar | EventKit works well, cross-platform out of scope for generalization milestone | — Pending |

---
*Last updated: 2026-02-07 after initialization*
