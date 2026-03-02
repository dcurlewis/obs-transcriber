// Meeting Transcriber Web UI
// Handles UI interactions and API calls

class MeetingTranscriber {
    constructor() {
        this.isRecording = false;
        this.currentMeeting = null;
        this.meetings = [];
        this.queue = [];
        this.statusInterval = null;
        this.meetingsInterval = null;
        this.currentQueuePage = 1;
        this.queueItemsPerPage = 10;
        this.currentViewDate = new Date(); // Date being viewed
        this.todayDate = new Date(); // Actual today
        
        this.init();
    }
    
    init() {
        // Set up event listeners
        this.setupEventListeners();
        
        // Initial data load
        this.refreshStatus();
        this.refreshMeetings();
        this.updateCurrentTimeDisplay();
        
        // Auto-refresh status/queue every 5 seconds
        this.statusInterval = setInterval(() => this.refreshStatus(), 5000);
        
        // Auto-refresh meetings every 1 minute (only if viewing today)
        this.meetingsInterval = setInterval(() => {
            if (this.isViewingToday()) {
                this.refreshMeetings();
            }
        }, 60 * 1000);
        
        // Update current time display every second
        this.timeInterval = setInterval(() => this.updateCurrentTimeDisplay(), 1000);
    }

    isViewingToday() {
        return this.currentViewDate.toDateString() === this.todayDate.toDateString();
    }
    
