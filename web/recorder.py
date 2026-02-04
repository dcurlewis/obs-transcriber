#!/usr/bin/env python3
"""
Recording controller for managing OBS recordings and processing queue
"""

import os
import subprocess
import time
from pathlib import Path
from datetime import datetime
import csv
import threading
import logging

# Configure logging for processing
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Set up file handler for processing logs
processing_logger = logging.getLogger('processing')
processing_logger.setLevel(logging.INFO)

# Create file handler that writes to a rotating log file
log_file = LOG_DIR / 'processing.log'
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
processing_logger.addHandler(file_handler)


class RecordingController:
    """Controls OBS recording and manages the processing queue"""
    
    # Class-level tracking for processing state
    _processing_pid = None
    _processing_lock = threading.Lock()
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.pending_file = self.project_root / '.pending_meeting'
        self.queue_file = self.project_root / 'processing_queue.csv'
        self.obs_controller = self.project_root / 'scripts' / 'obs_controller.py'
        self.python_cmd = self._get_python_cmd()
        self.log_dir = self.project_root / 'logs'
        self.log_dir.mkdir(exist_ok=True)
        
    def _get_python_cmd(self):
        """Get the Python command to use (prefer venv)"""
        venv_python = self.project_root / 'venv' / 'bin' / 'python'
        if venv_python.exists():
            return str(venv_python)
        return 'python3'
    
    def ensure_obs_running(self):
        """Launch OBS if not already running"""
        result = subprocess.run(['pgrep', '-x', 'OBS'], capture_output=True)
        if result.returncode != 0:
            # OBS not running, launch it
            print("Launching OBS...")
            subprocess.Popen(['open', '-a', 'OBS'])
            
            # Wait for OBS to start (check process every second, up to 10 seconds)
            max_wait = 10
            for i in range(max_wait):
                time.sleep(1)
                result = subprocess.run(['pgrep', '-x', 'OBS'], capture_output=True)
                if result.returncode == 0:
                    print(f"OBS started after {i+1} seconds")
                    # Give OBS WebSocket server time to initialize
                    time.sleep(3)
                    break
            else:
                raise Exception("OBS failed to start within 10 seconds")
            
            return True  # OBS was started
        return False  # OBS already running
    
    def get_status(self):
        """Get current recording status and queue information"""
        status = {
            'is_recording': self.pending_file.exists(),
            'current_meeting': None,
            'queue': []
        }
        
        # Get current recording info
        if self.pending_file.exists():
            try:
                lines = self.pending_file.read_text().strip().split('\n')
                if len(lines) >= 2:
                    status['current_meeting'] = {
                        'name': lines[0],
                        'date': lines[1]
                    }
            except Exception as e:
                print(f"Error reading pending file: {e}")
        
        # Get queue info
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    reader = csv.reader(f, delimiter=';')
                    for row in reader:
                        if len(row) >= 4:
                            status['queue'].append({
                                'path': row[0],
                                'name': row[1],
                                'date': row[2],
                                'status': row[3]
                            })
                
                # Sort by date descending (newest first)
                status['queue'].sort(key=lambda x: x['date'], reverse=True)
            except Exception as e:
                print(f"Error reading queue file: {e}")
        
        return status
    
    def start_recording(self, meeting_name, attendees=None):
        """Start a new recording"""
        # Check if already recording
        if self.pending_file.exists():
            last_meeting = self.pending_file.read_text().strip().split('\n')[0]
            return {
                'success': False,
                'error': f"Already recording '{last_meeting}'. Stop the current recording first."
            }
        
        # Ensure OBS is running
        try:
            obs_was_started = self.ensure_obs_running()
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to launch OBS: {str(e)}"
            }
        
        # Start recording via OBS controller
        try:
            result = subprocess.run(
                [self.python_cmd, str(self.obs_controller), 'start'],
                capture_output=True,
                text=True,
                check=True,
                timeout=10  # Add timeout to prevent hanging
            )
            
            # Create pending file with attendees (pipe-delimited)
            meeting_date = datetime.now().strftime("%Y%m%d_%H%M")
            attendee_str = '|'.join(attendees) if attendees else ''
            self.pending_file.write_text(f"{meeting_name}\n{meeting_date}\n{attendee_str}\n")
            
            return {
                'success': True,
                'message': f"Recording started for '{meeting_name}'",
                'obs_was_started': obs_was_started
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': "OBS WebSocket connection timeout. Make sure OBS WebSocket server is enabled and configured correctly."
            }
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            return {
                'success': False,
                'error': f"Failed to start recording: {error_msg}"
            }
    
    def stop_recording(self):
        """Stop the current recording"""
        # Check if recording
        if not self.pending_file.exists():
            return {
                'success': False,
                'error': "No recording in progress"
            }
        
        # Get meeting info (including attendees)
        lines = self.pending_file.read_text().strip().split('\n')
        meeting_name = lines[0]
        meeting_date = lines[1]
        attendees = lines[2] if len(lines) > 2 else ''
        
        # Stop recording via OBS controller
        try:
            result = subprocess.run(
                [self.python_cmd, str(self.obs_controller), 'stop'],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Give OBS time to finalize file
            time.sleep(4)
            
            # Find the latest recording
            recording_path = os.environ.get('RECORDING_PATH', '.')
            recording_path = recording_path.replace('~', os.path.expanduser('~'))
            
            # Find latest .mkv file
            result = subprocess.run(
                f'find "{recording_path}" -maxdepth 1 -name "*.mkv" -print0 | xargs -0 ls -t | head -n 1',
                shell=True,
                capture_output=True,
                text=True
            )
            
            latest_recording = result.stdout.strip()
            
            if not latest_recording:
                self.pending_file.unlink()
                return {
                    'success': False,
                    'error': f"Could not find recording file in {recording_path}"
                }
            
            # Add to queue (including attendees as 5th field)
            self.queue_file.touch(exist_ok=True)
            with open(self.queue_file, 'a') as f:
                f.write(f"{latest_recording};{meeting_name};{meeting_date};recorded;{attendees}\n")
            
            # Remove pending file
            self.pending_file.unlink()
            
            return {
                'success': True,
                'message': f"Recording stopped and queued for '{meeting_name}'",
                'recording_file': latest_recording
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'error': f"Failed to stop recording: {e.stderr}"
            }
    
    def _is_processing_running(self):
        """Check if a processing job is currently running"""
        with RecordingController._processing_lock:
            if RecordingController._processing_pid is not None:
                try:
                    # Check if process is still running
                    os.kill(RecordingController._processing_pid, 0)
                    return True
                except OSError:
                    # Process has finished
                    RecordingController._processing_pid = None
            return False
    
    def _run_processing(self, log_file_path):
        """Run processing in a thread, capturing output to log file"""
        run_script = self.project_root / 'run.sh'
        
        processing_logger.info("=" * 60)
        processing_logger.info("Starting transcription processing")
        processing_logger.info("=" * 60)
        
        try:
            with open(log_file_path, 'a') as log_file:
                log_file.write(f"\n{'='*60}\n")
                log_file.write(f"Processing started at {datetime.now().isoformat()}\n")
                log_file.write(f"{'='*60}\n\n")
                log_file.flush()
                
                process = subprocess.Popen(
                    [str(run_script), 'process'],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.project_root)
                )
                
                with RecordingController._processing_lock:
                    RecordingController._processing_pid = process.pid
                
                # Wait for process to complete
                process.wait()
                
                log_file.write(f"\n{'='*60}\n")
                log_file.write(f"Processing finished at {datetime.now().isoformat()}\n")
                log_file.write(f"Exit code: {process.returncode}\n")
                log_file.write(f"{'='*60}\n")
                
                processing_logger.info(f"Processing completed with exit code {process.returncode}")
                
        except Exception as e:
            processing_logger.error(f"Processing failed with error: {e}")
            with open(log_file_path, 'a') as log_file:
                log_file.write(f"\nERROR: {e}\n")
        finally:
            with RecordingController._processing_lock:
                RecordingController._processing_pid = None

    def get_processing_status(self):
        """Get the current processing status and recent log content"""
        is_running = self._is_processing_running()
        log_file = self.log_dir / 'processing.log'
        
        recent_log = ""
        if log_file.exists():
            try:
                # Get last 50 lines of log
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    recent_log = ''.join(lines[-50:])
            except Exception:
                pass
        
        return {
            'is_processing': is_running,
            'pid': RecordingController._processing_pid,
            'log_file': str(log_file),
            'recent_log': recent_log
        }

    def process_recordings(self):
        """Trigger transcription processing"""
        # Check if already processing
        if self._is_processing_running():
            return {
                'success': False,
                'error': f'Processing already in progress (PID: {RecordingController._processing_pid}). Check logs/processing.log for progress.',
                'log_file': str(self.log_dir / 'processing.log')
            }
        
        try:
            log_file_path = self.log_dir / 'processing.log'
            
            # Start processing in a background thread
            thread = threading.Thread(
                target=self._run_processing,
                args=(log_file_path,),
                daemon=True
            )
            thread.start()
            
            # Give the thread a moment to start the process
            time.sleep(0.5)
            
            return {
                'success': True,
                'message': 'Processing started in background. Check logs/processing.log for progress.',
                'log_file': str(log_file_path),
                'pid': RecordingController._processing_pid
            }
            
        except Exception as e:
            processing_logger.error(f"Failed to start processing: {e}")
            return {
                'success': False,
                'error': f"Failed to start processing: {str(e)}"
            }
    
    def abort_recording(self):
        """Abort the current recording without saving"""
        # Check if recording
        if not self.pending_file.exists():
            return {
                'success': False,
                'error': "No recording in progress"
            }
        
        # Get meeting info for logging
        lines = self.pending_file.read_text().strip().split('\n')
        meeting_name = lines[0]
        
        # Stop recording via OBS controller
        try:
            result = subprocess.run(
                [self.python_cmd, str(self.obs_controller), 'stop'],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Give OBS time to finalize file
            time.sleep(2)
            
            # Find and delete the latest recording
            recording_path = os.environ.get('RECORDING_PATH', '.')
            recording_path = recording_path.replace('~', os.path.expanduser('~'))
            
            # Find latest .mkv file
            result = subprocess.run(
                f'find "{recording_path}" -maxdepth 1 -name "*.mkv" -print0 | xargs -0 ls -t | head -n 1',
                shell=True,
                capture_output=True,
                text=True
            )
            
            latest_recording = result.stdout.strip()
            
            if latest_recording and os.path.exists(latest_recording):
                os.remove(latest_recording)
                print(f"Deleted aborted recording: {latest_recording}")
            
            # Remove pending file
            self.pending_file.unlink()
            
            return {
                'success': True,
                'message': f"Recording aborted for '{meeting_name}' (file deleted)"
            }
            
        except subprocess.CalledProcessError as e:
            # Even if OBS stop failed, remove pending file
            if self.pending_file.exists():
                self.pending_file.unlink()
            return {
                'success': False,
                'error': f"Failed to stop recording: {e.stderr}"
            }
        except Exception as e:
            # Even if deletion failed, remove pending file
            if self.pending_file.exists():
                self.pending_file.unlink()
            return {
                'success': False,
                'error': f"Error during abort: {str(e)}"
            }
    
    def discard_recording(self, recording_id):
        """Discard a recording from the queue"""
        # This would require implementing the discard logic
        # For now, return not implemented
        return {
            'success': False,
            'error': 'Discard functionality not yet implemented'
        }
