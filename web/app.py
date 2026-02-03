#!/usr/bin/env python3
"""
Flask web server for Meeting Transcriber
Provides a web UI for managing recordings and integrating with Google Calendar
"""

import os
import sys
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

# Add parent directory to path to import from scripts
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import our modules
from web.recorder import RecordingController
from web.calendar_service import CalendarService

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Initialize services
recorder = RecordingController()
calendar_service = CalendarService()


@app.route('/')
def index():
    """Serve the main UI page"""
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current recording status and processing queue"""
    try:
        status = recorder.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/meetings', methods=['GET'])
def get_meetings():
    """Get meetings for a specific date from Google Calendar"""
    try:
        # Get date parameter (YYYY-MM-DD format) or use today
        date_str = request.args.get('date')
        target_date = None
        
        if date_str:
            from datetime import datetime
            # Parse as local date (no timezone)
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        meetings = calendar_service.get_meetings_for_date(target_date)
        
        # Return date info for the frontend
        if target_date is None:
            from datetime import datetime
            target_date = datetime.now()
        
        return jsonify({
            'meetings': meetings,
            'date': target_date.strftime('%Y-%m-%d')
        })
    except Exception as e:
        # If calendar isn't set up yet, return empty list
        return jsonify({'meetings': [], 'error': str(e)})


@app.route('/api/start', methods=['POST'])
def start_recording():
    """Start a new recording"""
    try:
        data = request.get_json()
        meeting_name = data.get('meeting_name')
        attendees = data.get('attendees', [])
        
        if not meeting_name:
            return jsonify({'error': 'Meeting name is required'}), 400
        
        result = recorder.start_recording(meeting_name, attendees=attendees)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stop', methods=['POST'])
def stop_recording():
    """Stop the current recording"""
    try:
        result = recorder.stop_recording()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/abort', methods=['POST'])
def abort_recording():
    """Abort the current recording without saving"""
    try:
        result = recorder.abort_recording()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_recordings():
    """Trigger transcription processing"""
    try:
        result = recorder.process_recordings()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/discard', methods=['POST'])
def discard_recording():
    """Discard a recording from the queue"""
    try:
        data = request.get_json()
        recording_id = data.get('recording_id')
        
        result = recorder.discard_recording(recording_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def main():
    """Start the Flask server"""
    host = os.environ.get('WEB_HOST', '127.0.0.1')
    port = int(os.environ.get('WEB_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"🚀 Meeting Transcriber Web UI starting...")
    print(f"📍 Access at: http://{host}:{port}")
    print(f"⌨️  Press Ctrl+C to stop")
    
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