    updateDateDisplay() {
        const dateEl = document.getElementById('current-date');
        const options = { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' };
        const dateText = this.currentViewDate.toLocaleDateString('en-US', options);
        
        const isToday = this.isViewingToday();
        const dayLabel = isToday ? '(Today)' : '';
        
        dateEl.innerHTML = `
            <div class="date-navigation">
                <button class="btn-nav" onclick="app.changeMeetingsDay(-1)" title="Previous day">‹</button>
                <span class="date-text">
                    ${dateText} ${dayLabel}
                    ${!isToday ? `<button class="btn-today" onclick="app.goToToday()">Today</button>` : ''}
                </span>
                <button class="btn-nav" onclick="app.changeMeetingsDay(1)" title="Next day">›</button>
            </div>
        `;
    }
    
    updateCurrentTimeDisplay() {
        const timeEl = document.getElementById('current-time');
        if (!timeEl) return;
        
        const now = new Date();
        const timeOptions = { 
            hour: 'numeric', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: true 
        };
        const dateOptions = {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        };
        
        const timeStr = now.toLocaleTimeString('en-US', timeOptions);
        const dateStr = now.toLocaleDateString('en-US', dateOptions);
        
        timeEl.textContent = `${dateStr}, ${timeStr}`;
    }
    
    setupEventListeners() {
        // Manual start button
        const manualStartBtn = document.getElementById('manual-start-btn');
        const manualInput = document.getElementById('manual-meeting-name');
        
        manualStartBtn.addEventListener('click', () => {
            const meetingName = manualInput.value.trim();
            if (meetingName) {
                this.startRecording(meetingName);
                manualInput.value = '';
            } else {
                this.showToast('Please enter a meeting name', 'error');
            }
        });
        
        // Allow Enter key in manual input
        manualInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                manualStartBtn.click();
            }
        });
        
        // Process all button
        const processAllBtn = document.getElementById('process-all-btn');
        processAllBtn.addEventListener('click', () => {
            this.processAllRecordings();
        });
    }
    
    async refreshStatus() {
        try {
            // Fetch status
            const statusResponse = await fetch('/api/status');
            const status = await statusResponse.json();
            
            this.isRecording = status.is_recording;
            this.currentMeeting = status.current_meeting;
            this.queue = status.queue;
            
            // Update recording indicator
            this.updateRecordingIndicator();
            
            // Update queue display
            this.updateQueueDisplay();
            
        } catch (error) {
            console.error('Error refreshing status:', error);
        }
    }
    
    async refreshMeetings() {
        try {
            // Format date as YYYY-MM-DD in local timezone (not UTC)
            const year = this.currentViewDate.getFullYear();
            const month = String(this.currentViewDate.getMonth() + 1).padStart(2, '0');
            const day = String(this.currentViewDate.getDate()).padStart(2, '0');
            const dateStr = `${year}-${month}-${day}`;
            
            const meetingsResponse = await fetch(`/api/meetings?date=${dateStr}`);
            const meetingsData = await meetingsResponse.json();
            this.meetings = meetingsData.meetings || [];

            this.updateMeetingsDisplay();
            this.updateDateDisplay();
            this.updateCurrentTimeDisplay();
        } catch (error) {
            console.log('Calendar not available:', error);
        }
    }
    
    changeMeetingsDay(offset) {
        // Change the viewed day by offset days
        const newDate = new Date(this.currentViewDate);
        newDate.setDate(newDate.getDate() + offset);
        this.currentViewDate = newDate;
        this.refreshMeetings();
    }
    
    goToToday() {
        this.currentViewDate = new Date(this.todayDate);
        this.refreshMeetings();
    }
    
    updateRecordingIndicator() {
        const indicator = document.getElementById('recording-indicator');
        
        if (this.isRecording && this.currentMeeting) {
            indicator.textContent = `Recording: ${this.currentMeeting.name}`;
            indicator.classList.add('recording');
        } else {
            indicator.textContent = 'Ready';
            indicator.classList.remove('recording');
        }
    }
    
    updateMeetingsDisplay() {
        const meetingsList = document.getElementById('meetings-list');
        const hasCurrentMeeting = Boolean(this.currentMeeting && this.currentMeeting.name);
        const hasMatchingMeeting = hasCurrentMeeting &&
            this.meetings.some(meeting => meeting.name === this.currentMeeting.name);
        const showManualRecordingCard = this.isRecording && hasCurrentMeeting && !hasMatchingMeeting;
        
        let meetingsHtml = '';
        if (this.meetings.length === 0) {
            if (!showManualRecordingCard) {
                meetingsHtml = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📅</div>
                        <div>No meetings scheduled for today</div>
                        <div style="font-size: 12px; margin-top: 8px;">
                            Use Quick Record below to start a manual recording
                        </div>
                    </div>
                `;
            }
        } else {
            meetingsHtml = this.meetings.map(meeting => {
                const isPast = meeting.is_past;
                const isCurrent = meeting.is_current;
                const isRecordingThis = this.isRecording &&
                    this.currentMeeting &&
                    this.currentMeeting.name === meeting.name;
                
                let buttonHtml;
                if (isRecordingThis) {
                    buttonHtml = `
                        <div class="button-group">
                            <button class="btn btn-success btn-small" onclick="app.stopRecording()">
                                <span class="icon">■</span> Stop
                            </button>
                            <button class="btn btn-danger btn-small" onclick="app.abortRecording()">
                                <span class="icon">✕</span> Abort
                            </button>
                        </div>
                    `;
                } else if (this.isRecording) {
                    buttonHtml = `
                        <button class="btn btn-small" disabled>
                            Recording...
                        </button>
                    `;
                } else if (isPast) {
                    buttonHtml = `
                        <button class="btn btn-small" disabled>
                            Ended
                        </button>
                    `;
                } else {
                    buttonHtml = `
                        <button class="btn btn-primary btn-small" onclick="app.startRecording('${this.escapeHtml(meeting.name)}')">
                            <span class="icon">▶</span> Start
                        </button>
                    `;
                }
                
                const cardClass = isCurrent ? 'meeting-card current' : isPast ? 'meeting-card past' : 'meeting-card';
                
                let conferenceLink = '';
                if (meeting.has_conference && meeting.conference_url) {
                    conferenceLink = ` <a href="${meeting.conference_url}" target="_blank" rel="noopener noreferrer" class="conference-link" title="Join meeting">🔗</a>`;
                }
                
                return `
                    <div class="${cardClass}">
                        <div class="meeting-info">
                            <span class="meeting-time">${meeting.start_time} - ${meeting.end_time}</span>
                            <span class="meeting-separator">•</span>
                            <span class="meeting-name">${this.escapeHtml(meeting.name)}${conferenceLink}</span>
                        </div>
                        ${buttonHtml}
                    </div>
                `;
            }).join('');
        }

        let manualRecordingHtml = '';
        if (showManualRecordingCard) {
            manualRecordingHtml = `
                <div class="meeting-card current">
                    <div class="meeting-info">
                        <span class="meeting-time">Now</span>
                        <span class="meeting-separator">•</span>
                        <span class="meeting-name">${this.escapeHtml(this.currentMeeting.name)} (Quick Record)</span>
                    </div>
                    <div class="button-group">
                        <button class="btn btn-success btn-small" onclick="app.stopRecording()">
                            <span class="icon">■</span> Stop
                        </button>
                        <button class="btn btn-danger btn-small" onclick="app.abortRecording()">
                            <span class="icon">✕</span> Abort
                        </button>
                    </div>
                </div>
            `;
        }

        meetingsList.innerHTML = `${manualRecordingHtml}${meetingsHtml}`;
    }
    
    updateQueueDisplay() {
        const queueList = document.getElementById('queue-list');
        
        if (this.queue.length === 0) {
            queueList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">✓</div>
                    <div>No recordings in queue</div>
                </div>
            `;
            return;
        }
        
        // Calculate pagination
        const totalPages = Math.ceil(this.queue.length / this.queueItemsPerPage);
        const startIndex = (this.currentQueuePage - 1) * this.queueItemsPerPage;
        const endIndex = startIndex + this.queueItemsPerPage;
        const pageItems = this.queue.slice(startIndex, endIndex);
        
        // Render queue items
        const itemsHtml = pageItems.map(item => {
            const statusClass = item.status === 'recorded' ? 'pending' : 
                              item.status === 'processing' ? 'processing' : 'completed';
            
            const statusIcon = item.status === 'recorded' ? '⏳' : 
                             item.status === 'processing' ? '⚙️' : '✓';
            
            const statusLabel = item.status === 'recorded' ? 'Pending' : 
                              item.status === 'processing' ? 'Processing' : 'Done';
            
            // Format date: "20240203_1430" -> "Feb 3, 2024 2:30 PM"
            let formattedDate = item.date;
            try {
                if (item.date.match(/^\d{8}_\d{4}$/)) {
                    const year = item.date.substring(0, 4);
                    const month = item.date.substring(4, 6);
                    const day = item.date.substring(6, 8);
                    const hour = item.date.substring(9, 11);
                    const minute = item.date.substring(11, 13);
                    const dateObj = new Date(year, month - 1, day, hour, minute);
                    formattedDate = dateObj.toLocaleDateString('en-US', {
                        month: 'short', day: 'numeric', year: 'numeric',
                        hour: 'numeric', minute: '2-digit'
                    });
                }
            } catch (e) {
                // Use original if parsing fails
            }

            // Add discard button for pending recordings
            let actionButtons = '';
            if (item.status === 'recorded') {
                actionButtons = `
                    <div class="queue-actions">
                        <button class="btn btn-danger btn-small"
                                onclick="app.discardRecording('${this.escapeHtml(item.path)}', '${this.escapeHtml(item.name)}')">
                            <span class="icon">🗑️</span> Discard
                        </button>
                    </div>
                `;
            }

            return `
                <div class="queue-item">
                    <div class="queue-info">
                        <span class="queue-status ${statusClass}">${statusIcon} ${statusLabel}</span>
                        <span class="queue-separator">•</span>
                        <span class="queue-name">${this.escapeHtml(item.name)}</span>
                        <span class="queue-separator">•</span>
                        <span class="queue-date">${formattedDate}</span>
                    </div>
                    ${actionButtons}
                </div>
            `;
        }).join('');
        
        // Render pagination controls
        let paginationHtml = '';
        if (totalPages > 1) {
            const prevDisabled = this.currentQueuePage === 1 ? 'disabled' : '';
            const nextDisabled = this.currentQueuePage === totalPages ? 'disabled' : '';
            
            paginationHtml = `
                <div class="pagination">
                    <button class="btn btn-small" ${prevDisabled} onclick="app.changeQueuePage(${this.currentQueuePage - 1})">
                        ← Previous
                    </button>
                    <span class="pagination-info">
                        Page ${this.currentQueuePage} of ${totalPages} 
                        (${this.queue.length} total)
                    </span>
                    <button class="btn btn-small" ${nextDisabled} onclick="app.changeQueuePage(${this.currentQueuePage + 1})">
                        Next →
                    </button>
                </div>
            `;
        }
        
        queueList.innerHTML = itemsHtml + paginationHtml;
    }
    
    changeQueuePage(newPage) {
        const totalPages = Math.ceil(this.queue.length / this.queueItemsPerPage);
        if (newPage >= 1 && newPage <= totalPages) {
            this.currentQueuePage = newPage;
            this.updateQueueDisplay();
        }
    }
    
    async startRecording(meetingName) {
        // Find the meeting in our list to get attendees
        const meeting = this.meetings.find(m => m.name === meetingName);
        const attendees = meeting?.attendees || [];
        
        try {
            const response = await fetch('/api/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    meeting_name: meetingName,
                    attendees: attendees
                }),
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showToast(`Recording started for "${meetingName}"`, 'success');
                if (result.obs_was_started) {
                    this.showToast('OBS was launched automatically', 'success');
                }
                // Refresh both status and meetings to update button states
                await this.refreshStatus();
                await this.refreshMeetings();
            } else {
                this.showToast(result.error || 'Failed to start recording', 'error');
            }
        } catch (error) {
            this.showToast('Error starting recording: ' + error.message, 'error');
        }
    }
    
    async stopRecording() {
        try {
            const response = await fetch('/api/stop', {
                method: 'POST',
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showToast('Recording stopped and queued for processing', 'success');
                // Refresh both status and meetings to update button states
                await this.refreshStatus();
                await this.refreshMeetings();
            } else {
                this.showToast(result.error || 'Failed to stop recording', 'error');
            }
        } catch (error) {
            this.showToast('Error stopping recording: ' + error.message, 'error');
        }
    }
    
    async abortRecording() {
        // Confirm before aborting
        if (!confirm('Are you sure you want to abort this recording? The video file will be deleted.')) {
            return;
        }

        try {
            const response = await fetch('/api/abort', {
                method: 'POST',
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('Recording aborted (file deleted)', 'success');
                // Refresh both status and meetings to update button states
                await this.refreshStatus();
                await this.refreshMeetings();
            } else {
                this.showToast(result.error || 'Failed to abort recording', 'error');
            }
        } catch (error) {
            this.showToast('Error aborting recording: ' + error.message, 'error');
        }
    }

    async discardRecording(recordingPath, meetingName) {
        // Confirm before discarding
        if (!confirm(`Are you sure you want to discard "${meetingName}"? The recording file will be deleted.`)) {
            return;
        }

        try {
            const response = await fetch('/api/discard', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recording_id: recordingPath
                }),
            });

            const result = await response.json();

            if (result.success) {
                if (result.warning) {
                    this.showToast(`Discarded: ${result.warning}`, 'warning');
                } else {
                    this.showToast('Recording discarded successfully', 'success');
                }

                // Refresh queue and check pagination
                await this.refreshStatus();

                // Adjust page if needed
                const totalPages = Math.ceil(this.queue.length / this.queueItemsPerPage);
                if (this.currentQueuePage > totalPages && totalPages > 0) {
                    this.currentQueuePage = totalPages;
                }

                this.updateQueueDisplay();
            } else {
                this.showToast(result.error || 'Failed to discard recording', 'error');
            }
        } catch (error) {
            this.showToast('Error discarding recording: ' + error.message, 'error');
        }
    }
    
    async processAllRecordings() {
        try {
            const response = await fetch('/api/process', {
                method: 'POST',
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showToast('Processing started in background', 'success');
                this.refreshStatus();
            } else {
                this.showToast(result.error || 'Failed to start processing', 'error');
            }
        } catch (error) {
            this.showToast('Error starting processing: ' + error.message, 'error');
        }
    }
    
    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type}`;
        
        // Trigger reflow to restart animation
        void toast.offsetWidth;
        
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the app when DOM is ready
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new MeetingTranscriber();
});
