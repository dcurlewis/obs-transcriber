# Testing Patterns

**Analysis Date:** 2026-02-07

## Test Framework

**Runner:**
- No automated test framework configured
- Not detected: pytest, unittest, Jest, Vitest, or other test runners
- No `pytest.ini`, `setup.cfg`, `pyproject.toml`, or test configuration files present

**Assertion Library:**
- Not applicable (no automated tests)

**Run Commands:**
- No test execution commands defined
- Manual testing only (per CLAUDE.md project instructions)

## Test File Organization

**Location:**
- No test files present in repository
- No `tests/`, `__tests__/`, or `test_` prefixed files

**Naming:**
- Not established (no test files to reference)

**Structure:**
- Not applicable

## Manual Testing Approach

**Current Practice:**
Based on codebase structure and CLAUDE.md, testing is manual:

1. **Recording Control Testing:**
   - Manual invocation: `./run.sh start "Meeting Name"`
   - Manual stop: `./run.sh stop`
   - Verification: Check `.pending_meeting` file exists/removed, recording files created

2. **Processing Pipeline Testing:**
   - Manual invocation: `./run.sh process`
   - Verification: Check for WAV files created, SRT transcripts generated, final transcript created

3. **Web UI Testing:**
   - Manual server start: `python web/app.py`
   - Browser navigation to `http://localhost:5000`
   - Manual click-through of record/stop/process buttons

4. **Calendar Integration Testing:**
   - Manual date navigation in web UI
   - Visual verification of meetings displayed
   - Check event matching logic (Zoom link detection, attendee filtering)

## Integration Point Testing

**Python Scripts Integration:**
- `obs_controller.py` tested by invoking from `run.sh` and `web/recorder.py`
- `transcribe.py` tested in processing pipeline with real audio files
- `interleave.py` tested with SRT output from transcribe.py
- `filter_hallucinations.py` tested by processing real transcripts

**Web Layer Integration:**
- `web/app.py` tested manually via browser UI
- `web/recorder.py` tested by triggering start/stop/process from web endpoints
- `web/calendar_service.py` tested by verifying meeting list display

**Error Path Testing:**
Implicit error paths are tested by:
- Running with invalid inputs (missing OBS, missing audio files)
- Checking stderr output and exit codes
- Verifying recovery logic (e.g., resume processing if MKV is missing but WAV exists)

## Error Detection Patterns

**Expected Failures:**
- OBS not running or not responsive: `obs_controller.py` catches `ConnectionRefusedError`
- Audio file missing during transcription: `transcribe.py` checks `if not audio_path.exists()` and raises `FileNotFoundError`
- Recording file not found: `run.sh` checks `if [ -z "$LATEST_RECORDING" ]` and exits
- SRT parsing errors: Python scripts catch exceptions and return error status

**Recovery Mechanisms:**
- Transcription retry: `run.sh` retries failed transcriptions with smaller model (base)
- Processing resume: `run.sh` detects intermediate files and resumes from recovery point
- WAV file verification: Checks file size with `-s` flag to ensure content exists
- OBS startup wait: Waits up to 10 seconds for OBS to start with periodic polling

**Logging for Debugging:**
- Processing operations logged to `logs/processing.log` with timestamps
- Calendar debug mode: Set `DEBUG_CALENDAR=true` env var to see attendee filtering decisions
- Verbose transcription: MLX Whisper prints progress when `verbose=True`

## What IS Tested (Implicitly)

**Happy Path:**
- Full recording → audio extraction → transcription → interleaving workflow
- Calendar event fetching and filtering
- Web API endpoints responding to valid requests

**Error Cases (Implicit):**
- OBS connection failures
- Missing/corrupted audio files
- Network timeouts (OBS WebSocket)
- File system operations (permissions, disk space)

## What IS NOT Tested

**Unit Test Coverage:**
- Individual functions isolated from dependencies
- Edge cases in string parsing or formatting
- Model name mapping in `transcribe.py` not tested for all model variants
- Hallucination filtering patterns not tested comprehensively

**Integration Gaps:**
- Calendar service (EventKit) not tested without macOS/Calendar.app
- Flask routes not tested with various invalid JSON payloads
- Multi-threaded processing (background task queue) not tested under load
- Concurrent recording + processing not tested

**Data Validation:**
- Input meeting names: only basic validation (`if [ -z "$MEETING_NAME" ]`)
- Attendee name formats: no validation, assumes pipe-delimited strings
- Date format parsing: minimal validation in `interleave.py`

## Mocking Patterns

**Current Approach:**
- No mocking framework used (no mock objects or stubs)
- Tests use real external systems:
  - Real OBS WebSocket server required for `obs_controller.py` testing
  - Real audio files used for transcription testing
  - Real Calendar.app used for calendar integration testing

**What Could Be Mocked:**
- OBS WebSocket client: Could mock `obsws_python.ReqClient` to avoid needing running OBS
- MLX Whisper: Could mock transcription to return test SRT data
- EventKit: Could mock calendar event store
- Flask requests: Could mock HTTP requests for API testing

## Test Data Strategy

**Fixture Sources:**
- Real meeting recordings stored in `recordings/` directory
- Real SRT files from successful transcriptions used as reference

**Test Data Locations:**
- `recordings/` directory contains subdirectories with completed transcriptions
- Sample output files: `*_transcript.txt` (final interleaved output)

## Coverage Gaps

**High Risk, Untested Areas:**
- Parallel transcription process handling: Two concurrent `transcribe.py` invocations
- CSV parsing with special characters in meeting names
- Race conditions in web layer during simultaneous start/stop requests
- File system edge cases (permissions, full disk, symlink handling)

**Medium Risk, Partially Tested:**
- Recovery from partial failures (tested implicitly in processing, not systematically)
- Long-running transcriptions (stress test with large audio files)
- Calendar service with multiple calendars or complex attendee lists

**Low Priority, Untested:**
- Discard functionality (marked "not yet implemented" in `recorder.py`)
- Web UI responsive design (tested manually only)
- Performance optimization paths

## Testing Best Practices Going Forward

**For Future Test Implementation:**

1. **Recommended Framework:**
   - Python: pytest (lightweight, good for integration tests)
   - JavaScript/Web: Jest or Vitest for web UI components

2. **Test Structure:**
   ```python
   # tests/test_transcribe.py
   def test_transcribe_with_valid_audio():
       # Use real small audio file from fixtures/
       result = transcribe("fixtures/sample.wav", output_dir="/tmp", model="base")
       assert result.exists()

   def test_obs_controller_connection_refused():
       # Mock obsws_python.ReqClient to raise ConnectionRefusedError
       with pytest.raises(ConnectionRefusedError):
           client = obs.ReqClient(host="invalid", port=9999)
   ```

3. **Test Data Organization:**
   - Create `tests/fixtures/` directory with small audio/SRT files
   - Include sample calendar events for calendar service testing
   - Store expected outputs for comparison

4. **Continuous Integration:**
   - Could add GitHub Actions workflow to run tests on push
   - Require passing tests before merging to main

## Known Test Blockers

- EventKit dependency only available on macOS (test isolation needed)
- OBS WebSocket requires running OBS server (could use Docker or mock)
- Large audio files needed for real transcription testing (storage constraint)
- MLX Whisper model downloads (~3-4 GB per model, cache required)

---

*Testing analysis: 2026-02-07*
