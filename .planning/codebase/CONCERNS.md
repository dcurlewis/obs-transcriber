# Codebase Concerns

**Analysis Date:** 2026-02-07

## Tech Debt

**Hardcoded email address in calendar filtering:**
- Issue: The calendar service contains a hardcoded email filter for "dbdave@canva.com" which makes the code unusable for other users
- Files: `web/calendar_service.py` (lines 140-141)
- Impact: Application is tightly coupled to a single user's calendar. Any other user cannot use the calendar integration without modifying code.
- Fix approach: Replace hardcoded email with environment variable or user configuration that can be set at startup. Implement user preferences system for calendar filtering.

**Incomplete discard functionality in web interface:**
- Issue: `discard_recording()` method in `web/recorder.py` is stubbed out and not implemented
- Files: `web/recorder.py` (lines 432-439)
- Impact: Web UI users cannot discard recordings; only shell script users can. Creates inconsistency between CLI and web interfaces.
- Fix approach: Implement full discard logic mirroring the shell script `discard_recording()` function from `run.sh`.

**No validation of audio file integrity before transcription:**
- Issue: `transcribe.py` accepts audio files without checking if they contain valid audio data. Empty or corrupted WAV files pass through to MLX Whisper.
- Files: `scripts/transcribe.py` (lines 87-91)
- Impact: Processing fails partway through transcription if audio extraction produced empty files. No early detection of corrupted recordings.
- Fix approach: Add audio validation using ffmpeg before passing to mlx_whisper. Check file size and duration to detect empty audio.

**Weak hallucination filtering logic:**
- Issue: Hallucination detection uses simple regex patterns and heuristics that may not catch all hallucinations or may incorrectly filter legitimate speech
- Files: `scripts/filter_hallucinations.py` (lines 12-46)
- Impact: False positives (removing legitimate content) or false negatives (keeping spurious content). May require manual cleanup of transcripts after processing.
- Fix approach: Develop ML-based approach or contextual filtering that understands meeting context rather than pattern matching.

## Known Bugs

**Race condition in processing status tracking:**
- Symptoms: Multiple web UI requests may race when checking/setting `_processing_pid` global variable
- Files: `web/recorder.py` (lines 42-44, 249-258, 283-284, 301-302)
- Trigger: Rapid successive API calls to check processing status while process is starting/stopping
- Workaround: Use `_processing_lock` which IS implemented, but still check if all access paths use it consistently
- Current mitigation: Lock is used in most places but `_processing_pid` reads are not always locked

**Calendar event filtering loses attendee information:**
- Symptoms: Attendees from declined or no-response participants are excluded from transcripts
- Files: `web/calendar_service.py` (lines 187-190)
- Trigger: Any meeting with attendees who haven't accepted the invite
- Current mitigation: Only filters on ACCEPTED or TENTATIVE status; declined/no-response are skipped entirely
- Impact: Incomplete attendee list in meeting transcripts

**Shell script CSV parsing doesn't handle special characters properly:**
- Symptoms: Meeting names with semicolons or newlines corrupt the CSV queue format
- Files: `run.sh` (lines 130, 651-652)
- Trigger: User enters meeting name containing semicolons, pipes, or quotes
- Current mitigation: Basic sanitization in `run.sh` (line 179: `sed 's/[^a-zA-Z0-9]/-/g'`) but only applied to final filename, not queue CSV
- Impact: Queue file becomes unreadable; processing fails

**Empty SRT files not handled consistently:**
- Symptoms: Processing creates empty SRT files when audio contains no speech, then may fail during interleaving
- Files: `scripts/transcribe.py` (lines 125-129), `run.sh` (lines 338-402)
- Trigger: Recordings of meetings with only silence or music
- Current mitigation: Empty SRT files are created but verification exists, may still have edge cases
- Impact: Transcripts with missing speaker segments or malformed output

## Security Considerations

**OBS WebSocket password stored in plaintext .env file:**
- Risk: Credentials exposed if `.env` file is accidentally committed or backup is compromised
- Files: `.env` (not read for safety), `scripts/obs_controller.py` (lines 18-22)
- Current mitigation: `.env` is in `.gitignore`, but developers must manually manage it
- Recommendations:
  - Add setup validation to warn if `.env` is accessible to other users
  - Document credential management best practices
  - Consider prompting for password at runtime instead of storing

**Calendar service requests full access to all events:**
- Risk: Application can read all calendar events including private/sensitive ones
- Files: `web/calendar_service.py` (lines 47)
- Current mitigation: User must grant permission in macOS Security settings
- Recommendations:
  - Request only calendar read permission, not full access
  - Document data privacy implications clearly to users
  - Filter out sensitive events (e.g., marked private)

**Web interface lacks CSRF protection:**
- Risk: Cross-site requests could trigger unwanted recordings or processing
- Files: `web/app.py` (all POST endpoints lack CSRF tokens)
- Current mitigation: Only deployed locally (127.0.0.1)
- Recommendations:
  - Add CSRF token validation to all POST/PUT/DELETE endpoints
  - Implement proper session management
  - Add request origin validation

**No authentication for web API:**
- Risk: Any local process can access recording controls and start/stop transcription
- Files: `web/app.py` (all endpoints lack authentication)
- Current mitigation: Application listens only on 127.0.0.1 by default
- Recommendations:
  - Add session-based or token authentication for API access
  - Document security implications of listening on 127.0.0.1
  - Consider strict IP whitelisting

## Performance Bottlenecks

**Sequential MKV-to-WAV extraction is single-threaded:**
- Problem: FFmpeg audio extraction processes only one stream at a time, even though MKV has multiple tracks
- Files: `run.sh` (lines 215-218)
- Cause: FFmpeg command extracts audio:0 then audio:1 sequentially in same invocation
- Improvement path: Split into separate ffmpeg processes for each track to parallelize audio extraction. Could save 30-40% of processing time.

**Model downloads are not cached properly:**
- Problem: First transcription with a new model downloads GB of model weights to `~/.cache/huggingface`
- Files: `scripts/transcribe.py` (lines 107-117)
- Cause: MLX Whisper downloads model on first use, no progress indication or resumable downloads
- Improvement path: Pre-download models as part of setup, show download progress, implement resumable downloads for interrupted transfers.

**No parallelization across multiple recordings in queue:**
- Problem: Processing queue processes recordings serially, even though system could handle multiple in parallel
- Files: `run.sh` (lines 165-423), `web/recorder.py` (lines 260-302)
- Cause: Bash loop processes one recording at a time before moving to next
- Improvement path: Implement worker pool or queue processor that handles multiple recordings concurrently while respecting GPU memory limits.

**Large SRT files loaded entirely into memory:**
- Problem: No streaming processing for SRT files
- Files: `scripts/interleave.py` (lines 53-59), `scripts/filter_hallucinations.py` (lines 58-62)
- Cause: Both scripts use `srt.parse()` which loads entire file
- Impact: Memory usage scales with transcript length; very long meetings could cause OOM
- Improvement path: Implement streaming SRT parser for large files (>1 hour meetings).

## Fragile Areas

**Shell script string handling with paths containing spaces:**
- Files: `run.sh` (scattered throughout, especially lines 118, 212, 395)
- Why fragile: Paths are used in find/xargs commands which break with spaces or special characters
- Safe modification: Always quote variables containing file paths: `"$variable"` not `$variable`
- Test coverage: No tests for edge cases like paths with spaces, quotes, or special characters
- Current risk: Works in most cases but fails silently with unusual filenames

**Queue CSV format is custom and fragile:**
- Files: `run.sh` (lines 130, 437-441), `web/recorder.py` (lines 109-118)
- Why fragile: Semicolon delimiter chosen arbitrarily; no escaping mechanism for special characters. Meeting names with semicolons corrupt CSV format.
- Safe modification: Use proper CSV library for parsing/writing instead of sed/awk. Python code should use csv module consistently.
- Test coverage: No unit tests for queue file format handling
- Current risk: If user enters semicolon in meeting name, entire queue becomes unreadable

**Hard dependency on fixed directory structure:**
- Files: `web/app.py` (line 14), `web/recorder.py` (line 47), `run.sh` (lines 26-27, 47)
- Why fragile: Code assumes relative paths from project root. Will break if run from different directory.
- Safe modification: Calculate paths relative to script location using `Path(__file__).parent.parent` consistently
- Test coverage: No tests for running from arbitrary directories
- Current risk: CI/CD or containerization could break if working directory isn't set correctly

**MLX Whisper model loading not resilient to network issues:**
- Files: `scripts/transcribe.py` (lines 107-117)
- Why fragile: First use downloads multi-GB models from HuggingFace with no retry logic or resume support
- Safe modification: Add retry loop with exponential backoff, implement resumable downloads
- Test coverage: No error handling tests for network failures
- Current risk: Transient network issues cause entire transcription job to fail; must restart from scratch

**Calendar service hardcoded attendee email filtering:**
- Files: `web/calendar_service.py` (line 140)
- Why fragile: Single hardcoded email address makes code non-portable
- Safe modification: Load user email from environment or configuration
- Test coverage: No tests for multi-user scenarios
- Current risk: Code is unusable for any user except "dbdave@canva.com"

## Scaling Limits

**Processing queue stored in flat CSV file:**
- Current capacity: Works fine for <1000 recordings, but no pagination or archival
- Limit: CSV file could become >1MB with hundreds of recordings, slower to read/write
- Scaling path: Implement SQLite database for queue instead of CSV. Allows indexing, faster queries, easier filtering.

**Web UI maintains global processing state in-memory:**
- Current capacity: Single process handles all recording/processing state
- Limit: If process crashes, state is lost (though it's readable from files)
- Scaling path: Use persistent queue backend (Redis, database) instead of in-memory `_processing_pid`

**Calendar service fetches all events for date, filters in-memory:**
- Current capacity: Works fine for typical user with <50 events/day
- Limit: No pagination for users with hundreds of calendar entries
- Scaling path: Implement date range queries and pagination in EventKit integration

## Dependencies at Risk

**pyannote.audio (2.1.0+) as unused import:**
- Risk: Included in requirements.txt but never used in code
- Files: `requirements.txt`, never imported anywhere
- Impact: Adds 500MB+ to dependency tree unnecessarily; increases attack surface
- Migration plan: Remove from requirements.txt if speaker diarization not planned. If planned, implement diarization in transcription pipeline.

**obsws-python dependency version not pinned:**
- Risk: Dependency tracking is `obsws-python` (no version), could break with major version changes
- Files: `requirements.txt` (line 2), used in `scripts/obs_controller.py`
- Impact: Future versions could change API, breaking OBS integration
- Migration plan: Pin to specific version that's been tested (e.g., obsws-python==1.4.0)

**torch>=1.9.0 dependency is very broad:**
- Risk: PyTorch major version changes could break compatibility with other dependencies
- Files: `requirements.txt` (line 6), indirect dependency via mlx-whisper
- Impact: Could conflict with system PyTorch installation or other ML tools
- Migration plan: Test and pin to specific working version (e.g., torch==2.0.1)

**macOS-specific EventKit dependency:**
- Risk: Calendar feature only works on macOS; code imports EventKit conditionally but doesn't fail gracefully on other platforms
- Files: `web/calendar_service.py` (lines 14-23)
- Impact: Users on Linux/Windows cannot use calendar features at all
- Migration plan: Implement alternative calendar providers (Google Calendar API, Outlook) or clearly document macOS-only requirement

## Missing Critical Features

**No speaker diarization in transcripts:**
- Problem: "Others" audio track uses generic speaker labels "[Speaker 1]" instead of identifying who spoke
- Blocks: Cannot easily identify who said what in multi-person conversations
- Recommendation: Implement pyannote.audio diarization (already in requirements.txt but unused)

**No transcript search or indexing:**
- Problem: Transcripts are flat text files with no way to search across meetings
- Blocks: Users must manually grep/search through files
- Recommendation: Implement full-text search index (Sqlite FTS, ElasticSearch) for transcripts

**No transcript editing or manual correction UI:**
- Problem: Hallucination filtering is automatic; users cannot manually correct obvious errors
- Blocks: Error correction requires manual text file editing
- Recommendation: Add transcript editing UI in web app with before/after diff view

**No support for non-English languages:**
- Problem: Language defaults to 'en', no validation that selected language is supported
- Blocks: Non-English meetings cannot be transcribed accurately
- Recommendation: Add language selection UI, validate language codes, test with multiple languages

**No encryption for transcript files:**
- Problem: Transcripts stored as plain text, no access control
- Blocks: Sensitive meeting content is readable by any user with filesystem access
- Recommendation: Implement encryption at rest with per-meeting access keys

## Test Coverage Gaps

**No unit tests for shell script functions:**
- What's not tested: `process_recordings()`, `show_status()`, `discard_recording()` logic
- Files: `run.sh` (entire file)
- Risk: Refactoring or edge case changes could break functionality undetected
- Priority: High - Core workflow is untested

**No integration tests for transcription pipeline:**
- What's not tested: Full end-to-end flow from recording to final transcript
- Files: All of `scripts/`, called from `run.sh`
- Risk: Breaking changes could go unnoticed across module boundaries
- Priority: High - Pipeline is complex with many failure points

**No tests for CSV queue format handling:**
- What's not tested: Special characters in meeting names, queue corruption recovery
- Files: `run.sh` lines 130, 437-441
- Risk: Edge cases with unusual meeting names cause silent failures
- Priority: Medium - Affects data integrity but only with unusual inputs

**No tests for web API endpoints:**
- What's not tested: Start/stop/process recording API calls, error handling, concurrent requests
- Files: `web/app.py` (all endpoints)
- Risk: API failures in web UI not caught until user encounters them
- Priority: High - Web UI is primary user interface

**No tests for calendar filtering logic:**
- What's not tested: Attendee filtering, timezone handling, 1:1 vs group meeting detection
- Files: `web/calendar_service.py`
- Risk: Calendar filtering could exclude valid meetings or include invalid ones undetected
- Priority: Medium - Users would notice filtered meetings but hard to debug

**No tests for hallucination filtering:**
- What's not tested: False positives/negatives in hallucination detection
- Files: `scripts/filter_hallucinations.py`
- Risk: Legitimate content could be removed or hallucinations kept undetected
- Priority: Medium - Affects output quality

**No error handling tests:**
- What's not tested: Network failures, missing files, corrupted audio, disk space issues
- Files: All Python scripts
- Risk: Graceful degradation untested; users see raw exceptions
- Priority: High - Error messages are first impression of quality

---

*Concerns audit: 2026-02-07*
